import asyncio
import os
import logging
import colorlog  # Added for colorful logging
from dotenv import load_dotenv

from message_bus import MessageBus
from matrix_gateway_service import MatrixGatewayService
from ai_inference_service import AIInferenceService
from room_logic_service import RoomLogicService
from summarization_service import SummarizationService
from image_caption_service import ImageCaptionService
from image_analysis_service import ImageAnalysisService
from image_cache_service import ImageCacheService  # Added new service
from ollama_inference_service import OllamaInferenceService
from tool_manager import ToolLoader, ToolRegistry
from tool_execution_service import ToolExecutionService
import database
import prompt_constructor  # Added to set the message bus reference

def configure_logging():
    """Configure colorful logging with different colors for different log levels."""
    # Create a colorful formatter
    formatter = colorlog.ColoredFormatter(
        "%(log_color)s%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        reset=True,
        log_colors={
            'DEBUG': 'cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'red,bg_white',
        },
        secondary_log_colors={},
        style='%'
    )
    
    # Create console handler with the colorful formatter
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()  # Clear any existing handlers
    root_logger.addHandler(console_handler)
    
    # Make some specific loggers more verbose for debugging
    logging.getLogger("JsonCentricAI").setLevel(logging.INFO)
    logging.getLogger("ActionExecution").setLevel(logging.INFO)
    logging.getLogger("JsonCentricRLS").setLevel(logging.INFO)

