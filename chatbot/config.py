"""
Centralized Configuration Management

This module provides centralized configuration management for the RatiChat application.
It loads and validates configuration from environment variables and .env files.
Enhanced with nested configuration sections for better organization.
"""

import os
from pathlib import Path
from typing import Optional, List

from pydantic_settings import BaseSettings, SettingsConfigDict


class MatrixConfig(BaseSettings):
    """Matrix-specific configuration."""
    
    model_config = SettingsConfigDict(env_prefix="MATRIX_")
    
    homeserver: Optional[str] = None
    user_id: Optional[str] = None
    password: Optional[str] = None
    room_id: str = "#robot-laboratory:chat.ratimics.com"
    device_id: Optional[str] = None
    media_gallery_room_id: Optional[str] = None
    device_name: str = "ratichat_bot"
    
    # Auto-posting configuration
    auto_attach_media: bool = False
    gallery_auto_post: bool = True


class FarcasterConfig(BaseSettings):
    """Farcaster-specific configuration."""
    
    model_config = SettingsConfigDict(env_prefix="FARCASTER_")
    
    neynar_api_key: Optional[str] = None
    bot_fid: Optional[str] = None
    bot_signer_uuid: Optional[str] = None
    bot_username: Optional[str] = None
    
    # Auto-posting configuration
    auto_attach_media: bool = True
    min_post_interval_minutes: int = 1
    duplicate_check_hours: int = 1
    recent_posts_limit: int = 10
    
    # API configuration
    api_timeout: float = 30.0
    api_max_retries: int = 3
    api_base_delay: float = 1.0
    api_max_delay: float = 60.0


class AIConfig(BaseSettings):
    """AI and language model configuration."""
    
    model_config = SettingsConfigDict(env_prefix="AI_")
    
    model: str = "openai/gpt-4o-mini"
    multimodal_model: str = "openai/gpt-4o"
    summary_model: str = "openai/gpt-4o-mini"
    web_search_model: str = "openai/gpt-4o-mini:online"
    
    # Payload optimization
    conversation_history_length: int = 3
    action_history_length: int = 15
    thread_history_length: int = 2
    other_channels_summary_count: int = 1
    other_channels_message_snippet_length: int = 50
    include_detailed_user_info: bool = False
    context_token_threshold: int = 8000
    
    # Debugging and analysis
    enable_prompt_logging: bool = True
    log_full_prompts: bool = False
    log_token_usage: bool = True
    log_prompt_preview_length: int = 200
    dump_payloads_to_file: bool = False
    payload_dump_directory: str = "data/payload_dumps"
    payload_dump_max_files: int = 50
    optimization_level: str = "balanced"


class MediaConfig(BaseSettings):
    """Media generation and storage configuration."""
    
    model_config = SettingsConfigDict(env_prefix="MEDIA_")
    
    # Replicate configuration
    replicate_api_token: Optional[str] = None
    replicate_image_model: str = "stability-ai/sdxl"
    replicate_lora_weights_url: Optional[str] = None
    replicate_lora_scale: Optional[float] = 0.75
    
    # Google AI configuration
    google_api_key: Optional[str] = None
    google_gemini_image_model: str = "gemini-1.5-flash-latest"
    google_veo_video_model: str = "models/veo-experimental-v1"
    
    # Cooldowns and limits
    image_generation_cooldown_seconds: int = 120
    video_generation_cooldown_seconds: int = 600
    max_image_generations_per_hour: int = 15
    max_video_generations_per_hour: int = 5
    
    # Archival
    popular_archival_threshold_likes: int = 5
    popular_archival_interval_minutes: int = 30


class StorageConfig(BaseSettings):
    """Storage configuration for different services."""
    
    model_config = SettingsConfigDict(env_prefix="STORAGE_")
    
    # S3 configuration
    s3_api_key: Optional[str] = None
    s3_api_endpoint: Optional[str] = None
    s3_cloudfront_domain: Optional[str] = None
    s3_upload_timeout: float = 120.0
    use_s3_for_media: bool = True
    
    # Arweave configuration
    arweave_internal_uploader_service_url: str = "http://arweave-uploader:8001"
    arweave_gateway_url: str = "https://arweave.net"


