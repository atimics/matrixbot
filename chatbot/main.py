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
from chatbot.utils.logging_utils import setup_colorized_logging


def setup_logging() -> None:
    """Set up logging configuration with colorized output for VS Code terminal."""
    setup_colorized_logging(
        level=logging.INFO,
        log_file="chatbot.log",
        enable_colors=True
    )


async def main() -> None:
    """Main application entry point."""
    setup_logging()
    logger = logging.getLogger(__name__)

    logger.info("Starting chatbot application...")

    # Load configuration with node-based processing
    config = OrchestratorConfig(
        db_path=settings.chatbot_db_path,
        processing_config=ProcessingConfig(
            enable_node_based_processing=True,  # Advanced node-based mode
            observation_interval=settings.processing.observation_interval,
            max_cycles_per_hour=settings.processing.max_cycles_per_hour,
            traditional_ai_model=settings.processing.ai_model,
        ),
        ai_model=settings.processing.ai_model,
    )

    # Create and initialize the dependency container
    container = DependencyContainer(db_path=settings.chatbot_db_path)
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
