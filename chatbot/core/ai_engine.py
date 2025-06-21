"""
Unified AI Engine with Structured Outputs

This module provides a unified and robust AI engine for the chatbot system.

Key Features:
-   Structured outputs using Pydantic models for predictable and safe results.
-   Support for multiple AI providers through an abstract base class.
-   Advanced error handling with exponential backoff and retries.
-   Native tool-calling support with fallback to text-based JSON extraction.
-   Sophisticated prompt engineering that dynamically includes context and response format requirements.
-   Centralized and simplified configuration management.
-   Legacy compatibility layers to support existing application components during migration.
"""

import asyncio
import json
import logging
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Type

import httpx
from pydantic import BaseModel, Field, ValidationError

from ..config import settings

# --- Constants ---
# Centralized constants for easier updates and maintenance.

logger = logging.getLogger(__name__)


# --- Pydantic Models for Structured I/O ---
# These models define the expected structure of AI inputs and outputs,
# preventing malformed data and improving system reliability.

class AIProvider(Enum):
    """Enumeration of supported AI providers."""
    OPENROUTER = "openrouter"
    # Future providers like OPENAI, ANTHROPIC, OLLAMA can be added here.


class ToolCall(BaseModel):
    """A structured representation of a tool call requested by the AI."""
    name: str = Field(description="The name of the tool to be called.")
    parameters: Dict[str, Any] = Field(
        default_factory=dict, description="The parameters for the tool call."
    )
    reasoning: Optional[str] = Field(
        None, description="The AI's reasoning for this specific tool call."
    )


class AIResponse(BaseModel):
    """The standard structured response from the AI for making decisions."""
    reasoning: str = Field(
        description="The AI's high-level reasoning for its chosen actions or message."
    )
    tool_calls: List[ToolCall] = Field(
        default_factory=list,
        description="A list of tool calls to be executed by the system.",
    )
    message: Optional[str] = Field(
        None,
        description="A direct message to be sent if no tool calls are necessary.",
    )
    confidence: float = Field(
        default=0.8,
        description="The AI's confidence in the correctness of its response (0.0 to 1.0).",
    )


# --- Configuration ---
@dataclass
class AIEngineConfig:
    """Configuration settings for the AIEngine."""
    api_key: str
    provider: AIProvider = AIProvider.OPENROUTER
    model: str = settings.ai.model
    multimodal_model: str = settings.ai.multimodal_model
    temperature: float = 0.7
    max_tokens: int = 4000
    timeout: float = 45.0
    max_retries: int = 3
    use_structured_outputs: bool = True
    fallback_to_text_parsing: bool = True


