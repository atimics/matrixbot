#!/usr/bin/env python3
"""
Refactored Payload Builder

This module is responsible for constructing AI payloads from WorldStateData.
Refactored to delegate specific responsibilities to specialized modules.

The PayloadBuilder now focuses on:
1. Orchestrating payload construction
2. Integrating data from specialized handlers
3. Applying optimization strategies
4. Managing payload size and format

Specialized modules handle:
- Node path generation (NodePathGenerator)
- Node data retrieval (NodeDataHandlers)
- Bot activity context (BotActivityContext)
- Payload optimization (PayloadOptimizer)
"""

import json
import logging
import time
from dataclasses import asdict
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from chatbot.config import settings
from .structures import Channel, WorldStateData
from .node_path_generator import NodePathGenerator
from .node_data_handlers import NodeDataHandlers
from .payload_optimizer import PayloadOptimizer
from .bot_activity_context import BotActivityContextBuilder

if TYPE_CHECKING:
    from ..node_system.node_manager import NodeManager

logger = logging.getLogger(__name__)


class PayloadBuilder:
    """
    Constructs different types of AI payloads from WorldStateData.

    This refactored version delegates specialized tasks to focused modules
    while maintaining the same interface for backward compatibility.
    """

    def __init__(
        self,
        world_state_manager: Optional[Any] = None,
        node_manager: Optional["NodeManager"] = None,
    ):
        """
        Initialize PayloadBuilder with specialized handlers.

        Args:
            world_state_manager: Optional WorldStateManager instance.
            node_manager: Optional NodeManager for node-based payloads.
        """
        self.world_state_manager = world_state_manager
        self.node_manager = node_manager
        self.logger = logging.getLogger(__name__)
        
        # Initialize specialized handlers
        self.node_path_generator = NodePathGenerator()
        self.node_data_handlers = NodeDataHandlers()
        self.payload_optimizer = PayloadOptimizer()
        self.bot_activity_builder = BotActivityContextBuilder()
        
        # Last action context for AI self-awareness (addresses repetitive loops)
        self.last_action_result: Optional[Dict[str, Any]] = None
    
    def set_last_action_result(self, action_result: Dict[str, Any]) -> None:
        """
        Set the last action result for AI self-awareness.
        
        Args:
            action_result: Dictionary containing action details
        """
        self.last_action_result = action_result
        self.bot_activity_builder.set_last_action_result(action_result)
        logger.debug(f"Set last action result: {action_result.get('action_type')} -> "
                    f"{'SUCCESS' if action_result.get('success') else 'FAILED'}")

    def build_full_payload(
        self,
        world_state_data: WorldStateData,
        primary_channel_id: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Build a traditional full payload with intelligent filtering.

        Args:
            world_state_data: The world state data to convert.
            primary_channel_id: Primary channel being processed.
            config: Configuration dict with payload options.

        Returns:
            Dictionary with complete world state data for AI consumption.
        """
        cfg = config or {}
        optimize_for_size = cfg.get("optimize_for_size", False)
        
        # Build core payload structure
        payload = {
            "current_processing_channel_id": primary_channel_id,
            "system_status": {
                "timestamp": world_state_data.last_update,
                "rate_limits": world_state_data.rate_limits,
            },
            "channels": self._build_channels_payload(world_state_data, optimize_for_size),
            "action_history": self._build_action_history_payload(world_state_data, 20, optimize=optimize_for_size),
            "thread_context": self._build_thread_context(world_state_data, primary_channel_id),
            "immediate_action_context": self._build_immediate_action_context(),
        }

        # Add detailed data if not optimizing for size
        if not optimize_for_size:
            payload.update(self._get_full_detail_data(world_state_data))

        # Apply optimizations
        if optimize_for_size:
            payload = self.payload_optimizer.optimize_payload_size(payload)

        return payload

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
        
        # Generate all possible node paths
        all_node_paths = self.node_path_generator.get_node_paths_from_world_state(world_state_data)
        
        # Separate expanded and collapsed nodes
        expanded_nodes = {}
        collapsed_node_summaries = {}
        
        logger.debug(f"Processing {len(all_node_paths)} node paths for payload construction")

        for node_path in all_node_paths:
            metadata = node_manager.get_node_metadata(node_path)
            
            # DEBUG: Log detailed expansion state for key nodes
            if "channels/matrix/" in node_path or "farcaster/feeds/" in node_path:
                logger.info(f"🔍 PAYLOAD BUILD: {node_path} -> is_expanded={metadata.is_expanded}, is_pinned={metadata.is_pinned}, last_expanded_ts={metadata.last_expanded_ts}")
            
            # Use the corrected path parsing and data retrieval logic
            path_parts = self.node_path_generator.parse_node_path(node_path)
            if not path_parts:
                continue

            # Use the NodeDataHandlers interface to get node data
            node_data = self.node_data_handlers.get_node_data_by_path(
                world_state_data, 
                node_path, 
                expanded=metadata.is_expanded
            )

            if metadata.is_expanded:
                if node_data:
                    expanded_nodes[node_path] = node_data
                    logger.debug(f"EXPANDED node {node_path}: {type(node_data)} with keys {list(node_data.keys()) if isinstance(node_data, dict) else 'not dict'}")
            else:
                if node_data:
                    # Check if this is a channel with messages
                    if isinstance(node_data, dict) and "recent_messages" in node_data:
                        logger.debug(f"COLLAPSED channel {node_path}: {len(node_data['recent_messages'])} messages being converted to summary")
                        logger.debug(f"  Messages preview: {[msg.get('content', 'No content')[:50] for msg in node_data['recent_messages'][:2]]}")
                    
                    collapsed_node_summaries[node_path] = {
                        "summary": node_manager.get_node_metadata(node_path).ai_summary or f"Summary for {node_path} not yet generated.",
                        "node_path_for_tools": node_path
                    }
                    logger.debug(f"COLLAPSED node {node_path}: converted to summary only")

        logger.debug(f"Final payload structure: {len(expanded_nodes)} expanded, {len(collapsed_node_summaries)} collapsed")
        
        # Count total messages in payload
        total_messages_in_payload = 0
        for node_data in expanded_nodes.values():
            if isinstance(node_data, dict) and "recent_messages" in node_data:
                total_messages_in_payload += len(node_data["recent_messages"])
        
        logger.debug(f"Total messages included in expanded nodes: {total_messages_in_payload}")
        if total_messages_in_payload == 0:
            logger.warning("NO MESSAGES FOUND IN EXPANDED NODES - AI will not see any messages!")
            
            # FAILSAFE: Force expansion of channels with messages to ensure AI has context
            logger.warning("ACTIVATING FAILSAFE: Forcing expansion of channels with messages")
            
            # Find channels with messages and force expand them
            channels_with_messages = []
            for node_path in all_node_paths:
                if node_path.startswith("channels."):
                    # Get channel data to check for messages
                    node_data = self.node_data_handlers.get_node_data_by_path(
                        world_state_data, node_path, expanded=True  # Force expanded to see messages
                    )
                    if (isinstance(node_data, dict) and 
                        "recent_messages" in node_data and 
                        len(node_data["recent_messages"]) > 0):
                        channels_with_messages.append((node_path, len(node_data["recent_messages"])))
            
            if channels_with_messages:
                # Sort by message count and expand the top channels
                channels_with_messages.sort(key=lambda x: x[1], reverse=True)
                
                for node_path, msg_count in channels_with_messages[:3]:  # Expand top 3 channels with messages
                    logger.warning(f"FAILSAFE: Force expanding {node_path} ({msg_count} messages)")
                    node_manager.expand_node(node_path)
                    
                    # Add to expanded_nodes immediately
                    node_data = self.node_data_handlers.get_node_data_by_path(
                        world_state_data, node_path, expanded=True
                    )
                    if node_data:
                        expanded_nodes[node_path] = node_data
                        if isinstance(node_data, dict) and "recent_messages" in node_data:
                            total_messages_in_payload += len(node_data["recent_messages"])
                            logger.warning(f"FAILSAFE: Added {len(node_data['recent_messages'])} messages from {node_path}")
                        
                        # Remove from collapsed summaries if it was there
                        if node_path in collapsed_node_summaries:
                            del collapsed_node_summaries[node_path]
                
                logger.warning(f"FAILSAFE COMPLETE: Now have {total_messages_in_payload} messages in expanded nodes")
            else:
                logger.error("FAILSAFE FAILED: No channels with messages found to expand!")

        # Build final payload
        payload = {
            "current_processing_channel_id": primary_channel_id,
            "system_status": {
                "timestamp": world_state_data.last_update,
                "rate_limits": world_state_data.rate_limits,
            },
            "immediate_action_context": self._build_immediate_action_context(),
            "available_channels": self._build_available_channels_summary(world_state_data, node_manager),
            "expanded_nodes": expanded_nodes,
            "collapsed_node_summaries": collapsed_node_summaries,
            "expansion_status": node_manager.get_expansion_status_summary(),
            "system_events": node_manager.get_system_events(),
        }

        # Add payload statistics
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
        Estimate the size of a full payload without building it.

        Args:
            world_state_data: The world state data to estimate for.
            config: Optional configuration for estimation.

        Returns:
            Estimated payload size in bytes.
        """
        cfg = config or {}
        
        # Get basic metrics
        metrics = world_state_data.get_state_metrics()
        
        # Base payload overhead
        base_size = 2000  # JSON structure overhead
        
        # Channel data estimation
        channel_size = metrics["total_messages"] * 300  # ~300 bytes per message
        
        # Action history estimation
        action_size = metrics["action_history_count"] * 200  # ~200 bytes per action
        
        # Thread data estimation
        thread_size = metrics["thread_count"] * 500  # ~500 bytes per thread
        
        # Additional data estimation
        media_size = metrics.get("media_library_size", 0) * 150  # ~150 bytes per media item
        
        estimated_size = base_size + channel_size + action_size + thread_size + media_size
        
        # Apply optimization factor if enabled
        if cfg.get("optimize_for_size", False):
            estimated_size = int(estimated_size * 0.6)  # ~40% reduction with optimization
        
        return estimated_size

    # === Private Helper Methods ===

    def _build_immediate_action_context(self) -> Dict[str, Any]:
        """
        Build immediate action context to prevent repetitive AI behavior.
        """
        if not self.last_action_result:
            return {
                "status": "no_recent_action",
                "guidance": "This is a fresh analysis - proceed with appropriate actions based on current context."
            }
        
        action_type = self.last_action_result.get("action_type", "unknown")
        success = self.last_action_result.get("success", False)
        timestamp = self.last_action_result.get("timestamp", 0)
        time_since = time.time() - timestamp
        
        context = {
            "last_action": {
                "action_type": action_type,
                "success": success,
                "time_since_seconds": round(time_since, 1),
                "parameters": self.last_action_result.get("parameters", {}),
                "result_summary": str(self.last_action_result.get("result", ""))[:200]
            },
            "guidance": self._generate_action_specific_guidance(action_type, success, self.last_action_result)
        }
        
        return context

    def _generate_action_specific_guidance(self, action_type: str, success: bool, action_result: Dict[str, Any]) -> str:
        """Generate specific guidance based on the last action taken."""
        if not success:
            return f"Previous {action_type} action failed. Consider alternative approaches or investigate the error before retrying."
        
        if action_type in ["expand_node", "get_trending_casts", "get_channel_feed"]:
            return f"Just completed {action_type}. Review the results before taking similar actions. Consider acting on the new information instead of repeating data gathering."
        
        if action_type in ["send_message", "send_farcaster_reply", "post_to_farcaster"]:
            return f"Just sent a message via {action_type}. Wait for user responses before sending additional messages to avoid overwhelming the conversation."
        
        if action_type in ["analyze_user_sentiment", "get_user_profile"]:
            return f"Just analyzed user data via {action_type}. Use this information to inform responses rather than repeating the analysis."
        
        return f"Recently completed {action_type} successfully. Build on these results rather than repeating the same action."

    def _build_action_history_payload(self, world_state_data: WorldStateData, limit: int = 20, optimize: bool = False) -> List[Dict[str, Any]]:
        """Build action history for payload with optional optimization."""
        recent_actions = world_state_data.action_history[-limit:] if world_state_data.action_history else []
        
        if optimize:
            return [
                {
                    "action_type": action.action_type,
                    "timestamp": action.timestamp,
                    "success": "success" in action.result.lower() if action.result else False
                }
                for action in recent_actions
            ]
        else:
            return [asdict(action) for action in recent_actions]

    def _build_thread_context(self, world_state_data: WorldStateData, primary_channel_id: Optional[str]) -> Dict[str, Any]:
        """Build thread context for the primary channel."""
        if not primary_channel_id:
            return {}
        
        # Find active threads related to the primary channel
        thread_context = {
            "active_threads": [],
            "thread_count": len(world_state_data.threads)
        }
        
        # Add recent thread activity
        for thread_id, messages in world_state_data.threads.items():
            if messages and len(messages) > 1:  # Only include threads with multiple messages
                thread_context["active_threads"].append({
                    "thread_id": thread_id,
                    "message_count": len(messages),
                    "last_activity": messages[-1].timestamp if messages else 0,
                    "recent_messages": [msg.to_ai_summary_dict() for msg in messages[-3:]]
                })
        
        # Sort by last activity
        thread_context["active_threads"].sort(key=lambda t: t["last_activity"], reverse=True)
        thread_context["active_threads"] = thread_context["active_threads"][:5]  # Top 5 most recent
        
        return thread_context

    def _build_channels_payload(self, world_state_data: WorldStateData, optimize_for_size: bool) -> Dict[str, Any]:
        """Build channels payload with optional size optimization."""
        logger.debug(f"Building channels payload - optimize_for_size: {optimize_for_size}")
        logger.debug(f"Available platforms in world_state: {list(world_state_data.channels.keys())}")
        
        if optimize_for_size:
            compressed_payload = self.payload_optimizer.compress_channel_data(
                self._flatten_channels(world_state_data.channels), 
                max_messages_per_channel=5
            )
            logger.debug(f"Compressed payload structure: {list(compressed_payload.keys())}")
            return compressed_payload
        else:
            # Full channel data
            channels_payload = {}
            for platform, platform_channels in world_state_data.channels.items():
                logger.debug(f"Processing platform: {platform} with {len(platform_channels)} channels")
                channels_payload[platform] = {}
                for channel_id, channel in platform_channels.items():
                    messages_count = len(channel.recent_messages)
                    logger.debug(f"Channel {channel_id} ({platform}): {messages_count} recent messages")
                    if messages_count > 0:
                        logger.debug(f"  Latest message: {channel.recent_messages[-1].content[:100] if channel.recent_messages[-1].content else 'No content'}")
                    
                    channels_payload[platform][channel_id] = {
                        "id": channel.id,
                        "name": channel.name,
                        "type": channel.type,
                        "status": channel.status,
                        "member_count": len(getattr(channel, 'members', [])),
                        "recent_messages": [msg.to_ai_summary_dict() for msg in channel.recent_messages[-10:]]
                    }
            
            total_channels = sum(len(platform_channels) for platform_channels in channels_payload.values())
            total_messages = sum(
                len(channel_data["recent_messages"]) 
                for platform_data in channels_payload.values() 
                for channel_data in platform_data.values()
            )
            logger.debug(f"Final payload: {total_channels} channels, {total_messages} total messages")
            return channels_payload

    def _get_full_detail_data(self, world_state_data: WorldStateData) -> Dict[str, Any]:
        """Get full detail data for non-optimized payloads."""
        return {
            "generated_media_library": world_state_data.generated_media_library[-10:],
            "ecosystem_token_info": {
                "contract_address": world_state_data.ecosystem_token_contract,
                "token_metadata": asdict(world_state_data.token_metadata)
                if world_state_data.token_metadata
                else None,
                "monitored_holders_summary": self._summarize_token_holders_for_ai(
                    world_state_data.monitored_token_holders
                ),
            },
            "research_knowledge": {
                "available_topics": list(world_state_data.research_database.keys()),
                "topic_count": len(world_state_data.research_database),
                "note": "Use query_research tool to access detailed research information",
            },
        }

    def _build_available_channels_summary(self, world_state_data: WorldStateData, node_manager: "NodeManager") -> Dict[str, Any]:
        """Build a summary of all available channels for AI discovery."""
        available_channels = {
            "matrix": {},
            "farcaster": {},
            "summary": "Available channels the AI can expand for detailed content"
        }
        
        # Matrix channels
        if "matrix" in world_state_data.channels:
            for channel_id, channel in world_state_data.channels["matrix"].items():
                node_path = f"channels/{channel_id}"
                metadata = node_manager.get_node_metadata(node_path)
                
                available_channels["matrix"][channel_id] = {
                    "name": getattr(channel, 'name', channel_id),
                    "node_path": node_path,
                    "is_expanded": metadata.is_expanded,
                    "is_pinned": metadata.is_pinned,
                    "recent_message_count": len(getattr(channel, 'recent_messages', [])),
                    "last_activity": getattr(channel, 'recent_messages', [])[-1].timestamp if getattr(channel, 'recent_messages', []) else None
                }
        
        # Farcaster channels
        if "farcaster" in world_state_data.channels:
            for channel_id, channel in world_state_data.channels["farcaster"].items():
                node_path = f"channels/{channel_id}"
                metadata = node_manager.get_node_metadata(node_path)
                
                available_channels["farcaster"][channel_id] = {
                    "name": getattr(channel, 'name', channel_id),
                    "node_path": node_path,
                    "is_expanded": metadata.is_expanded,
                    "is_pinned": metadata.is_pinned,
                    "recent_message_count": len(getattr(channel, 'recent_messages', [])),
                    "last_activity": getattr(channel, 'recent_messages', [])[-1].timestamp if getattr(channel, 'recent_messages', []) else None
                }
        
        return available_channels

    def _summarize_token_holders_for_ai(self, monitored_holders: Dict) -> Dict[str, Any]:
        """Create an AI-optimized summary of token holders."""
        if not monitored_holders:
            return {
                "total_holders_monitored": 0,
                "recent_activity_summary": "No token holders currently monitored",
                "top_recent_casts": []
            }
        
        # Collect recent casts from all holders
        all_recent_casts = []
        active_holders = []
        
        for holder_fid, holder in monitored_holders.items():
            holder_summary = {
                "fid": holder.fid,
                "username": holder.username or f"FID_{holder.fid}",
                "display_name": holder.display_name,
                "recent_casts_count": len(holder.recent_casts),
                "last_activity": holder.last_activity_timestamp,
                "social_influence_score": holder.social_influence_score
            }
            
            if holder.token_holder_data:
                holder_summary["token_balance"] = holder.token_holder_data.balance
                holder_summary["rank"] = holder.token_holder_data.rank
            
            active_holders.append(holder_summary)
            
            # Collect recent casts
            for cast in holder.recent_casts[-3:]:
                cast_summary = {
                    "author": holder.username or f"FID_{holder.fid}",
                    "author_display_name": holder.display_name,
                    "content": cast.content[:150] + "..." if len(cast.content) > 150 else cast.content,
                    "timestamp": cast.timestamp,
                    "engagement": {
                        "likes": cast.metadata.get("reactions", {}).get("likes_count", 0) if cast.metadata else 0,
                        "recasts": cast.metadata.get("reactions", {}).get("recasts_count", 0) if cast.metadata else 0,
                        "replies": cast.metadata.get("replies_count", 0) if cast.metadata else 0
                    }
                }
                all_recent_casts.append(cast_summary)
        
        # Sort and return top casts
        all_recent_casts.sort(key=lambda x: x["timestamp"], reverse=True)
        active_holders.sort(key=lambda x: (x.get("social_influence_score", 0), x.get("last_activity", 0)), reverse=True)
        
        return {
            "total_holders_monitored": len(monitored_holders),
            "active_holders_summary": active_holders[:5],
            "recent_activity_summary": f"Monitoring {len(monitored_holders)} top token holders with {len(all_recent_casts)} recent casts",
            "top_recent_casts": all_recent_casts[:10],
            "last_updated": max([h.last_activity_timestamp or 0 for h in monitored_holders.values()]) if monitored_holders else 0
        }

    def _flatten_channels(self, channels_dict: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Flatten nested channels dict for compatibility."""
        flat = {}
        for platform_channels in channels_dict.values():
            if isinstance(platform_channels, dict):
                flat.update(platform_channels)
        return flat
