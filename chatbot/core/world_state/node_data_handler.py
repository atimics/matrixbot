#!/usr/bin/env python3
"""
Node Data Handlers

This module handles the retrieval of specific node data from WorldStateData.
Extracted from PayloadBuilder to improve maintainability and single responsibility.
Each handler is responsible for a specific data domain (channels, users, etc.).
"""

import logging
from dataclasses import asdict
from typing import Dict, List, Optional, Any
from .structures import WorldStateData

logger = logging.getLogger(__name__)


class NodeDataHandler:
    """
    Handles data retrieval for specific node paths in the node-based payload system.
    
    This class routes node path requests to appropriate domain-specific handlers
    and provides a clean interface for data access.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        # Map node types to their handler methods
        self._handlers = {
            "channels": self._get_channel_node_data,
            "users": self._get_user_node_data,
            "tools": self._get_tool_node_data,
            "memory_bank": self._get_memory_bank_node_data,
            "farcaster": self._get_farcaster_node_data,
            "threads": self._get_thread_node_data,
            "system": self._get_system_node_data,
            "media_gallery": self._get_media_gallery_node_data,
            "search": self._get_search_cache_node_data,
        }
    
    def get_node_data_by_path(self, world_state_data: WorldStateData, node_path: str, expanded: bool = False) -> Optional[Dict]:
        """
        Get data for a specific node path.
        
        Args:
            world_state_data: The world state data to query
            node_path: The node path (e.g., "channels/general", "users/farcaster/123")
            expanded: Whether to return expanded/detailed data
            
        Returns:
            Dictionary containing the node data, or None if not found
        """
        try:
            from .node_path_generator import NodePathGenerator
            path_generator = NodePathGenerator()
            path_parts = path_generator.parse_node_path(node_path)
            
            if not path_parts:
                self.logger.warning(f"Empty path parts for node: {node_path}")
                return None
            
            # Route to appropriate handler based on first path component
            node_type = path_parts[0]
            
            if node_type in self._handlers:
                return self._handlers[node_type](world_state_data, path_parts, expanded)
            else:
                self.logger.warning(f"Unknown node type '{node_type}' in path: {node_path}")
                return None
                
        except Exception as e:
            self.logger.error(f"Error getting node data for path '{node_path}': {e}")
            return None

    def _get_channel_node_data(self, world_state_data: WorldStateData, path_parts: List[str], expanded: bool = False) -> Optional[Dict]:
        """Handle channel node data retrieval."""
        if len(path_parts) == 1:
            # Root channels node - provide overview
            channel_overview = {}
            for platform, platform_channels in world_state_data.channels.items():
                channel_overview[platform] = {
                    'count': len(platform_channels),
                    'channels': list(platform_channels.keys())[:10]  # First 10 for overview
                }
            return channel_overview
        
        if len(path_parts) >= 2:
            channel_id = path_parts[1]
            
            # Find channel across all platforms
            for platform, platform_channels in world_state_data.channels.items():
                if channel_id in platform_channels:
                    channel = platform_channels[channel_id]
                    
                    if len(path_parts) == 2:
                        # Channel summary
                        return {
                            'id': channel_id,
                            'platform': platform,
                            'name': getattr(channel, 'name', channel_id),
                            'member_count': len(getattr(channel, 'members', [])),
                            'recent_message_count': len(getattr(channel, 'recent_messages', [])),
                            'has_recent_activity': bool(getattr(channel, 'recent_messages', []))
                        }
                    
                    elif len(path_parts) == 3:
                        sub_component = path_parts[2]
                        if sub_component == "members":
                            return {'members': getattr(channel, 'members', [])}
                        elif sub_component == "recent_messages":
                            messages = getattr(channel, 'recent_messages', [])
                            if expanded:
                                return {'messages': [msg.to_ai_summary_dict() for msg in messages]}
                            else:
                                return {'message_count': len(messages), 'latest_few': [msg.to_ai_summary_dict() for msg in messages[-3:]]}
        
        return None

    def _get_user_node_data(self, world_state_data: WorldStateData, path_parts: List[str], expanded: bool = False) -> Optional[Dict]:
        """Handle user node data retrieval."""
        if len(path_parts) == 1:
            # Root users node - provide overview
            return {
                'matrix_users_count': len(world_state_data.matrix_users),
                'farcaster_users_count': len(world_state_data.farcaster_users),
                'memory_bank_count': len(world_state_data.user_memory_bank)
            }
        
        if len(path_parts) >= 2:
            user_type = path_parts[1]
            
            if user_type == "matrix_users":
                if len(path_parts) == 2:
                    return {'user_ids': list(world_state_data.matrix_users.keys())[:20]}
                elif len(path_parts) == 3:
                    user_id = path_parts[2]
                    user = world_state_data.matrix_users.get(user_id)
                    return asdict(user) if user else None
            
            elif user_type == "farcaster_users":
                if len(path_parts) == 2:
                    return {'fids': list(world_state_data.farcaster_users.keys())[:20]}
                elif len(path_parts) == 3:
                    fid = path_parts[2]
                    user = world_state_data.farcaster_users.get(fid)
                    return asdict(user) if user else None
        
        return None

    def _get_farcaster_node_data(self, world_state_data: WorldStateData, path_parts: List[str], expanded: bool = False) -> Optional[Dict]:
        """Handle Farcaster node data retrieval."""
        if len(path_parts) == 1:
            # Root Farcaster node - provide overview
            return {
                'users_count': len(world_state_data.farcaster_users),
                'bot_media_count': len(world_state_data.bot_media_on_farcaster)
            }
        
        if len(path_parts) >= 2:
            farcaster_type = path_parts[1]
            
            if farcaster_type == "users":
                if len(path_parts) == 2:
                    return {'fids': list(world_state_data.farcaster_users.keys())[:20]}
                elif len(path_parts) == 3:
                    fid = path_parts[2]
                    user = world_state_data.farcaster_users.get(fid)
                    return asdict(user) if user else None
        
        return None

    def _get_system_node_data(self, world_state_data: WorldStateData, path_parts: List[str], expanded: bool = False) -> Optional[Dict]:
        """Handle system node data retrieval."""
        if len(path_parts) == 1:
            return {
                'components': ['notifications', 'rate_limits', 'status', 'action_history'],
                'pending_invites': len(world_state_data.pending_matrix_invites),
                'action_history_count': len(world_state_data.action_history)
            }
        
        if len(path_parts) >= 2:
            component = path_parts[1]
            
            if component == "notifications":
                return {"pending_matrix_invites": world_state_data.pending_matrix_invites}
            elif component == "rate_limits":
                return world_state_data.rate_limits
            elif component == "status":
                return world_state_data.system_status
            elif component == "action_history":
                # Return recent action history
                recent_actions = world_state_data.action_history[-10:] if world_state_data.action_history else []
                return {
                    'recent_actions': [
                        {
                            'action_type': action.action_type,
                            'timestamp': action.timestamp,
                            'result': action.result[:100] if len(action.result) > 100 else action.result  # Truncate long results
                        }
                        for action in recent_actions
                    ],
                    'total_count': len(world_state_data.action_history)
                }
        
        return None

    def _get_media_gallery_node_data(self, world_state_data: WorldStateData, path_parts: List[str], expanded: bool = False) -> Optional[Dict]:
        """Handle media gallery node data retrieval."""
        if len(path_parts) == 1:
            # Root media gallery node - provide overview
            return {
                'generated_media_count': len(world_state_data.generated_media_library),
                'bot_media_count': len(world_state_data.bot_media_on_farcaster),
                'categories': ['generated_media', 'bot_media']
            }
        
        if len(path_parts) >= 2:
            media_type = path_parts[1]
            
            if media_type == "generated_media":
                if len(path_parts) == 2:
                    return {
                        'count': len(world_state_data.generated_media_library),
                        'recent_items': world_state_data.generated_media_library[-5:] if world_state_data.generated_media_library else []
                    }
                elif len(path_parts) == 3:
                    try:
                        index = int(path_parts[2])
                        if 0 <= index < len(world_state_data.generated_media_library):
                            return world_state_data.generated_media_library[index]
                    except (ValueError, IndexError):
                        pass
            
            elif media_type == "bot_media":
                if len(path_parts) == 2:
                    return {
                        'count': len(world_state_data.bot_media_on_farcaster),
                        'cast_hashes': list(world_state_data.bot_media_on_farcaster.keys())[:10]
                    }
                elif len(path_parts) == 3:
                    cast_hash = path_parts[2]
                    return world_state_data.bot_media_on_farcaster.get(cast_hash)
        
        return None

    def _get_tool_node_data(self, world_state_data: WorldStateData, path_parts: List[str], expanded: bool = False) -> Optional[Dict]:
        """Handle tool cache node data retrieval."""
        if len(path_parts) == 1:
            return {
                'cached_tools': list(world_state_data.tool_cache.keys()),
                'cache_count': len(world_state_data.tool_cache)
            }
        
        if len(path_parts) == 2:
            tool_name = path_parts[1]
            return world_state_data.tool_cache.get(tool_name)
        
        return None

    def _get_memory_bank_node_data(self, world_state_data: WorldStateData, path_parts: List[str], expanded: bool = False) -> Optional[Dict]:
        """Handle memory bank node data retrieval."""
        if len(path_parts) == 1:
            return {
                'users_with_memories': list(world_state_data.user_memory_bank.keys()),
                'total_users': len(world_state_data.user_memory_bank)
            }
        
        if len(path_parts) == 2:
            user_id = path_parts[1]
            memories = world_state_data.user_memory_bank.get(user_id, [])
            if expanded:
                return {
                    'user_id': user_id,
                    'memories': [asdict(memory) for memory in memories]
                }
            else:
                return {
                    'user_id': user_id,
                    'memory_count': len(memories),
                    'recent_memories': [asdict(memory) for memory in memories[-3:]]
                }
        
        return None

    def _get_thread_node_data(self, world_state_data: WorldStateData, path_parts: List[str], expanded: bool = False) -> Optional[Dict]:
        """Handle thread node data retrieval."""
        if len(path_parts) == 1:
            return {
                'thread_count': len(world_state_data.threads),
                'thread_ids': list(world_state_data.threads.keys())[:10]
            }
        
        if len(path_parts) == 2:
            thread_id = path_parts[1]
            thread_messages = world_state_data.threads.get(thread_id, [])
            
            if expanded:
                return {
                    'thread_id': thread_id,
                    'messages': [msg.to_ai_summary_dict() for msg in thread_messages]
                }
            else:
                return {
                    'thread_id': thread_id,
                    'message_count': len(thread_messages),
                    'recent_messages': [msg.to_ai_summary_dict() for msg in thread_messages[-3:]]
                }
        
        return None

    def _get_search_cache_node_data(self, world_state_data: WorldStateData, path_parts: List[str], expanded: bool = False) -> Optional[Dict]:
        """Handle search cache node data retrieval."""
        if len(path_parts) == 1:
            return {
                'cached_searches': list(world_state_data.search_cache.keys())[:20],
                'cache_count': len(world_state_data.search_cache)
            }
        
        if len(path_parts) == 2:
            search_key = path_parts[1]
            return world_state_data.search_cache.get(search_key)
        
        return None

    def _iter_all_channels(self, channels_dict: Dict[str, Dict[str, Any]]) -> List[Any]:
        """Iterate through all channels across all platforms."""
        all_channels = []
        for platform_channels in channels_dict.values():
            all_channels.extend(platform_channels.values())
        return all_channels
