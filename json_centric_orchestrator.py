#!/usr/bin/env python3
"""
JSON-Centric Main Orchestrator

This orchestrator demonstrates the new JSON-centric AI system with two-step processing:
1. Thinker AI analyzes context and generates natural language reasoning
2. Planner AI converts reasoning into structured action plans
3. Action Execution Service executes the planned actions

This replaces the previous tool-calling approach with structured prompting.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add the current directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

from message_bus import MessageBus
from action_registry_service import ActionRegistryService
from action_execution_service import ActionExecutionService
from json_centric_ai_service import JsonCentricAIService
from json_centric_room_logic_service import JsonCentricRoomLogicService
from matrix_gateway_service import MatrixGatewayService
from image_cache_service import ImageCacheService
from summarization_service import SummarizationService
from unified_channel_manager import UnifiedChannelManager
from farcaster_service import FarcasterService
from event_definitions import BotDisplayNameReadyEvent, RequestAISummaryCommand
import database

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()

class JsonCentricOrchestrator:
    """Main orchestrator for the JSON-centric AI system."""
    
    def __init__(self):
        self.db_path = os.getenv("DATABASE_PATH", "matrix_bot_soa.db")
        self.bot_display_name = "AI Assistant"
        
        # Core components
        self.message_bus = MessageBus()
        self.action_registry = ActionRegistryService()
        self.services = []
        
        # Initialize services
        self._initialize_services()
    
    def _initialize_services(self):
        """Initialize all services for the JSON-centric system."""
        logger.info("JsonCentricOrchestrator: Initializing services...")
        
        # Core AI services
        self.ai_service = JsonCentricAIService(self.message_bus, self.action_registry)
        
        # Initialize unified channel manager and Farcaster service
        self.unified_channel_manager = UnifiedChannelManager(self.message_bus, self.db_path)
        self.farcaster_service = FarcasterService(self.db_path, self.unified_channel_manager)
        
        self.action_executor = ActionExecutionService(
            self.message_bus, 
            self.action_registry
        )
        # Set references for unified channel integration
        self.action_executor.farcaster_service = self.farcaster_service
        self.action_executor.unified_channel_manager = self.unified_channel_manager
        
        # Room logic service (new JSON-centric version)
        self.room_logic_service = JsonCentricRoomLogicService(
            self.message_bus,
            self.action_registry,
            self.action_executor,
            self.ai_service,
            self.db_path,
            self.bot_display_name
        )
        
        # Matrix gateway service
        self.matrix_service = MatrixGatewayService(self.message_bus)
        
        # Image cache service for handling images/PDFs
        self.image_cache_service = ImageCacheService(self.message_bus, self.db_path)
        
        # Summarization service (can still be used for channel summaries)
        self.summarization_service = SummarizationService(self.message_bus, self.db_path)
        
        # Add all services to the list
        self.services = [
            self.ai_service,
            self.action_executor,
            self.room_logic_service,
            self.matrix_service,
            self.image_cache_service,
            self.summarization_service,
            self.unified_channel_manager
        ]
        
        # Subscribe to bot ready event to update channel summaries
        self.message_bus.subscribe(
            BotDisplayNameReadyEvent.get_event_type(),
            self._handle_bot_ready_for_summary_update
        )
        
        logger.info(f"JsonCentricOrchestrator: Initialized {len(self.services)} services")
    
    async def initialize_database(self):
        """Initialize the database with required tables."""
        logger.info("JsonCentricOrchestrator: Initializing database...")
        await database.initialize_database(self.db_path)
        
        # Initialize default prompts if needed
        system_prompt = await database.get_prompt(self.db_path, "system_default")
        if not system_prompt:
            default_prompt = """You are an AI assistant that analyzes user requests and provides helpful responses.
