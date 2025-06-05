"""
Centralized Configuration Management

This module provides centralized configuration management using Pydantic BaseSettings
to load and validate all configuration from environment variables and .env files.
"""

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    """Centralized application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Chatbot Core
    CHATBOT_DB_PATH: str = "chatbot.db"
    OBSERVATION_INTERVAL: float = 2.0
    MAX_CYCLES_PER_HOUR: int = 300
    AI_MODEL: str = "openai/gpt-4o-mini"
    OPENROUTER_API_KEY: str
    LOG_LEVEL: str = "INFO"
    
    # Web Search and Research
    WEB_SEARCH_MODEL: str = "openai/gpt-4o-mini:online"  # OpenRouter online model for web search

    # Matrix
    MATRIX_HOMESERVER: str
    MATRIX_USER_ID: str
    MATRIX_PASSWORD: str
    MATRIX_ROOM_ID: str = (
        "#robot-laboratory:chat.ratimics.com"  # Default initial room to monitor
    )
    MATRIX_DEVICE_ID: Optional[str] = None
    DEVICE_NAME: str = "ratichat_bot"

    # Farcaster (Optional)
    NEYNAR_API_KEY: Optional[str] = None
    FARCASTER_BOT_FID: Optional[str] = None
    FARCASTER_BOT_SIGNER_UUID: Optional[str] = None
    FARCASTER_BOT_USERNAME: Optional[str] = None  # Bot's username for filtering

    # Ecosystem Token Tracking
    ECOSYSTEM_TOKEN_CONTRACT_ADDRESS: Optional[str] = "Ci6Y1UX8bY4jxn6YiogJmdCxFEu2jmZhCcG65PStpump"  # Contract address of the token
    ECOSYSTEM_TOKEN_NETWORK: str = "solana"  # Network of the token (ethereum, optimism, base, arbitrum, solana)
    NUM_TOP_HOLDERS_TO_TRACK: int = 10  # Number of top holders to monitor
    TOP_HOLDERS_UPDATE_INTERVAL_MINUTES: int = 60  # How often to refresh the top holders list
    HOLDER_CAST_HISTORY_LENGTH: int = 5  # Number of recent casts to store per holder

    # OpenRouter specific from original .env.example (these might be for other services or documentation)
    OPENROUTER_MODEL: str = "openai/gpt-4o-mini"  # Matches AI_MODEL typically
    OPENROUTER_MULTIMODAL_MODEL: str = (
        "openai/gpt-4o"  # Or your preferred OpenRouter multimodal model
    )
    YOUR_SITE_URL: Optional[str] = None
    YOUR_SITE_NAME: Optional[str] = None

    # Ollama (Optional - from .env.example)
    PRIMARY_LLM_PROVIDER: str = "openrouter"
    OLLAMA_API_URL: Optional[str] = "http://localhost:11434"
    OLLAMA_DEFAULT_CHAT_MODEL: Optional[str] = "llama3"
    OLLAMA_DEFAULT_SUMMARY_MODEL: Optional[str] = "llama3"
    # AI payload truncation settings - optimized to prevent 413 Payload Too Large errors
    AI_CONVERSATION_HISTORY_LENGTH: int = 7  # Max messages per channel for AI payload (reduced from 10)
    AI_ACTION_HISTORY_LENGTH: int = 3  # Max actions in history for AI payload (reduced from 5)
    AI_THREAD_HISTORY_LENGTH: int = 3  # Max thread messages for AI payload (reduced from 5)
    AI_OTHER_CHANNELS_SUMMARY_COUNT: int = (
        2  # How many other active channels to summarize (reduced from 3)
    )
    AI_OTHER_CHANNELS_MESSAGE_SNIPPET_LENGTH: int = (
        75  # Length of snippet for other channels
    )
    AI_INCLUDE_DETAILED_USER_INFO: bool = (
        False  # Include full user metadata or summarize - False reduces payload size significantly
    )

    # v0.0.3: Media Generation & Permaweb Storage Configuration

    # Replicate Configuration
    REPLICATE_API_TOKEN: Optional[str] = None
    REPLICATE_IMAGE_MODEL: str = "stability-ai/sdxl"
    REPLICATE_LORA_WEIGHTS_URL: Optional[str] = None
    REPLICATE_LORA_SCALE: Optional[float] = 0.75

    # Google AI Media Generation
    GOOGLE_API_KEY: Optional[
        str
    ] = None  # For Google AI services (separate from OpenRouter)
    GOOGLE_GEMINI_IMAGE_MODEL: str = "gemini-1.5-flash-latest"
    GOOGLE_VEO_VIDEO_MODEL: str = "models/veo-experimental-v1"

    # Arweave Uploader Service
    ARWEAVE_UPLOADER_API_ENDPOINT: Optional[str] = None
    ARWEAVE_UPLOADER_API_KEY: Optional[str] = None
    ARWEAVE_GATEWAY_URL: str = "https://arweave.net"

    # Tool Cooldowns & Resource Limits
    IMAGE_GENERATION_COOLDOWN_SECONDS: int = 120  # 2 minutes
    VIDEO_GENERATION_COOLDOWN_SECONDS: int = 600  # 10 minutes
    STORE_MEMORY_COOLDOWN_SECONDS: int = 60  # 1 minute
    MAX_IMAGE_GENERATIONS_PER_HOUR: int = 15
    MAX_VIDEO_GENERATIONS_PER_HOUR: int = 5
    MAX_MEMORIES_STORED_PER_HOUR: int = 30

    # Popular Media Archival
    POPULAR_MEDIA_ARCHIVAL_THRESHOLD_LIKES: int = 5
    POPULAR_MEDIA_ARCHIVAL_INTERVAL_MINUTES: int = 30

    # JSON Observer and Interactive Executor Configuration
    MAX_EXPANDED_NODES: int = 8  # Maximum number of simultaneously expanded nodes
    DEFAULT_PINNED_NODES: list[str] = [
        "channels.matrix.primary",  # Primary Matrix channel
        "system.notifications",     # Global notifications
        "system.rate_limits"       # Rate limit status
    ]
    AI_SUMMARY_MODEL: str = "openai/gpt-4o-mini"  # Model for generating node summaries
    ENABLE_TWO_PHASE_AI_PROCESS: bool = False  # Enable separate exploration/action phases
    MAX_EXPLORATION_ROUNDS: int = 3  # Max rounds in exploration phase if two-phase enabled
    
    # GitHub ACE (Autonomous Code Evolution) Integration
    GITHUB_TOKEN: Optional[str] = None
    GITHUB_USERNAME: Optional[str] = None


# Global settings instance
settings = AppConfig()
