#!/usr/bin/env python3
"""
Engagement Strategies for Proactive Conversation Management

This module defines different strategies for engaging with conversation 
opportunities, allowing the system to adapt its approach based on context,
platform, and community dynamics.
"""

import logging
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .proactive_engine import ConversationOpportunity, EngagementPlan

logger = logging.getLogger(__name__)


class EngagementStrategy(ABC):
    """Base class for proactive engagement strategies."""
    
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.success_rate = 0.0  # Track success rate for learning
        self.usage_count = 0
    
    @abstractmethod
    def can_handle(self, opportunity: ConversationOpportunity) -> bool:
        """Check if this strategy can handle the given opportunity."""
        pass
    
    @abstractmethod
    def generate_engagement_plan(self, opportunity: ConversationOpportunity) -> EngagementPlan:
        """Generate an engagement plan for the opportunity."""
        pass
    
    def update_success_rate(self, success: bool) -> None:
        """Update the strategy's success rate tracking."""
        self.usage_count += 1
        if success:
            self.success_rate = ((self.success_rate * (self.usage_count - 1)) + 1.0) / self.usage_count
        else:
            self.success_rate = (self.success_rate * (self.usage_count - 1)) / self.usage_count


class TrendingTopicStrategy(EngagementStrategy):
    """Strategy for engaging with trending topics."""
    
    def __init__(self):
        super().__init__(
            name="trending_topic",
            description="Engage with trending topics by providing insights, asking questions, or sharing relevant content"
        )
    
    def can_handle(self, opportunity: ConversationOpportunity) -> bool:
        return opportunity.opportunity_type == "trending_topic"
    
    def generate_engagement_plan(self, opportunity: ConversationOpportunity) -> EngagementPlan:
        topic = opportunity.context.get("topic", "unknown")
        channels = opportunity.context.get("channels_involved", [])
        trend_strength = opportunity.context.get("trend_strength", 0.5)
        
        # Choose engagement approach based on trend strength
        if trend_strength > 0.8:
            # Strong trend - join the conversation actively
            action_sequence = [
                {
                    "action_type": "research_topic",
                    "parameters": {"query": topic, "depth": "comprehensive"},
                    "reasoning": f"Research trending topic '{topic}' for informed engagement"
                },
                {
                    "action_type": "generate_insight_content",
                    "parameters": {
                        "topic": topic,
                        "content_type": "insightful_perspective",
                        "tone": "engaging"
                    },
                    "reasoning": "Generate valuable insights to contribute to trending discussion"
                }
            ]
            
            # Add platform-specific sharing actions
            if "farcaster" in [ch.get("platform") for ch in channels]:
                action_sequence.append({
                    "action_type": "send_farcaster_cast",
                    "parameters": {
                        "content": "{{generated_content}}",
                        "include_research_link": True
                    },
                    "reasoning": "Share insights on Farcaster to engage with trending topic"
                })
            
            if "matrix" in [ch.get("platform") for ch in channels]:
                action_sequence.append({
                    "action_type": "send_matrix_message",
                    "parameters": {
                        "content": "{{generated_content}}",
                        "format": "markdown"
                    },
                    "reasoning": "Share detailed analysis in Matrix room"
                })
                
        else:
            # Moderate trend - ask engaging questions
            action_sequence = [
                {
                    "action_type": "generate_engaging_question",
                    "parameters": {
                        "topic": topic,
                        "question_type": "thought_provoking"
                    },
                    "reasoning": f"Generate engaging question about '{topic}' to stimulate discussion"
                },
                {
                    "action_type": "post_question",
                    "parameters": {
                        "content": "{{generated_question}}",
                        "platforms": ["farcaster", "matrix"]
                    },
                    "reasoning": "Post question to encourage community engagement"
                }
            ]
        
        return EngagementPlan(
            plan_id=f"trending_{opportunity.opportunity_id}_{int(time.time())}",
            opportunity=opportunity,
            strategy_name=self.name,
            action_sequence=action_sequence,
            timing_preference="immediate",
            success_metrics={
                "engagement_responses": 0,
                "follow_up_conversations": 0,
                "community_participation": 0
            },
            estimated_impact=8 if trend_strength > 0.8 else 6,
            confidence=0.7 + (trend_strength * 0.2)
        )