class SecurityConfig(BaseSettings):
    """Security configuration."""
    
    model_config = SettingsConfigDict(env_prefix="SECURITY_")
    
    api_key: Optional[str] = None
    allowed_origins: List[str] = ["http://localhost:3000"]
    trusted_hosts: List[str] = ["localhost", "127.0.0.1"]
    rate_limit_requests_per_minute: int = 60
    rate_limit_burst_size: int = 100
    enable_api_key_auth: bool = True


class EcosystemConfig(BaseSettings):
    """Ecosystem token and community configuration."""
    
    model_config = SettingsConfigDict(env_prefix="ECOSYSTEM_")
    
    token_contract_address: Optional[str] = "Ci6Y1UX8bY4jxn6YiogJmdCxFEu2jmZhCcG65PStpump"
    token_network: str = "solana"
    num_top_holders_to_track: int = 10
    top_holders_update_interval_minutes: int = 60
    holder_cast_history_length: int = 5


class NodeSystemConfig(BaseSettings):
    """Node-based processing system configuration."""
    
    model_config = SettingsConfigDict(env_prefix="NODE_")
    
    max_expanded_nodes: int = 8
    default_pinned_nodes: List[str] = [
        "channels.matrix.primary",
        "system.notifications", 
        "system.rate_limits"
    ]
    enable_two_phase_ai_process: bool = False
    max_exploration_rounds: int = 3


class AppConfig(BaseSettings):
    """
    Centralized application configuration with nested sections.
    This provides better organization and maintainability.
    """

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Core application settings
    chatbot_db_path: str = "data/chatbot.db"
    observation_interval: float = 2.0
    max_cycles_per_hour: int = 300
    max_actions_per_hour: int = 600
    log_level: str = "INFO"
    
    # OpenRouter API configuration
    openrouter_api_key: Optional[str] = None
    your_site_url: Optional[str] = None
    your_site_name: Optional[str] = None
    
    # Primary LLM provider
    primary_llm_provider: str = "openrouter"
    
    # Ollama configuration (optional)
    ollama_api_url: Optional[str] = "http://localhost:11434"
    ollama_default_chat_model: Optional[str] = "llama3"
    ollama_default_summary_model: Optional[str] = "llama3"
    
    # Tool cooldowns
    store_memory_cooldown_seconds: int = 60
    max_memories_stored_per_hour: int = 30
    
    # NFT & Airdrop configuration
    nft_dev_wallet_private_key: Optional[str] = None
    base_rpc_url: Optional[str] = None
    nft_collection_name: str = "AI Collective"
    nft_collection_symbol: str = "AIC"
    nft_collection_address_base: Optional[str] = None
    nft_metadata_upload_service: str = "arweave"
    
    # Frame server configuration
    frames_base_url: Optional[str] = None
    frames_webhook_secret: Optional[str] = None
    
    # Airdrop eligibility
    airdrop_min_ecosystem_token_balance_sol: float = 1000.0
    airdrop_min_ecosystem_nft_count_base: int = 1
    airdrop_eligibility_check_interval_hours: int = 6
    
    # GitHub integration
    github_token: Optional[str] = None
    github_username: Optional[str] = None

    # Nested configuration sections
    matrix: MatrixConfig = MatrixConfig()
    farcaster: FarcasterConfig = FarcasterConfig()
    ai: AIConfig = AIConfig()
    media: MediaConfig = MediaConfig()
    storage: StorageConfig = StorageConfig()
    security_config: SecurityConfig = SecurityConfig()  # Renamed to avoid conflict
    ecosystem: EcosystemConfig = EcosystemConfig()
    node_system: NodeSystemConfig = NodeSystemConfig()

    
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

    # API Security Configuration
    class Security:
        """Security configuration nested class."""
        api_key: Optional[str] = None
        allowed_origins: List[str] = ["http://localhost:3000"]
        trusted_hosts: List[str] = ["localhost", "127.0.0.1"]
        rate_limit_requests_per_minute: int = 60
        rate_limit_burst_size: int = 100
        enable_api_key_auth: bool = True

    security: Security = Security()


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
