# 📚 API Documentation

This document provides comprehensive API documentation for the chatbot system, including tool interfaces, configuration options, and integration guidelines.

## 📋 Table of Contents

- [Tool System API](#-tool-system-api)
- [World State API](#-world-state-api)
- [Configuration API](#-configuration-api)
- [Platform Integration API](#-platform-integration-api)
- [AI Engine API](#-ai-engine-api)
- [Control Panel API](#-control-panel-api)

## 🛠️ Tool System API

### ToolInterface

The base interface that all tools must implement for integration with the system.

```python
from abc import ABC, abstractmethod
from typing import Any, Dict
from chatbot.tools.base import ActionContext

class ToolInterface(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool identifier used by AI for tool selection."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Detailed description for AI prompt generation."""
        pass

    @property
    @abstractmethod
    def parameters_schema(self) -> Dict[str, Any]:
        """Parameter schema for validation and AI guidance."""
        pass

    @abstractmethod
    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """Execute tool with parameters and context."""
        pass
```

### ActionContext

Provides tools with access to system components and shared resources.

```python
class ActionContext:
    def __init__(
        self,
        matrix_observer=None,
        farcaster_observer=None,
        world_state_manager=None,
        context_manager=None,
    ):
        self.matrix_observer = matrix_observer
        self.farcaster_observer = farcaster_observer
        self.world_state_manager = world_state_manager
        self.context_manager = context_manager
```

#### Available Context Components

| Component | Type | Description |
|-----------|------|-------------|
| `matrix_observer` | MatrixObserver | Matrix platform integration |
| `farcaster_observer` | FarcasterObserver | Farcaster platform integration |
| `world_state_manager` | WorldStateManager | Central state management |
| `context_manager` | ContextManager | Conversation context |

### ToolRegistry

Manages tool registration and provides AI-ready tool descriptions.

```python
class ToolRegistry:
    def register_tool(self, tool: ToolInterface) -> None:
        """Register a tool for use by the system."""
        
    def get_tool(self, name: str) -> Optional[ToolInterface]:
        """Retrieve a tool by name."""
        
    def get_all_tools(self) -> List[ToolInterface]:
        """Get all registered tools."""
        
    def generate_ai_prompt_section(self) -> str:
        """Generate AI prompt section with tool descriptions."""
```

### Core Tools

#### WaitTool

Provides intelligent waiting and observation capabilities.

```python
{
    "name": "wait",
    "description": "Wait for a specified duration or until next observation cycle",
    "parameters_schema": {
        "seconds": "number (optional) - seconds to wait, defaults to observation interval"
    }
}
```

**Usage Example**:
```json
{
    "tool": "wait",
    "parameters": {
        "seconds": 5.0
    }
}
```

#### ObserveTool

Provides world state observation and reporting.

```python
{
    "name": "observe",
    "description": "Observe current world state and recent activities",
    "parameters_schema": {
        "lookback_seconds": "number (optional) - how far back to look for activities"
    }
}
```

### Matrix Tools

#### SendMatrixMessageTool

Send messages to Matrix rooms.

```python
{
    "name": "send_matrix_message",
    "description": "Send a message to a Matrix room",
    "parameters_schema": {
        "room_id": "string - Matrix room ID (!room:server.com)",
        "content": "string - message content to send",
        "format": "string (optional) - 'markdown' or 'html', defaults to 'markdown'"
    }
}
```

#### SendMatrixReplyTool

Reply to specific Matrix messages.

```python
{
    "name": "send_matrix_reply",
    "description": "Reply to a specific message in Matrix",
    "parameters_schema": {
        "room_id": "string - Matrix room ID",
        "content": "string - reply content",
        "reply_to_event_id": "string - event ID to reply to"
    }
}
```

#### JoinMatrixRoomTool

Join Matrix rooms and accept invitations.

```python
{
    "name": "join_matrix_room",
    "description": "Join a Matrix room or accept an invitation",
    "parameters_schema": {
        "room_id": "string - Matrix room ID to join"
    }
}
```

### Farcaster Tools

#### SendFarcasterPostTool

Create new Farcaster posts.

```python
{
    "name": "send_farcaster_post",
    "description": "Send a new post to Farcaster",
    "parameters_schema": {
        "content": "string - post content (max 320 characters)",
        "embeds": "array (optional) - URLs to embed",
        "channel": "string (optional) - channel to post in"
    }
}
```

#### SendFarcasterReplyTool

Reply to Farcaster casts.

```python
{
    "name": "send_farcaster_reply",
    "description": "Reply to a Farcaster cast",
    "parameters_schema": {
        "content": "string - reply content",
        "reply_to_hash": "string - hash of cast to reply to"
    }
}
```

#### LikeFarcasterPostTool

Like Farcaster casts.

```python
{
    "name": "like_farcaster_post",
    "description": "Like a Farcaster cast",
    "parameters_schema": {
        "cast_hash": "string - hash of cast to like"
    }
}
```

#### QuoteFarcasterPostTool

Quote Farcaster casts with additional commentary.

```python
{
    "name": "quote_farcaster_post",
    "description": "Quote a Farcaster cast with commentary",
    "parameters_schema": {
        "content": "string - your commentary on the quoted cast",
        "quoted_cast_hash": "string - hash of cast to quote"
    }
}
```

#### FollowFarcasterUserTool

Follow Farcaster users.

```python
{
    "name": "follow_farcaster_user",
    "description": "Follow a user on Farcaster",
    "parameters_schema": {
        "fid": "number - Farcaster ID of user to follow"
    }
}
```

#### SendFarcasterDirectMessageTool

Send direct messages on Farcaster.

```python
{
    "name": "send_farcaster_direct_message",
    "description": "Send a direct message to a Farcaster user",
    "parameters_schema": {
        "recipient_fid": "number - Farcaster ID of recipient",
        "content": "string - message content"
    }
}
```

## 🌍 World State API

### WorldStateManager

Central interface for world state management and querying.

```python
class WorldStateManager:
    def add_message(self, channel_id: str, message: Message) -> None:
        """Add a new message to the world state."""
        
    def add_action_result(
        self, 
        action_type: str, 
        parameters: Dict[str, Any], 
        result: str, 
        action_id: Optional[str] = None
    ) -> str:
        """Record an action result and return action ID."""
        
    def update_action_result(
        self, 
        action_id: str, 
        new_result: str, 
        cast_hash: Optional[str] = None
    ) -> bool:
        """Update an existing action result."""
        
    def get_ai_optimized_payload(
        self, 
        primary_channel_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get optimized world state for AI consumption."""
        
    def has_replied_to_cast(self, cast_hash: str) -> bool:
        """Check if bot has already replied to a cast."""
        
    def has_liked_cast(self, cast_hash: str) -> bool:
        """Check if bot has already liked a cast."""
        
    def add_pending_matrix_invite(self, invite_info: Dict[str, Any]) -> None:
        """Add a pending Matrix invitation."""
        
    def remove_pending_matrix_invite(self, room_id: str) -> bool:
        """Remove a pending Matrix invitation."""
```

### Message Model

Unified message representation across platforms.

```python
@dataclass
class Message:
    # Core message data
    id: str                                    # Unique message identifier
    channel_id: str                           # Channel/room identifier
    channel_type: str                         # 'matrix' or 'farcaster'
    sender: str                               # Sender display name
    content: str                              # Message content
    timestamp: float                          # Unix timestamp
    reply_to: Optional[str] = None            # ID of message being replied to
    
    # Enhanced user information
    sender_username: Optional[str] = None     # Platform username
    sender_display_name: Optional[str] = None # Display name
    sender_fid: Optional[int] = None          # Farcaster ID
    sender_pfp_url: Optional[str] = None      # Profile picture URL
    sender_bio: Optional[str] = None          # User bio
    sender_follower_count: Optional[int] = None   # Follower count
    sender_following_count: Optional[int] = None  # Following count
    
    # Platform-specific metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_ai_summary_dict(self) -> Dict[str, Any]:
        """Return optimized version for AI consumption."""
        
    def is_from_bot(
        self, 
        bot_fid: Optional[str] = None, 
        bot_username: Optional[str] = None
    ) -> bool:
        """Check if message is from the bot."""
```

### Channel Model

Comprehensive channel/room representation.

```python
@dataclass
class Channel:
    # Core channel data
    id: str                                   # Channel identifier
    type: str                                 # Platform type
    name: str                                 # Channel name
    recent_messages: List[Message]            # Recent messages
    last_checked: float                       # Last observation time
    
    # Matrix-specific attributes
    canonical_alias: Optional[str] = None     # Primary alias
    alt_aliases: List[str] = field(default_factory=list)
    topic: Optional[str] = None               # Channel topic
    avatar_url: Optional[str] = None          # Channel avatar
    member_count: int = 0                     # Member count
    encrypted: bool = False                   # Encryption status
    public: bool = True                       # Public accessibility
    power_levels: Dict[str, int] = field(default_factory=dict)
    creation_time: Optional[float] = None     # Creation timestamp
    
    def get_activity_summary(self) -> Dict[str, Any]:
        """Get comprehensive activity analysis."""
```

## ⚙️ Configuration API

### AppConfig

Centralized configuration management using Pydantic settings.

```python
class AppConfig(BaseSettings):
    # Core system settings
    CHATBOT_DB_PATH: str = "chatbot.db"
    OBSERVATION_INTERVAL: float = 2.0
    MAX_CYCLES_PER_HOUR: int = 300
    LOG_LEVEL: str = "INFO"
    
    # AI configuration
    AI_MODEL: str = "openai/gpt-4o-mini"
    OPENROUTER_API_KEY: str
    PRIMARY_LLM_PROVIDER: str = "openrouter"
    
    # Matrix configuration
    MATRIX_HOMESERVER: str
    MATRIX_USER_ID: str
    MATRIX_PASSWORD: str
    MATRIX_ROOM_ID: str
    MATRIX_DEVICE_ID: Optional[str] = None
    DEVICE_NAME: str = "ratichat_bot"
    
    # Farcaster configuration
    NEYNAR_API_KEY: Optional[str] = None
    FARCASTER_BOT_FID: Optional[str] = None
    FARCASTER_BOT_SIGNER_UUID: Optional[str] = None
    FARCASTER_BOT_USERNAME: Optional[str] = None
    
    # AI optimization settings
    AI_CONVERSATION_HISTORY_LENGTH: int = 10
    AI_ACTION_HISTORY_LENGTH: int = 5
    AI_THREAD_HISTORY_LENGTH: int = 5
    AI_OTHER_CHANNELS_SUMMARY_COUNT: int = 3
    AI_OTHER_CHANNELS_MESSAGE_SNIPPET_LENGTH: int = 75
    AI_INCLUDE_DETAILED_USER_INFO: bool = True
```

### Configuration Usage

```python
from chatbot.config import settings

# Access configuration values
db_path = settings.CHATBOT_DB_PATH
ai_model = settings.AI_MODEL
matrix_homeserver = settings.MATRIX_HOMESERVER

# Override via environment variables
import os
os.environ['AI_MODEL'] = 'openai/gpt-4'
```

## 🌐 Platform Integration API

### Observer Interface

Base interface for platform observers.

```python
class Observer(ABC):
    @abstractmethod
    async def start(self) -> None:
        """Start observing platform events."""
        
    @abstractmethod
    async def stop(self) -> None:
        """Stop observing platform events."""
        
    @abstractmethod
    async def get_recent_messages(self, limit: int = 50) -> List[Message]:
        """Get recent messages from the platform."""
        
    @abstractmethod
    async def send_message(self, channel_id: str, content: str) -> Dict[str, Any]:
        """Send a message to the platform."""
```

### Matrix Integration

#### MatrixObserver

```python
class MatrixObserver:
    async def start(self) -> None:
        """Initialize Matrix client and start sync."""
        
    async def stop(self) -> None:
        """Stop Matrix client and cleanup."""
        
    async def send_message(
        self, 
        room_id: str, 
        content: str, 
        msgtype: str = "m.text"
    ) -> Dict[str, Any]:
        """Send message to Matrix room."""
        
    async def reply_to_message(
        self, 
        room_id: str, 
        content: str, 
        reply_to_event_id: str
    ) -> Dict[str, Any]:
        """Reply to specific Matrix message."""
        
    async def join_room(self, room_id: str) -> Dict[str, Any]:
        """Join Matrix room."""
        
    async def accept_invite(self, room_id: str) -> Dict[str, Any]:
        """Accept Matrix room invitation."""
```

### Farcaster Integration

#### FarcasterObserver

```python
class FarcasterObserver:
    async def start(self) -> None:
        """Start Farcaster feed monitoring."""
        
    async def stop(self) -> None:
        """Stop Farcaster monitoring."""
        
    async def send_cast(
        self, 
        content: str, 
        embeds: Optional[List[str]] = None,
        channel: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send new Farcaster cast."""
        
    async def reply_to_cast(
        self, 
        content: str, 
        reply_to_hash: str
    ) -> Dict[str, Any]:
        """Reply to Farcaster cast."""
        
    async def like_cast(self, cast_hash: str) -> Dict[str, Any]:
        """Like a Farcaster cast."""
        
    async def follow_user(self, fid: int) -> Dict[str, Any]:
        """Follow a Farcaster user."""
        
    async def send_direct_message(
        self, 
        recipient_fid: int, 
        content: str
    ) -> Dict[str, Any]:
        """Send direct message."""
```

## 🤖 AI Engine API

### AIEngine

Core AI integration and decision-making interface.

```python
class AIEngine:
    async def make_decision(
        self, 
        world_state_payload: Dict[str, Any], 
        available_tools: List[str]
    ) -> Dict[str, Any]:
        """Make AI decision based on world state."""
        
    def build_prompt(
        self, 
        world_state: Dict[str, Any], 
        tools_description: str
    ) -> str:
        """Build AI prompt with context and tools."""
        
    async def call_ai_api(self, prompt: str) -> str:
        """Call AI API with prompt."""
        
    def parse_ai_response(self, response: str) -> Dict[str, Any]:
        """Parse AI response into structured data."""
```

### AI Response Format

The AI engine expects responses in the following JSON format:

```json
{
    "reasoning": "Explanation of the decision-making process",
    "action": {
        "tool": "tool_name",
        "parameters": {
            "param1": "value1",
            "param2": "value2"
        }
    }
}
```

#### Example AI Response

```json
{
    "reasoning": "User asked about the weather, but I should wait to see if there are any new messages first",
    "action": {
        "tool": "wait",
        "parameters": {
            "seconds": 2.0
        }
    }
}
```

## 🎛️ Control Panel API

### Control Panel Endpoints

The control panel provides a web interface for monitoring and managing the bot.

#### GET /

Returns the main dashboard with current system status.

**Response**:
```html
<!DOCTYPE html>
<html>
<!-- Dashboard HTML -->
</html>
```

#### GET /api/status

Returns current system status as JSON.

**Response**:
```json
{
    "status": "running",
    "uptime": 3600,
    "platforms": {
        "matrix": {"connected": true, "rooms": 5},
        "farcaster": {"connected": true, "channels": 3}
    },
    "world_state": {
        "messages": 150,
        "actions": 25,
        "channels": 8
    }
}
```

#### GET /api/recent_activity

Returns recent bot activity.

**Response**:
```json
{
    "recent_messages": [...],
    "recent_actions": [...],
    "last_update": 1640995200
}
```

#### GET /api/configuration

Returns current configuration (sensitive values masked).

**Response**:
```json
{
    "AI_MODEL": "openai/gpt-4o-mini",
    "OBSERVATION_INTERVAL": 2.0,
    "MATRIX_HOMESERVER": "https://matrix.org",
    "OPENROUTER_API_KEY": "***masked***"
}
```

## 🔧 Error Handling

### Standard Error Response Format

All APIs use a consistent error response format:

```json
{
    "status": "error",
    "error": "Error message",
    "timestamp": 1640995200,
    "details": {
        "error_code": "INVALID_PARAMETER",
        "parameter": "room_id",
        "expected": "string in format !room:server.com"
    }
}
```

### Common Error Codes

| Code | Description | Resolution |
|------|-------------|------------|
| `INVALID_PARAMETER` | Parameter validation failed | Check parameter format and type |
| `TOOL_NOT_FOUND` | Requested tool not registered | Verify tool name and registration |
| `PLATFORM_ERROR` | Platform API error | Check platform connectivity and credentials |
| `RATE_LIMITED` | Rate limit exceeded | Wait for rate limit reset |
| `AUTHENTICATION_ERROR` | Authentication failed | Verify credentials and permissions |

## 📊 Response Standards

### Success Response Format

```json
{
    "status": "success",
    "message": "Action completed successfully",
    "timestamp": 1640995200,
    "data": {
        // Action-specific response data
    }
}
```

### Async Operation Response

For operations that may take time:

```json
{
    "status": "accepted",
    "message": "Action scheduled for execution",
    "action_id": "action_12345",
    "timestamp": 1640995200
}
```

## 🔄 Versioning

The API follows semantic versioning:

- **Major version**: Breaking changes to APIs
- **Minor version**: New features, backwards compatible
- **Patch version**: Bug fixes and security updates

Current API version: `1.0.0`

## 📝 Best Practices

### Tool Development

1. **Validation**: Always validate parameters before execution
2. **Error Handling**: Provide meaningful error messages
3. **Idempotency**: Make tools idempotent where possible
4. **Documentation**: Include comprehensive parameter descriptions
5. **Testing**: Write comprehensive tests for all tools

### Platform Integration

1. **Rate Limiting**: Respect platform rate limits
2. **Error Recovery**: Implement robust error recovery
3. **Authentication**: Securely handle credentials
4. **State Management**: Properly update world state
5. **Logging**: Include detailed logging for debugging

### AI Integration

1. **Prompt Engineering**: Design clear, specific prompts
2. **Response Parsing**: Implement robust JSON parsing
3. **Fallback Strategies**: Handle AI failures gracefully
4. **Context Management**: Optimize context for token efficiency
5. **Tool Awareness**: Keep tool descriptions current and accurate

This API documentation provides the foundation for extending and integrating with the chatbot system. For specific implementation examples, refer to the existing tool implementations in the codebase.
