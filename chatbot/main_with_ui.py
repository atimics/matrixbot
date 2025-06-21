"""
Main entry point for running the chatbot with management UI.

This script starts both the chatbot system and the FastAPI management server,
allowing for comprehensive monitoring and control of the bot through a web interface.
"""

import asyncio
import logging
import signal
import sys
from pathlib import Path
from threading import Thread

import uvicorn

from chatbot.api_server import create_secure_api_server
from chatbot.config import settings  # This imports from the config package
from chatbot.core.orchestration import MainOrchestrator, OrchestratorConfig, ProcessingConfig

logger = logging.getLogger(__name__)


def setup_logging() -> None:
    """Set up logging configuration."""
    # Convert string log level to logging constant
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("chatbot.log"),
        ],
    )


class ChatbotWithUI:
    """Main application class that manages both the chatbot and UI server."""
    
    def __init__(self):
        self.orchestrator = None
        self.api_server = None
        self.server_thread = None
        self.running = False
        
    async def setup_orchestrator(self):
        """Set up the main orchestrator with configuration."""
        config = OrchestratorConfig(
            db_path=settings.chatbot_db_path,
            processing_config=ProcessingConfig(
                enable_node_based_processing=True,  # Start with traditional mode
                observation_interval=settings.OBSERVATION_INTERVAL,
                max_cycles_per_hour=settings.MAX_CYCLES_PER_HOUR,
            ),
            ai_model=settings.AI_MODEL,
        )
        
        self.orchestrator = MainOrchestrator(config)
        logger.info("Orchestrator configured successfully")
        
    def setup_api_server(self):
        """Set up the FastAPI server for the management UI."""
        if not self.orchestrator:
            raise RuntimeError("Orchestrator must be set up before API server")
            
        self.api_server = create_secure_api_server(self.orchestrator, settings)
        logger.info("Secure API server configured successfully")
        
    def start_api_server(self):
        """Start the API server in a separate thread."""
        def run_server():
            config = uvicorn.Config(
                self.api_server,
                host="0.0.0.0",
                port=8000,
                log_level="info"
            )
            server = uvicorn.Server(config)
            asyncio.run(server.serve())
            
        self.server_thread = Thread(target=run_server, daemon=True)
        self.server_thread.start()
        logger.info("API server started on http://0.0.0.0:8000")
        logger.info("Management UI available at http://localhost:8000")
        
    async def start_chatbot(self):
        """Start the chatbot orchestrator."""
        if not self.orchestrator:
            raise RuntimeError("Orchestrator must be set up before starting")
            
        await self.orchestrator.start()
        logger.info("Chatbot orchestrator started")
        
    async def stop_chatbot(self):
        """Stop the chatbot orchestrator."""
        if self.orchestrator:
            await self.orchestrator.stop()
            logger.info("Chatbot orchestrator stopped")
            
    async def run(self):
        """Main run loop for the application."""
        setup_logging()
        logger.info("Starting Chatbot with Management UI...")
        
        # Set up signal handlers for graceful shutdown
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, shutting down gracefully...")
            self.running = False
            
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        try:
            # Set up components
            await self.setup_orchestrator()
            self.setup_api_server()
            
            # Start API server
            self.start_api_server()
            
            # Start chatbot
            await self.start_chatbot()
            
            self.running = True
            logger.info("All systems started successfully!")
            logger.info("=" * 60)
            logger.info("Chatbot Management Console is now running:")
            logger.info("  - Chatbot: Active and processing")
            logger.info("  - API Server: http://localhost:8000")
            logger.info("  - Management UI: http://localhost:8000")
            logger.info("  - API Documentation: http://localhost:8000/docs")
            logger.info("=" * 60)
            
            # Keep running until signal received
            while self.running:
                await asyncio.sleep(1)
                
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received, shutting down...")
        except Exception as e:
            logger.error(f"Application error: {e}")
            raise
        finally:
            # Clean shutdown
            await self.stop_chatbot()
            logger.info("Application shutdown complete")


async def main():
    """Main entry point."""
    app = ChatbotWithUI()
    await app.run()


if __name__ == "__main__":
    asyncio.run(main())
