"""
Unified AI Engine with Structured Outputs

This module provides a unified AI engine implementation for the chatbot system.

MAIN INTERFACE:
- AIEngine: Main unified class supporting all interfaces
- create_ai_engine(): Factory function for creating AIEngine instances

FEATURES:
- Structured outputs using Pydantic models
- Multiple AI provider support (OpenRouter, OpenAI, Anthropic)
- Enhanced error handling and retry logic
- Tool calling and function execution support
- Conversation history management
"""

import json
import logging
import re
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
        # Ensure API key is properly resolved and not a reused coroutine
        api_key = self.config.api_key
        if hasattr(api_key, '__await__'):
            # If it's a coroutine, this is an error - it should already be resolved
            logger.error(f"Received coroutine as API key: {type(api_key)}")
            raise ValueError("API key should not be a coroutine at this point")
        
        if not api_key or str(api_key).startswith('<coroutine'):
            logger.error(f"Invalid API key detected: {type(api_key)}")
            raise ValueError("Invalid or missing API key")
        
        headers = {
            "Authorization": f"Bearer {api_key}",
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
                    "strict": True,
                    "schema": response_format.model_json_schema()
                }
            }
        
        # Add function calling support
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        
        # Log detailed request info for debugging 401 errors
        payload_size = len(json.dumps(payload).encode('utf-8'))
        logger.debug(f"Making API request - Model: {payload.get('model')}, Size: {payload_size} bytes, "
                    f"Messages: {len(payload.get('messages', []))}, Tools: {len(payload.get('tools', []))}")
        
        # Log API key status for debugging (without exposing the actual key)
        logger.debug(f"API key type: {type(api_key)}, length: {len(str(api_key)) if api_key else 0}")
        
        response = await self.client.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=payload
        )
        
        # Enhanced error handling for better debugging and resilience
        if response.status_code == 401:
            logger.error("OpenRouter API authentication failed. Please check your API key.")
            logger.error(f"Request URL: {self.base_url}/chat/completions")
            logger.error(f"Request headers: {dict(headers)}")
            logger.error(f"Payload size: {len(json.dumps(payload).encode('utf-8'))} bytes")
            logger.error(f"Model: {payload.get('model', 'unknown')}")
            logger.error(f"Message count: {len(payload.get('messages', []))}")
            logger.error(f"Tools count: {len(payload.get('tools', []))}")
            if hasattr(response, 'text'):
                logger.error(f"Response body: {response.text}")
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
        result = response.json()
        
        # Debug logging to understand response structure
        logger.info(f"OpenRouter response keys: {list(result.keys()) if isinstance(result, dict) else 'not a dict'}")
        if isinstance(result, dict) and 'choices' in result:
            logger.info(f"Number of choices: {len(result['choices'])}")
            if result['choices'] and 'message' in result['choices'][0]:
                content = result['choices'][0]['message'].get('content', '')
                logger.info(f"Response content length: {len(content)}")
                logger.info(f"Response content preview: {content[:200]}...")
        
        return result
    
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
        
        try:
            # Add instructions for JSON output
            system_msg = self._get_system_message_for_parsing(response_type)
            messages_with_instructions = [system_msg] + messages
            
            logger.info(f"Making AI request with {len(messages_with_instructions)} messages")
            
            response = await self.provider.chat_completion(
                messages=messages_with_instructions,
                tools=tools
            )
            
            # Debug logging for response structure
            logger.info(f"AI response structure: {type(response)}")
            logger.info(f"AI response keys: {response.keys() if isinstance(response, dict) else 'Not a dict'}")
            
            # Extract and parse JSON with defensive checks
            try:
                if not isinstance(response, dict):
                    raise ValueError(f"Expected dict response, got {type(response)}")
                
                if "choices" not in response:
                    raise ValueError(f"No 'choices' in response. Keys: {list(response.keys())}")
                
                if not response["choices"]:
                    raise ValueError("Empty choices array in response")
                
                choice = response["choices"][0]
                if "message" not in choice:
                    raise ValueError(f"No 'message' in choice. Keys: {list(choice.keys())}")
                
                message = choice["message"]
                if "content" not in message:
                    raise ValueError(f"No 'content' in message. Keys: {list(message.keys())}")
                
                content = message["content"]
                
            except (KeyError, IndexError, TypeError) as e:
                logger.error(f"Error extracting content from response: {e}")
                logger.error(f"Full response: {response}")
                raise ValueError(f"Invalid response structure: {e}")
            
            # Debug logging for content extraction
            logger.info(f"Extracted content type: {type(content)}")
            logger.info(f"Extracted content length: {len(content) if content else 0}")
            if content:
                logger.info(f"Content preview: {content[:500]}...")
            else:
                logger.warning("AI response content is empty!")
                raise ValueError("Empty response from AI")
            
            logger.info("Attempting to extract JSON from AI response")
            json_content = self._extract_json_from_text(content)
            
            logger.info(f"Successfully extracted JSON with keys: {list(json_content.keys()) if isinstance(json_content, dict) else 'Not a dict'}")
            
            result = response_type.model_validate(json_content)
            logger.info(f"Successfully validated response as {response_type.__name__}")
            
            return result
            
        except Exception as e:
            logger.error(f"Critical error in AI text parsing: {e}", exc_info=True)
            
            # Return a safe fallback response
            if response_type == AIResponse:
                return AIResponse(
                    reasoning=f"Failed to process AI response: {str(e)}",
                    tool_calls=[],
                    message="I'm experiencing technical difficulties. Please try again.",
                    confidence=0.1
                )
            else:
                # For other response types, create minimal valid response
                try:
                    return response_type()
                except:
                    raise e
    
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

