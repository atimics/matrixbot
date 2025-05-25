import asyncio
import os
import httpx
import json
import logging
from typing import Dict, List, Optional, Any
from dotenv import load_dotenv

from message_bus import MessageBus
from event_definitions import (
    ThinkingRequestEvent, ThinkingResponseEvent,
    StructuredPlanningRequestEvent, StructuredPlanningResponseEvent,
    AIThoughts, AIResponsePlan, ChannelResponse, AIAction
)
from action_registry_service import ActionRegistryService
# Added imports for rich context building
import prompt_constructor
import database

logger = logging.getLogger(__name__)
load_dotenv()

class JsonCentricAIService:
    """Service for handling two-step AI processing: Thinking + Structured Planning."""
    
    def __init__(self, message_bus: MessageBus, action_registry: ActionRegistryService):
        self.bus = message_bus
        self.action_registry = action_registry
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        self.site_url = os.getenv("YOUR_SITE_URL", "https://your-matrix-bot.example.com/soa")
        self.site_name = os.getenv("YOUR_SITE_NAME", "MyMatrixBotSOA_AI")
        self._stop_event = asyncio.Event()
        
        # Model configuration for two-step processing
        self.thinker_model = os.getenv("THINKER_MODEL", "openai/gpt-4o-mini")
        self.planner_model = os.getenv("PLANNER_MODEL", "openai/gpt-4o-mini")
        
        # Database path for accessing bot context
        self.db_path = os.getenv("DATABASE_PATH", "matrix_bot_soa.db")
        
        # Set the message bus for prompt constructor image processing
        prompt_constructor.set_message_bus(message_bus)
    
    async def _make_openrouter_request(self, model_name: str, messages: List[Dict[str, Any]], 
                                     response_format: Optional[Dict[str, Any]] = None,
                                     plugins: Optional[List[str]] = None) -> tuple[bool, Optional[str], Optional[str]]:
        """Make a request to OpenRouter API."""
        if not self.api_key:
            return False, None, "OpenRouter API key not configured"
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": self.site_url,
            "X-Title": self.site_name,
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": model_name,
            "messages": messages
        }
        
        if response_format:
            payload["response_format"] = response_format
        
        if plugins:
            payload["plugins"] = plugins
        
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json=payload
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Log the full API response for debugging
                    logger.info(f"JsonCentricAI: Full API response for model {model_name}:")
                    logger.info(f"JsonCentricAI: Response data keys: {list(data.keys())}")
                    
                    if "choices" in data and len(data["choices"]) > 0:
                        choice = data["choices"][0]
                        logger.info(f"JsonCentricAI: Choice keys: {list(choice.keys())}")
                        
                        if "message" in choice:
                            message = choice["message"]
                            logger.info(f"JsonCentricAI: Message keys: {list(message.keys())}")
                            content = message.get("content")
                            logger.info(f"JsonCentricAI: Content type: {type(content)}, length: {len(content) if content else 0}")
                            
                            # Handle empty or None content
                            if not content or content.strip() == "":
                                logger.warning(f"JsonCentricAI: Empty response from model {model_name}")
                                
                                # Check if there's a reasoning field (for some models)
                                reasoning = message.get("reasoning")
                                if reasoning and reasoning.strip():
                                    logger.info(f"JsonCentricAI: Using reasoning field as content: {reasoning[:100]}...")
                                    return True, reasoning, None
                                
                                # Check for error info in the response
                                error_info = data.get("error") or choice.get("error")
                                if error_info:
                                    return False, None, f"API returned error: {error_info}"
                                
                                # Check finish reason for clues
                                finish_reason = choice.get("finish_reason") or choice.get("native_finish_reason")
                                if finish_reason:
                                    logger.info(f"JsonCentricAI: Finish reason: {finish_reason}")
                                    if finish_reason in ["content_filter", "safety"]:
                                        return False, None, f"Content filtered by model (reason: {finish_reason})"
                                    elif finish_reason == "length":
                                        return False, None, "Response truncated due to length limit"
                                
                                return False, None, f"Empty response from model {model_name} (finish_reason: {finish_reason})"
                            
                            return True, content, None
                        else:
                            return False, None, "No message in API response choice"
                    else:
                        return False, None, "No choices in API response"
                else:
                    error_msg = f"OpenRouter API error: {response.status_code} - {response.text}"
                    logger.error(f"JsonCentricAI: {error_msg}")
                    return False, None, error_msg
                    
        except Exception as e:
            error_msg = f"OpenRouter request failed: {str(e)}"
            logger.error(f"JsonCentricAI: {error_msg}")
            return False, None, error_msg
    
    async def _handle_thinking_request(self, event: ThinkingRequestEvent) -> None:
        """Handle Step 1: Thought Generation Request."""
        logger.info(f"JsonCentricAI: Processing thinking request {event.request_id}")
        
        try:
            # Build thinking prompt
            thinking_messages = await self._build_thinking_prompt(event.context_batch)
            
            # Log the thinking prompt for debugging
            logger.info(f"JsonCentricAI: Thinking prompt for {event.request_id}:")
            for i, msg in enumerate(thinking_messages):
                logger.info(f"JsonCentricAI: Message {i}: {msg['role']} - {msg['content'][:200]}...")
            
            # Configure plugins for PDF processing if needed
            plugins = None
            if self._context_has_pdfs(event.context_batch):
                plugins = ["pdf-text"]  # or "mistral-ocr" based on preference
            
            # Make request to Thinker AI
            success, thoughts_text, error_msg = await self._make_openrouter_request(
                event.model_name,
                thinking_messages,
                plugins=plugins
            )
            
            if success and thoughts_text:
                # Log the thinking response
                logger.info(f"JsonCentricAI: Thinking response for {event.request_id}:")
                logger.info(f"JsonCentricAI: {thoughts_text}")
                
                # Parse thoughts for each channel
                thoughts = self._parse_thinking_response(thoughts_text, event.context_batch)
                
                response_event = ThinkingResponseEvent(
                    request_id=event.request_id,
                    success=True,
                    thoughts=thoughts,
                    original_request_payload={
                        "context_batch": event.context_batch.model_dump(),
                        "model_name": event.model_name
                    }
                )
            else:
                logger.error(f"JsonCentricAI: Thinking failed for {event.request_id}: {error_msg}")
                
                # Provide a fallback response to allow the system to continue
                fallback_thoughts = []
                for context in event.context_batch.channel_contexts:
                    # Extract basic content from current user input
                    if isinstance(context.current_user_input, dict):
                        user_content = context.current_user_input.get('content', 'No content')
                    else:
                        user_content = str(context.current_user_input)
                    
                    fallback_text = f"""AI analysis temporarily unavailable. 
User input: {user_content}
Basic reasoning: The user has sent a message that appears to be a greeting or general request. 
Since the AI thinking service is experiencing issues, I should provide a helpful response acknowledging their message."""
                    
                    fallback_thoughts.append(AIThoughts(
                        channel_id=context.channel_id,
                        thoughts_text=fallback_text
                    ))
                
                logger.info(f"JsonCentricAI: Using fallback thoughts for {event.request_id}")
                
                response_event = ThinkingResponseEvent(
                    request_id=event.request_id,
                    success=True,  # Mark as success so the system continues
                    thoughts=fallback_thoughts,
                    original_request_payload={
                        "context_batch": event.context_batch.model_dump(),
                        "model_name": event.model_name,
                        "fallback_used": True,
                        "fallback_reason": error_msg
                    }
                )
            
            await self.bus.publish(response_event)
            
        except Exception as e:
            logger.error(f"JsonCentricAI: Error in thinking request {event.request_id}: {e}")
            error_response = ThinkingResponseEvent(
                request_id=event.request_id,
                success=False,
                error_message=str(e)
            )
            await self.bus.publish(error_response)
    
    async def _handle_structured_planning_request(self, event: StructuredPlanningRequestEvent) -> None:
        """Handle Step 2: Structured Planning Request."""
        logger.info(f"JsonCentricAI: Processing structured planning request {event.request_id}")
        
        try:
            # Build structured planning prompt
            planning_messages = await self._build_planning_prompt(event.thoughts, event.original_context)
            
            # Log the planning prompt for debugging
            logger.info(f"JsonCentricAI: Planning prompt for {event.request_id}:")
            for i, msg in enumerate(planning_messages):
                logger.info(f"JsonCentricAI: Message {i}: {msg['role']} - {msg['content'][:200]}...")
            
            # Build response format schema
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": "ai_response_plan",
                    "schema": event.actions_schema
                }
            }
            
            # Log the schema being used
            logger.info(f"JsonCentricAI: Using JSON schema for {event.request_id}:")
            logger.info(f"JsonCentricAI: {json.dumps(event.actions_schema, indent=2)}")
            
            # Make request to Planner AI
            success, plan_json, error_msg = await self._make_openrouter_request(
                event.model_name,
                planning_messages,
                response_format=response_format
            )
            
            if success and plan_json:
                # Log the raw planning response
                logger.info(f"JsonCentricAI: Planning response for {event.request_id}:")
                logger.info(f"JsonCentricAI: Raw response: '{plan_json}'")
                logger.info(f"JsonCentricAI: Response length: {len(plan_json) if plan_json else 0}")
                logger.info(f"JsonCentricAI: Response type: {type(plan_json)}")
                
                try:
                    # Parse the JSON response - first strip any markdown formatting
                    clean_json = plan_json.strip()
                    if clean_json.startswith('```json'):
                        # Remove markdown code block formatting
                        clean_json = clean_json[7:]  # Remove ```json
                        if clean_json.endswith('```'):
                            clean_json = clean_json[:-3]  # Remove trailing ```
                        clean_json = clean_json.strip()
                    elif clean_json.startswith('```'):
                        # Remove generic code block formatting
                        clean_json = clean_json[3:]  # Remove ```
                        if clean_json.endswith('```'):
                            clean_json = clean_json[:-3]  # Remove trailing ```
                        clean_json = clean_json.strip()
                    
                    logger.info(f"JsonCentricAI: Cleaned JSON for parsing: '{clean_json[:100]}...'")
                    
                    plan_data = json.loads(clean_json)
                    logger.info(f"JsonCentricAI: Parsed JSON successfully: {plan_data}")
                    action_plan = AIResponsePlan(**plan_data)
                    
                    response_event = StructuredPlanningResponseEvent(
                        request_id=event.request_id,
                        success=True,
                        action_plan=action_plan,
                        original_request_payload={
                            "thoughts": [t.model_dump() for t in event.thoughts],
                            "model_name": event.model_name
                        }
                    )
                except json.JSONDecodeError as e:
                    logger.error(f"JsonCentricAI: Failed to parse planning response JSON: {e}")
                    logger.error(f"JsonCentricAI: Raw response that failed to parse: '{plan_json}'")
                    response_event = StructuredPlanningResponseEvent(
                        request_id=event.request_id,
                        success=False,
                        error_message=f"Invalid JSON response: {str(e)}"
                    )
            else:
                logger.error(f"JsonCentricAI: Planning API call failed for {event.request_id}: {error_msg}")
                response_event = StructuredPlanningResponseEvent(
                    request_id=event.request_id,
                    success=False,
                    error_message=error_msg or "Failed to generate action plan"
                )
            
            await self.bus.publish(response_event)
            
        except Exception as e:
            logger.error(f"JsonCentricAI: Error in planning request {event.request_id}: {e}")
            error_response = StructuredPlanningResponseEvent(
                request_id=event.request_id,
                success=False,
                error_message=str(e)
            )
            await self.bus.publish(error_response)
    
    async def _build_thinking_prompt(self, context_batch) -> List[Dict[str, Any]]:
        """Build the prompt for the Thinker AI using rich context from prompt constructor."""
        # Extract information for rich context building
        bot_display_name = getattr(context_batch, 'bot_display_name', 'AI Assistant')
        
        # Process each channel context to build comprehensive prompts
        messages_for_ai = []
        
        # For thinking phase, we want to analyze all channels together with full context
        if context_batch.channel_contexts:
            # Use the first channel's context as primary, but include info about all channels
            primary_context = context_batch.channel_contexts[0]
            
            # Extract user IDs from all channels for memory retrieval
            current_user_ids = []
            for context in context_batch.channel_contexts:
                if context.sender_id and context.sender_id not in current_user_ids:
                    current_user_ids.append(context.sender_id)
            
            # Get tool states for the primary channel (could be enhanced to handle multi-channel)
            tool_states = await database.get_tool_states(self.db_path, primary_context.channel_id)
            
            # Build historical messages - convert context message history to proper format
            historical_messages = []
            if hasattr(primary_context, 'message_history') and primary_context.message_history:
                for hist_msg in primary_context.message_history:
                    if isinstance(hist_msg, dict):
                        historical_messages.append(hist_msg)
                    else:
                        # Convert from object to dict if needed
                        historical_messages.append({
                            'role': getattr(hist_msg, 'role', 'user'),
                            'content': getattr(hist_msg, 'content', ''),
                            'name': getattr(hist_msg, 'name', None),
                            'tool_calls': getattr(hist_msg, 'tool_calls', None),
                            'tool_call_id': getattr(hist_msg, 'tool_call_id', None),
                            'image_url': getattr(hist_msg, 'image_url', None)
                        })
            
            # Build current batched user inputs from all channels
            current_batched_inputs = []
            for context in context_batch.channel_contexts:
                user_input = {
                    'content': str(context.current_user_input.get('content', '')) if isinstance(context.current_user_input, dict) else str(context.current_user_input),
                    'name': context.sender_id.split(':')[0].replace('@', '') if context.sender_id else 'user',
                    'event_id': context.current_user_input.get('event_id') if isinstance(context.current_user_input, dict) else None
                }
                
                # Add image URL if present
                if isinstance(context.current_user_input, dict) and 'image_url' in context.current_user_input:
                    user_input['image_url'] = context.current_user_input['image_url']
                
                current_batched_inputs.append(user_input)
            
            # Get the last user event ID for context
            last_user_event_id = None
            if current_batched_inputs and current_batched_inputs[-1].get('event_id'):
                last_user_event_id = current_batched_inputs[-1]['event_id']
            
            # Use the sophisticated prompt constructor to build the full context
            messages_for_ai = await prompt_constructor.build_messages_for_ai(
                historical_messages=historical_messages,
                current_batched_user_inputs=current_batched_inputs,
                bot_display_name=bot_display_name,
                db_path=self.db_path,
                channel_summary=primary_context.channel_summary,
                tool_states=tool_states,
                current_user_ids_in_context=current_user_ids,
                last_user_event_id_in_batch=last_user_event_id,
                include_system_prompt=True
            )
            
            # Now modify the system prompt to be thinking-focused instead of action-focused
            thinking_system_additions = f"""

IMPORTANT: You are in the THINKING phase of a two-step AI process.

Your task is to analyze the situation and generate detailed reasoning and understanding.
Do NOT take actions or output JSON - just provide clear, detailed reasoning in natural language.

For each channel context provided, explain:
1. What the user is asking for or the situation you're observing
2. What context clues are important (from history, summaries, memories, etc.)
3. What you think should be done and why
4. Any considerations or nuances to keep in mind

Available actions for your consideration:
{self.action_registry.get_action_descriptions_for_prompt()}

Be thorough in your reasoning but focus on actionable insights.
"""
            
            # Modify the first message (system prompt) to include thinking-specific instructions
            if messages_for_ai and messages_for_ai[0]['role'] == 'system':
                messages_for_ai[0]['content'] += thinking_system_additions
            else:
                # Fallback: prepend a thinking-focused system message
                messages_for_ai.insert(0, {
                    'role': 'system', 
                    'content': f"You are {bot_display_name}, an AI assistant in the thinking phase.{thinking_system_additions}"
                })
        
        else:
            # Fallback for empty context
            messages_for_ai = [{
                'role': 'system',
                'content': f"You are {bot_display_name}, an AI assistant analyzing user messages. No context provided."
            }]
        
        return messages_for_ai

    async def _build_planning_prompt(self, thoughts: List[AIThoughts], original_context) -> List[Dict[str, Any]]:
        """Build the prompt for the Planner AI using rich context from prompt constructor."""
        # Extract bot display name
        bot_display_name = getattr(original_context, 'bot_display_name', 'AI Assistant')
        
        # For planning phase, we still want the rich context but with planning focus
        messages_for_ai = []
        
        if original_context.channel_contexts:
            # Use the first channel's context as primary
            primary_context = original_context.channel_contexts[0]
            
            # Extract user IDs for memory retrieval
            current_user_ids = []
            for context in original_context.channel_contexts:
                if context.sender_id and context.sender_id not in current_user_ids:
                    current_user_ids.append(context.sender_id)
            
            # Get tool states for the channel
            tool_states = await database.get_tool_states(self.db_path, primary_context.channel_id)
            
            # Build historical messages
            historical_messages = []
            if hasattr(primary_context, 'message_history') and primary_context.message_history:
                for hist_msg in primary_context.message_history:
                    if isinstance(hist_msg, dict):
                        historical_messages.append(hist_msg)
                    else:
                        historical_messages.append({
                            'role': getattr(hist_msg, 'role', 'user'),
                            'content': getattr(hist_msg, 'content', ''),
                            'name': getattr(hist_msg, 'name', None),
                            'tool_calls': getattr(hist_msg, 'tool_calls', None),
                            'tool_call_id': getattr(hist_msg, 'tool_call_id', None),
                            'image_url': getattr(hist_msg, 'image_url', None)
                        })
            
            # Build current batched user inputs
            current_batched_inputs = []
            for context in original_context.channel_contexts:
                user_input = {
                    'content': str(context.current_user_input.get('content', '')) if isinstance(context.current_user_input, dict) else str(context.current_user_input),
                    'name': context.sender_id.split(':')[0].replace('@', '') if context.sender_id else 'user',
                    'event_id': context.current_user_input.get('event_id') if isinstance(context.current_user_input, dict) else None
                }
                
                if isinstance(context.current_user_input, dict) and 'image_url' in context.current_user_input:
                    user_input['image_url'] = context.current_user_input['image_url']
                
                current_batched_inputs.append(user_input)
            
            # Get the last user event ID
            last_user_event_id = None
            if current_batched_inputs and current_batched_inputs[-1].get('event_id'):
                last_user_event_id = current_batched_inputs[-1]['event_id']
            
            # Use prompt constructor for rich context
            messages_for_ai = await prompt_constructor.build_messages_for_ai(
                historical_messages=historical_messages,
                current_batched_user_inputs=current_batched_inputs,
                bot_display_name=bot_display_name,
                db_path=self.db_path,
                channel_summary=primary_context.channel_summary,
                tool_states=tool_states,
                current_user_ids_in_context=current_user_ids,
                last_user_event_id_in_batch=last_user_event_id,
                include_system_prompt=True
            )
            
            # Replace the system prompt with planning-specific instructions
            planning_system_prompt = f"""You are {bot_display_name}, an AI assistant that converts natural language reasoning into structured action plans.

Based on the provided 'AI Thought Process' and the original user context, generate a structured JSON action plan.

Available actions with REQUIRED parameters:
{self.action_registry.get_action_descriptions_for_prompt()}

CRITICAL: You MUST provide ALL required parameters for each action. Empty parameters {{}} will cause failures.

Examples of correct action usage:
- send_reply_text: {{"text": "Your actual reply message here"}}
- send_message_text: {{"text": "Your message content here"}}
- react_to_message: {{"event_id": "$actual_event_id", "emoji": "👍"}}
- do_not_respond: {{}} (no required parameters for this action)

You must respond with a JSON object that follows this exact structure:
{{
  "channel_responses": [
    {{
      "channel_id": "room_id_here",
      "actions": [
        {{
          "action_name": "action_name_here",
          "parameters": {{
            // REQUIRED: Fill in all required parameters for the chosen action
            // Example: "text": "Your actual message content here"
          }}
        }}
      ],
      "reasoning": "Optional explanation of your plan for this channel"
    }}
  ]
}}

IMPORTANT RULES:
1. Every action MUST include its required parameters with actual values
2. For text-based actions (send_reply_text, send_message_text), the "text" parameter must contain your actual response content
3. Never use empty parameters {{}} unless the action truly has no required parameters
4. If replying to a message, use send_reply_text with both "text" and optionally "reply_to_event_id"
5. If sending a new message, use send_message_text with "text"
6. Always include at least one action per channel, even if it's 'do_not_respond'

Translate the intentions and steps from the thought process into concrete actions with their required parameters filled in."""
            
            # Replace the system message with planning-focused one
            if messages_for_ai and messages_for_ai[0]['role'] == 'system':
                messages_for_ai[0] = {'role': 'system', 'content': planning_system_prompt}
            else:
                messages_for_ai.insert(0, {'role': 'system', 'content': planning_system_prompt})
        
        else:
            # Fallback for empty context
            messages_for_ai = [{
                'role': 'system',
                'content': f"You are {bot_display_name}, an AI assistant generating action plans. No context provided."
            }]
        
        # Add the AI thought process as the final user message
        thoughts_text = "AI Thought Process:\n\n"
        for thought in thoughts:
            thoughts_text += f"Channel {thought.channel_id}:\n{thought.thoughts_text}\n\n"
        
        thoughts_text += "Based on this analysis, generate the structured JSON action plan with all required parameters filled in."
        
        # Replace or add the final user message with thoughts
        messages_for_ai.append({
            'role': 'user',
            'content': thoughts_text
        })
        
        return messages_for_ai
    
    def _context_has_pdfs(self, context_batch) -> bool:
        """Check if any context contains PDF content."""
        for context in context_batch.channel_contexts:
            for content_item in context.content:
                if content_item.get("type") == "file" and "pdf" in content_item.get("file", {}).get("filename", "").lower():
                    return True
        return False
    
    def _parse_thinking_response(self, thoughts_text: str, context_batch) -> List[AIThoughts]:
        """Parse the natural language thoughts response into structured thoughts."""
        # For now, simple parsing - in production, could use more sophisticated NLP
        thoughts = []
        
        # Split by channel mentions or create one thought per channel
        if len(context_batch.channel_contexts) == 1:
            # Single channel case
            thoughts.append(AIThoughts(
                channel_id=context_batch.channel_contexts[0].channel_id,
                thoughts_text=thoughts_text
            ))
        else:
            # Multi-channel case - try to split the response
            # This is a simplified approach - could be more sophisticated
            lines = thoughts_text.split('\n')
            current_channel_id = None
            current_thoughts = []
            
            for line in lines:
                # Look for channel references
                for context in context_batch.channel_contexts:
                    if context.channel_id in line or f"Channel" in line:
                        if current_channel_id and current_thoughts:
                            thoughts.append(AIThoughts(
                                channel_id=current_channel_id,
                                thoughts_text='\n'.join(current_thoughts)
                            ))
                        current_channel_id = context.channel_id
                        current_thoughts = []
                        break
                
                if current_channel_id:
                    current_thoughts.append(line)
            
            # Add the last channel
            if current_channel_id and current_thoughts:
                thoughts.append(AIThoughts(
                    channel_id=current_channel_id,
                    thoughts_text='\n'.join(current_thoughts)
                ))
            
            # Fallback: if parsing failed, create one thought per channel with the full text
            if not thoughts:
                for context in context_batch.channel_contexts:
                    thoughts.append(AIThoughts(
                        channel_id=context.channel_id,
                        thoughts_text=thoughts_text
                    ))
        
        return thoughts
    
    async def run(self) -> None:
        """Main run loop for the service."""
        logger.info("JsonCentricAIService: Starting...")
        self.bus.subscribe(ThinkingRequestEvent.get_event_type(), self._handle_thinking_request)
        self.bus.subscribe(StructuredPlanningRequestEvent.get_event_type(), self._handle_structured_planning_request)
        await self._stop_event.wait()
        logger.info("JsonCentricAIService: Stopped.")
    
    async def stop(self) -> None:
        """Stop the service."""
        logger.info("JsonCentricAIService: Stop requested.")
        self._stop_event.set()