Your task is to understand what users need and determine the best actions to take.
Be helpful, accurate, and concise in your responses."""
            
            await database.store_prompt(self.db_path, "system_default", default_prompt)
            logger.info("JsonCentricOrchestrator: Stored default system prompt")
    
    async def start(self):
        """Start all services."""
        logger.info("JsonCentricOrchestrator: Starting system...")
        
        # Initialize database
        await self.initialize_database()
        
        # Start MessageBus subscription tasks now that event loop is running
        self.message_bus.start_tasks()
        
        # Start all services
        service_tasks = []
        for service in self.services:
            if hasattr(service, 'run'):
                try:
                    task = asyncio.create_task(service.run())
                    service_tasks.append(task)
                    logger.info(f"JsonCentricOrchestrator: Started {service.__class__.__name__}")
                except Exception as e:
                    logger.error(f"JsonCentricOrchestrator: Failed to start {service.__class__.__name__}: {e}")
        
        # Wait for Matrix gateway to initialize its client and log in
        max_wait_time = 30.0  # Maximum time to wait for Matrix client
        wait_interval = 0.5   # Check every 500ms
        waited_time = 0.0
        
        while waited_time < max_wait_time:
            matrix_client = self.matrix_service.get_client()
            if matrix_client and hasattr(matrix_client, 'logged_in') and matrix_client.logged_in:
                self.image_cache_service.set_matrix_client(matrix_client)
                logger.info("JsonCentricOrchestrator: Matrix client reference set in ImageCacheService")
                break
            
            await asyncio.sleep(wait_interval)
            waited_time += wait_interval
        
        if waited_time >= max_wait_time:
            logger.warning("JsonCentricOrchestrator: Timed out waiting for Matrix client - image processing may not work for MXC URLs")
        
        logger.info("JsonCentricOrchestrator: All services started successfully")
        logger.info("JsonCentricOrchestrator: System using JSON-centric orchestration with two-step AI processing")
        logger.info("JsonCentricOrchestrator: - Step 1: Thinker AI analyzes context")
        logger.info("JsonCentricOrchestrator: - Step 2: Planner AI generates structured actions")
        logger.info("JsonCentricOrchestrator: - Step 3: Action Executor performs actions")
        
        # Wait for all services
        if service_tasks:
            try:
                await asyncio.gather(*service_tasks, return_exceptions=True)
            except KeyboardInterrupt:
                logger.info("JsonCentricOrchestrator: Received shutdown signal")
            except Exception as e:
                logger.error(f"JsonCentricOrchestrator: Error in service tasks: {e}")
            finally:
                await self.stop()
        else:
            logger.warning("JsonCentricOrchestrator: No service tasks to wait for")
            await self.stop()
    
    async def stop(self):
        """Stop all services."""
        logger.info("JsonCentricOrchestrator: Stopping system...")
        
        # Stop all services
        for service in self.services:
            if hasattr(service, 'stop'):
                try:
                    await service.stop()
                    logger.info(f"JsonCentricOrchestrator: Stopped {service.__class__.__name__}")
                except Exception as e:
                    logger.error(f"JsonCentricOrchestrator: Error stopping {service.__class__.__name__}: {e}")
        
        # Shutdown message bus
        await self.message_bus.shutdown()
        
        logger.info("JsonCentricOrchestrator: System stopped")

    async def _handle_bot_ready_for_summary_update(self, event: BotDisplayNameReadyEvent) -> None:
        """Handle bot ready event by updating channel summaries to prevent stale data."""
        logger.info("JsonCentricOrchestrator: Bot is ready, updating channel summaries to prevent stale data...")
        
        try:
            # Get all active channels
            channels = await database.get_all_channels(self.db_path)
            
            if not channels:
                logger.info("JsonCentricOrchestrator: No channels found for summary update")
                return
            
            logger.info(f"JsonCentricOrchestrator: Found {len(channels)} channels, updating summaries...")
            
            # Update summary for each channel
            for channel in channels:
                channel_id = channel["channel_id"]
                channel_type = channel.get("channel_type", "unknown")
                
                try:
                    # Get recent messages for the channel
                    messages = await database.get_channel_messages(
                        self.db_path, 
                        channel_id, 
                        limit=50,  # Get more messages for better summary
                        include_ai_replied=True
                    )
                    
                    if not messages:
                        logger.debug(f"JsonCentricOrchestrator: No messages found for channel {channel_id}")
                        continue
                    
                    # Convert database messages to HistoricalMessage format for summary
                    from event_definitions import HistoricalMessage
                    historical_messages = []
                    
                    for msg in messages:
                        historical_msg = HistoricalMessage(
                            role="user",  # Channel messages are from users
                            content=msg["content"],
                            event_id=msg["message_id"]
                        )
                        historical_messages.append(historical_msg)
                    
                    # Reverse to get chronological order for summary
                    historical_messages.reverse()
                    
                    # Create and publish summary request command
                    summary_command = RequestAISummaryCommand(
                        room_id=channel_id,
                        force_update=True,  # Force update to refresh stale summaries
                        messages_to_summarize=historical_messages,
                        last_event_id_in_messages=messages[0]["message_id"] if messages else None
                    )
                    
                    await self.message_bus.publish(summary_command)
                    logger.info(f"JsonCentricOrchestrator: Requested summary update for channel {channel_id} ({channel_type})")
                    
                except Exception as e:
                    logger.error(f"JsonCentricOrchestrator: Error updating summary for channel {channel_id}: {e}")
                    continue
            
            logger.info("JsonCentricOrchestrator: Completed channel summary update requests")
            
        except Exception as e:
            logger.error(f"JsonCentricOrchestrator: Error during channel summary update: {e}")

def main():
    """Main entry point."""
    logger.info("Starting JSON-Centric Matrix Bot with Structured AI Orchestration")
    
    orchestrator = JsonCentricOrchestrator()
    
    try:
        asyncio.run(orchestrator.start())
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()