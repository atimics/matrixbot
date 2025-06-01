# S3 Image Proxy Service Implementation

## Overview

This implementation provides a Python S3 service that solves the Matrix image accessibility problem by uploading Matrix images to a public S3/CloudFront CDN, making them accessible to external AI services.

## Problem Solved

**Original Issue**: Matrix media URLs (`mxc://` URIs converted to `https://matrix.server/_matrix/media/...`) require authentication and are not accessible to external services like OpenRouter AI models.

**Solution**: When a Matrix image is detected, our service:
1. Downloads the image from Matrix using authenticated requests
2. Uploads it to S3 via a proxy API
3. Returns a public CloudFront URL that AI services can access

## Architecture

```
Matrix Image → Matrix Observer → S3 Service → S3/CloudFront → AI Service
```

## Key Components

### 1. S3Service (`chatbot/tools/s3_service.py`)

- **Purpose**: Handles image upload to S3 via proxy API
- **Key Features**:
  - Downloads images with authentication support
  - Uploads to S3 using base64 encoding (matching JavaScript implementation)
  - Returns public CloudFront URLs
  - Error handling with fallback support

### 2. Matrix Observer Integration

- **File**: `chatbot/integrations/matrix/observer.py`
- **Enhancement**: Modified image handling in `_on_message()` method
- **Process**:
  1. Detects `RoomMessageImage` events
  2. Converts MXC URI to HTTP URL
  3. Creates authenticated HTTP client
  4. Uploads image to S3 using the S3Service
  5. Falls back to original Matrix URL if S3 upload fails

## Configuration

Environment variables required (already configured in `.env`):

```env
S3_API_ENDPOINT="https://zjc1xcynf1.execute-api.us-east-1.amazonaws.com/Production"
S3_API_KEY="rRsE4wK7AX3HADN4z1zfI6RZFF0qVB9R5gWTPGE8"
CLOUDFRONT_DOMAIN="https://d7xbminy5txaa.cloudfront.net"
```

## Usage Example

```python
from chatbot.tools.s3_service import s3_service

# Upload image from URL with authentication
public_url = await s3_service.upload_image_from_url(
    "https://matrix.server/_matrix/media/download/server/file",
    "image.jpg",
    authenticated_http_client
)

# Upload image data directly
public_url = await s3_service.upload_image_data(
    image_bytes,
    "image.jpg"
)
```

## API Contract

The S3 proxy API expects:

```json
{
  "image": "base64_encoded_image_data",
  "imageType": "jpg|png|gif|mp4"
}
```

And returns:

```json
{
  "url": "https://cloudfront.domain.com/uploaded_image.jpg"
}
```

## Integration Flow

1. **Matrix Image Detection**: Observer detects `RoomMessageImage`
2. **Authentication**: Creates `httpx.AsyncClient` with Matrix access token
3. **S3 Upload**: Calls `s3_service.upload_image_from_url()` with authenticated client
4. **URL Replacement**: Replaces Matrix URL with public CloudFront URL
5. **Fallback**: Uses original Matrix URL if S3 upload fails
6. **World State Update**: Stores message with public image URL

## Benefits

- ✅ **AI Accessibility**: External AI services can access images
- ✅ **Authentication Handling**: Properly handles Matrix media authentication
- ✅ **Fallback Support**: Graceful degradation if S3 upload fails
- ✅ **Performance**: Images cached on CDN for faster access
- ✅ **Security**: Original Matrix authentication preserved for fallback

## Testing

Comprehensive test coverage includes:

- **Unit Tests**: `tests/test_s3_service.py` (9 tests)
- **Integration Tests**: `tests/test_matrix_s3_integration.py` (4 tests)
- **Coverage**: Image upload success, failure scenarios, authentication, edge cases

## Files Modified/Created

### Created:
- `chatbot/tools/s3_service.py` - S3 service implementation
- `tests/test_s3_service.py` - Unit tests
- `tests/test_matrix_s3_integration.py` - Integration tests

### Modified:
- `chatbot/integrations/matrix/observer.py` - Added S3 integration to image handling

## Status

✅ **Implementation Complete**
✅ **Tests Passing** (13/13 new tests + existing test suite)
✅ **Ready for Production**

This implementation resolves the 404 image access errors for AI services while maintaining backward compatibility and robust error handling.
