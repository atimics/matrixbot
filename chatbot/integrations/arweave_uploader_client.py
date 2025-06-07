"""
Arweave Uploader Client

This module provides integration with Arweave for permanent data storage on the permaweb.
Communicates with the internal Arweave uploader microservice.
"""

import json
import logging
from typing import Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


class ArweaveUploaderClient:
    """Client for uploading data to Arweave via internal uploader service."""

    def __init__(
        self, 
        uploader_service_url: str, 
        gateway_url: str = "https://arweave.net",
        api_key: Optional[str] = None
    ):
        """
        Initialize Arweave uploader client.

        Args:
            uploader_service_url: URL of the internal Arweave uploader service
            gateway_url: Arweave gateway URL for constructing public URLs
            api_key: Optional API key for authenticating with the uploader service
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
        tags: Optional[List[Dict[str, str]]] = None,
    ) -> Optional[str]:
        """
        Upload data to Arweave via the uploader service.

        Args:
            data: Raw data bytes to upload  
            content_type: MIME type of the data
            tags: Optional list of Arweave tags in format [{"name": "key", "value": "val"}]

        Returns:
            Arweave transaction ID (TXID) or None if failed
        """
        try:
            # Prepare multipart form data
            files = {"file": ("data", data, content_type)}
            form_data = {"content_type": content_type}
            
            # Add tags as JSON string if provided
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

                # Extract transaction ID from response
                tx_id = result.get("tx_id")

                if tx_id:
                    logger.info(
                        f"ArweaveUploaderClient: Successfully uploaded data to Arweave: {tx_id}"
                    )
                    return tx_id
                else:
                    logger.error(
                        f"ArweaveUploaderClient: Upload succeeded but no transaction ID in response: {result}"
                    )
                    return None

        except httpx.HTTPStatusError as e:
            logger.error(
                f"ArweaveUploaderClient: HTTP error during upload: {e.response.status_code} - {e.response.text}"
            )
            return None
        except Exception as e:
            logger.error(f"ArweaveUploaderClient: Upload failed: {e}")
            return None

    def get_arweave_url(self, tx_id: str) -> str:
        """
        Construct a public Arweave URL from a transaction ID.

        Args:
            tx_id: Arweave transaction ID

        Returns:
            Public URL for accessing the data
        """
        return f"{self.gateway_url}/{tx_id}"

    async def get_upload_status(self, tx_id: str) -> Optional[Dict]:
        """
        Check the status of an Arweave transaction via the uploader service.

        Args:
            tx_id: Transaction ID to check

        Returns:
            Status information or None if failed
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.uploader_service_url}/status/{tx_id}",
                    headers=self._get_headers()
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(
                f"ArweaveUploaderClient: Failed to get status for {tx_id}: {e}"
            )
            return None

    async def get_wallet_address(self) -> Optional[str]:
        """
        Get the Arweave wallet address from the uploader service.

        Returns:
            Wallet address or None if failed
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.uploader_service_url}/wallet-info",
                    headers=self._get_headers()
                )
                response.raise_for_status()
                result = response.json()
                return result.get("address")
        except Exception as e:
            logger.error(f"ArweaveUploaderClient: Failed to get wallet address: {e}")
            return None

    async def get_wallet_balance(self) -> Optional[str]:
        """
        Get the Arweave wallet balance from the uploader service.

        Returns:
            Balance in Winston as string, or None if failed
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(f"{self.uploader_service_url}/wallet-info")
                response.raise_for_status()
                result = response.json()
                return result.get("balance_winston")
        except Exception as e:
            logger.error(f"ArweaveUploaderClient: Failed to get wallet balance: {e}")
            return None

    async def get_wallet_info(self) -> Optional[Dict]:
        """
        Get complete wallet information from the uploader service.

        Returns:
            Wallet info dictionary or None if failed
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(f"{self.uploader_service_url}/wallet-info")
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"ArweaveUploaderClient: Failed to get wallet info: {e}")
            return None
