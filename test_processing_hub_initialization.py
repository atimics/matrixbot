#!/usr/bin/env python3
"""
Test script to verify ProcessingHub initialization works correctly.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'chatbot'))

from chatbot.core.orchestration.processing_hub import ProcessingHub, ProcessingConfig
from unittest.mock import MagicMock

def test_processing_hub_initialization():
    """Test that ProcessingHub can be initialized with the correct parameters."""
    
    # Create mock objects
    world_state_manager = MagicMock()
    payload_builder = MagicMock()
    rate_limiter = MagicMock()
    config = ProcessingConfig()
    
    try:
        # Try to create ProcessingHub with the same parameters as main_orchestrator.py
        hub = ProcessingHub(
            world_state_manager=world_state_manager,
            payload_builder=payload_builder,
            rate_limiter=rate_limiter,
            config=config
        )
        
        print("✅ ProcessingHub initialization successful!")
        print(f"   - World state manager: {hub.world_state is not None}")
        print(f"   - Payload builder: {hub.payload_builder is not None}")
        print(f"   - Rate limiter: {hub.rate_limiter is not None}")
        print(f"   - Config: {hub.config is not None}")
        
        return True
        
    except Exception as e:
        print(f"❌ ProcessingHub initialization failed: {e}")
        return False

if __name__ == "__main__":
    success = test_processing_hub_initialization()
    sys.exit(0 if success else 1)