class UserMilestoneStrategy(EngagementStrategy):
    """Strategy for celebrating user milestones and achievements."""
    
    def __init__(self):
        super().__init__(
            name="user_milestone",
            description="Celebrate user achievements and milestones to build community connection"
        )
    
    def can_handle(self, opportunity: ConversationOpportunity) -> bool:
        return opportunity.opportunity_type == "user_milestone"
    
    def generate_engagement_plan(self, opportunity: ConversationOpportunity) -> EngagementPlan:
        user_id = opportunity.user_id
        username = opportunity.context.get("username", user_id)
        milestone_type = opportunity.context.get("milestone_type", "achievement")
        milestone_data = opportunity.context.get("milestone_data", {})
        platform = opportunity.platform
        
        action_sequence = []
        
        # Generate personalized congratulations
        if milestone_type == "follower_milestone":
            follower_count = milestone_data.get("followers", 0)
            action_sequence.append({
                "action_type": "generate_celebration_message",
                "parameters": {
                    "user": username,
                    "milestone": f"{follower_count} followers",
                    "tone": "celebratory",
                    "include_emoji": True
                },
                "reasoning": f"Generate congratulations for {username} reaching {follower_count} followers"
            })
        elif milestone_type == "activity_milestone":
            message_count = milestone_data.get("message_count", 0)
            action_sequence.append({
                "action_type": "generate_appreciation_message",
                "parameters": {
                    "user": username,
                    "contribution": f"{message_count} community messages",
                    "tone": "appreciative"
                },
                "reasoning": f"Appreciate {username}'s active community participation"
            })
        
        # Add platform-specific delivery
        if platform == "farcaster":
            action_sequence.append({
                "action_type": "send_farcaster_reply",
                "parameters": {
                    "content": "{{generated_message}}",
                    "mention_user": username
                },
                "reasoning": "Publicly celebrate milestone on Farcaster"
            })
        elif platform == "matrix":
            action_sequence.append({
                "action_type": "send_matrix_message",
                "parameters": {
                    "content": "{{generated_message}}",
                    "mention_user": user_id
                },
                "reasoning": "Acknowledge milestone in Matrix room"
            })
        
        # Consider follow-up actions
        action_sequence.append({
            "action_type": "store_user_achievement",
            "parameters": {
                "user_id": user_id,
                "achievement": milestone_type,
                "details": milestone_data,
                "platform": platform
            },
            "reasoning": "Store achievement in user memory for future reference"
        })
        
        return EngagementPlan(
            plan_id=f"milestone_{opportunity.opportunity_id}_{int(time.time())}",
            opportunity=opportunity,
            strategy_name=self.name,
            action_sequence=action_sequence,
            timing_preference="immediate",
            success_metrics={
                "user_response": 0,
                "community_reaction": 0,
                "relationship_building": 0
            },
            estimated_impact=7,
            confidence=0.8
        )


class QuietChannelStrategy(EngagementStrategy):
    """Strategy for re-engaging quiet channels."""
    
    def __init__(self):
        super().__init__(
            name="quiet_channel",
            description="Re-engage quiet channels with conversation starters or interesting content"
        )
    
    def can_handle(self, opportunity: ConversationOpportunity) -> bool:
        return opportunity.opportunity_type == "quiet_channel"
    
    def generate_engagement_plan(self, opportunity: ConversationOpportunity) -> EngagementPlan:
        channel_id = opportunity.channel_id
        channel_name = opportunity.context.get("channel_name", "channel")
        silence_duration = opportunity.context.get("silence_duration", 0)
        platform = opportunity.platform
        
        # Choose strategy based on how long the channel has been quiet
        if silence_duration > 7200:  # More than 2 hours
            # Share interesting content or news
            action_sequence = [
                {
                    "action_type": "research_trending_news",
                    "parameters": {
                        "topics": ["crypto", "technology", "community"],
                        "freshness": "today"
                    },
                    "reasoning": "Find interesting recent news to share with quiet community"
                },
                {
                    "action_type": "generate_content_summary",
                    "parameters": {
                        "content_type": "news_summary",
                        "tone": "engaging",
                        "include_discussion_prompt": True
                    },
                    "reasoning": "Create engaging summary with discussion prompt"
                }
            ]
        elif silence_duration > 3600:  # More than 1 hour
            # Ask an engaging question
            action_sequence = [
                {
                    "action_type": "generate_discussion_starter",
                    "parameters": {
                        "topic_type": "community_interest",
                        "question_style": "open_ended"
                    },
                    "reasoning": "Generate question to restart community discussion"
                }
            ]
        else:
            # Light engagement with topic continuation
            action_sequence = [
                {
                    "action_type": "analyze_recent_conversation",
                    "parameters": {
                        "channel_id": channel_id,
                        "analysis_type": "conversation_themes"
                    },
                    "reasoning": "Analyze recent conversation to find continuation opportunities"
                },
                {
                    "action_type": "generate_topic_continuation",
                    "parameters": {
                        "base_on": "recent_themes",
                        "style": "thoughtful_addition"
                    },
                    "reasoning": "Add thoughtful perspective to continue recent discussion"
                }
            ]
        
        # Add platform-specific delivery
        if platform == "farcaster":
            action_sequence.append({
                "action_type": "send_farcaster_cast",
                "parameters": {
                    "content": "{{generated_content}}",
                    "channel": channel_id
                },
                "reasoning": f"Re-engage {channel_name} with fresh content"
            })
        elif platform == "matrix":
            action_sequence.append({
                "action_type": "send_matrix_message",
                "parameters": {
                    "room_id": channel_id,
                    "content": "{{generated_content}}"
                },
                "reasoning": f"Restart conversation in {channel_name}"
            })
        
        return EngagementPlan(
            plan_id=f"quiet_{opportunity.opportunity_id}_{int(time.time())}",
            opportunity=opportunity,
            strategy_name=self.name,
            action_sequence=action_sequence,
            timing_preference="optimal_time",
            success_metrics={
                "conversation_restart": 0,
                "community_engagement": 0,
                "sustained_activity": 0
            },
            estimated_impact=6,
            confidence=0.6
        )


