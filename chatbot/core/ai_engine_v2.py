"""
Unified AI Engine with Structured Outputs

This module consolidates all AI engine implementations into a single unified interface:

CURRENT STANDARD (Recommended):
- AIEngine: Main unified class supporting all interfaces
- create_ai_engine(): Factory function for creating AIEngine instances

LEGACY COMPATIBILITY (Deprecated but supported):
- AIEngineV2: Alias for AIEngine (for orchestrator compatibility)  
- AIDecisionEngine: Alias for AIEngine (for legacy code compatibility)
- LegacyAIEngineAdapter: Alias for AIEngine (deprecated)
- EnhancedAIEngine: Base implementation (use AIEngine instead)

MIGRATION GUIDE:
1. Replace all AIDecisionEngine imports with AIEngine
2. Replace all AIEngineV2 imports with AIEngine  
3. Replace create_enhanced_ai_engine() calls with create_ai_engine()
4. Update constructor calls to use the unified AIEngine interface

FEATURES:
- Structured outputs using Pydantic models
- Multiple AI provider support (OpenRouter, OpenAI, Anthropic)
- Backward compatibility with all legacy interfaces
- Enhanced error handling and retry logic
- Tool calling and function execution support
- Conversation history management
"""

import json
import logging
import time
import asyncio
from typing import Any, Dict, List, Optional, Type, Union, Callable
from dataclasses import dataclass
from enum import Enum
from abc import ABC, abstractmethod

import httpx
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)


class AIProvider(Enum):
    """Supported AI providers."""
    OPENROUTER = "openrouter"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"


class ToolCall(BaseModel):
    """Structured representation of a tool call."""
    name: str = Field(description="Name of the tool to call")
    parameters: Dict[str, Any] = Field(description="Parameters for the tool call")
    reasoning: Optional[str] = Field(None, description="Reasoning for this tool call")


class AIResponse(BaseModel):
    """Structured AI response with tools and reasoning."""
    reasoning: str = Field(description="AI's reasoning for the response")
    tool_calls: List[ToolCall] = Field(default_factory=list, description="Tools to execute")
    message: Optional[str] = Field(None, description="Message to send if no tools needed")
    confidence: float = Field(default=0.8, description="Confidence in the response (0-1)")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "reasoning": "User asked about weather, I should search for current weather information",
                "tool_calls": [
                    {
                        "name": "web_search",
                        "parameters": {"query": "current weather San Francisco"},
                        "reasoning": "Need current weather data"
                    }
                ],
                "confidence": 0.9
            }
        }
    }


class ObservationResponse(BaseModel):
    """Response for observation-only cycles."""
    observations: List[str] = Field(description="Key observations about current state")
    should_act: bool = Field(description="Whether action is needed")
    priority: str = Field(description="Priority level: low, medium, high")
    reasoning: str = Field(description="Reasoning for the assessment")


class ErrorAnalysis(BaseModel):
    """Analysis of errors and recovery suggestions."""
    error_type: str = Field(description="Type of error encountered")
    severity: str = Field(description="Error severity: low, medium, high, critical") 
    recovery_suggestion: str = Field(description="Suggested recovery action")
    retry_recommended: bool = Field(description="Whether retry is recommended")


@dataclass
class ActionPlan:
    """Represents a planned action for legacy compatibility."""
    action_type: str
    parameters: Dict[str, Any]
    reasoning: str
    priority: int  # 1-10, higher is more important


@dataclass
class DecisionResult:
    """Result of AI decision making for legacy compatibility."""
    selected_actions: List[ActionPlan]
    reasoning: str
    observations: str
    thought: str  # AI's step-by-step thinking process
    cycle_id: str


@dataclass
class AIEngineConfig:
    """Configuration for the AI engine."""
    provider: AIProvider = AIProvider.OPENROUTER
    model: str = "openai/gpt-4o-mini"
    multimodal_model: str = "openai/gpt-4o"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    timeout: float = 30.0
    max_retries: int = 3
    use_structured_outputs: bool = True
    fallback_to_text_parsing: bool = True


