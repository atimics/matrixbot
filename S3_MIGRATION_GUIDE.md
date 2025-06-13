# S3 Service Migration Guide

This guide explains how to migrate from Arweave to S3 storage service or set up S3 service from scratch.

## Overview

The S3 service is a drop-in replacement for the Arweave service that provides:

- **Faster uploads** - Direct S3 storage vs blockchain transactions
- **Lower costs** - Standard S3 pricing vs AR token requirements  
- **Better reliability** - AWS infrastructure vs blockchain network dependency
- **Same API** - 100% compatible interface, no code changes needed

## Quick Start

### 1. Set up S3 Infrastructure

You need:
- An S3-compatible storage service (AWS S3, MinIO, etc.)
- A CloudFront distribution for fast global access
- An upload API endpoint that accepts the JavaScript S3Service format

### 2. Configure Environment Variables

Add these to your `.env` file:

```bash
# S3 Service Configuration
S3_API_KEY=your-s3-upload-service-api-key
S3_API_ENDPOINT=https://your-s3-upload-api.example.com/upload
CLOUDFRONT_DOMAIN=https://your-cloudfront-distribution.cloudfront.net
S3_SERVICE_API_KEY=optional-s3-service-auth-key  # Optional
```

### 3. Switch to S3 Service

Use the storage switcher script:

```bash
# Switch from Arweave to S3
./switch_storage.sh s3

# Check status
./switch_storage.sh status

# Switch back to Arweave if needed
./switch_storage.sh arweave
```

Or manually with docker-compose:

```bash
# Stop Arweave service
docker-compose stop arweave-service

# Start S3 service
docker-compose --profile s3 up -d s3-service
```

## Manual Setup

### Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `S3_API_KEY` | API key for your S3 upload service | `abc123xyz789` |
| `S3_API_ENDPOINT` | Endpoint that accepts image uploads | `https://api.example.com/upload` |
| `CLOUDFRONT_DOMAIN` | CloudFront distribution URL | `https://d1234.cloudfront.net` |
| `S3_SERVICE_API_KEY` | Optional auth for the S3 service itself | `service-auth-key` |

### Expected S3 Upload API Format

Your S3 upload endpoint should accept this format (matching the JavaScript S3Service):

**Request:**
```json
{
  "image": "base64-encoded-data",
  "imageType": "png"
}
```

**Response:**
```json
{
  "body": "{\"url\": \"https://your-cloudfront.com/filename.png\"}"
}
```

Or directly:
```json
{
  "url": "https://your-cloudfront.com/filename.png"
}
```

## Testing

### Test the S3 Service

```bash
# Run comprehensive tests
python s3-service/test_s3_service.py

# Test with custom URL
python s3-service/test_s3_service.py --url http://localhost:8001

# Run integration demo
python s3-service/integration_demo.py
```

### Health Check

```bash
curl http://localhost:8001/health
```

Expected response:
```json
{
  "status": "healthy",
  "wallet_ready": true,
  "wallet_address": "https://your-cloudfront.com"
}
```

## Code Migration

### No Changes Required

The S3 service provides the same API as Arweave service:

```python
# This code works with BOTH services unchanged
from chatbot.integrations.arweave_uploader_client import ArweaveUploaderClient
from chatbot.tools.arweave_service import ArweaveService

client = ArweaveUploaderClient(service_url, gateway_url, api_key)
service = ArweaveService(client)

# Upload works the same way
url = await service.upload_image_data(image_data, "image.png", "image/png")
```

### Optional: Use S3-specific imports

```python
# Use S3-specific imports for clarity
from s3_service.s3_uploader_client import S3UploaderClient
from s3_service.s3_service import S3Service

client = S3UploaderClient(s3_service_url, cloudfront_url, api_key)
service = S3Service(client)
```

## Deployment Options

### Option 1: Docker Compose Profiles

Use profiles to choose storage service:

```bash
# Start with Arweave
docker-compose --profile arweave up -d

# Start with S3
docker-compose --profile s3 up -d

# Start both (they'll conflict on port 8001)
# Don't do this - use one or the other
```

### Option 2: Environment-based switching

Set environment variable to choose service:

```bash
# In your .env file
STORAGE_SERVICE=s3  # or "arweave"
```

Then update your application initialization to choose the appropriate client.

### Option 3: Runtime switching

Keep both services available on different ports and switch at runtime.

## Comparison

| Feature | Arweave Service | S3 Service |
|---------|----------------|------------|
| **Upload Speed** | Slow (blockchain) | Fast (direct upload) |
| **Cost** | AR tokens needed | S3 storage costs |
| **Reliability** | Network dependent | High (AWS/CDN) |
| **Permanence** | Permanent (blockchain) | Depends on S3 lifecycle |
| **Global Access** | Arweave gateways | CloudFront CDN |
| **Setup** | Wallet + funding | Environment variables |
| **API Compatibility** | Original | 100% compatible |

## Troubleshooting

### Common Issues

1. **Service not starting**
   ```bash
   # Check logs
   docker-compose logs s3-service
   
   # Verify environment variables
   docker-compose exec s3-service env | grep S3_
   ```

2. **Upload failures**
   ```bash
   # Test S3 upload API directly
   curl -X POST $S3_API_ENDPOINT \
     -H "x-api-key: $S3_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"image": "dGVzdA==", "imageType": "txt"}'
   ```

3. **Missing environment variables**
   ```bash
   # Check required variables
   ./switch_storage.sh status
   
   # Update .env file
   cp .env.example .env
   # Edit .env with your S3 configuration
   ```

### Debug Mode

Run the service in debug mode:

```bash
# Stop the containerized service
docker-compose stop s3-service

# Run locally for debugging
cd s3-service
export S3_API_KEY=your-key
export S3_API_ENDPOINT=your-endpoint
export CLOUDFRONT_DOMAIN=your-domain
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8001
```

## Security Considerations

1. **API Keys**: Store securely in environment variables, never in code
2. **S3 Permissions**: Use minimal required permissions for uploads
3. **CloudFront**: Configure appropriate caching and security headers
4. **Service Auth**: Use `S3_SERVICE_API_KEY` for additional service protection

## Performance Tuning

1. **CloudFront**: Configure appropriate TTL and compression
2. **S3 Transfer**: Use multipart uploads for large files
3. **Connection Pooling**: Adjust httpx client settings for high throughput
4. **Monitoring**: Set up CloudWatch/monitoring for S3 and CloudFront

## Rollback Plan

To switch back to Arweave:

```bash
# Use the switcher script
./switch_storage.sh arweave

# Or manually
docker-compose stop s3-service
docker-compose --profile arweave up -d arweave-service
```

The application will continue working without changes since the API is identical.
