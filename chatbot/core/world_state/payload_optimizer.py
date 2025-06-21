#!/usr/bin/env python3
"""
Payload Optimization Utilities

This module contains utilities for optimizing AI payloads by removing empty values,
compressing data, and applying size reduction techniques.
Extracted from PayloadBuilder for better separation of concerns.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class PayloadOptimizer:
    """
    Utilities for optimizing payload size and structure for AI consumption.
    
    This class provides methods to:
    - Remove empty/null values from nested structures
    - Compress verbose data representations
    - Apply size-based filtering
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    @staticmethod
    def remove_empty_values(data: Any) -> Any:
        """
        Recursively remove empty values from nested data structures.
        
        Args:
            data: Any data structure (dict, list, primitive)
            
        Returns:
            Data structure with empty values removed
        """
        if isinstance(data, dict):
            return {
                key: PayloadOptimizer.remove_empty_values(value)
                for key, value in data.items()
                if value is not None and value != "" and value != [] and value != {}
            }
        elif isinstance(data, list):
            return [
                PayloadOptimizer.remove_empty_values(item)
                for item in data
                if item is not None and item != "" and item != [] and item != {}
            ]
        else:
            return data
    
    @staticmethod
    def optimize_payload_size(payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply various optimizations to reduce payload size.
        
        Args:
            payload: The payload dictionary to optimize
            
        Returns:
            Optimized payload with reduced size
        """
        return PayloadOptimizer.remove_empty_values(payload)
    
    def compress_channel_data(self, channels_dict: Dict[str, Any], max_messages_per_channel: int = 10) -> Dict[str, Any]:
        """
        Compress channel data by limiting messages and removing verbose fields.
        
        Args:
            channels_dict: Dictionary of channel data
            max_messages_per_channel: Maximum messages to keep per channel
            
        Returns:
            Compressed channel data
        """
        compressed = {}
        
        for channel_id, channel_data in channels_dict.items():
            if not channel_data:
                continue
                
            compressed_channel = {
                'id': channel_id,
                'name': channel_data.get('name', channel_id),
                'member_count': len(channel_data.get('members', [])),
                'recent_activity': bool(channel_data.get('recent_messages', []))
            }
            
            # Limit recent messages
            if 'recent_messages' in channel_data and channel_data['recent_messages']:
                messages = channel_data['recent_messages']
                if len(messages) > max_messages_per_channel:
                    messages = messages[-max_messages_per_channel:]
                
                compressed_channel['recent_messages'] = [
                    {
                        'sender': msg.get('sender', 'unknown'),
                        'content': msg.get('content', '')[:200],  # Truncate long messages
                        'timestamp': msg.get('timestamp')
                    }
                    for msg in messages
                ]
            
            compressed[channel_id] = compressed_channel
        
        return compressed
    
    def summarize_large_collections(self, data: Dict[str, Any], collection_size_threshold: int = 50) -> Dict[str, Any]:
        """
        Summarize large collections to prevent payload bloat.
        
        Args:
            data: Data dictionary that may contain large collections
            collection_size_threshold: Size threshold for summarization
            
        Returns:
            Data with large collections summarized
        """
        summarized = {}
        
        for key, value in data.items():
            if isinstance(value, list) and len(value) > collection_size_threshold:
                # Summarize large lists
                summarized[key] = {
                    '_summary': f'Large collection with {len(value)} items',
                    'first_few': value[:5],
                    'last_few': value[-5:] if len(value) > 5 else [],
                    'total_count': len(value)
                }
            elif isinstance(value, dict) and len(value) > collection_size_threshold:
                # Summarize large dictionaries
                summarized[key] = {
                    '_summary': f'Large dictionary with {len(value)} keys',
                    'sample_keys': list(value.keys())[:10],
                    'total_count': len(value)
                }
            else:
                summarized[key] = value
        
        return summarized
    
    def create_size_estimate(self, data: Any) -> Dict[str, Any]:
        """
        Create a size estimate for any data structure.
        
        Args:
            data: Data to estimate size for
            
        Returns:
            Dictionary with size metrics
        """
        import json
        
        try:
            json_str = json.dumps(data, default=str)
            byte_size = len(json_str.encode('utf-8'))
            
            return {
                'estimated_bytes': byte_size,
                'estimated_kb': round(byte_size / 1024, 2),
                'estimated_tokens': round(byte_size / 4),  # Rough estimate: 4 bytes per token
                'json_length': len(json_str)
            }
        except Exception as e:
            self.logger.warning(f"Could not estimate size: {e}")
            return {
                'estimated_bytes': 0,
                'estimated_kb': 0,
                'estimated_tokens': 0,
                'json_length': 0,
                'error': str(e)
            }
