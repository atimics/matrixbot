# S3 Service

This service provides a simple API to upload images and videos to S3-compatible storage using the provided S3 API endpoint.

## Features

- Direct S3 upload integration via API
- Support for images (PNG, JPG, JPEG, GIF) and videos (MP4)
- CloudFront URL serving
- Error handling and validation
- Base64 encoding for uploads

## Configuration

The service requires these environment variables:

- `S3_API_KEY`: API key for the S3 service
- `S3_API_ENDPOINT`: S3 API endpoint URL  
- `CLOUDFRONT_DOMAIN`: CloudFront domain for serving URLs

## Usage

### Python

```python
from chatbot.tools.s3_service import S3Service

# Initialize service (automatically configured from environment)
s3_service = S3Service()

# Upload image data
s3_url = await s3_service.upload_image_data(
    image_data=image_bytes,
    filename="my_image.png", 
    content_type="image/png"
)

# Upload image file
s3_url = await s3_service.upload_image("/path/to/image.jpg")

# Download file data
file_data = await s3_service.download_file_data(s3_url)
```

### JavaScript

```javascript
const { S3Service } = require('./S3Service');

// Initialize service
const s3Service = new S3Service({ logger: console });

// Upload image file
const s3Url = await s3Service.uploadImage('/path/to/image.jpg');

// Download image
const imageBuffer = await s3Service.downloadImage(s3Url);
```

## API

The S3 service expects a POST request to the configured endpoint with:

```json
{
  "image": "base64_encoded_data",
  "imageType": "jpg|png|gif|mp4"
}
```

Returns:
```json
{
  "url": "https://cloudfront.domain/path/to/file"
}
```

## Integration

This service replaces Arweave for all media storage in the chatbot system:

- Generated images from AI models
- Generated videos from Veo
- Matrix media re-uploads
- Permanent memory storage
- Media archiving

All tools and services have been updated to use S3 instead of Arweave for new uploads while maintaining backward compatibility with existing Arweave URLs.
