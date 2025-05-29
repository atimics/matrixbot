# Event-Driven AI Bot System

This is a rebuilt Matrix/Farcaster bot system with an event-driven architecture that responds to world state changes rather than continuous polling.

## Architecture

The system follows this pattern:
```
world_state_changes -> AI_decision -> action_execution -> world_state_update -> (repeat on changes)
```

### Core Components

1. **Event Orchestrator** (`event_orchestrator.py`) - Main coordination loop
2. **World State** (`world_state.py`) - Tracks messages, channels, and system state
3. **AI Engine** (`ai_engine.py`) - Makes decisions using OpenRouter API
4. **Action Executor** (`action_executor.py`) - Executes AI-selected actions
5. **Matrix Observer** (`matrix_observer.py`) - Monitors Matrix channels
6. **Farcaster Observer** (`farcaster_observer.py`) - Monitors Farcaster feeds

### Key Features

- **Event-driven**: Only acts when world state changes are detected
- **Rate limited**: Maximum 3 actions per cycle, configurable cycles per hour
- **Multi-platform**: Supports both Matrix and Farcaster
- **JSON-based**: Clean JSON in/JSON out communication with AI
- **Comprehensive logging**: Detailed logging throughout the system
- **Configurable**: Environment-based configuration

## Setup

1. Copy configuration:
   ```bash
   cp .env.example .env
   ```

2. Configure your settings in `.env`:
   - OpenRouter API key for AI decisions
   - Matrix credentials for bot account
   - Farcaster API key (optional, from Neynar)
   - Monitoring targets (Matrix rooms, Farcaster users/channels)

3. Install dependencies:
   ```bash
   pip install asyncio httpx python-dotenv
   ```

4. Run the system:
   ```bash
   python event_orchestrator.py
   ```

## Configuration

### Required Settings

- `OPENROUTER_API_KEY`: Your OpenRouter API key for AI decisions
- `MATRIX_HOMESERVER`: Matrix homeserver URL
- `MATRIX_USERNAME`: Bot's Matrix username
- `MATRIX_PASSWORD`: Bot's Matrix password

### Optional Settings

- `FARCASTER_API_KEY`: Neynar API key for Farcaster integration
- `FARCASTER_FIDS`: Comma-separated list of Farcaster user IDs to monitor
- `FARCASTER_CHANNELS`: Comma-separated list of Farcaster channels to monitor
- `OBSERVATION_INTERVAL`: How often to check for new messages (default: 30s)
- `MAX_CYCLES_PER_HOUR`: Rate limiting for AI decision cycles (default: 60)

## How It Works

1. **Observation**: The system periodically checks Matrix rooms and Farcaster feeds for new messages
2. **Change Detection**: When new messages arrive, the world state hash changes
3. **AI Decision**: The AI analyzes the current world state and selects up to 3 actions
4. **Action Execution**: Selected actions are executed (send messages, post content, etc.)
5. **State Update**: Action results are recorded in the world state
6. **Repeat**: The cycle continues when new changes are detected

### Available Actions

- `wait`: Do nothing, just observe
- `send_matrix_message`: Send a message to a Matrix room
- `send_matrix_reply`: Reply to a specific Matrix message
- `send_farcaster_post`: Post content to Farcaster
- `send_farcaster_reply`: Reply to a Farcaster cast

## Comparison with v1 System

The original v1 system (in `/v1/` directory) had several issues:
- Context persistence bugs causing infinite loops
- Complex thinking/planning phases
- Reactive message-based architecture
- Polling-based operation

This new system:
- Event-driven architecture
- Single AI decision phase (max 3 actions)
- Clean world state management
- Better error handling and rate limiting
- Structured separation of concerns

## Logging

The system provides comprehensive logging:
- Observation cycles and message detection
- AI decision making and reasoning
- Action execution results
- Error handling and recovery
- System status and health

## Development

To extend the system:

1. **Add new observers**: Implement new platform observers following the pattern
2. **Add new actions**: Add action types to the action executor
3. **Modify AI prompts**: Update the AI engine's system prompt for new behaviors
4. **Add triggers**: Implement clock-based or other event triggers

The system is designed to be modular and extensible while maintaining clean separation between observation, decision making, and action execution.
