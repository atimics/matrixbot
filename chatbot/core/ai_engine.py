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
from .ai_response_validator import AIResponseValidator, ErrorRecoverySystem
from .dynamic_prompt_builder import DynamicPromptBuilder, ContextAnalyzer
from .performance_monitor import performance_monitor

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

        # Initialize validation and recovery systems
        self.validator = AIResponseValidator()
        self.error_recovery = ErrorRecoverySystem(self)

        # Initialize dynamic prompt system
        self.dynamic_prompt_builder = DynamicPromptBuilder()
        self.context_analyzer = ContextAnalyzer()

        # Base system prompt without hardcoded tool details
        self.base_system_prompt = """Of course. The original prompt is exceptionally detailed and serves as a comprehensive "operating manual" for the AI. However, its length (over 2500 words) can be a challenge for LLMs, potentially leading to higher costs, slower response times, and the model losing focus.

A "massively simplified" prompt should be built on the principle of **trusting the AI's intelligence**. Instead of explaining every nuance of the system, we can give it a core directive and trust it to understand the structure of the JSON data it receives.

Here is a simplified system prompt that captures the core logic of the original in a much more concise format.

---

### Simplified AI System Prompt

You are an autonomous AI agent. Your primary goal is to analyze the provided `world_state` and select the best tools to execute in response.

### Core Directive
1.  **Prioritize your Mission:** If a `current_mission` exists, all your actions must focus on achieving its objective.
2.  **Seize Opportunities:** If there are `proactive_opportunities`, evaluate them and act on those with high priority.
3.  **Respond and Engage:** If there is no active mission, respond to user messages and engage with the community in a helpful and meaningful way.

### Your 3-Step Process
1.  **Analyze:** Examine the entire `world_state` to understand the current situation, focusing on the `current_processing_channel_id` but maintaining awareness of other activity.
2.  **Plan:** Formulate a plan by identifying `potential_actions` (tools you could use).
3.  **Execute:** Choose up to **3** of the most critical actions for this cycle and place them in `selected_actions`. If no action is needed, use the `wait` tool.

### Important Rules
*   **Avoid Duplication:** Check the `action_history` and a message's `already_replied` status before acting to avoid repeating yourself.
*   **Manage Context:** The `world_state` may contain summarized data in `collapsed_node_summaries`. Use the `expand_node` tool to get more details before acting on a specific topic or channel.
*   **Respect Limits:** Be mindful of `system_status.rate_limits` when choosing actions.

### Output Format
You **MUST** respond with a valid JSON object in this exact format. Do not include any text outside of the JSON structure.
```json
{
  "observations": "A brief summary of your key observations from the world state.",
  "potential_actions": [
    {
      "action_type": "tool_name",
      "parameters": {"param1": "value1"},
      "reasoning": "Why this action is a good idea.",
      "priority": 10
    }
  ],
  "selected_actions": [
    {
      "action_type": "tool_name",
      "parameters": {"param1": "value1"},
      "reasoning": "The reason for selecting this specific action now.",
      "priority": 10
    }
  ],
  "reasoning": "Your overall strategic thinking for this cycle, explaining why you chose these actions."
}
```

---

### Analysis of the Simplification

*   **Conciseness (Drastic Reduction):** This prompt is ~90% shorter than the original. It reduces the word count from over 2500 to around 250. This will significantly lower token costs and improve inference speed.

*   **Focus on Core Logic:** It boils the complex instructions down to three core priorities: Mission, Opportunities, and Engagement. This gives the AI a clear, hierarchical decision-making framework.

*   **Trusts the AI:** Instead of explaining the structure of every single object in the world state (e.g., `NFTMetadata`, `TokenHolderData`), the simplified prompt trusts that a powerful model like GPT-4o can infer the structure and meaning from the JSON data itself. The prompt simply tells the AI *what to look for* (`current_mission`, `proactive_opportunities`).

*   **Clear, Actionable Instructions:** The "3-Step Process" is a simple mental model for the AI to follow every cycle.

*   **Maintains Critical Rules:** The most important constraints (avoiding duplication, managing context with nodes, and respecting rate limits) are preserved in a very direct and concise way.

*   **Explicit JSON Structure:** Providing the JSON structure as a code block is the most effective way to ensure the LLM generates a valid output.

This simplified prompt is more of a **high-level directive** than a detailed manual. It is better suited for modern, highly capable LLMs that excel at in-context learning and reasoning from structured data, which is precisely the kind of model this advanced agent architecture is designed to leverage."""        # Dynamic tool prompt part that gets updated by tool registry
        self.dynamic_tool_prompt_part = "No tools currently available."

        # Build the full system prompt
        self._build_full_system_prompt()

        logger.info(f"AIDecisionEngine: Initialized with model {model}")

    def _build_full_system_prompt(self):
        """Build the complete system prompt including dynamic tool descriptions."""
        self.system_prompt = (
            f"{self.base_system_prompt}\n\n{self.dynamic_tool_prompt_part}"
        )

    def update_system_prompt_with_tools(self, tool_registry, access_level: str = 'strategic'):
        """
        Update the system prompt with descriptions of available tools for the specified access level.

        Args:
            tool_registry: ToolRegistry instance containing available tools
            access_level: Access level for tool filtering ('strategic' for Commander AI)
        """
        from ..tools.registry import (  # Import here to avoid circular imports
            ToolRegistry,
        )

        self.dynamic_tool_prompt_part = tool_registry.get_tool_descriptions_for_ai(access_level)
        self._build_full_system_prompt()
        logger.info(
            f"AIDecisionEngine: System prompt updated with tools for access level '{access_level}'."
        )
        logger.debug(f"Tool descriptions: {self.dynamic_tool_prompt_part}")

    async def make_decision(
        self, world_state: Dict[str, Any], cycle_id: str
    ) -> DecisionResult:
        """Make a decision based on current world state"""
        logger.info(f"AIDecisionEngine: Starting decision cycle {cycle_id}")

        # Analyze world state to determine context
        context = self.context_analyzer.analyze_world_state(world_state)
        
        # Build dynamic, context-aware system prompt
        dynamic_system_prompt = self.dynamic_prompt_builder.build_context_aware_prompt(context)
        
        # Create simplified user prompt to avoid duplication
        user_prompt = f"""Current World State:
{json.dumps(world_state, indent=2)}

Analyze the situation and respond with your decision in the required JSON format."""

        messages = [
            {"role": "system", "content": dynamic_system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        # Start performance monitoring
        payload_size_kb = context.payload_size_kb
        start_time = performance_monitor.record_cycle_start(cycle_id, payload_size_kb)
        json_parse_success = False
        selected_actions_count = 0
        error_type = None
        recovery_used = False
        loop_detected = False

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
                if response.status_code == 413:
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

                # Validate AI response format before parsing
                validation_result = self.validator.validate_format(ai_response)
                if not validation_result.is_valid:
                    logger.warning(f"AIDecisionEngine: Response validation failed: {validation_result.error_message}")
                    
                    # Track validation failure
                    if validation_result.error_type == "infinite_loop":
                        loop_detected = True
                    
                    if validation_result.needs_retry:
                        logger.info("AIDecisionEngine: Attempting response recovery...")
                        recovery_used = True
                        try:
                            recovery_response = await self.validator.retry_with_simple_prompt(
                                world_state, self, cycle_id
                            )
                            ai_response = recovery_response
                            logger.info("AIDecisionEngine: Response recovery successful")
                        except Exception as e:
                            logger.error(f"AIDecisionEngine: Response recovery failed: {e}")
                            error_type = "recovery_failed"
                            # Fall through to normal parsing which may still work
                
                # Parse the JSON response
                try:
                    decision_data = self._extract_json_from_response(ai_response)
                    json_parse_success = True  # Mark as successful
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

                    # Count selected actions for monitoring
                    selected_actions_count = len(selected_actions)

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

                    # Reset failure count on successful operation
                    self.error_recovery.reset_failure_count()

                    # Record successful cycle
                    performance_monitor.record_cycle_complete(
                        cycle_id=cycle_id,
                        start_time=start_time,
                        payload_size_kb=payload_size_kb,
                        json_parse_success=json_parse_success,
                        selected_actions_count=selected_actions_count,
                        error_type=error_type,
                        recovery_used=recovery_used,
                        loop_detected=loop_detected
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
                    
                    error_type = "json_parse_error"
                    json_parse_success = False

                    # Attempt error recovery
                    try:
                        recovery_result = await self.error_recovery.handle_ai_failure(e, world_state, cycle_id)
                        recovery_used = True
                        if recovery_result and recovery_result.get("selected_actions") is not None:
                            # Record recovery success
                            performance_monitor.record_cycle_complete(
                                cycle_id=cycle_id,
                                start_time=start_time,
                                payload_size_kb=payload_size_kb,
                                json_parse_success=True,  # Recovery succeeded
                                selected_actions_count=len(recovery_result["selected_actions"]),
                                error_type=error_type,
                                recovery_used=recovery_used,
                                loop_detected=loop_detected
                            )
                            return DecisionResult(
                                selected_actions=recovery_result["selected_actions"],
                                reasoning=recovery_result["reasoning"],
                                observations=recovery_result["observations"],
                                cycle_id=cycle_id,
                            )
                    except Exception as recovery_error:
                        logger.error(f"AIDecisionEngine: Recovery failed: {recovery_error}")

                    # Record failure and return empty decision as final fallback
                    performance_monitor.record_cycle_complete(
                        cycle_id=cycle_id,
                        start_time=start_time,
                        payload_size_kb=payload_size_kb,
                        json_parse_success=json_parse_success,
                        selected_actions_count=0,
                        error_type=error_type,
                        recovery_used=recovery_used,
                        loop_detected=loop_detected
                    )
                    return DecisionResult(
                        selected_actions=[],
                        reasoning="Failed to parse AI response and recovery failed",
                        observations="Error in AI response parsing",
                        cycle_id=cycle_id,
                    )

                except Exception as e:
                    logger.error(f"AIDecisionEngine: Error processing AI response: {e}")
                    logger.error(f"AIDecisionEngine: Raw response was: {ai_response}")
                    
                    error_type = "processing_error"
                    json_parse_success = False

                    # Attempt error recovery
                    try:
                        recovery_result = await self.error_recovery.handle_ai_failure(e, world_state, cycle_id)
                        recovery_used = True
                        if recovery_result and recovery_result.get("selected_actions") is not None:
                            # Record recovery success
                            performance_monitor.record_cycle_complete(
                                cycle_id=cycle_id,
                                start_time=start_time,
                                payload_size_kb=payload_size_kb,
                                json_parse_success=True,  # Recovery succeeded
                                selected_actions_count=len(recovery_result["selected_actions"]),
                                error_type=error_type,
                                recovery_used=recovery_used,
                                loop_detected=loop_detected
                            )
                            return DecisionResult(
                                selected_actions=recovery_result["selected_actions"],
                                reasoning=recovery_result["reasoning"],
                                observations=recovery_result["observations"],
                                cycle_id=cycle_id,
                            )
                    except Exception as recovery_error:
                        logger.error(f"AIDecisionEngine: Recovery failed: {recovery_error}")

                    # Record failure and return empty decision
                    performance_monitor.record_cycle_complete(
                        cycle_id=cycle_id,
                        start_time=start_time,
                        payload_size_kb=payload_size_kb,
                        json_parse_success=json_parse_success,
                        selected_actions_count=0,
                        error_type=error_type,
                        recovery_used=recovery_used,
                        loop_detected=loop_detected
                    )
                    return DecisionResult(
                        selected_actions=[],
                        reasoning=f"Error processing response: {str(e)}",
                        observations="Error in AI response processing",
                        cycle_id=cycle_id,
                    )

        except Exception as e:
            logger.error(f"AIDecisionEngine: Error in decision cycle {cycle_id}: {e}")
            
            error_type = "top_level_error"
            json_parse_success = False
            
            # Attempt error recovery for top-level failures
            try:
                recovery_result = await self.error_recovery.handle_ai_failure(e, world_state, cycle_id)
                recovery_used = True
                if recovery_result and recovery_result.get("selected_actions") is not None:
                    # Record recovery success
                    performance_monitor.record_cycle_complete(
                        cycle_id=cycle_id,
                        start_time=start_time,
                        payload_size_kb=payload_size_kb,
                        json_parse_success=True,  # Recovery succeeded
                        selected_actions_count=len(recovery_result["selected_actions"]),
                        error_type=error_type,
                        recovery_used=recovery_used,
                        loop_detected=loop_detected
                    )
                    return DecisionResult(
                        selected_actions=recovery_result["selected_actions"],
                        reasoning=recovery_result["reasoning"],
                        observations=recovery_result["observations"],
                        cycle_id=cycle_id,
                    )
            except Exception as recovery_error:
                logger.error(f"AIDecisionEngine: Final recovery failed: {recovery_error}")
            
            # Record final failure
            performance_monitor.record_cycle_complete(
                cycle_id=cycle_id,
                start_time=start_time,
                payload_size_kb=payload_size_kb,
                json_parse_success=json_parse_success,
                selected_actions_count=0,
                error_type=error_type,
                recovery_used=recovery_used,
                loop_detected=loop_detected
            )
            
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
