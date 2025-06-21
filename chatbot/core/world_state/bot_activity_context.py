#!/usr/bin/env python3
"""
Enhanced Bot Activity Context Builder

This module handles building enhanced bot activity context that combines regular 
activity tracking with immediate action context to prevent repetitive AI behavior.
"""

import logging
import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..structures import WorldStateData

logger = logging.getLogger(__name__)


class BotActivityContextBuilder:
    """Builds bot activity context to prevent repetitive AI responses and loops."""
    
    def __init__(self):
        self.last_action_result: Optional[Dict[str, Any]] = None
        self.logger = logging.getLogger(__name__)
    
    def set_last_action_result(self, action_result: Dict[str, Any]) -> None:
        """
        Set the last action result for AI self-awareness.
        
        This critical method stores information about the most recently executed action
        to prevent repetitive loops by giving the AI context about what it just did.
        
        Args:
            action_result: Dictionary containing:
                - action_type: The tool/action that was executed
                - parameters: Parameters passed to the action
                - success: Whether the action succeeded
                - result: The result/output of the action
                - timestamp: When the action was executed
                - reasoning: Why the AI chose this action
        """
        self.last_action_result = action_result
        logger.debug(f"Set last action result: {action_result.get('action_type')} -> "
                    f"{'SUCCESS' if action_result.get('success') else 'FAILED'}")
    
    def build_enhanced_bot_activity_context(self, world_state_data: 'WorldStateData') -> Dict[str, Any]:
        """
        Build enhanced bot activity context that combines regular activity tracking 
        with immediate action context to prevent repetitive AI behavior.
        
        This addresses the core issue where the AI doesn't remember what it just did,
        causing it to repeat the same analysis and come to the same conclusion.
        """
        try:
            # Get the existing bot activity context
            base_context = self._build_bot_activity_context(world_state_data)
            
            # Add immediate action context for anti-loop behavior
            immediate_context = self._build_immediate_action_context()
            
            # Combine both contexts
            enhanced_context = {
                **base_context,
                "immediate_action_context": immediate_context,
                "enhanced_features": {
                    "anti_loop_protection": True,
                    "last_action_awareness": immediate_context.get("status") != "no_recent_action",
                    "guidance_available": bool(immediate_context.get("guidance"))
                }
            }
            
            # Add high-level guidance based on both contexts
            if immediate_context.get("status") != "no_recent_action":
                enhanced_context["primary_guidance"] = immediate_context["guidance"]
            elif base_context.get("conversation_patterns"):
                # Use conversation pattern guidance if no immediate action
                pattern_guidance = []
                for channel_id, pattern_info in base_context["conversation_patterns"].items():
                    if pattern_info.get("recommendation"):
                        pattern_guidance.append(f"{pattern_info['channel_name']}: {pattern_info['recommendation']}")
                if pattern_guidance:
                    enhanced_context["primary_guidance"] = " | ".join(pattern_guidance)
            
            return enhanced_context
            
        except Exception as e:
            logger.error(f"Error building enhanced bot activity context: {e}", exc_info=True)
            # Fallback to basic context
            return self._build_bot_activity_context(world_state_data)
    
    def _build_immediate_action_context(self) -> Dict[str, Any]:
        """
        Build immediate action context to prevent repetitive AI behavior.
        
        This addresses the core issue where the AI doesn't remember what it just did,
        causing it to repeat the same analysis and come to the same conclusion.
        
        Returns:
            Dictionary with last action information and guidance for the AI
        """
        if not self.last_action_result:
            return {
                "status": "no_recent_action",
                "guidance": "This is your first action in this session. Analyze the situation and choose an appropriate action."
            }
        
        action_type = self.last_action_result.get("action_type", "unknown")
        success = self.last_action_result.get("success", False)
        result_preview = str(self.last_action_result.get("result", ""))[:200]
        reasoning = self.last_action_result.get("reasoning", "No reasoning provided")
        
        # Generate specific guidance based on the last action
        guidance = self._generate_action_specific_guidance(action_type, success, self.last_action_result)
        
        return {
            "last_action_type": action_type,
            "last_action_parameters": self.last_action_result.get("parameters", {}),
            "last_action_success": success,
            "last_action_result_preview": result_preview,
            "last_action_reasoning": reasoning,
            "seconds_since_last_action": time.time() - self.last_action_result.get("timestamp", time.time()),
            "guidance": guidance,
            "anti_loop_instruction": "CRITICAL: You just performed the action above. Do NOT repeat the same action unless the result indicates you should. Analyze the new information and decide the next logical step."
        }
    
    def _generate_action_specific_guidance(self, action_type: str, success: bool, action_result: Dict[str, Any]) -> str:
        """Generate specific guidance based on the type of action that was just performed."""
        if not success:
            return f"Your last action ({action_type}) failed. Consider why it failed and try a different approach or fix the issue."
        
        # Action-specific guidance for successful actions
        if action_type == "expand_node":
            node_path = action_result.get("parameters", {}).get("node_path", "unknown")
            return f"You just expanded node '{node_path}'. The new information is now available. Analyze it and respond appropriately instead of expanding another node."
        
        elif action_type == "get_trending_casts":
            return "You just retrieved trending casts. Review the trending content and decide if you should engage with any of it, or focus on other tasks."
        
        elif action_type in ["send_matrix_message", "send_farcaster_post", "send_farcaster_reply"]:
            return "You just sent a message. Wait for responses or focus on other activities rather than sending another message immediately."
        
        elif action_type == "search_casts":
            return "You just performed a search. Review the search results and engage with relevant content or move to other tasks."
        
        elif action_type == "collect_world_state":
            return "You just collected world state information. Use this fresh data to make informed decisions about what to do next."
        
        elif action_type == "wait":
            return "You just waited. Now analyze if there are any new developments that require action, or continue waiting if appropriate."
        
        # Add more specific guidance for common tools
        elif action_type in ["like_farcaster_post", "quote_farcaster_post"]:
            return "You just engaged with a post. Consider if you should continue engaging with other content or move to different activities."
            
        elif action_type in ["follow_farcaster_user", "unfollow_farcaster_user"]:
            return "You just modified your following status. Focus on other activities rather than immediately following/unfollowing more users."
            
        elif action_type in ["join_matrix_room", "leave_matrix_room"]:
            return "You just changed your room membership. Focus on participating in conversations or other activities."
            
        elif action_type in ["generate_image", "generate_video"]:
            return "You just generated media content. Consider sharing it or using it in conversations rather than generating more media immediately."
            
        elif action_type == "web_search":
            return "You just performed a web search. Use the search results to inform your next actions rather than searching again immediately."
            
        elif action_type in ["store_user_memory", "get_user_profile"]:
            return "You just worked with user data. Use this information to enhance your interactions rather than immediately accessing more user data."
        
        else:
            return f"You just completed '{action_type}'. Build on this action's results rather than repeating the same analysis or action type."
    
    def _build_bot_activity_context(self, world_state_data: 'WorldStateData') -> Dict[str, Any]:
        """
        Build enhanced bot activity context to prevent repetitive responses and loops.
        
        This method provides the AI with context about recent bot actions to help it:
        - Avoid sending duplicate or repetitive messages
        - Understand conversation flow and context
        - Prevent feedback loops
        - Make more informed decisions about when to respond
        """
        try:
            from datetime import datetime, timedelta
            
            current_time = time.time()
            recent_cutoff = current_time - 300  # Last 5 minutes
            
            bot_activity = {
                'recent_messages': [],
                'channel_activity': {},
                'conversation_patterns': {},
                'last_user_interactions': {},
                'repetitive_content_detection': {}
            }
            
            # Bot identifiers to check for
            bot_identifiers = ['@ratichat:chat.ratimics.com', 'ratichat']
            
            # Analyze recent bot messages across all channels
            for channel_type in ['matrix', 'farcaster']:
                if channel_type not in world_state_data.channels:
                    continue
                    
                for channel_id, channel_data in world_state_data.channels[channel_type].items():
                    messages = channel_data.recent_messages if hasattr(channel_data, 'recent_messages') else []
                    if not messages:
                        continue
                    
                    channel_name = channel_data.name if hasattr(channel_data, 'name') else channel_id
                    bot_messages_in_channel = []
                    user_messages_in_channel = []
                    last_user_message_time = 0
                    
                    # Analyze messages in this channel
                    for msg in messages:
                        msg_time = msg.timestamp if hasattr(msg, 'timestamp') else 0
                        sender = msg.sender if hasattr(msg, 'sender') else ''
                        content = msg.content.strip() if hasattr(msg, 'content') and msg.content else ''
                        
                        if sender in bot_identifiers:
                            # This is a bot message
                            if msg_time > recent_cutoff:
                                bot_messages_in_channel.append({
                                    'timestamp': msg_time,
                                    'content': content[:150],  # First 150 chars
                                    'channel': channel_name,
                                    'channel_id': channel_id,
                                    'channel_type': channel_type
                                })
                        else:
                            # This is a user message
                            user_messages_in_channel.append(msg)
                            if msg_time > last_user_message_time:
                                last_user_message_time = msg_time
                    
                    # Store channel-specific activity
                    if bot_messages_in_channel:
                        bot_activity['channel_activity'][channel_id] = {
                            'channel_name': channel_name,
                            'channel_type': channel_type,
                            'recent_bot_messages': len(bot_messages_in_channel),
                            'last_bot_message_time': max(msg['timestamp'] for msg in bot_messages_in_channel),
                            'last_user_message_time': last_user_message_time,
                            'time_since_last_user_message': current_time - last_user_message_time if last_user_message_time > 0 else None
                        }
                        
                        # Add to overall recent messages
                        bot_activity['recent_messages'].extend(bot_messages_in_channel)
                    
                    # Track last user interaction per channel
                    if last_user_message_time > 0:
                        bot_activity['last_user_interactions'][channel_id] = {
                            'channel_name': channel_name,
                            'last_user_message_time': last_user_message_time,
                            'time_since_last_user': current_time - last_user_message_time
                        }
                    
                    # Detect repetitive content patterns
                    recent_bot_content = [msg['content'] for msg in bot_messages_in_channel[-5:]]  # Last 5 bot messages
                    if len(recent_bot_content) >= 2:
                        # Check for similar content
                        similar_messages = []
                        for i, content1 in enumerate(recent_bot_content):
                            for j, content2 in enumerate(recent_bot_content[i+1:], i+1):
                                if self._messages_are_similar(content1, content2):
                                    similar_messages.append((i, j, content1[:100]))
                        
                        if similar_messages:
                            bot_activity['repetitive_content_detection'][channel_id] = {
                                'channel_name': channel_name,
                                'similar_message_pairs': len(similar_messages),
                                'examples': similar_messages[:3]  # First 3 examples
                            }
            
            # Sort recent messages by timestamp (most recent first)
            bot_activity['recent_messages'].sort(key=lambda x: x['timestamp'], reverse=True)
            bot_activity['recent_messages'] = bot_activity['recent_messages'][:10]  # Keep only last 10
            
            # Generate conversation pattern analysis
            for channel_id, activity in bot_activity['channel_activity'].items():
                pattern_flags = []
                
                # Check for potential conversation loops
                if activity['recent_bot_messages'] >= 3:
                    pattern_flags.append('high_bot_activity')
                
                if activity['time_since_last_user_message'] and activity['time_since_last_user_message'] > 600:  # 10 minutes
                    pattern_flags.append('no_recent_user_response')
                
                if channel_id in bot_activity['repetitive_content_detection']:
                    pattern_flags.append('repetitive_content')
                
                if pattern_flags:
                    bot_activity['conversation_patterns'][channel_id] = {
                        'channel_name': activity['channel_name'],
                        'pattern_flags': pattern_flags,
                        'recommendation': self._get_conversation_recommendation(pattern_flags)
                    }
            
            # Generate summary
            total_recent_messages = len(bot_activity['recent_messages'])
            channels_with_activity = len(bot_activity['channel_activity'])
            channels_with_patterns = len(bot_activity['conversation_patterns'])
            
            summary = f"Bot sent {total_recent_messages} messages recently across {channels_with_activity} channels"
            if channels_with_patterns > 0:
                summary += f". {channels_with_patterns} channels show conversation patterns requiring attention"
            
            return {
                'recent_bot_messages': bot_activity['recent_messages'],
                'channel_activity_summary': bot_activity['channel_activity'],
                'conversation_patterns': bot_activity['conversation_patterns'],
                'last_user_interactions': bot_activity['last_user_interactions'],
                'repetitive_content_alerts': bot_activity['repetitive_content_detection'],
                'activity_summary': summary,
                'total_recent_messages': total_recent_messages,
                'analysis_timestamp': current_time
            }
            
        except Exception as e:
            self.logger.error(f"Error building bot activity context: {e}")
            return {
                'recent_bot_messages': [],
                'channel_activity_summary': {},
                'conversation_patterns': {},
                'last_user_interactions': {},
                'repetitive_content_alerts': {},
                'activity_summary': "Unable to analyze recent bot activity",
                'total_recent_messages': 0,
                'analysis_timestamp': time.time(),
                'error': str(e)
            }
    
    def _messages_are_similar(self, content1: str, content2: str, threshold: float = 0.7) -> bool:
        """Check if two message contents are similar (basic similarity check)."""
        if not content1 or not content2:
            return False
        
        # Simple similarity check - can be enhanced with more sophisticated algorithms
        content1_lower = content1.lower().strip()
        content2_lower = content2.lower().strip()
        
        # Exact match
        if content1_lower == content2_lower:
            return True
        
        # Check if one is a substring of the other (for similar prompts)
        if len(content1_lower) > 20 and len(content2_lower) > 20:
            shorter = content1_lower if len(content1_lower) < len(content2_lower) else content2_lower
            longer = content2_lower if len(content1_lower) < len(content2_lower) else content1_lower
            
            if shorter in longer:
                return True
        
        # Basic word overlap check
        words1 = set(content1_lower.split())
        words2 = set(content2_lower.split())
        
        if len(words1) > 3 and len(words2) > 3:  # Only for messages with substantial content
            overlap = len(words1.intersection(words2))
            total_unique = len(words1.union(words2))
            similarity = overlap / total_unique if total_unique > 0 else 0
            return similarity >= threshold
        
        return False
    
    def _get_conversation_recommendation(self, pattern_flags: List[str]) -> str:
        """Generate recommendation based on conversation patterns."""
        if 'repetitive_content' in pattern_flags and 'no_recent_user_response' in pattern_flags:
            return "WAIT - Avoid sending more messages until user responds"
        elif 'repetitive_content' in pattern_flags:
            return "VARY_RESPONSE - Try a different approach or wait for user input"
        elif 'high_bot_activity' in pattern_flags and 'no_recent_user_response' in pattern_flags:
            return "PAUSE - Consider waiting for user engagement"
        elif 'high_bot_activity' in pattern_flags:
            return "MODERATE - Reduce message frequency"
        else:
            return "NORMAL - Continue normal conversation flow"
