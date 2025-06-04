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
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .structures import WorldStateData, Channel

if TYPE_CHECKING:
    from ..node_system.node_manager import NodeManager

logger = logging.getLogger(__name__)


class PayloadBuilder:
    """
    Constructs different types of AI payloads from WorldStateData.
    
    This class provides methods to build:
    1. Full payloads - Complete world state data with intelligent filtering
    2. Node-based payloads - Using expanded/collapsed node system for large datasets
    3. Payload size estimation for strategy selection
    """

    def __init__(self):
        pass

    def build_full_payload(
        self,
        world_state_data: WorldStateData,
        primary_channel_id: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Build a traditional full payload from world state data with size optimizations.
        
        This is the original approach that includes complete world state information
        with intelligent filtering and prioritization based on channel activity.
        
        Args:
            world_state_data: The world state data to convert
            primary_channel_id: Channel to prioritize in the payload
            config: Configuration dict with options like:
                - max_messages_per_channel: Max messages to include per channel
                - max_action_history: Max action history items
                - max_thread_messages: Max thread messages
                - max_other_channels: Max non-primary channels with full detail
                - message_snippet_length: Length for message truncation
                - include_detailed_user_info: Whether to include full user data
                - bot_fid: Bot's Farcaster ID for message filtering
                - bot_username: Bot's username for message filtering
        
        Returns:
            Dictionary optimized for AI consumption
        """
        # Set default config values with optimization focus
        if config is None:
            config = {}
        
        # Reduced default limits for payload optimization
        max_messages_per_channel = config.get("max_messages_per_channel", 8)  # Reduced from 10
        max_action_history = config.get("max_action_history", 4)  # Reduced from 5
        max_thread_messages = config.get("max_thread_messages", 4)  # Reduced from 5
        max_other_channels = config.get("max_other_channels", 2)  # Reduced from 3
        message_snippet_length = config.get("message_snippet_length", 60)  # Reduced from 75
        include_detailed_user_info = config.get("include_detailed_user_info", False)  # Changed default to False
        bot_fid = config.get("bot_fid")
        bot_username = config.get("bot_username")
        optimize_for_size = config.get("optimize_for_size", True)  # New optimization flag

        # Sort channels with improved cross-platform balance
        # First, identify active integrations (platforms with recent activity)
        active_integrations = set()
        current_time = time.time()
        recent_threshold = current_time - (30 * 60)  # 30 minutes
        
        for ch_id, ch_data in world_state_data.channels.items():
            if ch_data.recent_messages and ch_data.recent_messages[-1].timestamp > recent_threshold:
                active_integrations.add(ch_data.type)
        
        # Sort channels with dynamic prioritization
        def sort_key(channel_item):
            ch_id, ch_data = channel_item
            last_activity = ch_data.recent_messages[-1].timestamp if ch_data.recent_messages else 0
            
            # Primary channel always gets top priority
            if ch_id == primary_channel_id:
                return (0, -last_activity)
            
            # Key Farcaster feeds get high priority
            if ch_data.type == "farcaster" and ("home" in ch_id or "notification" in ch_id):
                return (1, -last_activity)
            
            # For other channels, slightly boost less represented platforms
            platform_boost = 2 if ch_data.type == "farcaster" else 3
            return (platform_boost, -last_activity)
        
        sorted_channels = sorted(world_state_data.channels.items(), key=sort_key)

        channels_payload = {}
        detailed_count = 0
        platforms_with_detailed = set()

        for ch_id, ch_data in sorted_channels:
            # Include all messages including bot's own for AI context
            # The AI needs to see its own recent messages to maintain conversational flow
            # and understand the current state of conversations
            all_messages = ch_data.recent_messages

            # Decide if this channel gets detailed treatment
            is_primary = ch_id == primary_channel_id
            # Always include key Farcaster channels for minimum visibility
            is_key_farcaster = ch_data.type == "farcaster" and (
                "home" in ch_id or "notification" in ch_id or "reply" in ch_id
            )
            
            # Enhanced logic: ensure at least one detailed channel per active platform
            platform_needs_representation = (
                ch_data.type in active_integrations and 
                ch_data.type not in platforms_with_detailed and
                detailed_count < max_other_channels
            )
            
            include_detailed = (
                is_primary or 
                is_key_farcaster or 
                platform_needs_representation or
                detailed_count < max_other_channels
            )

            if include_detailed and all_messages:
                platforms_with_detailed.add(ch_data.type)
                # Optimized message processing with conditional detail levels
                truncated_messages = all_messages[-max_messages_per_channel:]
                
                if optimize_for_size:
                    # Compact format for size optimization
                    messages_for_payload = [
                        {
                            "id": msg.id,
                            "sender": msg.sender_username or msg.sender,
                            "content": msg.content[:message_snippet_length] + "..." 
                                     if len(msg.content) > message_snippet_length else msg.content,
                            "timestamp": msg.timestamp,
                            "fid": msg.sender_fid,
                            "reply_to": msg.reply_to,
                            "has_images": bool(msg.image_urls),
                            "power_badge": msg.metadata.get("power_badge", False) if msg.metadata else False
                        }
                        for msg in truncated_messages
                    ]
                else:
                    # Full detail when size optimization is disabled
                    messages_for_payload = [
                        msg.to_ai_summary_dict()
                        if not include_detailed_user_info
                        else asdict(msg)
                        for msg in truncated_messages
                    ]

                # Optimized timestamp range calculation
                timestamp_range = {
                    "start": truncated_messages[0].timestamp,
                    "end": truncated_messages[-1].timestamp,
                    "span_hours": round(
                        (truncated_messages[-1].timestamp - truncated_messages[0].timestamp) / 3600, 1
                    ),
                    "message_count": len(truncated_messages)
                } if truncated_messages else None

                if optimize_for_size:
                    # Compact channel payload
                    channels_payload[ch_id] = {
                        "id": ch_data.id,
                        "type": ch_data.type,
                        "name": ch_data.name[:30] + "..." if len(ch_data.name) > 30 else ch_data.name,
                        "recent_messages": messages_for_payload,
                        "last_activity": timestamp_range["end"] if timestamp_range else ch_data.last_checked,
                        "msg_count": len(messages_for_payload),
                        "priority": "detailed" if is_primary else "secondary"
                    }
                else:
                    # Full channel payload
                    channels_payload[ch_id] = {
                        "id": ch_data.id,
                        "type": ch_data.type,
                        "name": ch_data.name,
                        "recent_messages": messages_for_payload,
                        "last_checked": ch_data.last_checked,
                        "topic": ch_data.topic[:100] if ch_data.topic else None,
                        "member_count": ch_data.member_count,
                        "activity_summary": ch_data.get_activity_summary(),
                        "priority": "detailed" if is_primary else "secondary",
                        "message_timestamp_range": timestamp_range,
                    }
                # Only count towards detailed limit if it's not primary or key Farcaster
                if not is_primary and not is_key_farcaster:
                    detailed_count += 1
            else:
                # Optimized summary for less active channels
                activity = ch_data.get_activity_summary()
                if optimize_for_size:
                    channels_payload[ch_id] = {
                        "id": ch_data.id,
                        "type": ch_data.type,
                        "name": ch_data.name[:20] + "..." if len(ch_data.name) > 20 else ch_data.name,
                        "last_activity": activity.get("last_activity", 0),
                        "msg_count": activity.get("message_count", 0),
                        "priority": "summary"
                    }
                else:
                    channels_payload[ch_id] = {
                        "id": ch_data.id,
                        "type": ch_data.type,
                        "name": ch_data.name,
                        "activity_summary": activity,
                        "priority": "summary_only",
                    }

        # Optimized action history with conditional detail
        if optimize_for_size:
            action_history_payload = [
                {
                    "type": action.action_type,
                    "result": action.result,
                    "timestamp": action.timestamp,
                    "params": str(action.parameters)[:50] + "..." 
                           if len(str(action.parameters)) > 50 else action.parameters
                }
                for action in world_state_data.action_history[-max_action_history:]
            ]
        else:
            action_history_payload = [
                asdict(action) for action in world_state_data.action_history[-max_action_history:]
            ]

        # Optimized threads processing - only include if relevant and not empty
        threads_payload = {}
        if primary_channel_id and not optimize_for_size:
            # Only include threads when size optimization is disabled
            for thread_id, msgs in list(world_state_data.threads.items())[:3]:  # Limit to 3 threads max
                # Include thread if any message belongs to primary channel
                relevant_thread = any(
                    msg.channel_id == primary_channel_id for msg in msgs
                )

                if relevant_thread and msgs:
                    # Compact thread messages
                    all_thread_msgs = msgs[-max_thread_messages:]
                    if optimize_for_size:
                        thread_msgs_for_payload = [
                            {
                                "id": msg.id,
                                "sender": msg.sender_username or msg.sender,
                                "content": msg.content[:message_snippet_length] + "..." 
                                         if len(msg.content) > message_snippet_length else msg.content,
                                "timestamp": msg.timestamp
                            }
                            for msg in all_thread_msgs
                        ]
                    else:
                        thread_msgs_for_payload = [
                            msg.to_ai_summary_dict()
                            if not include_detailed_user_info
                            else asdict(msg)
                            for msg in all_thread_msgs
                        ]
                    threads_payload[thread_id] = thread_msgs_for_payload

        # Build optimized final payload based on configuration
        if optimize_for_size:
            # Compact payload structure with essential information only
            payload = {
                "current_channel": primary_channel_id,
                "channels": channels_payload,
                "actions": action_history_payload,
                "system": {
                    "timestamp": time.time(),
                    "rate_limits": world_state_data.rate_limits or {}
                },
                "stats": {
                    "channels": len(channels_payload),
                    "messages": sum(
                        len(ch.get("recent_messages", []))
                        for ch in channels_payload.values()
                        if "recent_messages" in ch
                    ),
                    "bot_fid": bot_fid
                },
                "ecosystem_token_info": {
                    "contract_address": world_state_data.ecosystem_token_contract,
                    "monitored_holders_activity": [
                        {
                            "fid": holder.fid,
                            "username": holder.username,
                            "display_name": holder.display_name,
                            "recent_casts": [msg.to_ai_summary_dict() for msg in holder.recent_casts]
                        }
                        for holder in world_state_data.monitored_token_holders.values()
                    ] if world_state_data.monitored_token_holders else []
                }
            }
            
            # Only include threads and other data if they're not empty
            if threads_payload:
                payload["threads"] = threads_payload
            if world_state_data.pending_matrix_invites:
                payload["pending_invites"] = len(world_state_data.pending_matrix_invites)
            
            # Minimal recent media info
            recent_media = world_state_data.get_recent_media_actions()
            if recent_media.get("recent_media_actions"):
                payload["recent_media_count"] = len(recent_media["recent_media_actions"])
        else:
            # Full payload structure
            payload = {
                "current_processing_channel_id": primary_channel_id,
                "channels": channels_payload,
                "action_history": action_history_payload,
                "system_status": {**world_state_data.system_status, "rate_limits": world_state_data.rate_limits},
                "threads": threads_payload,
                "pending_matrix_invites": world_state_data.pending_matrix_invites,
                "recent_media_actions": world_state_data.get_recent_media_actions(),
                "generated_media_library": world_state_data.generated_media_library[-10:],  # Reduced from 20
                "current_time": time.time(),
                "payload_stats": {
                    "primary_channel": primary_channel_id,
                    "detailed_channels": detailed_count
                    + (1 if primary_channel_id in channels_payload else 0),
                    "summary_channels": len(sorted_channels)
                    - detailed_count
                    - (1 if primary_channel_id in channels_payload else 0),
                    "total_channels": len(sorted_channels),
                    "included_messages": sum(
                        len(ch.get("recent_messages", []))
                        for ch in channels_payload.values()
                        if "recent_messages" in ch
                    ),
                    "bot_identity": {"fid": bot_fid, "username": bot_username},
                    "pending_invites_count": len(world_state_data.pending_matrix_invites),
                },
                "ecosystem_token_info": {
                    "contract_address": world_state_data.ecosystem_token_contract,
                    "monitored_holders_activity": [
                        {
                            "fid": holder.fid,
                            "username": holder.username,
                            "display_name": holder.display_name,
                            "recent_casts": [msg.to_ai_summary_dict() for msg in holder.recent_casts]
                        }
                        for holder in world_state_data.monitored_token_holders.values()
                    ] if world_state_data.monitored_token_holders else []
                },
            }
        
        return payload

    def build_node_based_payload(
        self,
        world_state_data: WorldStateData,
        node_manager: "NodeManager",
        primary_channel_id: str,
        config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Build a node-based payload using the expanded/collapsed node system.
        
        This approach shows expanded nodes in full detail and collapsed nodes as
        AI-generated summaries, allowing for interactive exploration of large datasets.
        
        Args:
            world_state_data: The world state data to convert
            node_manager: Node manager for expansion/collapse state
            primary_channel_id: Primary channel being processed
            config: Configuration dict with options like:
                - bot_fid: Bot's Farcaster ID
                - bot_username: Bot's username
        
        Returns:
            Dictionary with node-based structure for AI consumption
        """
        # Set default config values
        if config is None:
            config = {}
        
        bot_fid = config.get("bot_fid")
        bot_username = config.get("bot_username")

        # Start with system status and core info
        payload = {
            "current_processing_channel_id": primary_channel_id,
            "system_status": {
                "timestamp": world_state_data.last_update,
                "rate_limits": world_state_data.rate_limits
            }
        }
        
        # Get all available node paths from world state
        all_node_paths = self._get_node_paths_from_world_state(world_state_data)
        
        # Separate expanded and collapsed nodes
        expanded_nodes = {}
        collapsed_node_summaries = {}
        
        for node_path in all_node_paths:
            metadata = node_manager.get_node_metadata(node_path)
            node_data = self._get_node_data_by_path(world_state_data, node_path)
            
            if node_data is None:
                continue
            
            if metadata.is_expanded:
                # Include full data for expanded nodes
                expanded_nodes[node_path] = {
                    "data": node_data,
                    "is_pinned": metadata.is_pinned,
                    "last_expanded": metadata.last_expanded_ts
                }
            else:
                # Include summary for collapsed nodes
                summary = metadata.ai_summary or f"Node {node_path} (no summary available)"
                
                # Check if data has changed since last summary
                data_changed = node_manager.is_data_changed(node_path, node_data)
                
                collapsed_node_summaries[node_path] = {
                    "summary": summary,
                    "data_changed": data_changed,
                    "last_summary_update": metadata.last_summary_update_ts
                }
        
        payload["expanded_nodes"] = expanded_nodes
        payload["collapsed_node_summaries"] = collapsed_node_summaries
        
        # Add expansion status info
        payload["expansion_status"] = node_manager.get_expansion_status_summary()
        
        # Add system events (auto-collapses, etc.)
        payload["system_events"] = node_manager.get_system_events()
        
        # Calculate payload size
        payload_size = len(json.dumps(payload, default=str).encode('utf-8'))
        payload["payload_stats"] = {
            "size_bytes": payload_size,
            "size_kb": payload_size / 1024,
            "expanded_nodes_count": len(expanded_nodes),
            "collapsed_nodes_count": len(collapsed_node_summaries),
            "total_nodes": len(all_node_paths),
            "bot_identity": {"fid": bot_fid, "username": bot_username},
        }
        
        return payload

    def estimate_payload_size(
        self,
        world_state_data: WorldStateData,
        config: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Estimate the size of a full payload in bytes.
        
        This provides a heuristic estimate without building the full payload,
        useful for deciding between full and node-based processing strategies.
        
        Args:
            world_state_data: The world state data to estimate
            config: Configuration options (currently unused but reserved)
        
        Returns:
            Estimated payload size in bytes
        """
        try:
            metrics = world_state_data.get_state_metrics()
            
            # Use heuristic calculations based on typical data sizes
            estimated_size = (
                metrics["channel_count"] * 1500 +       # ~1.5KB per channel
                metrics["total_messages"] * 800 +       # ~0.8KB per message  
                metrics["action_history_count"] * 500 + # ~0.5KB per action
                metrics["thread_count"] * 300 +         # ~0.3KB per thread
                len(world_state_data.generated_media_library) * 200 +  # ~0.2KB per media item
                5000  # 5KB base overhead
            )
            
            return int(estimated_size)
            
        except Exception as e:
            logger.error(f"Error estimating payload size: {e}")
            # Return conservative estimate if calculation fails
            return 50000  # 50KB fallback

    def _get_node_paths_from_world_state(self, world_state_data: WorldStateData) -> List[str]:
        """
        Extract all available node paths from the world state data.
        
        Args:
            world_state_data: The world state to extract paths from
            
        Returns:
            List of node paths that can be expanded/collapsed
        """
        paths = []
        
        # Channel nodes
        for channel_id, channel in world_state_data.channels.items():
            paths.append(f"channels.{channel.type}.{channel_id}")
        
        # Farcaster feed nodes (always available if Farcaster is active)
        has_farcaster = any(ch.type == "farcaster" for ch in world_state_data.channels.values())
        if has_farcaster:
            paths.extend([
                "farcaster.feeds.home",
                "farcaster.feeds.notifications",
                "farcaster.feeds.trending"
            ])
        
        # Enhanced user nodes with cached data
        user_fids = set()
        user_usernames = set()
        
        for channel in world_state_data.channels.values():
            for msg in channel.recent_messages[-10:]:  # Recent users
                if msg.sender_fid:
                    user_fids.add(msg.sender_fid)
                if msg.sender_username:
                    user_usernames.add(msg.sender_username)
        
        # Add users from enhanced user tracking
        for fid in world_state_data.farcaster_users.keys():
            user_fids.add(fid)
        
        for user_id in world_state_data.matrix_users.keys():
            user_usernames.add(user_id)
        
        # Create user node paths with enhanced data
        for fid in user_fids:
            base_path = f"users.farcaster.{fid}"
            paths.append(base_path)
            
            # Add sub-nodes for cached data
            if fid in world_state_data.farcaster_users:
                user = world_state_data.farcaster_users[fid]
                if user.timeline_cache:
                    paths.append(f"{base_path}.timeline_cache")
                if user.sentiment:
                    paths.append(f"{base_path}.sentiment")
                if user.memory_entries:
                    paths.append(f"{base_path}.memories")
        
        for username in user_usernames:
            base_path = f"users.matrix.{username}"
            paths.append(base_path)
            
            # Add sub-nodes for enhanced Matrix user data
            if username in world_state_data.matrix_users:
                user = world_state_data.matrix_users[username]
                if user.sentiment:
                    paths.append(f"{base_path}.sentiment")
                if user.memory_entries:
                    paths.append(f"{base_path}.memories")
        
        # Optimized tool cache nodes - only include if substantial data exists
        if world_state_data.tool_cache and len(world_state_data.tool_cache) > 1:
            paths.append("tools.cache")
            # Only add specific tool nodes for frequently used tools
            tool_counts = {}
            for cache_key in world_state_data.tool_cache.keys():
                tool_name = cache_key.split(":")[0] if ":" in cache_key else cache_key
                tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1
            
            # Only include tools with multiple cached results
            for tool_name, count in tool_counts.items():
                if count > 1:  # Only include if multiple cached results
                    paths.append(f"tools.cache.{tool_name}")
        
        # Optimized search cache nodes - limit to recent searches
        if world_state_data.search_cache and len(world_state_data.search_cache) > 0:
            paths.append("farcaster.search_cache")
            # Only include recent search hashes (limit to 3 most recent)
            recent_searches = sorted(
                world_state_data.search_cache.items(),
                key=lambda x: x[1].get("timestamp", 0),
                reverse=True
            )[:3]
            for query_hash, _ in recent_searches:
                paths.append(f"farcaster.search_cache.{query_hash}")
        
        # Optimized memory bank nodes - only include platforms with significant memories
        if world_state_data.user_memory_bank:
            platform_memory_counts = {}
            for user_platform_id, memories in world_state_data.user_memory_bank.items():
                platform = user_platform_id.split(":")[0] if ":" in user_platform_id else "unknown"
                platform_memory_counts[platform] = platform_memory_counts.get(platform, 0) + len(memories)
            
            # Only include memory bank if there are substantial memories
            if sum(platform_memory_counts.values()) > 5:
                paths.append("memory_bank")
                for platform, count in platform_memory_counts.items():
                    if count > 2:  # Only include platforms with multiple memories
                        paths.append(f"memory_bank.{platform}")
        
        # Optimized thread nodes - limit to active threads only
        if world_state_data.threads:
            active_threads = []
            current_time = time.time()
            for thread_id, msgs in world_state_data.threads.items():
                if msgs and msgs[-1].timestamp > (current_time - 7200):  # Active in last 2 hours
                    active_threads.append(thread_id)
            
            # Only include recent active threads (limit to 3)
            for thread_id in active_threads[:3]:
                paths.append(f"threads.farcaster.{thread_id}")
        
        # Essential system nodes only
        paths.extend([
            "system.rate_limits", 
            "system.status"
        ])
        
        # Only include notifications if there are pending invites
        if world_state_data.pending_matrix_invites:
            paths.append("system.notifications")
        
        # Only include action history node for node system
        paths.append("system.action_history")
        
        return paths

    def _get_node_data_by_path(self, world_state_data: WorldStateData, node_path: str) -> Any:
        """
        Get the actual data for a specific node path.
        
        Args:
            world_state_data: The world state to extract data from
            node_path: The path to the node (e.g., "channels.matrix.!room_id")
        
        Returns:
            The data for that node, or None if not found
        """
        try:
            path_parts = node_path.split(".")
            
            if len(path_parts) < 2:
                return None
            
            if path_parts[0] == "channels" and len(path_parts) >= 3:
                channel_type, channel_id = path_parts[1], path_parts[2]
                channel = world_state_data.channels.get(channel_id)
                if channel and channel.type == channel_type:
                    return {
                        "id": channel.id,
                        "name": channel.name[:30] + "..." if len(channel.name) > 30 else channel.name,
                        "type": channel.type,
                        "status": channel.status,
                        "recent_messages": [
                            {
                                "id": msg.id,
                                "content": msg.content[:100] + "..." if len(msg.content) > 100 else msg.content,
                                "sender": msg.sender_username or msg.sender,
                                "timestamp": msg.timestamp,
                                "has_images": bool(getattr(msg, 'image_urls', []))
                            }
                            for msg in channel.recent_messages[-5:]  # Reduced from 10 to 5
                        ],
                        "msg_count": len(channel.recent_messages),
                        "last_activity": channel.recent_messages[-1].timestamp if channel.recent_messages else channel.last_checked
                    }
            
            elif path_parts[0] == "users" and len(path_parts) >= 3:
                user_type, user_id = path_parts[1], path_parts[2]
                
                # Handle enhanced user data with sub-nodes
                if user_type == "farcaster":
                    farcaster_user = world_state_data.farcaster_users.get(user_id)
                    if farcaster_user:
                        # Check for sub-node requests
                        if len(path_parts) == 4:
                            sub_node = path_parts[3]
                            if sub_node == "timeline_cache" and farcaster_user.timeline_cache:
                                return farcaster_user.timeline_cache
                            elif sub_node == "sentiment" and farcaster_user.sentiment:
                                return asdict(farcaster_user.sentiment)
                            elif sub_node == "memories" and farcaster_user.memory_entries:
                                return [asdict(memory) for memory in farcaster_user.memory_entries[-5:]]
                        
                        # Return compact user data
                        user_data = {
                            "fid": farcaster_user.fid,
                            "username": farcaster_user.username,
                            "display_name": farcaster_user.display_name,
                            "follower_count": farcaster_user.follower_count,
                            "power_badge": farcaster_user.power_badge
                        }
                        # Truncate bio for display
                        if farcaster_user.bio and len(farcaster_user.bio) > 50:
                            user_data["bio"] = farcaster_user.bio[:50] + "..."
                        elif farcaster_user.bio:
                            user_data["bio"] = farcaster_user.bio
                        return user_data
                    else:
                        # Fallback - compact extraction from messages
                        user_info = {"type": user_type, "id": user_id}
                        for channel in world_state_data.channels.values():
                            for msg in channel.recent_messages[-3:]:  # Reduced from 5 to 3
                                if str(msg.sender_fid) == user_id:
                                    bio = msg.sender_bio
                                    if bio and len(bio) > 50:
                                        bio = bio[:50] + "..."
                                    user_info.update({
                                        "username": msg.sender_username,
                                        "display_name": msg.sender_display_name,
                                        "fid": msg.sender_fid,
                                        "follower_count": msg.sender_follower_count,
                                        "bio": bio if bio else None
                                    })
                                    break
                        return user_info
                
                elif user_type == "matrix":
                    matrix_user = world_state_data.matrix_users.get(user_id)
                    if matrix_user:
                        # Check for sub-node requests
                        if len(path_parts) == 4:
                            sub_node = path_parts[3]
                            if sub_node == "sentiment" and matrix_user.sentiment:
                                return asdict(matrix_user.sentiment)
                            elif sub_node == "memories" and matrix_user.memory_entries:
                                return [asdict(memory) for memory in matrix_user.memory_entries[-3:]]  # Reduced from 5 to 3
                        
                        # Return compact user info
                        return {
                            "user_id": matrix_user.user_id,
                            "display_name": matrix_user.display_name,
                            "avatar_url": matrix_user.avatar_url
                        }
                    else:
                        # Fallback - compact extraction from messages
                        user_info = {"type": user_type, "id": user_id}
                        for channel in world_state_data.channels.values():
                            for msg in channel.recent_messages[-3:]:  # Reduced from 5 to 3
                                if msg.sender_username == user_id:
                                    user_info.update({
                                        "username": msg.sender_username,
                                        "display_name": msg.sender_display_name
                                    })
                                    break
                        return user_info
            
            elif path_parts[0] == "tools" and len(path_parts) >= 2:
                if path_parts[1] == "cache":
                    if len(path_parts) == 2:
                        # Return compact overview of cached tools
                        tool_summary = {}
                        for cache_key, cache_data in list(world_state_data.tool_cache.items())[:10]:  # Limit to 10 entries
                            tool_name = cache_key.split(":")[0] if ":" in cache_key else cache_key
                            if tool_name not in tool_summary:
                                tool_summary[tool_name] = {
                                    "count": 0,
                                    "most_recent": 0
                                }
                            tool_summary[tool_name]["count"] += 1
                            tool_summary[tool_name]["most_recent"] = max(
                                tool_summary[tool_name]["most_recent"],
                                cache_data.get("timestamp", 0)
                            )
                        return {
                            "cached_tools": tool_summary,
                            "total_entries": len(world_state_data.tool_cache)
                        }
                    elif len(path_parts) == 3:
                        # Return compact cached results for specific tool
                        tool_name = path_parts[2]
                        tool_results = {}
                        count = 0
                        for cache_key, cache_data in world_state_data.tool_cache.items():
                            if cache_key.startswith(f"{tool_name}:") and count < 3:  # Limit to 3 results
                                # Return only essential cache data
                                tool_results[cache_key] = {
                                    "timestamp": cache_data.get("timestamp"),
                                    "result_type": cache_data.get("result_type"),
                                    "size": len(str(cache_data)) if cache_data else 0
                                }
                                count += 1
                        return {
                            "tool_name": tool_name,
                            "cached_results": tool_results,
                            "total_cached": count
                        }
            
            elif path_parts[0] == "memory_bank":
                if len(path_parts) == 1:
                    # Return overview of memory bank
                    memory_stats = {}
                    for user_platform_id, memories in world_state_data.user_memory_bank.items():
                        platform = user_platform_id.split(":")[0] if ":" in user_platform_id else "unknown"
                        if platform not in memory_stats:
                            memory_stats[platform] = {"users": 0, "total_memories": 0}
                        memory_stats[platform]["users"] += 1
                        memory_stats[platform]["total_memories"] += len(memories)
                    return {
                        "platform_breakdown": memory_stats,
                        "total_users_with_memories": len(world_state_data.user_memory_bank)
                    }
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
                                for mem in memories[-3:]  # Recent memories
                            ]
                    return {
                        "platform": platform,
                        "user_memories": platform_memories
                    }
            
            elif path_parts[0] == "farcaster" and len(path_parts) >= 2:
                if path_parts[1] == "search_cache":
                    if len(path_parts) == 2:
                        # Return overview of search cache
                        search_overview = {}
                        for query_hash, search_data in world_state_data.search_cache.items():
                            search_overview[query_hash] = {
                                "query": search_data.get("query", "Unknown"),
                                "channel_id": search_data.get("channel_id"),
                                "result_count": search_data.get("result_count", 0),
                                "timestamp": search_data.get("timestamp", 0)
                            }
                        return {
                            "cached_searches": search_overview,
                            "total_searches": len(world_state_data.search_cache)
                        }
                    elif len(path_parts) == 3:
                        # Return specific search results
                        query_hash = path_parts[2]
                        search_data = world_state_data.search_cache.get(query_hash)
                        if search_data:
                            return search_data
                        return {"error": f"Search cache not found for hash: {query_hash}"}
                
                # Handle farcaster.feeds.* nodes
                elif len(path_parts) >= 3 and path_parts[1] == "feeds":
                    feed_type = path_parts[2]
                    
                    if feed_type == "home":
                        # Aggregate recent activity from all Farcaster channels
                        home_messages = []
                        for channel in world_state_data.channels.values():
                            if channel.type == "farcaster" and "home" in channel.id:
                                home_messages.extend(channel.recent_messages[-5:])
                        
                        # Sort by timestamp and take most recent
                        home_messages.sort(key=lambda x: x.timestamp, reverse=True)
                        return {
                            "feed_type": "home",
                            "recent_activity": [msg.to_ai_summary_dict() for msg in home_messages[:10]],
                            "activity_summary": f"{len(home_messages)} recent home feed messages"
                        }
                    
                    elif feed_type == "notifications":
                        # Find notification/mention related messages
                        notification_messages = []
                        for channel in world_state_data.channels.values():
                            if channel.type == "farcaster" and ("notification" in channel.id or "mention" in channel.id):
                                notification_messages.extend(channel.recent_messages[-5:])
                        
                        notification_messages.sort(key=lambda x: x.timestamp, reverse=True)
                        return {
                            "feed_type": "notifications",
                            "recent_mentions": [msg.to_ai_summary_dict() for msg in notification_messages[:10]],
                            "notification_summary": f"{len(notification_messages)} recent notifications/mentions"
                        }
                    
                    elif feed_type == "trending":
                        # Placeholder for trending feed data
                        return {
                            "feed_type": "trending",
                            "status": "Available for expansion via get_trending_casts tool",
                            "note": "Use get_trending_casts to fetch current trending content"
                        }
            
            elif path_parts[0] == "threads" and len(path_parts) >= 3:
                thread_type, thread_id = path_parts[1], path_parts[2]
                thread_messages = world_state_data.threads.get(thread_id, [])
                return {
                    "thread_id": thread_id,
                    "type": thread_type,
                    "messages": [asdict(msg) for msg in thread_messages[-5:]]  # Recent thread messages
                }
            
            elif path_parts[0] == "system":
                if len(path_parts) >= 2:
                    system_component = path_parts[1]
                    
                    if system_component == "notifications":
                        return {"pending_matrix_invites": world_state_data.pending_matrix_invites}
                    elif system_component == "rate_limits":
                        return world_state_data.rate_limits
                    elif system_component == "status":
                        return world_state_data.system_status
                    elif system_component == "action_history":
                        return [asdict(action) for action in world_state_data.action_history[-10:]]
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting data for node path {node_path}: {e}")
            return None
