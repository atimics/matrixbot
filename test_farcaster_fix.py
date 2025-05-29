#!/usr/bin/env python3
"""
Test script to verify Farcaster notification summarization includes cast hashes.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from farcaster_service import FarcasterService

def test_notification_summarization():
    """Test that notification summarization includes cast hashes."""
    
    # Create a test service instance
    service = FarcasterService("test.db")
    
    # Create mock notifications with mentions
    mock_notifications = [
        {
            "type": "mention",
            "id": "notif1",
            "cast": {
                "hash": "0x1234567890abcdef",
                "text": "Hey @bot, what do you think about this new protocol?",
                "author": {
                    "username": "alice"
                }
            }
        },
        {
            "type": "mention", 
            "id": "notif2",
            "cast": {
                "hash": "0xfedcba0987654321",
                "text": "This is a longer message that should be truncated because it exceeds the 50 character limit for display",
                "author": {
                    "username": "bob"
                }
            }
        },
        {
            "type": "reply",
            "id": "notif3", 
            "cast": {
                "hash": "0xabcdef1234567890",
                "text": "Thanks for the reply!",
                "author": {
                    "username": "charlie"
                }
            }
        }
    ]
    
    # Test the summarization
    summary = service._summarize_notifications(mock_notifications)
    print(f"Generated summary: {summary}")
    
    # Verify that cast hashes are included
    assert "0x1234567890abcdef" in summary, "First mention hash should be included"
    assert "0xfedcba0987654321" in summary, "Second mention hash should be included" 
    assert "0xabcdef1234567890" in summary, "Reply hash should be included"
    
    # Verify that usernames are included
    assert "@alice" in summary, "First mention author should be included"
    assert "@bob" in summary, "Second mention author should be included"
    assert "@charlie" in summary, "Reply author should be included"
    
    # Verify text truncation works
    assert "This is a longer message that should be truncated ..." in summary, "Long text should be truncated"
    
    print("✅ All tests passed! Cast hashes are now included in notification summaries.")
    

if __name__ == "__main__":
    test_notification_summarization()
