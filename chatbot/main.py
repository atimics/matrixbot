"""
Main entry point for the chatbot application.
"""

import asyncio
import logging
import os
from pathlib import Path

from chatbot.core.orchestrator import ContextAwareOrchestrator, OrchestratorConfig


def setup_logging() -> None:
    """Set up logging configuration."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("chatbot.log"),
        ],
    )


async def main() -> None:
    """Main application entry point."""
    setup_logging()
    logger = logging.getLogger(__name__)
    
    logger.info("Starting chatbot application...")
    
    # Load configuration with more responsive settings
    config = OrchestratorConfig(
        db_path=os.getenv("CHATBOT_DB_PATH", "chatbot.db"),
        observation_interval=float(os.getenv("OBSERVATION_INTERVAL", "2")),  # Check every 2 seconds
        max_cycles_per_hour=int(os.getenv("MAX_CYCLES_PER_HOUR", "300")),  # Allow up to 5 per minute
        ai_model=os.getenv("AI_MODEL", "openai/gpt-4o-mini"),
    )
    
    # Create and start orchestrator
    orchestrator = ContextAwareOrchestrator(config)
    
    try:
        await orchestrator.start()
    except KeyboardInterrupt:
        logger.info("Shutting down gracefully...")
    except Exception as e:
        logger.error(f"Application error: {e}")
        raise
    finally:
        await orchestrator.stop()
        logger.info("Chatbot application stopped")


if __name__ == "__main__":
    asyncio.run(main())
