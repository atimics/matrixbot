#!/usr/bin/env python3
"""
AI Decision Engine

This module handles the AI decision-making process:
1. Takes world state observations
2. Generates action plans
3. Selects specific actions to execute (max 3 per cycle)
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List

import httpx

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

        # Base system prompt without hardcoded tools
        self.base_system_prompt = """You are an AI agent observing and acting in a digital world. You can see messages from Matrix and Farcaster channels, and you can take actions to respond or post content.

Your role is to:
1. Observe the current world state
2. Analyze what's happening and what might need attention
3. Plan up to 3 actions you could take this cycle
4. Select the most important actions to execute

WORLD STATE STRUCTURE:
The world state you receive is optimized for your decision-making:
- "current_processing_channel_id": The primary channel for this cycle's focus
- "channels": Contains channel data with different detail levels:
  * Channels with "priority": "detailed" have full recent message history including your own messages
  * Channels with "priority": "summary_only" have activity summaries but no full messages
  * The primary channel gets the most detailed view for informed responses
  * Message history includes all participants (including yourself) to maintain conversational context
- "action_history": Recent actions you have taken - use this to avoid repetitive actions
- "threads": Conversation threads relevant to the current channel (including your own messages)
- "system_status": Includes rate_limits for API awareness and current system health
- "pending_matrix_invites": Matrix room invitations waiting for your response (if any)
- "payload_stats": Information about data included in this context

MATRIX ROOM MANAGEMENT:
You can manage Matrix rooms using available tools:
- Join rooms by ID or alias using join_matrix_room
- Leave rooms you no longer want to participate in using leave_matrix_room
- Accept pending invitations from pending_matrix_invites using accept_matrix_invite
- Get current invitations using get_matrix_invites
- React to messages with emoji using react_to_matrix_message (use this for quick acknowledgments)

If you see pending_matrix_invites in the world state, you should consider whether to accept them based on:
- The inviter's identity and trustworthiness
- The room name/topic (if available)
- Your current participation in similar rooms

FARCASTER CONTENT DISCOVERY:
You have powerful content discovery tools to proactively explore and engage with Farcaster:
- get_user_timeline: View recent casts from any user (by username or FID) to understand their interests
- search_casts: Find casts matching keywords, optionally within specific channels
- get_trending_casts: Discover popular content based on engagement metrics
- get_cast_by_url: Resolve cast details from Warpcast URLs for context

Use these tools to:
- Research users before engaging to understand their interests and posting patterns
- Find relevant conversations to join based on your interests or expertise
- Discover trending topics to engage with popular content
- Analyze specific casts when URLs are mentioned in conversations

Examples of proactive discovery:
- Before replying to someone, check their timeline to understand their perspective
- Search for casts about topics you're knowledgeable about to provide value
- Check trending content in relevant channels to stay informed
- Resolve cast URLs mentioned in Matrix rooms to provide context

IMAGE UNDERSTANDING & GENERATION:
If a message in `channels` includes `image_urls` (a list of image URLs), you can understand the content of these images.
To do this, use the `describe_image` tool for each relevant image URL.
Provide the `image_url` from the message to the tool. You can also provide an optional `prompt_text` if you have a specific question about the image.
The tool will return a textual description of the image. Use this description to inform your response, make observations, or decide on further actions.

For IMAGE GENERATION, use the `generate_image` tool when:
- Users explicitly request a new image to be created
- You want to create visual content to enhance a response
- Generating diagrams, illustrations, or creative visuals would add value

IMPORTANT IMAGE TOOL USAGE GUIDELINES:
- Use `describe_image` for understanding EXISTING images from messages
- Use `generate_image` for creating NEW images when requested or valuable
- Check `recent_media_actions` to avoid repeatedly describing the same image
- If an image URL appears in `images_recently_described`, consider if another description is truly needed
- Generated images will have URLs returned - use these in follow-up messages when appropriate
- Check recent action_history to avoid redundant image operations

Example for understanding: A message has `image_urls: ["http://example.com/photo.jpg"]`.
{
  "action_type": "describe_image",
  "parameters": {"image_url": "http://example.com/photo.jpg", "prompt_text": "What is happening in this picture?"},
  "reasoning": "To understand the shared image content before replying.",
  "priority": 7
}

Example for generation: User asks "Can you create an image of a futuristic robot?"
{
  "action_type": "generate_image", 
  "parameters": {"prompt": "A sleek futuristic robot with glowing blue accents, standing in a high-tech laboratory"},
  "reasoning": "User explicitly requested image generation",
  "priority": 8
}