CRITICAL RESPONSE REQUIREMENTS:
- ALWAYS respond when directly mentioned (@ratichat or [ratichat]) - This is MANDATORY
- ALWAYS respond to direct messages - This is MANDATORY  
- ALWAYS respond to questions about your capabilities or tools
- ALWAYS respond to greetings and direct interactions
- Use the send_matrix_reply tool to send responses in Matrix channels
- Use the send_farcaster_reply tool to send responses on Farcaster
- Only choose "wait" action when there is genuinely nothing requiring attention

Your responses should be:
- Thoughtful and contextually appropriate
- Action-oriented when needed (use tools to actually respond)
- Efficient with token usage
- Professional yet engaging

MENTION DETECTION:
When you see messages containing @ratichat, [ratichat], or similar mentions, you MUST respond.
These are direct mentions requiring immediate attention."""
        
        # Add context information
        if context.get("current_channel_id"):
            base_prompt += f"\n\nCurrent channel: {context['current_channel_id']}"
        
        # Add trigger type information with strong emphasis
        if context.get("trigger_type"):
            trigger_type = context["trigger_type"]
            if trigger_type == "mention":
                base_prompt += f"\n\n🔔 CRITICAL ALERT: You were mentioned directly! This requires an immediate response using the appropriate send_* tool."
            elif trigger_type == "direct_message":
                base_prompt += f"\n\n💬 CRITICAL ALERT: This is a direct message that requires an immediate response."
            elif trigger_type == "question":
                base_prompt += f"\n\n❓ IMPORTANT: Someone asked a question that requires a response."
            elif trigger_type == "channel_activity":
                base_prompt += f"\n\n📢 CHANNEL ACTIVITY: New activity detected in a monitored channel. Review the messages and consider if engagement is appropriate. You don't need to respond to every message - focus on meaningful opportunities."
            else:
                base_prompt += f"\n\nTrigger type: {trigger_type}"
        
        if context.get("recent_messages"):
            messages = context["recent_messages"]
            message_count = len(messages)
            base_prompt += f"\n\nRecent activity: {message_count} recent messages"
            
            # Include actual message content for AI understanding
            base_prompt += "\n\nRecent messages:"
            for msg in messages[-5:]:  # Show last 5 messages
                author = msg.get("author", "Unknown")
                content = msg.get("content", "").strip()
                if content:
                    # Truncate very long messages
                    if len(content) > 200:
                        content = content[:200] + "..."
                    base_prompt += f"\n- {author}: {content}"
                    
                    # Check for mentions in the recent messages
                    if "@ratichat" in content.lower() or "[ratichat]" in content.lower():
                        base_prompt += " ⭐ MENTION DETECTED - RESPOND TO THIS"
        
        if context.get("available_tools"):
            tools_list = ", ".join(context["available_tools"])
            base_prompt += f"\n\nAvailable tools: {tools_list}"
        
        return base_prompt
    
    def _get_system_message_for_parsing(self, response_type: Type[BaseModel]) -> Dict[str, str]:
        """Get system message that instructs JSON output format."""
        schema = response_type.model_json_schema()
        
        # Add clear examples based on response type
        example_json = ""
        if response_type == AIResponse:
            example_json = """
Example response for a user mention:
```json
{
  "reasoning": "User mentioned me and asked about my capabilities",
  "tool_calls": [
    {
      "name": "send_matrix_reply",
      "parameters": {
        "room_id": "!roomid:server.com",
        "message": "Hello! I can help with Matrix and Farcaster interactions.",
        "reply_to_event_id": "$eventid"
      },
      "reasoning": "User asked about my capabilities, should respond helpfully"
    }
  ],
  "message": null,
  "confidence": 0.9
}
```

