"""
Enhanced configuration system with secure secret management.

This module implements the refactored configuration architecture recommended
in the engineering report, breaking down the monolithic config into smaller,
context-specific models and implementing secure secret management.
"""

import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import json


class CoreConfig(BaseModel):
    """Core system configuration."""
    db_path: str = Field(default="data/chatbot.db", description="SQLite database path")
    log_level: str = Field(default="INFO", description="Logging level")
    observation_interval: float = Field(default=2.0, description="Observation cycle interval in seconds")
    max_cycles_per_hour: int = Field(default=300, description="Maximum observation cycles per hour")
    max_actions_per_hour: int = Field(default=600, description="Maximum actions per hour")
    device_name: str = Field(default="ratichat_bot", description="Device identifier")
    
    @validator('log_level')
    def validate_log_level(cls, v):
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f'Log level must be one of {valid_levels}')
        return v.upper()
    
    @validator('observation_interval')
    def validate_observation_interval(cls, v):
        if v <= 0:
            raise ValueError('Observation interval must be positive')
        return v


class AIConfig(BaseModel):
    """AI service configuration."""
    primary_model: str = Field(default="openai/gpt-4o-mini", description="Primary AI model")
    multimodal_model: str = Field(default="openai/gpt-4o", description="Multimodal AI model")
    web_search_model: str = Field(default="openai/gpt-4o-mini:online", description="Web search model")
    summary_model: str = Field(default="openai/gpt-4o-mini", description="Summary generation model")
    
    # Payload optimization settings
    conversation_history_length: int = Field(default=3, description="Max messages per channel for AI payload")
    action_history_length: int = Field(default=15, description="Max actions in history for AI payload")
    thread_history_length: int = Field(default=2, description="Max thread messages for AI payload")
    context_token_threshold: int = Field(default=8000, description="Token threshold for context switching")
    
    # Analysis and debugging
    enable_prompt_logging: bool = Field(default=True, description="Enable detailed prompt logging")
    log_full_prompts: bool = Field(default=False, description="Log full prompts and responses")
    log_token_usage: bool = Field(default=True, description="Log token usage and cost estimation")
    dump_payloads_to_file: bool = Field(default=False, description="Write payloads to files for analysis")
    payload_dump_directory: str = Field(default="data/payload_dumps", description="Directory for payload dumps")
    
    @validator('conversation_history_length', 'action_history_length', 'thread_history_length')
    def validate_history_lengths(cls, v):
        if v < 1:
            raise ValueError('History length must be at least 1')
        return v


class MatrixConfig(BaseModel):
    """Matrix platform configuration."""
    homeserver: Optional[str] = Field(default=None, description="Matrix homeserver URL")
    user_id: Optional[str] = Field(default=None, description="Matrix user ID")
    room_id: str = Field(default="#robot-laboratory:chat.ratimics.com", description="Default Matrix room ID")
    device_id: Optional[str] = Field(default=None, description="Matrix device ID")
    media_gallery_room_id: Optional[str] = Field(default=None, description="Media gallery room ID")
    
    @validator('homeserver')
    def validate_homeserver(cls, v):
        if v and not (v.startswith('http://') or v.startswith('https://')):
            raise ValueError('Homeserver URL must start with http:// or https://')
        return v
    
    @validator('user_id')
    def validate_user_id(cls, v):
        if v and not v.startswith('@'):
            raise ValueError('Matrix user ID must start with @')
        if v and ':' not in v:
            raise ValueError('Matrix user ID must include homeserver domain')
        return v
    
    @validator('room_id')
    def validate_room_id(cls, v):
        if v and not (v.startswith('!') or v.startswith('#')):
            raise ValueError('Matrix room ID must start with ! or #')
        return v


