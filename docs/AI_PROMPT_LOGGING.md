# Enhanced AI Prompt Logging

This document describes the enhanced AI prompt logging features for better analysis and optimization of OpenRouter API calls.

## Features

### 1. Configurable Prompt Logging

New environment variables in `.env`:

```bash
# AI Debugging and Analysis
AI_ENABLE_PROMPT_LOGGING=true      # Enable detailed prompt logging for analysis
AI_LOG_FULL_PROMPTS=false          # Log full prompts and responses (very verbose)
AI_LOG_TOKEN_USAGE=true            # Log token usage and cost estimation
AI_LOG_PROMPT_PREVIEW_LENGTH=200   # Length of prompt previews when full logging is disabled
```

### 2. Enhanced Log Output

When `AI_ENABLE_PROMPT_LOGGING=true`, you'll see logs like:

```
AIDecisionEngine: Sending payload of size ~11.77 KB (12,057 bytes)
AIDecisionEngine: Prompt breakdown - System: 10.47 KB, User: 0.85 KB
AIDecisionEngine: Received response for cycle test_cycle_001
AIDecisionEngine: Response size: 1.25 KB (1,277 bytes)
AIDecisionEngine: Token usage - Prompt: 2,388, Completion: 531, Total: 2,919
AIDecisionEngine: Estimated cost: $0.039810
```

### 3. API Endpoints for Analysis

#### `/api/ai/prompt/analysis`
Analyzes current AI prompt payload sizes and provides optimization insights:

```json
{
  "analysis": {
    "total_payload_size_kb": 11.77,
    "total_payload_size_bytes": 12057,
    "system_prompt_size_kb": 10.47,
    "user_prompt_size_kb": 0.85,
    "model": "openrouter/auto"
  },
  "configuration": {
    "ai_conversation_history_length": 3,
    "ai_action_history_length": 2,
    "ai_thread_history_length": 2,
    "ai_context_token_threshold": 8000,
    "ai_enable_prompt_logging": true,
    "ai_log_full_prompts": false,
    "ai_log_token_usage": true
  },
  "recommendations": [
    "Enable AI_ENABLE_PROMPT_LOGGING for better debugging."
  ],
  "payload_thresholds": {
    "warning_kb": 200,
    "critical_kb": 300,
    "openrouter_limit_estimate_kb": 512
  }
}
```

#### `/api/ai/logging/config`
Get current AI logging configuration:

```json
{
  "config": {
    "ai_enable_prompt_logging": true,
    "ai_log_full_prompts": false,
    "ai_log_token_usage": true,
    "ai_log_prompt_preview_length": 200,
    "log_level": "INFO"
  },
  "description": {
    "ai_enable_prompt_logging": "Enable detailed prompt size and breakdown logging",
    "ai_log_full_prompts": "Log complete prompts and responses (very verbose)",
    "ai_log_token_usage": "Log token usage and cost estimation",
    "ai_log_prompt_preview_length": "Length of prompt previews when full logging is disabled"
  }
}
```

## Usage

### Basic Monitoring
Set `AI_ENABLE_PROMPT_LOGGING=true` to get payload size information in logs.

### Detailed Analysis
- Set `AI_LOG_TOKEN_USAGE=true` to track token usage and costs
- Set `AI_LOG_FULL_PROMPTS=true` for complete prompt/response logging (very verbose)
- Adjust `AI_LOG_PROMPT_PREVIEW_LENGTH` to control preview length

### API Monitoring
Use the `/api/ai/prompt/analysis` endpoint to get real-time payload analysis and optimization recommendations.

## Optimization Recommendations

The system will automatically provide recommendations based on payload size:

- **>200KB**: Consider reducing `AI_CONVERSATION_HISTORY_LENGTH`
- **>300KB**: Reduce `AI_ACTION_HISTORY_LENGTH` and `AI_THREAD_HISTORY_LENGTH`
- **System prompt >50KB**: Optimize prompt sections
- **Missing logging**: Enable `AI_ENABLE_PROMPT_LOGGING` for debugging

## Testing

Run the test script to verify logging functionality:

```bash
python test_enhanced_logging.py
```

Test the API endpoints:

```bash
python test_api_endpoints.py
```

## Cost Estimation

The logging includes rough cost estimation based on token usage:
- Prompt tokens: ~$0.00001 per token
- Completion tokens: ~$0.00003 per token

These are estimates and actual costs may vary based on the specific model and OpenRouter pricing.
