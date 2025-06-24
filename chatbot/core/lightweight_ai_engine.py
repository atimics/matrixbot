"""
Lightweight AI Engine for Mission-Oriented Sub-Agents

This engine is designed for simple, conversational tasks where we need fast,
cheap responses without the complexity of the full AI decision engine.
It uses simpler models and focused prompts for mission fulfillment.
"""

import json
import logging
from typing import Dict, List, Any, Optional
from dataclasses import asdict

import httpx

from chatbot.config import settings
from .ai_engine import ActionPlan
from .world_state.structures import Mission

logger = logging.getLogger(__name__)


class LightweightAIEngine:
    """
    A simplified AI engine for Sub-Agents handling specific missions.
    
    This engine is optimized for:
    - Quick conversational responses
    - Simple, goal-oriented tasks
    - Lower cost operation
    - Minimal context requirements
    - Tool access limited to 'conversational' level
    """
    
    def __init__(self, api_key: Optional[str] = None, tool_registry=None):
        """Initialize with a lightweight model configuration and access to conversational tools."""
        self.api_key = api_key or settings.openrouter_api_key
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        self.model = settings.processing.lightweight_ai_model or "openai/gpt-4o-mini"
        self.max_tokens = settings.processing.lightweight_ai_max_tokens or 500
        self.temperature = settings.processing.lightweight_ai_temperature or 0.7
        self.tool_registry = tool_registry
        self.access_level = 'conversational'  # Sub-Agents have conversational access level
        
        if not self.api_key:
            logger.warning("LightweightAIEngine: No API key provided, AI functions will be limited")
        
        logger.info(f"LightweightAIEngine initialized with model: {self.model}, access level: {self.access_level}")
    
    def set_tool_registry(self, tool_registry):
        """Set the tool registry for this engine."""
        self.tool_registry = tool_registry
        logger.info("LightweightAIEngine: Tool registry configured")
    
    def get_available_tools_description(self) -> str:
        """Get descriptions of tools available to this engine's access level."""
        if not self.tool_registry:
            # Fallback descriptions for basic functionality
            return """
Available tools:
- send_matrix_message: Send a message to a Matrix channel
  Parameters:
    - channel_id: string (Matrix room ID)
    - content: string (message content)
- send_farcaster_post: Post a message to Farcaster
  Parameters:
    - content: string (post content)
    - parent_hash: string (optional, for replies)
"""
        
        return self.tool_registry.get_tool_descriptions_for_ai(self.access_level)
    
    async def decide_mission_actions(
        self, 
        payload: Dict[str, Any],
        cycle_id: Optional[str] = None
    ) -> List[ActionPlan]:
        """
        Make decisions for a specific mission with minimal context.
        
        Args:
            payload: Simplified payload with mission and recent messages
            cycle_id: Optional cycle identifier for logging
            
        Returns:
            List of ActionPlan objects representing the Sub-Agent's decisions
        """
        try:
            mission_data = payload.get("mission", {})
            messages = payload.get("messages", [])
            
            # Build focused prompt for mission fulfillment
            prompt = self._build_mission_prompt(mission_data, messages)
            
            logger.debug(f"LightweightAI: Processing mission {mission_data.get('id', 'unknown')} for cycle {cycle_id}")
            
            # Get AI response using lightweight model
            response = await self._get_ai_response(prompt)
            
            # Parse response into action plans
            actions = self._parse_ai_response(response, mission_data.get("channel_id"))
            
            logger.info(f"LightweightAI: Generated {len(actions)} actions for mission {mission_data.get('id', 'unknown')}")
            return actions
            
        except Exception as e:
            logger.error(f"LightweightAI: Error in decide_mission_actions: {e}")
            return []
    
    def _build_mission_prompt(self, mission_data: Dict[str, Any], messages: List[Dict[str, Any]]) -> str:
        """
        Build a focused, minimal prompt for mission fulfillment.
        
        This prompt is much simpler than the main AI engine's complex prompts.
        """
        objective = mission_data.get("objective", "Assist the user")
        mission_id = mission_data.get("id", "unknown")
        channel_id = mission_data.get("channel_id", "unknown")
        
        # Get available tools for this access level
        tools_description = self.get_available_tools_description()
        
        # Format recent messages
        message_context = ""
        if messages:
            message_context = "Recent messages:\n"
            for msg in messages[-5:]:  # Only show last 5 messages
                sender = msg.get("sender", "unknown")
                content = msg.get("content", "")[:200]  # Truncate long messages
                message_context += f"- {sender}: {content}\n"
        
        prompt = f"""You are a focused AI assistant working on a specific mission.

MISSION:
ID: {mission_id}
Objective: {objective}
Channel: {channel_id}

{message_context}

Your role as a Sub-Agent:
1. Focus ONLY on completing the mission objective
2. Keep responses conversational and concise
3. Use available tools to communicate or gather information
4. Take simple, direct actions toward the mission goal

{tools_description}

Analyze the recent messages and mission objective, then respond with a JSON containing your decision:

{{
    "reasoning": "brief explanation of what you're doing",
    "actions": [
        {{
            "action_type": "tool_name",
            "parameters": {{"param": "value"}},
            "reasoning": "why this action helps the mission",
            "priority": 1-10
        }}
    ]
}}

Focus on simple, conversational actions that directly advance the mission. Avoid complex strategic planning."""
        
        return prompt
    
    async def _get_ai_response(self, prompt: str) -> str:
        """Get response from the lightweight AI model using OpenRouter."""
        if not self.api_key:
            logger.warning("LightweightAI: No API key available, returning default response")
            return '{"reasoning": "No API key available", "actions": []}'
        
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/ratimics/matrixbot",
                "X-Title": "MatrixBot Lightweight AI"
            }
            
            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "system", 
                        "content": "You are a helpful AI assistant. Always respond with valid JSON."
                    },
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": self.max_tokens,
                "temperature": self.temperature
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.base_url,
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                
                result = response.json()
                content = result["choices"][0]["message"]["content"]
                
                logger.debug(f"LightweightAI: Received response from {self.model}")
                return content.strip()
                
        except Exception as e:
            logger.error(f"LightweightAI: Error getting AI response: {e}")
            return '{"reasoning": "AI request failed", "actions": []}'
    
    def _parse_ai_response(self, response: str, channel_id: Optional[str]) -> List[ActionPlan]:
        """Parse the AI response into ActionPlan objects."""
        try:
            # Parse JSON response
            data = json.loads(response)
            reasoning = data.get("reasoning", "No reasoning provided")
            actions_data = data.get("actions", [])
            
            action_plans = []
            for action_data in actions_data:
                action_type = action_data.get("action_type")
                parameters = action_data.get("parameters", {})
                action_reasoning = action_data.get("reasoning", reasoning)
                priority = action_data.get("priority", 5)
                
                # Ensure channel_id is set for relevant actions
                if action_type in ["send_matrix_message", "send_farcaster_post"] and "channel_id" not in parameters:
                    parameters["channel_id"] = channel_id
                
                action_plan = ActionPlan(
                    action_type=action_type,
                    parameters=parameters,
                    reasoning=action_reasoning,
                    priority=priority
                )
                action_plans.append(action_plan)
            
            return action_plans
            
        except json.JSONDecodeError as e:
            logger.error(f"LightweightAI: Failed to parse JSON response: {e}")
            logger.error(f"LightweightAI: Raw response: {response}")
            return []
        except Exception as e:
            logger.error(f"LightweightAI: Error parsing AI response: {e}")
            return []
    
    def get_status(self) -> Dict[str, Any]:
        """Get current engine status."""
        return {
            "engine_type": "lightweight",
            "model": self.model,
            "access_level": self.access_level,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "api_available": bool(self.api_key),
            "tool_registry_available": bool(self.tool_registry)
        }
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "api_key_available": self.api_key is not None
        }
