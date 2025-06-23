"""
Dynamic Payload Optimizer

Intelligently optimizes AI payloads to prevent token limit errors while preserving
the most relevant context for the AI's decision-making process.
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import asdict

from ..world_state.structures import WorldStateData, Channel, Message

logger = logging.getLogger(__name__)


class PayloadOptimizationConfig:
    """Configuration for payload optimization strategies."""
    
    def __init__(self):
        # Token limits (conservative estimates)
        self.max_tokens_conservative = 120000  # ~80% of typical 150k context window
        self.max_tokens_aggressive = 80000     # For when we need to be very careful
        
        # Prioritization weights
        self.recent_message_weight = 1.0
        self.user_interaction_weight = 1.5     # Prioritize user messages
        self.action_result_weight = 1.2        # Recent tool results are important
        self.channel_activity_weight = 0.8     # Less active channels get less space
        
        # Compression strategies
        self.enable_message_summarization = True
        self.enable_action_deduplication = True
        self.enable_channel_prioritization = True
        
        # Minimum preservation limits
        self.min_recent_messages_per_channel = 2
        self.min_action_history_entries = 5
        self.preserve_last_n_user_messages = 10


class DynamicPayloadOptimizer:
    """
    Advanced payload optimization that adapts to context and constraints.
    
    Features:
    - Token-aware content prioritization
    - Intelligent message summarization
    - Channel-based importance scoring
    - Progressive compression strategies
    """
    
    def __init__(self, config: Optional[PayloadOptimizationConfig] = None):
        self.config = config or PayloadOptimizationConfig()
        self.optimization_stats = {
            "total_optimizations": 0,
            "average_size_reduction": 0.0,
            "strategies_used": {},
            "last_optimization": None
        }
    
    def optimize_payload(
        self, 
        payload: Dict[str, Any], 
        target_size: Optional[int] = None,
        urgency_level: str = "normal"
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Optimize a payload for size while preserving relevance.
        
        Args:
            payload: The original payload to optimize
            target_size: Target size in characters (None for automatic)
            urgency_level: "conservative", "normal", or "aggressive"
        
        Returns:
            Tuple of (optimized_payload, optimization_report)
        """
        start_time = time.time()
        original_size = len(json.dumps(payload))
        
        # Determine target size based on urgency
        if target_size is None:
            if urgency_level == "aggressive":
                target_size = self.config.max_tokens_aggressive * 4  # ~4 chars per token
            else:
                target_size = self.config.max_tokens_conservative * 4
        
        logger.info(f"Starting payload optimization: {original_size} chars -> target {target_size} chars")
        
        # Create working copy
        optimized = payload.copy()
        strategies_applied = []
        
        # Progressive optimization strategies
        current_size = original_size
        
        # Strategy 1: Remove redundant metadata
        if current_size > target_size:
            optimized, size_reduction = self._remove_redundant_metadata(optimized)
            if size_reduction > 0:
                strategies_applied.append("metadata_cleanup")
                current_size -= size_reduction
        
        # Strategy 2: Optimize message history
        if current_size > target_size:
            optimized, size_reduction = self._optimize_message_history(optimized, urgency_level)
            if size_reduction > 0:
                strategies_applied.append("message_optimization")
                current_size -= size_reduction
        
        # Strategy 3: Compress action history
        if current_size > target_size:
            optimized, size_reduction = self._compress_action_history(optimized, urgency_level)
            if size_reduction > 0:
                strategies_applied.append("action_compression")
                current_size -= size_reduction
        
        # Strategy 4: Summarize research data
        if current_size > target_size:
            optimized, size_reduction = self._summarize_research_data(optimized)
            if size_reduction > 0:
                strategies_applied.append("research_summarization")
                current_size -= size_reduction
        
        # Strategy 5: Aggressive channel pruning (last resort)
        if current_size > target_size and urgency_level in ["normal", "aggressive"]:
            optimized, size_reduction = self._aggressive_channel_pruning(optimized)
            if size_reduction > 0:
                strategies_applied.append("aggressive_pruning")
                current_size -= size_reduction
        
        # Generate optimization report
        final_size = len(json.dumps(optimized))
        size_reduction_percent = ((original_size - final_size) / original_size) * 100
        
        optimization_report = {
            "original_size": original_size,
            "final_size": final_size,
            "size_reduction": original_size - final_size,
            "size_reduction_percent": size_reduction_percent,
            "target_achieved": final_size <= target_size,
            "strategies_applied": strategies_applied,
            "optimization_time": time.time() - start_time,
            "urgency_level": urgency_level
        }
        
        # Update statistics
        self._update_stats(optimization_report)
        
        logger.info(f"Payload optimization complete: {size_reduction_percent:.1f}% reduction")
        
        return optimized, optimization_report
    
    def _remove_redundant_metadata(self, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        """Remove unnecessary metadata and duplicate information."""
        original_size = len(json.dumps(payload))
        
        # Remove debug fields
        if "debug_info" in payload:
            del payload["debug_info"]
        
        # Simplify system status (keep only essential fields)
        if "system_status" in payload:
            essential_status = {
                "running": payload["system_status"].get("running", False),
                "rate_limits": payload["system_status"].get("rate_limits", {}),
                "processing_mode": payload["system_status"].get("processing_mode", "traditional")
            }
            payload["system_status"] = essential_status
        
        # Remove empty or null fields
        payload = self._remove_empty_fields(payload)
        
        new_size = len(json.dumps(payload))
        return payload, original_size - new_size
    
    def _optimize_message_history(self, payload: Dict[str, Any], urgency_level: str) -> Tuple[Dict[str, Any], int]:
        """Intelligently reduce message history while preserving important context."""
        original_size = len(json.dumps(payload))
        
        if "channels" not in payload:
            return payload, 0
        
        # Calculate channel importance scores
        channel_scores = self._calculate_channel_importance(payload["channels"])
        
        # Optimize each channel based on importance and urgency
        for channel_id, channel_data in payload["channels"].items():
            if "recent_messages" not in channel_data:
                continue
            
            importance_score = channel_scores.get(channel_id, 0.5)
            max_messages = self._calculate_message_limit(importance_score, urgency_level)
            
            messages = channel_data["recent_messages"]
            if len(messages) > max_messages:
                # Preserve most recent messages and high-priority ones
                preserved_messages = self._select_important_messages(
                    messages, max_messages, importance_score
                )
                channel_data["recent_messages"] = preserved_messages
        
        new_size = len(json.dumps(payload))
        return payload, original_size - new_size
    
    def _compress_action_history(self, payload: Dict[str, Any], urgency_level: str) -> Tuple[Dict[str, Any], int]:
        """Compress action history by removing duplicates and summarizing old actions."""
        original_size = len(json.dumps(payload))
        
        if "action_history" not in payload:
            return payload, 0
        
        actions = payload["action_history"]
        
        # Remove duplicate actions (same tool, same parameters, within short time window)
        if self.config.enable_action_deduplication:
            actions = self._deduplicate_actions(actions)
        
        # Limit action history based on urgency
        if urgency_level == "aggressive":
            max_actions = 10
        elif urgency_level == "normal":
            max_actions = 20
        else:
            max_actions = 30
        
        if len(actions) > max_actions:
            # Keep most recent actions and summarize older ones
            recent_actions = actions[-max_actions:]
            if len(actions) > max_actions:
                summary = {
                    "type": "action_summary",
                    "summarized_count": len(actions) - max_actions,
                    "time_range": {
                        "start": actions[0].get("timestamp", 0),
                        "end": actions[max_actions-1].get("timestamp", 0)
                    },
                    "common_actions": self._get_common_action_types(actions[:-max_actions])
                }
                actions = [summary] + recent_actions
        
        payload["action_history"] = actions
        
        new_size = len(json.dumps(payload))
        return payload, original_size - new_size
    
    def _summarize_research_data(self, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        """Summarize research database entries to save space."""
        original_size = len(json.dumps(payload))
        
        if "research_database" not in payload:
            return payload, 0
        
        research_entries = payload["research_database"]
        
        # Keep only recent and high-relevance research
        if len(research_entries) > 10:
            # Sort by timestamp and relevance (if available)
            sorted_entries = sorted(
                research_entries,
                key=lambda x: (x.get("timestamp", 0), x.get("relevance_score", 0.5)),
                reverse=True
            )
            
            # Keep top 10 entries, summarize the rest
            payload["research_database"] = sorted_entries[:10]
            if len(sorted_entries) > 10:
                payload["research_summary"] = {
                    "total_entries": len(research_entries),
                    "summarized_entries": len(sorted_entries) - 10,
                    "topics_covered": list(set(
                        entry.get("topic", "unknown") 
                        for entry in sorted_entries[10:]
                    ))[:5]  # Top 5 topics
                }
        
        new_size = len(json.dumps(payload))
        return payload, original_size - new_size
    
    def _aggressive_channel_pruning(self, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        """Last resort: aggressively prune less important channels."""
        original_size = len(json.dumps(payload))
        
        if "channels" not in payload:
            return payload, 0
        
        # Calculate channel importance and keep only top channels
        channel_scores = self._calculate_channel_importance(payload["channels"])
        sorted_channels = sorted(
            channel_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        # Keep top 3 most important channels
        important_channels = dict(sorted_channels[:3])
        pruned_channels = {}
        
        for channel_id in important_channels:
            if channel_id in payload["channels"]:
                pruned_channels[channel_id] = payload["channels"][channel_id]
                # Further reduce messages in each channel
                if "recent_messages" in pruned_channels[channel_id]:
                    messages = pruned_channels[channel_id]["recent_messages"]
                    pruned_channels[channel_id]["recent_messages"] = messages[-2:]  # Keep only 2 most recent
        
        payload["channels"] = pruned_channels
        payload["pruning_applied"] = {
            "original_channel_count": len(channel_scores),
            "pruned_channel_count": len(pruned_channels),
            "pruning_reason": "aggressive_size_reduction"
        }
        
        new_size = len(json.dumps(payload))
        return payload, original_size - new_size
    
    def _calculate_channel_importance(self, channels: Dict[str, Any]) -> Dict[str, float]:
        """Calculate importance scores for channels based on activity and recency."""
        scores = {}
        current_time = time.time()
        
        for channel_id, channel_data in channels.items():
            score = 0.0
            
            # Factor 1: Message count and recency
            messages = channel_data.get("recent_messages", [])
            if messages:
                # Recent message bonus
                latest_message_time = max(
                    msg.get("timestamp", 0) for msg in messages
                )
                recency_bonus = max(0, 1 - (current_time - latest_message_time) / 3600)  # 1 hour decay
                score += len(messages) * 0.1 + recency_bonus * 0.5
            
            # Factor 2: User interaction level
            user_messages = [
                msg for msg in messages 
                if not msg.get("sender", "").startswith("@") or "bot" not in msg.get("sender", "").lower()
            ]
            score += len(user_messages) * 0.3
            
            # Factor 3: Channel type priority
            channel_type = channel_data.get("type", "unknown")
            if channel_type == "matrix_dm":
                score += 0.8  # DMs are high priority
            elif channel_type == "farcaster_channel":
                score += 0.6  # Public channels are medium priority
            
            scores[channel_id] = score
        
        return scores
    
    def _calculate_message_limit(self, importance_score: float, urgency_level: str) -> int:
        """Calculate message limit based on channel importance and urgency."""
        base_limits = {
            "conservative": 15,
            "normal": 10,
            "aggressive": 5
        }
        
        base_limit = base_limits.get(urgency_level, 10)
        
        # Adjust based on importance (0.5x to 2x multiplier)
        multiplier = 0.5 + (importance_score * 1.5)
        multiplier = max(0.5, min(2.0, multiplier))
        
        return max(self.config.min_recent_messages_per_channel, int(base_limit * multiplier))
    
    def _select_important_messages(self, messages: List[Dict], max_count: int, importance_score: float) -> List[Dict]:
        """Select the most important messages to preserve."""
        if len(messages) <= max_count:
            return messages
        
        # Always preserve the most recent messages
        recent_count = max(2, max_count // 2)
        recent_messages = messages[-recent_count:]
        
        # Select additional important messages from the rest
        older_messages = messages[:-recent_count]
        remaining_slots = max_count - recent_count
        
        if remaining_slots > 0 and older_messages:
            # Score older messages by importance
            scored_messages = []
            for msg in older_messages:
                score = 0.0
                
                # User messages are more important
                if not msg.get("sender", "").startswith("@") or "bot" not in msg.get("sender", "").lower():
                    score += 1.0
                
                # Messages with attachments or links
                if msg.get("attachments") or "http" in msg.get("content", ""):
                    score += 0.5
                
                # Longer messages might have more context
                content_length = len(msg.get("content", ""))
                if content_length > 100:
                    score += 0.3
                
                scored_messages.append((score, msg))
            
            # Select top scored messages
            scored_messages.sort(key=lambda x: x[0], reverse=True)
            selected_older = [msg for _, msg in scored_messages[:remaining_slots]]
            
            # Combine and sort by timestamp
            all_selected = selected_older + recent_messages
            all_selected.sort(key=lambda x: x.get("timestamp", 0))
            return all_selected
        
        return recent_messages
    
    def _deduplicate_actions(self, actions: List[Dict]) -> List[Dict]:
        """Remove duplicate actions within a short time window."""
        if len(actions) <= 1:
            return actions
        
        deduplicated = []
        seen_signatures = {}
        
        for action in actions:
            # Create signature based on action type and key parameters
            signature = self._create_action_signature(action)
            timestamp = action.get("timestamp", 0)
            
            # Check if we've seen this signature recently (within 10 minutes)
            if signature in seen_signatures:
                last_timestamp = seen_signatures[signature]
                if timestamp - last_timestamp < 600:  # 10 minutes
                    continue  # Skip duplicate
            
            seen_signatures[signature] = timestamp
            deduplicated.append(action)
        
        return deduplicated
    
    def _create_action_signature(self, action: Dict) -> str:
        """Create a signature for action deduplication."""
        action_type = action.get("action_type", "unknown")
        
        # Include key parameters that define uniqueness
        key_params = {}
        params = action.get("parameters", {})
        
        # Common parameters that matter for uniqueness
        for key in ["channel_id", "content", "user_id", "tool_name"]:
            if key in params:
                key_params[key] = params[key]
        
        return f"{action_type}:{json.dumps(key_params, sort_keys=True)}"
    
    def _get_common_action_types(self, actions: List[Dict]) -> List[str]:
        """Get the most common action types from a list of actions."""
        from collections import Counter
        
        action_types = [action.get("action_type", "unknown") for action in actions]
        counter = Counter(action_types)
        return [action_type for action_type, _ in counter.most_common(5)]
    
    def _remove_empty_fields(self, obj: Any) -> Any:
        """Recursively remove empty fields from a data structure."""
        if isinstance(obj, dict):
            cleaned = {}
            for key, value in obj.items():
                cleaned_value = self._remove_empty_fields(value)
                if cleaned_value is not None and cleaned_value != "" and cleaned_value != [] and cleaned_value != {}:
                    cleaned[key] = cleaned_value
            return cleaned
        elif isinstance(obj, list):
            return [self._remove_empty_fields(item) for item in obj if item is not None]
        else:
            return obj
    
    def _update_stats(self, optimization_report: Dict[str, Any]):
        """Update optimization statistics."""
        self.optimization_stats["total_optimizations"] += 1
        
        # Update average size reduction
        current_avg = self.optimization_stats["average_size_reduction"]
        new_reduction = optimization_report["size_reduction_percent"]
        total_optimizations = self.optimization_stats["total_optimizations"]
        
        self.optimization_stats["average_size_reduction"] = (
            (current_avg * (total_optimizations - 1) + new_reduction) / total_optimizations
        )
        
        # Track strategy usage
        for strategy in optimization_report["strategies_applied"]:
            if strategy not in self.optimization_stats["strategies_used"]:
                self.optimization_stats["strategies_used"][strategy] = 0
            self.optimization_stats["strategies_used"][strategy] += 1
        
        self.optimization_stats["last_optimization"] = time.time()
    
    def get_optimization_stats(self) -> Dict[str, Any]:
        """Get current optimization statistics."""
        return self.optimization_stats.copy()
    
    def reset_stats(self):
        """Reset optimization statistics."""
        self.optimization_stats = {
            "total_optimizations": 0,
            "average_size_reduction": 0.0,
            "strategies_used": {},
            "last_optimization": None
        }
