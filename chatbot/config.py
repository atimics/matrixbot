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


# Global settings instance
settings = AppConfig()