# --- Provider Abstraction ---
class AIProviderBase(ABC):
    """Abstract Base Class for all AI provider implementations."""

    def __init__(self, config: AIEngineConfig, client: httpx.AsyncClient):
        self.config = config
        self.client = client

    @abstractmethod
    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        response_model: Optional[Type[BaseModel]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Abstract method to generate a chat completion."""
        pass

    @abstractmethod
    def supports_structured_outputs(self) -> bool:
        """Abstract method to check for native structured output support."""
        pass


# --- Provider Implementation ---
class OpenRouterProvider(AIProviderBase):
    """AI Provider implementation for OpenRouter."""

    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        response_model: Optional[Type[BaseModel]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Generates a chat completion via OpenRouter with robust retry logic.
        """
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": settings.ai.http_referer,
            "X-Title": settings.ai.x_title,
        }

        payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }

        if response_model and self.supports_structured_outputs():
            schema = response_model.model_json_schema()
            
            # Recursively ensure additionalProperties is set to false for OpenAI compatibility
            def ensure_additional_properties_false(obj):
                if isinstance(obj, dict):
                    if obj.get("type") == "object" and "additionalProperties" not in obj:
                        obj["additionalProperties"] = False
                    # Recursively process nested objects
                    for key, value in obj.items():
                        if isinstance(value, dict):
                            ensure_additional_properties_false(value)
                        elif isinstance(value, list):
                            for item in value:
                                if isinstance(item, dict):
                                    ensure_additional_properties_false(item)
            
            ensure_additional_properties_false(schema)
            
            # Debug logging to see the actual schema being sent
            logger.debug(f"Structured output schema for {response_model.__name__}: {json.dumps(schema, indent=2)}")
            
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": response_model.__name__.lower(),
                    "strict": True,
                    "schema": schema
                }
            }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        last_exception = None
        for attempt in range(self.config.max_retries + 1):
            try:
                # Log payload size and structure for debugging 400 errors
                payload_size = len(str(payload))
                if payload_size > 50000:  # Log if payload is suspiciously large
                    logger.warning(f"Large payload detected: {payload_size} characters")
                    
                response = await self.client.post(settings.openrouter_api_url, headers=headers, json=payload)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 400:
                    # Log more details for 400 errors
                    logger.error(f"400 Bad Request. Payload size: {len(str(payload))} chars")
                    logger.error(f"Payload keys: {list(payload.keys())}")
                    if 'messages' in payload:
                        logger.error(f"Message count: {len(payload['messages'])}")
                        for i, msg in enumerate(payload['messages']):
                            logger.error(f"Message {i} length: {len(str(msg))}")
                    if 'tools' in payload:
                        logger.error(f"Tools count: {len(payload['tools'])}")
                    
                    try:
                        error_detail = e.response.json()
                        logger.error(f"OpenRouter error details: {error_detail}")
                    except:
                        logger.error(f"Response text: {e.response.text[:500]}")
                        
                last_exception = e
                last_exception = e
                if e.response.status_code in [401, 403]:
                    logger.error(f"Critical auth error ({e.response.status_code}): {e.response.text}")
                    raise ValueError(f"Authentication/Authorization failed. Check API key. Details: {e.response.text}") from e
                if e.response.status_code >= 500 or e.response.status_code == 429:
                    if attempt < self.config.max_retries:
                        delay = 2 ** attempt
                        logger.warning(
                            f"Server error or rate limit ({e.response.status_code}). Retrying in {delay}s..."
                        )
                        await asyncio.sleep(delay)
                        continue
                raise
            except (httpx.RequestError, asyncio.TimeoutError) as e:
                last_exception = e
                if attempt < self.config.max_retries:
                    delay = 2 ** attempt
                    logger.warning(f"Request failed ({type(e).__name__}). Retrying in {delay}s...")
                    await asyncio.sleep(delay)
                    continue
                raise

        raise ValueError(f"Chat completion failed after {self.config.max_retries} retries.") from last_exception


    def supports_structured_outputs(self) -> bool:
        """
        OpenRouter supports structured outputs for select models.
        Check if the current model supports structured outputs.
        """
        # List of models known to support structured outputs on OpenRouter
        supported_models = [
            "openai/gpt-4o",
            "openai/gpt-4o-mini", 
            "openai/gpt-4-turbo",
            "openai/gpt-4",
            "fireworks/",  # All Fireworks models
        ]
        
        model = self.config.model.lower()
        return any(model.startswith(supported.lower()) for supported in supported_models)


