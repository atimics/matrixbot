"""
Enhanced AI Engine with Structured Outputs

Implements the engineering report recommendations for:
- Structured outputs using function calling
- Simplified prompt engineering
- Better error handling and reliability
- Integration with instructor library for type-safe outputs
"""

import json
import logging
import time
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
    
    class Config:
        json_schema_extra = {
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
        """Generate chat completion via OpenRouter."""
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


# Factory function
def create_ai_engine(
    provider: AIProvider = AIProvider.OPENROUTER,
    model: str = "openai/gpt-4o-mini",
    api_key: Optional[str] = None,
    **kwargs
) -> EnhancedAIEngine:
    """Factory function to create an AI engine."""
    config = AIEngineConfig(
        provider=provider,
        model=model,
        api_key=api_key,
        **kwargs
    )
    return EnhancedAIEngine(config)


# Migration utilities for existing code
class LegacyAIEngineAdapter:
    """Adapter to maintain compatibility with existing AI engine interface."""
    
    def __init__(self, enhanced_engine: EnhancedAIEngine):
        self.enhanced_engine = enhanced_engine
    
    async def generate_response(self, prompt: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Legacy interface for generating responses."""
        response = await self.enhanced_engine.generate_structured_response(
            prompt, context, AIResponse
        )
        
        # Convert to legacy format
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
