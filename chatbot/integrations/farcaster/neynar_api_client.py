#!/usr/bin/env python3
"""
Neynar API Client for Farcaster

This module provides a client for interacting with the Neynar Farcaster API.
"""
import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


class NeynarAPIError(Exception):
    """Base exception for Neynar API errors."""
    pass


class NeynarNetworkError(NeynarAPIError):
    """Network-related errors when connecting to Neynar API."""
    pass


class NeynarRateLimitError(NeynarAPIError):
    """Rate limit exceeded error."""
    pass


class NeynarAPIClient:
    """
    A client for making requests to the Neynar Farcaster API.
    """

    DEFAULT_BASE_URL = "https://api.neynar.com/v2"

    def __init__(
        self,
        api_key: str,
        signer_uuid: Optional[str] = None,
        bot_fid: Optional[str] = None,
        base_url: Optional[str] = None,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        timeout: float = 30.0,
    ):
        if not api_key:
            raise ValueError("API key is required for NeynarAPIClient.")
        self.api_key = api_key
        self.signer_uuid = signer_uuid
        self.bot_fid = bot_fid
        self.base_url = base_url or self.DEFAULT_BASE_URL
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        
        # Create HTTP client with connection pooling and timeout settings
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout=timeout, connect=10.0),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            transport=httpx.AsyncHTTPTransport(retries=1),
        )
        
        # Rate limit tracking
        self.rate_limit_info = {
            "limit": None,
            "remaining": None,
            "reset": None, # Could be timestamp or seconds
            "last_updated_client": 0.0
        }
        
        # Network health tracking
        self.network_health = {
            "consecutive_failures": 0,
            "last_success": time.time(),
            "is_available": True,
        }

    def _get_headers(self, is_post: bool = False) -> Dict[str, str]:
        headers = {
            "accept": "application/json",
            "api_key": self.api_key,
        }
        if is_post:
            headers["content-type"] = "application/json"
        return headers

    async def _make_request_with_retries(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        json_data: Optional[Dict] = None,
    ) -> httpx.Response:
        """Make HTTP request with exponential backoff retry logic."""
        url = f"{self.base_url}{endpoint}"
        headers = self._get_headers(is_post=(method.upper() == "POST"))
        
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            try:
                logger.debug(
                    f"Making {method.upper()} request to {url} (attempt {attempt + 1}/{self.max_retries + 1})"
                )
                
                response = await self._client.request(
                    method, url, params=params, json=json_data, headers=headers
                )
                
                # Update network health on success
                self.network_health["consecutive_failures"] = 0
                self.network_health["last_success"] = time.time()
                self.network_health["is_available"] = True
                
                self._update_rate_limits(response)
                
                # Handle rate limit responses
                if response.status_code == 429:
                    retry_after = response.headers.get("retry-after")
                    if retry_after:
                        retry_delay = int(retry_after)
                    else:
                        # Default to exponential backoff if no retry-after header
                        retry_delay = min(self.base_delay * (2 ** attempt), self.max_delay)
                    
                    logger.warning(f"Rate limited by Neynar API. Retrying after {retry_delay} seconds.")
                    
                    if attempt < self.max_retries:
                        await asyncio.sleep(retry_delay)
                        continue
                    else:
                        raise NeynarRateLimitError(f"Rate limit exceeded after {self.max_retries} attempts")
                
                response.raise_for_status()
                return response
                
            except httpx.ConnectError as e:
                last_exception = e
                self.network_health["consecutive_failures"] += 1
                
                # DNS resolution failures, connection timeouts, etc.
                if "name resolution" in str(e).lower() or "dns" in str(e).lower():
                    error_msg = f"DNS resolution failed for {url}: {e}"
                    logger.warning(error_msg)
                else:
                    error_msg = f"Connection error for {url}: {e}"
                    logger.warning(error_msg)
                
                if attempt < self.max_retries:
                    delay = min(self.base_delay * (2 ** attempt), self.max_delay)
                    logger.debug(f"Retrying in {delay} seconds...")
                    await asyncio.sleep(delay)
                else:
                    self.network_health["is_available"] = False
                    raise NeynarNetworkError(f"Network error after {self.max_retries} attempts: {error_msg}")
            
            except httpx.TimeoutException as e:
                last_exception = e
                self.network_health["consecutive_failures"] += 1
                
                logger.warning(f"Timeout error for {method.upper()} {url}: {e}")
                
                if attempt < self.max_retries:
                    delay = min(self.base_delay * (2 ** attempt), self.max_delay)
                    logger.debug(f"Retrying in {delay} seconds...")
                    await asyncio.sleep(delay)
                else:
                    self.network_health["is_available"] = False
                    raise NeynarNetworkError(f"Timeout error after {self.max_retries} attempts: {e}")
            
            except httpx.HTTPStatusError as e:
                last_exception = e
                
                if e.response.status_code == 429:
                    # Rate limit - handled above
                    continue
                elif 500 <= e.response.status_code < 600:
                    # Server errors - retry
                    self.network_health["consecutive_failures"] += 1
                    logger.warning(f"Server error {e.response.status_code} for {method.upper()} {url}: {e.response.text}")
                    
                    if attempt < self.max_retries:
                        delay = min(self.base_delay * (2 ** attempt), self.max_delay)
                        logger.debug(f"Retrying server error in {delay} seconds...")
                        await asyncio.sleep(delay)
                    else:
                        raise NeynarAPIError(f"Server error after {self.max_retries} attempts: {e.response.status_code} - {e.response.text}")
                else:
                    # Client errors (4xx) - don't retry
                    logger.error(f"Client error {e.response.status_code} for {method.upper()} {url}: {e.response.text}")
                    raise NeynarAPIError(f"Client error: {e.response.status_code} - {e.response.text}")
            
            except httpx.RequestError as e:
                last_exception = e
                self.network_health["consecutive_failures"] += 1
                
                logger.warning(f"Request error for {method.upper()} {url}: {e}")
                
                if attempt < self.max_retries:
                    delay = min(self.base_delay * (2 ** attempt), self.max_delay)
                    logger.debug(f"Retrying request error in {delay} seconds...")
                    await asyncio.sleep(delay)
                else:
                    self.network_health["is_available"] = False
                    raise NeynarNetworkError(f"Request error after {self.max_retries} attempts: {e}")
        
        # This should not be reached, but just in case
        if last_exception:
            raise NeynarNetworkError(f"Failed after {self.max_retries} attempts: {last_exception}")

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        json_data: Optional[Dict] = None,
    ) -> httpx.Response:
        """Wrapper for backward compatibility - now uses retry logic."""
        return await self._make_request_with_retries(method, endpoint, params, json_data)

    def _update_rate_limits(self, response: httpx.Response):
        """
        Parse and store rate limit information from Neynar API response headers.
        Neynar typically provides rate limit headers like:
        - x-ratelimit-limit: The rate limit ceiling for that given request
        - x-ratelimit-remaining: The number of requests left for the time window
        - x-ratelimit-reset: The remaining window before the rate limit resets (timestamp or seconds)
        """
        try:
            # Standard rate limit headers (adjust based on Neynar's actual headers)
            limit_hdr = response.headers.get("x-ratelimit-limit")
            remaining_hdr = response.headers.get("x-ratelimit-remaining")
            reset_hdr = response.headers.get("x-ratelimit-reset") # This is often a Unix timestamp
            retry_after_hdr = response.headers.get("x-ratelimit-retry-after")

            # Alternative header names some APIs might use
            if not limit_hdr: limit_hdr = response.headers.get("ratelimit-limit")
            if not remaining_hdr: remaining_hdr = response.headers.get("ratelimit-remaining")
            if not reset_hdr: reset_hdr = response.headers.get("ratelimit-reset")
            if not retry_after_hdr: retry_after_hdr = response.headers.get("retry-after")

            updated = False
            if limit_hdr:
                self.rate_limit_info["limit"] = int(limit_hdr)
                updated = True
            if remaining_hdr:
                remaining = int(remaining_hdr)
                self.rate_limit_info["remaining"] = remaining
                updated = True
                
                # Warn when approaching rate limits
                if remaining < 10:
                    logger.warning(f"Farcaster API rate limit approaching: {remaining} requests remaining")
                elif remaining < 50:
                    logger.debug(f"Farcaster API rate limit status: {remaining} requests remaining")
                    
            if reset_hdr:
                try:
                    self.rate_limit_info["reset"] = int(reset_hdr) # Assume it's a Unix timestamp
                    updated = True
                except ValueError:
                    logger.warning(f"Could not parse rate limit reset header value: {reset_hdr}")
                    
            if retry_after_hdr:
                try:
                    self.rate_limit_info["retry_after"] = int(retry_after_hdr)
                    updated = True
                except ValueError:
                    logger.warning(f"Could not parse retry-after header value: {retry_after_hdr}")

            if updated:
                import time
                self.rate_limit_info["last_updated_client"] = time.time()
                logger.debug(f"NeynarAPIClient: Updated internal rate limits: {self.rate_limit_info}")

        except (ValueError, TypeError) as e:
            logger.debug(f"NeynarAPIClient: Could not parse rate limit headers: {e}")
        except Exception as e:
            logger.error(f"NeynarAPIClient: Unexpected error updating rate limits: {e}", exc_info=True)

    def is_network_available(self) -> bool:
        """Check if the Neynar API is currently available."""
        return self.network_health["is_available"]
    
    def get_network_status(self) -> Dict[str, Any]:
        """Get detailed network status information."""
        return {
            "is_available": self.network_health["is_available"],
            "consecutive_failures": self.network_health["consecutive_failures"],
            "last_success": self.network_health["last_success"],
            "seconds_since_last_success": time.time() - self.network_health["last_success"],
            "rate_limits": self.rate_limit_info.copy(),
        }
    
    async def health_check(self) -> bool:
        """Perform a lightweight health check of the API."""
        try:
            # Use a simple endpoint that doesn't require authentication
            response = await self._make_request_with_retries("GET", "/farcaster/channel/list", {"limit": 1})
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Health check failed: {e}")
            return False
    
    async def close(self):
        """Close the HTTP client connection."""
        await self._client.aclose()

    async def get_casts_by_fid(
        self, fid: int, limit: int = 25, include_replies: bool = True
    ) -> Dict[str, Any]:
        params = {"fid": fid, "limit": limit, "include_replies": include_replies}
        response = await self._make_request("GET", "/farcaster/feed/user/casts", params=params)
        return response.json()

    async def get_feed_by_channel_ids(
        self, channel_ids: str, limit: int = 25, include_replies: bool = True
    ) -> Dict[str, Any]:
        params = {
            "channel_ids": channel_ids,
            "limit": limit,
            "include_replies": include_replies,
        }
        response = await self._make_request(
            "GET", "/farcaster/feed/channels", params=params
        )
        return response.json()

    async def get_home_feed(
        self,
        fid: str,
        limit: int = 25,
        include_replies: bool = True,
        with_recasts: bool = True,
    ) -> Dict[str, Any]:
        params = {
            "fid": fid,
            "feed_type": "following",
            "limit": limit,
            "include_replies": include_replies,
            "with_recasts": with_recasts,
        }
        response = await self._make_request("GET", "/farcaster/feed", params=params)
        return response.json()

    async def get_notifications(self, fid: str, limit: int = 25) -> Dict[str, Any]:
        params = {"fid": fid, "limit": limit}
        response = await self._make_request(
            "GET", "/farcaster/notifications", params=params
        )
        return response.json()

    async def get_replies_and_recasts_for_user(
        self, fid: str, limit: int = 25, filter_type: str = "replies"
    ) -> Dict[str, Any]:
        params = {"fid": fid, "limit": limit, "filter_type": filter_type}
        response = await self._make_request(
            "GET", "/farcaster/feed/user/replies_and_recasts", params=params
        )
        return response.json()

    async def get_user_by_username(self, username: str) -> Dict[str, Any]:
        params = {"username": username}
        response = await self._make_request(
            "GET", "/farcaster/user/by-username", params=params
        )
        return response.json()

    async def get_user_by_fid(self, fid: int) -> Dict[str, Any]:
        """Get user information by FID (Farcaster ID)."""
        params = {"fid": fid}
        response = await self._make_request(
            "GET", "/farcaster/user", params=params
        )
        return response.json()

    async def publish_cast(
        self,
        text: str,
        signer_uuid: str,
        channel_id: Optional[str] = None,
        parent: Optional[str] = None,
        embeds: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        if not signer_uuid:
            raise ValueError("signer_uuid is required to publish a cast.")
        payload = {"text": text, "signer_uuid": signer_uuid}
        if channel_id:
            payload["channel_id"] = channel_id
        if parent:
            payload["parent"] = parent
        if embeds:
            payload["embeds"] = embeds

        response = await self._make_request(
            "POST", "/farcaster/cast", json_data=payload
        )
        return response.json()

    async def react_to_cast(
        self, signer_uuid: str, reaction_type: str, target_hash: str
    ) -> Dict[str, Any]:
        if not signer_uuid:
            raise ValueError("signer_uuid is required to react to a cast.")
        payload = {
            "signer_uuid": signer_uuid,
            "reaction_type": reaction_type,
            "target": target_hash,
        }
        response = await self._make_request(
            "POST", "/farcaster/reaction", json_data=payload
        )
        return response.json()

    async def manage_follow(
        self, signer_uuid: str, target_fid: int, unfollow: bool = False
    ) -> Dict[str, Any]:
        if not signer_uuid:
            raise ValueError("signer_uuid is required to follow/unfollow.")
        payload_single_fid = {"signer_uuid": signer_uuid, "fid": target_fid}
        endpoint_original = (
            "/farcaster/user/follow" if not unfollow else "/farcaster/user/unfollow"
        )
        response = await self._make_request(
            "POST", endpoint_original, json_data=payload_single_fid
        )
        return response.json()

    async def search_casts_by_query(
        self, query: str, limit: int = 25, channel_id: Optional[str] = None
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {"q": query.strip(), "limit": min(limit, 25)}
        if channel_id:
            normalized_channel = channel_id.lstrip("/")
            if normalized_channel.startswith("channel/"):
                params["channel_id"] = normalized_channel
            else:
                params["channel_id"] = f"channel/{normalized_channel}"

        response = None
        try:
            response = await self._make_request(
                "GET", "/farcaster/cast/search", params=params
            )
            return response.json()
        except Exception as e:
            logger.error(f"Error in search_casts_by_query with params {params}: {e}", exc_info=True)
            if response is not None:
                try:
                    logger.error(f"Response status: {getattr(response, 'status_code', 'unknown')}")
                    logger.error(f"Response text: {getattr(response, 'text', 'unknown')}")
                except:
                    pass
            return {"casts": [], "error": str(e)}

    async def get_trending_casts_feed(
        self,
        limit: int = 25,
        channel_id: Optional[str] = None,
        timeframe_hours: int = 24,
        provider: str = "neynar",
        with_recasts: bool = True,
        with_likes: bool = True,
    ) -> Dict[str, Any]:
        # Convert timeframe_hours to time_window parameter
        if timeframe_hours <= 1:
            time_window = "1h"
        elif timeframe_hours <= 6:
            time_window = "6h"  
        elif timeframe_hours <= 24:
            time_window = "24h"
        elif timeframe_hours <= 168:  # 7 days
            time_window = "7d"
        else:
            time_window = "7d"  # Default to max available
            
        params = {
            "limit": min(limit, 25),  # API has a max limit
            "time_window": time_window,
            "provider": provider,
            "with_likes": with_likes,
            "with_recasts": with_recasts,
        }
        
        if channel_id:
            params["channel_id"] = channel_id
            
        response = await self._make_request("GET", "/farcaster/feed/trending", params=params)
        return response.json()

    async def get_cast_by_hash(self, cast_hash: str) -> Dict[str, Any]:
        params = {"type": "hash", "identifier": cast_hash.strip()}
        response = await self._make_request("GET", "/farcaster/cast", params=params)
        return response.json()

    async def reply_to_cast(
        self, text: str, parent_hash: str, signer_uuid: Optional[str] = None
    ) -> Dict[str, Any]:
        """Reply to a cast by setting it as parent."""
        uuid = signer_uuid or self.signer_uuid
        if not uuid:
            raise ValueError("signer_uuid is required to reply to a cast.")
        return await self.publish_cast(text, uuid, parent=parent_hash)

    async def follow_user(
        self, target_fid: int, signer_uuid: Optional[str] = None
    ) -> Dict[str, Any]:
        """Follow a user."""
        uuid = signer_uuid or self.signer_uuid
        return await self.manage_follow(uuid, target_fid, unfollow=False)

    async def unfollow_user(
        self, target_fid: int, signer_uuid: Optional[str] = None
    ) -> Dict[str, Any]:
        """Unfollow a user."""
        uuid = signer_uuid or self.signer_uuid
        return await self.manage_follow(uuid, target_fid, unfollow=True)

    async def send_dm(
        self, recipient_fid: int, text: str, signer_uuid: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send a direct message - DEPRECATED: Farcaster DM API not supported."""
        raise NotImplementedError("Farcaster DM functionality is not supported by the API")

    async def delete_cast(
        self, cast_hash: str, signer_uuid: Optional[str] = None
    ) -> Dict[str, Any]:
        """Delete a cast by hash."""
        uuid = signer_uuid or self.signer_uuid
        if not uuid:
            raise ValueError("signer_uuid is required to delete a cast.")
        
        payload = {
            "signer_uuid": uuid,
            "target_hash": cast_hash
        }
        
        response = await self._make_request(
            "DELETE", "/farcaster/cast", json_data=payload
        )
        return response.json()

    async def delete_reaction(
        self, cast_hash: str, signer_uuid: Optional[str] = None
    ) -> Dict[str, Any]:
        """Delete a reaction (like/recast) from a cast."""
        uuid = signer_uuid or self.signer_uuid
        if not uuid:
            raise ValueError("signer_uuid is required to delete a reaction.")
        
        payload = {
            "signer_uuid": uuid,
            "target_hash": cast_hash
        }
        
        response = await self._make_request(
            "DELETE", "/farcaster/reaction", json_data=payload
        )
        return response.json()

    async def quote_cast(
        self,
        content: str,
        quoted_cast_hash: str,
        quoted_cast_author_fid: int,
        channel: Optional[str] = None,
        embed_urls: Optional[List[str]] = None,
        signer_uuid: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Quote a cast by including it as an embed."""
        uuid = signer_uuid or self.signer_uuid
        if not uuid:
            raise ValueError("signer_uuid is required to quote a cast.")

        # Create embeds with the quoted cast using the protocol-correct cast_id object
        embeds = [{"cast_id": {"hash": quoted_cast_hash, "fid": quoted_cast_author_fid}}]
        if embed_urls:
            embeds.extend([{"url": url} for url in embed_urls])

        result = await self.publish_cast(content, uuid, channel, embeds=embeds)
        # Add quoted_cast info to result for test compatibility
        if result:
            result["quoted_cast"] = quoted_cast_hash
        return result

    async def search_casts(
        self, query: str, channel_id: Optional[str] = None, limit: int = 25
    ) -> Dict[str, Any]:
        """Search for casts matching a query."""
        return await self.search_casts_by_query(query, limit, channel_id)

    async def get_trending_casts(
        self,
        channel_id: Optional[str] = None,
        timeframe_hours: int = 24,
        limit: int = 25,
    ) -> Dict[str, Any]:
        """Get trending casts, optionally within a specific channel and timeframe."""
        return await self.get_trending_casts_feed(
            limit=limit, 
            channel_id=channel_id, 
            timeframe_hours=timeframe_hours
        )

    async def get_conversation_messages(
        self, fid: str, conversation_with_fid: str, limit: int = 25
    ) -> Dict[str, Any]:
        """Get conversation messages between two users - DEPRECATED: DM functionality not supported."""
        raise NotImplementedError("Farcaster DM conversation functionality is not supported by the API")

    async def get_token_holders(
        self, token_contract_address: str, limit: int = 100
    ) -> Dict[str, Any]:
        """
        Fetches a list of FIDs holding a specific token.
        
        Note: This is a workaround implementation since direct token holder endpoints may not be available.
        In practice, you might need to:
        1. Get users from a token-gated channel
        2. Or use external indexers (like Alchemy, Moralis) to get holder addresses
        3. Then resolve those addresses to FIDs using Neynar's address-to-FID endpoints
        
        For now, this returns a placeholder response indicating the limitation.
        """
        logger.warning(f"get_token_holders: Direct token holder fetching for {token_contract_address} "
                      "may require a combination of external token indexers and address-to-FID resolution. "
                      "Consider implementing via: 1) External token APIs (Alchemy/Moralis) + "
                      "2) Neynar's address-to-FID endpoints + 3) User balance verification.")
        
        # Return structured placeholder data for simulation
        return {
            "holders": [],
            "total_count": 0,
            "contract_address": token_contract_address,
            "note": "Implementation requires external token indexer + address-to-FID resolution",
            "suggested_approach": [
                "Use external API (Alchemy/Moralis) to get token holder addresses",
                "Use Neynar's /farcaster/user/bulk-by-address to resolve addresses to FIDs",
                "Verify balances using /farcaster/user/token-balance if needed"
            ]
        }

    async def get_user_token_balance(
        self, fid: int, token_contract_address: str
    ) -> Dict[str, Any]:
        """
        Fetches a user's balance for a specific token.
        Based on the pattern from Neynar docs: https://docs.neynar.com/reference/fetch-user-balance
        """
        params = {"fid": fid}
        try:
            # Try the documented endpoint pattern
            response = await self._make_request("GET", "/farcaster/user/balance", params=params)
            balance_data = response.json()
            
            # Filter for the specific token if multiple tokens are returned
            if "balances" in balance_data:
                for balance in balance_data["balances"]:
                    if balance.get("contract_address", "").lower() == token_contract_address.lower():
                        return {"balance": balance, "fid": fid}
            
            return {"balance": None, "fid": fid, "error": "Token not found in user's balance"}
        except Exception as e:
            logger.warning(f"get_user_token_balance failed for FID {fid}: {e}")
            return {"balance": None, "fid": fid, "error": str(e)}

    async def get_user_details_for_fids(self, fids: List[int]) -> Dict[str, Any]:
        """
        Fetches user details for a list of FIDs.
        Corresponds to: https://docs.neynar.com/reference/fetch-bulk-users
        """
        if not fids:
            return {"users": []}
        fids_str = ",".join(map(str, fids))
        params = {"fids": fids_str}
        response = await self._make_request("GET", "/farcaster/user/bulk", params=params)
        return response.json()

    async def get_relevant_fungible_owners(
        self,
        contract_address: str,
        network: str,  # 'ethereum', 'optimism', 'base', 'arbitrum', 'solana'
        viewer_fid: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch a list of relevant owners for a specific fungible asset.
        API Docs: https://docs.neynar.com/reference/fetch-relevant-owners-for-a-fungible-asset
        
        Args:
            contract_address: The contract address of the fungible token
            network: Network of the fungible asset ('ethereum', 'optimism', 'base', 'arbitrum', 'solana')
            viewer_fid: Optional FID to personalize results based on social graph
            
        Returns:
            Dictionary containing relevant owners data or None if error/no data
            Response includes:
            - top_relevant_fungible_owners_hydrated: Array of User objects with full profile data
            - all_relevant_fungible_owners_dehydrated: Array of User objects with minimal data
        """
        # Input validation
        if not contract_address or not contract_address.strip():
            raise ValueError("contract_address is required and cannot be empty")
        
        valid_networks = ['ethereum', 'optimism', 'base', 'arbitrum', 'solana']
        if network not in valid_networks:
            raise ValueError(f"network must be one of {valid_networks}, got: {network}")
        
        if viewer_fid is not None and viewer_fid <= 0:
            raise ValueError("viewer_fid must be a positive integer if provided")
        
        endpoint = "/farcaster/fungible/owner/relevant"
        params = {
            "contract_address": contract_address.strip(),
            "network": network,
        }
        if viewer_fid:
            params["viewer_fid"] = viewer_fid

        try:
            response = await self._make_request("GET", endpoint, params=params)
            response_data = response.json()
            
            # Validate expected response structure
            if response_data and (
                "top_relevant_fungible_owners_hydrated" in response_data or 
                "all_relevant_fungible_owners_dehydrated" in response_data
            ):
                logger.debug(
                    f"Successfully fetched relevant fungible owners for {contract_address} "
                    f"on {network}. Hydrated: {len(response_data.get('top_relevant_fungible_owners_hydrated', []))}, "
                    f"Dehydrated: {len(response_data.get('all_relevant_fungible_owners_dehydrated', []))}"
                )
                return response_data
            
            logger.warning(
                f"Relevant fungible owners response missing expected keys for {contract_address} "
                f"on {network}. Response keys: {list(response_data.keys()) if response_data else 'None'}"
            )
            return None
            
        except Exception as e:
            logger.error(
                f"Error fetching relevant fungible owners for {contract_address} "
                f"on {network}: {e}"
            )
            return None

    async def get_relevant_token_owners(
        self,
        contract_address: str,
        network: str,
        viewer_fid: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Alias for get_relevant_fungible_owners for backward compatibility.
        
        Args:
            contract_address: The contract address of the fungible token
            network: Network of the fungible asset ('ethereum', 'optimism', 'base', 'arbitrum', 'solana')
            viewer_fid: Optional FID to personalize results based on social graph
            
        Returns:
            Dictionary containing relevant owners data or None if error/no data
        """
        return await self.get_relevant_fungible_owners(contract_address, network, viewer_fid)

    async def close(self):
        await self._client.aclose()

    async def get_cast_details(self, cast_hash: str) -> Dict[str, Any]:
        """
        Get detailed information about a specific cast by its hash.
        
        Args:
            cast_hash: The hash identifier of the cast
            
        Returns:
            Dictionary containing cast details including author information
        """
        try:
            params = {"type": "hash", "identifier": cast_hash}
            response = await self._make_request("GET", "/farcaster/cast", params=params)
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching cast details for {cast_hash}: {e}")
            return {"error": str(e)}

    async def get_for_you_feed(
        self,
        fid: str,
        limit: int = 25,
        include_replies: bool = True,
        with_recasts: bool = True,
    ) -> Dict[str, Any]:
        """Get personalized 'For You' feed for a user based on their activity and preferences."""
        params = {
            "fid": fid,
            "feed_type": "filter",
            "filter_type": "global_trending",
            "limit": limit,
            "include_replies": include_replies,
            "with_recasts": with_recasts,
        }
        response = await self._make_request("GET", "/farcaster/feed", params=params)
        return response.json()

    async def lookup_cast_conversation(self, cast_hash: str) -> Dict[str, Any]:
        """
        Gets all casts in a conversation surrounding a given cast.
        This is used for authoritative duplicate detection - to check if the bot
        has already replied to a cast by examining the actual thread on Farcaster.
        
        API Docs: https://docs.neynar.com/reference/lookup-cast-conversation
        
        Args:
            cast_hash: The hash of the cast to get the conversation for
            
        Returns:
            Dictionary containing the conversation thread with all replies
        """
        params = {
            "type": "hash", 
            "identifier": cast_hash.strip(),
            "reply_depth": 5,  # Fetch reasonable depth to check for bot replies
            "include_chronological_parent_casts": False  # We only need the replies
        }
        response = await self._make_request("GET", "/farcaster/cast/conversation", params=params)
        return response.json()
