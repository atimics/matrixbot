"""
Attention Engine - Intelligence Filter and Context Aggregator

This module implements the core AttentionEngine that transforms the system from
event-driven to attention-driven processing. The engine acts as an intelligent
filter that:

1. Receives all new message events from WorldStateManager
2. Ignores the bot's own messages to solve self-reply feedback loops  
3. Evaluates external messages to determine if they require the bot's attention
4. Constructs rich ContextualThread objects for messages that warrant attention
5. Places these threads into the AttentionQueue for processing

The AttentionEngine is the cornerstone of the new architecture, ensuring that
no message is ever processed in isolation and that the AI always has rich
context for intelligent decision-making.
"""

import asyncio
import logging
import time
from typing import Optional, Dict, Any, List, Union

from .structures import ContextualThread, ThreadPriority, AttentionMetrics
from ..world_state.manager import WorldStateManager
from ..world_state.structures import Message, FarcasterUserDetails, MatrixUserDetails, Channel
from ...config import settings

logger = logging.getLogger(__name__)


class AttentionEngine:
    """
    The intelligent filter and context aggregator for the attention-driven architecture.
    
    This engine transforms raw message events into rich ContextualThread objects,
    ensuring that the AI never sees a message without its full context. It serves
    as the first stage of the new processing pipeline, replacing direct event
    processing with intelligent attention detection.
    
    Key Features:
    - Automatic self-message filtering to prevent feedback loops
    - Conversation cooldown management to allow for user responses
    - Rich context aggregation including author profiles and conversation history
    - Priority-based thread creation for optimal processing order
    - Comprehensive metrics tracking for performance optimization
    """
    
    def __init__(
        self, 
        world_state: WorldStateManager, 
        attention_queue: asyncio.Queue, 
        config: Dict[str, Any]
    ):
        """
        Initialize the AttentionEngine.
        
        Args:
            world_state: WorldStateManager instance for accessing state and context
            attention_queue: Queue where ContextualThread objects will be placed
            config: Configuration dictionary containing bot identity and settings
        """
        self.world_state = world_state
        self.attention_queue = attention_queue
        
        # Bot identity for self-message filtering
        self.bot_fid = config.get('bot_fid')
        self.bot_user_id = config.get('bot_user_id', settings.matrix.user_id)
        self.bot_username = config.get('bot_username', settings.farcaster.bot_username)
        
        # Attention control parameters
        self.conversation_cooldown = config.get('conversation_cooldown', 180)  # seconds
        self.max_thread_age = config.get('max_thread_age', 3600)  # 1 hour max processing age
        self.priority_boost_keywords = config.get('priority_boost_keywords', [
            'help', 'error', 'problem', 'urgent', 'issue'
        ])
        
        # Performance tracking
        self.metrics = AttentionMetrics()
        self.thread_cache: Dict[str, float] = {}  # thread_id -> creation_time for deduplication
        
        logger.info(f"AttentionEngine initialized")
        logger.info(f"Bot identity: FID={self.bot_fid}, User={self.bot_user_id}, Username={self.bot_username}")
        logger.info(f"Conversation cooldown: {self.conversation_cooldown}s")
    
    async def process_new_message(self, message: Message) -> Optional[ContextualThread]:
        """
        Process a new message and potentially create a ContextualThread.
        
        This is the main entry point for the AttentionEngine. It evaluates whether
        a new message warrants the bot's attention and, if so, constructs a rich
        ContextualThread with all necessary context for intelligent processing.
        
        Args:
            message: The new message to evaluate for attention
            
        Returns:
            ContextualThread if the message warrants attention, None otherwise
        """
        start_time = time.time()
        
        try:
            # Step 1: Filter out the bot's own messages (CRITICAL for feedback loop prevention)
            if self._is_self_message(message):
                logger.debug(f"Ignoring self-message: {message.id}")
                self.metrics.add_message_filtered("self_message")
                return None
            
            # Step 2: Check conversation cooldown to allow for user responses
            if self._is_in_cooldown(message):
                logger.debug(f"Skipping message {message.id} due to conversation cooldown")
                self.metrics.add_message_filtered("cooldown")
                return None
            
            # Step 3: Check for thread deduplication
            thread_id = self._generate_thread_id(message)
            if self._is_duplicate_thread(thread_id):
                logger.debug(f"Skipping duplicate thread: {thread_id}")
                self.metrics.add_message_filtered("duplicate")
                return None
            
            # Step 4: Build the ContextualThread with rich context
            logger.info(f"New attention-worthy message detected: {message.id}")
            thread = await self._build_contextual_thread(message, thread_id)
            
            # Step 5: Add to queue for processing
            await self.attention_queue.put(thread)
            
            # Step 6: Track metrics and performance
            processing_time = time.time() - start_time
            self.metrics.add_thread_created(thread, processing_time)
            self.thread_cache[thread_id] = start_time
            
            logger.info(f"ContextualThread created: {thread.thread_id} (priority: {thread.priority.name})")
            return thread
            
        except Exception as e:
            logger.error(f"Error processing message {message.id}: {e}")
            self.metrics.add_message_filtered("error")
            return None
    
    def _is_self_message(self, message: Message) -> bool:
        """
        Check if a message is from the bot itself.
        
        This is the critical filter that prevents self-reply feedback loops.
        Uses multiple identification strategies to handle different platforms.
        
        Args:
            message: Message to check
            
        Returns:
            True if the message is from the bot, False otherwise
        """
        # Check Farcaster ID
        if self.bot_fid and message.sender_fid and str(message.sender_fid) == str(self.bot_fid):
            return True
        
        # Check Matrix user ID
        if self.bot_user_id and message.sender == self.bot_user_id:
            return True
        
        # Check username
        if self.bot_username and (
            message.sender_username == self.bot_username or 
            message.sender == self.bot_username
        ):
            return True
        
        # Check metadata bot flag
        if message.metadata and message.metadata.get('is_bot') and message.metadata.get('from_our_bot'):
            return True
        
        return False
    
    def _is_in_cooldown(self, message: Message) -> bool:
        """
        Check if a message is within the conversation cooldown period.
        
        This prevents the bot from responding too quickly in active conversations,
        allowing users time to continue their thoughts or other users to respond.
        
        Args:
            message: Message to check
            
        Returns:
            True if the message should be skipped due to cooldown, False otherwise
        """
        thread_id = message.reply_to or message.id
        
        # Check if we have recent bot activity in this thread
        if message.channel_id is None:
            logger.warning("Message has no channel_id, skipping cooldown check")
            return False
            
        last_bot_activity = self._get_last_bot_activity_in_thread(thread_id, message.channel_id)
        
        if last_bot_activity:
            time_since_activity = time.time() - last_bot_activity
            if time_since_activity < self.conversation_cooldown:
                return True
        
        return False
    
    def _get_last_bot_activity_in_thread(self, thread_id: str, channel_id: str) -> Optional[float]:
        """
        Get the timestamp of the last bot activity in a specific thread.
        
        Args:
            thread_id: Thread identifier
            channel_id: Channel identifier
            
        Returns:
            Timestamp of last bot activity or None if no recent activity
        """
        try:
            # Get recent messages in the channel
            state_data = self.world_state.get_state_data()
            channel = state_data.channels.get(channel_id)
            
            if not channel:
                return None
            
            # Look for recent bot messages in this thread
            for message in reversed(channel.recent_messages):
                if self._is_self_message(message):
                    # Check if this message is in the same thread
                    if message.reply_to == thread_id or message.id == thread_id:
                        return message.timestamp
                    # For messages without explicit threading, use time proximity
                    elif not message.reply_to and abs(message.timestamp - time.time()) < 300:  # 5 minutes
                        return message.timestamp
            
            return None
            
        except Exception as e:
            logger.warning(f"Error checking last bot activity: {e}")
            return None
    
    def _generate_thread_id(self, message: Message) -> str:
        """
        Generate a unique thread identifier for a message.
        
        Args:
            message: Message to generate thread ID for
            
        Returns:
            Unique thread identifier
        """
        # Use reply_to if available, otherwise use the message ID
        base_id = message.reply_to or message.id
        return f"{message.channel_id}_{base_id}"
    
    def _is_duplicate_thread(self, thread_id: str) -> bool:
        """
        Check if we've already created a thread for this conversation recently.
        
        Args:
            thread_id: Thread identifier to check
            
        Returns:
            True if this is a duplicate thread, False otherwise
        """
        if thread_id in self.thread_cache:
            creation_time = self.thread_cache[thread_id]
            age = time.time() - creation_time
            
            # Consider it a duplicate if created within the last 5 minutes
            if age < 300:
                return True
            else:
                # Clean up old cache entry
                del self.thread_cache[thread_id]
        
        return False
    
    async def _build_contextual_thread(self, message: Message, thread_id: str) -> ContextualThread:
        """
        Build a rich ContextualThread with comprehensive context.
        
        This is where the magic happens - we aggregate all relevant context
        about the message, author, conversation, and channel to create a
        self-contained unit of work for the AI.
        
        Args:
            message: The triggering message
            thread_id: Generated thread identifier
            
        Returns:
            Complete ContextualThread ready for processing
        """
        # Gather conversation history
        history = self._get_conversation_history(message)
        
        # Get author context
        author_context = await self._get_author_context(message)
        
        # Get channel context
        if message.channel_id:
            channel_context = self._get_channel_context(message.channel_id)
        else:
            channel_context = None
        
        # Calculate priority
        priority = self._calculate_priority(message, author_context, channel_context)
        
        # Determine processing deadline
        deadline = time.time() + self.max_thread_age
        
        # Generate reason for attention
        reason = self._generate_attention_reason(message, priority)
        
        # Build context metadata
        context_metadata = {
            "conversation_length": len(history),
            "author_platform": message.channel_type,
            "has_media": bool(message.image_urls),
            "message_length": len(message.content),
            "channel_activity_level": len(channel_context.recent_messages) if channel_context else 0
        }
        
        return ContextualThread(
            thread_id=thread_id,
            triggering_message=message,
            conversation_history=history,
            author_context=author_context,
            channel_context=channel_context,
            priority=priority,
            reason=reason,
            processing_deadline=deadline,
            context_metadata=context_metadata
        )
    
    def _get_conversation_history(self, message: Message) -> List[Message]:
        """
        Get the conversation history leading up to this message.
        
        Args:
            message: The triggering message
            
        Returns:
            List of messages in the conversation thread
        """
        try:
            if not message.channel_id:
                return []
                
            state_data = self.world_state.get_state_data()
            channel = state_data.channels.get(message.channel_id)
            
            if not channel:
                return []
            
            history = []
            target_thread_id = message.reply_to
            
            if target_thread_id:
                # Find all messages in this reply thread
                for msg in channel.recent_messages:
                    if msg.id == target_thread_id or msg.reply_to == target_thread_id:
                        history.append(msg)
            else:
                # For non-threaded messages, get recent context (last 5 messages)
                history = channel.recent_messages[-5:] if len(channel.recent_messages) > 0 else []
            
            # Sort by timestamp and limit to reasonable size
            history.sort(key=lambda x: x.timestamp)
            return history[-10:]  # Last 10 messages max
            
        except Exception as e:
            logger.warning(f"Error getting conversation history: {e}")
            return []
    
    async def _get_author_context(self, message: Message) -> Optional[Union[FarcasterUserDetails, MatrixUserDetails]]:
        """
        Get rich context about the message author.
        
        Args:
            message: Message to get author context for
            
        Returns:
            Author details or None if not available
        """
        try:
            state_data = self.world_state.get_state_data()
            
            if message.channel_type == 'farcaster' and message.sender_fid:
                return state_data.farcaster_users.get(str(message.sender_fid))
            elif message.channel_type == 'matrix' and message.sender:
                return state_data.matrix_users.get(message.sender)
            
            return None
            
        except Exception as e:
            logger.warning(f"Error getting author context: {e}")
            return None
    
    def _get_channel_context(self, channel_id: str) -> Optional[Channel]:
        """
        Get context about the channel where the message was posted.
        
        Args:
            channel_id: Channel identifier
            
        Returns:
            Channel object or None if not found
        """
        try:
            state_data = self.world_state.get_state_data()
            return state_data.channels.get(channel_id)
        except Exception as e:
            logger.warning(f"Error getting channel context: {e}")
            return None
    
    def _calculate_priority(
        self, 
        message: Message, 
        author_context: Optional[Union[FarcasterUserDetails, MatrixUserDetails]], 
        channel_context: Optional[Channel]
    ) -> ThreadPriority:
        """
        Calculate the priority level for this thread.
        
        Uses multiple signals to determine how urgently this thread should be processed.
        
        Args:
            message: The triggering message
            author_context: Author information
            channel_context: Channel information
            
        Returns:
            ThreadPriority level for this thread
        """
        priority_score = ThreadPriority.NORMAL.value
        
        # Direct mentions or questions get higher priority
        bot_mentioned = any(
            identifier in message.content.lower() 
            for identifier in [self.bot_username, self.bot_user_id] 
            if identifier
        )
        
        if bot_mentioned:
            priority_score += 4  # High priority for direct mentions
        
        if '?' in message.content:
            priority_score += 2  # Questions get priority
        
        # Urgent keywords boost priority
        content_lower = message.content.lower()
        if any(keyword in content_lower for keyword in self.priority_boost_keywords):
            priority_score += 3
        
        # Author influence (for Farcaster)
        if isinstance(author_context, FarcasterUserDetails):
            if author_context.power_badge:
                priority_score += 1
            if author_context.follower_count and author_context.follower_count > 1000:
                priority_score += 1
        
        # Channel activity level
        if channel_context and len(channel_context.recent_messages) > 20:
            priority_score += 1  # Active channels get slight boost
        
        # Media content gets attention
        if message.image_urls:
            priority_score += 1
        
        # Convert score to ThreadPriority
        priority_score = max(ThreadPriority.LOWEST.value, min(priority_score, ThreadPriority.CRITICAL.value))
        
        # Map to nearest valid ThreadPriority value
        if priority_score <= 1:
            return ThreadPriority.LOWEST
        elif priority_score <= 3:
            return ThreadPriority.LOW
        elif priority_score <= 5:
            return ThreadPriority.NORMAL
        elif priority_score <= 7:
            return ThreadPriority.HIGH
        elif priority_score <= 9:
            return ThreadPriority.URGENT
        else:
            return ThreadPriority.CRITICAL
    
    def _generate_attention_reason(self, message: Message, priority: ThreadPriority) -> str:
        """
        Generate a human-readable reason for why this message caught attention.
        
        Args:
            message: The triggering message
            priority: Calculated priority level
            
        Returns:
            Human-readable reason string
        """
        reasons = []
        
        # Check for direct mentions
        bot_mentioned = any(
            identifier in message.content.lower() 
            for identifier in [self.bot_username, self.bot_user_id] 
            if identifier
        )
        
        if bot_mentioned:
            reasons.append("Direct mention")
        
        if '?' in message.content:
            reasons.append("Question")
        
        if any(keyword in message.content.lower() for keyword in self.priority_boost_keywords):
            reasons.append("Urgent keywords")
        
        if message.image_urls:
            reasons.append("Media content")
        
        if not reasons:
            reasons.append("New user message")
        
        base_reason = ", ".join(reasons)
        return f"{base_reason} (Priority: {priority.name})"
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """
        Get a summary of attention engine performance metrics.
        
        Returns:
            Dictionary with performance and behavior metrics
        """
        return self.metrics.to_summary_dict()
    
    def reset_metrics(self) -> None:
        """Reset performance metrics for a fresh measurement period."""
        self.metrics.reset_metrics()
        self.thread_cache.clear()
        logger.info("AttentionEngine metrics reset")
    
    def cleanup_old_threads(self) -> None:
        """Clean up old thread cache entries to prevent memory leaks."""
        current_time = time.time()
        expired_threads = [
            thread_id for thread_id, creation_time in self.thread_cache.items()
            if current_time - creation_time > self.max_thread_age
        ]
        
        for thread_id in expired_threads:
            del self.thread_cache[thread_id]
        
        if expired_threads:
            logger.debug(f"Cleaned up {len(expired_threads)} expired thread cache entries")
