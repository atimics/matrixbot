#!/usr/bin/env python3
"""
Dynamic Prompt Builder System

This module implements a modular, context-aware prompt building system
to replace the monolithic system prompt, addressing the token overflow
and complexity issues identified in the engineering report.
"""

import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from pathlib import Path

from .prompts import prompt_builder

logger = logging.getLogger(__name__)


@dataclass
class PromptContext:
    """Context information for building dynamic prompts"""
    situation: str
    available_tools: List[str]
    recent_actions: List[str]
    world_state_summary: Dict[str, Any]
    payload_size_kb: float
    channel_type: Optional[str] = None
    urgency_level: int = 1  # 1-5, higher = more urgent


class DynamicPromptBuilder:
    """Builds lean, contextual prompts based on current situation."""
    
    def __init__(self):
        self.prompt_builder = prompt_builder
        self.base_core_prompt = self._load_core_prompt()
        self.situation_templates = self._load_situation_templates()
        self.max_total_tokens = 3000  # Conservative token limit
        
    def build_context_aware_prompt(self, context: PromptContext) -> str:
        """
        Build a lean, contextual prompt based on the current situation.
        
        Args:
            context: PromptContext with current situation details
            
        Returns:
            Optimized system prompt string
        """
        prompt_modules = []
        
        # 1. Core instructions (always included)
        core_instructions = self._get_core_instructions()
        prompt_modules.append(("core", core_instructions))
        
        # 2. Situation-specific guidance
        situation_guidance = self._get_situation_specific_guidance(context.situation)
        if situation_guidance:
            prompt_modules.append(("situation", situation_guidance))
        
        # 3. Relevant tools only (filtered by context)
        relevant_tools = self._get_relevant_tools_only(context.available_tools, context.situation)
        prompt_modules.append(("tools", relevant_tools))
        
        # 4. Anti-duplication rules (based on recent actions)
        if context.recent_actions:
            anti_duplication = self._get_anti_duplication_rules(context.recent_actions)
            prompt_modules.append(("deduplication", anti_duplication))
        
        # 5. JSON format enforcement (always included)
        format_enforcement = self._get_json_format_enforcement()
        prompt_modules.append(("format", format_enforcement))
        
        # 6. Context-specific constraints
        constraints = self._get_context_constraints(context)
        if constraints:
            prompt_modules.append(("constraints", constraints))
        
        # Combine modules and check size
        final_prompt = self._combine_modules(prompt_modules, context)
        
        # Log the optimization
        estimated_tokens = len(final_prompt.split()) * 1.3  # Rough token estimate
        logger.info(f"DynamicPromptBuilder: Built prompt with ~{estimated_tokens:.0f} tokens for situation: {context.situation}")
        
        if estimated_tokens > self.max_total_tokens:
            logger.warning(f"DynamicPromptBuilder: Prompt may be too long ({estimated_tokens:.0f} tokens)")
        
        return final_prompt
    
    def _load_core_prompt(self) -> str:
        """Load the core, essential prompt instructions."""
        return """You are an AI agent observing and acting in a digital world. You can see messages from multiple platforms and plan actions accordingly.

Your role:
1. Observe the world state.
2. Analyze and plan up to 3 actions.
3. Provide overall reasoning.

WORLD STATE STRUCTURE:
- "current_processing_channel_id": The primary channel for this cycle's focus
- "channels": Contains channel data with different detail levels
- "action_history": Recent actions taken to avoid repetition
- "system_status": Rate limit and health information

RATE LIMIT AWARENESS:
* Your actions are subject to rate limits (per-tool, per-channel, and global).
* If rate limited, prefer wait actions or highest-impact tasks."""
    
    def _load_situation_templates(self) -> Dict[str, str]:
        """Load situation-specific prompt templates."""
        return {
            "user_waiting_for_reply": """
IMMEDIATE PRIORITY: A user is waiting for your response.
- Check for direct mentions, questions, or messages requiring replies
- Prioritize timely, relevant responses over other activities
- Ensure you haven't already replied to the same message recently
            """,
            
            "high_activity": """
ACTIVITY SURGE: Multiple channels have new activity.
- Focus on the primary channel but monitor others for urgent needs
- Avoid overwhelming responses - select most impactful actions
- Prioritize user engagement over automated activities
            """,
            
            "low_activity": """
MONITORING MODE: Limited recent activity detected.
- Consider proactive engagement if appropriate
- Review for missed mentions or delayed responses needed
- Check for trending topics or opportunities to add value
            """,
            
            "rate_limited": """
RATE LIMITED: API limits are approaching or exceeded.
- Prefer wait actions over API-heavy operations
- Focus only on highest-priority, most impactful actions
- Consider using cached data instead of fresh API calls
            """,
            
            "error_recovery": """
RECOVERY MODE: Previous AI operations failed.
- Keep actions simple and reliable
- Prefer basic tools with high success rates
- Provide clear, concise reasoning for all decisions
            """,
            
            "new_user_engagement": """
NEW USER DETECTED: Fresh engagement opportunity.
- Welcome new users appropriately
- Provide helpful context about the community
- Encourage meaningful participation
            """
        }
    
    def _get_core_instructions(self) -> str:
        """Get the core instruction set."""
        return self.base_core_prompt
    
    def _get_situation_specific_guidance(self, situation: str) -> str:
        """Get guidance specific to the current situation."""
        return self.situation_templates.get(situation, "")
    
    def _get_relevant_tools_only(self, available_tools: List[str], situation: str) -> str:
        """Get only tools relevant to the current situation."""
        # Tool categories by situation
        situation_tool_priorities = {
            "user_waiting_for_reply": ["send_matrix_message", "send_farcaster_reply", "react_to_matrix_message"],
            "high_activity": ["send_matrix_message", "send_farcaster_reply", "wait"],
            "low_activity": ["get_trending_casts", "search_casts", "send_farcaster_post", "generate_image"],
            "rate_limited": ["wait", "react_to_matrix_message"],
            "error_recovery": ["wait", "send_matrix_message"],
            "new_user_engagement": ["send_matrix_message", "send_farcaster_reply", "get_user_timeline"]
        }
        
        priority_tools = situation_tool_priorities.get(situation, available_tools[:10])  # Fallback to first 10
        
        # Filter available tools to only include priority ones
        relevant_tools = [tool for tool in available_tools if any(priority in tool for priority in priority_tools)]
        
        if not relevant_tools:
            relevant_tools = available_tools[:5]  # Fallback to first 5 tools
        
        # Get tool descriptions for relevant tools only
        tool_descriptions = []
        for tool in relevant_tools[:8]:  # Limit to top 8 tools to save space
            tool_descriptions.append(f"- {tool}: Available for use")
        
        return f"""
AVAILABLE TOOLS (prioritized for current situation):
{chr(10).join(tool_descriptions)}

Note: Additional tools available but not prioritized for this situation.
        """.strip()
    
    def _get_anti_duplication_rules(self, recent_actions: List[str]) -> str:
        """Generate anti-duplication rules based on recent actions."""
        action_types = [action.split(":")[0] if ":" in action else action for action in recent_actions[-5:]]
        action_counts = {}
        for action in action_types:
            action_counts[action] = action_counts.get(action, 0) + 1
        
        rules = []
        for action, count in action_counts.items():
            if count >= 2:
                rules.append(f"- Avoid repeated {action} actions (used {count} times recently)")
        
        if rules:
            return f"""
ANTI-DUPLICATION RULES:
{chr(10).join(rules)}
            """.strip()
        
        return ""
    
    def _get_json_format_enforcement(self) -> str:
        """Get strict JSON format enforcement rules."""
        return """
CRITICAL: Respond ONLY with valid JSON in this exact format:
{
  "observations": "What you notice about the current state",
  "selected_actions": [
    {
      "action_type": "tool_name_here",
      "parameters": {"param1": "value1"},
      "reasoning": "Why this action makes sense",
      "priority": 8
    }
  ],
  "reasoning": "Overall reasoning for your selections"
}

FORMATTING RULES:
- NO text before or after the JSON object
- NO markdown code blocks or formatting
- NO explanatory text
- Ensure all quotes and braces are properly balanced
- Maximum 3 actions in selected_actions array
        """.strip()
    
    def _get_context_constraints(self, context: PromptContext) -> str:
        """Get constraints based on the current context."""
        constraints = []
        
        if context.payload_size_kb > 100:
            constraints.append("- Keep responses concise due to large context size")
        
        if context.urgency_level >= 4:
            constraints.append("- Respond quickly - high urgency situation")
        
        if context.channel_type == "private":
            constraints.append("- Maintain appropriate tone for private conversation")
        elif context.channel_type == "public":
            constraints.append("- Consider broader audience impact")
        
        if constraints:
            return f"""
CONTEXT CONSTRAINTS:
{chr(10).join(constraints)}
            """.strip()
        
        return ""
    
    def _combine_modules(self, modules: List[tuple], context: PromptContext) -> str:
        """Combine prompt modules into final prompt."""
        combined_parts = []
        
        for module_name, module_content in modules:
            if module_content.strip():
                combined_parts.append(module_content.strip())
        
        return "\n\n".join(combined_parts)
    
    def get_prompt_stats(self, prompt: str) -> Dict[str, Any]:
        """Get statistics about the generated prompt."""
        lines = prompt.split('\n')
        words = prompt.split()
        estimated_tokens = len(words) * 1.3  # Rough estimate
        
        return {
            "lines": len(lines),
            "words": len(words),
            "characters": len(prompt),
            "estimated_tokens": int(estimated_tokens),
            "size_kb": len(prompt.encode('utf-8')) / 1024
        }


