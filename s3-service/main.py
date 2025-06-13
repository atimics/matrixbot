"""
S3 Service - Secure, lean microservice for S3 uploads
Drop-in replacement for the Arweave service using S3 compatible storage.
"""
import asyncio
import json
import logging
import os
import uuid
from typing import Dict, Optional, Annotated
from urllib.parse import urlparse

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Depends, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import httpx

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class S3Manager:
    """Manages S3 uploads using the provided JavaScript S3 service"""
    
    def __init__(self, api_key: str, api_endpoint: str, cloudfront_domain: str):
        self.api_key = api_key
        self.api_endpoint = api_endpoint.rstrip("/") if api_endpoint else ""
        self.cloudfront_domain = cloudfront_domain.rstrip("/") if cloudfront_domain else ""
        self.client = httpx.AsyncClient(timeout=120.0)
    
    async def initialize(self):
        """Initialize the S3 manager"""
        if not self.api_key or not self.api_endpoint or not self.cloudfront_domain:
            logger.critical("FATAL: Missing required environment variables (S3_API_KEY, S3_API_ENDPOINT, CLOUDFRONT_DOMAIN)")
            return False
        
        logger.info(f"S3 Manager initialized with endpoint: {self.api_endpoint}")
        return True
    
    def is_ready(self) -> bool:
        """Check if the S3 manager is ready for operations"""
        return bool(self.api_key and self.api_endpoint and self.cloudfront_domain)
    
    async def upload_data(self, data: bytes, content_type: str) -> Optional[str]:
        """
        Upload data to S3 and return the public URL
        
        Args:
            data: Raw data bytes to upload
            content_type: MIME type of the data
            
        Returns:
            Public S3 URL or None if failed
        """
        if not self.is_ready():
            logger.error("S3Manager not ready - missing configuration")
            return None
            
        try:
            # Determine file extension from content type
            ext_map = {
                'image/png': 'png',
                'image/jpeg': 'jpg', 
                'image/jpg': 'jpg',
                'image/gif': 'gif',
                'video/mp4': 'mp4',
                'text/plain': 'txt',
                'application/json': 'json'
            }
            
            file_ext = ext_map.get(content_type, 'bin')
            filename = f"{uuid.uuid4().hex}.{file_ext}"
            
            # Prepare the request payload similar to the JavaScript service
            import base64
            image_base64 = base64.b64encode(data).decode('utf-8')
            
            payload = {
                "image": image_base64,
                "imageType": file_ext,
            }
            
            # Parse the endpoint URL
            parsed_url = urlparse(self.api_endpoint)
            
            headers = {
                'Content-Type': 'application/json',
                'x-api-key': self.api_key,
            }
            
            logger.info(f"Uploading {len(data)} bytes to S3 as {filename}")
            
            response = await self.client.post(
                self.api_endpoint,
                json=payload,
                headers=headers
            )
            
            if response.status_code == 200:
                try:
                    result = response.json()
                    response_data = result.get('body')
                    if isinstance(response_data, str):
                        response_data = json.loads(response_data)
                    elif response_data is None:
                        response_data = result
                    
                    if response_data and response_data.get('url'):
                        s3_url = response_data['url']
                        logger.info(f"Upload successful: {s3_url}")
                        return s3_url
                    else:
                        logger.error(f"Invalid S3 response format - missing URL. Response: {result}")
                        return None
                        
                except (json.JSONDecodeError, KeyError) as e:
                    logger.error(f"Failed to parse S3 response: {e}")
                    logger.error(f"Raw response: {response.text}")
                    return None
            else:
                logger.error(f"S3 upload failed with status {response.status_code}: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"S3 upload error: {e}", exc_info=True)
            return None
    
    async def download_data(self, url: str) -> Optional[bytes]:
        """
        Download data from a URL (supports redirects)
        
        Args:
            url: URL to download from
            
        Returns:
            Downloaded data bytes or None if failed
        """
        try:
            response = await self.client.get(url, follow_redirects=True)
            if response.status_code == 200:
                logger.info(f"Successfully downloaded data from {url} ({len(response.content)} bytes)")
                return response.content
            else:
                logger.error(f"Failed to download from {url}: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Download error from {url}: {e}")
            return None
    
    async def cleanup(self):
        """Clean up resources"""
        if self.client:
            await self.client.aclose()


# Pydantic models for API requests/responses (matching Arweave service)
class UploadResponse(BaseModel):
    transaction_id: str  # Using S3 URL as transaction ID for compatibility
    wallet_address: str  # Using CloudFront domain for compatibility
    data_size: int
    content_type: str
    upload_status: str
    arweave_url: str  # Actually S3 URL, but keeping same field name for compatibility


class WalletInfo(BaseModel):
    address: str  # CloudFront domain
    balance_ar: float  # Always 1.0 for S3 (unlimited)
    status: str


class HealthResponse(BaseModel):
    status: str
    wallet_ready: bool
    wallet_address: Optional[str] = None


# Initialize the S3 manager
def get_s3_manager():
    """Factory function to get the S3 manager"""
    api_key = os.getenv("S3_API_KEY")
    api_endpoint = os.getenv("S3_API_ENDPOINT") 
    cloudfront_domain = os.getenv("CLOUDFRONT_DOMAIN")
    return S3Manager(api_key, api_endpoint, cloudfront_domain)


# Initialize FastAPI app
app = FastAPI(
    title="S3 Service",
    description="Secure, lean microservice for S3 uploads (drop-in replacement for Arweave service)",
    version="1.0.0"
)

# Global S3 manager instance
s3_manager = get_s3_manager()

# API Key for basic authentication
API_KEY = os.getenv("S3_SERVICE_API_KEY")


def validate_api_key(x_api_key: Optional[str] = None):
    """Validate API key if one is configured"""
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")


@app.on_event("startup")
async def startup_event():
    """Initialize the S3 manager on startup"""
    success = await s3_manager.initialize()
    if not success:
        logger.error("Failed to initialize S3 manager")
    else:
        logger.info("S3 service started successfully")


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown"""
    await s3_manager.cleanup()


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    is_ready = s3_manager.is_ready()
    return HealthResponse(
        status="healthy" if is_ready else "unhealthy",
        wallet_ready=is_ready,
        wallet_address=s3_manager.cloudfront_domain if is_ready else None
    )


@app.get("/wallet", response_model=WalletInfo)
async def get_wallet_info():
    """Get wallet information (S3 equivalent)"""
    if not s3_manager.is_ready():
        raise HTTPException(status_code=503, detail="S3 service not configured")
    
    return WalletInfo(
        address=s3_manager.cloudfront_domain,
        balance_ar=1.0,  # S3 has "unlimited" balance
        status="ready"
    )


async def _parse_tags(tags: Optional[str]) -> Dict[str, str]:
    """Parse tags from JSON string format"""
    if not tags:
        return {}
    
    try:
        parsed_tags = json.loads(tags)
        if isinstance(parsed_tags, dict):
            return parsed_tags
        else:
            logger.warning(f"Tags must be a JSON object, got: {type(parsed_tags)}")
            return {}
    except json.JSONDecodeError as e:
        logger.warning(f"Invalid JSON in tags parameter: {e}")
        return {}


def _create_upload_response(
    s3_url: str, 
    data_size: int, 
    content_type: str
) -> UploadResponse:
    """Create a standardized upload response"""
    return UploadResponse(
        transaction_id=s3_url,  # Use S3 URL as transaction ID
        wallet_address=s3_manager.cloudfront_domain,
        data_size=data_size,
        content_type=content_type,
        upload_status="submitted",
        arweave_url=s3_url  # Return S3 URL in arweave_url field for compatibility
    )


@app.post("/upload", response_model=UploadResponse)
async def upload_to_s3(
    file: UploadFile = File(...),
    tags: Optional[str] = Form(None),
    x_api_key: Annotated[str | None, Header()] = None
):
    """
    Upload a file to S3
    
    Args:
        file: The file to upload
        tags: Optional JSON string of tags (for compatibility, not used in S3)
        x_api_key: Optional API key for authentication
    """
    # Validate API key if configured
    validate_api_key(x_api_key)
    
    if not s3_manager.is_ready():
        raise HTTPException(status_code=503, detail="S3 service not configured")
    
    try:
        # Read file content
        file_content = await file.read()
        if not file_content:
            raise HTTPException(status_code=400, detail="Empty file provided")
        
        logger.info(f"Uploading file: {file.filename} ({len(file_content)} bytes)")
        
        # Parse custom tags (for compatibility, though S3 doesn't use them the same way)
        custom_tags = await _parse_tags(tags)
        
        # Upload to S3
        s3_url = await s3_manager.upload_data(
            data=file_content,
            content_type=file.content_type or "application/octet-stream"
        )
        
        if not s3_url:
            raise HTTPException(status_code=500, detail="Failed to upload to S3")
        
        # Create response
        response = _create_upload_response(
            s3_url=s3_url,
            data_size=len(file_content),
            content_type=file.content_type or "application/octet-stream"
        )
        
        logger.info(f"Upload successful: {s3_url}")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@app.post("/upload/data", response_model=UploadResponse)
async def upload_data_to_s3(
    data: str = Form(...),
    content_type: str = Form("text/plain"),
    tags: Optional[str] = Form(None),
    x_api_key: Annotated[str | None, Header()] = None
):
    """
    Upload raw data to S3
    
    Args:
        data: The data to upload as a string
        content_type: Content type of the data
        tags: Optional JSON string of tags (for compatibility)
        x_api_key: Optional API key for authentication
    """
    # Validate API key if configured
    validate_api_key(x_api_key)
    
    if not s3_manager.is_ready():
        raise HTTPException(status_code=503, detail="S3 service not configured")
    
    try:
        data_bytes = data.encode('utf-8')
        logger.info(f"Uploading data ({len(data_bytes)} bytes)")
        
        # Parse custom tags
        custom_tags = await _parse_tags(tags)
        
        # Upload to S3
        s3_url = await s3_manager.upload_data(
            data=data_bytes,
            content_type=content_type
        )
        
        if not s3_url:
            raise HTTPException(status_code=500, detail="Failed to upload data to S3")
        
        # Create response
        response = _create_upload_response(
            s3_url=s3_url,
            data_size=len(data_bytes),
            content_type=content_type
        )
        
        logger.info(f"Data upload successful: {s3_url}")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Data upload failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Data upload failed: {str(e)}")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
