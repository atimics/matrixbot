# JSON-Centric AI Orchestration System

This document describes the new JSON-centric AI orchestration system that replaces the previous tool-calling approach with structured prompting and two-step AI processing.

## Architecture Overview

The system uses a two-step AI processing approach:

1. **Thinker AI**: Analyzes user context and generates natural language reasoning
2. **Planner AI**: Converts reasoning into structured JSON action plans  
3. **Action Executor**: Executes the planned actions

## Key Components

### Core Services

- **ActionRegistryService**: Manages action definitions and JSON schemas
- **JsonCentricAIService**: Handles two-step AI processing (Thinking + Planning)
- **ActionExecutionService**: Executes structured actions from AI plans
- **JsonCentricRoomLogicService**: Orchestrates the complete workflow
- **JsonCentricOrchestrator**: Main coordinator for all services

### Action Registry (`actions_registry.json`)

Defines all available actions the AI can take:

```json
{
  "actions": {
    "send_reply_text": {
      "description_for_ai": "Send a text reply to a message in the channel",
      "parameters_json_schema": {
        "type": "object",
        "properties": {
          "text": {"type": "string"},
          "reply_to_event_id": {"type": "string"}
        },
        "required": ["text"]
      }
    }
  }
}
```

## Workflow

### 1. Message Processing

When a user sends a message:

1. **MatrixGatewayService** receives the message
2. **JsonCentricRoomLogicService** batches messages and builds channel context
3. Context includes:
   - Current user input (with images/PDFs in OpenRouter format)
   - Message history
   - Channel summary
   - User memories

### 2. Two-Step AI Processing

**Step 1: Thinking**
- System sends context to "Thinker" AI (e.g., Claude Haiku)
- AI analyzes situation and generates natural language reasoning
- No structured output required - just detailed thinking

**Step 2: Planning**
- System sends thoughts + context to "Planner" AI (e.g., GPT-4)
- AI converts reasoning into structured JSON action plan
- Uses `response_format.json_schema` to enforce structure

### 3. Action Execution

- **ActionExecutionService** receives the structured plan
- Validates actions against registry
- Executes each action (send messages, create memories, etc.)
- Updates conversation memory

## Configuration

### Environment Variables

```bash
# AI Models for two-step processing
THINKER_MODEL=anthropic/claude-3-haiku    # Fast, cheap model for reasoning
PLANNER_MODEL=openai/gpt-4o               # Precise model for structured output

# OpenRouter Configuration
OPENROUTER_API_KEY=your_api_key
YOUR_SITE_URL=https://your-site.com
YOUR_SITE_NAME=YourBotName

# System Configuration
DATABASE_PATH=matrix_bot_soa.db
MESSAGE_BATCH_DELAY=3.0
MAX_MESSAGES_PER_ROOM_MEMORY_ITEMS=20
```

## Running the System

### Start the JSON-Centric System

```bash
python json_centric_orchestrator.py
```

### Legacy System (for comparison)

```bash
python main_orchestrator.py
```

## Image and PDF Handling

The system leverages OpenRouter's native multimodal capabilities:

### Images
- Matrix `mxc://` URLs are converted to S3 URLs or base64 data URIs
- Included in context as `{"type": "image_url", "image_url": {"url": "..."}}`
- AI can analyze and describe images naturally

### PDFs
- Converted to base64 data URIs: `data:application/pdf;base64,...`
- Uses OpenRouter plugins (`pdf-text` or `mistral-ocr`) for parsing
- PDF annotations cached to avoid re-parsing costs

## Action Types

### Communication Actions
- `send_reply_text`: Reply to a specific message
- `send_message`: Send a regular message
- `react_to_message`: Add emoji reaction

### Memory Actions
- `create_user_memory`: Store information about users
- `manage_channel_summary`: Update channel summaries

### Control Actions
- `do_not_respond`: Take no action
- `describe_image`: Analyze shared images

## Benefits vs Tool Calling

### Advantages
1. **Model Specialization**: Use cheaper models for reasoning, precise models for structure
2. **Better Image/PDF Support**: Native OpenRouter multimodal capabilities
3. **Clearer AI Intent**: Explicit reasoning before action planning
4. **Multi-Channel Ready**: Can process multiple channels simultaneously
5. **Strongly Typed**: JSON schema validation prevents malformed responses

### Trade-offs
- **Increased Latency**: Two AI calls instead of one
- **Complexity**: More moving parts and state management
- **Cost**: Potentially higher token usage (though offset by model tiering)

## Extending the System

### Adding New Actions

1. Add action definition to `actions_registry.json`
2. Implement execution logic in `ActionExecutionService._execute_specific_action()`
3. Action becomes available to AI automatically

### Custom AI Models

Configure different models for thinking vs planning:

```python
# In JsonCentricRoomLogicService
self.thinker_model = "anthropic/claude-3-haiku"      # Fast reasoning
self.planner_model = "openai/gpt-4o"                 # Precise structuring
```

## Monitoring and Debugging

### Logging
- Each step logs its progress with request IDs
- AI reasoning is captured for debugging
- Action execution results are tracked

### Key Log Messages
```
JsonCentricRLS: [room_id] Processing batch with N messages
JsonCentricRLS: [room_id] Sent thinking request <id>
JsonCentricRLS: [room_id] Received thinking response, proceeding to planning
JsonCentricRLS: [room_id] Sent planning request <id>
JsonCentricRLS: [room_id] Received action plan, executing actions
ActionExecution: Successfully executed action_name for room_id
```

## Migration from Tool Calling

The new system is designed to coexist with the existing tool-calling system:

1. **Actions map to Tools**: Most existing tools can become actions
2. **Context Preservation**: User memories and summaries are maintained
3. **Database Compatibility**: Uses the same database schema
4. **Gradual Migration**: Can run both systems and compare results

## Future Enhancements

- **Multi-Channel Batching**: Process multiple rooms simultaneously
- **PDF Annotation Caching**: Persistent storage of PDF analysis results
- **Action Composition**: Complex workflows combining multiple actions
- **Streaming Responses**: Progressive action execution with user feedback