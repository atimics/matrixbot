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

from .prompts import prompt_builder

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

    def __init__(self, api_key: str, model: str = "openai/gpt-4o-mini", prompt_builder_instance=None):
        if not prompt_builder_instance:
            # Use the global prompt_builder instance by default
            prompt_builder_instance = prompt_builder
        
        self.api_key = api_key
        self.model = model
        self.prompt_builder = prompt_builder_instance
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        self.max_actions_per_cycle = 3

        logger.info(f"AIDecisionEngine: Initialized with model {model} and PromptBuilder.")

    async def make_decision(
        self, world_state: Dict[str, Any], cycle_id: str
    ) -> DecisionResult:
        """Make a decision based on current world state"""
        logger.info(f"AIDecisionEngine: Starting decision cycle {cycle_id}")

        # Dynamically build the system prompt for this specific cycle
        # This is a simple example; it can be made more sophisticated
        # based on the content of the world_state.
        prompt_sections = [
            "identity", 
            "interaction_style", 
            "world_state_context", 
            "tools_context", 
            "safety_guidelines"
        ]
        
        # Add platform-specific context if relevant
        primary_channel_id = world_state.get("current_processing_channel_id")
        if primary_channel_id and "matrix" in str(primary_channel_id):
            prompt_sections.append("matrix_context")
        if primary_channel_id and "farcaster" in str(primary_channel_id):
            prompt_sections.append("farcaster_context")

        # Get tool descriptions from the tool registry (which should be passed in context or available)
        tool_descriptions = world_state.get("available_tools", "No tools available.")
        
        system_prompt = self.prompt_builder.build_system_prompt(
            include_sections=prompt_sections
        )
        system_prompt += f"\n\n## Available Tools\n{tool_descriptions}"

        # Construct the user prompt
        user_prompt = f"""Current World State:
{json.dumps(world_state, indent=2)}

Based on this world state, what actions (if any) should you take? Remember you can take up to {self.max_actions_per_cycle} actions this cycle, or choose to wait and observe."""

        messages = [
            {"role": "system", "content": system_prompt},
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
            
            # Warn if payload is getting large (with new optimized thresholds)
            if payload_size_kb > 256:  # Reduced from 512 KB due to optimizations
                logger.warning(f"AIDecisionEngine: Large payload detected ({payload_size_kb:.2f} KB) - payload optimization is enabled but still large")
            elif payload_size_kb > 100:  # Info threshold for monitoring
                logger.info(f"AIDecisionEngine: Moderate payload size ({payload_size_kb:.2f} KB) - within acceptable range after optimization")

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
                if response.status_code == 402:
                    # 402 Payment Required - Re-raise specifically for the orchestrator to catch and handle fallbacks
                    logger.error(f"AIDecisionEngine: HTTP 402 Payment Required. Raising exception for fallback handler.")
                    response.raise_for_status()  # This will raise an httpx.HTTPStatusError
                elif response.status_code == 413:
                    # 413 Payload Too Large - try to provide information
                    logger.error(
                        f"AIDecisionEngine: HTTP 413 Payload Too Large error - "
                        f"payload was {payload_size_kb:.2f} KB. Payload optimization is enabled "
                        f"but payload is still too large. Check for excessive world state data or adjust AI payload settings in config."
                    )
                    return DecisionResult(
                        selected_actions=[],
                        reasoning=f"Payload too large ({payload_size_kb:.2f} KB) - reduce AI payload settings in config.",
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

        # If all else fails, raise an error with context
        raise json.JSONDecodeError(
            f"Could not extract valid JSON from response. Response preview: {response[:200]}...",
            response,
            0,
        )
