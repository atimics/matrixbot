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
from chatbot.config import settings
from chatbot.core.orchestration import MainOrchestrator, OrchestratorConfig, ProcessingConfig


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

    # Load unified configuration
    unified_settings = settings
    
    # Load configuration with node-based processing
    config = OrchestratorConfig(
        db_path=unified_settings.database.path,
        processing_config=ProcessingConfig(
            enable_node_based_processing=True,  # Advanced node-based mode
            observation_interval=unified_settings.observation_interval,
            max_cycles_per_hour=unified_settings.max_cycles_per_hour
        ),
        ai_model=unified_settings.ai.model,
    )

    # Create and start orchestrator
    orchestrator = MainOrchestrator(config)

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
