#!/usr/bin/env python3
"""
Farcaster Data Converter

Utilities for converting Farcaster API data into standardized Message objects
and other parsing tasks.
"""
import asyncio
import logging
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

from ...core.world_state import Message

logger = logging.getLogger(__name__)


def parse_farcaster_timestamp(timestamp_str: str) -> float:
    if not timestamp_str:
        return time.time()
    try:
        dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        return dt.timestamp()
    except ValueError:
        logger.warning(
            f"Could not parse timestamp: {timestamp_str}. Using current time."
        )
        return time.time()
    except Exception as e:
        logger.error(f"Unexpected error parsing timestamp '{timestamp_str}': {e}")
        return time.time()


def extract_cast_hash_from_url(url: str) -> Optional[str]:
    if not url:
        return None
    patterns = [
        r"/0x([a-fA-F0-9]{40,})",
        r"/conversations/0x([a-fA-F0-9]{40,})",
        r"cast/0x([a-fA-F0-9]{40,})",
        r"hash=0x([a-fA-F0-9]{40,})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            hash_part = match.group(1)
            if not hash_part.startswith("0x"):
                hash_part = "0x" + hash_part
            if re.fullmatch(r"0x[a-fA-F0-9]+", hash_part):
                logger.debug(f"Extracted cast hash {hash_part} from URL {url}")
                return hash_part
            else:
                logger.warning(
                    f"Pattern '{pattern}' matched but '{match.group(1)}' is not a valid hash part from URL: {url}"
                )
    logger.warning(f"Could not extract cast hash from URL: {url} using known patterns.")
    return None


async def _create_message_from_cast_data(
    cast_data: Dict[str, Any],
    channel_id_prefix: str,
    cast_type_metadata: str = "unknown",
    bot_fid: Optional[str] = None,
    current_time_for_filtering: Optional[float] = None,
    last_seen_hashes: Optional[set] = None,
    custom_metadata: Optional[Dict[str, Any]] = None,
) -> Optional[Message]:
    try:
        cast_hash = cast_data.get("hash", "")
        if not cast_hash:
            logger.debug("Skipping cast data without hash.")
            return None
        if last_seen_hashes is not None and cast_hash in last_seen_hashes:
            logger.debug(f"Skipping already seen cast: {cast_hash}")
            return None
        author = cast_data.get("author", {})
        author_fid_str = str(author.get("fid"))
        if bot_fid and author_fid_str == str(bot_fid):
            logger.debug(f"Skipping cast from self (bot_fid={bot_fid}): {cast_hash}")
            return None
        cast_timestamp_str = cast_data.get("timestamp", "")
        cast_timestamp = parse_farcaster_timestamp(cast_timestamp_str)
        if (
            current_time_for_filtering is not None
            and cast_timestamp <= current_time_for_filtering
        ):
            logger.debug(
                f"Skipping old cast {cast_hash} (timestamp {cast_timestamp} <= {current_time_for_filtering})"
            )
            return None
        content = cast_data.get("text", "")
        if not content.strip():
            logger.debug(f"Skipping cast with empty content: {cast_hash}")
            return None
        username = author.get("username", "unknown_user")
        display_name = author.get("display_name", username)
        reply_to_hash = cast_data.get("parent_hash")
        parent_url = cast_data.get("parent_url")
        derived_channel_id = channel_id_prefix
        if parent_url and parent_url.startswith("farcaster://casts/channel/"):
            derived_channel_id = parent_url.replace("farcaster://casts/channel/", "")
        elif parent_url:
            derived_channel_id = (
                f"{channel_id_prefix}:{parent_url.split('/')[-1]}"
                if "/" in parent_url
                else f"{channel_id_prefix}:unknown_context"
            )
        metadata_dict = {
            "cast_type": cast_type_metadata,
            "verified_addresses": author.get("verified_addresses", {}),
            "power_badge": author.get("power_badge", False),
            "channel": derived_channel_id,
            "raw_parent_url": parent_url,
            "reactions": cast_data.get("reactions", {}),
            "replies_count": cast_data.get("replies", {}).get("count", 0),
            "embeds": cast_data.get("embeds", []),
        }
        if custom_metadata:
            metadata_dict.update(custom_metadata)

        # Extract image URLs from embeds and text content
        image_urls_list = []

        # From Embeds: Iterate through embeds
        embeds = cast_data.get("embeds", [])
        for embed in embeds:
            if isinstance(embed, dict) and "url" in embed:
                embed_url = embed["url"]
                # Basic check for common image extensions or common image hosting domains
                if embed_url.lower().endswith(
                    (".png", ".jpg", ".jpeg", ".gif", ".webp")
                ) or any(
                    domain in embed_url.lower()
                    for domain in [
                        "i.imgur.com",
                        "pbs.twimg.com/media",
                        "imagedelivery.net",
                    ]
                ):  # Add more as needed
                    image_urls_list.append(embed_url)
                    logger.debug(
                        f"FarcasterConverter: Detected image URL in embed: {embed_url}"
                    )

        # From Text: Use regex to find common image URLs in text content
        url_pattern = re.compile(r"https?://\S+\.(?:png|jpe?g|gif|webp)", re.IGNORECASE)
        found_in_text = url_pattern.findall(content)
        for img_url in found_in_text:
            if img_url not in image_urls_list:  # Avoid duplicates from embeds
                image_urls_list.append(img_url)
                logger.debug(
                    f"FarcasterConverter: Detected image URL in text: {img_url}"
                )

        # Extract and validate all URLs from text content
        validated_urls_list = []
        extracted_urls = extract_urls_from_text(content)
        if extracted_urls:
            logger.debug(f"FarcasterConverter: Found {len(extracted_urls)} URLs to validate")
            # Validate URLs asynchronously  
            validation_tasks = [validate_url(url) for url in extracted_urls]
            try:
                validation_results = await asyncio.gather(*validation_tasks, return_exceptions=True)
                for result in validation_results:
                    if isinstance(result, dict):
                        validated_urls_list.append(result)
                        logger.debug(f"FarcasterConverter: URL {result['url']} status: {result['status']}")
                    else:
                        logger.warning(f"FarcasterConverter: URL validation exception: {result}")
            except Exception as e:
                logger.error(f"FarcasterConverter: Error during URL validation: {e}")

        message = Message(
            id=cast_hash,
            channel_id=derived_channel_id,
            channel_type="farcaster",
            sender=username,
            content=content,
            timestamp=cast_timestamp,
            reply_to=reply_to_hash,
            sender_username=username,
            sender_display_name=display_name,
            sender_fid=author.get("fid"),
            sender_pfp_url=author.get("pfp_url"),
            sender_bio=author.get("profile", {}).get("bio", {}).get("text"),
            sender_follower_count=author.get("follower_count"),
            sender_following_count=author.get("following_count"),
            image_urls=image_urls_list if image_urls_list else None,
            validated_urls=validated_urls_list if validated_urls_list else None,
            metadata=metadata_dict,
        )
        if last_seen_hashes is not None:
            last_seen_hashes.add(cast_hash)
        return message
    except Exception as e:
        logger.error(
            f"Error converting cast to message (hash: {cast_data.get('hash', 'N/A')}): {e}",
            exc_info=True,
        )
        return None


async def convert_api_casts_to_messages(
    api_casts: List[Dict[str, Any]],
    channel_id_prefix: str,
    cast_type_metadata: str,
    bot_fid: Optional[str] = None,
    last_check_time_for_filtering: Optional[float] = None,
    last_seen_hashes: Optional[set] = None,
    custom_metadata_per_cast: Optional[Dict[str, Any]] = None,
) -> List[Message]:
    messages: List[Message] = []
    if not api_casts:
        return messages
    for cast_data in api_casts:
        message = await _create_message_from_cast_data(
            cast_data=cast_data,
            channel_id_prefix=channel_id_prefix,
            cast_type_metadata=cast_type_metadata,
            bot_fid=bot_fid,
            current_time_for_filtering=last_check_time_for_filtering,
            last_seen_hashes=last_seen_hashes,
            custom_metadata=custom_metadata_per_cast,
        )
        if message:
            messages.append(message)
    return messages


async def convert_api_notifications_to_messages(
    api_notifications: List[Dict[str, Any]],
    bot_fid: Optional[str] = None,
    last_check_time_for_filtering: Optional[float] = None,
    last_seen_hashes: Optional[set] = None,
) -> List[Message]:
    messages: List[Message] = []
    if not api_notifications:
        return messages
    for notification_data in api_notifications:
        try:
            cast_data = notification_data.get("cast")
            if not cast_data:
                logger.debug(
                    f"Skipping notification without cast data: {notification_data.get('id')}"
                )
                continue
            notification_type = notification_data.get("type", "unknown_notification")
            message = await _create_message_from_cast_data(
                cast_data=cast_data,
                channel_id_prefix=f"farcaster:notifications:{notification_type}",
                cast_type_metadata=f"notification_{notification_type}",
                bot_fid=bot_fid,
                current_time_for_filtering=last_check_time_for_filtering,
                last_seen_hashes=last_seen_hashes,
                custom_metadata={"notification_type_detail": notification_type},
            )
            if message:
                messages.append(message)
        except Exception as e:
            logger.error(
                f"Error converting notification to message (id: {notification_data.get('id')}): {e}",
                exc_info=True,
            )
            continue
    return messages


async def convert_single_api_cast_to_message(
    api_cast_data: Dict[str, Any],
    channel_id_if_unknown: str = "farcaster:direct",
    cast_type_metadata: str = "direct_access",
    custom_metadata: Optional[Dict[str, Any]] = None,
) -> Optional[Message]:
    if not api_cast_data:
        return None
    return await _create_message_from_cast_data(
        cast_data=api_cast_data,
        channel_id_prefix=channel_id_if_unknown,
        cast_type_metadata=cast_type_metadata,
        custom_metadata=custom_metadata,
    )


async def validate_url(url: str) -> Dict[str, Any]:
    """
    Validate a URL by making an HTTP request and checking its status.

    Args:
        url: The URL to validate

    Returns:
        Dictionary with validation results:
        - url: original URL
        - status: 'valid', 'invalid', 'error_timeout', 'error_dns', 'error_other'
        - http_status_code: HTTP status code if request succeeded
        - content_type: Content-Type header if available
        - error_message: Error description if validation failed
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.head(url, follow_redirects=True)

            status = "valid" if 200 <= response.status_code < 400 else "invalid"
            content_type = response.headers.get("content-type", "").split(";")[0].strip()

            return {
                "url": url,
                "status": status,
                "http_status_code": response.status_code,
                "content_type": content_type or None,
                "error_message": None,
            }

    except httpx.TimeoutException:
        return {
            "url": url,
            "status": "error_timeout",
            "http_status_code": None,
            "content_type": None,
            "error_message": "Request timed out",
        }
    except httpx.ConnectError:
        return {
            "url": url,
            "status": "error_dns",
            "http_status_code": None,
            "content_type": None,
            "error_message": "DNS resolution or connection failed",
        }
    except Exception as e:
        return {
            "url": url,
            "status": "error_other",
            "http_status_code": None,
            "content_type": None,
            "error_message": str(e),
        }


def extract_urls_from_text(text: str) -> List[str]:
    """Extract all URLs from text content."""
    url_pattern = re.compile(
        r"https?://(?:[-\w.])+(?:[:\d]+)?(?:/(?:[\w/_.])*(?:\?(?:[\w&=%.])*)?(?:#(?:[\w.])*)?)?",
        re.IGNORECASE,
    )
    return url_pattern.findall(text)