# --- Main AIEngine Class ---
class AIEngine:
    """
    The primary, unified AI engine. It orchestrates prompting, tool registration,
    API calls, and response parsing.
    """

    def __init__(self, config: AIEngineConfig):
        self.config = config
        self.http_client = httpx.AsyncClient(timeout=config.timeout)
        self.provider = self._create_provider()
        self.tool_schemas: Dict[str, Dict[str, Any]] = {}
        logger.debug(
            f"AIEngine initialized with provider '{config.provider.value}' and model '{config.model}'"
        )

    def _create_provider(self) -> AIProviderBase:
        """Factory method to instantiate the configured AI provider."""
        if self.config.provider == AIProvider.OPENROUTER:
            return OpenRouterProvider(self.config, self.http_client)
        raise NotImplementedError(f"Provider '{self.config.provider}' is not implemented.")

    def register_tool(self, name: str, schema: Dict[str, Any]):
        """Registers a tool's schema for use in tool-calling."""
        self.tool_schemas[name] = {
            "type": "function",
            "function": {
                "name": name,
                "description": schema.get("description", "No description available."),
                "parameters": schema.get("parameters", {"type": "object", "properties": {}}),
            },
        }
        logger.debug(f"Registered tool: {name}")

    async def generate_structured_response(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: Type[BaseModel] = AIResponse,
        available_tools: Optional[List[str]] = None,
    ) -> BaseModel:
        """
        Core method to generate a structured, validated response from the AI.
        """
        # 1. Build tool schemas
        tools = [self.tool_schemas[tool] for tool in available_tools if tool in self.tool_schemas] if available_tools else None

        # 2. Try native structured output first (if enabled)
        if self.config.use_structured_outputs and self.provider.supports_structured_outputs():
            logger.debug("Attempting generation with native structured outputs.")
            json_instructions = self._build_json_instructions(response_model)
            messages = [
                {"role": "system", "content": f"{system_prompt}\n{json_instructions}"},
                {"role": "user", "content": user_prompt},
            ]
            try:
                response_data = await self.provider.chat_completion(
                    messages=messages, response_model=response_model, tools=tools
                )
                content = response_data["choices"][0]["message"]["content"]
                return response_model.model_validate_json(content)
            except (ValidationError, KeyError, IndexError, json.JSONDecodeError) as e:
                logger.warning(f"Native structured output failed: {e}. Falling back to text parsing.")
                if not self.config.fallback_to_text_parsing:
                    raise

        # 3. Fallback to text parsing
        logger.debug("Using fallback text parsing for structured output.")
        json_instructions = self._build_json_instructions(response_model, with_rules=True)
        messages = [
            {"role": "system", "content": f"{system_prompt}\n{json_instructions}"},
            {"role": "user", "content": user_prompt},
        ]
        response_data = await self.provider.chat_completion(messages=messages, tools=tools)
        raw_content = response_data["choices"][0]["message"]["content"]
        
        if not raw_content:
            raise ValueError("AI returned an empty response.")
            
        json_content = self._extract_json_from_text(raw_content)
        return response_model.model_validate(json_content)

    def _build_json_instructions(
        self, response_model: Type[BaseModel], with_rules: bool = False
    ) -> str:
        """Constructs the part of the prompt that demands JSON output."""
        schema = json.dumps(response_model.model_json_schema(), indent=2)
        instructions = f"""
RESPONSE FORMATTING:
Your entire response MUST be a single, valid JSON object that conforms to the following schema.
Do not include any text, markdown, or explanations outside of the JSON object.

SCHEMA:
{schema}"""

        if with_rules:
            instructions += """

CRITICAL FORMATTING RULES:
- The final output must only be the JSON object.
- Wrap the JSON in ```json ... ``` if necessary.
- Ensure all strings are enclosed in double quotes.
- Do not add comments or trailing commas.
"""
        return instructions

    def _extract_json_from_text(self, text: str) -> Dict[str, Any]:
        """
        Robustly extracts a JSON object from a string, which might include markdown.
        """
        text = text.strip()
        
        # Strategy 1: Look for markdown code blocks
        match = re.search(r"```(?:json)?\s*\n({.*?})\s*\n```", text, re.DOTALL)
        if match:
            json_str = match.group(1)
            try:
                logger.debug("JSON extraction successful via markdown block.")
                return json.loads(json_str)
            except json.JSONDecodeError:
                logger.warning("Found markdown block but failed to parse JSON.")

        # Strategy 2: Find the first '{' and last '}'
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            json_str = text[start : end + 1]
            try:
                logger.debug("JSON extraction successful via first/last brace.")
                return json.loads(json_str)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse content between braces: {e}")

        # Strategy 3: Try to parse the entire string
        try:
            logger.debug("JSON extraction successful via direct parse.")
            return json.loads(text)
        except json.JSONDecodeError:
            raise ValueError(f"Could not extract valid JSON from AI response. Content: {text[:500]}...")


    async def decide_actions(self, world_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Primary decision-making interface for the application orchestrator.
        Takes the world state and returns a plan of action.
        """
        try:
            system_prompt = self._build_system_prompt(world_state)
            user_prompt = "Analyze the current state and decide on the next actions based on my instructions."
            
            response = await self.generate_structured_response(
                system_prompt, user_prompt, AIResponse
            )
            
            return {
                "reasoning": response.reasoning,
                "selected_actions": [
                    {
                        "action_type": call.name,
                        "parameters": call.parameters,
                        "reasoning": call.reasoning or response.reasoning,
                    }
                    for call in response.tool_calls
                ],
                "message": response.message,
            }
        except Exception as e:
            logger.error(f"Failed to decide actions: {e}", exc_info=True)
            return {
                "reasoning": f"An error occurred during decision making: {e}",
                "selected_actions": [],
                "message": "I encountered an internal error. Please try again later.",
            }

    def _build_system_prompt(self, context: Dict[str, Any]) -> str:
        """Constructs the main system prompt from the world state context."""

        # Identity and Core Directives
        prompt_parts = [
            """You are RatiChat, an advanced AI assistant integrated into a multi-platform chat system (Matrix, Farcaster).
Your primary goal is to be helpful, engaging, and context-aware.

CORE DIRECTIVES:
- You MUST respond when directly mentioned (e.g., '@ratichat') or in a direct message.
- Use tools to perform actions like sending replies, searching, or analyzing data.
- Provide clear reasoning for your decisions.
- If there is nothing to do, state that clearly in your reasoning and select no tools."""
        ]

        # Dynamic Context
        if context.get("current_processing_channel_id"):
            prompt_parts.append(
                f"CONTEXT: You are currently focused on channel: {context['current_processing_channel_id']}."
            )

        if (trigger_type := context.get("trigger_type")):
             prompt_parts.append(f"TRIGGER: This cycle was triggered by '{trigger_type}'. Direct mentions require an immediate response.")

        # --- ENHANCED MESSAGE EXTRACTION ---
        all_messages = []

        # 1. Look in expanded_nodes (primary source)
        if (expanded_nodes := context.get("expanded_nodes")):
            for node_path, node_data in expanded_nodes.items():
                if isinstance(node_data, dict) and "recent_messages" in node_data and node_data["recent_messages"]:
                    channel_name = node_data.get('name', node_path)
                    all_messages.append({"role": "system", "content": f"--- Messages from {channel_name} ---"})
                    for msg in node_data["recent_messages"]:
                        sender = msg.get("sender", "unknown")
                        content = msg.get("content", "")
                        role = "assistant" if sender == "@ratichat:chat.ratimics.com" else "user"
                        
                        if role == "user" and ("@ratichat" in content.lower() or "[ratichat]" in content.lower()):
                            content += " [DIRECT MENTION - RESPONSE REQUIRED]"

                        all_messages.append({
                            "role": role,
                            "content": f"{sender}: {content}"
                        })

        # 2. Fallback to top-level recent_messages (for backward compatibility)
        if not all_messages and (legacy_messages := context.get("recent_messages")):
            for msg in legacy_messages:
                author = msg.get("author", "unknown")
                content = msg.get("content", "")
                role = "assistant" if author == "@ratichat:chat.ratimics.com" else "user"

                if role == "user" and ("@ratichat" in content.lower() or "[ratichat]" in content.lower()):
                    content += " [DIRECT MENTION - RESPONSE REQUIRED]"

                all_messages.append({
                    "role": role,
                    "content": f"{author}: {content}"
                })

        # 3. Add extracted messages to the prompt
        if all_messages:
            prompt_parts.append("\nRECENT MESSAGES:")
            # Limit to last 20 messages overall for context size
            for msg in all_messages[-20:]:
                if msg["role"] == "system":
                     prompt_parts.append(msg["content"])
                else:
                     # We've already formatted the content with the sender
                     prompt_parts.append(f"- {msg['content']}")

        # Available Tools
        if self.tool_schemas:
            prompt_parts.append(f"AVAILABLE TOOLS: {', '.join(self.tool_schemas.keys())}")

        return "\n\n".join(prompt_parts)


    async def cleanup(self):
        """Closes network connections and cleans up resources."""
        await self.http_client.aclose()
        logger.debug("AIEngine resources have been cleaned up.")


# --- Factory Function ---
def create_ai_engine(
    api_key: str,
    model: str = settings.ai.model,
    **kwargs,
) -> AIEngine:
    """
    Factory function to create and configure an AIEngine instance.

    Args:
        api_key: The API key for the selected provider.
        model: The specific AI model to use.
        **kwargs: Additional configuration options for AIEngineConfig.

    Returns:
        An initialized modern AIEngine instance.
    """
    if not api_key:
        raise ValueError("API key must be provided to create an AI engine.")

    config = AIEngineConfig(api_key=api_key, model=model, **kwargs)
    return AIEngine(config)


# --- Exports ---
# A clear list of what this module provides for external use.
__all__ = [
    "AIEngine",
    "AIEngineConfig", 
    "AIProvider",
    "AIResponse",
    "ToolCall",
    "create_ai_engine",
]
