"""
Main entry point for the chatbot application.

This unified script can run the chatbot in two modes:
1. Standalone mode (default): Just the chatbot without UI
2. UI mode (--with-ui): Chatbot with management web interface

Copyright (c) 2025 Ratimics
Licensed under Creative Commons Attribution-NonCommercial 4.0 International License.
For commercial use, contact the copyright holder for permission.
"""

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path
from threading import Thread
from typing import Optional

import uvicorn

from chatbot.config import settings
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


class ChatbotApp:
    """Main application class that manages the chatbot and optionally the UI server."""
    
    def __init__(self, with_ui: bool = False, ui_host: str = "0.0.0.0", ui_port: int = 8000):
        self.with_ui = with_ui
        self.ui_host = ui_host
        self.ui_port = ui_port
        self.orchestrator = None
        self.api_server = None
        self.server_thread = None
        self.running = False
        
    async def setup_orchestrator(self):
        """Set up the main orchestrator with configuration."""
        config = OrchestratorConfig(
            db_path=settings.chatbot_db_path,
            processing_config=ProcessingConfig(
                enable_node_based_processing=True,  # Advanced node-based mode
                observation_interval=settings.observation_interval,
                max_cycles_per_hour=settings.max_cycles_per_hour,
            ),
            ai_model=settings.ai.model,
        )
        
        self.orchestrator = MainOrchestrator(config)
        logger.info("Orchestrator configured successfully")
        
    def setup_api_server(self):
        """Set up the FastAPI server for the management UI."""
        if not self.orchestrator:
            raise RuntimeError("Orchestrator must be set up before API server")
            
        # Import here to avoid circular imports
        from chatbot.api_server import create_secure_api_server
        self.api_server = create_secure_api_server(self.orchestrator, settings)
        logger.debug("Secure API server configured successfully")
        
    def start_api_server(self):
        """Start the API server in a separate thread."""
        def run_server():
            config = uvicorn.Config(
                self.api_server,
                host=self.ui_host,
                port=self.ui_port,
                log_level="info"
            )
            server = uvicorn.Server(config)
            asyncio.run(server.serve())
            
        self.server_thread = Thread(target=run_server, daemon=True)
        self.server_thread.start()
        logger.info(f"API server started on http://{self.ui_host}:{self.ui_port}")
        logger.info(f"Management UI available at http://localhost:{self.ui_port}")
        
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
        
        if self.with_ui:
            logger.debug("Starting Chatbot with Management UI...")
        else:
            logger.debug("Starting Chatbot in standalone mode...")
        
        # Set up signal handlers for graceful shutdown
        def signal_handler(signum, frame):
            logger.debug(f"Received signal {signum}, shutting down gracefully...")
            self.running = False
            
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        try:
            # Set up orchestrator
            await self.setup_orchestrator()
            
            # Set up and start API server if UI mode is enabled
            if self.with_ui:
                self.setup_api_server()
                self.start_api_server()
            
            # Start chatbot
            await self.start_chatbot()
            
            self.running = True
            
            if self.with_ui:
                logger.info("All systems started successfully!")
                logger.info("=" * 60)
                logger.info("Chatbot Management Console is now running:")
                logger.info("  - Chatbot: Active and processing")
                logger.info(f"  - API Server: http://localhost:{self.ui_port}")
                logger.info(f"  - Management UI: http://localhost:{self.ui_port}")
                logger.info(f"  - API Documentation: http://localhost:{self.ui_port}/docs")
                logger.info("=" * 60)
            else:
                logger.info("Chatbot started successfully in standalone mode!")
                logger.info("Press Ctrl+C to stop the chatbot.")
            
            # Keep running until signal received
            while self.running:
                await asyncio.sleep(1)
                
        except KeyboardInterrupt:
            logger.debug("Keyboard interrupt received, shutting down...")
        except Exception as e:
            logger.error(f"Application error: {e}")
            raise
        finally:
            # Clean shutdown
            await self.stop_chatbot()
            logger.debug("Application shutdown complete")


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="RatiChat Bot - AI-powered social media chatbot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m chatbot.main                    # Run chatbot only
  python -m chatbot.main --with-ui          # Run with web UI
  python -m chatbot.main --with-ui --port 8080  # Run with UI on port 8080
        """
    )
    
    parser.add_argument(
        "--with-ui", 
        action="store_true", 
        help="Run with management web interface"
    )
    
    parser.add_argument(
        "--host", 
        default="0.0.0.0", 
        help="Host for the web interface (default: 0.0.0.0)"
    )
    
    parser.add_argument(
        "--port", 
        type=int, 
        default=8000, 
        help="Port for the web interface (default: 8000)"
    )
    
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Override log level from configuration"
    )
    
    return parser.parse_args()


async def main() -> None:
    """Main application entry point."""
    args = parse_arguments()
    
    # Override log level if specified
    if args.log_level:
        settings.log_level = args.log_level.lower()
    
    # Create and run the application
    app = ChatbotApp(
        with_ui=args.with_ui,
        ui_host=args.host,
        ui_port=args.port
    )
    
    await app.run()


if __name__ == "__main__":
    asyncio.run(main())
