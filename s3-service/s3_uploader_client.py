"""
S3 Uploader Client

Drop-in replacement for ArweaveUploaderClient that uses S3 storage instead of Arweave.
Provides the same interface as ArweaveUploaderClient for seamless migration.
"""

import json
import logging
from typing import Dict, Optional

import httpx

logger = logging.getLogger(__name__)


class S3UploaderClient:
    """Client for uploading data to S3 via S3 uploader service - drop-in replacement for ArweaveUploaderClient."""

    def __init__(
        self, 
        uploader_service_url: str, 
        gateway_url: str = "https://cloudfront.example.com",
        api_key: Optional[str] = None
    ):
        """
        Initialize S3 uploader client.

        Args:
            uploader_service_url: URL of the S3 service (replaces Arweave service)
            gateway_url: CloudFront domain for constructing public URLs (replaces Arweave gateway)
            api_key: Optional API key for authenticating with the S3 service
        """
        self.uploader_service_url = uploader_service_url.rstrip("/")
        self.gateway_url = gateway_url.rstrip("/")
        self.api_key = api_key

    def _get_headers(self) -> Dict[str, str]:
        """Get headers for requests including API key if configured."""
        headers = {}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    async def upload_data(
        self,
        data: bytes,
        content_type: str,
        tags: Optional[Dict[str, str]] = None,
    ) -> Optional[str]:
        """
        Upload data to S3 via the S3 service.

        Args:
            data: Raw data bytes to upload  
            content_type: MIME type of the data
            tags: Optional dictionary of tags (for compatibility, not used in S3)

        Returns:
            S3 URL (formatted like Arweave transaction ID for compatibility) or None if failed
        """
        try:
            # Prepare multipart form data for file upload
            files = {"file": ("data", data, content_type)}
            form_data = {}
            
            # Add tags as JSON string if provided (for compatibility)
            if tags:
                form_data["tags"] = json.dumps(tags)

            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self.uploader_service_url}/upload",
                    files=files,
                    data=form_data,
                    headers=self._get_headers(),
                )

                response.raise_for_status()
                result = response.json()

                # Extract S3 URL from response - S3 service uses 'arweave_url' field for compatibility
                s3_url = result.get("arweave_url")

                if s3_url:
                    logger.info(
                        f"S3UploaderClient: Successfully uploaded data to S3: {s3_url}"
                    )
                    # Return just the path part to mimic Arweave transaction ID format
                    if s3_url.startswith(self.gateway_url):
                        return s3_url[len(self.gateway_url):].lstrip('/')
                    return s3_url
                else:
                    logger.error(
                        f"S3UploaderClient: Upload succeeded but no URL in response: {result}"
                    )
                    return None

        except httpx.HTTPStatusError as e:
            logger.error(
                f"S3UploaderClient: HTTP error during upload: {e.response.status_code} - {e.response.text}"
            )
            return None
        except Exception as e:
            logger.error(f"S3UploaderClient: Upload failed: {e}")
            return None

    def get_arweave_url(self, tx_id: str) -> str:
        """
        Construct a public S3 URL from a transaction ID (actually S3 path).

        Args:
            tx_id: S3 path or full URL

        Returns:
            Public URL for accessing the data
        """
        if tx_id.startswith('http'):
            return tx_id
        return f"{self.gateway_url}/{tx_id}"

    async def get_upload_status(self, tx_id: str) -> Optional[Dict]:
        """
        Get upload status (compatibility method - S3 uploads are immediate).

        Args:
            tx_id: S3 URL or path

        Returns:
            Status dict or None
        """
        try:
            # For S3, we can just check if the file exists by making a HEAD request
            url = self.get_arweave_url(tx_id)
            async with httpx.AsyncClient() as client:
                response = await client.head(url)
                if response.status_code == 200:
                    return {
                        "status": "confirmed",
                        "url": url,
                        "confirmed": True
                    }
                else:
                    return {
                        "status": "not_found",
                        "url": url,
                        "confirmed": False
                    }
        except Exception as e:
            logger.error(f"S3UploaderClient: Failed to check upload status: {e}")
            return None

    async def get_wallet_address(self) -> Optional[str]:
        """
        Get the S3 service address (CloudFront domain).

        Returns:
            CloudFront domain or None if failed
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.uploader_service_url}/wallet",
                    headers=self._get_headers()
                )
                response.raise_for_status()
                wallet_info = response.json()
                return wallet_info.get("address")
        except Exception as e:
            logger.error(f"S3UploaderClient: Failed to get wallet address: {e}")
            return None

    async def get_wallet_balance(self) -> Optional[str]:
        """
        Get the S3 service balance (always unlimited for S3).

        Returns:
            Balance string or None if failed
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.uploader_service_url}/wallet",
                    headers=self._get_headers()
                )
                response.raise_for_status()
                wallet_info = response.json()
                balance = wallet_info.get("balance_ar", 1.0)
                return f"{balance} AR"  # Format like Arweave for compatibility
        except Exception as e:
            logger.error(f"S3UploaderClient: Failed to get wallet balance: {e}")
            return None

    async def get_wallet_info(self) -> Optional[Dict]:
        """
        Get complete S3 service information.

        Returns:
            Service info dictionary or None if failed
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.uploader_service_url}/wallet",
                    headers=self._get_headers()
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"S3UploaderClient: Failed to get wallet info: {e}")
            return None


# Alias for drop-in replacement
ArweaveUploaderClient = S3UploaderClient
