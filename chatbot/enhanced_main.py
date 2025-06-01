"""
Enhanced Main entry point for the chatbot application with JSON Observer support.

This version uses the EnhancedContextAwareOrchestrator which can automatically
switch between traditional and node-based processing to handle payload size issues.

Copyright (c) 2025 Ratimics
Licensed under Creative Commons Attribution-NonCommercial 4.0 International License.
For commercial use, contact the copyright holder for permission.
"""


import asyncio
import logging
from pathlib import Path

from dotenv import load_dotenv
# Load environment variables from .env file
load_dotenv(Path(__file__).parent / ".env")

from chatbot.config import settings
from chatbot.core.enhanced_orchestrator import (
    EnhancedContextAwareOrchestrator,
    EnhancedOrchestratorConfig,
)


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
    """Main application entry point with enhanced orchestrator."""
    setup_logging()
    logger = logging.getLogger(__name__)

    logger.info("Starting enhanced chatbot application with JSON Observer support...")

    # Load enhanced configuration
    config = EnhancedOrchestratorConfig(
        db_path=settings.CHATBOT_DB_PATH,
        observation_interval=settings.OBSERVATION_INTERVAL,
        max_cycles_per_hour=settings.MAX_CYCLES_PER_HOUR,
        ai_model=settings.AI_MODEL,
        # Enhanced settings
        enable_json_observer=True,
        use_node_based_processing=True,
        max_traditional_payload_size=80000,  # 80KB threshold
        json_observer_model=settings.AI_SUMMARY_MODEL,
    )

    # Create and start enhanced orchestrator
    orchestrator = EnhancedContextAwareOrchestrator(config)

    try:
        # Log startup configuration
        logger.info(f"JSON Observer enabled: {config.enable_json_observer}")
        logger.info(f"Node-based processing: {config.use_node_based_processing}")
        logger.info(f"Payload size threshold: {config.max_traditional_payload_size} bytes")
        
        await orchestrator.start()
    except KeyboardInterrupt:
        logger.info("Shutting down gracefully...")
    except Exception as e:
        logger.error(f"Application error: {e}")
        raise
    finally:
        await orchestrator.stop()
        logger.info("Enhanced chatbot application stopped")


if __name__ == "__main__":
    asyncio.run(main())
