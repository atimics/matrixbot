import asyncio
import os
from dotenv import load_dotenv

from message_bus import MessageBus
from matrix_gateway_service import MatrixGatewayService
from ai_inference_service import AIInferenceService
from room_logic_service import RoomLogicService
from summarization_service import SummarizationService
import database
from event_definitions import BotDisplayNameReadyEvent # For initial display name

async def main():
    load_dotenv()
    print("Orchestrator: Starting bot services...")

    # Initialize database
    database.initialize_database()

    # Initialize Message Bus
    bus = MessageBus()

    # Initialize Services
    # Bot display name will be set via BotDisplayNameReadyEvent
    # Matrix Gateway will fetch it and publish it. Other services subscribe.
    matrix_gateway = MatrixGatewayService(bus)
    ai_inference = AIInferenceService(bus)
    room_logic = RoomLogicService(bus) # Will get bot_display_name via event
    summarization = SummarizationService(bus) # Will get bot_display_name via event
    
    services = [matrix_gateway, ai_inference, room_logic, summarization]
    
    service_tasks = []
    try:
        # Start all service run loops
        for service in services:
            service_tasks.append(asyncio.create_task(service.run()))
        
        print("Orchestrator: All services started. Running...")
        # Keep main running, or wait for a specific condition like KeyboardInterrupt
        # For now, let services run until an error or shutdown signal
        if service_tasks:
            done, pending = await asyncio.wait(service_tasks, return_when=asyncio.FIRST_COMPLETED)
            # If any task finishes (e.g. MatrixGateway sync error), it will trigger shutdown sequence.
            print(f"Orchestrator: A service task completed. Done: {len(done)}, Pending: {len(pending)}")
            for task in done:
                try:
                    task.result() # Raise exception if task failed
                except Exception as e:
                    print(f"Orchestrator: Service task exited with error: {e}")
            
    except KeyboardInterrupt:
        print("\nOrchestrator: KeyboardInterrupt received. Initiating shutdown...")
    except Exception as e:
        print(f"Orchestrator: Unhandled exception in main: {e}")
    finally:
        print("Orchestrator: Starting shutdown sequence for all services...")
        # Stop services (they should handle their own cleanup)
        for service in reversed(services): # Stop in reverse order of start perhaps
            if hasattr(service, 'stop'):
                print(f"Orchestrator: Requesting stop for {service.__class__.__name__}...")
                await service.stop() # Services should set their internal _stop_event

        # Wait for service tasks to actually finish after stop is called
        # This assumes service.run() exits when its _stop_event is set.
        # Give them some time to clean up.
        if service_tasks:
            print("Orchestrator: Allowing time for service run loops to exit...")
            # For tasks that were still pending when FIRST_COMPLETED happened
            for task in pending: # From the asyncio.wait above
                if not task.done():
                    task.cancel() # Force cancel if not stopped by service.stop()

            results = await asyncio.gather(*service_tasks, return_exceptions=True)
            for i, result in enumerate(results):
                service_name = services[i].__class__.__name__
                if isinstance(result, asyncio.CancelledError):
                    print(f"Orchestrator: {service_name} task was cancelled.")
                elif isinstance(result, Exception):
                     print(f"Orchestrator: {service_name} task exited with error during gather: {result}")
                # else:
                #     print(f"Orchestrator: {service_name} task completed normally.")


        # Shutdown message bus (waits for its internal listener tasks)
        await bus.shutdown()
        print("Orchestrator: Bot shutdown complete.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Orchestrator: Main execution stopped by KeyboardInterrupt (already handled).")
    except Exception as e:
        print(f"Orchestrator: Critical error during asyncio.run: {type(e).__name__} - {e}")