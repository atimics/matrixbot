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
        """Generate paths for channels using singular 'channel' type."""
        yield "channel"
        if hasattr(world_state_data, 'channels') and world_state_data.channels:
            for platform, platform_channels in world_state_data.channels.items():
                yield f"channel.{platform}"
                for channel_id in platform_channels.keys():
                    yield f"channel.{platform}.{channel_id}"

    def _generate_farcaster_feed_paths(self, world_state_data: WorldStateData):
        """Generate paths for Farcaster feed data."""
        yield "farcaster"
        
        # Farcaster users
        if hasattr(world_state_data, 'farcaster_users') and world_state_data.farcaster_users:
            yield "farcaster.users"
            for fid in world_state_data.farcaster_users.keys():
                yield f"farcaster.users.{fid}"

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
        """Generate paths for users using singular 'user' type."""
        yield "user"
        
        # Matrix users
        if hasattr(world_state_data, 'matrix_users') and world_state_data.matrix_users:
            yield "user/matrix"
            for user_id in world_state_data.matrix_users.keys():
                yield f"user/matrix/{user_id}"
        
        # Farcaster users  
        if hasattr(world_state_data, 'farcaster_users') and world_state_data.farcaster_users:
            yield "user/farcaster"
            for fid in world_state_data.farcaster_users.keys():
                yield f"user/farcaster/{fid}"

    def _generate_tool_cache_paths(self, world_state_data: WorldStateData):
        """Generate paths for tool cache using singular 'tool' type."""
        yield "tool"
        if hasattr(world_state_data, 'tool_cache') and world_state_data.tool_cache:
            for tool_name in world_state_data.tool_cache.keys():
                yield f"tool.cache.{tool_name}"

    def _generate_search_cache_paths(self, world_state_data: WorldStateData):
        """Generate paths for search cache."""
        yield "search"
        if hasattr(world_state_data, 'search_cache') and world_state_data.search_cache:
            for search_key in world_state_data.search_cache.keys():
                yield f"search.{search_key}"

    def _generate_memory_bank_paths(self, world_state_data: WorldStateData):
        """Generate paths for memory bank."""
        yield "memory_bank"
        if hasattr(world_state_data, 'user_memory_bank') and world_state_data.user_memory_bank:
            for user_id in world_state_data.user_memory_bank.keys():
                yield f"memory_bank/{user_id}"

    def _generate_thread_paths(self, world_state_data: WorldStateData):
        """Generate paths for threads using singular 'thread' type."""
        yield "thread"
        if hasattr(world_state_data, 'threads') and world_state_data.threads:
            # The threads dict maps root cast id to thread messages
            for thread_id in world_state_data.threads.keys():
                yield f"thread.farcaster.{thread_id}"

    def _generate_system_paths(self, world_state_data: WorldStateData):
        """Generate paths for system data."""
        yield "system"

    def parse_node_path(self, node_path: str) -> List[str]:
        """
        Parse a node path into its constituent parts.
        
        Args:
            node_path: Node path like "channels.matrix.!room:server.com"
            
        Returns:
            List of path parts: ["channels", "matrix", "!room:server.com"]
        """
        if not node_path:
            return []
        
        # Split by '.' for the new hierarchical path structure
        parts = [part.strip() for part in node_path.split(".") if part.strip()]
        
        # Validate path structure
        if not parts:
            self.logger.warning(f"Invalid node path: {node_path}")
            return []
        
        # No need for decoding with this format
        return parts
