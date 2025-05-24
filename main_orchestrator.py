import asyncio
import os
import logging
from dotenv import load_dotenv

from message_bus import MessageBus
from matrix_gateway_service import MatrixGatewayService
from ai_inference_service import AIInferenceService
from room_logic_service import RoomLogicService
from summarization_service import SummarizationService
from image_caption_service import ImageCaptionService
from image_analysis_service import ImageAnalysisService
from ollama_inference_service import OllamaInferenceService
from tool_manager import ToolLoader, ToolRegistry
from tool_execution_service import ToolExecutionService
import database

def configure_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

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

    # Initialize Tooling Infrastructure (Phase 1)
    tool_loader = ToolLoader() # Uses default 'available_tools/' directory
    loaded_tools = tool_loader.load_tools()
    tool_registry = ToolRegistry(loaded_tools)
    logger.info(f"Orchestrator: Loaded {len(loaded_tools)} tools into registry.")
    for tool_def in tool_registry.get_all_tool_definitions():
        logger.info(f"Orchestrator: Registered tool - Name: {tool_def.get('function',{}).get('name')}, Desc: {tool_def.get('function',{}).get('description')}")

    tool_execution_service = ToolExecutionService(bus, tool_registry)

    # Pass ToolRegistry to services that need it (e.g., RoomLogicService)
    # RoomLogicService will be modified to accept this in its __init__
    room_logic = RoomLogicService(bus, tool_registry=tool_registry, db_path=db_path)
    summarization = SummarizationService(bus)
    image_caption = ImageCaptionService(bus)
    image_analysis = ImageAnalysisService(bus)

    services = [
        matrix_gateway,
        ai_inference,
        ollama_inference,
        room_logic,
        summarization,
        image_caption,
        image_analysis,
        tool_execution_service,
    ]
    
    service_tasks = []
    try:
        # Start all service run loops
        for service in services:
            service_tasks.append(asyncio.create_task(service.run()))
        
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