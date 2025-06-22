# Migration from Arweave to S3

This document outlines the migration from Arweave to S3 for media storage in the matrixbot project.

## Changes Made

### 1. New S3 Services

- **Created `chatbot/integrations/s3_client.py`**: Core S3 client for API communication
- **Created `chatbot/tools/s3_service.py`**: High-level S3 service wrapper
- **Created `s3-service/S3Service.js`**: JavaScript implementation for Node.js compatibility

### 2. Configuration Updates

Added new environment variables to `chatbot/config.py`:
- `S3_API_ENDPOINT`: S3 API endpoint URL
- `S3_API_KEY`: API key for S3 service  
- `CLOUDFRONT_DOMAIN`: CloudFront domain for serving URLs

### 3. Updated Components

#### Core Tools
- **`media_generation_tools.py`**: Updated to use S3 for generated images/videos
- **`permaweb_tools.py`**: Renamed and updated to use S3 for permanent storage
- **`describe_image_tool.py`**: Updated Matrix media re-upload to use S3

#### Integrations
- **`veo_service.py`**: Updated to use S3 service instead of Arweave
- **`main_orchestrator.py`**: Added S3 service initialization and injection

#### Base Classes
- **`tools/base.py`**: Added `s3_service` to ActionContext

## Environment Variables Required

Add these to your `.env` file:

```bash
# S3 Configuration
S3_API_ENDPOINT=https://your-s3-api-endpoint.com
S3_API_KEY=your-s3-api-key
CLOUDFRONT_DOMAIN=https://your-cloudfront-domain.com
```

## Backward Compatibility

- All existing Arweave functionality is preserved for reading existing content
- New uploads will use S3 while maintaining the same API interface
- Tools will prefer S3 but can still access Arweave URLs for existing content

## Migration Strategy

1. **Immediate**: Deploy with S3 configuration - new content goes to S3
2. **Gradual**: Existing Arweave URLs continue to work for access
3. **Optional**: Later migration tool could move critical content from Arweave to S3

## API Changes

### Tool Response Changes

Tools now return S3 URLs instead of Arweave URLs:

**Before:**
```json
{
  "status": "success",
  "arweave_image_url": "https://arweave.net/tx_id",
  "arweave_tx_id": "tx_id"
}
```

**After:**
```json
{
  "status": "success", 
  "s3_image_url": "https://cloudfront.domain/path/file.jpg"
}
```

### Service Method Changes

Service methods maintain the same interface but use S3:

```python
# Still works the same way
s3_url = await context.s3_service.upload_image_data(image_data, "file.png", "image/png")
```

## Benefits of S3 Migration

1. **Cost**: S3 storage is more cost-effective than Arweave for frequent uploads
2. **Speed**: Faster upload and download times with CloudFront CDN
3. **Reliability**: Enterprise-grade infrastructure
4. **Integration**: Better integration with existing AWS services
5. **Control**: More control over data lifecycle and access patterns

## Testing

1. Set up S3 API credentials in environment
2. Test image generation - verify S3 URLs are returned
3. Test video generation - verify S3 upload works
4. Test Matrix media re-upload functionality
5. Verify backward compatibility with existing Arweave URLs

## Rollback Plan

If issues arise:
1. Comment out S3 service initialization in `main_orchestrator.py`
2. Revert tools to use `arweave_service` instead of `s3_service`
3. All existing functionality will continue with Arweave

The migration is designed to be reversible with minimal code changes.
