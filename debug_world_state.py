#!/usr/bin/env python3
"""
Debug script to check world state for pending matrix invites
"""
import sys
import sqlite3
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from chatbot.core.world_state.manager import WorldStateManager


def debug_world_state():
    """Debug the current world state"""
    print("🔍 Debugging world state for pending Matrix invites...")
    
    # Initialize world state manager
    ws_manager = WorldStateManager()
    
    # Get current state
    state = ws_manager.get_state_data()
    
    print(f"📊 World State Summary:")
    print(f"  Channels: {len(state.channels)}")
    print(f"  Pending Matrix invites: {len(state.pending_matrix_invites)}")
    print(f"  Action history: {len(state.action_history)}")
    print(f"  Media library: {len(state.generated_media_library)}")
    
    if state.pending_matrix_invites:
        print(f"\n📨 Pending Matrix Invites:")
        for i, invite in enumerate(state.pending_matrix_invites, 1):
            print(f"  {i}. {invite}")
    else:
        print("\n✅ No pending Matrix invites")
    
    if state.channels:
        print(f"\n📱 Channels:")
        for channel_id, channel in list(state.channels.items())[:5]:  # Show first 5
            print(f"  {channel_id}: {channel.name} ({channel.type})")


if __name__ == "__main__":
    debug_world_state()