class NewUserWelcomeStrategy(EngagementStrategy):
    """Strategy for welcoming new users."""
    
    def __init__(self):
        super().__init__(
            name="new_user_welcome",
            description="Welcome new users and help them integrate into the community"
        )
    
    def can_handle(self, opportunity: ConversationOpportunity) -> bool:
        return opportunity.opportunity_type == "new_user_welcome"
    
    def generate_engagement_plan(self, opportunity: ConversationOpportunity) -> EngagementPlan:
        new_user = opportunity.context.get("new_user", "user")
        channel_name = opportunity.context.get("channel_name", "community")
        platform = opportunity.platform
        
        action_sequence = [
            {
                "action_type": "generate_welcome_message",
                "parameters": {
                    "user": new_user,
                    "community": channel_name,
                    "tone": "warm",
                    "include_resources": True
                },
                "reasoning": f"Generate welcoming message for new user {new_user}"
            }
        ]
        
        # Add platform-specific delivery
        if platform == "farcaster":
            action_sequence.append({
                "action_type": "send_farcaster_reply",
                "parameters": {
                    "content": "{{welcome_message}}",
                    "mention_user": new_user
                },
                "reasoning": "Welcome new user on Farcaster"
            })
        elif platform == "matrix":
            action_sequence.append({
                "action_type": "send_matrix_message",
                "parameters": {
                    "content": "{{welcome_message}}",
                    "mention_user": new_user
                },
                "reasoning": "Welcome new user in Matrix room"
            })
        
        # Store user info for future reference
        action_sequence.append({
            "action_type": "create_user_profile",
            "parameters": {
                "user_id": new_user,
                "platform": platform,
                "first_seen": "{{current_time}}",
                "status": "new_user"
            },
            "reasoning": "Create user profile for future personalized interactions"
        })
        
        return EngagementPlan(
            plan_id=f"welcome_{opportunity.opportunity_id}_{int(time.time())}",
            opportunity=opportunity,
            strategy_name=self.name,
            action_sequence=action_sequence,
            timing_preference="immediate",
            success_metrics={
                "user_response": 0,
                "integration_success": 0,
                "continued_participation": 0
            },
            estimated_impact=7,
            confidence=0.8
        )