class ContextAnalyzer:
    """Analyzes world state to determine appropriate prompt context."""
    
    def __init__(self):
        self.urgency_keywords = [
            "urgent", "emergency", "help", "error", "broken", "down", 
            "failed", "critical", "important", "asap", "quickly"
        ]
    
    def analyze_world_state(self, world_state: Dict[str, Any]) -> PromptContext:
        """
        Analyze world state and determine the appropriate prompt context.
        
        Args:
            world_state: Current world state dictionary
            
        Returns:
            PromptContext with situation analysis
        """
        # Determine the current situation
        situation = self._determine_situation(world_state)
        
        # Extract available tools (this would come from tool registry)
        available_tools = self._extract_available_tools(world_state)
        
        # Get recent actions
        recent_actions = self._extract_recent_actions(world_state)
        
        # Calculate payload size
        import json
        payload_size_kb = len(json.dumps(world_state).encode('utf-8')) / 1024
        
        # Determine urgency
        urgency_level = self._calculate_urgency(world_state)
        
        # Get channel type
        channel_type = self._get_channel_type(world_state)
        
        # Create summary
        world_state_summary = self._create_world_state_summary(world_state)
        
        return PromptContext(
            situation=situation,
            available_tools=available_tools,
            recent_actions=recent_actions,
            world_state_summary=world_state_summary,
            payload_size_kb=payload_size_kb,
            channel_type=channel_type,
            urgency_level=urgency_level
        )
    
    def _determine_situation(self, world_state: Dict[str, Any]) -> str:
        """Determine the current situation type."""
        # Check for rate limiting
        system_status = world_state.get("system_status", {})
        rate_limits = system_status.get("rate_limits", {})
        
        if any(limit.get("remaining", 100) < 10 for limit in rate_limits.values() if isinstance(limit, dict)):
            return "rate_limited"
        
        # Check for errors or recovery mode
        if system_status.get("status") == "reduced_context_mode":
            return "error_recovery"
        
        # Check activity levels
        channels = world_state.get("channels", {})
        recent_message_count = 0
        has_direct_mentions = False
        
        for channel_data in channels.values():
            if isinstance(channel_data, dict):
                messages = channel_data.get("recent_messages", [])
                recent_message_count += len(messages)
                
                # Check for mentions or questions
                for message in messages:
                    if isinstance(message, dict):
                        content = message.get("content", "").lower()
                        if any(indicator in content for indicator in ["@", "?", "help", "can you"]):
                            has_direct_mentions = True
        
        if has_direct_mentions:
            return "user_waiting_for_reply"
        elif recent_message_count > 10:
            return "high_activity"
        elif recent_message_count < 2:
            return "low_activity"
        else:
            return "monitoring"
    
    def _extract_available_tools(self, world_state: Dict[str, Any]) -> List[str]:
        """Extract available tools from world state or use defaults."""
        # This would normally come from the tool registry
        # For now, return a default set
        return [
            "wait", "send_matrix_message", "send_farcaster_reply", 
            "send_farcaster_post", "react_to_matrix_message",
            "get_trending_casts", "search_casts", "generate_image"
        ]
    
    def _extract_recent_actions(self, world_state: Dict[str, Any]) -> List[str]:
        """Extract recent actions from world state."""
        action_history = world_state.get("action_history", [])
        return [str(action) for action in action_history[-5:]]  # Last 5 actions
    
    def _calculate_urgency(self, world_state: Dict[str, Any]) -> int:
        """Calculate urgency level (1-5) based on world state."""
        urgency = 1
        
        # Check for urgent keywords in messages
        channels = world_state.get("channels", {})
        for channel_data in channels.values():
            if isinstance(channel_data, dict):
                messages = channel_data.get("recent_messages", [])
                for message in messages:
                    if isinstance(message, dict):
                        content = message.get("content", "").lower()
                        if any(keyword in content for keyword in self.urgency_keywords):
                            urgency = max(urgency, 4)
        
        # Check system status
        system_status = world_state.get("system_status", {})
        if "error" in str(system_status).lower():
            urgency = max(urgency, 3)
        
        return urgency
    
    def _get_channel_type(self, world_state: Dict[str, Any]) -> Optional[str]:
        """Determine if we're in a public or private context."""
        current_channel = world_state.get("current_processing_channel_id")
        if current_channel:
            if current_channel.startswith("!"):  # Matrix room
                return "public"
            elif current_channel.startswith("@"):  # Direct message
                return "private"
        return None
    
    def _create_world_state_summary(self, world_state: Dict[str, Any]) -> Dict[str, Any]:
        """Create a compact summary of world state for context."""
        summary = {}
        
        if "current_processing_channel_id" in world_state:
            summary["primary_channel"] = world_state["current_processing_channel_id"]
        
        channels = world_state.get("channels", {})
        summary["total_channels"] = len(channels)
        
        action_history = world_state.get("action_history", [])
        summary["recent_actions_count"] = len(action_history)
        
        return summary
