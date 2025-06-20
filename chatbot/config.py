"""
Centralized Configuration Management

This module provides centralized configuration management for the RatiChat application.
It loads and validates configuration from environment variables and .env files.
"""

import os
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    """Centralized application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Chatbot Core
    CHATBOT_DB_PATH: str = "data/chatbot.db"
    OBSERVATION_INTERVAL: float = 2.0
    MAX_CYCLES_PER_HOUR: int = 300
    MAX_ACTIONS_PER_HOUR: int = 600
    AI_MODEL: str = "openai/gpt-4o-mini"
    AI_MULTIMODAL_MODEL: str = "openai/gpt-4o"  # Model for image/video analysis
    OPENROUTER_API_KEY: Optional[str] = None  # Made optional for demo mode
    LOG_LEVEL: str = "INFO"
    
    # Web Search and Research
    WEB_SEARCH_MODEL: str = "openai/gpt-4o-mini:online"  # OpenRouter online model for web search

    # Matrix (Optional since we removed Synapse dependency)
    MATRIX_HOMESERVER: Optional[str] = None
    MATRIX_USER_ID: Optional[str] = None
    MATRIX_PASSWORD: Optional[str] = None
    MATRIX_ROOM_ID: str = (
        "#robot-laboratory:chat.ratimics.com"  # Default initial room to monitor
    )
    MATRIX_DEVICE_ID: Optional[str] = None
    MATRIX_MEDIA_GALLERY_ROOM_ID: Optional[str] = None  # Dedicated channel for auto-posting generated media
    DEVICE_NAME: str = "ratichat_bot"

    # Matrix Auto-Posting Configuration
    MATRIX_AUTO_ATTACH_MEDIA: bool = False  # Auto-attach recent media to Matrix messages (disabled by default)
    MATRIX_GALLERY_AUTO_POST: bool = True   # Auto-post generated media to gallery room (enabled by default)

    # Farcaster (Optional)
    NEYNAR_API_KEY: Optional[str] = None
    FARCASTER_BOT_FID: Optional[str] = None
    FARCASTER_BOT_SIGNER_UUID: Optional[str] = None
    FARCASTER_BOT_USERNAME: Optional[str] = None  # Bot's username for filtering
    
    # Farcaster Auto-Posting Configuration  
    FARCASTER_AUTO_ATTACH_MEDIA: bool = True  # Auto-attach recent media to Farcaster posts (enabled by default)
    
    # Farcaster Rate Limiting and Context
    FARCASTER_MIN_POST_INTERVAL_MINUTES: int = 1  # Minimum minutes between posts
    FARCASTER_DUPLICATE_CHECK_HOURS: int = 1  # Hours to look back for duplicate content
    FARCASTER_RECENT_POSTS_LIMIT: int = 10  # Number of recent posts to fetch for context
    
    # Farcaster Network Configuration
    NEYNAR_API_BASE_URL: Optional[str] = None  # Override default Neynar API base URL
    FARCASTER_API_TIMEOUT: float = 30.0  # API request timeout in seconds
    FARCASTER_API_MAX_RETRIES: int = 3  # Maximum retry attempts for failed requests
    FARCASTER_API_BASE_DELAY: float = 1.0  # Base delay for exponential backoff (seconds)
    FARCASTER_API_MAX_DELAY: float = 60.0  # Maximum delay between retries (seconds)

    # Ecosystem Token Tracking
    ECOSYSTEM_TOKEN_CONTRACT_ADDRESS: Optional[str] = "Ci6Y1UX8bY4jxn6YiogJmdCxFEu2jmZhCcG65PStpump"  # Contract address of the token
    ECOSYSTEM_TOKEN_NETWORK: str = "solana"  # Network of the token (ethereum, optimism, base, arbitrum, solana)
    NUM_TOP_HOLDERS_TO_TRACK: int = 10  # Number of top holders to monitor
    TOP_HOLDERS_UPDATE_INTERVAL_MINUTES: int = 60  # How often to refresh the top holders list
    HOLDER_CAST_HISTORY_LENGTH: int = 5  # Number of recent casts to store per holder

    # OpenRouter specific from original .env.example (these might be for other services or documentation)
    YOUR_SITE_URL: Optional[str] = None
    YOUR_SITE_NAME: Optional[str] = None

    # Ollama (Optional - from .env.example)
    PRIMARY_LLM_PROVIDER: str = "openrouter"
    OLLAMA_API_URL: Optional[str] = "http://localhost:11434"
    OLLAMA_DEFAULT_CHAT_MODEL: Optional[str] = "llama3"
    OLLAMA_DEFAULT_SUMMARY_MODEL: Optional[str] = "llama3"
    # AI payload truncation settings - aggressively optimized to prevent 402/413 errors
    AI_CONVERSATION_HISTORY_LENGTH: int = 3  # Max messages per channel for AI payload (reduced from 7)
    AI_ACTION_HISTORY_LENGTH: int = 15  # Max actions in history for AI payload (increased from 2 to prevent action loops)
    AI_THREAD_HISTORY_LENGTH: int = 2  # Max thread messages for AI payload (reduced from 3)
    AI_OTHER_CHANNELS_SUMMARY_COUNT: int = (
        1  # How many other active channels to summarize (reduced from 2)
    )
    AI_OTHER_CHANNELS_MESSAGE_SNIPPET_LENGTH: int = (
        50  # Length of snippet for other channels (reduced from 75)
    )
    AI_INCLUDE_DETAILED_USER_INFO: bool = (
        False  # Include full user metadata or summarize - False reduces payload size significantly
    )
    AI_CONTEXT_TOKEN_THRESHOLD: int = 8000  # Switch to node-based payload when estimated tokens exceed this (reduced from 12000)
    
    # AI Debugging and Analysis Configuration
    AI_ENABLE_PROMPT_LOGGING: bool = True  # Enable detailed prompt logging for analysis
    AI_LOG_FULL_PROMPTS: bool = False  # Log full prompts and responses (very verbose)
    AI_LOG_TOKEN_USAGE: bool = True  # Log token usage and cost estimation
    AI_LOG_PROMPT_PREVIEW_LENGTH: int = 200  # Length of prompt preview in logs when full logging is disabled
    AI_DUMP_PAYLOADS_TO_FILE: bool = False  # Write payloads to files for offline analysis
    AI_PAYLOAD_DUMP_DIRECTORY: str = "data/payload_dumps"  # Directory to store payload dumps
    AI_PAYLOAD_DUMP_MAX_FILES: int = 50  # Maximum number of payload files to keep
    AI_OPTIMIZATION_LEVEL: str = "balanced"  # Options: "original", "balanced", "aggressive"

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

    # Arweave Configuration (Internal Uploader Service)
    ARWEAVE_INTERNAL_UPLOADER_SERVICE_URL: str = "http://arweave-uploader:8001"
    ARWEAVE_GATEWAY_URL: str = "https://arweave.net"

    # NFT & Airdrop Configuration (v0.0.4)
    NFT_DEV_WALLET_PRIVATE_KEY: Optional[str] = None  # For sponsoring transactions or direct minting
    BASE_RPC_URL: Optional[str] = None  # e.g., from Alchemy or Infura
    NFT_COLLECTION_NAME: str = "AI Collective"
    NFT_COLLECTION_SYMBOL: str = "AIC"
    NFT_COLLECTION_ADDRESS_BASE: Optional[str] = None  # The address of your NFT contract on Base
    NFT_METADATA_UPLOAD_SERVICE: str = "arweave"  # or "ipfs"
    
    # Frame Server Configuration
    FRAMES_BASE_URL: Optional[str] = None  # Base URL for serving frames (e.g., https://yourbot.com)
    FRAMES_WEBHOOK_SECRET: Optional[str] = None  # Secret for validating frame requests
    
    # Airdrop Eligibility Criteria
    AIRDROP_MIN_ECOSYSTEM_TOKEN_BALANCE_SOL: float = 1000.0
    AIRDROP_MIN_ECOSYSTEM_NFT_COUNT_BASE: int = 1
    AIRDROP_ELIGIBILITY_CHECK_INTERVAL_HOURS: int = 6  # How often to check eligibility

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

    # S3 Storage Configuration (Primary media storage)
    S3_API_KEY: Optional[str] = None  # S3 API key for authentication
    S3_API_ENDPOINT: Optional[str] = None  # S3 service endpoint URL
    CLOUDFRONT_DOMAIN: Optional[str] = None  # CloudFront domain for public URLs
    S3_UPLOAD_TIMEOUT: float = 120.0  # Upload timeout in seconds
    USE_S3_FOR_MEDIA: bool = True  # Use S3 as primary media storage (keep Arweave for NFTs)


# Global settings instance
def create_settings() -> AppConfig:
    """Create settings instance from environment variables and .env files only."""
    return AppConfig()


settings = create_settings()

# For backward compatibility with code expecting UnifiedSettings
UnifiedSettings = AppConfig

# For backward compatibility with code expecting get_settings() function
def get_settings() -> AppConfig:
    """Get the global settings instance."""
    return settings
