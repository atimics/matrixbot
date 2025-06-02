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
        Build a traditional full payload from world state data.
        
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
        # Set default config values
        if config is None:
            config = {}
        
        max_messages_per_channel = config.get("max_messages_per_channel", 10)
        max_action_history = config.get("max_action_history", 5)
        max_thread_messages = config.get("max_thread_messages", 5)
        max_other_channels = config.get("max_other_channels", 3)
        message_snippet_length = config.get("message_snippet_length", 75)
        include_detailed_user_info = config.get("include_detailed_user_info", True)
        bot_fid = config.get("bot_fid")
        bot_username = config.get("bot_username")

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
                # Full detail for priority channels
                messages_for_payload = [
                    msg.to_ai_summary_dict()
                    if not include_detailed_user_info
                    else asdict(msg)
                    for msg in all_messages[-max_messages_per_channel:]
                ]

                # Calculate timestamp range for the included messages
                truncated_messages = all_messages[-max_messages_per_channel:]
                timestamp_range = None
                if truncated_messages:
                    timestamp_range = {
                        "start": truncated_messages[0].timestamp,
                        "end": truncated_messages[-1].timestamp,
                        "span_hours": round(
                            (
                                truncated_messages[-1].timestamp
                                - truncated_messages[0].timestamp
                            )
                            / 3600,
                            2,
                        ),
                        "total_available_messages": len(all_messages),
                        "included_messages": len(truncated_messages),
                    }

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
                # Summary only for less active channels
                channels_payload[ch_id] = {
                    "id": ch_data.id,
                    "type": ch_data.type,
                    "name": ch_data.name,
                    "activity_summary": ch_data.get_activity_summary(),
                    "priority": "summary_only",
                }

        # Include all action history for AI context - the AI should see its own past actions
        # This provides better context for decision-making and prevents repetitive actions
        action_history_payload = [
            asdict(action) for action in world_state_data.action_history[-max_action_history:]
        ]

        # Handle threads with bot filtering - only include threads relevant to primary channel
        threads_payload = {}
        if primary_channel_id:
            # Look for threads that might be related to the primary channel
            for thread_id, msgs in world_state_data.threads.items():
                # Include thread if any message belongs to primary channel or references it
                relevant_thread = any(
                    msg.channel_id == primary_channel_id
                    or msg.reply_to
                    in [
                        m.id
                        for m in world_state_data.channels.get(
                            primary_channel_id, Channel("", "", "", [], 0)
                        ).recent_messages
                    ]
                    for msg in msgs
                )

                if relevant_thread:
                    # Include all thread messages including bot's own for conversation context
                    all_thread_msgs = msgs[-max_thread_messages:]

                    if all_thread_msgs:
                        thread_msgs_for_payload = [
                            msg.to_ai_summary_dict()
                            if not include_detailed_user_info
                            else asdict(msg)
                            for msg in all_thread_msgs
                        ]
                        threads_payload[thread_id] = thread_msgs_for_payload

        return {
            "current_processing_channel_id": primary_channel_id,
            "channels": channels_payload,
            "action_history": action_history_payload,
            "system_status": {**world_state_data.system_status, "rate_limits": world_state_data.rate_limits},
            "threads": threads_payload,
            "pending_matrix_invites": world_state_data.pending_matrix_invites,
            "recent_media_actions": world_state_data.get_recent_media_actions(),
            "generated_media_library": world_state_data.generated_media_library[-20:],  # Last 20 generated media items
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
        }

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
        
        # User nodes (from recent activity) 
        user_fids = set()
        user_usernames = set()
        
        for channel in world_state_data.channels.values():
            for msg in channel.recent_messages[-10:]:  # Recent users
                if msg.sender_fid:
                    user_fids.add(msg.sender_fid)
                if msg.sender_username:
                    user_usernames.add(msg.sender_username)
        
        for fid in user_fids:
            paths.append(f"users.farcaster.{fid}")
        
        for username in user_usernames:
            paths.append(f"users.matrix.{username}")
        
        # Thread nodes
        for thread_id in world_state_data.threads:
            paths.append(f"threads.farcaster.{thread_id}")
        
        # System nodes
        paths.extend([
            "system.notifications",
            "system.rate_limits", 
            "system.status",
            "system.action_history"
        ])
        
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
                        "name": channel.name,
                        "type": channel.type,
                        "status": channel.status,
                        "recent_messages": [
                            {
                                "id": msg.id,
                                "content": msg.content,
                                "sender": msg.sender,
                                "sender_username": msg.sender_username,
                                "timestamp": msg.timestamp,
                                "image_urls": getattr(msg, 'image_urls', [])
                            }
                            for msg in channel.recent_messages[-10:]  # Recent messages
                        ],
                        "last_checked": channel.last_checked
                    }
            
            elif path_parts[0] == "users" and len(path_parts) >= 3:
                user_type, user_id = path_parts[1], path_parts[2]
                # Extract user info from recent messages
                user_info = {"type": user_type, "id": user_id}
                
                # Collect user information from recent messages
                for channel in world_state_data.channels.values():
                    for msg in channel.recent_messages[-5:]:  # Recent messages
                        if user_type == "farcaster" and str(msg.sender_fid) == user_id:
                            # Compact user info for node data
                            bio = msg.sender_bio
                            if bio and len(bio) > 75:
                                bio = bio[:75] + "..."
                            
                            user_info.update({
                                "username": msg.sender_username,
                                "display_name": msg.sender_display_name,
                                "fid": msg.sender_fid,
                                "follower_count": msg.sender_follower_count,
                                "bio_snippet": bio if bio else None
                            })
                            break
                        elif user_type == "matrix" and msg.sender_username == user_id:
                            user_info.update({
                                "username": msg.sender_username,
                                "display_name": msg.sender_display_name
                            })
                            break
                
                return user_info
            
            elif path_parts[0] == "farcaster" and len(path_parts) >= 3:
                # Handle farcaster.feeds.* nodes
                if path_parts[1] == "feeds":
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