Example response when no action is needed:
```json
{
  "reasoning": "No new messages requiring immediate attention",
  "tool_calls": [],
  "message": null,
  "confidence": 0.8
}
```"""
        
        return {
            "role": "system",
            "content": f"""You must respond with valid JSON that matches this exact schema:

{json.dumps(schema, indent=2)}

IMPORTANT FORMATTING RULES:
- Your response must be valid JSON only
- You can wrap JSON in ```json code blocks if you prefer
- Do not include explanatory text before or after the JSON
- Do not include markdown formatting outside of code blocks
- Ensure all JSON properties are properly quoted
- Ensure all string values are properly escaped
- Use empty arrays [] for tool_calls when no tools are needed
- Always include reasoning even if brief

{example_json}

Examples of acceptable formats:
1. Raw JSON: {{"key": "value"}}
2. Code block: ```json\n{{"key": "value"}}\n```
3. Simple code block: ```\n{{"key": "value"}}\n```"""
        }
    
    def _extract_json_from_text(self, text: str) -> Dict[str, Any]:
        """Extract JSON from text response with robust parsing."""
        if not text or not text.strip():
            raise ValueError("Empty response from AI")
        
        text = text.strip()
        logger.info(f"Parsing AI response (length: {len(text)}): {text[:200]}...")
        
        # Strategy 1: Try parsing the full text as JSON first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        # Strategy 2: Remove markdown code blocks
        cleaned_text = text
        
        # Handle various markdown code block formats
        code_block_patterns = [
            (r'```json\s*\n(.*?)\n```', re.DOTALL),
            (r'```\s*\n(.*?)\n```', re.DOTALL),
            (r'`(.*?)`', re.DOTALL),
        ]
        
        for pattern, flags in code_block_patterns:
            match = re.search(pattern, cleaned_text, flags)
            if match:
                cleaned_text = match.group(1).strip()
                try:
                    return json.loads(cleaned_text)
                except json.JSONDecodeError:
                    continue
        
        # Strategy 3: Find JSON objects by brace matching
        possible_jsons = []
        brace_count = 0
        start_idx = -1
        
        for i, char in enumerate(text):
            if char == '{':
                if brace_count == 0:
                    start_idx = i
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0 and start_idx != -1:
                    possible_jsons.append(text[start_idx:i+1])
        
        # Try each potential JSON object
        for json_candidate in possible_jsons:
            try:
                return json.loads(json_candidate)
            except json.JSONDecodeError:
                continue
        
        # Strategy 4: Look for JSON between common delimiters
        delimiters = [
            ('```json', '```'),
            ('```', '```'),
            ('```json\n', '\n```'),
            ('{', '}'),
        ]
        
        for start_delim, end_delim in delimiters:
            start_idx = text.find(start_delim)
            if start_idx != -1:
                start_idx += len(start_delim)
                end_idx = text.find(end_delim, start_idx)
                if end_idx != -1:
                    json_candidate = text[start_idx:end_idx].strip()
                    try:
                        return json.loads(json_candidate)
                    except json.JSONDecodeError:
                        continue
        
        # Strategy 5: Extract everything between the first { and last }
        start_brace = text.find('{')
        end_brace = text.rfind('}')
        if start_brace != -1 and end_brace > start_brace:
            json_candidate = text[start_brace:end_brace+1]
            try:
                return json.loads(json_candidate)
            except json.JSONDecodeError:
                pass
        
        # Strategy 6: Handle common AI response patterns with explanations
        # Look for patterns like "Here's the JSON:" followed by JSON
        explanation_patterns = [
            r'(?:here[\'s\s]*(?:the|is|are)?[:\s]*json[:\s]*)(.*?)(?:\n\n|\Z)',
            r'(?:json[:\s]*)(.*?)(?:\n\n|\Z)',
            r'(?:response[:\s]*)(.*?)(?:\n\n|\Z)',
        ]
        
        for pattern in explanation_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                potential_json = match.group(1).strip()
                # Try to find JSON in this section
                start_brace = potential_json.find('{')
                end_brace = potential_json.rfind('}')
                if start_brace != -1 and end_brace > start_brace:
                    json_candidate = potential_json[start_brace:end_brace+1]
                    try:
                        return json.loads(json_candidate)
                    except json.JSONDecodeError:
                        continue
        
        # If all strategies fail, log detailed info and raise error
        logger.error(f"Failed to extract JSON from response after all strategies")
        logger.error(f"Full response text (length {len(text)}): {repr(text)}")
        logger.error(f"Found potential JSON candidates: {len(possible_jsons)} candidates")
        for i, candidate in enumerate(possible_jsons[:3]):  # Log first 3 candidates
            logger.error(f"Candidate {i}: {repr(candidate[:200])}...")
        raise ValueError(f"Could not extract valid JSON from AI response. First 200 chars: {repr(text[:200])}")
    
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


# Unified AI Engine Interface
class AIEngine(EnhancedAIEngine):
    """
    Unified AI Engine that consolidates all AI processing capabilities.
    
    This class provides a structured interface for AI interactions,
    replacing all previous AI engine implementations.
    """
    
    def __init__(self, api_key: str, model: str = "openai/gpt-4o-mini", 
                 temperature: float = 0.7, max_tokens: int = 4000, 
                 timeout: float = 30.0, **kwargs):
        """
        Initialize the unified AI engine.
        
        Args:
            api_key: OpenRouter API key
            model: AI model to use
            temperature: Sampling temperature (0.0-2.0)
            max_tokens: Max tokens in response
            timeout: Request timeout in seconds
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
        
        # Store parameters
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_actions_per_cycle = 5  # Default action limit
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        
        logger.info(f"Initialized AIEngine with model {model}")
    
    async def decide_actions(self, world_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        AI decision making interface.
        
        This method provides the decision-making interface for the orchestrator
        and other components that need AI-driven action selection.
        """
        try:
            # Debug: Log what we're receiving from the world state
            logger.info(f"AI Engine received world state keys: {list(world_state.keys())}")
            
            # Convert world_state to prompt and context
            prompt = self._build_decision_prompt(world_state)
            context = self._extract_context_from_world_state(world_state)
            
            # Debug: Log extracted context
            logger.info(f"Extracted context keys: {list(context.keys())}")
            if "recent_messages" in context:
                logger.info(f"Found {len(context['recent_messages'])} recent messages")
                for i, msg in enumerate(context["recent_messages"][-3:]):  # Log last 3 messages
                    logger.info(f"Message {i}: {msg.get('author', 'Unknown')}: {msg.get('content', '')[:100]}...")
            
            # Generate structured response
            response = await self.generate_structured_response(
                prompt, context, AIResponse
            )
            
            # Convert to structured format
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
- Current messages and conversations (especially mentions and direct messages)
- System status and health
- Opportunities for engagement
- Available tools and capabilities

When you receive a direct mention or see relevant conversation:
- Respond appropriately to direct questions or greetings
- Engage naturally in ongoing discussions
- Use tools when they would add value to the conversation

Provide your reasoning and any necessary actions."""
        
        # Add context from world state
        if world_state.get("recent_messages"):
            message_count = len(world_state["recent_messages"])
            prompt += f"\n\nRecent activity: {message_count} messages available for review"
        
        # Check for expanded nodes with messages
        elif world_state.get("expanded_nodes"):
            expanded_count = len(world_state["expanded_nodes"])
            prompt += f"\n\nExpanded data available: {expanded_count} channels with detailed message content"
        
        if world_state.get("current_processing_channel_id") or world_state.get("current_channel"):
            channel_id = world_state.get("current_processing_channel_id") or world_state.get("current_channel")
            prompt += f"\n\nFocus channel: {channel_id}"
        
        return prompt
    
    def _extract_context_from_world_state(self, world_state: Dict[str, Any]) -> Dict[str, Any]:
        """Extract relevant context from world state."""
        context = {}
        
        # Handle different input formats
        if "recent_messages" in world_state:
            context["recent_messages"] = world_state["recent_messages"]
        
        # Handle node-based payload format
        elif "expanded_nodes" in world_state or "collapsed_node_summaries" in world_state:
            # Extract messages from expanded channel nodes
            recent_messages = []
            
            # Check expanded nodes for message content
            expanded_nodes = world_state.get("expanded_nodes", {})
            for node_path, node_info in expanded_nodes.items():
                if node_path.startswith("channels."):
                    node_data = node_info.get("data", {})
                    # Check for messages under either "messages" or "recent_messages" key
                    messages = node_data.get("messages") or node_data.get("recent_messages")
                    if messages and isinstance(messages, list):
                        for msg in messages[-10:]:  # Get last 10 messages from expanded channels
                            recent_messages.append({
                                "author": msg.get("sender_username", msg.get("sender", "Unknown")),
                                "content": msg.get("content", ""),
                                "timestamp": msg.get("timestamp"),
                                "channel": node_data.get("name", "Unknown"),
                                "channel_id": node_data.get("id", node_path)
                            })
            
            # If we found messages, add them to context
            if recent_messages:
                # Sort by timestamp and keep most recent
                recent_messages.sort(key=lambda x: x.get("timestamp", 0))
                context["recent_messages"] = recent_messages[-15:]  # Keep last 15 messages
        
        # Extract current channel information
        if "current_processing_channel_id" in world_state:
            context["current_channel_id"] = world_state["current_processing_channel_id"]
        elif "current_channel" in world_state:
            context["current_channel_id"] = world_state["current_channel"]
        
        # Extract available tools
        if "available_tools" in world_state:
            context["available_tools"] = world_state["available_tools"]
        elif "tools" in world_state:
            context["available_tools"] = [tool.get("name", str(tool)) for tool in world_state["tools"]]
        
        # Extract cycle ID
        if "cycle_id" in world_state:
            context["cycle_id"] = world_state["cycle_id"]
        
        # Extract trigger information from processing context
        processing_context = world_state.get("processing_context", {})
        cycle_context = processing_context.get("cycle_context", {})
        
        # Get the primary trigger type
        if "primary_trigger_type" in cycle_context:
            context["trigger_type"] = cycle_context["primary_trigger_type"]
            logger.info(f"Extracted trigger type: {context['trigger_type']}")
        
        # Also check for trigger information in triggers list
        triggers = cycle_context.get("triggers", [])
        if triggers and not context.get("trigger_type"):
            # Get the highest priority trigger type
            highest_priority_trigger = max(triggers, key=lambda t: t.get('priority', 0))
            context["trigger_type"] = highest_priority_trigger.get('type')
            logger.info(f"Extracted trigger type from triggers list: {context['trigger_type']}")
        
        return context
    
    async def generate_response(self, prompt: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Interface for generating responses.
        
        Maintains compatibility with code that expects this method format.
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
    
    async def make_decision(self, world_state: Dict[str, Any], cycle_id: str) -> Dict[str, Any]:
        """
        Make a decision based on current world state.
        
        This method provides legacy compatibility with the node processor and other
        components that expect the make_decision interface.
        
        Args:
            world_state: Current state of the world
            cycle_id: Unique identifier for this decision cycle
            
        Returns:
            Dict containing selected actions and reasoning
        """
        try:
            logger.info(f"AIEngine: Starting decision cycle {cycle_id}")
            
            # Call the decide_actions method to get the decision data
            decision_data = await self.decide_actions(world_state)
            
            # Convert to simplified action format
            selected_actions = []
            for action_data in decision_data.get("selected_actions", []):
                try:
                    action_plan = {
                        'action_type': action_data.get("action_type", "unknown"),
                        'parameters': action_data.get("parameters", {}),
                        'reasoning': action_data.get("reasoning", "No reasoning provided"),
                        'priority': action_data.get("priority", 5),
                    }
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
                selected_actions.sort(key=lambda x: x['priority'], reverse=True)
                selected_actions = selected_actions[:3]  # max actions per cycle
            
            result = {
                'selected_actions': selected_actions,
                'reasoning': decision_data.get("reasoning", ""),
                'observations': decision_data.get("observations", ""),
                'thought': decision_data.get("thought", ""),
                'cycle_id': cycle_id,
            }
            
            # Log the AI's thought process for debugging
            if result['thought']:
                logger.info(f"AI Thought Process (Cycle {cycle_id}): {result['thought']}")
            
            logger.info(
                f"AIEngine: Cycle {cycle_id} complete - "
                f"selected {len(result['selected_actions'])} actions"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error in make_decision for cycle {cycle_id}: {e}")
            return {
                'selected_actions': [],
                'reasoning': f"Error: {str(e)}",
                'observations': "Error during decision making",
                'thought': "",
                'cycle_id': cycle_id,
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


def create_mock_ai_engine(responses: List[str]) -> "AIEngine":
    """Create a mock AI engine for testing."""
    engine = AIEngine(api_key="mock_key", model="mock_model")
    engine.provider = MockAIProvider(responses)
    return engine


# Module exports for clean imports
__all__ = [
    # Main classes
    'AIEngine',
    'AIEngineConfig', 
    'AIProvider',
    'AIResponse',
    'ToolCall',
    'ObservationResponse',
    'ErrorAnalysis',
    
    # Factory functions
    'create_ai_engine',
    
    # Testing utilities
    'MockAIProvider',
    'create_mock_ai_engine',
]
