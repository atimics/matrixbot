#!/usr/bin/env python3
"""
Neynar API Client for Farcaster

This module provides a client for interacting with the Neynar Farcaster API.
"""
import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


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
    ):
        if not api_key:
            raise ValueError("API key is required for NeynarAPIClient.")
        self.api_key = api_key
        self.signer_uuid = signer_uuid
        self.bot_fid = bot_fid
        self.base_url = base_url or self.DEFAULT_BASE_URL
        self._client = httpx.AsyncClient(timeout=30.0)

    def _get_headers(self, is_post: bool = False) -> Dict[str, str]:
        headers = {
            "accept": "application/json",
            "api_key": self.api_key,
        }
        if is_post:
            headers["content-type"] = "application/json"
        return headers

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        json_data: Optional[Dict] = None,
    ) -> httpx.Response:
        url = f"{self.base_url}{endpoint}"
        headers = self._get_headers(is_post=(method.upper() == "POST"))
        logger.debug(
            f"Making {method.upper()} request to {url} with params={params} json={json_data}"
        )
        try:
            response = await self._client.request(
                method, url, params=params, json=json_data, headers=headers
            )
            self._update_rate_limits(response)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error for {method.upper()} {url}: {e.response.status_code} - {e.response.text}"
            )
            raise
        except httpx.RequestError as e:
            logger.error(f"Request error for {method.upper()} {url}: {e}")
            raise

    def _update_rate_limits(self, response: httpx.Response):
        """
        Parse and store rate limit information from Neynar API response headers.
        Neynar typically provides rate limit headers like:
        - x-ratelimit-limit: The rate limit ceiling for that given request
        - x-ratelimit-remaining: The number of requests left for the time window  
        - x-ratelimit-reset: The remaining window before the rate limit resets
        """
        try:
            # Standard rate limit headers (adjust based on Neynar's actual headers)
            limit = response.headers.get("x-ratelimit-limit")
            remaining = response.headers.get("x-ratelimit-remaining") 
            reset = response.headers.get("x-ratelimit-reset")
            
            # Alternative header names Neynar might use
            if not limit:
                limit = response.headers.get("ratelimit-limit")
            if not remaining:
                remaining = response.headers.get("ratelimit-remaining")
            if not reset:
                reset = response.headers.get("ratelimit-reset")
                
            if limit:
                self.rate_limit_info["limit"] = int(limit)
            if remaining:
                self.rate_limit_info["remaining"] = int(remaining)
            if reset:
                # Reset time could be timestamp or seconds from now
                try:
                    self.rate_limit_info["reset"] = int(reset)
                except ValueError:
                    pass
                    
            # Log rate limit info for monitoring
            if any([limit, remaining, reset]):
                logger.debug(f"Rate limit: {remaining}/{limit}, resets: {reset}")
                
                # Warn when approaching limits
                if remaining and int(remaining) < 10:
                    logger.warning(f"Approaching Neynar rate limit: {remaining} requests remaining")
                    
        except (ValueError, TypeError) as e:
            logger.debug(f"Could not parse rate limit headers: {e}")
            pass

    async def get_casts_by_fid(
        self, fid: int, limit: int = 25, include_replies: bool = True
    ) -> Dict[str, Any]:
        params = {"fid": fid, "limit": limit, "include_replies": include_replies}
        response = await self._make_request("GET", "/farcaster/casts", params=params)
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
            "/farcaster/follow" if not unfollow else "/farcaster/unfollow"
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

        response = await self._make_request(
            "GET", "/farcaster/cast/search", params=params
        )
        return response.json()

    async def get_trending_casts_feed(
        self,
        limit: int = 25,
        channel_id: Optional[str] = None,
        feed_type: str = "filter",
        filter_type: str = "global_trending",
        with_recasts: bool = True,
        with_likes: bool = True,
    ) -> Dict[str, Any]:
        if channel_id:
            normalized_channel = channel_id.lstrip("/")
            if not normalized_channel.startswith("channel/"):
                normalized_channel = f"channel/{normalized_channel}"
            params = {
                "channel_ids": normalized_channel,
                "limit": min(limit * 2, 50),
                "with_likes": with_likes,
                "with_recasts": with_recasts,
            }
            response = await self._make_request(
                "GET", "/farcaster/feed/channels", params=params
            )
        else:
            params = {
                "feed_type": feed_type,
                "filter_type": filter_type,
                "limit": min(limit * 2, 50),
                "with_likes": with_likes,
                "with_recasts": with_recasts,
            }
            response = await self._make_request("GET", "/farcaster/feed", params=params)
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

    async def quote_cast(
        self,
        content: str,
        quoted_cast_hash: str,
        channel: Optional[str] = None,
        embed_urls: Optional[List[str]] = None,
        signer_uuid: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Quote a cast by including it as an embed."""
        uuid = signer_uuid or self.signer_uuid
        if not uuid:
            raise ValueError("signer_uuid is required to quote a cast.")

        # Create embeds with the quoted cast and any additional URLs
        embeds = [{"cast_id": {"hash": quoted_cast_hash}}]
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
        return await self.get_trending_casts_feed(limit, channel_id)

    async def get_conversation_messages(
        self, fid: str, conversation_with_fid: str, limit: int = 25
    ) -> Dict[str, Any]:
        """Get conversation messages between two users - DEPRECATED: DM functionality not supported."""
        raise NotImplementedError("Farcaster DM conversation functionality is not supported by the API")

    async def close(self):
        await self._client.aclose()
