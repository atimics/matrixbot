#!/usr/bin/env python3
"""
Farcaster Action Scheduler

Manages queuing and scheduled sending of Farcaster posts and replies.
"""
import asyncio
import logging
import time
from typing import Any, Dict, Optional

from .neynar_api_client import NeynarAPIClient

logger = logging.getLogger(__name__)

class FarcasterScheduler:
    """
    Schedules and sends Farcaster posts and replies at controlled intervals.
    """
    DEFAULT_SCHEDULER_INTERVAL = 60.0  # seconds

    def __init__(
        self,
        api_client: NeynarAPIClient,
        world_state_manager: Any,
        scheduler_interval: Optional[float] = None,
    ):
        self.api_client = api_client
        self.world_state_manager = world_state_manager
        self.post_queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        self.reply_queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        self.scheduler_interval: float = scheduler_interval or self.DEFAULT_SCHEDULER_INTERVAL
        self._post_task: Optional[asyncio.Task] = None
        self._reply_task: Optional[asyncio.Task] = None
        self.replied_to_hashes: set[str] = set()
        logger.info("FarcasterScheduler initialized.")

    async def start(self):
        if self._post_task is None or self._post_task.done():
            self._post_task = asyncio.create_task(self._send_posts_loop())
            logger.info("Post scheduler task started.")
        if self._reply_task is None or self._reply_task.done():
            self._reply_task = asyncio.create_task(self._send_replies_loop())
            logger.info("Reply scheduler task started.")

    async def stop(self):
        if self._post_task and not self._post_task.done():
            self._post_task.cancel()
            try:
                await self._post_task
            except asyncio.CancelledError:
                logger.info("Post scheduler task cancelled successfully.")
            except Exception as e:
                logger.error(f"Error during post task cancellation: {e}")
        if self._reply_task and not self._reply_task.done():
            self._reply_task.cancel()
            try:
                await self._reply_task
            except asyncio.CancelledError:
                logger.info("Reply scheduler task cancelled successfully.")
            except Exception as e:
                logger.error(f"Error during reply task cancellation: {e}")
        logger.info("FarcasterScheduler stopped.")

    def schedule_post(self, content: str, channel: Optional[str] = None, action_id: Optional[str] = None) -> bool:
        logger.info(f"Attempting to schedule post: action_id={action_id}, content='{content[:50]}...', channel={channel}")
        if self._is_duplicate_in_queue(self.post_queue, {"content": content, "channel": channel}):
            logger.debug("Duplicate content for the same channel in post queue, skipping schedule.")
            return False
        post_data = {
            "content": content,
            "channel": channel,
            "action_id": action_id,
            "scheduled_at": time.time()
        }
        self.post_queue.put_nowait(post_data)
        logger.info(f"Post added to queue. New queue size: {self.post_queue.qsize()}")
        return True

    def schedule_reply(self, content: str, reply_to_hash: str, action_id: Optional[str] = None) -> bool:
        logger.info(f"Attempting to schedule reply: action_id={action_id}, reply_to_hash={reply_to_hash}, content='{content[:50]}...'")
        if reply_to_hash in self.replied_to_hashes:
            logger.warning(f"Already replied or scheduled reply to cast {reply_to_hash}, skipping.")
            return False
        for queued_item in list(self.reply_queue._queue): # type: ignore
            if queued_item.get("reply_to_hash") == reply_to_hash:
                logger.warning(f"Duplicate reply (for hash {reply_to_hash}) in reply queue, skipping schedule.")
                return False
        reply_data = {
            "content": content,
            "reply_to_hash": reply_to_hash,
            "action_id": action_id,
            "scheduled_at": time.time()
        }
        self.reply_queue.put_nowait(reply_data)
        self.replied_to_hashes.add(reply_to_hash)
        logger.info(f"Reply added to queue. New queue size: {self.reply_queue.qsize()}")
        return True
    
    def add_to_replied_hashes(self, cast_hash: str):
        self.replied_to_hashes.add(cast_hash)
        logger.info(f"Manually added {cast_hash} to replied_to_hashes set.")

    async def _send_posts_loop(self) -> None:
        logger.info("Starting Farcaster posts scheduler loop.")
        while True:
            try:
                logger.debug(f"Post scheduler loop: waiting for item. Queue size: {self.post_queue.qsize()}")
                post_data = await self.post_queue.get()
                content = post_data["content"]
                channel_id = post_data["channel"]
                action_id = post_data.get("action_id")
                logger.info(f"Dequeued scheduled post for channel {channel_id or 'default'}: {content[:70]}...")
                cast_result_data: Optional[Dict[str, Any]] = None
                error_message: Optional[str] = None
                try:
                    if not self.api_client.signer_uuid:
                        raise ValueError("Signer UUID not configured in API client, cannot post.")
                    api_response = await self.api_client.publish_cast(
                        text=content,
                        signer_uuid=self.api_client.signer_uuid,
                        channel_id=channel_id
                    )
                    if "cast" in api_response and "hash" in api_response["cast"]:
                        cast_result_data = api_response["cast"]
                        logger.info(f"Successfully sent scheduled post. Cast hash: {cast_result_data.get('hash')}")
                    else:
                        error_message = api_response.get('message', f"Unknown error from API: {str(api_response)[:200]}")
                        logger.error(f"Failed to send scheduled post: {error_message}")
                except Exception as e:
                    error_message = str(e)
                    logger.error(f"Error sending scheduled post: {e}", exc_info=True)
                if self.world_state_manager:
                    params_for_wsm = {"content": content, "channel": channel_id}
                    if cast_result_data and cast_result_data.get("hash"):
                        cast_hash = cast_result_data["hash"]
                        params_for_wsm["cast_hash"] = cast_hash
                        if action_id:
                            self.world_state_manager.update_action_result(action_id, "success", cast_hash)
                        else:
                            self.world_state_manager.add_action_result("send_farcaster_post", params_for_wsm, "success")
                    else:
                        result_status = f"failure: {error_message or 'unknown error'}"
                        if action_id:
                            self.world_state_manager.update_action_result(action_id, result_status)
                        else:
                            self.world_state_manager.add_action_result("send_farcaster_post", params_for_wsm, result_status)
                self.post_queue.task_done()
                await asyncio.sleep(self.scheduler_interval)
            except asyncio.CancelledError:
                logger.info("Post scheduler loop cancelled.")
                break
            except Exception as e:
                logger.error(f"Unexpected error in post scheduler loop: {e}", exc_info=True)
                await asyncio.sleep(5)

    async def _send_replies_loop(self) -> None:
        logger.info("Starting Farcaster replies scheduler loop.")
        while True:
            try:
                logger.debug(f"Reply scheduler loop: waiting for item. Queue size: {self.reply_queue.qsize()}")
                reply_data = await self.reply_queue.get()
                content = reply_data["content"]
                reply_to_hash = reply_data["reply_to_hash"]
                action_id = reply_data.get("action_id")
                logger.info(f"Dequeued scheduled reply to {reply_to_hash}: {content[:70]}...")
                cast_result_data: Optional[Dict[str, Any]] = None
                error_message: Optional[str] = None
                try:
                    if not self.api_client.signer_uuid:
                        raise ValueError("Signer UUID not configured in API client, cannot reply.")
                    api_response = await self.api_client.publish_cast(
                        text=content,
                        signer_uuid=self.api_client.signer_uuid,
                        parent=reply_to_hash
                    )
                    if "cast" in api_response and "hash" in api_response["cast"]:
                        cast_result_data = api_response["cast"]
                        logger.info(f"Successfully sent scheduled reply. Cast hash: {cast_result_data.get('hash')}")
                    else:
                        error_message = api_response.get('message', f"Unknown error from API: {str(api_response)[:200]}")
                        logger.error(f"Failed to send scheduled reply: {error_message}")
                        self.replied_to_hashes.discard(reply_to_hash)
                except Exception as e:
                    error_message = str(e)
                    logger.error(f"Error sending scheduled reply: {e}", exc_info=True)
                    self.replied_to_hashes.discard(reply_to_hash)
                if self.world_state_manager:
                    params_for_wsm = {"content": content, "reply_to_hash": reply_to_hash}
                    if cast_result_data and cast_result_data.get("hash"):
                        cast_hash = cast_result_data["hash"]
                        params_for_wsm["cast_hash"] = cast_hash
                        if action_id:
                            self.world_state_manager.update_action_result(action_id, "success", cast_hash)
                        else:
                            self.world_state_manager.add_action_result("send_farcaster_reply", params_for_wsm, "success")
                    else:
                        result_status = f"failure: {error_message or 'unknown error'}"
                        if action_id:
                            self.world_state_manager.update_action_result(action_id, result_status)
                        else:
                             self.world_state_manager.add_action_result("send_farcaster_reply", params_for_wsm, result_status)
                self.reply_queue.task_done()
                await asyncio.sleep(self.scheduler_interval)
            except asyncio.CancelledError:
                logger.info("Reply scheduler loop cancelled.")
                break
            except Exception as e:
                logger.error(f"Unexpected error in reply scheduler loop: {e}", exc_info=True)
                await asyncio.sleep(5)
