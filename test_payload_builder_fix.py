#!/usr/bin/env python3
"""
Test script to verify the PayloadBuilder fix for the infinite loop issue.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mock the required structures
@dataclass
class MockMessage:
    id: str
    channel_id: str
    channel_type: str
    sender: str
    content: str
    timestamp: float
    sender_username: Optional[str] = None
    reply_to: Optional[str] = None
    sender_fid: Optional[int] = None
    sender_follower_count: Optional[int] = None
    neynar_user_score: Optional[float] = None
    image_urls: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_ai_summary_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "sender": self.sender_username or self.sender,
            "content": self.content[:100] + "..." if len(self.content) > 100 else self.content,
            "timestamp": self.timestamp,
            "type": "summary"
        }

@dataclass 
class MockChannel:
    id: str
    name: str
    type: str
    status: str = "active"
    recent_messages: List[MockMessage] = field(default_factory=list)
    last_checked: float = field(default_factory=time.time)

@dataclass
class MockWorldStateData:
    channels: Dict[str, MockChannel] = field(default_factory=dict)
    last_update: float = field(default_factory=time.time)
    rate_limits: Dict[str, Any] = field(default_factory=dict)

@dataclass
class MockNodeMetadata:
    is_expanded: bool = False
    is_pinned: bool = False
    last_expanded_ts: Optional[float] = None
    ai_summary: Optional[str] = None
    last_summary_update_ts: Optional[float] = None

class MockNodeManager:
    def __init__(self):
        self.nodes: Dict[str, MockNodeMetadata] = {}
    
    def get_node_metadata(self, node_path: str) -> MockNodeMetadata:
        if node_path not in self.nodes:
            self.nodes[node_path] = MockNodeMetadata()
        return self.nodes[node_path]
    
    def expand_node(self, node_path: str):
        metadata = self.get_node_metadata(node_path)
        metadata.is_expanded = True
        metadata.last_expanded_ts = time.time()
        logger.info(f"Node {node_path} expanded")
    
    def is_data_changed(self, node_path: str, node_data: Any) -> bool:
        return False
    
    def get_expansion_status_summary(self) -> Dict[str, Any]:
        return {"expanded_count": sum(1 for m in self.nodes.values() if m.is_expanded)}
    
    def get_system_events(self) -> List[Dict[str, Any]]:
        return []

def test_payload_builder_fix():
    """Test that the PayloadBuilder fix resolves the infinite loop issue."""
    
    # Import the actual PayloadBuilder
    import sys
    sys.path.append('/workspaces/matrixbot')
    from chatbot.core.world_state.payload_builder import PayloadBuilder
    from dataclasses import asdict
    
    # Create test data
    msg1 = MockMessage(
        id="msg1",
        channel_id="test_room",
        channel_type="matrix", 
        sender="@testuser:chat.ratimics.com",
        content="Hello @ratichat:chat.ratimics.com, can you see this message? Please respond if you can read this.",
        timestamp=time.time(),
        sender_username="@testuser:chat.ratimics.com"
    )
    
    channel = MockChannel(
        id="!zBaUOGAwGyzOEGWJFd:chat.ratimics.com",
        name="Robot Laboratory",
        type="matrix",
        recent_messages=[msg1]
    )
    
    world_state = MockWorldStateData(
        channels={"!zBaUOGAwGyzOEGWJFd:chat.ratimics.com": channel}
    )
    
    node_manager = MockNodeManager()
    builder = PayloadBuilder()
    
    # Test 1: Collapsed node should return summary data
    logger.info("=== Test 1: Collapsed Node ===")
    node_path = "channels.matrix.!zBaUOGAwGyzOEGWJFd:chat.ratimics.com"
    
    # Get data for collapsed node
    collapsed_data = builder._get_node_data_by_path(world_state, node_path, expanded=False)
    logger.info(f"Collapsed data messages: {collapsed_data['recent_messages']}")
    
    # Verify we get summary data
    assert collapsed_data['recent_messages'][0]['type'] == 'summary'
    assert len(collapsed_data['recent_messages'][0]['content']) <= 103  # 100 + "..."
    logger.info("✓ Collapsed node returns summary data")
    
    # Test 2: Expanded node should return full data  
    logger.info("=== Test 2: Expanded Node ===")
    
    # Get data for expanded node
    expanded_data = builder._get_node_data_by_path(world_state, node_path, expanded=True)
    logger.info(f"Expanded data messages: {expanded_data['recent_messages']}")
    
    # Verify we get full data (from asdict)
    assert 'type' not in expanded_data['recent_messages'][0]  # asdict doesn't add type field
    assert expanded_data['recent_messages'][0]['content'] == msg1.content  # Full content
    logger.info("✓ Expanded node returns full data")
    
    # Test 3: Integration test with node-based payload
    logger.info("=== Test 3: Node-Based Payload Integration ===")
    
    # Start with collapsed node
    payload_collapsed = builder.build_node_based_payload(
        world_state, 
        node_manager, 
        "!zBaUOGAwGyzOEGWJFd:chat.ratimics.com"
    )
    
    logger.info(f"Collapsed payload nodes: {list(payload_collapsed.get('collapsed_node_summaries', {}).keys())}")
    assert node_path in payload_collapsed.get('collapsed_node_summaries', {})
    logger.info("✓ Node appears in collapsed summaries")
    
    # Expand the node
    node_manager.expand_node(node_path)
    
    # Get payload with expanded node
    payload_expanded = builder.build_node_based_payload(
        world_state,
        node_manager, 
        "!zBaUOGAwGyzOEGWJFd:chat.ratimics.com"
    )
    
    logger.info(f"Expanded payload nodes: {list(payload_expanded.get('expanded_nodes', {}).keys())}")
    assert node_path in payload_expanded.get('expanded_nodes', {})
    
    # Check that expanded node has full message data
    expanded_node_data = payload_expanded['expanded_nodes'][node_path]['data']
    expanded_messages = expanded_node_data['recent_messages']
    logger.info(f"Expanded message content length: {len(expanded_messages[0]['content'])}")
    
    # Verify the full content is present (not truncated)
    assert len(expanded_messages[0]['content']) > 100  # Should be full content
    assert expanded_messages[0]['content'] == msg1.content
    logger.info("✓ Expanded node contains full message data")
    
    logger.info("🎉 All tests passed! The PayloadBuilder fix works correctly.")
    
    return True

if __name__ == "__main__":
    try:
        test_payload_builder_fix()
        print("\n✅ SUCCESS: PayloadBuilder fix is working correctly!")
        print("The AI will now receive different data based on node expansion state:")
        print("- Collapsed nodes: Summary data (truncated content)")  
        print("- Expanded nodes: Full data (complete content)")
        print("This should resolve the infinite loop issue.")
        
    except Exception as e:
        print(f"\n❌ ERROR: Test failed with: {e}")
        import traceback
        traceback.print_exc()
