#!/usr/bin/env python3
"""
AI Response Validation and Recovery System

This module implements proactive validation and retry logic for AI responses,
addressing the critical JSON parsing failures identified in the engineering report.
"""

import json
import logging
import re
from typing import Dict, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of response validation"""
    is_valid: bool
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    needs_retry: bool = False
    suggested_fix: Optional[str] = None


class AIResponseValidator:
    """Validates AI responses and provides retry strategies."""
    
    def __init__(self):
        self.loop_detection_threshold = 3
        self.max_retry_attempts = 2
        
    def validate_format(self, response: str) -> ValidationResult:
        """
        Validate response format before attempting to parse JSON.
        
        Args:
            response: Raw AI response string
            
        Returns:
            ValidationResult with validation details
        """
        response_stripped = response.strip()
        
        # Check 1: Detect infinite loop pattern
        if self._detect_infinite_loop(response_stripped):
            return ValidationResult(
                is_valid=False,
                error_type="infinite_loop",
                error_message="AI response contains infinite loop pattern",
                needs_retry=True,
                suggested_fix="Use simplified prompt with clear constraints"
            )
        
        # Check 2: Ensure response contains JSON structure
        if not self._contains_json_structure(response_stripped):
            return ValidationResult(
                is_valid=False,
                error_type="no_json",
                error_message="Response does not contain recognizable JSON structure",
                needs_retry=True,
                suggested_fix="Use format-enforced prompt"
            )
        
        # Check 3: Basic JSON format validation
        if not self._basic_json_validation(response_stripped):
            return ValidationResult(
                is_valid=False,
                error_type="malformed_json",
                error_message="Response contains malformed JSON",
                needs_retry=False,  # Let existing parser handle this
                suggested_fix="Apply JSON repair strategies"
            )
        
        return ValidationResult(is_valid=True)
    
    def _detect_infinite_loop(self, response: str) -> bool:
        """Detect if the AI response contains infinite loop patterns."""
        # Look for repetitive phrases that indicate loops
        loop_indicators = [
            "I will wait for the next observation cycle",
            "I will analyze the recent messages",
            "I will determine if any immediate action",
            "Based on this, I will determine"
        ]
        
        for indicator in loop_indicators:
            count = response.lower().count(indicator.lower())
            if count > self.loop_detection_threshold:
                logger.warning(f"Detected infinite loop: '{indicator}' repeated {count} times")
                return True
        
        # Check for excessive repetition of any phrase
        if self._detect_excessive_repetition(response):
            return True
            
        return False
    
    def _detect_excessive_repetition(self, response: str) -> bool:
        """Detect excessive repetition of any phrase."""
        # Split into sentences and look for repetition
        sentences = re.split(r'[.!?]\s+', response)
        sentence_counts = {}
        
        for sentence in sentences:
            sentence_clean = sentence.strip().lower()
            if len(sentence_clean) > 10:  # Only check meaningful sentences
                sentence_counts[sentence_clean] = sentence_counts.get(sentence_clean, 0) + 1
        
        # Check if any sentence appears too many times
        for sentence, count in sentence_counts.items():
            if count > self.loop_detection_threshold:
                logger.warning(f"Excessive repetition detected: '{sentence[:50]}...' repeated {count} times")
                return True
        
        return False
    
    def _contains_json_structure(self, response: str) -> bool:
        """Check if response contains basic JSON structure indicators."""
        json_indicators = [
            "selected_actions",
            "observations",
            "reasoning",
            "potential_actions"
        ]
        
        # Must contain at least one key JSON field
        has_json_field = any(indicator in response for indicator in json_indicators)
        
        # Must contain some brace structure
        has_braces = "{" in response and "}" in response
        
        return has_json_field and has_braces
    
    def _basic_json_validation(self, response: str) -> bool:
        """Perform basic JSON structure validation."""
        # Count braces - they should be roughly balanced
        open_braces = response.count("{")
        close_braces = response.count("}")
        
        # Allow for some imbalance that can be fixed
        brace_diff = abs(open_braces - close_braces)
        if brace_diff > 3:  # Too imbalanced to fix easily
            return False
        
        # Check for basic quote balance (rough check)
        quote_count = response.count('"')
        if quote_count % 2 != 0 and quote_count > 10:  # Significant quote imbalance
            logger.warning(f"Potential quote imbalance: {quote_count} quotes found")
        
        return True
    
    async def retry_with_simple_prompt(self, world_state: Dict, ai_engine, cycle_id: str) -> str:
        """
        Fallback to a highly constrained, simplified prompt on validation failure.
        
        Args:
            world_state: Current world state
            ai_engine: AI engine instance for making the retry call
            cycle_id: Current cycle ID
            
        Returns:
            Simplified AI response
        """
        # Summarize the current situation to reduce context size
        situation_summary = self._summarize_state(world_state)
        
        # Create a minimal, highly constrained prompt
        simple_prompt = f"""
