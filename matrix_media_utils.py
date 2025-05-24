import logging
from typing import Optional

logger = logging.getLogger(__name__)

class MatrixMediaUtils:
    """Centralized utilities for Matrix media URL handling using nio client."""

    @staticmethod
    async def download_media_simple(mxc_url: str, matrix_client) -> Optional[bytes]:
        """
        Simple and robust media download using matrix-nio client's built-in download method.
        
        This is the preferred method for downloading Matrix media as it handles authentication,
        federation, and API version compatibility automatically through the nio client.
        
        Args:
            mxc_url: Matrix content URI (e.g., "mxc://server.org/mediaId").
            matrix_client: Authenticated matrix-nio AsyncClient instance.
            
        Returns:
            Media content as bytes if successful, None if failed.
        """
        if not mxc_url or not isinstance(mxc_url, str) or not mxc_url.startswith("mxc://"):
            logger.warning(f"MatrixMediaUtils: Invalid MXC URL format: {mxc_url}")
            return None
            
        if not matrix_client:
            logger.error("MatrixMediaUtils: No matrix client provided for download")
            return None
            
        try:
            logger.debug(f"MatrixMediaUtils: Downloading media via nio client: {mxc_url}")
            download_response = await matrix_client.download(mxc_url)
            
            if download_response and download_response.body:
                logger.info(f"MatrixMediaUtils: Successfully downloaded media. Size: {len(download_response.body)} bytes")
                return download_response.body
            else:
                logger.warning(f"MatrixMediaUtils: Download response empty for: {mxc_url}")
                return None
                
        except Exception as e:
            logger.error(f"MatrixMediaUtils: Failed to download media '{mxc_url}': {e}", exc_info=True)
            return None

