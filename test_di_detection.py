#!/usr/bin/env python3
"""
Test script to verify DependencyContainer and DI mode detection.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from chatbot.config import settings
from chatbot.core.container import DependencyContainer
from chatbot.core.orchestration import MainOrchestrator, OrchestratorConfig, ProcessingConfig

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_di_mode():
    """Test DI mode detection."""
    logger.info("Testing DependencyContainer and DI mode detection...")
    
    # Create config
    config = OrchestratorConfig(
        db_path="test_di_mode.db",
        processing_config=ProcessingConfig(
            enable_node_based_processing=True,
            observation_interval=30,
            max_cycles_per_hour=10,
        ),
    )
    
    # Create and initialize the dependency container
    container = DependencyContainer(db_path="test_di_mode.db")
    await container.initialize()
    
    # Log each dependency to verify they're created
    logger.info(f"World State Manager: {container._world_state_manager}")
    logger.info(f"Context Manager: {container._context_manager}")
    logger.info(f"Integration Manager: {container._integration_manager}")
    logger.info(f"AI Engine: {container._ai_engine}")
    logger.info(f"Payload Builder: {container._payload_builder}")
    logger.info(f"Processing Hub: {container._processing_hub}")
    logger.info(f"Rate Limiter: {container._rate_limiter}")
    logger.info(f"Proactive Engine: {container._proactive_engine}")
    logger.info(f"Tool Registry: {container._tool_registry}")
    logger.info(f"Action Context: {container._action_context}")
    logger.info(f"Arweave Client: {container._arweave_client}")
    
    # Create orchestrator with dependency injection
    logger.info("Creating MainOrchestrator with DI...")
    orchestrator = container.create_main_orchestrator(config)
    
    # Check if DI mode is detected
    logger.info(f"DI Mode Detected: {orchestrator._is_di_mode}")
    
    # Clean up
    await container.cleanup()
    
    return orchestrator._is_di_mode

if __name__ == "__main__":
    result = asyncio.run(test_di_mode())
    print(f"\nDI Mode Detection Result: {result}")