Your previous response was invalid. Respond with ONLY valid JSON in this exact format, with no other text:

{{
  "observations": "Brief observation about the current situation",
  "selected_actions": [],
  "reasoning": "Brief explanation of why waiting or taking no action"
}}

Current situation: {situation_summary}

Rules:
1. Respond ONLY with the JSON object above
2. No explanatory text before or after
3. Keep all text fields brief (under 100 characters each)
4. Use empty array for selected_actions unless immediate action is clearly needed
5. If unsure, choose to wait and observe
        """.strip()
        
        try:
            # Make a simplified API call with reduced context
            import httpx
            
            payload = {
                "model": ai_engine.model,
                "messages": [
                    {"role": "system", "content": "You are an AI assistant. Respond only with valid JSON in the exact format requested."},
                    {"role": "user", "content": simple_prompt}
                ],
                "temperature": 0.1,  # Lower temperature for more consistent format
                "max_tokens": 500    # Limit response length
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    ai_engine.base_url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {ai_engine.api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://github.com/ratimics/chatbot",
                        "X-Title": "Ratimics Chatbot - Recovery",
                    },
                )
                
                if response.status_code == 200:
                    result = response.json()
                    ai_response = result["choices"][0]["message"]["content"]
                    logger.info(f"AIResponseValidator: Recovery attempt successful for cycle {cycle_id}")
                    return ai_response
                else:
                    logger.error(f"AIResponseValidator: Recovery API call failed: {response.status_code}")
                    return self._emergency_fallback_response()
                    
        except Exception as e:
            logger.error(f"AIResponseValidator: Recovery attempt failed: {e}")
            return self._emergency_fallback_response()
    
    def _summarize_state(self, world_state: Dict) -> str:
        """Create a brief summary of the world state for recovery prompts."""
        summary_parts = []
        
        # Get primary channel info
        if "current_processing_channel_id" in world_state:
            channel_id = world_state["current_processing_channel_id"]
            summary_parts.append(f"Processing channel: {channel_id}")
        
        # Get basic channel info
        if "channels" in world_state:
            channel_count = len(world_state["channels"])
            summary_parts.append(f"Active channels: {channel_count}")
        
        # Get recent activity
        if "action_history" in world_state:
            recent_actions = len(world_state.get("action_history", []))
            summary_parts.append(f"Recent actions: {recent_actions}")
        
        return " | ".join(summary_parts) if summary_parts else "Standard monitoring state"
    
    def _emergency_fallback_response(self) -> str:
        """Provide an emergency fallback response when all else fails."""
        return json.dumps({
            "observations": "AI response validation failed, entering safe mode",
            "selected_actions": [],
            "reasoning": "Using emergency fallback due to AI response issues"
        })


class ErrorRecoverySystem:
    """Manages comprehensive error recovery strategies for AI failures."""
    
    def __init__(self, ai_engine):
        self.ai_engine = ai_engine
        self.validator = AIResponseValidator()
        self.failure_count = 0
        self.max_failures = 3
        
    async def handle_ai_failure(self, error: Exception, world_state: Dict, cycle_id: str) -> Dict:
        """
        Attempt a series of fallback strategies to recover from AI failure.
        
        Args:
            error: The exception that caused the failure
            world_state: Current world state
            cycle_id: Current cycle ID
            
        Returns:
            Recovery result dict with selected_actions, reasoning, etc.
        """
        self.failure_count += 1
        logger.warning(f"AI failure #{self.failure_count} in cycle {cycle_id}: {error}")
        
        strategies = [
            self._retry_with_reduced_context,
            self._retry_with_simple_prompt,
            self._fallback_to_wait_action,
            self._enter_emergency_safe_mode
        ]
        
        for i, strategy in enumerate(strategies):
            try:
                logger.info(f"Attempting recovery strategy {i+1}: {strategy.__name__}")
                result = await strategy(world_state, cycle_id)
                if result is not None and result.get("selected_actions") is not None:
                    logger.info(f"Recovery successful with strategy: {strategy.__name__}")
                    return result
            except Exception as e:
                logger.error(f"Recovery strategy {strategy.__name__} failed: {e}")
                continue
        
        # If all strategies fail, return safe default
        logger.error(f"All recovery strategies failed for cycle {cycle_id}")
        return self._safe_default_response(cycle_id)
    
    async def _retry_with_reduced_context(self, world_state: Dict, cycle_id: str) -> Optional[Dict]:
        """Retry with significantly reduced context."""
        # Create a minimal world state with only essential information
        reduced_state = {
            "current_processing_channel_id": world_state.get("current_processing_channel_id"),
            "system_status": {"status": "reduced_context_mode"},
            "action_history": world_state.get("action_history", [])[-3:]  # Only last 3 actions
        }
        
        try:
            # Use the existing AI engine but with reduced payload
            decision_result = await self.ai_engine.make_decision(reduced_state, f"{cycle_id}-recovery1")
            return {
                "selected_actions": decision_result.selected_actions,
                "reasoning": f"Recovery with reduced context: {decision_result.reasoning}",
                "observations": decision_result.observations
            }
        except Exception as e:
            logger.error(f"Reduced context retry failed: {e}")
            return None
    
    async def _retry_with_simple_prompt(self, world_state: Dict, cycle_id: str) -> Optional[Dict]:
        """Use the validator's simple prompt retry."""
        try:
            simple_response = await self.validator.retry_with_simple_prompt(
                world_state, self.ai_engine, f"{cycle_id}-recovery2"
            )
            
            # Parse the simple response
            decision_data = json.loads(simple_response)
            
            # Convert to the expected format
            from .ai_engine import ActionPlan
            selected_actions = []
            for action_data in decision_data.get("selected_actions", []):
                action_plan = ActionPlan(
                    action_type=action_data.get("action_type", "wait"),
                    parameters=action_data.get("parameters", {}),
                    reasoning=action_data.get("reasoning", "Recovery action"),
                    priority=action_data.get("priority", 5)
                )
                selected_actions.append(action_plan)
            
            return {
                "selected_actions": selected_actions,
                "reasoning": decision_data.get("reasoning", "Recovery with simple prompt"),
                "observations": decision_data.get("observations", "Using recovery mode")
            }
        except Exception as e:
            logger.error(f"Simple prompt retry failed: {e}")
            return None
    
    async def _fallback_to_wait_action(self, world_state: Dict, cycle_id: str) -> Dict:
        """Fallback to a simple wait action."""
        from .ai_engine import ActionPlan
        
        wait_action = ActionPlan(
            action_type="wait",
            parameters={"duration": 2.0},
            reasoning="AI recovery mode - waiting for system stabilization",
            priority=1
        )
        
        return {
            "selected_actions": [wait_action],
            "reasoning": "Entered AI recovery mode due to response failures",
            "observations": f"AI failure recovery in cycle {cycle_id}"
        }
    
    async def _enter_emergency_safe_mode(self, world_state: Dict, cycle_id: str) -> Dict:
        """Enter emergency safe mode with no actions."""
        if self.failure_count >= self.max_failures:
            logger.critical(f"AI engine in emergency safe mode after {self.failure_count} failures")
        
        return {
            "selected_actions": [],
            "reasoning": f"Emergency safe mode - AI engine requires attention (failure #{self.failure_count})",
            "observations": f"Critical AI failure in cycle {cycle_id}"
        }
    
    def _safe_default_response(self, cycle_id: str) -> Dict:
        """Provide a safe default response when all recovery fails."""
        return {
            "selected_actions": [],
            "reasoning": f"All AI recovery strategies failed for cycle {cycle_id}",
            "observations": "AI engine requires manual intervention"
        }
    
    def reset_failure_count(self):
        """Reset the failure count after successful operation."""
        if self.failure_count > 0:
            logger.info(f"Resetting AI failure count (was {self.failure_count})")
            self.failure_count = 0