RATE LIMIT AWARENESS:
Check system_status.rate_limits before taking actions that use external APIs:
- "farcaster_api": Neynar/Farcaster API limits
- "matrix_homeserver": Matrix server rate limits
If remaining requests are low, prefer wait actions or prioritize most important responses.

RATE LIMITING AWARENESS:
* Your actions are subject to sophisticated rate limiting to ensure responsible platform usage
* Action-specific limits: Each tool type has hourly limits (e.g., 100 Matrix messages, 50 Farcaster posts)
* Channel-specific limits: Each channel has messaging limits per hour
* Adaptive limits: During high activity periods, processing may slow down automatically
* Burst detection: Rapid consecutive actions trigger cooldown periods
* When rate limited, prefer Wait actions or focus on highest-priority responses only
* Rate limit status is logged periodically - failed actions will indicate rate limiting

You should respond with JSON in this format:
{
  "observations": "What you notice about the current state",
  "potential_actions": [
    {
      "action_type": "tool_name_here",
      "parameters": {"param1": "value1", ...},
      "reasoning": "Why this action makes sense",
      "priority": 8
    }
  ],
  "selected_actions": [
    // The top 1-3 actions you want to execute this cycle, matching potential_actions structure
  ],
  "reasoning": "Overall reasoning for your selections"
}

