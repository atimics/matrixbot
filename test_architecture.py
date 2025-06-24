#!/usr/bin/env python3
"""
Simple test script to verify the new dependency injection architecture works.
"""

import asyncio
import logging
import os
import tempfile
from pathlib import Path

# Set up basic logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Set minimal environment variables needed for testing
os.environ.setdefault('CHATBOT_DB_PATH', str(Path(tempfile.gettempdir()) / 'test_chatbot.db'))
os.environ.setdefault('OBSERVATION_INTERVAL', '30')
os.environ.setdefault('MAX_CYCLES_PER_HOUR', '120')
os.environ.setdefault('MAX_ACTIONS_PER_HOUR', '60')
os.environ.setdefault('AI_MODEL', 'anthropic/claude-sonnet-4')
os.environ.setdefault('OPENROUTER_API_KEY', 'test-key')
os.environ.setdefault('RATICHAT_ENCRYPTION_KEY', 'i5_aCOs2cZn90gD6L7OeBloMbkDTrPzmNNvxSESIrjU=')
os.environ.setdefault('MAX_EXPANDED_NODES', '8')
os.environ.setdefault('DEFAULT_PINNED_NODES', '["system.test"]')
os.environ.setdefault('AI_SUMMARY_MODEL', 'anthropic/claude-sonnet-4')

async def test_architecture():
    """Test that we can create and initialize the new architecture."""
    try:
        # Import after setting environment variables
        from chatbot.core.container import DependencyContainer
        from chatbot.core.orchestration import OrchestratorConfig, ProcessingConfig
        
        logger.info("✓ Successfully imported DependencyContainer and configs")
        
        # Create the dependency container
        db_path = str(Path(tempfile.gettempdir()) / 'test_architecture.db')
        container = DependencyContainer(db_path=db_path)
        logger.info("✓ Created DependencyContainer")
        
        # Initialize the container
        await container.initialize()
        logger.info("✓ Initialized DependencyContainer")
        
        # Create orchestrator config
        config = OrchestratorConfig(
            db_path=db_path,
            ai_model='anthropic/claude-sonnet-4',
        )
        logger.info("✓ Created OrchestratorConfig")
        
        # Create orchestrator with dependency injection
        orchestrator = container.create_main_orchestrator(config)
        logger.info("✓ Created MainOrchestrator with dependency injection")
        
        # Verify key components are properly injected
        assert orchestrator.world_state is not None, "WorldStateManager not injected"
        assert orchestrator.ai_engine is not None, "AIDecisionEngine not injected"
        assert orchestrator.tool_registry is not None, "ToolRegistry not injected"
        assert orchestrator.context_manager is not None, "ContextManager not injected"
        assert orchestrator.integration_manager is not None, "IntegrationManager not injected"
        assert orchestrator.processing_hub is not None, "ProcessingHub not injected"
        logger.info("✓ All core dependencies properly injected")
        
        # Test that the orchestrator was created in DI mode
        assert hasattr(orchestrator, '_is_di_mode'), "Orchestrator missing DI mode flag"
        assert orchestrator._is_di_mode == True, "Orchestrator not in DI mode"
        logger.info("✓ Orchestrator correctly initialized in DI mode")
        
        # Test that the tool registry was populated
        tool_stats = orchestrator.tool_registry.get_tool_stats()
        assert tool_stats['total_tools'] > 0, "No tools registered"
        logger.info(f"✓ Tool registry populated with {tool_stats['total_tools']} tools")
        
        # Clean up
        await container.cleanup()
        logger.info("✓ Container cleanup completed")
        
        logger.info("\n🎉 ALL TESTS PASSED! 🎉")
        logger.info("The new dependency injection architecture is working correctly!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Main test function."""
    logger.info("Testing new dependency injection architecture...")
    logger.info("=" * 60)
    
    success = await test_architecture()
    
    if success:
        logger.info("=" * 60)
        logger.info("Architecture test completed successfully!")
        return 0
    else:
        logger.error("Architecture test failed!")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
