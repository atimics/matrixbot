#!/usr/bin/env python3
"""
Debug script to check world state for pending matrix invites
"""
import asyncio
import sys
import sqlite3
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from chatbot.core.world_state.manager import WorldStateManager


async def debug_world_state():
    """Debug the current world state"""
    print("🔍 Debugging world state for pending Matrix invites...")
    
    # Initialize world state manager
    ws_manager = WorldStateManager(db_path="chatbot.db")
    await ws_manager.initialize()
    
    # Get current state
    state = await ws_manager.get_state()
    
    print(f"📊 World State Summary:")
    print(f"  Matrix rooms: {len(state.matrix_rooms)}")
    print(f"  Pending Matrix invites: {len(state.pending_matrix_invites)}")
    print(f"  Target repositories: {len(state.target_repositories)}")
    print(f"  Development tasks: {len(state.development_tasks)}")
    
    if state.pending_matrix_invites:
        print(f"\n📨 Pending Matrix Invites:")
        for i, invite in enumerate(state.pending_matrix_invites, 1):
            print(f"  {i}. {invite}")
    else:
        print("\n✅ No pending Matrix invites")
    
    if state.matrix_rooms:
        print(f"\n🏠 Matrix Rooms:")
        for room_id, room_info in list(state.matrix_rooms.items())[:5]:  # Show first 5
            print(f"  {room_id}: {room_info.get('name', 'Unknown')}")
    
    # Close the manager
    await ws_manager.close()


if __name__ == "__main__":
    asyncio.run(debug_world_state())