async def main() -> None:
    configure_logging()
    logger = logging.getLogger(__name__)
    load_dotenv()
    logger.info("Orchestrator: Starting bot services...")

    # Define and Initialize database path
    db_path = os.getenv("DATABASE_PATH", "matrix_bot_soa.db")
    await database.initialize_database(db_path)

    # Initialize Message Bus
    bus = MessageBus()

    # Initialize Services
    # Bot display name will be set via BotDisplayNameReadyEvent
    # Matrix Gateway will fetch it and publish it. Other services subscribe.
    matrix_gateway = MatrixGatewayService(bus)
    ai_inference = AIInferenceService(bus) # For OpenRouter
    ollama_inference = OllamaInferenceService(bus) # For Ollama

    # Initialize Image Cache Service (needs to be early to handle image processing)
    image_cache = ImageCacheService(bus, db_path)

    # Initialize Tooling Infrastructure (Phase 1)
    tool_loader = ToolLoader() # Uses default 'available_tools/' directory
    loaded_tools = tool_loader.load_tools()
    tool_registry = ToolRegistry(loaded_tools)
    logger.info(f"Orchestrator: Loaded {len(loaded_tools)} tools into registry.")
    for tool_def in tool_registry.get_all_tool_definitions():
        logger.info(f"Orchestrator: Registered tool - Name: {tool_def.get('function',{}).get('name')}, Desc: {tool_def.get('function',{}).get('description')}")

    tool_execution_service = ToolExecutionService(bus, tool_registry)

    # Pass ToolRegistry and MatrixGateway to services that need them
    # RoomLogicService will be modified to accept this in its __init__
    room_logic = RoomLogicService(bus, tool_registry=tool_registry, db_path=db_path, matrix_client=matrix_gateway.get_client())
    summarization = SummarizationService(bus)
    image_caption = ImageCaptionService(bus)  # Remove matrix_gateway dependency
    image_analysis = ImageAnalysisService(bus)

    services = [
        matrix_gateway,
        image_cache,  # Start image cache early
        ai_inference,
        ollama_inference,
        room_logic,
        summarization,
        image_caption,
        image_analysis,
        tool_execution_service,
    ]
    
    # Set up message bus reference for prompt constructor
    prompt_constructor.set_message_bus(bus)
    logger.info("Orchestrator: Message bus reference set for prompt constructor")
    
    service_tasks = []
    try:
        # Start all service run loops
        for service in services:
            service_tasks.append(asyncio.create_task(service.run()))
        
        # After matrix gateway starts, give it time to initialize, then set matrix client reference
        # This could be improved with proper event signaling, but for now use a small delay
        await asyncio.sleep(2.0)  # Increased delay to ensure proper initialization
        if matrix_gateway.get_client():
            image_cache.set_matrix_client(matrix_gateway.get_client())
            logger.info("Orchestrator: Image cache service connected to Matrix client")
        else:
            logger.warning("Orchestrator: Matrix client not ready for image cache service")
        
        logger.info("Orchestrator: All services started. Running...")
        # Keep main running, or wait for a specific condition like KeyboardInterrupt
        # For now, let services run until an error or shutdown signal
        if service_tasks:
            done, pending = await asyncio.wait(service_tasks, return_when=asyncio.FIRST_COMPLETED)
            # If any task finishes (e.g. MatrixGateway sync error), it will trigger shutdown sequence.
            logger.warning(f"Orchestrator: A service task completed. Done: {len(done)}, Pending: {len(pending)}")
            # If a task fails, log the exception and request shutdown of other services
            for task in done:
                try:
                    # This will re-raise the exception if the task failed
                    task.result() 
                    # If no exception, it means the task completed normally (e.g. service stopped via its own logic)
                    # Find the service name associated with this task
                    # service_name = next((name for name, t in service_tasks.items() if t == task), "Unknown Service")
                    # logger.info(f"Orchestrator: {service_name} task completed normally.") # Replaced print with logger
                except asyncio.CancelledError:
                    service_name = next((name for name, t in service_tasks.items() if t == task), "Unknown Service")
                    logger.info(f"Orchestrator: {service_name} task was cancelled.")
                except KeyboardInterrupt:
                    # Re-raise KeyboardInterrupt to trigger main's exception handler
                    logger.info("Orchestrator: KeyboardInterrupt from service task, propagating...")
                    raise
                except Exception as e:
                    logger.error(f"Orchestrator: Service task exited with error: {e}")
            
    except KeyboardInterrupt:
        logger.info("\nOrchestrator: KeyboardInterrupt received. Initiating shutdown...")
    except Exception as e:
        logger.error(f"Orchestrator: Unhandled exception in main: {e}")
    finally:
        logger.info("Orchestrator: Starting shutdown sequence for all services...")
        # Stop services (they should handle their own cleanup)
        for service in reversed(services): # Stop in reverse order of start perhaps
            if hasattr(service, 'stop'):
                logger.info(f"Orchestrator: Requesting stop for {service.__class__.__name__}...")
                await service.stop() # Services should set their internal _stop_event

        # Wait for service tasks to actually finish after stop is called
        # This assumes service.run() exits when its _stop_event is set.
        # Give them some time to clean up.
        if service_tasks:
            logger.info("Orchestrator: Allowing time for service run loops to exit...")
            # Initialize pending as empty list if not set from asyncio.wait above
            if 'pending' not in locals():
                pending = service_tasks
            
            # For tasks that were still pending when FIRST_COMPLETED happened
            for task in pending: # From the asyncio.wait above
                if not task.done():
                    task.cancel() # Force cancel if not stopped by service.stop()

            results = await asyncio.gather(*service_tasks, return_exceptions=True)
            for i, result in enumerate(results):
                service_name = services[i].__class__.__name__
                if isinstance(result, asyncio.CancelledError):
                    logger.info(f"Orchestrator: {service_name} task was cancelled.")
                elif isinstance(result, Exception):
                     logger.error(f"Orchestrator: {service_name} task exited with error during gather: {result}")
                # else:
                #     print(f"Orchestrator: {service_name} task completed normally.")


        # Shutdown message bus (waits for its internal listener tasks)
        await bus.shutdown()
        logger.info("Orchestrator: Bot shutdown complete.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Orchestrator: Main execution stopped by KeyboardInterrupt (already handled).")
    except Exception as e:
        logging.getLogger(__name__).error(f"Orchestrator: Critical error during asyncio.run: {type(e).__name__} - {e}")