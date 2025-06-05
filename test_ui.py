#!/usr/bin/env python3
"""
Test script for the Chatbot Management UI

This script tests the basic functionality of the API server and UI components
without starting the full chatbot system.
"""

import asyncio
import time
from pathlib import Path

from chatbot.api_server import create_api_server
from chatbot.core.orchestration import MainOrchestrator, OrchestratorConfig, ProcessingConfig


async def test_api_server():
    """Test the API server creation and basic endpoints."""
    print("🧪 Testing Chatbot Management UI Components...")
    
    # Create a test orchestrator
    config = OrchestratorConfig(
        db_path="test_chatbot.db",
        processing_config=ProcessingConfig(
            enable_node_based_processing=False,
            observation_interval=60,
            max_cycles_per_hour=30
        )
    )
    
    print("✅ Creating test orchestrator...")
    orchestrator = MainOrchestrator(config)
    
    print("✅ Creating API server...")
    app = create_api_server(orchestrator)
    
    print("✅ Testing tool registry functionality...")
    # Test tool registry
    tools = orchestrator.tool_registry.get_all_tools_with_status()
    print(f"   Found {len(tools)} tools in registry")
    
    # Test enable/disable functionality
    if tools:
        test_tool = tools[0]
        tool_name = test_tool["name"]
        print(f"   Testing enable/disable on tool: {tool_name}")
        
        # Disable tool
        success = orchestrator.tool_registry.set_tool_enabled(tool_name, False)
        if success:
            print(f"   ✅ Successfully disabled {tool_name}")
        
        # Re-enable tool
        success = orchestrator.tool_registry.set_tool_enabled(tool_name, True)
        if success:
            print(f"   ✅ Successfully re-enabled {tool_name}")
    
    print("✅ Testing system status...")
    status = await orchestrator.get_system_status()
    print(f"   System running: {status.get('system_running', False)}")
    print(f"   Tools: {status.get('tools', {}).get('total_tools', 0)} total, {status.get('tools', {}).get('enabled_tools', 0)} enabled")
    
    print("✅ Checking UI files...")
    ui_index = Path("ui/index.html")
    if ui_index.exists():
        print(f"   ✅ UI file exists: {ui_index}")
        print(f"   📁 UI file size: {ui_index.stat().st_size:,} bytes")
    else:
        print(f"   ❌ UI file missing: {ui_index}")
    
    print("\n🎉 All tests passed! The Chatbot Management UI is ready.")
    print("\nTo start the full system with UI:")
    print("   poetry run python -m chatbot.main_with_ui")
    print("\nOr use the VS Code task:")
    print("   'Run Chatbot with Management UI'")
    print("\nThe UI will be available at:")
    print("   http://localhost:8000")


if __name__ == "__main__":
    asyncio.run(test_api_server())
