"""
Arweave Uploader Client

This module provides integration with Arweave for permanent data storage on the permaweb.
Supports uploading text, JSON, images, and videos with custom tags.
"""

import logging
from typing import Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


class ArweaveUploaderClient:
    """Client for uploading data to Arweave via an uploader service."""

    def __init__(
        self, api_endpoint: str, api_key: str, gateway_url: str = "https://arweave.net"
    ):
        """
        Initialize Arweave uploader client.

        Args:
            api_endpoint: API endpoint of the Arweave uploader service
            api_key: API key for authentication
            gateway_url: Arweave gateway URL for constructing public URLs
        """
        self.api_endpoint = api_endpoint.rstrip("/")
        self.api_key = api_key
        self.gateway_url = gateway_url.rstrip("/")

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
            # Prepare headers
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/octet-stream",
            }

            # Prepare form data
            files = {"data": ("data", data, content_type)}

            # Prepare tags as JSON
            form_data = {}
            if tags:
                # Convert tags to the format expected by the uploader service
                form_data["tags"] = str(tags)  # Will be JSON stringified

            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.api_endpoint}/upload",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    files=files,
                    data=form_data,
                )

                response.raise_for_status()
                result = response.json()

                # Extract transaction ID from response
                tx_id = (
                    result.get("txid")
                    or result.get("transaction_id")
                    or result.get("id")
                )

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
        Check the status of an Arweave transaction.

        Args:
            tx_id: Transaction ID to check

        Returns:
            Status information or None if failed
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(f"{self.gateway_url}/tx/{tx_id}")
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(
                f"ArweaveUploaderClient: Failed to get status for {tx_id}: {e}"
            )
            return None
