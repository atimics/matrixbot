"""
Consolidated AI Decision Engine with multiple optimization levels.
Main AI engine that supports original, balanced, and aggressive optimization approaches.
"""

import json
import logging
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path
import os
from dataclasses import dataclass

import httpx
from pydantic_settings import BaseSettings

from .prompts import prompt_builder
from ..config import settings

logger = logging.getLogger(__name__)


@dataclass
class ActionPlan:
    """Represents a planned action"""

    action_type: str
    parameters: Dict[str, Any]
    reasoning: str
    priority: int  # 1-10, higher is more important


@dataclass
class DecisionResult:
    """Result of AI decision making"""

    selected_actions: List[ActionPlan]
    reasoning: str
    observations: str
    thought: str  # AI's step-by-step thinking process
    cycle_id: str


class OptimizationLevel:
    """Available optimization levels for payload reduction."""
    ORIGINAL = "original"      # Full verbose prompts and world state (90-100KB)
    BALANCED = "balanced"      # Essential content with recent messages (15-25KB) 
    AGGRESSIVE = "aggressive"  # Minimal structured data only (8-12KB)


class BaseAIDecisionEngine:
    """Base class for AI decision engines - legacy compatibility."""
    
    async def make_decision(self, world_state: Dict[str, Any], cycle_id: str):
        """Make a decision based on current world state"""
        raise NotImplementedError


