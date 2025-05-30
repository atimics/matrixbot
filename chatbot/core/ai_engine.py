#!/usr/bin/env python3
"""
AI Decision Engine

This module handles the AI decision-making process:
1. Takes world state observations
2. Generates action plans
3. Selects specific actions to execute (max 3 per cycle)
"""

import asyncio
import json
import logging
import time
from typing import Dict, List, Any, Optional
import httpx
from dataclasses import dataclass

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
    cycle_id: str

class AIDecisionEngine:
    """Handles AI decision making and action planning"""
    
    def __init__(self, api_key: str, model: str = "openai/gpt-4o-mini"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        self.max_actions_per_cycle = 3
        
        # System prompt that defines the AI's role and capabilities
        self.system_prompt = """You are an AI agent observing and acting in a digital world. You can see messages from Matrix and Farcaster channels, and you can take actions to respond or post content.

Your role is to:
1. Observe the current world state
2. Analyze what's happening and what might need attention
3. Plan up to 3 actions you could take this cycle
4. Select the most important actions to execute

Available actions:
- send_matrix_message: Send a message to a Matrix channel
- send_matrix_reply: Reply to a specific Matrix message  
- send_farcaster_post: Post to Farcaster
- wait: Do nothing this cycle (use when no action is needed)

You should respond with JSON in this format:
{
  "observations": "What you notice about the current state",
  "potential_actions": [
    {
      "action_type": "send_matrix_reply",
      "parameters": {"channel_id": "...", "reply_to_id": "...", "content": "..."},
      "reasoning": "Why this action makes sense",
      "priority": 8
    }
  ],
  "selected_actions": [
    // The top 1-3 actions you want to execute this cycle
  ],
  "reasoning": "Overall reasoning for your selections"
}

Be thoughtful about when to act vs when to wait and observe. Don't feel compelled to act every cycle."""

        logger.info(f"AIDecisionEngine: Initialized with model {model}")
    
    async def make_decision(self, world_state: Dict[str, Any], cycle_id: str) -> DecisionResult:
        """Make a decision based on current world state"""
        logger.info(f"AIDecisionEngine: Starting decision cycle {cycle_id}")
        
        # Construct the prompt
        user_prompt = f"""Current World State:
{json.dumps(world_state, indent=2)}

Based on this world state, what actions (if any) should you take? Remember you can take up to {self.max_actions_per_cycle} actions this cycle, or choose to wait and observe."""

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        try:
            # Make API request with proper OpenRouter headers
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    self.base_url,
                    json={
                        "model": self.model,
                        "messages": messages,
                        "temperature": 0.7,
                        "max_tokens": 2000
                    },
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://github.com/ratimics/chatbot",
                        "X-Title": "Ratimics Chatbot"
                    }
                )
                
                # Check for HTTP errors and log response details
                if response.status_code != 200:
                    error_details = response.text
                    logger.error(f"AIDecisionEngine: HTTP {response.status_code} error: {error_details}")
                    return DecisionResult(
                        selected_actions=[],
                        reasoning=f"API Error: {response.status_code}",
                        observations=f"HTTP Error: {error_details}",
                        cycle_id=cycle_id
                    )
                
                response.raise_for_status()
                
                result = response.json()
                ai_response = result["choices"][0]["message"]["content"]
                
                logger.info(f"AIDecisionEngine: Received response for cycle {cycle_id}")
                logger.debug(f"AIDecisionEngine: Raw response: {ai_response[:500]}...")
                
                # Parse the JSON response
                try:
                    # Clean up the response (remove markdown formatting if present)
                    import re
                    # Use regex to strip markdown code block markers
                    cleaned_response = re.sub(r"^\s*```json\s*|\s*```\s*$", "", ai_response.strip(), flags=re.DOTALL)
                    
                    decision_data = json.loads(cleaned_response)
                    
                    # Convert to ActionPlan objects
                    selected_actions = []
                    for action_data in decision_data.get("selected_actions", []):
                        action_plan = ActionPlan(
                            action_type=action_data["action_type"],
                            parameters=action_data["parameters"],
                            reasoning=action_data["reasoning"],
                            priority=action_data.get("priority", 5)
                        )
                        selected_actions.append(action_plan)
                    
                    # Limit to max actions
                    if len(selected_actions) > self.max_actions_per_cycle:
                        logger.warning(f"AIDecisionEngine: AI selected {len(selected_actions)} actions, "
                                     f"limiting to {self.max_actions_per_cycle}")
                        # Sort by priority and take top N
                        selected_actions.sort(key=lambda x: x.priority, reverse=True)
                        selected_actions = selected_actions[:self.max_actions_per_cycle]
                    
                    result = DecisionResult(
                        selected_actions=selected_actions,
                        reasoning=decision_data.get("reasoning", ""),
                        observations=decision_data.get("observations", ""),
                        cycle_id=cycle_id
                    )
                    
                    logger.info(f"AIDecisionEngine: Cycle {cycle_id} complete - "
                              f"selected {len(result.selected_actions)} actions")
                    
                    for i, action in enumerate(result.selected_actions):
                        logger.info(f"AIDecisionEngine: Action {i+1}: {action.action_type} "
                                  f"(priority {action.priority})")
                    
                    return result
                    
                except json.JSONDecodeError as e:
                    logger.error(f"AIDecisionEngine: Failed to parse AI response as JSON: {e}")
                    logger.error(f"AIDecisionEngine: Raw response was: {ai_response}")
                    
                    # Return empty decision
                    return DecisionResult(
                        selected_actions=[],
                        reasoning="Failed to parse AI response",
                        observations="Error in AI response parsing",
                        cycle_id=cycle_id
                    )
                
        except Exception as e:
            logger.error(f"AIDecisionEngine: Error in decision cycle {cycle_id}: {e}")
            return DecisionResult(
                selected_actions=[],
                reasoning=f"Error: {str(e)}",
                observations="Error during decision making",
                cycle_id=cycle_id
            )
