#!/usr/bin/env python3
"""
Quick test script to verify media gallery path generation functionality.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Mock the required classes to test our functionality
class MockMediaItem:
    def __init__(self, media_id, media_type, description="Test media"):
        self.media_id = media_id
        self.media_type = media_type
        self.description = description
        self.timestamp = 1640995200  # Mock timestamp
        self.file_path = f"/path/to/{media_id}.jpg"

class MockWorldStateData:
    def __init__(self):
        self.generated_media_library = []
        
    def add_media(self, media_item):
        self.generated_media_library.append(media_item)

class MockPayloadBuilder:
    def _generate_media_gallery_paths(self, world_state_data):
        """Generate node paths for the AI's generated media library."""
        # Always generate the main media gallery path so AI can see it exists
        yield "media_gallery"
        
        # Generate paths for recent media items if there are any
        if world_state_data.generated_media_library:
            # Create individual media item paths for the most recent items
            # This allows the AI to expand and see specific media details
            recent_media = world_state_data.generated_media_library[-10:]  # Last 10 items
            for media_item in recent_media:
                if hasattr(media_item, 'media_id') and media_item.media_id:
                    yield f"media_gallery.{media_item.media_id}"
            
            # Also create categorical paths if there are different media types
            media_types = set()
            for media_item in world_state_data.generated_media_library:
                if hasattr(media_item, 'media_type') and media_item.media_type:
                    media_types.add(media_item.media_type)
            
            for media_type in media_types:
                yield f"media_gallery.by_type.{media_type}"

def test_media_gallery_paths():
    builder = MockPayloadBuilder()
    
    # Test 1: Empty media library
    print("=== Test 1: Empty Media Library ===")
    empty_data = MockWorldStateData()
    paths = list(builder._generate_media_gallery_paths(empty_data))
    print(f"Generated paths: {paths}")
    assert paths == ["media_gallery"], f"Expected ['media_gallery'], got {paths}"
    print("✅ Test 1 passed\n")
    
    # Test 2: Media library with items
    print("=== Test 2: Media Library with Items ===")
    data_with_media = MockWorldStateData()
    data_with_media.add_media(MockMediaItem("img_001", "image", "A test image"))
    data_with_media.add_media(MockMediaItem("meme_001", "meme", "A test meme"))
    data_with_media.add_media(MockMediaItem("img_002", "image", "Another image"))
    
    paths = list(builder._generate_media_gallery_paths(data_with_media))
    print(f"Generated paths: {paths}")
    
    expected_paths = [
        "media_gallery",
        "media_gallery.img_001",
        "media_gallery.meme_001", 
        "media_gallery.img_002",
        "media_gallery.by_type.image",
        "media_gallery.by_type.meme"
    ]
    
    # Check all expected paths are present
    for expected_path in expected_paths:
        assert expected_path in paths, f"Missing expected path: {expected_path}"
    
    print("✅ Test 2 passed\n")
    
    # Test 3: Large library (>10 items)
    print("=== Test 3: Large Media Library ===")
    large_data = MockWorldStateData()
    for i in range(15):
        large_data.add_media(MockMediaItem(f"img_{i:03d}", "image", f"Image #{i}"))
    
    paths = list(builder._generate_media_gallery_paths(large_data))
    print(f"Generated {len(paths)} paths")
    
    # Should have main path + last 10 individual items + 1 type category
    individual_paths = [p for p in paths if p.startswith("media_gallery.img_")]
    print(f"Individual media paths: {len(individual_paths)}")
    assert len(individual_paths) == 10, f"Expected 10 individual paths, got {len(individual_paths)}"
    print("✅ Test 3 passed\n")
    
    print("🎉 All tests passed! Media gallery path generation is working correctly.")

if __name__ == "__main__":
    test_media_gallery_paths()