class AIDecisionEngine(BaseAIDecisionEngine):
    """
    Main AI Decision Engine supporting multiple optimization levels.
    
    - ORIGINAL: Full world state with complete prompts (legacy behavior)
    - BALANCED: Essential content with recent messages (recommended)
    - AGGRESSIVE: Minimal structured data (for extreme size constraints)
    """
    
    def __init__(self, 
                 api_key: str, 
                 model: str = "openrouter/auto", 
                 optimization_level: str = OptimizationLevel.BALANCED,
                 prompt_builder_instance=None,
                 config=None):
        """
        Initialize the unified AI engine.
        
        Args:
            api_key: OpenRouter API key
            model: AI model to use
            optimization_level: One of OptimizationLevel constants
            prompt_builder_instance: Legacy prompt builder (for ORIGINAL mode)
            config: Configuration object for settings
        """
        self.api_key = api_key
        self.model = model
        self.optimization_level = optimization_level
        self.prompt_builder = prompt_builder_instance
        self.config = config
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        self.max_actions_per_cycle = 3
        
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.info(f"Initialized AIDecisionEngine with {optimization_level} optimization")
        
        # Set up prompt_builder fallback
        if not self.prompt_builder:
            self.prompt_builder = prompt_builder
        
        # Load configuration if not provided
        if not self.config:
            try:
                # Try to load config dynamically
                import sys
                sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
                from config import AppConfig
                self.config = AppConfig()
            except Exception as e:
                self.logger.warning(f"Could not load config: {e}")
                self.config = None
    
    def decide_actions(self, world_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main decision-making method with configurable optimization.
        
        Args:
            world_state: Complete world state data
            
        Returns:
            Dict containing observations, selected_actions, and reasoning
        """
        try:
            if self.optimization_level == OptimizationLevel.ORIGINAL:
                return self._decide_actions_original(world_state)
            elif self.optimization_level == OptimizationLevel.BALANCED:
                return self._decide_actions_balanced(world_state)
            elif self.optimization_level == OptimizationLevel.AGGRESSIVE:
                return self._decide_actions_aggressive(world_state)
            else:
                self.logger.warning(f"Unknown optimization level: {self.optimization_level}, using BALANCED")
                return self._decide_actions_balanced(world_state)
                
        except Exception as e:
            self.logger.error(f"Error in decide_actions: {e}")
            return {
                "observations": f"Error occurred: {str(e)}",
                "selected_actions": [{"action_type": "wait", "parameters": {}, "reasoning": "Error recovery", "priority": 1}],
                "reasoning": "Falling back to wait due to processing error"
            }
    
    def _decide_actions_original(self, world_state: Dict[str, Any]) -> Dict[str, Any]:
        """Original implementation with full prompts and world state."""
        if not self.prompt_builder:
            raise ValueError("prompt_builder_instance required for ORIGINAL optimization level")
        
        # Build full system prompt
        prompt_sections = ["identity", "interaction_style", "world_state_context", "tools_context", "safety_guidelines"]
        
        primary_channel_id = world_state.get("current_processing_channel_id")
        if primary_channel_id and "matrix" in str(primary_channel_id):
            prompt_sections.append("matrix_context")
        if primary_channel_id and "farcaster" in str(primary_channel_id):
            prompt_sections.append("farcaster_context")

        tool_descriptions = world_state.get("available_tools", "No tools available.")
        
        # Get world state data reference for template substitution
        world_state_data_ref = world_state.get("_world_state_data_ref")
        system_prompt = self.prompt_builder.build_system_prompt(
            include_sections=prompt_sections,
            world_state_data=world_state_data_ref
        )
        system_prompt += f"\n\n## Available Tools\n{tool_descriptions}"

        user_prompt = f"""Current World State:
{json.dumps(world_state, indent=2)}

Based on this world state, what actions should you take? You can take up to {self.max_actions_per_cycle} actions this cycle. Look for opportunities to engage meaningfully across all channels, not just the primary one. Be proactive and take multiple actions when valuable opportunities exist - don't default to waiting unless there are truly no meaningful engagement possibilities."""

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 3500
        }
        
        # Log and dump payload
        payload_size = len(json.dumps(payload).encode('utf-8'))
        self.logger.info(f"Original payload size: {payload_size:,} bytes ({payload_size/1024:.1f}KB)")
        self._dump_payload_to_file(payload, payload_size, "original")
        
        return self._make_api_call(payload)
    
    def _decide_actions_balanced(self, world_state: Dict[str, Any]) -> Dict[str, Any]:
        """Balanced optimization: essential content with recent messages."""
        try:
            # Build balanced world state with essential content
            compact_world_state = self._build_balanced_world_state(world_state)
            
            # Create the optimized payload
            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": self._get_system_prompt_balanced()
                    },
                    {
                        "role": "user", 
                        "content": json.dumps({
                            "world_state": compact_world_state,
                            "tools_available": self._get_essential_tools(),
                            "instruction": "Analyze the world state with recent message context and select up to 3 actions. Respond with JSON only."
                        })
                    }
                ],
                "tools": self._get_essential_tool_definitions(),
                "temperature": 0.7,
                "max_tokens": 3500
                # Note: Removed response_format because Google models don't support it with function calling
            }
            
            # Only add response_format for models that support it with tools
            # Google models don't support response_format with function calling
            if not self.model.startswith("google/"):
                payload["response_format"] = {"type": "json_object"}
            
            # Log payload size
            payload_size = len(json.dumps(payload).encode('utf-8'))
            self.logger.info(f"Balanced payload size: {payload_size:,} bytes ({payload_size/1024:.1f}KB)")
            
            # Dump payload to file if configured
            self._dump_payload_to_file(payload, payload_size, "balanced")
            
            # Make the API call
            return self._make_api_call(payload)
            
        except Exception as e:
            self.logger.error(f"Error in _decide_actions_balanced: {e}")
            return {
                "observations": f"Error occurred: {str(e)}",
                "selected_actions": [{"action_type": "wait", "parameters": {}, "reasoning": "Error recovery", "priority": 1}],
                "reasoning": "Falling back to wait due to processing error"
            }
    
    def _decide_actions_aggressive(self, world_state: Dict[str, Any]) -> Dict[str, Any]:
        """Aggressive optimization: minimal structured data only."""
        minimal_state = self._build_minimal_world_state(world_state)
        
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": self._get_system_prompt_minimal()
                },
                {
                    "role": "user",
                    "content": json.dumps({
                        "state": minimal_state,
                        "tools": ["wait", "send_matrix_reply", "send_farcaster_reply", "expand_node"],
                        "task": "Select 1 action based on state data."
                    })
                }
            ],
            "temperature": 0.7,
            "max_tokens": 1500,
            "response_format": {"type": "json_object"}
        }
        
        payload_size = len(json.dumps(payload).encode('utf-8'))
        self.logger.info(f"Aggressive payload size: {payload_size:,} bytes ({payload_size/1024:.1f}KB)")
        self._dump_payload_to_file(payload, payload_size, "aggressive")
        
        return self._make_api_call(payload)
    
    def _build_balanced_world_state(self, world_state: Dict[str, Any]) -> Dict[str, Any]:
        """Build balanced world state with essential message content."""
        compact_state = {
            "primary_channel": world_state.get("current_processing_channel_id"),
            "system": {
                "timestamp": world_state.get("system_status", {}).get("timestamp"),
                "rate_limits": world_state.get("system_status", {}).get("rate_limits", {})
            }
        }
        
        # Channel metadata
        channels = {}
        available_channels = world_state.get("available_channels", {})
        for platform, platform_channels in available_channels.items():
            if platform == "summary":
                continue
            channels[platform] = {}
            for channel_id, channel_info in platform_channels.items():
                channels[platform][channel_id] = {
                    "name": channel_info.get("name"),
                    "recent_msgs": channel_info.get("recent_message_count", 0),
                    "last_activity": channel_info.get("last_activity"),
                    "expanded": channel_info.get("is_expanded", False)
                }
        compact_state["channels"] = channels
        
        # CRITICAL: Include recent messages from expanded nodes
        recent_messages = {}
        expanded_nodes = world_state.get("expanded_nodes", {})
        for node_path, node_data in expanded_nodes.items():
            if "data" in node_data and "recent_messages" in node_data["data"]:
                channel_id = node_path.split(".")[-1]
                messages = []
                for msg in node_data["data"]["recent_messages"][-5:]:  # Last 5 messages
                    messages.append({
                        "sender": self._extract_username(msg.get("sender_username", "")),
                        "content": self._truncate_content(msg.get("content", "")),
                        "timestamp": msg.get("timestamp"),
                        "id": msg.get("id"),
                        "reply_to": msg.get("reply_to"),
                        "images": len(msg.get("image_urls", []))
                    })
                recent_messages[channel_id] = {
                    "channel_name": node_data["data"].get("name", "Unknown"),
                    "messages": messages
                }
        
        if recent_messages:
            compact_state["recent_messages"] = recent_messages
        
        # Recent actions (compact)
        action_history = world_state.get("action_history", [])
        if action_history:
            compact_state["recent_actions"] = []
            for action in action_history[-10:]:
                compact_state["recent_actions"].append({
                    "tool": action.get("tool"),
                    "timestamp": action.get("timestamp"),
                    "channel": action.get("channel_id"),
                    "success": action.get("success", True)
                })
        
        # Expansion status
        expansion_status = world_state.get("expansion_status", {})
        compact_state["expansion"] = {
            "expanded": expansion_status.get("total_expanded", 0),
            "max": expansion_status.get("max_allowed", 8),
            "pinned": expansion_status.get("pinned_nodes", []),
            "unpinned": expansion_status.get("unpinned_nodes", [])
        }
        
        return compact_state
    
    def _build_minimal_world_state(self, world_state: Dict[str, Any]) -> Dict[str, Any]:
        """Build minimal world state for aggressive optimization."""
        primary_channel = world_state.get("current_processing_channel_id")
        
        # Only include absolutely essential data
        minimal_state = {
            "channel": primary_channel,
            "timestamp": world_state.get("system_status", {}).get("timestamp")
        }
        
        # Check if primary channel has activity
        available_channels = world_state.get("available_channels", {})
        for platform, channels in available_channels.items():
            if primary_channel in channels:
                channel_info = channels[primary_channel]
                if channel_info.get("recent_message_count", 0) > 0:
                    minimal_state["has_activity"] = True
                    minimal_state["msg_count"] = channel_info.get("recent_message_count", 0)
                break
        
        return minimal_state
    
    def _extract_username(self, full_username: str) -> str:
        """Extract clean username from full Matrix/Farcaster username."""
        if ":" in full_username:
            return full_username.split(":")[-1]
        return full_username or "unknown"
    
    def _truncate_content(self, content: str, max_length: int = 200) -> str:
        """Truncate message content while preserving essential information."""
        if len(content) <= max_length:
            return content
        
        truncated = content[:max_length]
        last_space = truncated.rfind(' ')
        if last_space > max_length * 0.8:
            truncated = truncated[:last_space]
        
        return truncated + "..."
    
    def _get_system_prompt_balanced(self) -> str:
        """System prompt for balanced optimization."""
        return """# AI Agent Instructions

## Identity
You are an autonomous AI agent operating across Matrix and Farcaster platforms.

## Response Format (STRICT JSON ONLY)
CRITICAL: You MUST respond with valid JSON in the exact format below. Do not include any text before or after the JSON.

```json
{
  "observations": "Brief summary of notable world state changes requiring action",
  "selected_actions": [
    {
      "action_type": "tool_name",
      "parameters": {...},
      "reasoning": "Why this action",
      "priority": 8
    }
  ],
  "reasoning": "Overall strategy for this cycle"
}
```

## Core Rules
1. ALWAYS respond with valid JSON in the exact format above
2. NO TEXT BEFORE OR AFTER THE JSON
3. **Take up to 3 actions per cycle** - use this capacity when meaningful opportunities exist
4. Check recent_actions to avoid duplicates  
5. Skip actions on messages with "already_replied": true
6. **Be proactive across all channels** - look for engagement opportunities in Matrix, Farcaster, and other platforms
7. Only use "wait" when there are truly no valuable opportunities across any channel

## Decision Framework
- **High Priority (8-10)**: Direct replies, urgent issues, new conversations, proactive valuable contributions
- **Medium Priority (5-7)**: Cross-channel engagement, content creation, community building
- **Low Priority (1-4)**: Maintenance, optional interactions, wait-and-observe

## Engagement Philosophy  
- **Multi-channel awareness**: Consider opportunities across all active channels, not just the primary one
- **Value-driven action**: Prioritize actions that genuinely help, inform, entertain, or build community
- **Proactive engagement**: Don't just react - create conversations, ask questions, share insights
- **Multiple actions**: Combine different types of engagement (like + reply, react + store memory, etc.)

## Platform Guidelines
- Matrix: Use send_matrix_reply for conversations, send_matrix_message for announcements
- Farcaster: Use send_farcaster_reply for responses, send_farcaster_post for new content
- Always check recent_messages for conversation context
- Expand nodes only when you need more detailed information"""
    
    def _get_system_prompt_minimal(self) -> str:
        """Minimal system prompt for aggressive optimization."""
        return """AI Agent: Respond with JSON only.
Format: {"observations": "...", "selected_actions": [{"action_type": "tool", "parameters": {}, "reasoning": "...", "priority": 5}], "reasoning": "..."}
Take action when opportunities exist. Use "wait" only if no valuable engagement possibilities."""
    
    def _get_essential_tools(self) -> List[str]:
        """Return list of essential tool names."""
        return [
            "wait", "send_matrix_message", "send_matrix_reply",
            "send_farcaster_post", "send_farcaster_reply", "like_farcaster_post",
            "generate_image", "web_search", "expand_node", "collapse_node", "describe_image"
        ]
    
    def _get_essential_tool_definitions(self) -> List[Dict[str, Any]]:
        """Return compact essential tool definitions."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "wait",
                    "description": "Observe without taking action. Only use when there are truly no valuable engagement opportunities across any channel.",
                    "parameters": {"type": "object", "properties": {"duration": {"type": "number", "default": 0}}}
                }
            },
            {
                "type": "function", 
                "function": {
                    "name": "send_matrix_reply",
                    "description": "Reply to a Matrix message. Auto-attaches recent media.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "channel_id": {"type": "string"},
                            "content": {"type": "string"},
                            "reply_to_id": {"type": "string"},
                            "format_as_markdown": {"type": "boolean"}
                        },
                        "required": ["channel_id", "content", "format_as_markdown"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "send_matrix_message", 
                    "description": "Send new Matrix message. Auto-attaches recent media.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "channel_id": {"type": "string"},
                            "content": {"type": "string"},
                            "format_as_markdown": {"type": "boolean"}
                        },
                        "required": ["channel_id", "content", "format_as_markdown"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "send_farcaster_post",
                    "description": "Send new Farcaster cast. Auto-attaches recent media.",
                    "parameters": {
                        "type": "object", 
                        "properties": {
                            "content": {"type": "string"},
                            "channel": {"type": "string"},
                            "embed_url": {"type": "string"}
                        },
                        "required": ["content"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "send_farcaster_reply",
                    "description": "Reply to Farcaster cast.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "content": {"type": "string"},
                            "reply_to_hash": {"type": "string"}
                        },
                        "required": ["content", "reply_to_hash"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "expand_node",
                    "description": "Expand node to view full details. Max 8 nodes.",
                    "parameters": {
                        "type": "object",
                        "properties": {"node_path": {"type": "string"}},
                        "required": ["node_path"]  
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "collapse_node",
                    "description": "Collapse expanded node to free up slots.",
                    "parameters": {
                        "type": "object",
                        "properties": {"node_path": {"type": "string"}},
                        "required": ["node_path"]
                    }
                }
            }
        ]
    
    def _extract_json_from_response(self, ai_response: str) -> Dict[str, Any]:
        """Extract JSON from AI response with robust parsing."""
        try:
            # Remove markdown code blocks if present
            if ai_response.startswith("```json"):
                ai_response = ai_response.strip("```json").strip("```").strip()
            elif ai_response.startswith("```"):
                ai_response = ai_response.strip("```").strip()
            
            # Try to parse directly first
            try:
                return json.loads(ai_response)
            except json.JSONDecodeError:
                pass
            
            # PRIORITY 1: Try to fix missing opening brace first (before pattern matching)
            if ('"selected_actions"' in ai_response or '"observations"' in ai_response or 'observations"' in ai_response) and not ai_response.strip().startswith('{'):
                # Check if it looks like JSON missing opening brace
                if ai_response.strip().startswith('"') or ai_response.strip().startswith('observations"'):
                    potential_json = '{' + ai_response.strip()
                    # Fix malformed start (missing quote before observations)
                    if potential_json.startswith('{observations"'):
                        potential_json = '{"observations"' + potential_json[13:]
                    try:
                        result = json.loads(potential_json)
                        # Prefer results with both observations and selected_actions
                        if isinstance(result, dict) and 'observations' in result and 'selected_actions' in result:
                            return result
                    except json.JSONDecodeError:
                        pass
                
                # Try to reconstruct the entire JSON structure
                potential_json = '{\n' + ai_response.strip()
                # Fix malformed start (missing quote before observations)
                if potential_json.startswith('{\nobservations"'):
                    potential_json = '{\n"observations"' + potential_json[15:]
                try:
                    result = json.loads(potential_json)
                    if isinstance(result, dict) and ('observations' in result or 'selected_actions' in result):
                        return result
                except json.JSONDecodeError:
                    pass
                
                # Try line-by-line reconstruction
                lines = ai_response.split('\n')
                for i, line in enumerate(lines):
                    if ('"selected_actions"' in line or '"observations"' in line or 'observations"' in line) and not line.strip().startswith('{'):
                        # Try to reconstruct JSON by adding opening brace
                        potential_json = '{' + '\n'.join(lines[i:])
                        # Fix malformed start (missing quote before observations)
                        if potential_json.startswith('{observations"'):
                            potential_json = '{"observations"' + potential_json[13:]
                        try:
                            result = json.loads(potential_json)
                            if isinstance(result, dict) and 'observations' in result and 'selected_actions' in result:
                                return result
                        except json.JSONDecodeError:
                            pass
            
            # PRIORITY 2: Look for complete JSON blocks between curly braces
            json_blocks = []
            brace_count = 0
            start_pos = -1
            
            for i, char in enumerate(ai_response):
                if char == '{':
                    if brace_count == 0:
                        start_pos = i
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0 and start_pos != -1:
                        json_blocks.append(ai_response[start_pos:i+1])
                        start_pos = -1
            
            # Sort by length (prefer larger objects)
            json_blocks.sort(key=len, reverse=True)
            
            if json_blocks:
                # First try to find a match with 'observations' and 'selected_actions'
                for block in json_blocks:
                    try:
                        parsed = json.loads(block)
                        if isinstance(parsed, dict) and 'observations' in parsed and 'selected_actions' in parsed:
                            return parsed
                    except json.JSONDecodeError:
                        continue
                
                # If no perfect match, try to find one with 'observations'
                for block in json_blocks:
                    try:
                        parsed = json.loads(block)
                        if isinstance(parsed, dict) and 'observations' in parsed:
                            return parsed
                    except json.JSONDecodeError:
                        continue
                
                # If no match with 'observations', try the largest valid JSON
                for block in json_blocks:
                    try:
                        parsed = json.loads(block)
                        if isinstance(parsed, dict):
                            return parsed
                    except json.JSONDecodeError:
                        continue
            
            # If we reach here, no valid JSON was found - raise an exception
            # This is expected behavior for completely invalid input
            raise ValueError(f"No valid JSON found in response: {ai_response[:100]}...")
            
        except ValueError:
            # Re-raise ValueError (our custom exception for no JSON found)
            raise
        except Exception as e:
            # For other unexpected errors, also raise
            raise ValueError(f"JSON extraction error: {str(e)}")
    
    
    def _dump_payload_to_file(self, payload: Dict[str, Any], payload_size: int, optimization_level: str) -> None:
        """Dump payload to file for analysis."""
        try:
            if not self.config:
                return
                
            dump_enabled = getattr(self.config, 'AI_DUMP_PAYLOADS_TO_FILE', False)
            if not dump_enabled:
                return
                
            dump_dir = getattr(self.config, 'AI_PAYLOAD_DUMP_DIRECTORY', 'data/payload_dumps')
            os.makedirs(dump_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"payload_{optimization_level}_{timestamp}.json"
            filepath = os.path.join(dump_dir, filename)
            
            dump_data = {
                "metadata": {
                    "timestamp": datetime.now().isoformat(),
                    "model": payload.get("model"),
                    "payload_size_bytes": payload_size,
                    "payload_size_kb": payload_size / 1024,
                    "optimization_level": optimization_level
                },
                "payload": payload
            }
            
            with open(filepath, 'w') as f:
                json.dump(dump_data, f, indent=2, default=str)
                
            self.logger.info(f"Dumped {optimization_level} payload to {filepath}")
            
        except Exception as e:
            self.logger.error(f"Error dumping payload: {e}")
    
    def _make_api_call(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Make API call to OpenRouter and return parsed response."""
        
        async def _async_api_call():
            try:
                # Log the complete request payload for debugging 400 errors
                payload_size_kb = len(json.dumps(payload).encode('utf-8')) / 1024
                self.logger.info(f"API Request: {self.base_url}")
                self.logger.info(f"Payload size: {payload_size_kb:.2f} KB")
                self.logger.info(f"Model: {payload.get('model', 'not specified')}")
                self.logger.info(f"Messages count: {len(payload.get('messages', []))}")
                self.logger.info(f"Tools count: {len(payload.get('tools', []))}")
                
                # Log payload structure for debugging
                if payload_size_kb < 50:  # Only log full payload if it's reasonably small
                    self.logger.debug(f"Full payload: {json.dumps(payload, indent=2)}")
                else:
                    # Log just the essential parts
                    debug_payload = {
                        "model": payload.get("model"),
                        "temperature": payload.get("temperature"),
                        "max_tokens": payload.get("max_tokens"),
                        "response_format": payload.get("response_format"),
                        "messages": [
                            {
                                "role": msg.get("role"),
                                "content_length": len(str(msg.get("content", "")))
                            } for msg in payload.get("messages", [])
                        ],
                        "tools_count": len(payload.get("tools", []))
                    }
                    self.logger.debug(f"Payload structure: {json.dumps(debug_payload, indent=2)}")
                
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(
                        self.base_url,
                        json=payload,
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                            "HTTP-Referer": "https://github.com/ratimics/chatbot",
                            "X-Title": "Ratimics Chatbot",
                        },
                    )
                    
                    # Enhanced error logging for 400 Bad Request
                    if response.status_code == 400:
                        error_details = {
                            "status_code": response.status_code,
                            "response_text": response.text,
                            "request_model": payload.get("model"),
                            "request_size_kb": payload_size_kb,
                            "has_tools": bool(payload.get("tools")),
                            "has_response_format": bool(payload.get("response_format")),
                            "message_roles": [msg.get("role") for msg in payload.get("messages", [])]
                        }
                        self.logger.error(f"HTTP 400 Bad Request - Error details: {json.dumps(error_details, indent=2)}")
                        
                        # Try to parse error response for more details
                        try:
                            error_response = response.json()
                            self.logger.error(f"OpenRouter error response: {json.dumps(error_response, indent=2)}")
                        except:
                            self.logger.error(f"Could not parse error response as JSON")
                        
                        return {
                            "observations": f"API 400 error: {response.text[:200]}",
                            "selected_actions": [{"action_type": "wait", "parameters": {}, "reasoning": "API 400 error recovery", "priority": 1}],
                            "reasoning": "Falling back to wait due to API 400 Bad Request error"
                        }
                    
                    if response.status_code == 413:
                        self.logger.error(f"HTTP 413 Payload Too Large - payload was {payload_size_kb:.2f} KB")
                        return {
                            "observations": f"Payload too large ({payload_size_kb:.2f} KB)",
                            "selected_actions": [{"action_type": "wait", "parameters": {}, "reasoning": "Payload too large", "priority": 1}],
                            "reasoning": "Reducing activity due to payload size constraints"
                        }
                    
                    response.raise_for_status()
                    result = response.json()
                    
                    # Extract AI response
                    ai_response = result["choices"][0]["message"]["content"]
                    
                    # Log token usage if available
                    usage_info = result.get("usage", {})
                    if usage_info:
                        total_tokens = usage_info.get("total_tokens", 0)
                        self.logger.info(f"API Success - Token usage: {total_tokens:,} tokens")
                    
                    # Parse JSON response using the extraction method
                    return self._extract_json_from_response(ai_response)
                        
            except Exception as e:
                self.logger.error(f"API call failed: {e}")
                return {
                    "observations": f"API error: {str(e)}",
                    "selected_actions": [{"action_type": "wait", "parameters": {}, "reasoning": "API error recovery", "priority": 1}],
                    "reasoning": "Falling back to wait due to API error"
                }
        
        # Run the async function - handle event loop properly
        try:
            # Check if we're already in an event loop
            try:
                loop = asyncio.get_running_loop()
                # We're in a running loop - this is common in async tests
                # Create a new event loop in a thread for the API call
                import concurrent.futures
                import threading
                
                def run_in_new_loop():
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        return new_loop.run_until_complete(_async_api_call())
                    finally:
                        new_loop.close()
                
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(run_in_new_loop)
                    try:
                        return future.result(timeout=120)  # 2 minute timeout for API calls
                    except concurrent.futures.TimeoutError:
                        self.logger.warning("API call exceeded 2 minute timeout")
                        return {
                            "observations": "API call timeout",
                            "selected_actions": [{"action_type": "wait", "parameters": {}, "reasoning": "API timeout recovery", "priority": 1}],
                            "reasoning": "Falling back to wait due to API timeout"
                        }
                        
            except RuntimeError:
                # No event loop running, safe to use asyncio.run
                return asyncio.run(_async_api_call())
        except Exception as e:
            self.logger.error(f"Error in async execution: {e}")
            return {
                "observations": f"Async execution error: {str(e)}",
                "selected_actions": [{"action_type": "wait", "parameters": {}, "reasoning": "Async error recovery", "priority": 1}],
                "reasoning": "Falling back to wait due to async execution error"
            }

    async def make_decision(self, world_state: Dict[str, Any], cycle_id: str):
        """
        Make a decision based on current world state.
        This method bridges the async interface with the sync decide_actions method.
        """
        try:
            self.logger.info(f"AIDecisionEngine: Starting decision cycle {cycle_id}")
            
            # Call the sync decide_actions method
            decision_data = self.decide_actions(world_state)
            
            # Convert to DecisionResult format
            selected_actions = []
            for action_data in decision_data.get("selected_actions", []):
                try:
                    action_plan = ActionPlan(
                        action_type=action_data.get("action_type", "unknown"),
                        parameters=action_data.get("parameters", {}),
                        reasoning=action_data.get("reasoning", "No reasoning provided"),
                        priority=action_data.get("priority", 5),
                    )
                    selected_actions.append(action_plan)
                except Exception as e:
                    self.logger.warning(f"Skipping malformed action: {e}")
                    continue
            
            # Limit to max actions
            if len(selected_actions) > self.max_actions_per_cycle:
                self.logger.warning(
                    f"AI selected {len(selected_actions)} actions, "
                    f"limiting to {self.max_actions_per_cycle}"
                )
                selected_actions.sort(key=lambda x: x.priority, reverse=True)
                selected_actions = selected_actions[:self.max_actions_per_cycle]
            
            result = DecisionResult(
                selected_actions=selected_actions,
                reasoning=decision_data.get("reasoning", ""),
                observations=decision_data.get("observations", ""),
                thought=decision_data.get("thought", ""),
                cycle_id=cycle_id,
            )
            
            # Log the AI's thought process for debugging
            if result.thought:
                self.logger.info(f"AI Thought Process (Cycle {cycle_id}): {result.thought}")
            
            self.logger.info(
                f"AIDecisionEngine: Cycle {cycle_id} complete - "
                f"selected {len(result.selected_actions)} actions"
            )
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error in make_decision for cycle {cycle_id}: {e}")
            return DecisionResult(
                selected_actions=[],
                reasoning=f"Error: {str(e)}",
                observations="Error during decision making",
                thought="",
                cycle_id=cycle_id,
            )
            
    @property
    def base_system_prompt(self) -> str:
        """Get the base system prompt with core sections."""
        base_prompt = ""
        
        if self.prompt_builder:
            try:
                base_prompt = self.prompt_builder.build_system_prompt(
                    include_sections=[
                        "identity", 
                        "interaction_style", 
                        "world_state_context", 
                        "tools_context", 
                        "safety_guidelines",
                        "matrix_context",
                        "farcaster_context"
                    ]
                )
            except Exception as e:
                self.logger.warning(f"Error building system prompt: {e}")
                base_prompt = ""
        
        # If prompt builder failed or returned empty, use enhanced fallback
        if not base_prompt:
            base_prompt = """You are a helpful AI assistant operating across Matrix and Farcaster platforms.

## Cross-Platform Awareness
You operate on both platforms simultaneously, maintaining platform balance and understanding the unique characteristics of each:

### Matrix Platform
- Real-time messaging in rooms
- Rich markdown formatting support
- Image sharing and media capabilities
- Community-focused discussions

### Farcaster Platform  
- Decentralized social protocol
- Cast-based interactions with FID identification
- Home timeline and notifications
- Trending content discovery
- Channel-based communities

## Node-Based System
Your world state uses an expandable node structure:
- Nodes can be expanded to view full details
- Nodes can be collapsed to save space
- Pin important nodes to keep them expanded
- Maximum of 8 nodes can be expanded simultaneously
- Use expand/collapse tools to manage information flow

## Core Capabilities
- Cross-platform message coordination
- Context-aware responses
- Media generation and sharing
- Proactive conversation engagement
- Platform-specific optimizations"""
        
        return base_prompt