class FarcasterConfig(BaseModel):
    """Farcaster platform configuration."""
    bot_fid: Optional[str] = Field(default=None, description="Farcaster bot FID")
    bot_signer_uuid: Optional[str] = Field(default=None, description="Farcaster signer UUID")
    bot_username: Optional[str] = Field(default=None, description="Bot username for filtering")
    
    # Rate limiting and context
    min_post_interval_minutes: int = Field(default=1, description="Minimum minutes between posts")
    duplicate_check_hours: int = Field(default=1, description="Hours to look back for duplicate content")
    recent_posts_limit: int = Field(default=10, description="Number of recent posts to fetch")
    
    # Network configuration
    api_base_url: Optional[str] = Field(default=None, description="Override default Neynar API base URL")
    api_timeout: float = Field(default=30.0, description="API request timeout in seconds")
    api_max_retries: int = Field(default=3, description="Maximum retry attempts for failed requests")
    api_base_delay: float = Field(default=1.0, description="Base delay for exponential backoff")
    api_max_delay: float = Field(default=60.0, description="Maximum delay between retries")
    
    @validator('min_post_interval_minutes', 'duplicate_check_hours', 'recent_posts_limit')
    def validate_positive_integers(cls, v):
        if v < 0:
            raise ValueError('Value must be non-negative')
        return v


class MediaConfig(BaseModel):
    """Media generation and storage configuration."""
    # Generation settings
    image_generation_cooldown_seconds: int = Field(default=120, description="Image generation cooldown")
    video_generation_cooldown_seconds: int = Field(default=600, description="Video generation cooldown")
    max_image_generations_per_hour: int = Field(default=15, description="Max images per hour")
    max_video_generations_per_hour: int = Field(default=5, description="Max videos per hour")
    
    # Replicate configuration
    replicate_image_model: str = Field(default="stability-ai/sdxl", description="Replicate image model")
    replicate_lora_scale: Optional[float] = Field(default=0.75, description="LoRA scale for image generation")
    
    # Google AI configuration
    google_gemini_image_model: str = Field(default="gemini-1.5-flash-latest", description="Google Gemini image model")
    google_veo_video_model: str = Field(default="models/veo-experimental-v1", description="Google Veo video model")
    
    # Storage configuration
    arweave_gateway_url: str = Field(default="https://arweave.net", description="Arweave gateway URL")
    arweave_uploader_service_url: str = Field(default="http://arweave-uploader:8001", description="Internal uploader service URL")
    use_s3_for_media: bool = Field(default=True, description="Use S3 as primary media storage")
    s3_upload_timeout: float = Field(default=120.0, description="S3 upload timeout in seconds")
    
    # Archival settings
    popular_media_archival_threshold_likes: int = Field(default=5, description="Likes threshold for archival")
    popular_media_archival_interval_minutes: int = Field(default=30, description="Archival check interval")


class SecurityConfig(BaseModel):
    """Security and authentication configuration."""
    # API security
    api_cors_origins: List[str] = Field(default=["http://localhost:3000"], description="Allowed CORS origins")
    api_key_header: str = Field(default="X-API-Key", description="API key header name")
    
    # Frame server security
    frames_webhook_secret: Optional[str] = Field(default=None, description="Webhook secret for frame validation")
    
    # Rate limiting
    rate_limit_requests_per_minute: int = Field(default=60, description="API rate limit per minute")
    rate_limit_burst_size: int = Field(default=10, description="Rate limit burst size")


class PerformanceConfig(BaseModel):
    """Performance and resource limits configuration."""
    # Node processing
    max_expanded_nodes: int = Field(default=8, description="Maximum simultaneously expanded nodes")
    enable_two_phase_ai_process: bool = Field(default=False, description="Enable exploration/action phases")
    max_exploration_rounds: int = Field(default=3, description="Max exploration rounds if two-phase enabled")
    
    # Memory management
    store_memory_cooldown_seconds: int = Field(default=60, description="Memory storage cooldown")
    max_memories_stored_per_hour: int = Field(default=30, description="Max memories stored per hour")
    
    # Default pinned nodes
    default_pinned_nodes: List[str] = Field(
        default=[
            "channels.matrix.primary",
            "system.notifications",
            "system.rate_limits"
        ],
        description="Default pinned nodes"
    )