class AIProvider_Base(ABC):
    """Abstract base class for AI providers."""
    
    @abstractmethod
    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        response_format: Optional[Type[BaseModel]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Generate chat completion."""
        pass
    
    @abstractmethod
    def supports_structured_outputs(self) -> bool:
        """Check if provider supports structured outputs."""
        pass


class OpenRouterProvider(AIProvider_Base):
    """OpenRouter AI provider implementation."""
    
    def __init__(self, config: AIEngineConfig):
        self.config = config
        self.base_url = "https://openrouter.ai/api/v1"
        self.client = httpx.AsyncClient(timeout=config.timeout)
    
    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        response_format: Optional[Type[BaseModel]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Generate chat completion via OpenRouter with retry logic."""
        max_retries = 3
        base_delay = 1.0
        
        for attempt in range(max_retries + 1):
            try:
                return await self._make_request(messages, response_format, tools, **kwargs)
            except ValueError as e:
                # Don't retry for authentication or client errors
                if "Authentication failed" in str(e) or "Access forbidden" in str(e):
                    raise e
                
                # Retry for rate limits and server errors
                if attempt < max_retries and ("Rate limit" in str(e) or "Server error" in str(e)):
                    delay = base_delay * (2 ** attempt)  # Exponential backoff
                    logger.warning(f"Retrying in {delay}s after error: {e}")
                    await asyncio.sleep(delay)
                    continue
                
                # Re-raise on final attempt
                raise e
            except Exception as e:
                logger.error(f"Unexpected error in chat completion: {e}")
                if attempt < max_retries:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(f"Retrying in {delay}s after unexpected error")
                    await asyncio.sleep(delay)
                    continue
                raise ValueError(f"Chat completion failed after {max_retries} retries: {e}")
    
    async def _make_request(
        self,
        messages: List[Dict[str, Any]],
        response_format: Optional[Type[BaseModel]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Make the actual HTTP request to OpenRouter."""
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/ratichat/matrixbot",
            "X-Title": "RatiChat Matrix Bot"
        }
        
        payload = {
            "model": kwargs.get("model", self.config.model),
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 2000)
        }
        
        # Add structured output support if available
        if response_format and self.supports_structured_outputs():
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": response_format.__name__,
                    "schema": response_format.model_json_schema()
                }
            }
        
        # Add function calling support
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        
        response = await self.client.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=payload
        )
        
        # Enhanced error handling for better debugging and resilience
        if response.status_code == 401:
            logger.error("OpenRouter API authentication failed. Please check your API key.")
            raise ValueError(
                "Authentication failed: Invalid or missing OpenRouter API key. "
                "Please check your OPENROUTER_API_KEY environment variable."
            )
        elif response.status_code == 403:
            logger.error("OpenRouter API access forbidden. Check your API key permissions.")
            raise ValueError(
                "Access forbidden: Your API key may not have permission for this model or feature."
            )
        elif response.status_code == 429:
            logger.warning("Rate limit exceeded. Implementing exponential backoff.")
            raise ValueError(
                "Rate limit exceeded. Please wait before making more requests."
            )
        elif response.status_code >= 500:
            logger.error(f"OpenRouter server error: {response.status_code}")
            raise ValueError(
                f"Server error: OpenRouter is experiencing issues (HTTP {response.status_code}). "
                "This is typically temporary, please try again later."
            )
        
        response.raise_for_status()
        return response.json()
    
    def supports_structured_outputs(self) -> bool:
        """OpenRouter supports structured outputs for compatible models."""
        compatible_models = ["openai/gpt-4o", "openai/gpt-4o-mini", "anthropic/claude-3"]
        return any(model in self.config.model for model in compatible_models)


class EnhancedAIEngine:
    """Enhanced AI engine with structured outputs and better error handling."""
    
    def __init__(self, config: AIEngineConfig):
        self.config = config
        self.provider = self._create_provider()
        self.tool_schemas = {}
        self.conversation_history = []
        
    def _create_provider(self) -> AIProvider_Base:
        """Create AI provider based on configuration."""
        if self.config.provider == AIProvider.OPENROUTER:
            return OpenRouterProvider(self.config)
        else:
            raise ValueError(f"Unsupported provider: {self.config.provider}")
    
    def register_tool_schema(self, tool_name: str, schema: Dict[str, Any]):
        """Register a tool schema for function calling."""
        self.tool_schemas[tool_name] = {
            "type": "function",
            "function": {
                "name": tool_name,
                "description": schema.get("description", ""),
                "parameters": schema.get("parameters", {})
            }
        }
    
    def register_tool_from_class(self, tool_class):
        """Register tool schema from a tool class."""
        if hasattr(tool_class, 'get_schema'):
            schema = tool_class.get_schema()
            self.register_tool_schema(tool_class.__name__, schema)
    
    async def generate_structured_response(
        self,
        prompt: str,
        context: Dict[str, Any],
        response_type: Type[BaseModel] = AIResponse,
        available_tools: Optional[List[str]] = None
    ) -> BaseModel:
        """Generate a structured response using the specified model."""
        
        # Build messages
        messages = self._build_messages(prompt, context)
        
        # Get tool schemas if needed
        tools = None
        if available_tools:
            tools = [self.tool_schemas[tool] for tool in available_tools 
                    if tool in self.tool_schemas]
        
        try:
            # Try structured output first
            if self.config.use_structured_outputs and self.provider.supports_structured_outputs():
                return await self._generate_with_structured_output(
                    messages, response_type, tools
                )
            else:
                # Fall back to text parsing
                return await self._generate_with_text_parsing(
                    messages, response_type, tools
                )
        
        except Exception as e:
            logger.error(f"AI generation failed: {e}")
            
            # Return error response
            if response_type == AIResponse:
                return AIResponse(
                    reasoning=f"Error occurred: {str(e)}",
                    tool_calls=[],
                    message="I encountered an error processing your request.",
                    confidence=0.1
                )
            else:
                # Create minimal valid response for other types
                return response_type()
    
    async def _generate_with_structured_output(
        self,
        messages: List[Dict[str, Any]],
        response_type: Type[BaseModel],
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> BaseModel:
        """Generate response using native structured output support."""
        
        try:
            response = await self.provider.chat_completion(
                messages=messages,
                response_format=response_type,
                tools=tools
            )
            
            # Parse structured response
            content = response["choices"][0]["message"]["content"]
            return response_type.model_validate_json(content)
        
        except (ValidationError, KeyError, json.JSONDecodeError) as e:
            logger.warning(f"Structured output parsing failed: {e}")
            if self.config.fallback_to_text_parsing:
                return await self._generate_with_text_parsing(messages, response_type, tools)
            else:
                raise
    
    async def _generate_with_text_parsing(
        self,
        messages: List[Dict[str, Any]],
        response_type: Type[BaseModel],
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> BaseModel:
        """Generate response and parse from text output."""
        
        # Add instructions for JSON output
        system_msg = self._get_system_message_for_parsing(response_type)
        messages_with_instructions = [system_msg] + messages
        
        response = await self.provider.chat_completion(
            messages=messages_with_instructions,
            tools=tools
        )
        
        # Extract and parse JSON
        content = response["choices"][0]["message"]["content"]
        json_content = self._extract_json_from_text(content)
        
        return response_type.model_validate(json_content)
    
    def _build_messages(self, prompt: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Build message list for AI completion."""
        messages = []
        
        # System message with context
        system_content = self._build_system_message(context)
        messages.append({"role": "system", "content": system_content})
        
        # Add conversation history (last few messages)
        messages.extend(self.conversation_history[-5:])  # Keep last 5 messages
        
        # Current prompt
        messages.append({"role": "user", "content": prompt})
        
        return messages
    
    def _build_system_message(self, context: Dict[str, Any]) -> str:
        """Build comprehensive system message."""
        base_prompt = """You are RatiChat, an advanced AI assistant for a multi-platform chatbot system.

Core Capabilities:
- Intelligent conversation across Matrix and Farcaster
- Tool-based action execution
- Context-aware decision making
- Multi-platform awareness

Your responses should be:
- Thoughtful and contextually appropriate
- Action-oriented when needed
- Efficient with token usage
- Professional yet engaging"""
        
        # Add context information
        if context.get("current_channel_id"):
            base_prompt += f"\n\nCurrent channel: {context['current_channel_id']}"
        
        if context.get("recent_messages"):
            message_count = len(context["recent_messages"])
            base_prompt += f"\n\nRecent activity: {message_count} recent messages"
        
        if context.get("available_tools"):
            tools_list = ", ".join(context["available_tools"])
            base_prompt += f"\n\nAvailable tools: {tools_list}"
        
        return base_prompt
    
    def _get_system_message_for_parsing(self, response_type: Type[BaseModel]) -> Dict[str, str]:
        """Get system message that instructs JSON output format."""
        schema = response_type.model_json_schema()
        return {
            "role": "system",
            "content": f"""You must respond with valid JSON that matches this exact schema:

{json.dumps(schema, indent=2)}

Your response must be parseable JSON. Do not include any text outside the JSON structure."""
        }
    
    def _extract_json_from_text(self, text: str) -> Dict[str, Any]:
        """Extract JSON from text response."""
        # Remove code blocks
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        
        # Find JSON boundaries
        start_idx = text.find("{")
        end_idx = text.rfind("}") + 1
        
        if start_idx != -1 and end_idx > start_idx:
            json_text = text[start_idx:end_idx]
            try:
                return json.loads(json_text)
            except json.JSONDecodeError:
                pass
        
        # If no valid JSON found, try to parse the whole text
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to extract JSON from response: {e}")
            logger.debug(f"Response text: {text}")
            raise ValueError(f"Could not extract valid JSON from AI response: {e}")
    
    async def analyze_error(self, error: Exception, context: str) -> ErrorAnalysis:
        """Analyze an error and provide recovery suggestions."""
        error_prompt = f"""
Analyze this error and provide recovery guidance:

Error: {str(error)}
Error Type: {type(error).__name__}
Context: {context}

Provide analysis and recovery suggestions.
"""
        
        try:
            return await self.generate_structured_response(
                error_prompt,
                {"error": str(error), "context": context},
                ErrorAnalysis
            )
        except Exception as e:
            logger.error(f"Error analysis failed: {e}")
            return ErrorAnalysis(
                error_type=type(error).__name__,
                severity="medium",
                recovery_suggestion="Manual intervention required",
                retry_recommended=False
            )
    
    async def observation_cycle(self, world_state: Dict[str, Any]) -> ObservationResponse:
        """Perform an observation cycle to assess if action is needed."""
        prompt = """
Analyze the current world state and determine:
1. Key observations about current activity
2. Whether any action is needed
3. Priority level of any required actions
4. Your reasoning

Focus on:
- New messages that might need responses
- System status that might need attention
- Opportunities for proactive engagement
"""
        
        return await self.generate_structured_response(
            prompt,
            world_state,
            ObservationResponse
        )
    
    def update_conversation_history(self, role: str, content: str):
        """Update conversation history."""
        self.conversation_history.append({
            "role": role,
            "content": content,
            "timestamp": time.time()
        })
        
        # Keep history manageable
        if len(self.conversation_history) > 20:
            self.conversation_history = self.conversation_history[-15:]
    
    async def cleanup(self):
        """Cleanup resources."""
        if hasattr(self.provider, 'client'):
            await self.provider.client.aclose()


# Factory functions
def create_ai_engine(
    provider: AIProvider = AIProvider.OPENROUTER,
    model: str = "openai/gpt-4o-mini",
    api_key: Optional[str] = None,
    **kwargs
) -> "AIEngine":
    """
    Factory function to create the unified AI engine.
    
    Returns:
        AIEngine: Unified AI engine with all interfaces
    """
    return AIEngine(
        api_key=api_key,
        model=model,
        **kwargs
    )


def create_enhanced_ai_engine(*args, **kwargs) -> "AIEngine":
    """
    DEPRECATED: Use create_ai_engine() instead.
    
    This function is maintained for backward compatibility.
    """
    import warnings
    warnings.warn(
        "create_enhanced_ai_engine() is deprecated. Use create_ai_engine() instead.",
        DeprecationWarning,
        stacklevel=2
    )
    return create_ai_engine(*args, **kwargs)


# Unified AI Engine Interface
class AIEngine(EnhancedAIEngine):
    """
    Unified AI Engine that consolidates all previous implementations.
    
    This class provides both the new structured interface and legacy compatibility.
    It replaces AIDecisionEngine, AIEngineV2, and EnhancedAIEngine.
    """
    
    def __init__(self, api_key: str, model: str = "openai/gpt-4o-mini", 
                 temperature: float = 0.7, max_tokens: int = 4000, 
                 timeout: float = 30.0, optimization_level: str = "balanced",
                 **kwargs):
        """
        Initialize the unified AI engine.
        
        Args:
            api_key: OpenRouter API key
            model: AI model to use
            temperature: Sampling temperature (0.0-2.0)
            max_tokens: Max tokens in response
            timeout: Request timeout in seconds
            optimization_level: Optimization level (for legacy compatibility)
            **kwargs: Additional configuration options
        """
        config = AIEngineConfig(
            provider=AIProvider.OPENROUTER,
            model=model,
            api_key=api_key,
            timeout=timeout,
            **kwargs
        )
        super().__init__(config)
        
        # Store parameters for legacy compatibility
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.optimization_level = optimization_level
        
        # Legacy compatibility attributes
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        self.max_actions_per_cycle = 3
        
        logger.info(f"Initialized unified AIEngine with model {model}")
    
    async def decide_actions(self, world_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Legacy interface for AI decision making.
        
        This method maintains compatibility with existing code that expects
        the old AIDecisionEngine interface.
        """
        try:
            # Convert world_state to prompt and context
            prompt = self._build_decision_prompt(world_state)
            context = self._extract_context_from_world_state(world_state)
            
            # Generate structured response
            response = await self.generate_structured_response(
                prompt, context, AIResponse
            )
            
            # Convert to legacy format
            return {
                "observations": response.reasoning,
                "selected_actions": [
                    {
                        "action_type": call.name,
                        "parameters": call.parameters,
                        "reasoning": call.reasoning or response.reasoning,
                        "priority": 5  # Default priority
                    }
                    for call in response.tool_calls
                ],
                "reasoning": response.reasoning,
                "thought": response.reasoning,
                "cycle_id": context.get("cycle_id", "unknown")
            }
        except Exception as e:
            logger.error(f"Decision making failed: {e}")
            return {
                "observations": f"Error: {str(e)}",
                "selected_actions": [],
                "reasoning": "An error occurred during decision making",
                "thought": "Error in AI processing",
                "cycle_id": "error"
            }
    
    def _build_decision_prompt(self, world_state: Dict[str, Any]) -> str:
        """Build decision prompt from world state."""
        prompt = """Analyze the current situation and decide what actions to take.

Consider:
- Current messages and conversations
- System status and health
- Opportunities for engagement
- Available tools and capabilities

Provide your reasoning and any necessary actions."""
        
        # Add context from world state
        if world_state.get("recent_messages"):
            message_count = len(world_state["recent_messages"])
            prompt += f"\n\nRecent activity: {message_count} messages"
        
        if world_state.get("current_channel"):
            prompt += f"\nCurrent channel: {world_state['current_channel']}"
        
        return prompt
    
    def _extract_context_from_world_state(self, world_state: Dict[str, Any]) -> Dict[str, Any]:
        """Extract relevant context from world state."""
        context = {}
        
        # Copy relevant fields
        if "recent_messages" in world_state:
            context["recent_messages"] = world_state["recent_messages"]
        if "current_channel" in world_state:
            context["current_channel_id"] = world_state["current_channel"]
        if "available_tools" in world_state:
            context["available_tools"] = world_state["available_tools"]
        if "cycle_id" in world_state:
            context["cycle_id"] = world_state["cycle_id"]
        
        return context
    
    async def generate_response(self, prompt: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Legacy interface for generating responses.
        
        Maintains compatibility with older code that expects this method.
        """
        response = await self.generate_structured_response(
            prompt, context, AIResponse
        )
        
        return {
            "reasoning": response.reasoning,
            "actions": [
                {
                    "tool": call.name,
                    "parameters": call.parameters
                }
                for call in response.tool_calls
            ],
            "message": response.message,
            "confidence": response.confidence
        }
    
    async def make_decision(self, world_state: Dict[str, Any], cycle_id: str) -> DecisionResult:
        """
        Make a decision based on current world state.
        
        This method provides legacy compatibility with the node processor and other
        components that expect the make_decision interface.
        
        Args:
            world_state: Current state of the world
            cycle_id: Unique identifier for this decision cycle
            
        Returns:
            DecisionResult containing selected actions and reasoning
        """
        try:
            logger.info(f"AIEngine: Starting decision cycle {cycle_id}")
            
            # Call the decide_actions method to get the decision data
            decision_data = await self.decide_actions(world_state)
            
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
                    logger.warning(f"Skipping malformed action: {e}")
                    continue
            
            # Limit to max actions per cycle
            if len(selected_actions) > self.max_actions_per_cycle:
                logger.warning(
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
                logger.info(f"AI Thought Process (Cycle {cycle_id}): {result.thought}")
            
            logger.info(
                f"AIEngine: Cycle {cycle_id} complete - "
                f"selected {len(result.selected_actions)} actions"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error in make_decision for cycle {cycle_id}: {e}")
            return DecisionResult(
                selected_actions=[],
                reasoning=f"Error: {str(e)}",
                observations="Error during decision making",
                thought="",
                cycle_id=cycle_id,
            )


# Aliases for backward compatibility
AIEngineV2 = AIEngine  # For orchestrator compatibility
AIDecisionEngine = AIEngine  # For legacy code compatibility
LegacyAIEngineAdapter = AIEngine  # Deprecated - use AIEngine directly


# Testing utilities
class MockAIProvider(AIProvider_Base):
    """Mock AI provider for testing."""
    
    def __init__(self, responses: List[str]):
        self.responses = responses
        self.call_count = 0
    
    async def chat_completion(self, messages, response_format=None, tools=None, **kwargs):
        response = self.responses[self.call_count % len(self.responses)]
        self.call_count += 1
        
        return {
            "choices": [
                {
                    "message": {
                        "content": response
                    }
                }
            ]
        }
    
    def supports_structured_outputs(self) -> bool:
        return False


def create_mock_ai_engine(responses: List[str]) -> "AIEngine":
    """Create a mock AI engine for testing."""
    engine = AIEngine(api_key="mock_key", model="mock_model")
    engine.provider = MockAIProvider(responses)
    return engine


# Module exports for clean imports
__all__ = [
    # Main classes (recommended)
    'AIEngine',
    'AIEngineConfig', 
    'AIProvider',
    'AIResponse',
    'ToolCall',
    'ObservationResponse',
    'ErrorAnalysis',
    
    # Factory functions
    'create_ai_engine',
    
    # Legacy aliases (deprecated)
    'AIEngineV2',
    'AIDecisionEngine', 
    'LegacyAIEngineAdapter',
    'EnhancedAIEngine',
    'create_enhanced_ai_engine',
    
    # Testing utilities
    'MockAIProvider',
    'create_mock_ai_engine',
]
