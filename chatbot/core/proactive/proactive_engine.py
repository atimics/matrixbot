#!/usr/bin/env python3
"""
Proactive Conversation Engine

Core engine responsible for detecting conversation opportunities and 
initiating proactive engagement based on world state changes, user 
activity patterns, and community dynamics.
"""

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set
from abc import ABC, abstractmethod

from ..world_state.structures import WorldStateData, Message, Channel

logger = logging.getLogger(__name__)


@dataclass
class ConversationOpportunity:
    """Represents a detected opportunity for proactive conversation."""
    opportunity_id: str
    opportunity_type: str  # "trending_topic", "user_milestone", "community_event", "follow_up", etc.
    priority: int  # 1-10, where 10 is highest priority
    context: Dict[str, Any]  # Context data for the opportunity
    platform: str  # "matrix", "farcaster", "cross_platform"
    channel_id: Optional[str] = None
    user_id: Optional[str] = None
    expires_at: Optional[float] = None  # Timestamp when opportunity expires
    reasoning: str = ""  # Why this is an opportunity
    
    def is_expired(self) -> bool:
        """Check if this opportunity has expired."""
        if not self.expires_at:
            return False
        return time.time() > self.expires_at


@dataclass
class EngagementPlan:
    """Plan for engaging with a conversation opportunity."""
    plan_id: str
    opportunity: ConversationOpportunity
    strategy_name: str
    action_sequence: List[Dict[str, Any]]  # Sequence of actions to take
    timing_preference: str  # "immediate", "delayed", "optimal_time"
    success_metrics: Dict[str, Any]  # How to measure success
    estimated_impact: int  # 1-10 expected community impact
    confidence: float  # 0.0-1.0 confidence in plan success


