#!/usr/bin/env python3
"""
Node Path Generator

This module handles the generation of node paths for the node-based payload system.
Extracted from PayloadBuilder to improve maintainability and single responsibility.
"""

import logging
from typing import List, Generator, Optional
from .structures import WorldStateData

logger = logging.getLogger(__name__)


class NodePathGenerator:
    """
    Generates hierarchical node paths from WorldStateData for the node-based system.
    
    This class is responsible for creating the tree-like navigation structure
    that allows the AI to drill down into specific data areas efficiently.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def get_node_paths_from_world_state(
        self, world_state_data: WorldStateData
    ) -> List[str]:
        """Generate all possible node paths from world state data."""
        node_paths = []
        for path in self._generate_node_paths(world_state_data):
            node_paths.append(path)
        return node_paths
    
    def _generate_node_paths(
        self, world_state_data: WorldStateData
    ) -> Generator[str, None, None]:
        """Generate node paths from world state data."""
        yield from self._generate_channel_paths(world_state_data)
        yield from self._generate_farcaster_feed_paths(world_state_data)
        yield from self._generate_media_gallery_paths(world_state_data)
        yield from self._generate_user_paths(world_state_data)
        yield from self._generate_tool_cache_paths(world_state_data)
        yield from self._generate_search_cache_paths(world_state_data)
        yield from self._generate_memory_bank_paths(world_state_data)
        yield from self._generate_thread_paths(world_state_data)
        yield from self._generate_system_paths(world_state_data)

    def _generate_channel_paths(self, world_state_data: WorldStateData):
        """Generate paths for channels."""
        yield "channels"
        if hasattr(world_state_data, 'channels') and world_state_data.channels:
            for channel_id in world_state_data.channels.keys():
                yield f"channels/{channel_id}"
                yield f"channels/{channel_id}/members"
                yield f"channels/{channel_id}/recent_messages"

    def _generate_farcaster_feed_paths(self, world_state_data: WorldStateData):
        """Generate paths for Farcaster feed data."""
        yield "farcaster"
        
        # Farcaster users
        if hasattr(world_state_data, 'farcaster_users') and world_state_data.farcaster_users:
            yield "farcaster/users"
            for fid in world_state_data.farcaster_users.keys():
                yield f"farcaster/users/{fid}"

    def _generate_media_gallery_paths(self, world_state_data: WorldStateData):
        """Generate paths for media gallery."""
        yield "media_gallery"
        if hasattr(world_state_data, 'generated_media_library') and world_state_data.generated_media_library:
            yield "media_gallery/generated_media"
            for i, media_item in enumerate(world_state_data.generated_media_library):
                yield f"media_gallery/generated_media/{i}"
        
        if hasattr(world_state_data, 'bot_media_on_farcaster') and world_state_data.bot_media_on_farcaster:
            yield "media_gallery/bot_media"
            for cast_hash in world_state_data.bot_media_on_farcaster.keys():
                yield f"media_gallery/bot_media/{cast_hash}"

    def _generate_user_paths(self, world_state_data: WorldStateData):
        """Generate paths for users."""
        yield "users"
        
        # Matrix users
        if hasattr(world_state_data, 'matrix_users') and world_state_data.matrix_users:
            yield "users/matrix_users"
            for user_id in world_state_data.matrix_users.keys():
                yield f"users/matrix_users/{user_id}"
        
        # Farcaster users  
        if hasattr(world_state_data, 'farcaster_users') and world_state_data.farcaster_users:
            yield "users/farcaster_users"
            for fid in world_state_data.farcaster_users.keys():
                yield f"users/farcaster_users/{fid}"

    def _generate_tool_cache_paths(self, world_state_data: WorldStateData):
        """Generate paths for tool cache."""
        yield "tools"
        if hasattr(world_state_data, 'tool_cache') and world_state_data.tool_cache:
            for tool_name in world_state_data.tool_cache.keys():
                yield f"tools/{tool_name}"

    def _generate_search_cache_paths(self, world_state_data: WorldStateData):
        """Generate paths for search cache."""
        yield "search"
        if hasattr(world_state_data, 'search_cache') and world_state_data.search_cache:
            for search_key in world_state_data.search_cache.keys():
                yield f"search/{search_key}"

    def _generate_memory_bank_paths(self, world_state_data: WorldStateData):
        """Generate paths for memory bank."""
        yield "memory_bank"
        if hasattr(world_state_data, 'user_memory_bank') and world_state_data.user_memory_bank:
            for user_id in world_state_data.user_memory_bank.keys():
                yield f"memory_bank/{user_id}"

    def _generate_thread_paths(self, world_state_data: WorldStateData):
        """Generate paths for threads."""
        yield "threads"
        if hasattr(world_state_data, 'threads') and world_state_data.threads:
            # The threads dict maps root cast id to thread messages
            for thread_id in world_state_data.threads.keys():
                yield f"threads/{thread_id}"

    def _generate_system_paths(self, world_state_data: WorldStateData):
        """Generate paths for system data."""
        yield "system"

    def parse_node_path(self, node_path: str) -> List[str]:
        """
        Parse a node path into its constituent parts.
        
        Args:
            node_path: Node path like "channels/general/recent_messages"
            
        Returns:
            List of path parts: ["channels", "general", "recent_messages"]
        """
        if not node_path:
            return []
        
        # Handle root paths
        if "/" not in node_path:
            return [node_path]
        
        # Split path and filter empty parts
        parts = [part.strip() for part in node_path.split("/") if part.strip()]
        
        # Validate path structure
        if not parts:
            self.logger.warning(f"Invalid node path: {node_path}")
            return []
        
        # Decode any URL-encoded parts if needed
        decoded_parts = []
        for part in parts:
            try:
                # Basic URL decoding for common cases
                decoded_part = part.replace("%20", " ").replace("%2F", "/")
                decoded_parts.append(decoded_part)
            except Exception as e:
                self.logger.warning(f"Error decoding path part '{part}': {e}")
                decoded_parts.append(part)
        
        return decoded_parts