Be thoughtful about when to act vs when to wait and observe. Focus primarily on the current_processing_channel_id but use other channel summaries for context. Don't feel compelled to act every cycle."""

        # Dynamic tool prompt part that gets updated by tool registry
        self.dynamic_tool_prompt_part = "No tools currently available."

        # Build the full system prompt
        self._build_full_system_prompt()

        logger.info(f"AIDecisionEngine: Initialized with model {model}")

    def _build_full_system_prompt(self):
        """Build the complete system prompt including dynamic tool descriptions."""
        self.system_prompt = (
            f"{self.base_system_prompt}\n\n{self.dynamic_tool_prompt_part}"
        )

    def update_system_prompt_with_tools(self, tool_registry):
        """
        Update the system prompt with descriptions of available tools.

        Args:
            tool_registry: ToolRegistry instance containing available tools
        """
        from ..tools.registry import (  # Import here to avoid circular imports
            ToolRegistry,
        )

        self.dynamic_tool_prompt_part = tool_registry.get_tool_descriptions_for_ai()
        self._build_full_system_prompt()
        logger.info(
            "AIDecisionEngine: System prompt updated with dynamic tool descriptions."
        )
        logger.debug(f"Tool descriptions: {self.dynamic_tool_prompt_part}")

    async def make_decision(
        self, world_state: Dict[str, Any], cycle_id: str
    ) -> DecisionResult:
        """Make a decision based on current world state"""
        logger.info(f"AIDecisionEngine: Starting decision cycle {cycle_id}")

        # Construct the prompt
        user_prompt = f"""Current World State:
{json.dumps(world_state, indent=2)}

Based on this world state, what actions (if any) should you take? Remember you can take up to {self.max_actions_per_cycle} actions this cycle, or choose to wait and observe."""

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            # Log payload size to monitor API limits
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 3500,
            }
            payload_size_bytes = len(json.dumps(payload).encode('utf-8'))
            payload_size_kb = payload_size_bytes / 1024
            logger.info(f"AIDecisionEngine: Sending payload of size ~{payload_size_kb:.2f} KB ({payload_size_bytes:,} bytes)")
            
            # Warn if payload is getting large (approaching typical 1MB limits)
            if payload_size_kb > 512:  # 512 KB warning threshold
                logger.warning(f"AIDecisionEngine: Large payload detected ({payload_size_kb:.2f} KB) - consider reducing AI_CONVERSATION_HISTORY_LENGTH or AI_INCLUDE_DETAILED_USER_INFO")

            # Make API request with proper OpenRouter headers
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

                # Check for HTTP errors and log response details
                if response.status_code == 413:
                    # 413 Payload Too Large - try to provide helpful information
                    logger.error(
                        f"AIDecisionEngine: HTTP 413 Payload Too Large error - "
                        f"payload was {payload_size_kb:.2f} KB. Consider reducing "
                        f"AI_CONVERSATION_HISTORY_LENGTH, AI_ACTION_HISTORY_LENGTH, "
                        f"or setting AI_INCLUDE_DETAILED_USER_INFO=False"
                    )
                    return DecisionResult(
                        selected_actions=[],
                        reasoning=f"Payload too large ({payload_size_kb:.2f} KB) - reduce configuration settings",
                        observations=f"HTTP 413 Error: Request payload exceeded server limits",
                        cycle_id=cycle_id,
                    )
                elif response.status_code != 200:
                    error_details = response.text
                    logger.error(
                        f"AIDecisionEngine: HTTP {response.status_code} error: {error_details}"
                    )
                    return DecisionResult(
                        selected_actions=[],
                        reasoning=f"API Error: {response.status_code}",
                        observations=f"HTTP Error: {error_details}",
                        cycle_id=cycle_id,
                    )

                response.raise_for_status()

                result = response.json()
                ai_response = result["choices"][0]["message"]["content"]

                logger.info(f"AIDecisionEngine: Received response for cycle {cycle_id}")
                logger.debug(f"AIDecisionEngine: Raw response: {ai_response[:500]}...")

                # Parse the JSON response
                try:
                    decision_data = self._extract_json_from_response(ai_response)
                    logger.debug(
                        f"AIDecisionEngine: Parsed decision data keys: {list(decision_data.keys())}"
                    )

                    # Validate basic structure
                    if not isinstance(decision_data, dict):
                        raise ValueError(f"Expected dict, got {type(decision_data)}")

                    if "selected_actions" not in decision_data:
                        logger.warning(
                            "AIDecisionEngine: No 'selected_actions' field in response, using empty list"
                        )
                        decision_data["selected_actions"] = []

                    # Convert to ActionPlan objects
                    selected_actions = []
                    for action_data in decision_data.get("selected_actions", []):
                        try:
                            action_plan = ActionPlan(
                                action_type=action_data.get("action_type", "unknown"),
                                parameters=action_data.get("parameters", {}),
                                reasoning=action_data.get(
                                    "reasoning", "No reasoning provided"
                                ),
                                priority=action_data.get("priority", 5),
                            )
                            selected_actions.append(action_plan)
                        except Exception as e:
                            logger.warning(
                                f"AIDecisionEngine: Skipping malformed action: {e}"
                            )
                            logger.debug(
                                f"AIDecisionEngine: Malformed action data: {action_data}"
                            )
                            continue

                    # Limit to max actions
                    if len(selected_actions) > self.max_actions_per_cycle:
                        logger.warning(
                            f"AIDecisionEngine: AI selected {len(selected_actions)} actions, "
                            f"limiting to {self.max_actions_per_cycle}"
                        )
                        # Sort by priority and take top N
                        selected_actions.sort(key=lambda x: x.priority, reverse=True)
                        selected_actions = selected_actions[
                            : self.max_actions_per_cycle
                        ]

                    result = DecisionResult(
                        selected_actions=selected_actions,
                        reasoning=decision_data.get("reasoning", ""),
                        observations=decision_data.get("observations", ""),
                        cycle_id=cycle_id,
                    )

                    logger.info(
                        f"AIDecisionEngine: Cycle {cycle_id} complete - "
                        f"selected {len(result.selected_actions)} actions"
                    )

                    for i, action in enumerate(result.selected_actions):
                        logger.info(
                            f"AIDecisionEngine: Action {i+1}: {action.action_type} "
                            f"(priority {action.priority})"
                        )

                    return result

                except json.JSONDecodeError as e:
                    logger.error(
                        f"AIDecisionEngine: Failed to parse AI response as JSON: {e}"
                    )
                    logger.error(f"AIDecisionEngine: Raw response was: {ai_response}")

                    # Return empty decision
                    return DecisionResult(
                        selected_actions=[],
                        reasoning="Failed to parse AI response",
                        observations="Error in AI response parsing",
                        cycle_id=cycle_id,
                    )

                except Exception as e:
                    logger.error(f"AIDecisionEngine: Error processing AI response: {e}")
                    logger.error(f"AIDecisionEngine: Raw response was: {ai_response}")

                    # Return empty decision
                    return DecisionResult(
                        selected_actions=[],
                        reasoning=f"Error processing response: {str(e)}",
                        observations="Error in AI response processing",
                        cycle_id=cycle_id,
                    )

        except Exception as e:
            logger.error(f"AIDecisionEngine: Error in decision cycle {cycle_id}: {e}")
            return DecisionResult(
                selected_actions=[],
                reasoning=f"Error: {str(e)}",
                observations="Error during decision making",
                cycle_id=cycle_id,
            )

    def _extract_json_from_response(self, response: str) -> Dict[str, Any]:
        """
        Robust JSON extraction that handles various response formats:
        - Pure JSON
        - JSON wrapped in markdown code blocks
        - JSON embedded in explanatory text
        - Multiple JSON blocks (takes the largest/most complete one)
        - JSON missing opening/closing braces
        """

        # Strategy 1: Try to parse as pure JSON first
        response_stripped = response.strip()
        if response_stripped.startswith("{") and response_stripped.endswith("}"):
            try:
                return json.loads(response_stripped)
            except json.JSONDecodeError:
                pass

        # Strategy 2: Look for JSON code blocks
        json_blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", response, re.DOTALL)
        for block in json_blocks:
            try:
                return json.loads(block.strip())
            except json.JSONDecodeError:
                continue

        # Strategy 3: Try to fix common JSON formatting issues
        # Check if it looks like JSON but is missing opening/closing braces
        response_clean = response_stripped

        # Case 1: Missing opening brace
        if not response_clean.startswith("{") and (
            "observations" in response_clean or "selected_actions" in response_clean
        ):
            # Try adding opening brace
            response_clean = "{" + response_clean

        # Case 2: Missing closing brace
        if response_clean.startswith("{") and not response_clean.endswith("}"):
            # Count braces to see if we need to add closing brace(s)
            open_count = response_clean.count("{")
            close_count = response_clean.count("}")
            if open_count > close_count:
                response_clean += "}" * (open_count - close_count)

        # Try parsing the cleaned version
        if response_clean != response_stripped:
            try:
                return json.loads(response_clean)
            except json.JSONDecodeError:
                pass

        # Strategy 4: Look for any JSON-like structure (most permissive)
        # Find all potential JSON objects in the text by looking for balanced braces
        def find_json_objects(text):
            """Find JSON objects with proper brace balancing."""
            potential_jsons = []
            i = 0
            while i < len(text):
                if text[i] == "{":
                    # Found start of potential JSON, now find the matching closing brace
                    brace_count = 1
                    start = i
                    i += 1
                    while i < len(text) and brace_count > 0:
                        if text[i] == "{":
                            brace_count += 1
                        elif text[i] == "}":
                            brace_count -= 1
                        i += 1

                    if brace_count == 0:  # Found complete JSON object
                        candidate = text[start:i]
                        try:
                            parsed = json.loads(candidate)
                            if isinstance(parsed, dict) and any(
                                key in parsed
                                for key in [
                                    "selected_actions",
                                    "observations",
                                    "potential_actions",
                                ]
                            ):
                                potential_jsons.append((len(candidate), parsed))
                        except json.JSONDecodeError:
                            pass
                else:
                    i += 1
            return potential_jsons

        potential_jsons = find_json_objects(response)

        # Return the largest/most complete JSON found
        if potential_jsons:
            potential_jsons.sort(key=lambda x: x[0], reverse=True)  # Sort by size
            return potential_jsons[0][1]

        # Strategy 5: Try to extract JSON from between common markers
        markers = [
            (r"```json\s*(.*?)\s*```", re.DOTALL),
            (r"```\s*(.*?)\s*```", re.DOTALL),
            (r"(\{.*?\})", re.DOTALL),
        ]

        for pattern, flags in markers:
            matches = re.findall(pattern, response, flags)
            for match in matches:
                cleaned = match.strip()
                if cleaned.startswith("{") and cleaned.endswith("}"):
                    try:
                        return json.loads(cleaned)
                    except json.JSONDecodeError:
                        continue

        # Strategy 6: Last resort - try to reconstruct JSON from likely content
        # Look for key patterns and try to build a minimal valid JSON
        if any(
            key in response
            for key in ["observations", "selected_actions", "potential_actions"]
        ):
            logger.warning(
                "Attempting last-resort JSON reconstruction from malformed response"
            )

            # Try to find the content between quotes after key indicators
            reconstructed = {}

            # Extract observations
            obs_match = re.search(
                r'"observations":\s*"([^"]*(?:\\.[^"]*)*)"', response, re.DOTALL
            )
            if obs_match:
                reconstructed["observations"] = obs_match.group(1)

            # Extract selected_actions (this is complex, so we'll provide an empty list if not found properly)
            actions_match = re.search(
                r'"selected_actions":\s*(\[.*?\])', response, re.DOTALL
            )
            if actions_match:
                try:
                    reconstructed["selected_actions"] = json.loads(
                        actions_match.group(1)
                    )
                except json.JSONDecodeError:
                    reconstructed["selected_actions"] = []
            else:
                reconstructed["selected_actions"] = []

            # Extract reasoning
            reasoning_match = re.search(
                r'"reasoning":\s*"([^"]*(?:\\.[^"]*)*)"', response, re.DOTALL
            )
            if reasoning_match:
                reconstructed["reasoning"] = reasoning_match.group(1)
            else:
                reconstructed[
                    "reasoning"
                ] = "Unable to extract reasoning from malformed response"

            if reconstructed:
                logger.info(
                    f"Successfully reconstructed JSON with keys: {list(reconstructed.keys())}"
                )
                return reconstructed

        # If all else fails, raise an error with helpful context
        raise json.JSONDecodeError(
            f"Could not extract valid JSON from response. Response preview: {response[:200]}...",
            response,
            0,
        )
