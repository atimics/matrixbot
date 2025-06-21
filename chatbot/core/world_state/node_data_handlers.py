#!/usr/bin/env python3
"""
Node Data Handlers

This module contains handlers for retrieving data from different node types
in the node-based payload system.
"""

import logging
import time
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING
from dataclasses import asdict

if TYPE_CHECKING:
    from .structures import WorldStateData

logger = logging.getLogger(__name__)


class NodeDataHandlers:
    """Handles data retrieval for different node types in the node-based system."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        # Map node types to their handler methods for backward compatibility
        self._handlers = {
            "channel": self.get_channel_node_data,
            "user": self.get_user_node_data,
            "tool": self.get_tool_node_data,
            "memory_bank": self.get_memory_bank_node_data,
            "farcaster": self.get_farcaster_node_data,
            "thread": self.get_thread_node_data,
            "system": self.get_system_node_data,
            "media_gallery": self.get_media_gallery_node_data,
            "search": self.get_search_node_data,
        }
    

    
    def get_node_data_by_path(self, world_state_data: 'WorldStateData', node_path: str, expanded: bool = False) -> Optional[Dict]:
        """
        Get data for a specific node path (backward compatibility method).
        
        Args:
            world_state_data: The world state data to query
            node_path: The node path (e.g., "channels/general", "users/farcaster/123")
            expanded: Whether to return expanded/detailed data
            
        Returns:
            Dictionary containing node data or None if not found
        """
        if not node_path:
            return None
        
        # Parse the node path - handle both '/' and '.' separators
        # For channels, be careful not to split Matrix room IDs on dots
        if '/' in node_path:
            path_parts = [part.strip() for part in node_path.split("/") if part.strip()]
        else:
            # For dot-separated paths, be more careful with channel paths
            initial_parts = [part.strip() for part in node_path.split(".") if part.strip()]
            
            # Special handling for channel paths that might have Matrix room IDs with dots
            if len(initial_parts) > 3 and initial_parts[0] == "channel":
                # Rejoin everything after the channel type as the channel ID
                path_parts = initial_parts[:2] + ['.'.join(initial_parts[2:])]
            else:
                path_parts = initial_parts
        
        if not path_parts:
            return None
        
        # Route to the appropriate handler
        node_type = path_parts[0]
        handler = self._handlers.get(node_type)
        
        if handler:
            try:
                return handler(world_state_data, path_parts, expanded=expanded)
            except Exception as e:
                self.logger.error(f"Error getting data for node path {node_path}: {e}")
                return None
        else:
            self.logger.warning(f"No handler found for node type: {node_type}")
            return None

    def get_channel_node_data(self, world_state_data: 'WorldStateData', path_parts: List[str], expanded: bool = False) -> Optional[Dict]:
        """Get channel node data."""
        
        # Handle hierarchical navigation nodes
        if len(path_parts) == 1:
            # Root channels node - provide overview of all channels
            all_channels = {}
            total_messages = 0
            for platform, platform_channels in world_state_data.channels.items():
                all_channels[platform] = len(platform_channels)
                for channel in platform_channels.values():
                    total_messages += len(channel.recent_messages)
            
            return {
                "type": "channels_overview",
                "platforms": list(world_state_data.channels.keys()),
                "channel_counts": all_channels,
                "total_channels": sum(all_channels.values()),
                "total_messages": total_messages
            }
        
        if len(path_parts) == 2:
            # Platform-level node - provide overview of channels in platform
            platform = path_parts[1]
            if platform not in world_state_data.channels:
                logger.warning(f"Platform '{platform}' not found in channels")
                return None
            
            platform_channels = world_state_data.channels[platform]
            return {
                "type": "platform_overview", 
                "platform": platform,
                "channel_count": len(platform_channels),
                "channels": [
                    {
                        "id": ch_id,
                        "name": channel.name,
                        "message_count": len(channel.recent_messages),
                        "last_activity": channel.recent_messages[-1].timestamp if channel.recent_messages else channel.last_checked
                    }
                    for ch_id, channel in platform_channels.items()
                ]
            }
        
        if len(path_parts) < 3: 
            logger.warning(f"Invalid channel node path parts (unexpected format): {path_parts}")
            return None
        
        # Handle case where we have more than 3 parts due to dots in Matrix room IDs
        if len(path_parts) > 3:
            # Rejoin everything after the channel type as the channel ID
            channel_type = path_parts[1]
            channel_id = '.'.join(path_parts[2:])
        else:
            _, channel_type, channel_id = path_parts
        
        logger.info(f"Getting channel node data: type={channel_type}, id={channel_id}, expanded={expanded}")
        
        # Access channel from nested structure: channels[platform][channel_id]
        if channel_type not in world_state_data.channels:
            logger.warning(f"Channel type '{channel_type}' not in world state channels: {list(world_state_data.channels.keys())}")
            return None
        
        channel = world_state_data.channels[channel_type].get(channel_id)
        if not channel: 
            logger.warning(f"Channel '{channel_id}' not found in {channel_type} channels: {list(world_state_data.channels[channel_type].keys())}")
            return None
        
        # Determine message list based on expansion status
        if expanded:
            # For expanded nodes, provide enhanced summaries with more messages and context
            messages_for_payload = [msg.to_ai_summary_dict() for msg in channel.recent_messages[-8:]] # More messages but still summaries
            logger.info(f"Channel {channel_id} EXPANDED: {len(channel.recent_messages)} total messages, including {len(messages_for_payload)} in payload")
        else:
            # For collapsed nodes, provide basic summaries
            messages_for_payload = [msg.to_ai_summary_dict() for msg in channel.recent_messages[-3:]]
            logger.info(f"Channel {channel_id} COLLAPSED: {len(channel.recent_messages)} total messages, including {len(messages_for_payload)} in payload")

        result = {
            "id": channel.id,
            "name": channel.name,
            "type": channel.type,
            "status": channel.status,
            "msg_count": len(channel.recent_messages),
            "last_activity": channel.recent_messages[-1].timestamp if channel.recent_messages else channel.last_checked,
            "recent_messages": messages_for_payload,
        }
        
        logger.info(f"Returning channel data for {channel_id}: {result['name']} with {len(result['recent_messages'])} messages")
        return result

    def get_user_node_data(self, world_state_data: 'WorldStateData', path_parts: List[str], expanded: bool = False) -> Optional[Dict]:
        """Get user node data."""
        if len(path_parts) < 3: 
            return None
        _, user_type, user_id = path_parts[0], path_parts[1], path_parts[2]
        
        user = None
        if user_type == "farcaster":
            user = world_state_data.farcaster_users.get(user_id)
        elif user_type == "matrix":
            user = world_state_data.matrix_users.get(user_id)
        
        if len(path_parts) == 4 and user: # Sub-node request
            sub_node = path_parts[3]
            if sub_node == "timeline_cache": 
                return getattr(user, 'timeline_cache', None)
            if sub_node == "sentiment": 
                sentiment = getattr(user, 'sentiment', None)
                return asdict(sentiment) if sentiment else None
            if sub_node == "memories": 
                memories = getattr(user, 'memory_entries', [])
                return {"memories": [asdict(mem) for mem in memories[-5:]]}
        
        if user:
            # Create basic dict representation (to_ai_summary_dict may not be available)
            return {
                "id": user_id,
                "type": user_type,
                "username": getattr(user, 'username', None),
                "display_name": getattr(user, 'display_name', None),
                "fid": getattr(user, 'fid', None) if user_type == 'farcaster' else None
            }
        
        # Fallback for users not in the main dict
        for channel in self._iter_all_channels(world_state_data.channels):
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

    def get_farcaster_node_data(self, world_state_data: 'WorldStateData', path_parts: List[str], expanded: bool = False) -> Optional[Dict]:
        """Get Farcaster-specific node data."""
        if len(path_parts) < 2: 
            return None
        node_type = path_parts[1]
        
        if node_type == "recent_posts":
            return {
                "status": "Available via Farcaster observer",
                "note": "Recent posts are checked automatically for rate limiting and duplicate prevention"
            }
        elif node_type == "rate_limits":
            rate_limits = world_state_data.rate_limits.get('farcaster_api', {})
            return {
                "remaining": rate_limits.get("remaining", 0),
                "limit": rate_limits.get("limit", 0),
                "reset_time": rate_limits.get("reset_time"),
                "last_updated": rate_limits.get("last_updated"),
                "can_post": rate_limits.get("remaining", 0) > 0
            }
        elif node_type == "feeds" and len(path_parts) >= 3:
            feed_type = path_parts[2]
            if feed_type == "trending":
                return {"feed_type": "trending", "status": "Available via get_trending_casts tool"}
            
            messages = []
            for ch in self._iter_all_channels(world_state_data.channels):
                if ch.type == "farcaster":
                    if feed_type == "home" and "home" in ch.id:
                        messages.extend(ch.recent_messages[-5:])
                    elif feed_type == "notifications" and ("notification" in ch.id or "mention" in ch.id):
                        messages.extend(ch.recent_messages[-5:])
                    elif feed_type == "for_you" and "for_you" in ch.id:
                        messages.extend(ch.recent_messages[-5:])
                    elif feed_type == "holders" and "holders" in ch.id:
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

    def get_system_node_data(self, world_state_data: 'WorldStateData', path_parts: List[str], expanded: bool = False) -> Optional[Dict]:
        """Get system node data."""
        if len(path_parts) < 2: 
            return None
        component = path_parts[1]
        
        if component == "notifications": 
            return {"pending_matrix_invites": world_state_data.pending_matrix_invites}
        if component == "rate_limits": 
            return world_state_data.rate_limits
        if component == "status": 
            return world_state_data.system_status
        if component == "action_history": 
            # Use optimized action history to prevent large payloads
            history = world_state_data.action_history[-10:]
            return {
                "action_history": [
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
            }
        return None

    def get_media_gallery_node_data(self, world_state_data: 'WorldStateData', path_parts: List[str], expanded: bool = False) -> Optional[Dict]:
        """Get node data for the AI's generated media library."""
        if len(path_parts) == 1:
            # Root media gallery node - provide overview
            media_library = world_state_data.generated_media_library
            if not media_library:
                return {
                    "status": "empty",
                    "total_media_count": 0,
                    "message": "No generated media available yet. Use image generation tools to create media.",
                    "available_tools": ["generate_image", "generate_meme"]
                }
            
            # Recent media summary
            recent_media = media_library[-10:]  # Last 10 items
            
            # Group by media type
            media_by_type = {}
            for media_item in media_library:
                media_type = getattr(media_item, 'media_type', 'unknown')
                if media_type not in media_by_type:
                    media_by_type[media_type] = []
                media_by_type[media_type].append(media_item)
            
            summary_data = {
                "status": "available",
                "total_media_count": len(media_library),
                "recent_media_count": len(recent_media),
                "media_types": {
                    media_type: len(items) 
                    for media_type, items in media_by_type.items()
                },
                "recent_media": [
                    {
                        "media_id": getattr(item, 'media_id', None),
                        "media_type": getattr(item, 'media_type', 'unknown'),
                        "description": getattr(item, 'description', 'No description'),
                        "timestamp": getattr(item, 'timestamp', 0),
                        "file_path": getattr(item, 'file_path', None),
                        "available_for_posting": bool(getattr(item, 'file_path', None))
                    }
                    for item in recent_media
                ],
                "usage_instructions": "Use media_id or file_path to attach media to Farcaster posts with cast_with_image tool"
            }
            
            if expanded:
                # When expanded, include more details about recent media
                summary_data["detailed_recent_media"] = [
                    {
                        "media_id": getattr(item, 'media_id', None),
                        "media_type": getattr(item, 'media_type', 'unknown'),
                        "description": getattr(item, 'description', 'No description'),
                        "prompt": getattr(item, 'generation_prompt', 'No prompt recorded'),
                        "timestamp": getattr(item, 'timestamp', 0),
                        "file_path": getattr(item, 'file_path', None),
                        "file_size": getattr(item, 'file_size', 0),
                        "dimensions": getattr(item, 'dimensions', None),
                        "available_for_posting": bool(getattr(item, 'file_path', None)),
                        "node_path": f"media_gallery.{getattr(item, 'media_id', 'unknown')}" if getattr(item, 'media_id', None) else None
                    }
                    for item in recent_media
                ]
            
            return summary_data
            
        elif len(path_parts) == 2:
            # Specific media item or category
            item_id = path_parts[1]
            
            # Find specific media item by ID
            for media_item in world_state_data.generated_media_library:
                # Handle both dict and object formats
                if isinstance(media_item, dict):
                    media_id = media_item.get('media_id')
                else:
                    media_id = getattr(media_item, 'media_id', None)
                    
                if media_id == item_id:
                    if isinstance(media_item, dict):
                        return {
                            "media_id": media_item.get('media_id'),
                            "media_type": media_item.get('media_type', 'unknown'),
                            "description": media_item.get('description', 'No description'),
                            "generation_prompt": media_item.get('generation_prompt', 'No prompt recorded'),
                            "timestamp": media_item.get('timestamp', 0),
                            "file_path": media_item.get('file_path'),
                            "file_size": media_item.get('file_size', 0),
                            "dimensions": media_item.get('dimensions'),
                            "available_for_posting": bool(media_item.get('file_path')),
                            "usage_instructions": f"Use media_id '{media_item.get('media_id')}' or file_path '{media_item.get('file_path', '')}' with cast_with_image tool"
                        }
                    else:
                        return {
                            "media_id": media_item.media_id,
                            "media_type": getattr(media_item, 'media_type', 'unknown'),
                            "description": getattr(media_item, 'description', 'No description'),
                            "generation_prompt": getattr(media_item, 'generation_prompt', 'No prompt recorded'),
                            "timestamp": getattr(media_item, 'timestamp', 0),
                            "file_path": getattr(media_item, 'file_path', None),
                            "file_size": getattr(media_item, 'file_size', 0),
                            "dimensions": getattr(media_item, 'dimensions', None),
                            "available_for_posting": bool(getattr(media_item, 'file_path', None)),
                            "usage_instructions": f"Use media_id '{media_item.media_id}' or file_path '{getattr(media_item, 'file_path', '')}' with cast_with_image tool"
                        }
            
            return {"error": f"Media item '{item_id}' not found in gallery"}
            
        elif len(path_parts) == 3 and path_parts[1] == "by_type":
            # Media items filtered by type
            media_type = path_parts[2]
            filtered_media = [
                media_item for media_item in world_state_data.generated_media_library
                if getattr(media_item, 'media_type', 'unknown') == media_type
            ]
            
            return {
                "media_type": media_type,
                "count": len(filtered_media),
                "media_items": [
                    {
                        "media_id": getattr(item, 'media_id', None),
                        "description": getattr(item, 'description', 'No description'),
                        "timestamp": getattr(item, 'timestamp', 0),
                        "file_path": getattr(item, 'file_path', None),
                        "available_for_posting": bool(getattr(item, 'file_path', None))
                    }
                    for item in filtered_media[-10:]  # Last 10 of this type
                ]
            }
        
        return None

    def get_tool_node_data(self, world_state_data: 'WorldStateData', path_parts: List[str], expanded: bool = False) -> Optional[Dict]:
        """Get tool cache node data."""
        if len(path_parts) < 2: 
            return None
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

    def get_memory_bank_node_data(self, world_state_data: 'WorldStateData', path_parts: List[str], expanded: bool = False) -> Optional[Dict]:
        """Get memory bank node data."""
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

    def get_thread_node_data(self, world_state_data: 'WorldStateData', path_parts: List[str], expanded: bool = False) -> Optional[Dict]:
        """Get thread node data."""
        if len(path_parts) >= 3:
            thread_type, thread_id = path_parts[1], path_parts[2]
            
            # Check if this is an existing thread in world state
            if thread_id in world_state_data.threads:
                thread_messages = world_state_data.threads[thread_id]
                return {
                    "thread_id": thread_id,
                    "type": thread_type,
                    "message_count": len(thread_messages),
                    "messages": [msg.to_ai_summary_dict() for msg in thread_messages[-5:]]  # Use summaries instead of full data
                }
            
            # Handle individual cast thread expansion
            elif thread_type == "farcaster" and expanded:
                root_cast = self._find_cast_by_id(world_state_data, thread_id)
                if root_cast:
                    if expanded:
                        return {
                            "thread_id": thread_id,
                            "type": "farcaster_cast_thread",
                            "root_cast": root_cast.to_ai_summary_dict(),
                            "conversation_available": True,
                            "note": "This cast can be expanded to view its full conversation thread. Use 'expand_node' to see all replies."
                        }
                    else:
                        return {
                            "thread_id": thread_id,
                            "type": "farcaster_cast_thread", 
                            "root_cast": root_cast.to_ai_summary_dict(),
                            "conversation_available": True
                        }
        return None

    def _find_cast_by_id(self, world_state_data: 'WorldStateData', cast_id: str) -> Optional[Any]:
        """Find a Farcaster cast by its ID across all channels."""
        for platform_channels in world_state_data.channels.values():
            if isinstance(platform_channels, dict):
                for channel_id, channel in platform_channels.items():
                    if channel.type == "farcaster":
                        for msg in channel.recent_messages:
                            if hasattr(msg, 'id') and msg.id == cast_id:
                                return msg
        return None

    def _iter_all_channels(self, channels_dict):
        """Yield all Channel objects from possibly nested channels dict."""
        for platform_channels in channels_dict.values():
            if isinstance(platform_channels, dict):
                for ch in platform_channels.values():
                    yield ch
            elif hasattr(platform_channels, 'recent_messages'):
                yield platform_channels

    def get_search_node_data(self, world_state_data: 'WorldStateData', path_parts: List[str], expanded: bool = False) -> Optional[Dict]:
        """Get search node data."""
        if len(path_parts) < 1:
            logger.warning(f"Invalid search node path parts (empty): {path_parts}")
            return None
        
        # Handle case where we only have ['search'] without a query
        if len(path_parts) == 1:
            return {
                "query": "",
                "search_type": "general",
                "context": "General search context",
                "expanded": expanded,
                "note": "Search context node - no specific query provided"
            }
        
        # Parse search query from path
        search_query = path_parts[1]
        
        # Decode URL-encoded query if needed
        import urllib.parse
        try:
            decoded_query = urllib.parse.unquote(search_query)
        except Exception:
            decoded_query = search_query
        
        logger.debug(f"Processing search node: query='{decoded_query}', expanded={expanded}")
        
        return {
            "query": decoded_query,
            "search_type": "semantic" if len(decoded_query.split()) > 1 else "keyword",
            "context": f"Search for: '{decoded_query}'",
            "expanded": expanded,
            "note": "Search context node - provides search query information for AI context"
        }