class CrossPlatformBridgeStrategy(EngagementStrategy):
    """Strategy for bridging conversations across platforms."""
    
    def __init__(self):
        super().__init__(
            name="cross_platform_bridge",
            description="Bridge interesting conversations between Matrix and Farcaster"
        )
    
    def can_handle(self, opportunity: ConversationOpportunity) -> bool:
        return opportunity.opportunity_type == "cross_platform_bridge"
    
    def generate_engagement_plan(self, opportunity: ConversationOpportunity) -> EngagementPlan:
        topic = opportunity.context.get("topic", "discussion")
        source_platform = opportunity.context.get("source_platform", "unknown")
        target_platform = opportunity.context.get("target_platform", "unknown")
        relevance_score = opportunity.context.get("relevance_score", 0.5)
        
        action_sequence = [
            {
                "action_type": "analyze_cross_platform_context",
                "parameters": {
                    "topic": topic,
                    "source_platform": source_platform,
                    "target_platform": target_platform
                },
                "reasoning": f"Analyze context for bridging '{topic}' discussion between platforms"
            },
            {
                "action_type": "generate_bridge_content",
                "parameters": {
                    "topic": topic,
                    "adaptation": f"{source_platform}_to_{target_platform}",
                    "relevance": relevance_score
                },
                "reasoning": "Generate content adapted for target platform"
            }
        ]
        
        # Add target platform delivery
        if target_platform == "farcaster":
            action_sequence.append({
                "action_type": "send_farcaster_cast",
                "parameters": {
                    "content": "{{bridge_content}}",
                    "reference_source": source_platform
                },
                "reasoning": "Share Matrix discussion on Farcaster"
            })
        elif target_platform == "matrix":
            action_sequence.append({
                "action_type": "send_matrix_message",
                "parameters": {
                    "content": "{{bridge_content}}",
                    "reference_source": source_platform
                },
                "reasoning": "Share Farcaster discussion in Matrix"
            })
        
        return EngagementPlan(
            plan_id=f"bridge_{opportunity.opportunity_id}_{int(time.time())}",
            opportunity=opportunity,
            strategy_name=self.name,
            action_sequence=action_sequence,
            timing_preference="optimal_time",
            success_metrics={
                "cross_platform_engagement": 0,
                "conversation_bridge_success": 0,
                "community_connection": 0
            },
            estimated_impact=int(6 + (relevance_score * 3)),
            confidence=0.5 + (relevance_score * 0.3)
        )


class ContentSharingStrategy(EngagementStrategy):
    """Strategy for sharing relevant content and research."""
    
    def __init__(self):
        super().__init__(
            name="content_sharing",
            description="Share relevant research, insights, or content in response to community questions"
        )
    
    def can_handle(self, opportunity: ConversationOpportunity) -> bool:
        return opportunity.opportunity_type == "content_sharing"
    
    def generate_engagement_plan(self, opportunity: ConversationOpportunity) -> EngagementPlan:
        original_message = opportunity.context.get("original_message", "")
        sender = opportunity.context.get("sender", "user")
        channel_id = opportunity.channel_id
        platform = opportunity.platform
        
        action_sequence = [
            {
                "action_type": "analyze_information_need",
                "parameters": {
                    "message": original_message,
                    "context": "community_question"
                },
                "reasoning": "Analyze what information would be most helpful"
            },
            {
                "action_type": "research_comprehensive_answer",
                "parameters": {
                    "query": "{{analyzed_need}}",
                    "depth": "detailed",
                    "sources": "multiple"
                },
                "reasoning": "Research comprehensive answer to community question"
            },
            {
                "action_type": "generate_helpful_response",
                "parameters": {
                    "research_data": "{{research_results}}",
                    "tone": "helpful",
                    "include_sources": True,
                    "mention_user": sender
                },
                "reasoning": "Generate helpful response with researched information"
            }
        ]
        
        # Add platform-specific delivery
        if platform == "farcaster":
            action_sequence.append({
                "action_type": "send_farcaster_reply",
                "parameters": {
                    "content": "{{helpful_response}}",
                    "reply_to": opportunity.context.get("message_id")
                },
                "reasoning": "Reply with helpful information on Farcaster"
            })
        elif platform == "matrix":
            action_sequence.append({
                "action_type": "send_matrix_reply",
                "parameters": {
                    "content": "{{helpful_response}}",
                    "reply_to": opportunity.context.get("message_id")
                },
                "reasoning": "Reply with researched answer in Matrix"
            })
        
        return EngagementPlan(
            plan_id=f"content_{opportunity.opportunity_id}_{int(time.time())}",
            opportunity=opportunity,
            strategy_name=self.name,
            action_sequence=action_sequence,
            timing_preference="immediate",
            success_metrics={
                "information_helpfulness": 0,
                "user_satisfaction": 0,
                "knowledge_sharing": 0
            },
            estimated_impact=6,
            confidence=0.7
        )


