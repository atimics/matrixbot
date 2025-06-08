#!/usr/bin/env python3
"""
User Profiling Tools

Tools for enhanced user profiling, sentiment analysis, and memory management.
Part of Initiative B: Enhanced User Profiling Implementation.
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional

from .base import ActionContext, ToolInterface
from ..core.world_state.structures import MemoryEntry, SentimentData

logger = logging.getLogger(__name__)


class SentimentAnalysisTool(ToolInterface):
    """Tool for analyzing and storing user sentiment from messages."""

    @property
    def name(self) -> str:
        return "analyze_user_sentiment"

    @property
    def description(self) -> str:
        return (
            "Analyze sentiment from a user's message and update their sentiment profile. "
            "This helps build better user understanding and context for future interactions."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "platform": {
                    "type": "string",
                    "enum": ["farcaster", "matrix"],
                    "description": "Platform where the message was sent"
                },
                "user_identifier": {
                    "type": "string", 
                    "description": "User's FID (for Farcaster) or user_id (for Matrix)"
                },
                "message_content": {
                    "type": "string",
                    "description": "The message content to analyze for sentiment"
                },
                "context": {
                    "type": "object",
                    "description": "Additional context about the message (optional)",
                    "properties": {
                        "topic": {"type": "string"},
                        "is_reply": {"type": "boolean"},
                        "channel_context": {"type": "string"}
                    }
                }
            },
            "required": ["platform", "user_identifier", "message_content"]
        }

    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """Execute sentiment analysis and store results."""
        try:
            platform = params.get("platform")
            user_identifier = params.get("user_identifier")
            message_content = params.get("message_content")
            msg_context = params.get("context", {})

            if not all([platform, user_identifier, message_content]):
                return {
                    "status": "failure",
                    "error": "Missing required parameters",
                    "timestamp": time.time()
                }

            # Simple rule-based sentiment analysis
            # In a production system, this could use ML models or external APIs
            sentiment_score, sentiment_label = self._analyze_sentiment(message_content)
            
            # Create sentiment data
            sentiment_data = SentimentData(
                current_sentiment=sentiment_label,
                sentiment_score=sentiment_score,
                message_count=1,
                last_interaction_time=time.time(),
                interaction_history=[{
                    "timestamp": time.time(),
                    "sentiment": sentiment_label,
                    "score": sentiment_score,
                    "context": msg_context
                }]
            )

            # Store in world state
            if context.world_state_manager:
                context.world_state_manager.update_user_sentiment(
                    platform, user_identifier, sentiment_data
                )
                
                logger.info(f"Updated sentiment for {platform} user {user_identifier}: {sentiment_label} ({sentiment_score:.2f})")
                
                return {
                    "status": "success",
                    "platform": platform,
                    "user_identifier": user_identifier,
                    "sentiment": {
                        "label": sentiment_label,
                        "score": sentiment_score
                    },
                    "timestamp": time.time()
                }
            else:
                return {
                    "status": "failure",
                    "error": "World state manager not available",
                    "timestamp": time.time()
                }

        except Exception as e:
            logger.error(f"Error in sentiment analysis: {e}", exc_info=True)
            return {
                "status": "failure",
                "error": str(e),
                "timestamp": time.time()
            }

    def _analyze_sentiment(self, text: str) -> tuple[float, str]:
        """Simple rule-based sentiment analysis."""
        text_lower = text.lower()
        
        # Positive indicators
        positive_words = [
            "good", "great", "awesome", "excellent", "amazing", "wonderful", 
            "fantastic", "love", "like", "enjoy", "happy", "excited", "thank"
        ]
        
        # Negative indicators
        negative_words = [
            "bad", "terrible", "awful", "hate", "dislike", "angry", "frustrated",
            "disappointed", "sad", "wrong", "problem", "issue", "broken"
        ]
        
        # Question indicators (neutral but engaged)
        question_indicators = ["?", "how", "what", "when", "where", "why", "which"]
        
        positive_count = sum(1 for word in positive_words if word in text_lower)
        negative_count = sum(1 for word in negative_words if word in text_lower)
        question_count = sum(1 for indicator in question_indicators if indicator in text_lower)
        
        # Calculate score
        score = (positive_count - negative_count) / max(len(text_lower.split()), 1)
        
        # Adjust for questions (slightly positive engagement)
        if question_count > 0:
            score += 0.1
            
        # Normalize to -1 to 1 range
        score = max(-1.0, min(1.0, score))
        
        # Determine label
        if score > 0.2:
            label = "positive"
        elif score < -0.2:
            label = "negative"
        else:
            label = "neutral"
            
        return score, label


class StoreUserMemoryTool(ToolInterface):
    """Tool for storing important user memories and context."""

    @property
    def name(self) -> str:
        return "store_user_memory"

    @property
    def description(self) -> str:
        return (
            "Store important information about a user for future reference. "
            "This helps build persistent user context and improves personalized interactions."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "platform": {
                    "type": "string",
                    "enum": ["farcaster", "matrix"],
                    "description": "Platform where the interaction occurred"
                },
                "user_identifier": {
                    "type": "string",
                    "description": "User's FID (for Farcaster) or user_id (for Matrix)"
                },
                "memory_type": {
                    "type": "string",
                    "enum": ["preference", "fact", "interest", "goal", "project", "skill"],
                    "description": "Type of memory being stored"
                },
                "content": {
                    "type": "string",
                    "description": "The memory content to store"
                },
                "importance": {
                    "type": "string",
                    "enum": ["high", "medium", "low"],
                    "default": "medium",
                    "description": "Importance level of this memory"
                },
                "context": {
                    "type": "object",
                    "description": "Additional context about when/where this was learned",
                    "properties": {
                        "conversation_topic": {"type": "string"},
                        "channel_id": {"type": "string"},
                        "related_message_id": {"type": "string"}
                    }
                }
            },
            "required": ["platform", "user_identifier", "memory_type", "content"]
        }

    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """Execute memory storage."""
        try:
            platform = params.get("platform")
            user_identifier = params.get("user_identifier")
            memory_type = params.get("memory_type")
            content = params.get("content")
            importance = params.get("importance", "medium")
            memory_context = params.get("context", {})

            if not all([platform, user_identifier, memory_type, content]):
                return {
                    "status": "failure",
                    "error": "Missing required parameters",
                    "timestamp": time.time()
                }

            # Create memory entry
            memory_entry = MemoryEntry(
                content=content,
                memory_type=memory_type,
                importance=importance,
                timestamp=time.time(),
                context=memory_context
            )

            # Store in world state
            if context.world_state_manager:
                # Create platform-specific user identifier
                user_platform_id = f"{platform}:{user_identifier}"
                
                context.world_state_manager.add_user_memory(user_platform_id, memory_entry)
                
                logger.info(f"Stored {memory_type} memory for {platform} user {user_identifier}: {content[:50]}...")
                
                return {
                    "status": "success",
                    "platform": platform,
                    "user_identifier": user_identifier,
                    "memory_type": memory_type,
                    "importance": importance,
                    "timestamp": time.time()
                }
            else:
                return {
                    "status": "failure",
                    "error": "World state manager not available",
                    "timestamp": time.time()
                }

        except Exception as e:
            logger.error(f"Error storing user memory: {e}", exc_info=True)
            return {
                "status": "failure",
                "error": str(e),
                "timestamp": time.time()
            }


class GetUserProfileTool(ToolInterface):
    """Tool for retrieving comprehensive user profile information."""

    @property
    def name(self) -> str:
        return "get_user_profile"

    @property
    def description(self) -> str:
        return (
            "Retrieve comprehensive profile information about a user including "
            "sentiment data, memories, and interaction history."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "platform": {
                    "type": "string",
                    "enum": ["farcaster", "matrix"],
                    "description": "Platform to get user profile from"
                },
                "user_identifier": {
                    "type": "string",
                    "description": "User's FID (for Farcaster) or user_id (for Matrix)"
                },
                "include_memories": {
                    "type": "boolean",
                    "default": True,
                    "description": "Whether to include user memories in the profile"
                },
                "memory_limit": {
                    "type": "integer",
                    "default": 10,
                    "description": "Maximum number of memories to retrieve"
                }
            },
            "required": ["platform", "user_identifier"]
        }

    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """Execute user profile retrieval."""
        try:
            platform = params.get("platform")
            user_identifier = params.get("user_identifier")
            include_memories = params.get("include_memories", True)
            memory_limit = params.get("memory_limit", 10)

            if not all([platform, user_identifier]):
                return {
                    "status": "failure",
                    "error": "Missing required parameters",
                    "timestamp": time.time()
                }

            if not context.world_state_manager:
                return {
                    "status": "failure",
                    "error": "World state manager not available",
                    "timestamp": time.time()
                }

            profile_data = {
                "platform": platform,
                "user_identifier": user_identifier,
                "basic_info": {},
                "sentiment": None,
                "memories": [],
                "interaction_stats": {},
                "timestamp": time.time()
            }

            # Get user details based on platform
            if platform == "farcaster":
                user_details = context.world_state_manager.get_or_create_farcaster_user(user_identifier)
                profile_data["basic_info"] = {
                    "fid": user_details.fid,
                    "username": user_details.username,
                    "display_name": user_details.display_name,
                    "bio": user_details.bio,
                    "follower_count": user_details.follower_count,
                    "following_count": user_details.following_count,
                    "power_badge": user_details.power_badge,
                    "verified_addresses": user_details.verified_addresses
                }
                
                # Add sentiment data
                if user_details.sentiment:
                    profile_data["sentiment"] = {
                        "current_sentiment": user_details.sentiment.current_sentiment,
                        "sentiment_score": user_details.sentiment.sentiment_score,
                        "message_count": user_details.sentiment.message_count,
                        "last_interaction": user_details.sentiment.last_interaction_time
                    }

            elif platform == "matrix":
                user_details = context.world_state_manager.get_or_create_matrix_user(user_identifier)
                profile_data["basic_info"] = {
                    "user_id": user_details.user_id,
                    "display_name": user_details.display_name,
                    "avatar_url": user_details.avatar_url
                }
                
                # Add sentiment data
                if user_details.sentiment:
                    profile_data["sentiment"] = {
                        "current_sentiment": user_details.sentiment.current_sentiment,
                        "sentiment_score": user_details.sentiment.sentiment_score,
                        "message_count": user_details.sentiment.message_count,
                        "last_interaction": user_details.sentiment.last_interaction_time
                    }

            # Get memories if requested
            if include_memories:
                user_platform_id = f"{platform}:{user_identifier}"
                memories = context.world_state_manager.get_user_memories(user_platform_id, memory_limit)
                
                profile_data["memories"] = [
                    {
                        "content": memory.content,
                        "memory_type": memory.memory_type,
                        "importance": memory.importance,
                        "timestamp": memory.timestamp,
                        "context": memory.context
                    }
                    for memory in memories
                ]

            logger.info(f"Retrieved profile for {platform} user {user_identifier}")
            
            return {
                "status": "success",
                "profile": profile_data
            }

        except Exception as e:
            logger.error(f"Error retrieving user profile: {e}", exc_info=True)
            return {
                "status": "failure",
                "error": str(e),
                "timestamp": time.time()
            }
