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
    model_config = {"extra": "forbid"}  # Forbid additional properties
    
    name: str = Field(description="The name of the tool to be called.")
    parameters: Dict[str, Any] = Field(
        default_factory=dict, description="The parameters for the tool call."
    )
    reasoning: Optional[str] = Field(
        None, description="The AI's reasoning for this specific tool call."
    )


class AIResponse(BaseModel):
    """The standard structured response from the AI for making decisions."""
    model_config = {"extra": "forbid"}  # Forbid additional properties
    
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
        self._structured_output_cache = None  # Cache for model capabilities
        self._cache_expiry = 0  # Cache expiry time

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
        # Validate model exists, fallback to openrouter/auto if not
        validated_model = await self._validate_and_get_model()
        
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": settings.ai.http_referer,
            "X-Title": settings.ai.x_title,
        }

        payload = {
            "model": validated_model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }

        # Structured output handling with better capability detection
        structured_output_attempted = False
        if response_model and self.config.use_structured_outputs:
            # Ensure we have fresh capability data
            capabilities = await self._check_model_capabilities()
            logger.debug(f"Model capabilities cache: {capabilities}")
            
            # Check various possible model ID formats using the validated model
            model_variations = [
                validated_model.lower(),
                validated_model,
                validated_model.replace("/", "_").lower(),
            ]
            
            model_supports_structured = False
            for model_var in model_variations:
                if capabilities.get(model_var, False):
                    model_supports_structured = True
                    logger.debug(f"Found structured output support for model variant: {model_var}")
                    break
            
            if model_supports_structured:
                try:
                    schema = response_model.model_json_schema()
                    
                    # Fix additionalProperties for all object types in the schema
                    def fix_additional_properties(obj):
                        if isinstance(obj, dict):
                            if obj.get("type") == "object":
                                obj["additionalProperties"] = False
                            # Recursively process nested objects
                            for key, value in obj.items():
                                if isinstance(value, dict):
                                    fix_additional_properties(value)
                                elif isinstance(value, list):
                                    for item in value:
                                        if isinstance(item, dict):
                                            fix_additional_properties(item)
                    
                    fix_additional_properties(schema)
                    
                    response_format = {
                        "type": "json_schema",
                        "json_schema": {
                            "name": response_model.__name__.lower(),
                            "strict": True,
                            "schema": schema
                        }
                    }
                    
                    payload["response_format"] = response_format
                    structured_output_attempted = True
                    
                    logger.info(f"=== STRUCTURED OUTPUT ENABLED ===")
                    logger.info(f"Model: {validated_model}")
                    logger.info(f"Response model: {response_model.__name__}")
                    logger.info(f"Schema properties: {list(schema.get('properties', {}).keys())}")
                    logger.info(f"=== END STRUCTURED DEBUG ===")
                    
                except Exception as e:
                    logger.warning(f"Failed to setup structured output: {e}")
                    structured_output_attempted = False
            else:
                logger.debug(f"Model {self.config.model} does not support structured outputs. Available models: {list(capabilities.keys())[:10]}...")

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        last_exception = None
        for attempt in range(self.config.max_retries + 1):
            try:
                # Log comprehensive request details
                payload_size = len(str(payload))
                logger.info(f"🚀 OPENROUTER REQUEST (Attempt {attempt + 1}/{self.config.max_retries + 1})")
                logger.info(f"   URL: {settings.openrouter_api_url}")
                logger.info(f"   Model: {validated_model}")
                logger.info(f"   Temperature: {payload.get('temperature')}")
                logger.info(f"   Max Tokens: {payload.get('max_tokens')}")
                logger.info(f"   Structured Output: {structured_output_attempted}")
                logger.info(f"   Tools: {len(tools) if tools else 0}")
                logger.info(f"   Payload Size: {payload_size} chars")
                logger.info(f"   Messages Count: {len(messages)}")
                
                # Log message details
                for i, msg in enumerate(messages):
                    role = msg.get('role', 'unknown')
                    content = msg.get('content', '')
                    content_preview = content[:200] + "..." if len(content) > 200 else content
                    logger.info(f"   Message {i+1} [{role}]: {content_preview}")
                
                # Log headers (excluding sensitive auth)
                safe_headers = {k: v for k, v in headers.items() if k.lower() != 'authorization'}
                safe_headers['authorization'] = f"Bearer {self.config.api_key[:10]}..." if self.config.api_key else "None"
                logger.info(f"   Headers: {safe_headers}")
                
                # Log tools if present
                if tools:
                    logger.info(f"   Available Tools:")
                    for tool in tools:
                        tool_name = tool.get('function', {}).get('name', 'unknown')
                        tool_desc = tool.get('function', {}).get('description', 'no description')
                        logger.info(f"     - {tool_name}: {tool_desc[:100]}...")
                
                # Log structured output schema if present
                if 'response_format' in payload:
                    schema_name = payload['response_format'].get('json_schema', {}).get('name', 'unknown')
                    logger.info(f"   Response Schema: {schema_name}")
                    schema_props = list(payload['response_format'].get('json_schema', {}).get('schema', {}).get('properties', {}).keys())
                    logger.info(f"   Schema Properties: {schema_props}")
                
                logger.info("📤 Sending request to OpenRouter...")
                    
                response = await self.client.post(settings.openrouter_api_url, headers=headers, json=payload)
                response.raise_for_status()
                result = response.json()
                
                # Log comprehensive response details
                logger.info("📥 OPENROUTER RESPONSE RECEIVED")
                logger.info(f"   Status: {response.status_code}")
                logger.info(f"   Headers: {dict(response.headers)}")
                
                if 'choices' in result and result['choices']:
                    choice = result['choices'][0]
                    message = choice.get('message', {})
                    content = message.get('content', '')
                    
                    logger.info(f"   Choices: {len(result['choices'])}")
                    logger.info(f"   Finish Reason: {choice.get('finish_reason', 'unknown')}")
                    logger.info(f"   Content Length: {len(content)} chars")
                    
                    # Log content preview
                    content_preview = content[:500] + "..." if len(content) > 500 else content
                    logger.info(f"   Content Preview: {content_preview}")
                    
                    # Log tool calls if present
                    if 'tool_calls' in message and message['tool_calls']:
                        logger.info(f"   Tool Calls: {len(message['tool_calls'])}")
                        for i, tool_call in enumerate(message['tool_calls']):
                            tool_name = tool_call.get('function', {}).get('name', 'unknown')
                            tool_args = tool_call.get('function', {}).get('arguments', '{}')
                            logger.info(f"     Tool {i+1}: {tool_name} with args: {tool_args[:200]}...")
                
                # Log usage information if available
                if 'usage' in result:
                    usage = result['usage']
                    logger.info(f"   Token Usage:")
                    logger.info(f"     Prompt: {usage.get('prompt_tokens', 'unknown')}")
                    logger.info(f"     Completion: {usage.get('completion_tokens', 'unknown')}")
                    logger.info(f"     Total: {usage.get('total_tokens', 'unknown')}")
                
                # Log model information if available
                if 'model' in result:
                    logger.info(f"   Response Model: {result['model']}")
                
                logger.info("✅ OpenRouter request completed successfully")
                
                return result
                
            except httpx.HTTPStatusError as e:
                logger.error(f"❌ OPENROUTER HTTP ERROR")
                logger.error(f"   Status Code: {e.response.status_code}")
                logger.error(f"   Response Headers: {dict(e.response.headers)}")
                
                try:
                    error_detail = e.response.text
                    logger.error(f"   Response Text: {error_detail}")
                    
                    # Try to parse as JSON for better error details
                    if error_detail:
                        try:
                            error_json = e.response.json()
                            logger.error(f"   Error JSON: {error_json}")
                        except:
                            pass  # Not JSON, already logged as text
                except Exception as detail_error:
                    logger.error(f"   Could not read response details: {detail_error}")
                
                if e.response.status_code == 400:
                    # If structured output failed, try without it
                    if structured_output_attempted and 'response_format' in payload:
                        try:
                            logger.warning("🔄 Structured output failed, retrying without response_format")
                            payload_without_format = payload.copy()
                            del payload_without_format['response_format']
                            
                            logger.info("🚀 OPENROUTER RETRY WITHOUT STRUCTURED OUTPUT")
                            logger.info(f"   Retry Payload Size: {len(str(payload_without_format))} chars")
                            
                            response = await self.client.post(settings.openrouter_api_url, headers=headers, json=payload_without_format)
                            response.raise_for_status()
                            result = response.json()
                            
                            logger.info("📥 OPENROUTER RETRY RESPONSE")
                            if 'choices' in result and result['choices']:
                                content_length = len(result['choices'][0].get('message', {}).get('content', ''))
                                logger.info(f"   Retry Content Length: {content_length} chars")
                            logger.info("✅ Retry without structured output succeeded")
                            
                            return result
                            
                        except Exception as fallback_error:
                            logger.error(f"❌ Fallback without structured output also failed: {fallback_error}")
                        
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
                logger.error(f"❌ OPENROUTER CONNECTION ERROR")
                logger.error(f"   Error Type: {type(e).__name__}")
                logger.error(f"   Error Details: {str(e)}")
                
                last_exception = e
                if attempt < self.config.max_retries:
                    delay = 2 ** attempt
                    logger.warning(f"🔄 Request failed ({type(e).__name__}). Retrying in {delay}s...")
                    await asyncio.sleep(delay)
                    continue
                raise

        logger.error(f"💥 OPENROUTER REQUEST FAILED AFTER ALL RETRIES")
        logger.error(f"   Total Attempts: {self.config.max_retries + 1}")
        logger.error(f"   Final Exception: {type(last_exception).__name__}: {last_exception}")
        logger.error(f"   Model: {validated_model}")
        logger.error(f"   Payload Size: {len(str(payload))} chars")
        
        raise ValueError(f"Chat completion failed after {self.config.max_retries} retries.") from last_exception


    async def _validate_and_get_model(self) -> str:
        """
        Validate that the configured model exists in OpenRouter's model list.
        If not found, fallback to 'openrouter/auto'.
        """
        try:
            logger.info("🔍 VALIDATING MODEL WITH OPENROUTER")
            logger.info(f"   Checking model: {self.config.model}")
            
            # Get available models from OpenRouter
            response = await self.client.get("https://openrouter.ai/api/v1/models")
            response.raise_for_status()
            
            logger.info(f"   Model validation response: {response.status_code}")
            
            models_data = response.json()
            available_model_ids = {model.get("id", "").lower() for model in models_data.get("data", [])}
            
            logger.info(f"   Total available models: {len(available_model_ids)}")
            
            current_model = self.config.model.lower()
            
            # Check if current model exists
            if current_model in available_model_ids:
                logger.info(f"✅ Model '{self.config.model}' validated successfully")
                return self.config.model
            else:
                logger.warning(f"⚠️ Model '{self.config.model}' not found in OpenRouter model list. Falling back to 'openrouter/auto'")
                logger.info(f"   Some available models: {list(sorted(available_model_ids))[:10]}...")
                # Update the config to use the fallback
                self.config.model = "openrouter/auto"
                return "openrouter/auto"
                
        except Exception as e:
            logger.error(f"❌ Failed to validate model via OpenRouter API: {e}. Using configured model '{self.config.model}' as-is")
            return self.config.model

    async def _check_model_capabilities(self) -> Dict[str, bool]:
        """
        Fetch model capabilities from OpenRouter Models API.
        Returns a dict mapping model IDs to whether they support structured outputs.
        """
        current_time = time.time()
        
        # Use cache if it's still valid (cache for 1 hour)
        if self._structured_output_cache and current_time < self._cache_expiry:
            logger.debug(f"📋 Using cached model capabilities ({len(self._structured_output_cache)} models)")
            return self._structured_output_cache
        
        try:
            logger.info("🔍 FETCHING MODEL CAPABILITIES FROM OPENROUTER")
            response = await self.client.get("https://openrouter.ai/api/v1/models")
            response.raise_for_status()
            
            logger.info(f"   Capabilities response: {response.status_code}")
            
            models_data = response.json()
            capabilities = {}
            structured_output_models = []
            
            for model in models_data.get("data", []):
                model_id = model.get("id", "")
                supported_params = model.get("supported_parameters", [])
                
                # Check if the model supports structured outputs
                supports_structured = "structured_outputs" in supported_params
                capabilities[model_id.lower()] = supports_structured
                
                if supports_structured:
                    structured_output_models.append(model_id)
                    logger.debug(f"   Model {model_id} supports structured outputs")
            
            # Cache the results for 1 hour
            self._structured_output_cache = capabilities
            self._cache_expiry = current_time + 3600
            
            logger.info(f"✅ Loaded capabilities for {len(capabilities)} models from OpenRouter API")
            logger.info(f"   Models supporting structured outputs: {len(structured_output_models)}")
            if structured_output_models:
                logger.info(f"   Examples: {structured_output_models[:5]}")
            
            return capabilities
            
        except Exception as e:
            logger.error(f"❌ Failed to fetch model capabilities from OpenRouter API: {e}")
            
            # Fallback to hardcoded list if API fails
            fallback_models = {
                "openai/gpt-4o": True,
                "openai/gpt-4o-mini": True,
                "openai/gpt-4-turbo": True,
                "openai/gpt-4": True,
            }
            logger.warning(f"   Using fallback hardcoded model capabilities: {list(fallback_models.keys())}")
            return fallback_models

    def supports_structured_outputs(self) -> bool:
        """
        OpenRouter supports structured outputs for select models.
        Check if the current model supports structured outputs using the Models API.
        """
        logger.debug(f"Checking structured output support for model: {self.config.model}")
        
        # This is a sync method but we need async data, so we'll use a cached approach
        # The cache will be populated during the first async call
        if self._structured_output_cache:
            model_key = self.config.model.lower()
            is_supported = self._structured_output_cache.get(model_key, False)
            logger.debug(f"Model {model_key} structured output support: {is_supported}")
            return is_supported
        
        # If no cache yet, assume no support for safety
        logger.debug(f"No capability cache available for {self.config.model}, assuming no structured output support")
        return False


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
        
        Supports OODA loop phases via ai_instruction context.
        """
        try:
            system_prompt = self._build_system_prompt(world_state)
            user_prompt = self._build_user_prompt(world_state)
            
            response = await self.generate_structured_response(
                system_prompt, user_prompt, AIResponse
            )
            
            # Type assertion to help with type checking
            if not isinstance(response, AIResponse):
                raise ValueError(f"Expected AIResponse, got {type(response)}")
            
            return {
                "reasoning": response.reasoning,
                "selected_actions": [
                    {
                        "action_type": call.name,
                        "arguments": call.parameters,
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

    def _build_user_prompt(self, context: Dict[str, Any]) -> str:
        """Build phase-specific user prompt based on context."""
        
        # Check for OODA phase-specific instructions
        ai_instruction = context.get("ai_instruction", {})
        phase = ai_instruction.get("phase")
        
        if phase == "orientation":
            return (
                "ORIENTATION PHASE:\n"
                "Your goal is to determine what information needs deeper inspection.\n"
                "Review the collapsed_node_summaries and system_events.\n"
                "Use ONLY the expand_node, pin_node, or collapse_node tools to request more detailed information.\n"
                "DO NOT use any other tools in this phase - your only job is to decide what information you need to see.\n"
                "Focus on nodes that seem most relevant to the current situation or trigger."
            )
        elif phase == "decision":
            return (
                "DECISION PHASE:\n"
                "You have expanded the relevant nodes and can see their detailed content in expanded_nodes.\n"
                "Based on this full context, decide on the best external actions to take.\n"
                "You can use any available tools EXCEPT node management tools (expand_node, pin_node, collapse_node).\n"
                "Choose actions like sending messages, searching, or other external operations."
            )
        else:
            # Default behavior for non-OODA processing
            return "Analyze the current state and decide on the next actions based on my instructions."

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
