import logging
import httpx
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

class MatrixMediaUtils:
    """Centralized utilities for Matrix media URL handling with API version fallback."""
    
    @staticmethod
    async def convert_mxc_to_http_with_fallback(
        mxc_url: str, 
        client_hs_base_url: Optional[str] = None,
        access_token: Optional[str] = None  # New parameter
    ) -> str:
        """
        Convert an MXC URI to an HTTP download URL using fallback API versions.
        
        This method tries multiple Matrix media API versions and validates URLs
        before returning them. Prefers using the client's homeserver for federation
        support, with fallback to direct origin server resolution.
        
        Args:
            mxc_url: Matrix content URI (mxc://server/media_id)
            client_hs_base_url: Optional bot's homeserver URL (e.g., "https://matrix.org")
                               If provided, uses this server to fetch media via federation.
                               If None, falls back to direct origin server resolution.
            access_token: Optional Matrix access token for authenticated requests.
            
        Returns:
            HTTP URL that can be accessed externally, or original URL if conversion fails
        """
        if not mxc_url or not isinstance(mxc_url, str) or not mxc_url.startswith("mxc://"):
            logger.warning(f"MatrixMediaUtils: Invalid MXC URL format: {mxc_url}")
            return mxc_url
        
        try:
            # Extract server and media_id from mxc://server/media_id format
            parts = mxc_url[6:].split("/", 1)  # Remove "mxc://" and split
            if len(parts) != 2:
                logger.error(f"MatrixMediaUtils: Invalid MXC URL format: {mxc_url}")
                return mxc_url
            
            mxc_origin_server, mxc_media_id = parts
            if not mxc_origin_server or not mxc_media_id:
                logger.error(f"MatrixMediaUtils: Empty server or media_id in MXC URL: {mxc_url}")
                return mxc_url
            
            # Try multiple Matrix media API versions as fallbacks
            api_versions = ["v3", "v1", "r0"]
            
            headers = {}
            if (access_token):
                headers["Authorization"] = f"Bearer {access_token}"
                logger.info("MatrixMediaUtils: Using access token for media validation requests.")
            
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers=headers) as client:
                # First try: Use client's homeserver if provided (federation approach)
                if client_hs_base_url and client_hs_base_url.startswith("http"):
                    clean_client_hs_base_url = client_hs_base_url.rstrip('/')
                    logger.info(f"MatrixMediaUtils: Trying federation approach via {clean_client_hs_base_url} for {mxc_url}")
                    
                    for version in api_versions:
                        federation_url = f"{clean_client_hs_base_url}/_matrix/media/{version}/download/{mxc_origin_server}/{mxc_media_id}"
                        logger.info(f"MatrixMediaUtils: Trying federation API {version}: {federation_url}")
                        
                        try:
                            response = await client.head(federation_url)
                            if 200 <= response.status_code < 400:
                                logger.info(f"MatrixMediaUtils: Successfully validated federation URL (status: {response.status_code}): {federation_url}")
                                return federation_url
                            else:
                                logger.warning(f"MatrixMediaUtils: Federation API {version} returned status {response.status_code}")
                        except httpx.RequestError as e:
                            logger.warning(f"MatrixMediaUtils: Federation API {version} request error: {e}")
                        except Exception as e:
                            logger.warning(f"MatrixMediaUtils: Federation API {version} unexpected error: {e}")
                
                # Second try: Direct origin server approach (fallback)
                logger.info(f"MatrixMediaUtils: Trying direct approach via origin server {mxc_origin_server} for {mxc_url}")
                
                for version in api_versions:
                    direct_url = f"https://{mxc_origin_server}/_matrix/media/{version}/download/{mxc_origin_server}/{mxc_media_id}"
                    logger.info(f"MatrixMediaUtils: Trying direct API {version}: {direct_url}")
                    
                    try:
                        response = await client.head(direct_url)
                        if 200 <= response.status_code < 400:
                            logger.info(f"MatrixMediaUtils: Successfully validated direct URL (status: {response.status_code}): {direct_url}")
                            return direct_url
                        else:
                            logger.warning(f"MatrixMediaUtils: Direct API {version} returned status {response.status_code}")
                    except httpx.RequestError as e:
                        logger.warning(f"MatrixMediaUtils: Direct API {version} request error: {e}")
                    except Exception as e:
                        logger.warning(f"MatrixMediaUtils: Direct API {version} unexpected error: {e}")
            
            # If all validation attempts fail, return the preferred fallback URL
            if client_hs_base_url and client_hs_base_url.startswith("http"):
                clean_client_hs_base_url = client_hs_base_url.rstrip('/')
                fallback_url = f"{clean_client_hs_base_url}/_matrix/media/v3/download/{mxc_origin_server}/{mxc_media_id}"
                logger.error(f"MatrixMediaUtils: All validation attempts failed. Using federation v3 fallback: {fallback_url}")
            else:
                fallback_url = f"https://{mxc_origin_server}/_matrix/media/v3/download/{mxc_origin_server}/{mxc_media_id}"
                logger.error(f"MatrixMediaUtils: All validation attempts failed. Using direct v3 fallback: {fallback_url}")
            
            return fallback_url
            
        except Exception as e:
            logger.error(f"MatrixMediaUtils: Failed to convert MXC URL '{mxc_url}': {e}")
            return mxc_url

    @staticmethod
    def convert_mxc_to_http_simple(
        mxc_url: str,
        client_hs_base_url: Optional[str] = None, # If None, resolves against MXC origin server
        preferred_version: str = "v3",
        access_token: Optional[str] = None # New parameter, though not used in simple sync version
    ) -> str:
        """
        Simple MXC to HTTP conversion without validation (for synchronous use).
        
        Args:
            mxc_url: Matrix content URI (mxc://server/media_id)
            client_hs_base_url: Optional bot's homeserver URL. If provided, uses federation approach.
            preferred_version: API version to use (default: "v3")
            access_token: Optional Matrix access token (not used in this simple version).
            
        Returns:
            HTTP URL using specified API version, or original URL if conversion fails
        """
        if not mxc_url or not isinstance(mxc_url, str) or not mxc_url.startswith("mxc://"):
            logger.warning(f"MatrixMediaUtils: Invalid MXC URL format: {mxc_url}")
            return mxc_url
        
        try:
            # Extract server and media_id from mxc://server/media_id format
            parts = mxc_url[6:].split("/", 1)  # Remove "mxc://" and split
            if len(parts) != 2:
                logger.error(f"MatrixMediaUtils: Invalid MXC URL format: {mxc_url}")
                return mxc_url
            
            mxc_origin_server, mxc_media_id = parts
            if not mxc_origin_server or not mxc_media_id:
                logger.error(f"MatrixMediaUtils: Empty server or media_id in MXC URL: {mxc_url}")
                return mxc_url

            # Prefer federation approach if client homeserver is provided
            if client_hs_base_url and client_hs_base_url.startswith("http"):
                try:
                    clean_client_hs_base_url = client_hs_base_url.rstrip('/')
                    http_url = f"{clean_client_hs_base_url}/_matrix/media/{preferred_version}/download/{mxc_origin_server}/{mxc_media_id}"
                    logger.debug(f"MatrixMediaUtils: Using federation approach: {http_url}")
                    return http_url
                except Exception as e:
                    logger.warning(f"MatrixMediaUtils: Could not construct federation URL, falling back to direct: {e}")
            
            # Fallback: Direct origin server approach
            http_url = f"https://{mxc_origin_server}/_matrix/media/{preferred_version}/download/{mxc_origin_server}/{mxc_media_id}"
            logger.debug(f"MatrixMediaUtils: Using direct approach: {http_url}")
            return http_url
            
        except Exception as e:
            logger.error(f"MatrixMediaUtils: Failed to convert MXC URL '{mxc_url}': {e}")
            return mxc_url

    @staticmethod
    def extract_homeserver_from_user_id(user_id: str) -> Optional[str]:
        """
        Extract homeserver domain from a Matrix user ID.
        
        Args:
            user_id: Matrix user ID (e.g., "@user:matrix.org")
            
        Returns:
            Homeserver domain (e.g., "matrix.org") or None if invalid
        """
        try:
            if user_id.startswith("@") and ":" in user_id:
                return user_id.split(":", 1)[1]
        except Exception as e:
            logger.warning(f"MatrixMediaUtils: Could not extract homeserver from user_id '{user_id}': {e}")
        return None