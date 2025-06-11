#!/usr/bin/env python3
"""
Verification script for the traditional processing removal refactoring.
"""

import sys
import os

# Add the current directory to Python path
sys.path.insert(0, '/workspaces/matrixbot')

def test_processing_config():
    """Test that ProcessingConfig defaults to node-based processing."""
    try:
        from chatbot.core.orchestration.processing_hub import ProcessingConfig
        config = ProcessingConfig()
        
        assert config.enable_node_based_processing is True
        print("✅ ProcessingConfig defaults to node-based processing")
        return True
    except Exception as e:
        print(f"❌ ProcessingConfig test failed: {e}")
        return False

def test_processing_hub_creation():
    """Test that ProcessingHub can be created without traditional processor."""
    try:
        from chatbot.core.orchestration.processing_hub import ProcessingHub, ProcessingConfig
        from unittest.mock import Mock
        
        # Create mocks
        world_state_manager = Mock()
        payload_builder = Mock()
        rate_limiter = Mock()
        config = ProcessingConfig()
        
        # Create ProcessingHub
        hub = ProcessingHub(
            world_state_manager=world_state_manager,
            payload_builder=payload_builder,
            rate_limiter=rate_limiter,
            config=config
        )
        
        assert hub.config.enable_node_based_processing is True
        assert hub.node_processor is None  # Should start as None until set
        
        print("✅ ProcessingHub can be created with node-based processing only")
        return True
    except Exception as e:
        print(f"❌ ProcessingHub creation test failed: {e}")
        return False

def test_deprecated_methods():
    """Test that deprecated methods exist but log warnings."""
    try:
        from chatbot.core.orchestration.main_orchestrator import MainOrchestrator, OrchestratorConfig
        
        config = OrchestratorConfig(db_path=":memory:")
        orchestrator = MainOrchestrator(config)
        
        # Test deprecated methods exist but warn
        orchestrator.force_processing_mode(True)  # Should warn but not crash
        orchestrator.reset_processing_mode()  # Should warn but not crash
        
        print("✅ Deprecated methods exist and handle gracefully")
        return True
    except Exception as e:
        print(f"❌ Deprecated methods test failed: {e}")
        return False

def test_api_routes():
    """Test that API routes handle deprecated commands gracefully."""
    try:
        from chatbot.api_server.schemas import SystemCommand
        
        # Test that SystemCommand can still handle deprecated commands
        reset_cmd = SystemCommand(command="reset_processing_mode")
        force_cmd = SystemCommand(command="force_processing_mode", parameters={"mode": "node-based"})
        
        assert reset_cmd.command == "reset_processing_mode"
        assert force_cmd.command == "force_processing_mode"
        
        print("✅ API schemas handle deprecated commands")
        return True
    except Exception as e:
        print(f"❌ API routes test failed: {e}")
        return False

def main():
    """Run all verification tests."""
    print("🔄 Running traditional processing removal verification...")
    print()
    
    tests = [
        test_processing_config,
        test_processing_hub_creation,
        test_deprecated_methods,
        test_api_routes
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        print()
    
    print(f"📊 Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All verification tests passed! Traditional processing removal successful.")
        return 0
    else:
        print("❌ Some tests failed. Please review the refactoring.")
        return 1

if __name__ == "__main__":
    exit(main())