class ProactiveConversationEngine:
    """
    Core engine for proactive conversation management.
    
    Responsibilities:
    - Monitor world state for conversation opportunities
    - Evaluate opportunities based on multiple criteria
    - Generate engagement plans for promising opportunities
    - Track engagement success and adapt strategies
    """
    
    def __init__(self, world_state_manager, context_manager=None, ai_engine=None):
        self.world_state_manager = world_state_manager
        self.context_manager = context_manager
        self.ai_engine = ai_engine
        
        # Opportunity detection and tracking
        self.active_opportunities: Dict[str, ConversationOpportunity] = {}
        self.opportunity_history: List[ConversationOpportunity] = []
        self.engagement_plans: Dict[str, EngagementPlan] = {}
        
        # Configuration
        self.max_active_opportunities = 10
        self.opportunity_cooldown = 300  # 5 minutes between similar opportunities
        self.min_priority_threshold = 5  # Only consider opportunities with priority >= 5
        
        # Tracking and learning
        self.recent_engagements: Set[str] = set()  # Recent channel/user engagements
        self.engagement_success_history: List[Dict[str, Any]] = []
        
        logger.info("ProactiveConversationEngine initialized")
    
    def analyze_world_state_for_opportunities(
        self, world_state_data: WorldStateData
    ) -> List[ConversationOpportunity]:
        """
        Analyze current world state to identify proactive conversation opportunities.
        
        Returns:
            List of detected conversation opportunities, sorted by priority
        """
        opportunities = []
        current_time = time.time()
        
        try:
            # 1. Analyze channel activity patterns
            opportunities.extend(self._detect_activity_opportunities(world_state_data))
            
            # 2. Look for trending topics and discussions
            opportunities.extend(self._detect_trending_opportunities(world_state_data))
            
            # 3. Identify user milestone opportunities
            opportunities.extend(self._detect_user_milestone_opportunities(world_state_data))
            
            # 4. Check for follow-up opportunities from previous conversations
            opportunities.extend(self._detect_follow_up_opportunities(world_state_data))
            
            # 5. Look for cross-platform conversation bridging opportunities
            opportunities.extend(self._detect_cross_platform_opportunities(world_state_data))
            
            # 6. Detect community engagement opportunities
            opportunities.extend(self._detect_community_opportunities(world_state_data))
            
            # 7. Detect automatic image processing opportunities
            opportunities.extend(self._detect_image_analysis_opportunities(world_state_data))
            
            # Filter and prioritize opportunities
            opportunities = self._filter_and_prioritize_opportunities(opportunities, current_time)
            
            logger.info(f"ProactiveEngine: Detected {len(opportunities)} conversation opportunities")
            return opportunities
            
        except Exception as e:
            logger.error(f"Error analyzing world state for opportunities: {e}", exc_info=True)
            return []
    
    def _detect_activity_opportunities(self, world_state_data: WorldStateData) -> List[ConversationOpportunity]:
        """Detect opportunities based on unusual activity patterns."""
        opportunities = []
        current_time = time.time()
        
        # Handle nested structure: channels[platform][channel_id]
        for platform, platform_channels in world_state_data.channels.items():
            if not isinstance(platform_channels, dict):
                continue
            for channel_id, channel in platform_channels.items():
                if not channel.recent_messages:
                    continue
                    
                # Look for channels with sudden activity increases
                recent_activity = self._analyze_channel_activity_pattern(channel)
                
                if recent_activity.get("activity_spike", False):
                    opportunities.append(ConversationOpportunity(
                        opportunity_id=f"activity_spike_{channel_id}_{int(current_time)}",
                        opportunity_type="activity_spike",
                        priority=7,
                        context={
                            "channel_id": channel_id,
                            "channel_name": channel.name,
                            "activity_metrics": recent_activity,
                            "recent_message_count": len(channel.recent_messages)
                        },
                        platform=channel.type or "unknown",
                        channel_id=channel_id,
                        expires_at=current_time + 1800,  # 30 minutes
                        reasoning=f"Detected increased activity in {channel.name}: {recent_activity.get('spike_reason', 'activity increase')}"
                    ))
                
                # Look for channels going quiet that might benefit from engagement
                if recent_activity.get("going_quiet", False):
                    opportunities.append(ConversationOpportunity(
                        opportunity_id=f"quiet_channel_{channel_id}_{int(current_time)}",
                        opportunity_type="quiet_channel",
                        priority=5,
                        context={
                            "channel_id": channel_id,
                            "channel_name": channel.name,
                            "last_activity": recent_activity.get("last_activity_time"),
                            "silence_duration": recent_activity.get("silence_duration", 0)
                        },
                        platform=channel.type or "unknown",
                        channel_id=channel_id,
                        expires_at=current_time + 3600,  # 1 hour
                        reasoning=f"Channel {channel.name} has been quiet - opportunity to re-engage community"
                    ))
        
        return opportunities
    
    def _detect_trending_opportunities(self, world_state_data: WorldStateData) -> List[ConversationOpportunity]:
        """Detect opportunities based on trending topics and keywords."""
        opportunities = []
        current_time = time.time()
        
        # Analyze recent messages for trending keywords/topics
        trending_analysis = self._analyze_trending_topics(world_state_data)
        
        for topic_data in trending_analysis.get("trending_topics", []):
            if topic_data.get("trend_strength", 0) > 0.7:  # Strong trend
                opportunities.append(ConversationOpportunity(
                    opportunity_id=f"trending_topic_{topic_data['topic']}_{int(current_time)}",
                    opportunity_type="trending_topic",
                    priority=8,
                    context={
                        "topic": topic_data["topic"],
                        "mentions": topic_data.get("mentions", 0),
                        "channels_involved": topic_data.get("channels", []),
                        "trend_strength": topic_data.get("trend_strength"),
                        "sample_messages": topic_data.get("sample_messages", [])
                    },
                    platform="cross_platform",
                    expires_at=current_time + 7200,  # 2 hours
                    reasoning=f"Topic '{topic_data['topic']}' is trending across {len(topic_data.get('channels', []))} channels"
                ))
        
        return opportunities
    
    def _detect_user_milestone_opportunities(self, world_state_data: WorldStateData) -> List[ConversationOpportunity]:
        """Detect opportunities based on user milestones and achievements."""
        opportunities = []
        current_time = time.time()
        
        # Check Farcaster user milestones
        for fid, user_details in world_state_data.farcaster_users.items():
            milestones = self._check_user_milestones(user_details, "farcaster")
            for milestone in milestones:
                opportunities.append(ConversationOpportunity(
                    opportunity_id=f"user_milestone_{fid}_{milestone['type']}_{int(current_time)}",
                    opportunity_type="user_milestone",
                    priority=6,
                    context={
                        "user_id": fid,
                        "username": getattr(user_details, 'username', f"fid:{fid}"),
                        "milestone_type": milestone["type"],
                        "milestone_data": milestone["data"],
                        "platform": "farcaster"
                    },
                    platform="farcaster",
                    user_id=fid,
                    expires_at=current_time + 43200,  # 12 hours
                    reasoning=f"User {getattr(user_details, 'username', fid)} achieved milestone: {milestone['type']}"
                ))
        
        # Check Matrix user milestones
        for user_id, user_details in world_state_data.matrix_users.items():
            milestones = self._check_user_milestones(user_details, "matrix")
            for milestone in milestones:
                opportunities.append(ConversationOpportunity(
                    opportunity_id=f"user_milestone_{user_id}_{milestone['type']}_{int(current_time)}",
                    opportunity_type="user_milestone",
                    priority=6,
                    context={
                        "user_id": user_id,
                        "display_name": getattr(user_details, 'display_name', user_id),
                        "milestone_type": milestone["type"],
                        "milestone_data": milestone["data"],
                        "platform": "matrix"
                    },
                    platform="matrix",
                    user_id=user_id,
                    expires_at=current_time + 43200,  # 12 hours
                    reasoning=f"User {getattr(user_details, 'display_name', user_id)} achieved milestone: {milestone['type']}"
                ))
        
        return opportunities
    
    def _detect_follow_up_opportunities(self, world_state_data: WorldStateData) -> List[ConversationOpportunity]:
        """Detect opportunities for following up on previous conversations."""
        opportunities = []
        current_time = time.time()
        
        # Analyze recent action history for follow-up opportunities
        for action in world_state_data.action_history[-20:]:  # Last 20 actions
            if current_time - action.timestamp > 3600:  # Skip actions older than 1 hour
                continue
                
            follow_up_context = self._analyze_action_for_follow_up(action, world_state_data)
            if follow_up_context:
                opportunities.append(ConversationOpportunity(
                    opportunity_id=f"follow_up_{action.action_id}_{int(current_time)}",
                    opportunity_type="follow_up",
                    priority=follow_up_context.get("priority", 6),
                    context={
                        "original_action": action.action_type,
                        "action_timestamp": action.timestamp,
                        "channel_id": follow_up_context.get("channel_id"),
                        "follow_up_type": follow_up_context.get("follow_up_type"),
                        "follow_up_reason": follow_up_context.get("reason"),
                        "original_context": follow_up_context.get("original_context", {})
                    },
                    platform=follow_up_context.get("platform", "unknown"),
                    channel_id=follow_up_context.get("channel_id"),
                    expires_at=current_time + 7200,  # 2 hours
                    reasoning=follow_up_context.get("reason", "Follow-up opportunity detected")
                ))
        
        return opportunities
    
    def _detect_cross_platform_opportunities(self, world_state_data: WorldStateData) -> List[ConversationOpportunity]:
        """Detect opportunities for cross-platform conversation bridging."""
        opportunities = []
        current_time = time.time()
        
        # Look for similar topics/discussions happening on different platforms
        cross_platform_analysis = self._analyze_cross_platform_conversations(world_state_data)
        
        for bridge_opportunity in cross_platform_analysis.get("bridge_opportunities", []):
            opportunities.append(ConversationOpportunity(
                opportunity_id=f"cross_platform_{bridge_opportunity['topic']}_{int(current_time)}",
                opportunity_type="cross_platform_bridge",
                priority=7,
                context={
                    "topic": bridge_opportunity["topic"],
                    "source_platform": bridge_opportunity["source_platform"],
                    "target_platform": bridge_opportunity["target_platform"],
                    "source_channels": bridge_opportunity.get("source_channels", []),
                    "target_channels": bridge_opportunity.get("target_channels", []),
                    "bridge_type": bridge_opportunity.get("bridge_type", "topic_sharing"),
                    "relevance_score": bridge_opportunity.get("relevance_score", 0.5)
                },
                platform="cross_platform",
                expires_at=current_time + 3600,  # 1 hour
                reasoning=f"Opportunity to bridge discussion about '{bridge_opportunity['topic']}' between platforms"
            ))
        
        return opportunities
    
    def _detect_community_opportunities(self, world_state_data: WorldStateData) -> List[ConversationOpportunity]:
        """Detect opportunities for general community engagement."""
        opportunities = []
        current_time = time.time()
        
        # Look for opportunities to welcome new users
        new_user_opportunities = self._detect_new_user_opportunities(world_state_data)
        opportunities.extend(new_user_opportunities)
        
        # Look for opportunities to celebrate community achievements
        achievement_opportunities = self._detect_achievement_opportunities(world_state_data)
        opportunities.extend(achievement_opportunities)
        
        # Look for opportunities to share relevant content/research
        content_opportunities = self._detect_content_sharing_opportunities(world_state_data)
        opportunities.extend(content_opportunities)
        
        return opportunities
    
    def _detect_image_analysis_opportunities(self, world_state_data: WorldStateData) -> List[ConversationOpportunity]:
        """Detect opportunities for automatic image analysis and processing."""
        opportunities = []
        current_time = time.time()
        
        # Get recently described images to avoid reprocessing
        media_context = world_state_data.get_media_context()
        recently_described = set(media_context.get("images_recently_described", []))
        
        # Analyze recent messages across all platforms for image content
        for platform, platform_channels in world_state_data.channels.items():
            if not isinstance(platform_channels, dict):
                continue
                
            for channel_id, channel in platform_channels.items():
                if not channel.recent_messages:
                    continue
                    
                for message in channel.recent_messages:
                    # Skip old messages (older than 2 hours)
                    if message.timestamp < current_time - 7200:
                        continue
                    
                    # Check if message has image URLs that haven't been analyzed
                    if hasattr(message, 'image_urls') and message.image_urls:
                        for image_url in message.image_urls:
                            # Skip already analyzed images
                            if image_url in recently_described:
                                continue
                                
                            opportunities.append(ConversationOpportunity(
                                opportunity_id=f"auto_image_analysis_{hash(image_url)}_{int(current_time)}",
                                opportunity_type="auto_image_analysis",
                                priority=6,  # Medium-high priority for automatic processing
                                context={
                                    "image_url": image_url,
                                    "message_id": message.id,
                                    "sender": message.sender,
                                    "channel_id": channel_id,
                                    "channel_name": getattr(channel, 'name', channel_id),
                                    "message_content": message.content,
                                    "platform": platform
                                },
                                platform=platform,
                                channel_id=channel_id,
                                expires_at=current_time + 1800,  # 30 minutes to process
                                reasoning=f"New image detected from {message.sender} - automatic analysis opportunity"
                            ))
        
        return opportunities
    
    def _analyze_channel_activity_pattern(self, channel: Channel) -> Dict[str, Any]:
        """Analyze a channel's activity pattern for opportunities."""
        if not channel.recent_messages:
            return {"activity_spike": False, "going_quiet": False}
        
        current_time = time.time()
        recent_messages = [msg for msg in channel.recent_messages if current_time - msg.timestamp < 3600]  # Last hour
        
        analysis = {
            "activity_spike": False,
            "going_quiet": False,
            "recent_message_count": len(recent_messages),
            "last_activity_time": channel.recent_messages[-1].timestamp if channel.recent_messages else 0
        }
        
        # Simple heuristic: if more than 5 messages in last hour, it's active
        if len(recent_messages) > 5:
            analysis["activity_spike"] = True
            analysis["spike_reason"] = f"{len(recent_messages)} messages in last hour"
        
        # Channel going quiet: no messages in last 30 minutes but had activity before
        silence_duration = current_time - analysis["last_activity_time"]
        if silence_duration > 1800:  # 30 minutes
            analysis["going_quiet"] = True
            analysis["silence_duration"] = silence_duration
        
        return analysis
    
    def _analyze_trending_topics(self, world_state_data: WorldStateData) -> Dict[str, Any]:
        """Analyze messages for trending topics and keywords."""
        # Simple keyword frequency analysis
        keyword_counts = {}
        recent_messages = []
        current_time = time.time()
        
        # Handle nested channel structure: channels[platform][channel_id]
        for platform_channels in world_state_data.channels.values():
            for channel in platform_channels.values():
                for message in channel.recent_messages:
                    if current_time - message.timestamp < 7200:  # Last 2 hours
                        recent_messages.append(message)
        
        # Extract keywords (simple approach - can be enhanced with NLP)
        for message in recent_messages:
            words = message.content.lower().split()
            for word in words:
                if len(word) > 4 and word.isalpha():  # Filter out short words and non-alphabetic
                    keyword_counts[word] = keyword_counts.get(word, 0) + 1
        
        # Identify trending topics (words mentioned multiple times)
        trending_topics = []
        for word, count in keyword_counts.items():
            if count >= 3:  # Mentioned at least 3 times
                trending_topics.append({
                    "topic": word,
                    "mentions": count,
                    "trend_strength": min(count / 10.0, 1.0),  # Normalize to 0-1
                    "channels": [],  # Could be enhanced to track which channels
                    "sample_messages": []  # Could include sample messages
                })
        
        return {"trending_topics": sorted(trending_topics, key=lambda x: x["mentions"], reverse=True)}
    
    def _check_user_milestones(self, user_details, platform: str) -> List[Dict[str, Any]]:
        """Check if a user has achieved any notable milestones."""
        milestones = []
        
        # Example milestone checks (can be expanded based on platform capabilities)
        if platform == "farcaster":
            follower_count = getattr(user_details, 'follower_count', 0)
            following_count = getattr(user_details, 'following_count', 0)
            
            # Follower milestone
            if follower_count > 0 and follower_count % 100 == 0:  # Every 100 followers
                milestones.append({
                    "type": "follower_milestone",
                    "data": {"followers": follower_count}
                })
            
            # Recent activity milestone
            last_interaction = getattr(getattr(user_details, 'sentiment', None), 'last_interaction_time', None)
            if last_interaction and time.time() - last_interaction < 300:  # Active in last 5 minutes
                message_count = getattr(getattr(user_details, 'sentiment', None), 'message_count', 0)
                if message_count > 0 and message_count % 10 == 0:  # Every 10 messages
                    milestones.append({
                        "type": "activity_milestone",
                        "data": {"message_count": message_count}
                    })
        
        return milestones
    
    def _analyze_action_for_follow_up(self, action, world_state_data: WorldStateData) -> Optional[Dict[str, Any]]:
        """Analyze an action to see if it warrants a follow-up."""
        # Example follow-up logic
        if action.action_type in ["send_farcaster_reply", "send_matrix_reply"]:
            # Check if the conversation continued after our reply
            channel_id = action.parameters.get("channel_id")
            if channel_id and channel_id in world_state_data.channels:
                channel = world_state_data.channels[channel_id]
                
                # Look for messages after our action
                subsequent_messages = [
                    msg for msg in channel.recent_messages 
                    if msg.timestamp > action.timestamp
                ]
                
                if len(subsequent_messages) >= 2:  # Conversation continued
                    return {
                        "channel_id": channel_id,
                        "platform": channel.type,
                        "follow_up_type": "conversation_continuation",
                        "priority": 7,
                        "reason": f"Conversation continued after our reply - {len(subsequent_messages)} new messages"
                    }
        
        return None
    
    def _analyze_cross_platform_conversations(self, world_state_data: WorldStateData) -> Dict[str, Any]:
        """Analyze conversations for cross-platform bridging opportunities."""
        # Simple implementation - can be enhanced with semantic analysis
        matrix_topics = set()
        farcaster_topics = set()
        
        # Extract topics from each platform
        for platform, platform_channels in world_state_data.channels.items():
            if not isinstance(platform_channels, dict):
                continue
            for channel_id, channel in platform_channels.items():
                if channel.type == "matrix":
                    for message in channel.recent_messages[-5:]:  # Last 5 messages
                        words = message.content.lower().split()
                        matrix_topics.update(word for word in words if len(word) > 4)
                elif channel.type == "farcaster":
                    for message in channel.recent_messages[-5:]:  # Last 5 messages
                        words = message.content.lower().split()
                        farcaster_topics.update(word for word in words if len(word) > 4)
        
        # Find common topics
        common_topics = matrix_topics.intersection(farcaster_topics)
        bridge_opportunities = []
        
        for topic in common_topics:
            bridge_opportunities.append({
                "topic": topic,
                "source_platform": "matrix",
                "target_platform": "farcaster",
                "bridge_type": "topic_sharing",
                "relevance_score": 0.8  # Could be calculated based on frequency, recency, etc.
            })
        
        return {"bridge_opportunities": bridge_opportunities}
    
    def _detect_new_user_opportunities(self, world_state_data: WorldStateData) -> List[ConversationOpportunity]:
        """Detect opportunities to welcome new users."""
        opportunities = []
        current_time = time.time()
        
        # Look for users who have recently joined or started participating
        for platform, platform_channels in world_state_data.channels.items():
            if not isinstance(platform_channels, dict):
                continue
            for channel_id, channel in platform_channels.items():
                recent_users = set()
                for message in channel.recent_messages[-10:]:  # Last 10 messages
                    if current_time - message.timestamp < 3600:  # Last hour
                        recent_users.add(message.sender_username or message.sender)
                
                # Check if any users are new (haven't been seen in earlier messages)
                historical_users = set()
                for message in channel.recent_messages[:-10]:  # Earlier messages
                    historical_users.add(message.sender_username or message.sender)
                
                new_users = recent_users - historical_users
                for user in new_users:
                    opportunities.append(ConversationOpportunity(
                        opportunity_id=f"new_user_{channel_id}_{user}_{int(current_time)}",
                        opportunity_type="new_user_welcome",
                        priority=6,
                        context={
                            "channel_id": channel_id,
                            "channel_name": channel.name,
                            "new_user": user,
                            "platform": channel.type
                        },
                        platform=channel.type or "unknown",
                        channel_id=channel_id,
                        user_id=user,
                        expires_at=current_time + 7200,  # 2 hours
                        reasoning=f"New user {user} detected in {channel.name} - opportunity to welcome"
                    ))
        
        return opportunities
    
    def _detect_achievement_opportunities(self, world_state_data: WorldStateData) -> List[ConversationOpportunity]:
        """Detect opportunities to celebrate community achievements."""
        # This could be enhanced to detect specific achievements
        # For now, return empty list - can be expanded based on specific community metrics
        return []
    
    def _detect_content_sharing_opportunities(self, world_state_data: WorldStateData) -> List[ConversationOpportunity]:
        """Detect opportunities to share relevant content or research."""
        opportunities = []
        current_time = time.time()
        
        # Look for questions or discussions where we could contribute research/knowledge
        for platform, platform_channels in world_state_data.channels.items():
            if not isinstance(platform_channels, dict):
                continue
            for channel_id, channel in platform_channels.items():
                for message in channel.recent_messages[-5:]:  # Last 5 messages
                    if current_time - message.timestamp > 1800:  # Older than 30 minutes
                        continue
                        
                    # Simple heuristic: messages with question marks or specific keywords
                    content_lower = message.content.lower()
                    if ("?" in message.content or 
                        any(word in content_lower for word in ["how", "what", "why", "when", "where", "research", "study"])):
                        
                        opportunities.append(ConversationOpportunity(
                            opportunity_id=f"content_share_{channel_id}_{message.id}_{int(current_time)}",
                            opportunity_type="content_sharing",
                            priority=5,
                            context={
                                "channel_id": channel_id,
                                "message_id": message.id,
                                "original_message": message.content,
                                "sender": message.sender_username or message.sender,
                                "content_type": "research_response"
                            },
                            platform=channel.type or "unknown",
                            channel_id=channel_id,
                            expires_at=current_time + 3600,  # 1 hour
                            reasoning=f"Question or research opportunity detected in message: {message.content[:50]}..."
                        ))
        
        return opportunities
    
    def _filter_and_prioritize_opportunities(
        self, opportunities: List[ConversationOpportunity], current_time: float
    ) -> List[ConversationOpportunity]:
        """Filter and prioritize opportunities based on various criteria."""
        filtered_opportunities = []
        
        for opportunity in opportunities:
            # Skip expired opportunities
            if opportunity.is_expired():
                continue
            
            # Skip opportunities below priority threshold
            if opportunity.priority < self.min_priority_threshold:
                continue
            
            # Skip if we've recently engaged with this channel/user (cooldown)
            cooldown_key = f"{opportunity.channel_id}_{opportunity.user_id}"
            if cooldown_key in self.recent_engagements:
                continue
            
            # Skip duplicate opportunity types for same channel/user
            duplicate_found = False
            for existing_opp in self.active_opportunities.values():
                if (existing_opp.opportunity_type == opportunity.opportunity_type and
                    existing_opp.channel_id == opportunity.channel_id and
                    existing_opp.user_id == opportunity.user_id):
                    duplicate_found = True
                    break
            
            if not duplicate_found:
                filtered_opportunities.append(opportunity)
        
        # Sort by priority (highest first)
        filtered_opportunities.sort(key=lambda x: x.priority, reverse=True)
        
        # Limit to max active opportunities
        return filtered_opportunities[:self.max_active_opportunities]
    
    def register_active_opportunity(self, opportunity: ConversationOpportunity) -> None:
        """Register an opportunity as active for tracking."""
        self.active_opportunities[opportunity.opportunity_id] = opportunity
        self.opportunity_history.append(opportunity)
        
        # Add to recent engagements for cooldown
        if opportunity.channel_id:
            cooldown_key = f"{opportunity.channel_id}_{opportunity.user_id}"
            self.recent_engagements.add(cooldown_key)
        
        logger.info(f"ProactiveEngine: Registered active opportunity: {opportunity.opportunity_type} - {opportunity.reasoning}")
    
    def cleanup_expired_opportunities(self) -> None:
        """Remove expired opportunities from active tracking."""
        current_time = time.time()
        expired_ids = []
        
        for opportunity_id, opportunity in self.active_opportunities.items():
            if opportunity.is_expired():
                expired_ids.append(opportunity_id)
        
        for opportunity_id in expired_ids:
            del self.active_opportunities[opportunity_id]
            logger.debug(f"ProactiveEngine: Removed expired opportunity: {opportunity_id}")
        
        # Cleanup recent engagements older than cooldown period
        self.recent_engagements = {
            engagement for engagement in self.recent_engagements
            # For now, keep all engagements - could add timestamp tracking for more sophisticated cleanup
        }
    
    def get_active_opportunities(self) -> List[ConversationOpportunity]:
        """Get list of currently active opportunities."""
        self.cleanup_expired_opportunities()
        return list(self.active_opportunities.values())
    
    def record_engagement_result(
        self, opportunity_id: str, success: bool, metrics: Dict[str, Any]
    ) -> None:
        """Record the result of an engagement attempt for learning."""
        result_record = {
            "opportunity_id": opportunity_id,
            "timestamp": time.time(),
            "success": success,
            "metrics": metrics
        }
        
        self.engagement_success_history.append(result_record)
        
        # Remove from active opportunities
        if opportunity_id in self.active_opportunities:
            del self.active_opportunities[opportunity_id]
        
        logger.info(f"ProactiveEngine: Recorded engagement result for {opportunity_id}: {'success' if success else 'failure'}")

    async def start(self) -> None:
        """Start the proactive conversation engine."""
        logger.info("Starting ProactiveConversationEngine...")
        # Initialize any background tasks or scheduled jobs here
        # For now, just log that we're started
        logger.info("ProactiveConversationEngine started successfully")

    async def stop(self) -> None:
        """Stop the proactive conversation engine."""
        logger.info("Stopping ProactiveConversationEngine...")
        # Clean up any background tasks or scheduled jobs here
        self.active_opportunities.clear()
        self.recent_engagements.clear()
        logger.info("ProactiveConversationEngine stopped successfully")

    async def on_world_state_change(self) -> None:
        """Handle world state changes by detecting new opportunities."""
        try:
            # Get current world state data
            world_state_data = self.world_state_manager.get_world_state_data()
            
            # Detect new opportunities
            opportunities = self.analyze_world_state_for_opportunities(world_state_data)
            
            # Register promising opportunities
            for opportunity in opportunities:
                if opportunity.priority >= self.min_priority_threshold:
                    self.register_active_opportunity(opportunity)
                    
            logger.debug(f"ProactiveEngine: Processed world state change, found {len(opportunities)} opportunities")
            
        except Exception as e:
            logger.error(f"Error handling world state change: {e}", exc_info=True)

    async def detect_opportunities(self, opportunity_types: List[str] = None, minimum_priority: float = 0.5) -> List[Dict[str, Any]]:
        """Detect conversation opportunities based on current world state."""
        try:
            # Get current world state data
            world_state_data = await self.world_state_manager.get_world_state_data()
            
            # Analyze for opportunities
            opportunities = self.analyze_world_state_for_opportunities(world_state_data)
            
            # Filter by types if specified
            if opportunity_types:
                opportunities = [
                    opp for opp in opportunities 
                    if opp.opportunity_type in opportunity_types
                ]
            
            # Filter by minimum priority (convert from 1-10 scale to 0-1 scale)
            min_priority_scaled = minimum_priority * 10
            opportunities = [
                opp for opp in opportunities 
                if opp.priority >= min_priority_scaled
            ]
            
            # Convert to dict format for tool response
            opportunity_dicts = []
            for opp in opportunities:
                opportunity_dicts.append({
                    "opportunity_id": opp.opportunity_id,
                    "opportunity_type": opp.opportunity_type,
                    "priority_score": opp.priority / 10.0,  # Convert to 0-1 scale
                    "channel_id": opp.channel_id,
                    "user_id": opp.user_id,
                    "platform": opp.platform,
                    "reasoning": opp.reasoning,
                    "context": opp.context,
                    "expires_at": opp.expires_at
                })
            
            return opportunity_dicts
            
        except Exception as e:
            logger.error(f"Error detecting opportunities: {e}", exc_info=True)
            return []

    async def execute_engagement_plan(self, engagement_plan) -> bool:
        """Execute a proactive engagement plan."""
        try:
            logger.info(f"Executing engagement plan: {engagement_plan.opportunity_id}")
            
            # For now, simulate execution by logging the plan
            # In a full implementation, this would execute the actual actions
            logger.info(f"Engagement plan actions: {engagement_plan.actions}")
            logger.info(f"Target channel: {engagement_plan.channel_id}")
            logger.info(f"Strategy: {engagement_plan.opportunity_type}")
            
            # Mark as executed (simplified)
            return True
            
        except Exception as e:
            logger.error(f"Error executing engagement plan: {e}", exc_info=True)
            return False

    async def track_engagement_outcome(self, opportunity_id: str, status: str, metrics: Dict[str, Any]) -> None:
        """Track the outcome of a proactive engagement."""
        try:
            outcome_record = {
                "opportunity_id": opportunity_id,
                "status": status,
                "timestamp": time.time(),
                "metrics": metrics
            }
            
            # Store in engagement history
            self.engagement_success_history.append(outcome_record)
            
            logger.info(f"Tracked engagement outcome: {opportunity_id} -> {status}")
            
        except Exception as e:
            logger.error(f"Error tracking engagement outcome: {e}", exc_info=True)

    async def schedule_engagement(self, scheduled_engagement: Dict[str, Any]) -> bool:
        """Schedule a proactive engagement for future execution."""
        try:
            # For now, just log the scheduled engagement
            # In a full implementation, this would integrate with a task scheduler
            logger.info(f"Scheduled engagement: {scheduled_engagement['opportunity_id']} for {scheduled_engagement['scheduled_time']}")
            
            # Store in engagement plans for tracking
            plan_id = f"scheduled_{scheduled_engagement['opportunity_id']}"
            self.engagement_plans[plan_id] = scheduled_engagement
            
            return True
            
        except Exception as e:
            logger.error(f"Error scheduling engagement: {e}", exc_info=True)
            return False

    async def get_engagement_status(self, opportunity_id: str) -> Optional[Dict[str, Any]]:
        """Get the status of a specific engagement."""
        try:
            # Look in engagement history
            for record in reversed(self.engagement_success_history):
                if record.get("opportunity_id") == opportunity_id:
                    return {
                        "opportunity_id": opportunity_id,
                        "status": record.get("status"),
                        "timestamp": record.get("timestamp"),
                        "metrics": record.get("metrics", {})
                    }
            
            # Look in active opportunities
            if opportunity_id in self.active_opportunities:
                opp = self.active_opportunities[opportunity_id]
                return {
                    "opportunity_id": opportunity_id,
                    "status": "active",
                    "priority": opp.priority,
                    "context": opp.context
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting engagement status: {e}", exc_info=True)
            return None

    async def get_recent_engagements(self, since_time, status_filter: List[str] = None, include_metrics: bool = True) -> List[Dict[str, Any]]:
        """Get recent engagements with optional filtering."""
        try:
            since_timestamp = since_time.timestamp() if hasattr(since_time, 'timestamp') else since_time
            
            recent_engagements = []
            for record in self.engagement_success_history:
                if record.get("timestamp", 0) >= since_timestamp:
                    if not status_filter or record.get("status") in status_filter:
                        engagement_data = {
                            "opportunity_id": record.get("opportunity_id"),
                            "status": record.get("status"),
                            "timestamp": record.get("timestamp")
                        }
                        
                        if include_metrics:
                            engagement_data["metrics"] = record.get("metrics", {})
                        
                        recent_engagements.append(engagement_data)
            
            return recent_engagements
            
        except Exception as e:
            logger.error(f"Error getting recent engagements: {e}", exc_info=True)
            return []