class AutoImageAnalysisStrategy(EngagementStrategy):
    """Strategy for automatically analyzing images in conversations."""
    
    def __init__(self):
        super().__init__(
            name="auto_image_analysis",
            description="Automatically analyze images posted in conversations to provide context and enable discussion"
        )
    
    def can_handle(self, opportunity: ConversationOpportunity) -> bool:
        """Check if this strategy can handle image analysis opportunities."""
        return opportunity.opportunity_type == "auto_image_analysis"
    
    def generate_engagement_plan(self, opportunity: ConversationOpportunity) -> EngagementPlan:
        """Generate a plan to analyze an image and potentially respond."""
        context = opportunity.context
        image_url = context.get("image_url")
        sender = context.get("sender")
        message_content = context.get("message_content", "")
        
        # Determine analysis approach based on context
        if message_content.strip():
            # If there's accompanying text, analyze in context
            analysis_prompt = f"Analyze this image in the context of the message: '{message_content}'"
        else:
            # If it's just an image, provide general description
            analysis_prompt = "Describe this image and identify any interesting or notable elements"
        
        action_sequence = [
            {
                "tool": "describe_image",
                "parameters": {
                    "image_url": image_url,
                    "prompt_text": analysis_prompt
                },
                "rationale": f"Automatically analyze image from {sender}"
            }
        ]
        
        # Optionally add a follow-up response if the image is particularly interesting
        # This would be determined by the describe_image result
        
        return EngagementPlan(
            plan_id=f"auto_analysis_{opportunity.opportunity_id}",
            opportunity=opportunity,
            strategy_name=self.name,
            action_sequence=action_sequence,
            timing_preference="immediate",  # Process images quickly
            success_metrics={
                "image_analyzed": True,
                "response_relevance": "high",
                "community_engagement": "optional"
            },
            estimated_impact=5,  # Medium impact - provides context
            confidence=0.8  # High confidence in analysis capability
        )


class EngagementStrategyRegistry:
    """Registry for managing engagement strategies."""
    
    def __init__(self):
        self.strategies: Dict[str, EngagementStrategy] = {}
        self._register_default_strategies()
    
    def _register_default_strategies(self):
        """Register the default engagement strategies."""
        default_strategies = [
            TrendingTopicStrategy(),
            UserMilestoneStrategy(),
            QuietChannelStrategy(),
            NewUserWelcomeStrategy(),
            CrossPlatformBridgeStrategy(),
            ContentSharingStrategy(),
            AutoImageAnalysisStrategy()
        ]
        
        for strategy in default_strategies:
            self.register_strategy(strategy)
    
    def register_strategy(self, strategy: EngagementStrategy):
        """Register a new engagement strategy."""
        self.strategies[strategy.name] = strategy
        logger.debug(f"EngagementRegistry: Registered strategy '{strategy.name}'")
    
    def get_strategy(self, name: str) -> Optional[EngagementStrategy]:
        """Get a strategy by name."""
        return self.strategies.get(name)
    
    def find_suitable_strategies(
        self, opportunity: ConversationOpportunity
    ) -> List[EngagementStrategy]:
        """Find all strategies that can handle the given opportunity."""
        suitable_strategies = []
        
        for strategy in self.strategies.values():
            if strategy.can_handle(opportunity):
                suitable_strategies.append(strategy)
        
        # Sort by success rate (best performing strategies first)
        suitable_strategies.sort(key=lambda s: s.success_rate, reverse=True)
        
        return suitable_strategies
    
    def get_best_strategy(
        self, opportunity: ConversationOpportunity
    ) -> Optional[EngagementStrategy]:
        """Get the best strategy for the given opportunity."""
        suitable_strategies = self.find_suitable_strategies(opportunity)
        
        if not suitable_strategies:
            return None
        
        # Return the strategy with the highest success rate
        # If multiple strategies have the same success rate, use the one with more usage
        best_strategy = suitable_strategies[0]
        for strategy in suitable_strategies[1:]:
            if (strategy.success_rate > best_strategy.success_rate or 
                (strategy.success_rate == best_strategy.success_rate and 
                 strategy.usage_count > best_strategy.usage_count)):
                best_strategy = strategy
        
        return best_strategy
    
    def update_strategy_performance(self, strategy_name: str, success: bool):
        """Update a strategy's performance metrics."""
        if strategy_name in self.strategies:
            self.strategies[strategy_name].update_success_rate(success)
            logger.debug(f"EngagementRegistry: Updated performance for '{strategy_name}': success={success}")
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get performance summary for all strategies."""
        summary = {}
        for name, strategy in self.strategies.items():
            summary[name] = {
                "success_rate": strategy.success_rate,
                "usage_count": strategy.usage_count,
                "description": strategy.description
            }
        return summary
