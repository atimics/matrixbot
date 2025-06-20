#!/usr/bin/env python3
"""
Test Service-Oriented Architecture

Simple test to verify the new service-oriented components work correctly.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def test_service_imports():
    """Test that service components can be imported"""
    try:
        from chatbot.core.services.service_registry import (
            ServiceRegistry, 
            ServiceInterface,
            MessagingServiceInterface,
            MediaServiceInterface,
            SocialServiceInterface
        )
        print("✅ Service registry components imported successfully")
        
        from chatbot.core.services.matrix_service import MatrixService
        print("✅ Matrix service imported successfully")
        
        from chatbot.core.services.farcaster_service import FarcasterService
        print("✅ Farcaster service imported successfully")
        
        return True
        
    except Exception as e:
        print(f"❌ Import error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_service_registry():
    """Test service registry functionality"""
    try:
        from chatbot.core.services.service_registry import ServiceRegistry
        
        # Create registry
        registry = ServiceRegistry()
        print("✅ Service registry created")
        
        # Test initial state
        services = registry.list_available_services()
        assert len(services) == 0, "Registry should start empty"
        print("✅ Initial registry state correct")
        
        # Test service type filtering
        messaging_services = registry.get_services_by_type("matrix")
        assert len(messaging_services) == 0, "No matrix services should exist initially"
        print("✅ Service type filtering works")
        
        return True
        
    except Exception as e:
        print(f"❌ Registry error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_service_tools():
    """Test that service-oriented tools can be imported"""
    try:
        from chatbot.tools.service_oriented_matrix_tools import (
            ServiceOrientedSendMatrixReplyTool,
            ServiceOrientedReactToMatrixMessageTool
        )
        print("✅ Service-oriented Matrix tools imported successfully")
        
        from chatbot.tools.service_oriented_farcaster_tools import (
            ServiceOrientedSendFarcasterPostTool,
            ServiceOrientedLikeFarcasterPostTool
        )
        print("✅ Service-oriented Farcaster tools imported successfully")
        
        # Test tool instantiation
        matrix_reply_tool = ServiceOrientedSendMatrixReplyTool()
        assert matrix_reply_tool.name == "send_matrix_reply"
        print("✅ Service-oriented tools can be instantiated")
        
        return True
        
    except Exception as e:
        print(f"❌ Service tools error: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests"""
    print("🧪 Testing Service-Oriented Architecture Components\n")
    
    all_passed = True
    
    # Test imports
    print("1. Testing component imports...")
    if not test_service_imports():
        all_passed = False
    print()
    
    # Test registry functionality
    print("2. Testing service registry...")
    if not test_service_registry():
        all_passed = False
    print()
    
    # Test service tools
    print("3. Testing service-oriented tools...")
    if not test_service_tools():
        all_passed = False
    print()
    
    if all_passed:
        print("🎉 All Service-Oriented Architecture tests passed!")
        return 0
    else:
        print("❌ Some tests failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
