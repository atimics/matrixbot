"""
Advanced World State Query Tools

These tools allow the AI to perform targeted queries about the world state
rather than parsing the entire JSON payload, making decision-making more
efficient and focused.
"""

import logging
import time
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

from .base import ActionContext, ToolInterface

logger = logging.getLogger(__name__)


class QueryChannelActivityTool(ToolInterface):
    """
    Tool for querying specific channel activity within a time window.
    """
    
    @property
    def name(self) -> str:
        return "query_channel_activity"
    
    @property
    def description(self) -> str:
        return "Query activity in a specific channel over a time window. Returns a focused summary of messages, reactions, and user activity."
    
    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "channel_id": {
                    "type": "string",
                    "description": "The channel/room ID to query"
                },
                "time_window_minutes": {
                    "type": "integer",
                    "description": "Time window in minutes to look back (default: 60)",
                    "default": 60
                },
                "include_reactions": {
                    "type": "boolean",
                    "description": "Whether to include reaction data (default: true)",
                    "default": True
                }
            },
            "required": ["channel_id"]
        }
    
    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """
        Execute the channel activity query.
        """
        logger.debug(f"Executing tool '{self.name}' with params: {params}")
        
        channel_id = params.get("channel_id")
        time_window_minutes = params.get("time_window_minutes", 60)
        include_reactions = params.get("include_reactions", True)
        
        if not channel_id:
            error_msg = "Missing required parameter: channel_id"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}
        
        if not context.world_state_manager:
            error_msg = "World state manager not available"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}
        
        try:
            # Calculate time window
            current_time = time.time()
            cutoff_time = current_time - (time_window_minutes * 60)
            
            # Get channel data
            world_state = context.world_state_manager.get_world_state_data()
            channel_data = None
            
            # Find the channel in either matrix or farcaster channels
            if hasattr(world_state, 'matrix_channels') and channel_id in world_state.matrix_channels:
                channel_data = world_state.matrix_channels[channel_id]
                platform = "matrix"
            elif hasattr(world_state, 'farcaster_channels') and channel_id in world_state.farcaster_channels:
                channel_data = world_state.farcaster_channels[channel_id]
                platform = "farcaster"
            
            if not channel_data:
                return {
                    "status": "success",
                    "channel_id": channel_id,
                    "activity_summary": "Channel not found or no data available",
                    "message_count": 0,
                    "active_users": [],
                    "timestamp": time.time()
                }
            
            # Filter messages by time window
            recent_messages = []
            active_users = set()
            user_message_counts = {}
            
            for message in getattr(channel_data, 'messages', []):
                if message.timestamp >= cutoff_time:
                    recent_messages.append(message)
                    active_users.add(message.sender)
                    user_message_counts[message.sender] = user_message_counts.get(message.sender, 0) + 1
            
            # Sort messages by timestamp
            recent_messages.sort(key=lambda m: m.timestamp, reverse=True)
            
            # Analyze message patterns
            topic_keywords = []
            if recent_messages:
                # Simple keyword extraction from recent messages
                all_content = " ".join([msg.content for msg in recent_messages[:10]])  # Last 10 messages
                words = all_content.lower().split()
                word_freq = {}
                for word in words:
                    if len(word) > 4:  # Focus on meaningful words
                        word_freq[word] = word_freq.get(word, 0) + 1
                topic_keywords = [word for word, count in sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:5]]
            
            # Build activity summary
            activity_summary = f"Last {time_window_minutes} minutes: {len(recent_messages)} messages from {len(active_users)} users"
            if topic_keywords:
                activity_summary += f". Key topics: {', '.join(topic_keywords)}"
            
            # Get top active users
            top_users = sorted(user_message_counts.items(), key=lambda x: x[1], reverse=True)[:3]
            
            result = {
                "status": "success",
                "channel_id": channel_id,
                "platform": platform,
                "time_window_minutes": time_window_minutes,
                "activity_summary": activity_summary,
                "message_count": len(recent_messages),
                "active_users": list(active_users),
                "top_contributors": [{"user": user, "message_count": count} for user, count in top_users],
                "recent_messages_preview": [
                    {
                        "sender": msg.sender,
                        "content": msg.content[:100] + "..." if len(msg.content) > 100 else msg.content,
                        "timestamp": msg.timestamp,
                        "reply_to": getattr(msg, 'reply_to', None)
                    }
                    for msg in recent_messages[:5]  # Show last 5 messages
                ],
                "topic_keywords": topic_keywords,
                "timestamp": time.time()
            }
            
            logger.debug(f"Channel activity query successful: {len(recent_messages)} messages found")
            return result
            
        except Exception as e:
            error_msg = f"Error executing channel activity query: {str(e)}"
            logger.exception(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}


