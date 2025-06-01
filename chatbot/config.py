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

    # OpenRouter specific from original .env.example (these might be for other services or documentation)
    OPENROUTER_MODEL: str = "openai/gpt-4o-mini"  # Matches AI_MODEL typically
    OPENROUTER_MULTIMODAL_MODEL: str = "openai/gpt-4o"  # Or your preferred OpenRouter multimodal model
    YOUR_SITE_URL: Optional[str] = None
    YOUR_SITE_NAME: Optional[str] = None

    # Ollama (Optional - from .env.example)
    PRIMARY_LLM_PROVIDER: str = "openrouter"
    OLLAMA_API_URL: Optional[str] = "http://localhost:11434"
    OLLAMA_DEFAULT_CHAT_MODEL: Optional[str] = "llama3"
    OLLAMA_DEFAULT_SUMMARY_MODEL: Optional[str] = "llama3"
    # AI payload truncation settings
    AI_CONVERSATION_HISTORY_LENGTH: int = 10  # Max messages per channel for AI payload
    AI_ACTION_HISTORY_LENGTH: int = 5  # Max actions in history for AI payload
    AI_THREAD_HISTORY_LENGTH: int = 5  # Max thread messages for AI payload
    AI_OTHER_CHANNELS_SUMMARY_COUNT: int = (
        3  # How many other active channels to summarize
    )
    AI_OTHER_CHANNELS_MESSAGE_SNIPPET_LENGTH: int = (
        75  # Length of snippet for other channels
    )
    AI_INCLUDE_DETAILED_USER_INFO: bool = (
        True  # Include full user metadata or summarize
    )

    # v0.0.3: Media Generation & Permaweb Storage Configuration

    # Replicate Configuration
    REPLICATE_API_TOKEN: Optional[str] = None
    REPLICATE_IMAGE_MODEL: str = "stability-ai/sdxl"
    REPLICATE_LORA_WEIGHTS_URL: Optional[str] = None
    REPLICATE_LORA_SCALE: Optional[float] = 0.75

    # Google AI Media Generation
    GOOGLE_API_KEY: Optional[str] = None  # For Google AI services (separate from OpenRouter)
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


# Global settings instance
settings = AppConfig()
