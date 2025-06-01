"""
Enhanced WorldState Manager with JSON Observer Pattern

This module extends the existing WorldStateManager to support the JSON Observer 
and Interactive Executor pattern with expandable/collapsible nodes, LRU auto-collapse,
and AI-generated summaries.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Set

from chatbot.config import settings
from chatbot.core.node_manager import NodeManager
from chatbot.core.node_summary_service import NodeSummaryService
from chatbot.core.world_state import WorldStateManager

logger = logging.getLogger(__name__)


class EnhancedWorldStateManager(WorldStateManager):
    """
    Enhanced WorldStateManager with node expansion/collapse functionality.
    
    This extends the base WorldStateManager to provide:
    - Expandable/collapsible node management
    - LRU auto-collapse with pinning
    - AI-generated node summaries
    - Interactive node exploration for AI
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Initialize node management system
        self.node_manager = NodeManager(
            max_expanded_nodes=settings.MAX_EXPANDED_NODES,
            default_pinned_nodes=settings.DEFAULT_PINNED_NODES
        )
        
        # Initialize summary service (will be set by orchestrator)
        self.summary_service: Optional[NodeSummaryService] = None
        
        # Track which nodes need summary updates
        self._pending_summary_updates: Set[str] = set()
    
    def set_summary_service(self, summary_service: NodeSummaryService):
        """Set the summary service (called by orchestrator during initialization)."""
        self.summary_service = summary_service
    
    def get_node_paths_from_world_state(self) -> List[str]:
        """
        Extract all available node paths from the current world state.
        
        Returns:
            List of node paths that can be expanded/collapsed
        """
        paths = []
        
        # Channel nodes
        for channel_id in self.world_state.channels:
            channel_type = self.world_state.channels[channel_id].channel_type
            paths.append(f"channels.{channel_type}.{channel_id}")
        
        # User nodes (from recent activity)
        user_fids = set()
        user_usernames = set()
        
        for channel in self.world_state.channels.values():
            for msg in channel.recent_messages[-10:]:  # Recent users
                if msg.sender_fid:
                    user_fids.add(msg.sender_fid)
                if msg.sender_username:
                    user_usernames.add(msg.sender_username)
        
        for fid in user_fids:
            paths.append(f"users.farcaster.{fid}")
        
        for username in user_usernames:
            paths.append(f"users.matrix.{username}")
        
        # Thread nodes (from active threads)
        for thread_id in self.world_state.active_threads:
            paths.append(f"threads.farcaster.{thread_id}")
        
        # System nodes
        paths.extend([
            "system.notifications",
            "system.rate_limits",
            "system.status",
            "system.action_history"
        ])
        
        return paths
    
    def get_node_data_by_path(self, node_path: str) -> Any:
        """
        Get the actual data for a specific node path.
        
        Args:
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
                channel = self.world_state.channels.get(channel_id)
                if channel and channel.channel_type == channel_type:
                    return {
                        "id": channel.id,
                        "name": channel.name,
                        "channel_type": channel.channel_type,
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
                            for msg in channel.recent_messages[-settings.AI_CONVERSATION_HISTORY_LENGTH:]
                        ],
                        "last_activity": channel.last_activity_timestamp
                    }
            
            elif path_parts[0] == "users" and len(path_parts) >= 3:
                user_type, user_id = path_parts[1], path_parts[2]
                # Get user data from world state
                user_info = None
                
                if user_type == "farcaster":
                    user_info = self.world_state.farcaster_users.get(int(user_id))
                elif user_type == "matrix":
                    # For Matrix users, we'd need to collect from message history
                    # This is a simplified version
                    user_info = {"username": user_id, "type": "matrix"}
                
                return user_info
            
            elif path_parts[0] == "threads" and len(path_parts) >= 3:
                thread_type, thread_id = path_parts[1], path_parts[2]
                thread = self.world_state.active_threads.get(thread_id)
                return thread.__dict__ if thread else None
            
            elif path_parts[0] == "system":
                if len(path_parts) >= 2:
                    system_component = path_parts[1]
                    
                    if system_component == "notifications":
                        return self.world_state.pending_notifications
                    elif system_component == "rate_limits":
                        return self.world_state.rate_limits
                    elif system_component == "status":
                        return {
                            "current_cycle_id": getattr(self.world_state, 'current_cycle_id', None),
                            "last_update": getattr(self.world_state, 'last_update_timestamp', None)
                        }
                    elif system_component == "action_history":
                        return [
                            {
                                "action_type": action.action_type,
                                "parameters": action.parameters,
                                "result": action.result,
                                "timestamp": action.timestamp
                            }
                            for action in self.world_state.action_history[-settings.AI_ACTION_HISTORY_LENGTH:]
                        ]
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting data for node path {node_path}: {e}")
            return None
    
    async def update_summaries_for_changed_nodes(self) -> Dict[str, str]:
        """
        Update AI summaries for nodes that need it.
        
        Returns:
            Dictionary mapping node_path to new summary
        """
        if not self.summary_service:
            logger.warning("No summary service available for generating summaries")
            return {}
        
        all_node_paths = self.get_node_paths_from_world_state()
        
        # Find nodes that need summaries
        nodes_needing_summary = []
        
        for node_path in all_node_paths:
            node_data = self.get_node_data_by_path(node_path)
            if node_data is None:
                continue
            
            # Check if data has changed or summary is missing
            if self.node_manager.is_data_changed(node_path, node_data):
                metadata = self.node_manager.get_node_metadata(node_path)
                
                # Only generate summaries for collapsed nodes
                if not metadata.is_expanded:
                    path_parts = node_path.split(".")
                    node_type = path_parts[1] if len(path_parts) >= 2 else path_parts[0] if path_parts else "unknown"
                    nodes_needing_summary.append({
                        "node_path": node_path,
                        "node_data": node_data,
                        "node_type": node_type
                    })
        
        if not nodes_needing_summary:
            return {}
        
        logger.info(f"Generating summaries for {len(nodes_needing_summary)} nodes")
        
        # Generate summaries
        try:
            summaries = await self.summary_service.generate_multiple_summaries(nodes_needing_summary)
            
            # Update node metadata with new summaries
            for node_path, summary in summaries.items():
                self.node_manager.update_node_summary(node_path, summary)
            
            return summaries
            
        except Exception as e:
            logger.error(f"Failed to generate summaries: {e}")
            return {}
    
    def get_ai_optimized_payload_with_nodes(
        self, 
        primary_channel_id: str, 
        bot_fid: Optional[int] = None, 
        bot_username: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get AI-optimized payload using the node expansion system.
        
        This replaces the traditional get_ai_optimized_payload() with a view
        that shows expanded nodes in detail and collapsed nodes as summaries.
        """
        
        # Start with system status and core info
        payload = {
            "current_processing_channel_id": primary_channel_id,
            "system_status": {
                "timestamp": self.world_state.last_update_timestamp,
                "rate_limits": self.world_state.rate_limits
            }
        }
        
        # Get all available node paths
        all_node_paths = self.get_node_paths_from_world_state()
        
        # Separate expanded and collapsed nodes
        expanded_nodes = {}
        collapsed_node_summaries = {}
        
        for node_path in all_node_paths:
            metadata = self.node_manager.get_node_metadata(node_path)
            node_data = self.get_node_data_by_path(node_path)
            
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
                data_changed = self.node_manager.is_data_changed(node_path, node_data)
                
                collapsed_node_summaries[node_path] = {
                    "summary": summary,
                    "data_changed": data_changed,
                    "last_summary_update": metadata.last_summary_update_ts
                }
        
        payload["expanded_nodes"] = expanded_nodes
        payload["collapsed_node_summaries"] = collapsed_node_summaries
        
        # Add expansion status info
        payload["expansion_status"] = self.node_manager.get_expansion_status_summary()
        
        # Add system events (auto-collapses, etc.)
        payload["system_events"] = self.node_manager.get_system_events()
        
        # Calculate payload size
        import json
        payload_size = len(json.dumps(payload, default=str).encode('utf-8'))
        payload["payload_stats"] = {
            "size_bytes": payload_size,
            "size_kb": payload_size / 1024,
            "expanded_nodes_count": len(expanded_nodes),
            "collapsed_nodes_count": len(collapsed_node_summaries),
            "total_nodes": len(all_node_paths)
        }
        
        return payload
    
    def _infer_node_type_from_path(self, node_path: str) -> str:
        """Infer node type from path for summary generation."""
        path_parts = node_path.split(".")
        if len(path_parts) >= 2:
            return path_parts[1]
        elif len(path_parts) >= 1:
            return path_parts[0]
        else:
            return "unknown"
