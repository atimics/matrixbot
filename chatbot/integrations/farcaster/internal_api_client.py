"""
Internal Farcaster API Client

This client communicates with our in-house farcaster-api-service instead of
directly with Neynar or the Snapchain node. It provides the same interface
as NeynarAPIClient but uses our internal REST API.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Union

import httpx

logger = logging.getLogger(__name__)


class InternalFarcasterAPIClient:
    """
    A client for making requests to our internal Farcaster API service.
    
    This client provides the same interface as NeynarAPIClient but communicates
    with our in-house API service that wraps the Snapchain node. For methods
    not supported by the basic Snapchain node, it falls back to a Neynar client.
    """

    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        signer_uuid: Optional[str] = None,
        bot_fid: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        fallback_to_neynar: bool = True,
    ):
        """
        Initialize the internal API client.
        
        Args:
            base_url: The base URL of our internal farcaster-api-service
            api_key: Neynar API key for fallback operations
            signer_uuid: Signer UUID for posting (if needed)
            bot_fid: Bot's Farcaster ID
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries for failed requests
            retry_delay: Delay between retries in seconds
            fallback_to_neynar: Whether to use Neynar for unsupported operations
        """
        if not base_url:
            raise ValueError("Base URL is required for InternalFarcasterAPIClient.")
        
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.signer_uuid = signer_uuid
        self.bot_fid = bot_fid
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.fallback_to_neynar = fallback_to_neynar
        
        # Create client with custom timeout settings
        timeout_config = httpx.Timeout(
            connect=10.0,    # Connection timeout
            read=timeout,    # Read timeout  
            write=10.0,      # Write timeout
            pool=30.0        # Pool timeout
        )
        self._client = httpx.AsyncClient(timeout=timeout_config)
        
        # Initialize fallback Neynar client if configured
        self._neynar_client = None
        if self.fallback_to_neynar and self.api_key:
            from .neynar_api_client import NeynarAPIClient
            self._neynar_client = NeynarAPIClient(
                api_key=self.api_key,
                signer_uuid=self.signer_uuid,
                bot_fid=self.bot_fid,
                timeout=timeout,
                max_retries=max_retries,
                retry_delay=retry_delay
            )
            logger.info("Initialized Neynar fallback client for unsupported operations")
        
        logger.info(f"InternalFarcasterAPIClient initialized with base_url: {self.base_url}")
        if self._neynar_client:
            logger.info("Fallback to Neynar enabled for unsupported operations")
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
    
    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()
        if self._neynar_client:
            await self._neynar_client.close()
    
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Make an HTTP request to the internal API with retry logic.
        """
        url = f"{self.base_url}{endpoint}"
        
        for attempt in range(self.max_retries + 1):
            try:
                response = await self._client.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json_data,
                    **kwargs
                )
                response.raise_for_status()
                return response.json()
                
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    # Don't retry 404s
                    logger.debug(f"Resource not found: {url}")
                    return {}
                elif e.response.status_code >= 500 and attempt < self.max_retries:
                    # Retry server errors
                    logger.warning(f"Server error on attempt {attempt + 1}/{self.max_retries + 1}: {e}")
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                    continue
                else:
                    logger.error(f"HTTP error: {e}")
                    raise
                    
            except (httpx.RequestError, httpx.TimeoutException) as e:
                if attempt < self.max_retries:
                    logger.warning(f"Request error on attempt {attempt + 1}/{self.max_retries + 1}: {e}")
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                    continue
                else:
                    logger.error(f"Request failed after {self.max_retries + 1} attempts: {e}")
                    raise
        
        # Should not reach here, but just in case
        raise Exception("Max retries exceeded")
    
    # Core API methods that match NeynarAPIClient interface
    
    async def get_cast_by_hash(self, cast_hash: str) -> Optional[Dict[str, Any]]:
        """
        Get a cast by its hash.
        
        Args:
            cast_hash: The cast hash (with or without 0x prefix)
            
        Returns:
            Cast data dictionary or None if not found
        """
        try:
            result = await self._make_request("GET", f"/cast/{cast_hash}")
            return result if result else None
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise
    
    async def get_casts_by_fid(
        self, 
        fid: int, 
        limit: int = 25, 
        cursor: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get casts by a user's FID.
        
        Args:
            fid: The Farcaster ID
            limit: Maximum number of casts to return
            cursor: Pagination cursor (not implemented in our internal API yet)
            
        Returns:
            Dictionary containing casts and pagination info
        """
        params: Dict[str, Union[str, int]] = {"fid": fid, "limit": limit}
        if cursor:
            params["cursor"] = cursor
            
        casts = await self._make_request("GET", "/casts", params=params)
        
        # Format response to match Neynar structure
        return {
            "casts": casts,
            "next": {
                "cursor": None  # TODO: Implement pagination in internal API
            }
        }
    
    async def get_user_by_fid(self, fid: int) -> Optional[Dict[str, Any]]:
        """
        Get user information by FID.
        
        Args:
            fid: The Farcaster ID
            
        Returns:
            User data dictionary or None if not found
        """
        try:
            result = await self._make_request("GET", f"/user/{fid}")
            return result if result else None
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise
    
    async def get_users_by_fids(self, fids: List[int]) -> Dict[str, Any]:
        """
        Get multiple users by their FIDs.
        
        Args:
            fids: List of Farcaster IDs
            
        Returns:
            Dictionary containing list of users
        """
        fids_str = ",".join(str(fid) for fid in fids)
        params = {"fids": fids_str}
        
        result = await self._make_request("GET", "/v2/farcaster/user/bulk", params=params)
        return result
    

    
    async def get_node_info(self) -> Dict[str, Any]:
        """
        Get information about the underlying Snapchain node.
        
        Returns:
            Dictionary containing node information
        """
        return await self._make_request("GET", "/info")
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Check the health of the internal API service.
        
        Returns:
            Dictionary containing health status
        """
        return await self._make_request("GET", "/health")
    
    # Compatibility methods for existing code
    
    async def get_user_info(self, fid: Union[str, int]) -> Optional[Dict[str, Any]]:
        """
        Get user information by FID (compatibility method).
        """
        return await self.get_user_by_fid(int(fid))
    
    async def get_feed_by_channel_ids(
        self,
        channel_ids: List[str],
        limit: int = 25,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Get feed by channel IDs (forwards to Neynar fallback).
        """
        if self._neynar_client:
            logger.debug("Forwarding get_feed_by_channel_ids to Neynar client")
            # Convert list to comma-separated string if needed
            channel_ids_str = ",".join(channel_ids) if isinstance(channel_ids, list) else channel_ids
            return await self._neynar_client.get_feed_by_channel_ids(
                channel_ids=channel_ids_str, limit=limit, **kwargs
            )
        else:
            logger.warning("get_feed_by_channel_ids not available - no Neynar fallback configured")
            return {"casts": [], "next": {"cursor": None}}
    
    async def get_home_feed(
        self,
        fid: Optional[Union[str, int]] = None,
        limit: int = 25,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Get home feed (forwards to Neynar fallback).
        """
        if self._neynar_client:
            logger.debug("Forwarding get_home_feed to Neynar client")
            fid_str = str(fid) if fid is not None else self.bot_fid
            if fid_str:
                return await self._neynar_client.get_home_feed(fid=fid_str, limit=limit, **kwargs)
            else:
                logger.warning("No FID available for get_home_feed")
                return {"casts": [], "next": {"cursor": None}}
        else:
            logger.warning("get_home_feed not available - no Neynar fallback configured")
            return {"casts": [], "next": {"cursor": None}}
    
    async def get_notifications(
        self,
        fid: Union[str, int],
        **kwargs
    ) -> Dict[str, Any]:
        """
        Get notifications (forwards to Neynar fallback).
        """
        if self._neynar_client:
            logger.debug("Forwarding get_notifications to Neynar client")
            return await self._neynar_client.get_notifications(fid=str(fid), **kwargs)
        else:
            logger.warning("get_notifications not available - no Neynar fallback configured")
            return {"notifications": [], "next": {"cursor": None}}
    
    async def get_replies_and_recasts_for_user(
        self,
        fid: Union[str, int],
        **kwargs
    ) -> Dict[str, Any]:
        """
        Get replies and recasts for user (forwards to Neynar fallback).
        """
        if self._neynar_client:
            logger.debug("Forwarding get_replies_and_recasts_for_user to Neynar client")
            return await self._neynar_client.get_replies_and_recasts_for_user(fid=str(fid), **kwargs)
        else:
            logger.warning("get_replies_and_recasts_for_user not available - no Neynar fallback configured")
            return {"casts": [], "next": {"cursor": None}}
    
    async def get_trending_casts(
        self,
        limit: int = 25,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Get trending casts (forwards to Neynar fallback).
        """
        if self._neynar_client:
            logger.debug("Forwarding get_trending_casts to Neynar client")
            return await self._neynar_client.get_trending_casts(limit=limit, **kwargs)
        else:
            logger.warning("get_trending_casts not available - no Neynar fallback configured")
            return {"casts": [], "next": {"cursor": None}}
    
    async def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Get user by username (forwards to Neynar fallback).
        """
        if self._neynar_client:
            logger.debug("Forwarding get_user_by_username to Neynar client")
            return await self._neynar_client.get_user_by_username(username)
        else:
            logger.warning("get_user_by_username not available - no Neynar fallback configured")
            return None
    
    async def get_cast_details(self, cast_hash: str) -> Optional[Dict[str, Any]]:
        """
        Get cast details (compatibility method).
        """
        return await self.get_cast_by_hash(cast_hash)
    
    async def get_for_you_feed(
        self,
        fid: Optional[Union[str, int]] = None,
        limit: int = 25,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Get 'For You' feed (forwards to Neynar fallback).
        """
        if self._neynar_client:
            logger.debug("Forwarding get_for_you_feed to Neynar client")
            fid_str = str(fid) if fid is not None else self.bot_fid
            if fid_str:
                return await self._neynar_client.get_for_you_feed(fid=fid_str, limit=limit, **kwargs)
            else:
                logger.warning("No FID available for get_for_you_feed")
                return {"casts": [], "next": {"cursor": None}}
        else:
            logger.warning("get_for_you_feed not available - no Neynar fallback configured")
            return {"casts": [], "next": {"cursor": None}}
    
    async def quote_cast(
        self,
        text: str,
        cast_hash: str,
        signer_uuid: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Quote a cast (forwards to Neynar fallback).
        """
        if self._neynar_client:
            logger.debug("Forwarding quote_cast to Neynar client")
            # Note: We'd need to look up the cast author FID for proper quoting
            # For now, this is a simplified implementation
            logger.warning("quote_cast forwarding requires cast author FID lookup - not fully implemented")
            raise NotImplementedError(
                "quote_cast forwarding requires additional cast metadata lookup"
            )
        else:
            logger.warning("quote_cast not available - no Neynar fallback configured")
            raise NotImplementedError("quote_cast requires Neynar fallback client")
    
    async def follow_user(
        self,
        fid: Union[str, int],
        signer_uuid: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Follow a user (forwards to Neynar fallback).
        """
        if self._neynar_client:
            logger.debug("Forwarding follow_user to Neynar client")
            return await self._neynar_client.follow_user(
                target_fid=int(fid), signer_uuid=signer_uuid or self.signer_uuid
            )
        else:
            logger.warning("follow_user not available - no Neynar fallback configured")
            raise NotImplementedError("follow_user requires Neynar fallback client")
    
    async def unfollow_user(
        self,
        fid: Union[str, int],
        signer_uuid: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Unfollow a user (forwards to Neynar fallback).
        """
        if self._neynar_client:
            logger.debug("Forwarding unfollow_user to Neynar client")
            return await self._neynar_client.unfollow_user(
                target_fid=int(fid), signer_uuid=signer_uuid or self.signer_uuid
            )
        else:
            logger.warning("unfollow_user not available - no Neynar fallback configured")
            raise NotImplementedError("unfollow_user requires Neynar fallback client")
    
    async def delete_cast(
        self,
        cast_hash: str,
        signer_uuid: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Delete a cast (forwards to Neynar fallback).
        """
        if self._neynar_client:
            logger.debug("Forwarding delete_cast to Neynar client")
            return await self._neynar_client.delete_cast(
                cast_hash=cast_hash, signer_uuid=signer_uuid or self.signer_uuid
            )
        else:
            logger.warning("delete_cast not available - no Neynar fallback configured")
            raise NotImplementedError("delete_cast requires Neynar fallback client")
    
    async def delete_reaction(
        self,
        cast_hash: str,
        signer_uuid: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Delete a reaction (forwards to Neynar fallback).
        """
        if self._neynar_client:
            logger.debug("Forwarding delete_reaction to Neynar client")
            return await self._neynar_client.delete_reaction(
                cast_hash=cast_hash, signer_uuid=signer_uuid or self.signer_uuid
            )
        else:
            logger.warning("delete_reaction not available - no Neynar fallback configured")
            raise NotImplementedError("delete_reaction requires Neynar fallback client")

    async def publish_cast(
        self,
        text: str,
        signer_uuid: Optional[str] = None,
        parent: Optional[str] = None,
        embeds: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Publish a cast to Farcaster via our internal signing service.
        """
        try:
            import time
            
            # Prepare the request payload
            cast_data = {
                "text": text,
                "embeds": embeds or []
            }
            
            # Handle parent cast for replies
            if parent:
                # If parent is a cast hash, we need to look up the cast to get the FID
                parent_cast = await self.get_cast_by_hash(parent)
                if parent_cast and parent_cast.get("author", {}).get("fid"):
                    cast_data["parent_cast_hash"] = parent
                    cast_data["parent_cast_fid"] = parent_cast["author"]["fid"]
                else:
                    logger.warning(f"Could not find parent cast {parent} for reply")
            
            # Submit to our internal API
            result = await self._make_request("POST", "/v1/cast", json_data=cast_data)
            
            if result.get("success"):
                return {
                    "cast": {
                        "hash": result.get("hash"),
                        "text": text,
                        "author": {"fid": self.bot_fid} if self.bot_fid else {},
                        "timestamp": int(time.time())
                    }
                }
            else:
                logger.error(f"Failed to publish cast: {result.get('error')}")
                raise Exception(f"Cast publication failed: {result.get('error')}")
                
        except Exception as e:
            logger.error(f"Error publishing cast: {e}")
            # Try fallback to Neynar if configured
            if self._neynar_client and self.fallback_to_neynar:
                logger.info("Falling back to Neynar for cast publication")
                signer = signer_uuid or self.signer_uuid
                if not signer:
                    raise ValueError("signer_uuid is required for Neynar fallback")
                return await self._neynar_client.publish_cast(
                    text=text,
                    signer_uuid=signer,
                    parent=parent,
                    embeds=embeds,
                    **kwargs
                )
            raise
    
    async def react_to_cast(
        self,
        cast_hash: str,
        reaction_type: str = "like",
        signer_uuid: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        React to a cast via our internal signing service.
        """
        try:
            # Map reaction type string to integer
            reaction_type_map = {"like": 1, "recast": 2}
            reaction_type_int = reaction_type_map.get(reaction_type.lower(), 1)
            
            # Get the target cast to find the author FID
            target_cast = await self.get_cast_by_hash(cast_hash)
            if not target_cast or not target_cast.get("author", {}).get("fid"):
                raise ValueError(f"Could not find target cast {cast_hash} or missing author FID")
            
            # Prepare the request payload
            reaction_data = {
                "target_cast_hash": cast_hash,
                "target_cast_fid": target_cast["author"]["fid"],
                "reaction_type": reaction_type_int
            }
            
            # Submit to our internal API
            result = await self._make_request("POST", "/v1/reaction", json_data=reaction_data)
            
            if result.get("success"):
                return {
                    "reaction": {
                        "hash": result.get("hash"),
                        "target_hash": cast_hash,
                        "reaction_type": reaction_type,
                        "author": {"fid": self.bot_fid} if self.bot_fid else {}
                    }
                }
            else:
                logger.error(f"Failed to post reaction: {result.get('error')}")
                raise Exception(f"Reaction posting failed: {result.get('error')}")
                
        except Exception as e:
            logger.error(f"Error posting reaction: {e}")
            # Try fallback to Neynar if configured
            if self._neynar_client and self.fallback_to_neynar:
                logger.info("Falling back to Neynar for reaction posting")
                signer = signer_uuid or self.signer_uuid
                if not signer:
                    raise ValueError("signer_uuid is required for Neynar fallback")
                return await self._neynar_client.react_to_cast(
                    signer_uuid=signer,
                    reaction_type=reaction_type,
                    target_hash=cast_hash
                )
            raise

    async def lookup_cast_conversation(
        self, 
        cast_identifier: str, 
        include_chronological_parent_casts: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Lookup cast conversation (compatibility method).
        
        For now, this just returns the single cast. In the future,
        we could implement conversation threading by following
        parent/child relationships.
        """
        cast = await self.get_cast_by_hash(cast_identifier)
        if not cast:
            return {"conversation": {"cast": None}}
        
        return {
            "conversation": {
                "cast": cast,
                # TODO: Implement conversation threading
                "direct_replies": [],
                "chronological_parent_casts": [] if include_chronological_parent_casts else None
            }
        }
    
    async def search_casts(
        self,
        q: str,
        author_fid: Optional[int] = None,
        limit: int = 25,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Search casts (not implemented in basic Snapchain).
        
        This would require building a search index on top of the raw data.
        """
        logger.warning("search_casts not available with direct Snapchain access")
        return {"casts": [], "next": {"cursor": None}}
    
    def get_status(self) -> Dict[str, Any]:
        """Get client status information."""
        return {
            "client_type": "internal_api",
            "base_url": self.base_url,
            "signer_uuid": self.signer_uuid,
            "bot_fid": self.bot_fid,
            "max_retries": self.max_retries,
            "retry_delay": self.retry_delay
        }
