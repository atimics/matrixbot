# S3 Service

Drop-in replacement for the Arweave service using S3-compatible storage.

## Overview

This service provides the same API interface as the Arweave service but uploads files to S3-compatible storage instead of the Arweave blockchain. It's designed to be a seamless replacement that requires no changes to client code.

## Key Features

- **Drop-in Replacement**: Same API as Arweave service - just change the endpoint
- **S3 Compatible**: Works with AWS S3, CloudFront, and S3-compatible services
- **Secure Design**: API key authentication and non-root execution
- **Clean API**: Simple REST endpoints for file and data uploads
- **Health Monitoring**: Built-in health checks and service status monitoring

## API Endpoints

### `GET /health`
Returns service health status and readiness.

**Response:**
```json
{
  "status": "healthy",
  "wallet_ready": true,
  "wallet_address": "https://your-cloudfront-domain.com"
}
```

### `GET /wallet`
Returns service information (S3 equivalent of wallet info).

**Response:**
```json
{
  "address": "https://your-cloudfront-domain.com",
  "balance_ar": 1.0,
  "status": "ready"
}
```

### `POST /upload`
Upload a file to S3.

**Request:**
- **file**: Multipart file upload
- **tags**: Optional JSON string of metadata tags (for compatibility)
- **x-api-key**: Optional API key header

**Response:**
```json
{
  "transaction_id": "https://your-cloudfront-domain.com/abc123.png",
  "wallet_address": "https://your-cloudfront-domain.com",
  "data_size": 12345,
  "content_type": "image/png",
  "upload_status": "submitted",
  "arweave_url": "https://your-cloudfront-domain.com/abc123.png"
}
```

### `POST /upload/data`
Upload raw data to S3.

**Request:**
- **data**: String data to upload
- **content_type**: MIME type of the data (default: "text/plain")
- **tags**: Optional JSON string of metadata tags (for compatibility)
- **x-api-key**: Optional API key header

**Response:** Same format as `/upload`

## Configuration

### Environment Variables

- `S3_API_KEY`: API key for the S3 upload service
- `S3_API_ENDPOINT`: Endpoint URL for the S3 upload service
- `CLOUDFRONT_DOMAIN`: CloudFront domain for public file access
- `S3_SERVICE_API_KEY`: Optional API key for endpoint authentication

### Required Setup

1. **S3 Upload Service**: You need a running S3 upload service that accepts the JavaScript-style API (image base64 + imageType)
2. **CloudFront Distribution**: For public file access
3. **Environment Variables**: All required variables must be set

## Docker Usage

```bash
# Build the image
docker build -t s3-service .

# Run with environment variables
docker run -d \
  --name s3-service \
  -p 8001:8001 \
  -e S3_API_KEY=your_s3_api_key \
  -e S3_API_ENDPOINT=https://your-s3-api.com/upload \
  -e CLOUDFRONT_DOMAIN=https://your-cloudfront.com \
  -e S3_SERVICE_API_KEY=optional_auth_key \
  s3-service
```

## Integration Example

This service is designed to be a drop-in replacement for the Arweave service:

```python
import httpx

# Upload a file (same as Arweave service)
with open("image.jpg", "rb") as f:
    response = httpx.post(
        "http://s3-service:8001/upload",
        files={"file": f},
        data={"tags": '{"App-Name": "ChatBot", "Type": "Image"}'}
    )
    
if response.status_code == 200:
    result = response.json()
    print(f"Uploaded to: {result['arweave_url']}")  # Actually S3 URL
```

## Compatibility Notes

- **Field Names**: Uses the same response field names as Arweave service (including `arweave_url`) for compatibility
- **Transaction ID**: Uses the S3 URL as the transaction ID
- **Wallet Address**: Uses the CloudFront domain as the wallet address
- **Balance**: Always returns 1.0 (unlimited capacity)
- **Tags**: Accepts tags for compatibility but doesn't use them the same way as Arweave

## Security Features

- **Non-root execution**: Service runs as `appuser`
- **API key authentication**: Optional API key protection for endpoints
- **Environment-based config**: Sensitive data via environment variables
- **Structured logging**: Comprehensive audit trail

## Development

```bash
# Install dependencies
poetry install

# Run tests
poetry run pytest

# Run the service locally
poetry run uvicorn main:app --reload --host 0.0.0.0 --port 8001
```

## File Type Support

The service automatically determines file extensions based on MIME types:

- `image/png` → `.png`
- `image/jpeg` → `.jpg`
- `image/gif` → `.gif`
- `video/mp4` → `.mp4`
- `text/plain` → `.txt`
- `application/json` → `.json`
- Other types → `.bin`

## Monitoring

The service provides comprehensive logging and health checks:

- Health endpoint for monitoring systems
- Structured logging with timestamps
- Error tracking and reporting
- Upload success/failure metrics

## Migration from Arweave

To migrate from Arweave service to S3 service:

1. **Deploy S3 Service**: Use the same Docker compose setup
2. **Update Environment**: Change service endpoint in your application
3. **No Code Changes**: The API is identical, no client code changes needed
4. **Test Thoroughly**: Verify uploads work correctly with your S3 setup

The service is designed to be completely transparent to existing client code.