class UnifiedSettings(BaseSettings):
    """Unified settings composed of all configuration sections."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True
    )
    
    # Configuration sections
    core: CoreConfig = Field(default_factory=CoreConfig)
    ai: AIConfig = Field(default_factory=AIConfig)
    matrix: MatrixConfig = Field(default_factory=MatrixConfig)
    farcaster: FarcasterConfig = Field(default_factory=FarcasterConfig)
    media: MediaConfig = Field(default_factory=MediaConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    performance: PerformanceConfig = Field(default_factory=PerformanceConfig)
    
    # Secrets (loaded from environment or secret management)
    openrouter_api_key: Optional[str] = Field(default=None, description="OpenRouter API key")
    matrix_password: Optional[str] = Field(default=None, description="Matrix password")
    neynar_api_key: Optional[str] = Field(default=None, description="Neynar API key")
    replicate_api_token: Optional[str] = Field(default=None, description="Replicate API token")
    google_api_key: Optional[str] = Field(default=None, description="Google AI API key")
    github_token: Optional[str] = Field(default=None, description="GitHub token")
    s3_api_key: Optional[str] = Field(default=None, description="S3 API key")
    
    def __init__(self, **kwargs):
        """Initialize with config.json merger."""
        # Load from config.json if it exists
        config_json = self._load_config_json()
        
        # Merge config.json values with environment
        merged_data = {**config_json, **kwargs}
        
        super().__init__(**merged_data)
    
    @staticmethod
    def _load_config_json() -> Dict[str, Any]:
        """Load configuration from config.json file if it exists."""
        config_path = Path("data/config.json")
        if config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    # Remove metadata fields
                    config.pop("_setup_completed", None)
                    config.pop("_setup_timestamp", None)
                    return config
            except Exception as e:
                print(f"Warning: Error reading config.json: {e}")
        return {}
    
    def get_config_status(self) -> Dict[str, Any]:
        """Get configuration status and validation summary."""
        secrets_configured = sum([
            1 for key in ['openrouter_api_key', 'matrix_password', 'neynar_api_key']
            if getattr(self, key) is not None
        ])
        
        return {
            "core_configured": bool(self.core.db_path),
            "ai_configured": bool(self.openrouter_api_key),
            "matrix_configured": bool(self.matrix.user_id and self.matrix_password),
            "farcaster_configured": bool(self.neynar_api_key and self.farcaster.bot_fid),
            "secrets_configured": secrets_configured,
            "total_secrets": 3,
            "security_hardened": len(self.security.api_cors_origins) > 0 and self.security.api_cors_origins != ["*"]
        }
    
    def to_legacy_format(self) -> Dict[str, Any]:
        """Convert to legacy format for backward compatibility."""
        return {
            # Core settings
            "CHATBOT_DB_PATH": self.core.db_path,
            "LOG_LEVEL": self.core.log_level,
            "OBSERVATION_INTERVAL": self.core.observation_interval,
            "MAX_CYCLES_PER_HOUR": self.core.max_cycles_per_hour,
            "MAX_ACTIONS_PER_HOUR": self.core.max_actions_per_hour,
            "DEVICE_NAME": self.core.device_name,
            
            # AI settings
            "AI_MODEL": self.ai.primary_model,
            "AI_MULTIMODAL_MODEL": self.ai.multimodal_model,
            "WEB_SEARCH_MODEL": self.ai.web_search_model,
            "AI_CONVERSATION_HISTORY_LENGTH": self.ai.conversation_history_length,
            "AI_ACTION_HISTORY_LENGTH": self.ai.action_history_length,
            "AI_CONTEXT_TOKEN_THRESHOLD": self.ai.context_token_threshold,
            "AI_ENABLE_PROMPT_LOGGING": self.ai.enable_prompt_logging,
            "AI_LOG_TOKEN_USAGE": self.ai.log_token_usage,
            
            # Matrix settings
            "MATRIX_HOMESERVER": self.matrix.homeserver,
            "MATRIX_USER_ID": self.matrix.user_id,
            "MATRIX_ROOM_ID": self.matrix.room_id,
            "MATRIX_DEVICE_ID": self.matrix.device_id,
            
            # Secrets
            "OPENROUTER_API_KEY": self.openrouter_api_key,
            "MATRIX_PASSWORD": self.matrix_password,
            "NEYNAR_API_KEY": self.neynar_api_key,
            
            # Performance
            "MAX_EXPANDED_NODES": self.performance.max_expanded_nodes,
            "IMAGE_GENERATION_COOLDOWN_SECONDS": self.media.image_generation_cooldown_seconds,
        }


# Global settings instance
def create_settings() -> UnifiedSettings:
    """Create settings instance with enhanced configuration management."""
    return UnifiedSettings()


# Backward compatibility
settings = create_settings()
