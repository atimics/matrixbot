"""
Main entry point for the chatbot application.

Copyright (c) 2025 Ratimics
Licensed under Creative Commons Attribution-NonCommercial 4.0 International License.
For commercial use, contact the copyright holder for permission.
"""

import asyncio
import logging
from pathlib import Path

from chatbot.config import settings
from chatbot.core.container import DependencyContainer
from chatbot.core.orchestration import OrchestratorConfig, ProcessingConfig


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

    # Load configuration with node-based processing
    config = OrchestratorConfig(
        db_path=settings.CHATBOT_DB_PATH,
        processing_config=ProcessingConfig(
            enable_node_based_processing=True,  # Advanced node-based mode
            observation_interval=settings.OBSERVATION_INTERVAL,
            max_cycles_per_hour=settings.MAX_CYCLES_PER_HOUR,
            traditional_ai_model=settings.AI_MODEL,
        ),
        ai_model=settings.AI_MODEL,
    )

    # Create and initialize the dependency container
    container = DependencyContainer(db_path=settings.CHATBOT_DB_PATH)
    await container.initialize()

    # Create orchestrator with dependency injection
    orchestrator = container.create_main_orchestrator(config)

    try:
        await orchestrator.start()
    except KeyboardInterrupt:
        logger.info("Shutting down gracefully...")
    except Exception as e:
        logger.error(f"Application error: {e}")
        raise
    finally:
        await orchestrator.stop()
        await container.cleanup()
        logger.info("Chatbot application stopped")


if __name__ == "__main__":
    asyncio.run(main())
