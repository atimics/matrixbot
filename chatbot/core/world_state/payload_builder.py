#!/usr/bin/env python3
"""
Payload Builder

This module is responsible for constructing different types of AI payloads from
WorldStateData. It supports both traditional full payloads and node-based payloads
for handling large datasets efficiently.

The PayloadBuilder implements the separation of concerns principle by moving payload
construction logic out of the WorldStateManager, making the system more modular
and testable.
"""

import json
import logging
import time
from dataclasses import asdict
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING, Generator

from chatbot.config import settings
from .structures import Channel, WorldStateData

if TYPE_CHECKING:
    from ..node_system.node_manager import NodeManager
    from ..world_state_manager import WorldStateManager

logger = logging.getLogger(__name__)


class PayloadBuilder:
    """
    Constructs different types of AI payloads from WorldStateData.

    This class provides methods to build:
    1. Full payloads - Complete world state data with intelligent filtering
    2. Node-based payloads - Using expanded/collapsed node system for large datasets
    3. Payload size estimation for strategy selection
    """

    def __init__(
        self,
        world_state_manager: Optional["WorldStateManager"] = None,
        node_manager: Optional["NodeManager"] = None,
    ):
        """
        Initialize PayloadBuilder.

        Args:
            world_state_manager: Optional WorldStateManager instance.
            node_manager: Optional NodeManager for node-based payloads.
        """
        self.world_state_manager = world_state_manager
        self.node_manager = node_manager
        # Dispatcher for node data retrieval, improving maintainability
        self._node_data_handlers = {
            "channels": self._get_channel_node_data,
            "users": self._get_user_node_data,
            "tools": self._get_tool_node_data,
            "memory_bank": self._get_memory_bank_node_data,
            "farcaster": self._get_farcaster_node_data,
            "threads": self._get_thread_node_data,
            "system": self._get_system_node_data,
        }

    def _build_action_history_payload(
        self, world_state_data: WorldStateData, max_history: int, optimize: bool
    ) -> List[Dict[str, Any]]:
        """Builds a consistent action history payload."""
        history = world_state_data.action_history[-max_history:]
        if not optimize:
            return [asdict(action) for action in history]

        return [
            {
                "action_type": action.action_type,
                "result": (
                    action.result[:100] + "..."
                    if action.result and len(action.result) > 100
                    else action.result
                ),
                "timestamp": action.timestamp,
            }
            for action in history
        ]

    def _build_thread_context(
        self,
        world_state_data: WorldStateData,
        primary_channel_id: Optional[str],
        max_messages: int,
        optimize: bool,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Build a focused thread context for the primary channel."""
        if not primary_channel_id:
            return {}

        # Find the primary channel in nested structure
        primary_channel = None
        for platform_channels in world_state_data.channels.values():
            if primary_channel_id in platform_channels:
                primary_channel = platform_channels[primary_channel_id]
                break
                
        if not primary_channel or not primary_channel.recent_messages:
            return {}

        thread_ids_in_channel: Set[str] = {
            msg.reply_to or msg.id
            for msg in primary_channel.recent_messages
            if msg.reply_to or msg.id
        }

        thread_context = {}
        for thread_id in thread_ids_in_channel:
            if thread_id in world_state_data.threads:
                thread_messages = sorted(
                    world_state_data.threads[thread_id], key=lambda m: m.timestamp
                )[-max_messages:]
                if optimize:
                    thread_context[thread_id] = [
                        m.to_ai_summary_dict() for m in thread_messages
                    ]
                else:
                    thread_context[thread_id] = [asdict(m) for m in thread_messages]

        return thread_context

    def build_full_payload(
        self,
        world_state_data: WorldStateData,
        primary_channel_id: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Build a traditional full payload from world state data with size optimizations.
        Includes tactical fixes for handling newly joined channels and data spikes.

        Args:
            world_state_data: The world state data to convert.
            primary_channel_id: Channel to prioritize in the payload.
            config: Configuration dict with payload options.

        Returns:
            Dictionary optimized for AI consumption.
        """
        cfg = config or {}
        
        # Tactical fix: More aggressive defaults when optimizing
        base_max_messages = settings.AI_CONVERSATION_HISTORY_LENGTH
        base_max_other_channels = settings.AI_OTHER_CHANNELS_SUMMARY_COUNT
        
        # Detect if we have many recently joined channels (potential data spike)
        current_time = time.time()
        all_channels = [ch for platform_channels in world_state_data.channels.values() for ch in platform_channels.values()]
        recent_channels = [
            ch for ch in all_channels 
            if ch.recent_messages and 
            current_time - ch.recent_messages[0].timestamp < 3600  # Last hour
        ]
        
        # Apply more aggressive filtering if we detect a data spike
        data_spike_detected = len(recent_channels) > 10
        
        if data_spike_detected:
            logger.info(f"Data spike detected: {len(recent_channels)} active channels. Applying aggressive filtering.")
            # Reduce limits significantly for data spikes
            max_messages_per_channel = cfg.get("max_messages_per_channel", max(1, base_max_messages // 2))
            max_other_channels = cfg.get("max_other_channels", max(1, base_max_other_channels // 2))
        else:
            max_messages_per_channel = cfg.get("max_messages_per_channel", base_max_messages)
            max_other_channels = cfg.get("max_other_channels", base_max_other_channels)
            
        max_action_history = cfg.get(
            "max_action_history", settings.AI_ACTION_HISTORY_LENGTH
        )
        max_thread_messages = cfg.get(
            "max_thread_messages", settings.AI_THREAD_HISTORY_LENGTH
        )
        optimize_for_size = cfg.get("optimize_for_size", True)

        def sort_key(channel_item):
            ch_id, ch_data = channel_item
            last_activity = (
                ch_data.recent_messages[-1].timestamp if ch_data.recent_messages else 0
            )
            if ch_id == primary_channel_id:
                return (0, -last_activity)
            if ch_data.type == "farcaster" and ("home" in ch_id or "notification" in ch_id):
                return (1, -last_activity)
            return (2 if ch_data.type == "farcaster" else 3, -last_activity)

        # Flatten channels from nested structure for sorting
        all_channel_items = [
            (channel_id, channel) 
            for platform_channels in world_state_data.channels.values() 
            for channel_id, channel in platform_channels.items()
        ]
        sorted_channels = sorted(all_channel_items, key=sort_key)

        channels_payload = {}
        detailed_count = 0
        for ch_id, ch_data in sorted_channels:
            is_primary = ch_id == primary_channel_id
            is_key_farcaster = ch_data.type == "farcaster" and any(
                k in ch_id for k in ["home", "notification", "reply"]
            )
            
            # Tactical fix: Detect newly joined channels and be more aggressive
            is_newly_joined = False
            if ch_data.recent_messages:
                first_msg_time = ch_data.recent_messages[0].timestamp
                is_newly_joined = current_time - first_msg_time < 1800  # Last 30 minutes
            
            include_detailed = (
                is_primary or 
                (is_key_farcaster and not is_newly_joined) or  # Skip newly joined non-primary channels
                (detailed_count < max_other_channels and not is_newly_joined)
            )

            if include_detailed and ch_data.recent_messages:
                # Tactical fix: Further reduce message count for newly joined channels
                msg_limit = max_messages_per_channel
                if is_newly_joined and not is_primary:
                    msg_limit = max(1, msg_limit // 2)
                    
                messages = ch_data.recent_messages[-msg_limit:]
                messages_for_payload = []
                for msg in messages:
                    msg_dict = (
                        msg.to_ai_summary_dict() if optimize_for_size else asdict(msg)
                    )
                    msg_dict["already_replied"] = world_state_data.has_replied_to_cast(
                        msg.id
                    )
                    messages_for_payload.append(msg_dict)

                channel_payload = {
                    "id": ch_data.id,
                    "type": ch_data.type,
                    "name": ch_data.name,
                    "recent_messages": messages_for_payload,
                }
                
                # Mark newly joined channels for AI awareness
                if is_newly_joined:
                    channel_payload["recently_joined"] = True
                    
                channels_payload[ch_id] = channel_payload
                
                if not is_primary and not is_key_farcaster:
                    detailed_count += 1
            else:
                # Tactical fix: Provide more compact summaries for newly joined channels
                summary = ch_data.get_activity_summary()
                summary.update({"id": ch_data.id, "type": ch_data.type, "name": ch_data.name})
                
                if is_newly_joined:
                    summary["recently_joined"] = True
                    # Truncate summary for newly joined channels
                    if "recent_activity" in summary:
                        summary["recent_activity"] = summary["recent_activity"][:2]  # Only 2 most recent
                        
                channels_payload[ch_id] = summary

        payload = {
            "current_processing_channel_id": primary_channel_id,
            "channels": channels_payload,
            "action_history": self._build_action_history_payload(
                world_state_data, max_action_history, optimize_for_size
            ),
            "thread_context": self._build_thread_context(
                world_state_data, primary_channel_id, max_thread_messages, optimize_for_size
            ),
            "system_status": {
                **world_state_data.system_status,
                "rate_limits": world_state_data.rate_limits,
            },
            "pending_matrix_invites": world_state_data.pending_matrix_invites,
            "recent_media_actions": world_state_data.get_recent_media_actions(),
            "payload_stats": {
                "primary_channel": primary_channel_id,
                "detailed_channels": detailed_count,
                "summary_channels": len(sorted_channels) - detailed_count,
                "data_spike_detected": data_spike_detected,
                "active_channels_count": len(recent_channels),
                "bot_identity": {
                    "fid": settings.FARCASTER_BOT_FID,
                    "username": settings.FARCASTER_BOT_USERNAME,
                },
            },
            "user_profiling": self._build_user_profiling_payload(
                world_state_data, optimize_for_size
            ),
        }

        if not optimize_for_size:
            payload.update(self._get_full_detail_data(world_state_data))

        return self._optimize_payload_size(payload)

    def _get_full_detail_data(self, world_state_data: WorldStateData) -> Dict[str, Any]:
        """Constructs the non-optimized, detailed parts of the payload."""
        return {
            "generated_media_library": [
                asdict(m) for m in world_state_data.generated_media_library[-10:]
            ],
            "ecosystem_token_info": {
                "contract_address": world_state_data.ecosystem_token_contract,
                "token_metadata": asdict(world_state_data.token_metadata)
                if world_state_data.token_metadata
                else None,
                "monitored_holders_activity": [
                    asdict(h)
                    for h in world_state_data.monitored_token_holders.values()
                ],
            },
            "research_knowledge": {
                "available_topics": list(world_state_data.research_database.keys()),
                "topic_count": len(world_state_data.research_database),
                "note": "Use query_research tool to access detailed research information",
            },
        }

    def build_node_based_payload(
        self,
        world_state_data: WorldStateData,
        node_manager: "NodeManager",
        primary_channel_id: str,
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Build a node-based payload using the expanded/collapsed node system.

        Args:
            world_state_data: The world state data to convert.
            node_manager: Node manager for expansion/collapse state.
            primary_channel_id: Primary channel being processed.
            config: Configuration dict with payload options.

        Returns:
            Dictionary with node-based structure for AI consumption.
        """
        cfg = config or {}
        all_node_paths = self._get_node_paths_from_world_state(world_state_data)
        expanded_nodes, collapsed_node_summaries = {}, {}

        for node_path in all_node_paths:
            metadata = node_manager.get_node_metadata(node_path)
            
            if metadata.is_expanded:
                # Request EXPANDED data for this node
                node_data = self._get_node_data_by_path(world_state_data, node_path, expanded=True)
                if node_data is not None:
                    expanded_nodes[node_path] = {
                        "data": node_data,
                        "is_pinned": metadata.is_pinned,
                        "last_expanded": metadata.last_expanded_ts,
                    }
            else:
                # Request SUMMARY data for this node
                node_data = self._get_node_data_by_path(world_state_data, node_path, expanded=False)
                if node_data is not None:
                    summary = metadata.ai_summary or f"Node {node_path} (no summary available)"
                    collapsed_node_summaries[node_path] = {
                        "summary": summary,
                        "data_changed": node_manager.is_data_changed(node_path, node_data),
                        "last_summary_update": metadata.last_summary_update_ts,
                    }

        payload = {
            "current_processing_channel_id": primary_channel_id,
            "system_status": {
                "timestamp": world_state_data.last_update,
                "rate_limits": world_state_data.rate_limits,
            },
            "expanded_nodes": expanded_nodes,
            "collapsed_node_summaries": collapsed_node_summaries,
            "expansion_status": node_manager.get_expansion_status_summary(),
            "system_events": node_manager.get_system_events(),
        }

        # Calculating size is expensive, but necessary for stats
        payload_size_bytes = len(json.dumps(payload, default=str).encode("utf-8"))
        payload["payload_stats"] = {
            "size_bytes": payload_size_bytes,
            "size_kb": round(payload_size_bytes / 1024, 2),
            "expanded_nodes_count": len(expanded_nodes),
            "collapsed_nodes_count": len(collapsed_node_summaries),
            "total_nodes": len(all_node_paths),
            "bot_identity": {
                "fid": cfg.get("bot_fid"),
                "username": cfg.get("bot_username"),
            },
        }

        return payload

    @staticmethod
    def estimate_payload_size(
        world_state_data: WorldStateData, config: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Estimate the size of a full payload in bytes using heuristics.

        Args:
            world_state_data: The world state data to estimate.
            config: Configuration options (reserved).

        Returns:
            Estimated payload size in bytes.
        """
        try:
            metrics = world_state_data.get_state_metrics()
            estimated_size = (
                metrics.get("channel_count", 0) * 1500
                + metrics.get("total_messages", 0) * 800
                + metrics.get("action_history_count", 0) * 500
                + metrics.get("thread_count", 0) * 300
                + len(world_state_data.generated_media_library) * 200
                + 5000  # Base overhead
            )
            return int(estimated_size)
        except Exception as e:
            logger.error(f"Error estimating payload size: {e}", exc_info=True)
            return 50000  # Conservative fallback

    # --- Node-based Payload Helpers ---

    def _get_node_paths_from_world_state(
        self, world_state_data: WorldStateData
    ) -> List[str]:
        """Extract all available node paths from the world state data."""
        return list(self._generate_node_paths(world_state_data))

    def _generate_node_paths(
        self, world_state_data: WorldStateData
    ) -> Generator[str, None, None]:
        """Generate all node paths from different parts of the world state."""
        yield from self._generate_channel_paths(world_state_data)
        yield from self._generate_farcaster_feed_paths(world_state_data)
        yield from self._generate_user_paths(world_state_data)
        yield from self._generate_tool_cache_paths(world_state_data)
        yield from self._generate_search_cache_paths(world_state_data)
        yield from self._generate_memory_bank_paths(world_state_data)
        yield from self._generate_thread_paths(world_state_data)
        yield from self._generate_system_paths(world_state_data)

    def _generate_channel_paths(self, world_state_data: WorldStateData):
        for platform, platform_channels in world_state_data.channels.items():
            for channel_id, channel in platform_channels.items():
                yield f"channels.{channel.type}.{channel_id}"

    def _generate_farcaster_feed_paths(self, world_state_data: WorldStateData):
        # Check if any channel is of type farcaster
        has_farcaster = any(
            any(ch.type == "farcaster" for ch in platform_channels.values()) 
            for platform_channels in world_state_data.channels.values()
        )
        if has_farcaster:
            yield from ["farcaster.feeds.home", "farcaster.feeds.notifications", "farcaster.feeds.trending"]

    def _generate_user_paths(self, world_state_data: WorldStateData):
        user_fids = set(world_state_data.farcaster_users.keys())
        user_matrix_ids = set(world_state_data.matrix_users.keys())

        for platform_channels in world_state_data.channels.values():
            for channel in platform_channels.values():
                for msg in channel.recent_messages[-10:]:  # Limit scan to recent messages
                    if msg.sender_fid: user_fids.add(str(msg.sender_fid))
                    if msg.sender_username: user_matrix_ids.add(msg.sender_username)

        for fid in user_fids:
            yield f"users.farcaster.{fid}"
            if fid in world_state_data.farcaster_users:
                user = world_state_data.farcaster_users[fid]
                if user.timeline_cache: yield f"users.farcaster.{fid}.timeline_cache"
                if user.sentiment: yield f"users.farcaster.{fid}.sentiment"
                if user.memory_entries: yield f"users.farcaster.{fid}.memories"

        for user_id in user_matrix_ids:
            yield f"users.matrix.{user_id}"
            if user_id in world_state_data.matrix_users:
                user = world_state_data.matrix_users[user_id]
                if user.sentiment: yield f"users.matrix.{user_id}.sentiment"
                if user.memory_entries: yield f"users.matrix.{user_id}.memories"
    
    def _generate_tool_cache_paths(self, world_state_data: WorldStateData):
        if len(world_state_data.tool_cache) > 1:
            yield "tools.cache"
            tool_counts = {}
            for key in world_state_data.tool_cache:
                tool_name = key.split(":", 1)[0]
                tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1
            for tool_name, count in tool_counts.items():
                if count > 1:
                    yield f"tools.cache.{tool_name}"

    def _generate_search_cache_paths(self, world_state_data: WorldStateData):
        if world_state_data.search_cache:
            yield "farcaster.search_cache"
            recent_searches = sorted(
                world_state_data.search_cache.items(),
                key=lambda item: item[1].get("timestamp", 0),
                reverse=True,
            )[:3]
            for query_hash, _ in recent_searches:
                yield f"farcaster.search_cache.{query_hash}"

    def _generate_memory_bank_paths(self, world_state_data: WorldStateData):
        if world_state_data.user_memory_bank and sum(len(m) for m in world_state_data.user_memory_bank.values()) > 5:
            yield "memory_bank"
            platform_counts = {}
            for key, memories in world_state_data.user_memory_bank.items():
                platform = key.split(":", 1)[0]
                platform_counts[platform] = platform_counts.get(platform, 0) + len(memories)
            for platform, count in platform_counts.items():
                if count > 2:
                    yield f"memory_bank.{platform}"

    def _generate_thread_paths(self, world_state_data: WorldStateData):
        if world_state_data.threads:
            active_threads = []
            two_hours_ago = time.time() - 7200
            for thread_id, msgs in world_state_data.threads.items():
                if msgs and msgs[-1].timestamp > two_hours_ago:
                    active_threads.append(thread_id)
            for thread_id in active_threads[:3]: # Limit to 3 most active
                yield f"threads.farcaster.{thread_id}"

    def _generate_system_paths(self, world_state_data: WorldStateData):
        yield from ["system.rate_limits", "system.status", "system.action_history"]
        if world_state_data.pending_matrix_invites:
            yield "system.notifications"

    def _get_node_data_by_path(
        self, world_state_data: WorldStateData, node_path: str, expanded: bool = False
    ) -> Any:
        """
        Get the actual data for a specific node path using a dispatcher.
        
        Args:
            world_state_data: The world state to extract data from.
            node_path: The path to the node (e.g., "channels.matrix.!room_id").
            expanded: Whether to return full details for the node.
        
        Returns:
            The data for that node, or None if not found.
        """
        try:
            path_parts = node_path.split(".")
            handler = self._node_data_handlers.get(path_parts[0])
            if handler:
                return handler(world_state_data, path_parts, expanded=expanded)
            logger.warning(f"No handler found for node path prefix: {path_parts[0]}")
            return None
        except Exception as e:
            logger.error(f"Error getting data for node path {node_path}: {e}", exc_info=True)
            return None

    # --- Node Data Handlers ---

    def _get_channel_node_data(self, world_state_data: WorldStateData, path_parts: List[str], expanded: bool = False) -> Optional[Dict]:
        if len(path_parts) != 3: return None
        _, channel_type, channel_id = path_parts
        
        # Access channel from nested structure: channels[platform][channel_id]
        if channel_type not in world_state_data.channels:
            return None
        
        channel = world_state_data.channels[channel_type].get(channel_id)
        if not channel: 
            return None
        
        # Determine message list based on expansion status
        if expanded:
            # For expanded nodes, provide enhanced summaries with more messages and context
            messages_for_payload = [msg.to_ai_summary_dict() for msg in channel.recent_messages[-8:]] # More messages but still summaries
        else:
            # For collapsed nodes, provide basic summaries
            messages_for_payload = [msg.to_ai_summary_dict() for msg in channel.recent_messages[-3:]]

        return {
            "id": channel.id,
            "name": channel.name,
            "type": channel.type,
            "status": channel.status,
            "msg_count": len(channel.recent_messages),
            "last_activity": channel.recent_messages[-1].timestamp if channel.recent_messages else channel.last_checked,
            "recent_messages": messages_for_payload,
        }

    def _get_user_node_data(self, world_state_data: WorldStateData, path_parts: List[str], expanded: bool = False) -> Optional[Dict]:
        if len(path_parts) < 3: return None
        _, user_type, user_id = path_parts[0], path_parts[1], path_parts[2]
        
        user = None
        if user_type == "farcaster":
            user = world_state_data.farcaster_users.get(user_id)
        elif user_type == "matrix":
            user = world_state_data.matrix_users.get(user_id)
        
        if len(path_parts) == 4 and user: # Sub-node request
            sub_node = path_parts[3]
            if sub_node == "timeline_cache": return getattr(user, 'timeline_cache', None)
            if sub_node == "sentiment": return asdict(getattr(user, 'sentiment', None)) if getattr(user, 'sentiment', None) else None
            if sub_node == "memories": return [asdict(mem) for mem in getattr(user, 'memory_entries', [])[-5:]]
        
        if user:
            # Use to_ai_summary_dict if available, otherwise create basic dict
            if hasattr(user, 'to_ai_summary_dict'):
                return user.to_ai_summary_dict()
            else:
                return {
                    "id": user_id,
                    "type": user_type,
                    "username": getattr(user, 'username', None),
                    "display_name": getattr(user, 'display_name', None)
                }
        
        # Fallback for users not in the main dict
        for channel in world_state_data.channels.values():
            for msg in reversed(channel.recent_messages[-5:]):
                if user_type == "farcaster" and str(msg.sender_fid) == user_id:
                    return {
                        "id": user_id,
                        "type": user_type,
                        "username": msg.sender_username,
                        "display_name": msg.sender_display_name,
                        "fid": msg.sender_fid
                    }
                if user_type == "matrix" and msg.sender_username == user_id:
                    return {
                        "id": user_id,
                        "type": user_type,
                        "username": msg.sender_username,
                        "display_name": msg.sender_display_name
                    }
        return {"type": user_type, "id": user_id, "error": "User data not found"}

    def _get_farcaster_node_data(self, world_state_data: WorldStateData, path_parts: List[str], expanded: bool = False) -> Optional[Dict]:
        if len(path_parts) < 2: return None
        node_type = path_parts[1]
        
        if node_type == "feeds" and len(path_parts) >= 3:
            feed_type = path_parts[2]
            if feed_type == "trending":
                return {"feed_type": "trending", "status": "Available via get_trending_casts tool"}
            
            messages = []
            if feed_type == "home":
                for ch in world_state_data.channels.values():
                    if ch.type == "farcaster" and "home" in ch.id:
                        messages.extend(ch.recent_messages[-5:])
            elif feed_type == "notifications":
                for ch in world_state_data.channels.values():
                    if ch.type == "farcaster" and ("notification" in ch.id or "mention" in ch.id):
                        messages.extend(ch.recent_messages[-5:])
            
            messages.sort(key=lambda m: m.timestamp, reverse=True)
            return {
                "feed_type": feed_type,
                "recent_activity": [m.to_ai_summary_dict() for m in messages[:10]]
            }
            
        elif node_type == "search_cache":
            if len(path_parts) == 2:
                return {"cached_searches": [d.get("query", "Unknown") for d in world_state_data.search_cache.values()]}
            if len(path_parts) == 3:
                return world_state_data.search_cache.get(path_parts[2])
        return None

    def _get_system_node_data(self, world_state_data: WorldStateData, path_parts: List[str], expanded: bool = False) -> Optional[Dict]:
        if len(path_parts) < 2: return None
        component = path_parts[1]
        if component == "notifications": return {"pending_matrix_invites": world_state_data.pending_matrix_invites}
        if component == "rate_limits": return world_state_data.rate_limits
        if component == "status": return world_state_data.system_status
        if component == "action_history": 
            # Use optimized action history to prevent large payloads
            return self._build_action_history_payload(world_state_data, 10, optimize=True)
        return None

    # Simplified handlers for other node types
    def _get_tool_node_data(self, world_state_data: WorldStateData, path_parts: List[str], expanded: bool = False) -> Optional[Dict]:
        if len(path_parts) < 2: return None
        if path_parts[1] == "cache":
            if len(path_parts) == 2:
                # Return compact overview of cached tools
                tool_summary = {}
                for cache_key, cache_data in list(world_state_data.tool_cache.items())[:10]:
                    tool_name = cache_key.split(":")[0] if ":" in cache_key else cache_key
                    if tool_name not in tool_summary:
                        tool_summary[tool_name] = {"count": 0, "most_recent": 0}
                    tool_summary[tool_name]["count"] += 1
                    tool_summary[tool_name]["most_recent"] = max(
                        tool_summary[tool_name]["most_recent"],
                        cache_data.get("timestamp", 0)
                    )
                return {"cached_tools": tool_summary, "total_entries": len(world_state_data.tool_cache)}
            elif len(path_parts) == 3:
                # Return specific tool cache data
                tool_name = path_parts[2]
                tool_results = {}
                count = 0
                for cache_key, cache_data in world_state_data.tool_cache.items():
                    if cache_key.startswith(f"{tool_name}:") and count < 3:
                        tool_results[cache_key] = {
                            "timestamp": cache_data.get("timestamp"),
                            "result_type": cache_data.get("result_type"),
                            "size": len(str(cache_data)) if cache_data else 0
                        }
                        count += 1
                return {"tool_name": tool_name, "cached_results": tool_results, "total_cached": count}
        return None

    def _get_memory_bank_node_data(self, world_state_data: WorldStateData, path_parts: List[str], expanded: bool = False) -> Optional[Dict]:
        if len(path_parts) == 1:
            # Return overview of memory bank
            memory_stats = {}
            for user_platform_id, memories in world_state_data.user_memory_bank.items():
                platform = user_platform_id.split(":")[0] if ":" in user_platform_id else "unknown"
                if platform not in memory_stats:
                    memory_stats[platform] = {"users": 0, "total_memories": 0}
                memory_stats[platform]["users"] += 1
                memory_stats[platform]["total_memories"] += len(memories)
            return {"platform_breakdown": memory_stats, "total_users_with_memories": len(world_state_data.user_memory_bank)}
        elif len(path_parts) == 2:
            # Return memories for specific platform
            platform = path_parts[1]
            platform_memories = {}
            for user_platform_id, memories in world_state_data.user_memory_bank.items():
                if user_platform_id.startswith(f"{platform}:"):
                    platform_memories[user_platform_id] = [
                        {
                            "memory_id": mem.memory_id,
                            "content": mem.content[:100] + "..." if len(mem.content) > 100 else mem.content,
                            "memory_type": mem.memory_type,
                            "importance": mem.importance,
                            "timestamp": mem.timestamp
                        }
                        for mem in memories[-3:]
                    ]
            return {"platform": platform, "user_memories": platform_memories}
        return None

    def _get_thread_node_data(self, world_state_data: WorldStateData, path_parts: List[str], expanded: bool = False) -> Optional[Dict]:
        if len(path_parts) >= 3:
            thread_type, thread_id = path_parts[1], path_parts[2]
            thread_messages = world_state_data.threads.get(thread_id, [])
            return {
                "thread_id": thread_id,
                "type": thread_type,
                "messages": [msg.to_ai_summary_dict() for msg in thread_messages[-5:]]  # Use summaries instead of full data
            }
        return None

    # --- User Profiling and Payload Optimization Helpers ---

    def _build_single_user_profile(
        self, user: Any, optimize_for_size: bool
    ) -> Dict[str, Any]:
        """Helper to build a profile dict from a user object."""
        profile = {}
        # Add sentiment
        if sentiment := getattr(user, "sentiment", None):
            profile["sentiment"] = asdict(sentiment)
        # Add memories
        if memory_entries := getattr(user, "memory_entries", []):
            limit = 3 if optimize_for_size else 5
            profile["recent_memories"] = [
                asdict(mem) for mem in memory_entries[-limit:]
            ]
        return profile

    def _build_user_profiling_payload(
        self, world_state_data: WorldStateData, optimize_for_size: bool
    ) -> Dict[str, Any]:
        """Builds user profiling data for inclusion in AI payloads."""
        user_profiling = {}
        
        # Farcaster Profiles
        farcaster_profiles = {}
        for fid, user in world_state_data.farcaster_users.items():
            profile = {
                "username": getattr(user, 'username', None),
                "display_name": getattr(user, 'display_name', None),
                "follower_count": getattr(user, 'follower_count', 0),
            }
            profile.update(self._build_single_user_profile(user, optimize_for_size))
            farcaster_profiles[fid] = profile
        
        if farcaster_profiles:
            user_profiling["farcaster_users"] = farcaster_profiles

        # Matrix Profiles  
        matrix_profiles = {}
        for uid, user in world_state_data.matrix_users.items():
            profile = {
                "user_id": getattr(user, 'user_id', uid),
                "display_name": getattr(user, 'display_name', None),
            }
            profile.update(self._build_single_user_profile(user, optimize_for_size))
            matrix_profiles[uid] = profile
        
        if matrix_profiles:
            user_profiling["matrix_users"] = matrix_profiles

        if user_profiling:
            user_profiling["available_tools"] = [
                "analyze_user_sentiment", "store_user_memory", "get_user_profile"
            ]
        return user_profiling

    @staticmethod
    def _remove_empty_values(data: Any) -> Any:
        """Recursively remove empty values (None, "", [], {}) from dicts and lists."""
        if isinstance(data, dict):
            cleaned_dict = {}
            for key, value in data.items():
                # Preserve important structural keys even if they're empty
                preserve_empty = key in ["channels", "action_history", "thread_context", "system_status"]
                cleaned_value = PayloadBuilder._remove_empty_values(value)
                if cleaned_value not in (None, "", [], {}) or preserve_empty:
                    cleaned_dict[key] = cleaned_value
            return cleaned_dict
        if isinstance(data, list):
            cleaned_list = []
            for item in data:
                if (cleaned_item := PayloadBuilder._remove_empty_values(item)) not in (None, "", [], {}):
                    cleaned_list.append(cleaned_item)
            return cleaned_list
        return data

    @staticmethod
    def _optimize_payload_size(payload: Dict[str, Any]) -> Dict[str, Any]:
        """Apply various optimizations to reduce payload size."""
        return PayloadBuilder._remove_empty_values(payload)