class FindMessagesFromUserTool(ToolInterface):
    """
    Tool for finding recent messages from a specific user across all channels.
    """
    
    @property
    def name(self) -> str:
        return "find_messages_from_user"
    
    @property
    def description(self) -> str:
        return "Find recent messages from a specific user across all channels. Useful for understanding user context and conversation history."
    
    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "user_identifier": {
                    "type": "string",
                    "description": "User identifier (username, user ID, or display name)"
                },
                "max_messages": {
                    "type": "integer",
                    "description": "Maximum number of messages to return (default: 5)",
                    "default": 5
                },
                "time_window_hours": {
                    "type": "integer",
                    "description": "Time window in hours to search (default: 24)",
                    "default": 24
                }
            },
            "required": ["user_identifier"]
        }
    
    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """
        Execute the user message search.
        """
        logger.debug(f"Executing tool '{self.name}' with params: {params}")
        
        user_identifier = params.get("user_identifier")
        max_messages = params.get("max_messages", 5)
        time_window_hours = params.get("time_window_hours", 24)
        
        if not user_identifier:
            error_msg = "Missing required parameter: user_identifier"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}
        
        if not context.world_state_manager:
            error_msg = "World state manager not available"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}
        
        try:
            # Calculate time window
            current_time = time.time()
            cutoff_time = current_time - (time_window_hours * 3600)
            
            # Get world state
            world_state = context.world_state_manager.get_world_state_data()
            
            user_messages = []
            
            # Search Matrix channels
            if hasattr(world_state, 'matrix_channels'):
                for channel_id, channel_data in world_state.matrix_channels.items():
                    for message in getattr(channel_data, 'messages', []):
                        if (message.timestamp >= cutoff_time and 
                            (user_identifier.lower() in message.sender.lower() or
                             message.sender == user_identifier)):
                            user_messages.append({
                                "platform": "matrix",
                                "channel_id": channel_id,
                                "message": message,
                                "timestamp": message.timestamp
                            })
            
            # Search Farcaster channels
            if hasattr(world_state, 'farcaster_channels'):
                for channel_id, channel_data in world_state.farcaster_channels.items():
                    for message in getattr(channel_data, 'messages', []):
                        if (message.timestamp >= cutoff_time and 
                            (user_identifier.lower() in message.sender.lower() or
                             message.sender == user_identifier)):
                            user_messages.append({
                                "platform": "farcaster",
                                "channel_id": channel_id,
                                "message": message,
                                "timestamp": message.timestamp
                            })
            
            # Sort by timestamp (most recent first) and limit results
            user_messages.sort(key=lambda x: x["timestamp"], reverse=True)
            user_messages = user_messages[:max_messages]
            
            # Format results
            formatted_messages = []
            for msg_data in user_messages:
                message = msg_data["message"]
                formatted_messages.append({
                    "platform": msg_data["platform"],
                    "channel_id": msg_data["channel_id"],
                    "content": message.content,
                    "timestamp": message.timestamp,
                    "reply_to": getattr(message, 'reply_to', None),
                    "metadata": getattr(message, 'metadata', {})
                })
            
            result = {
                "status": "success",
                "user_identifier": user_identifier,
                "time_window_hours": time_window_hours,
                "messages_found": len(formatted_messages),
                "messages": formatted_messages,
                "timestamp": time.time()
            }
            
            logger.debug(f"User message search successful: {len(formatted_messages)} messages found for {user_identifier}")
            return result
            
        except Exception as e:
            error_msg = f"Error executing user message search: {str(e)}"
            logger.exception(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}


class CheckActionHistoryTool(ToolInterface):
    """
    Tool for checking if specific types of actions have been performed recently.
    """
    
    @property
    def name(self) -> str:
        return "check_action_history"
    
    @property
    def description(self) -> str:
        return "Check if specific types of actions have been performed recently. Useful for avoiding repetitive behavior."
    
    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action_type": {
                    "type": "string",
                    "description": "Type of action to check for (e.g., 'generate_image', 'like_farcaster_post', 'send_matrix_reply')"
                },
                "time_window_minutes": {
                    "type": "integer",
                    "description": "Time window in minutes to check (default: 60)",
                    "default": 60
                },
                "parameters_filter": {
                    "type": "object",
                    "description": "Optional filter for action parameters (e.g., {'channel_id': 'specific_channel'})",
                    "default": {}
                }
            },
            "required": ["action_type"]
        }
    
    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """
        Execute the action history check.
        """
        logger.debug(f"Executing tool '{self.name}' with params: {params}")
        
        action_type = params.get("action_type")
        time_window_minutes = params.get("time_window_minutes", 60)
        parameters_filter = params.get("parameters_filter", {})
        
        if not action_type:
            error_msg = "Missing required parameter: action_type"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}
        
        if not context.world_state_manager:
            error_msg = "World state manager not available"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}
        
        try:
            # Calculate time window
            current_time = time.time()
            cutoff_time = current_time - (time_window_minutes * 60)
            
            # Get action history from world state
            world_state = context.world_state_manager.get_world_state_data()
            action_history = getattr(world_state, 'action_history', [])
            
            # Filter actions by type, time, and parameters
            matching_actions = []
            for action in action_history:
                if (action.get('action_type') == action_type and
                    action.get('timestamp', 0) >= cutoff_time):
                    
                    # Check parameter filter if provided
                    if parameters_filter:
                        action_params = action.get('parameters', {})
                        match = True
                        for key, value in parameters_filter.items():
                            if action_params.get(key) != value:
                                match = False
                                break
                        if not match:
                            continue
                    
                    matching_actions.append(action)
            
            # Sort by timestamp (most recent first)
            matching_actions.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
            
            result = {
                "status": "success",
                "action_type": action_type,
                "time_window_minutes": time_window_minutes,
                "parameters_filter": parameters_filter,
                "actions_found": len(matching_actions),
                "has_recent_actions": len(matching_actions) > 0,
                "most_recent_action": matching_actions[0] if matching_actions else None,
                "all_matching_actions": matching_actions[:10],  # Limit to 10 most recent
                "timestamp": time.time()
            }
            
            logger.debug(f"Action history check successful: {len(matching_actions)} matching actions found")
            return result
            
        except Exception as e:
            error_msg = f"Error executing action history check: {str(e)}"
            logger.exception(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}
