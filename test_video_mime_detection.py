#!/usr/bin/env python3
"""
Test script to verify video MIME type detection logic
"""

import mimetypes
import tempfile
import os

def test_mime_detection(filename, response_content_type=None):
    """Test the MIME type detection logic from SendMatrixVideoTool"""
    print(f"\n--- Testing: {filename} ---")
    
    # Get content type from HTTP response headers (simulated)
    response_content_type = response_content_type or ''
    response_content_type = response_content_type.split(';')[0].strip()
    print(f"HTTP Content-Type: '{response_content_type}'")

    # Determine MIME type for the video file
    mime_type, _ = mimetypes.guess_type(filename)
    print(f"mimetypes.guess_type(): {mime_type}")
    
    # Prefer HTTP response content type if it's a video type
    if response_content_type and response_content_type.startswith('video/'):
        mime_type = response_content_type
        print(f"Using content-type from HTTP response: {mime_type}")
    elif not mime_type or not mime_type.startswith('video/'):
        # Fallback to file extension detection
        lower_filename = filename.lower()
        if lower_filename.endswith('.webm'):
            mime_type = "video/webm"
        elif lower_filename.endswith('.mov'):
            mime_type = "video/quicktime"
        elif lower_filename.endswith('.avi'):
            mime_type = "video/avi"
        elif lower_filename.endswith('.mkv'):
            mime_type = "video/x-matroska"
        else:
            mime_type = "video/mp4"  # Default fallback
        print(f"Using fallback detection")
    
    print(f"Final detected video MIME type: {mime_type}")
    return mime_type

def main():
    print("Testing Video MIME Type Detection Logic")
    print("=" * 50)
    
    # Test cases
    test_cases = [
        # (filename, simulated_http_content_type)
        ("video.mp4", None),
        ("video.webm", None),
        ("video.mov", None),
        ("video.avi", None),
        ("video.mkv", None),
        ("unknown_extension.xyz", None),
        ("video.mp4", "video/mp4"),
        ("video.webm", "video/webm"),
        ("video.mov", "video/quicktime"),
        ("video.mp4", "video/webm"),  # HTTP overrides extension
        ("video.webm", "video/mp4"),  # HTTP overrides extension
        ("video.mp4", "application/octet-stream"),  # Non-video HTTP type
    ]
    
    results = []
    for filename, http_content_type in test_cases:
        detected_type = test_mime_detection(filename, http_content_type)
        results.append((filename, http_content_type, detected_type))
    
    print("\n" + "=" * 50)
    print("SUMMARY:")
    print("=" * 50)
    for filename, http_type, detected_type in results:
        http_display = http_type or "None"
        print(f"{filename:20} | HTTP: {http_display:20} | Detected: {detected_type}")
    
    # Verify expected results
    print("\n" + "=" * 50)
    print("VERIFICATION:")
    print("=" * 50)
    
    expected_results = {
        ("video.mp4", None): "video/mp4",
        ("video.webm", None): "video/webm", 
        ("video.mov", None): "video/quicktime",
        ("video.avi", None): "video/x-msvideo",  # System returns proper MIME type
        ("video.mkv", None): "video/x-matroska",
        ("unknown_extension.xyz", None): "video/mp4",  # fallback
        ("video.mp4", "video/webm"): "video/webm",  # HTTP wins
    }
    
    all_passed = True
    for (filename, http_type), expected in expected_results.items():
        actual = next(detected for f, h, detected in results if f == filename and h == http_type)
        if actual == expected:
            print(f"✅ {filename} with HTTP '{http_type}' -> {actual}")
        else:
            print(f"❌ {filename} with HTTP '{http_type}' -> Expected: {expected}, Got: {actual}")
            all_passed = False
    
    if all_passed:
        print("\n🎉 All tests passed! The MIME type detection logic is working correctly.")
    else:
        print("\n⚠️  Some tests failed. Please check the implementation.")

if __name__ == "__main__":
    main()
