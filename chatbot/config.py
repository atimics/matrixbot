"""
Centralized Configuration Management

This module provides centralized configuration management using nested Pydantic BaseSettings
to load and validate all configuration from environment variables and .env files.

The configuration is organized into logical sections with proper validation to ensure
all dependencies between settings are properly enforced.
"""

import json
import os
from pathlib import Path
from typing import Optional, List
from pydantic import BaseModel, model_validator, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def load_config_json() -> dict:
    """Load configuration from config.json file if it exists."""
    config_path = Path("data/config.json")
    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                # Remove metadata fields that aren't configuration
                config.pop("_setup_completed", None)
                config.pop("_setup_timestamp", None)
                return config
        except Exception as e:
            print(f"Warning: Error reading config.json: {e}")
    return {}


class ProcessingConfig(BaseSettings):
    """Configuration for the Commander/Sub-Agent processing architecture."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    # Commander/Sub-Agent Architecture
    enable_mission_delegation: bool = Field(default=True, alias="ENABLE_MISSION_DELEGATION")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    
    # AI Models and Performance
    openrouter_api_key: Optional[str] = Field(default=None, alias="OPENROUTER_API_KEY")
    ai_model: str = Field(default="openai/gpt-4o-mini", alias="AI_MODEL")
    ai_multimodal_model: str = Field(default="openai/gpt-4o", alias="AI_MULTIMODAL_MODEL")
    lightweight_ai_model: str = Field(default="openai/gpt-4o-mini", alias="LIGHTWEIGHT_AI_MODEL")
    lightweight_ai_max_tokens: int = Field(default=500, alias="LIGHTWEIGHT_AI_MAX_TOKENS")
    lightweight_ai_temperature: float = Field(default=0.7, alias="LIGHTWEIGHT_AI_TEMPERATURE")
    web_search_model: str = Field(default="openai/gpt-4o-mini:online", alias="WEB_SEARCH_MODEL")
    ai_summary_model: str = Field(default="openai/gpt-4o-mini", alias="AI_SUMMARY_MODEL")
    
    # Rate Limiting
    observation_interval: float = Field(default=2.0, alias="OBSERVATION_INTERVAL")
    max_cycles_per_hour: int = Field(default=300, alias="MAX_CYCLES_PER_HOUR")
    max_actions_per_hour: int = Field(default=600, alias="MAX_ACTIONS_PER_HOUR")
    
    # Node System Configuration
    max_expanded_nodes: int = Field(default=8, alias="MAX_EXPANDED_NODES")
    default_pinned_nodes: List[str] = Field(
        default=["channels.matrix.primary", "system.notifications", "system.rate_limits"],
        alias="DEFAULT_PINNED_NODES"
    )
    enable_two_phase_ai_process: bool = Field(default=False, alias="ENABLE_TWO_PHASE_AI_PROCESS")
    max_exploration_rounds: int = Field(default=3, alias="MAX_EXPLORATION_ROUNDS")
    
    # User Interaction Limits
    daily_unsolicited_reply_cap: int = Field(default=5, alias="DAILY_UNSOLICITED_REPLY_CAP")


class MatrixConfig(BaseSettings):
    """Matrix platform configuration."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    homeserver: Optional[str] = Field(default=None, alias="MATRIX_HOMESERVER")
    user_id: Optional[str] = Field(default=None, alias="MATRIX_USER_ID")
    password: Optional[str] = Field(default=None, alias="MATRIX_PASSWORD")
    room_id: str = Field(default="#robot-laboratory:chat.ratimics.com", alias="MATRIX_ROOM_ID")
    device_id: Optional[str] = Field(default=None, alias="MATRIX_DEVICE_ID")
    device_name: str = Field(default="ratichat_bot", alias="DEVICE_NAME")
    media_gallery_room_id: Optional[str] = Field(default=None, alias="MATRIX_MEDIA_GALLERY_ROOM_ID")
    
    @model_validator(mode='after')
    def validate_matrix_dependencies(self):
        """Validate that if any Matrix setting is configured, all required settings are present."""
        matrix_fields = [self.homeserver, self.user_id, self.password]
        if any(field is not None for field in matrix_fields):
            if not all(field is not None for field in matrix_fields):
                raise ValueError(
                    "If Matrix is configured, MATRIX_HOMESERVER,.matrix_user_id, and MATRIX_PASSWORD are all required"
                )
        return self


class FarcasterConfig(BaseSettings):
    """Farcaster platform configuration."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    neynar_api_key: Optional[str] = Field(default=None, alias="NEYNAR_API_KEY")
    bot_fid: Optional[str] = Field(default=None, alias="FARCASTER_BOT_FID")
    bot_signer_uuid: Optional[str] = Field(default=None, alias="FARCASTER_BOT_SIGNER_UUID")
    bot_username: Optional[str] = Field(default=None, alias="FARCASTER_BOT_USERNAME")
    post_cooldown_seconds: int = Field(default=300, alias="FARCASTER_POST_COOLDOWN_SECONDS")
    
    @model_validator(mode='after')
    def validate_farcaster_dependencies(self):
        """Validate that if Farcaster is configured, all required settings are present."""
        if self.neynar_api_key:
            if not all([self.bot_fid, self.bot_signer_uuid, self.bot_username]):
                raise ValueError(
                    "If NEYNAR_API_KEY is set, FARCASTER_BOT_FID, FARCASTER_BOT_SIGNER_UUID, and FARCASTER_BOT_USERNAME are all required"
                )
        return self


class MediaGenerationConfig(BaseSettings):
    """Configuration for AI media generation services."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    # Replicate Configuration
    replicate_api_token: Optional[str] = Field(default=None, alias="REPLICATE_API_TOKEN")
    replicate_image_model: str = Field(default="stability-ai/sdxl", alias="REPLICATE_IMAGE_MODEL")
    replicate_lora_weights_url: Optional[str] = Field(default=None, alias="REPLICATE_LORA_WEIGHTS_URL")
    replicate_lora_scale: Optional[float] = Field(default=0.75, alias="REPLICATE_LORA_SCALE")
    
    # Google AI Media Generation
    google_api_key: Optional[str] = Field(default=None, alias="GOOGLE_API_KEY")
    google_gemini_image_model: str = Field(default="gemini-2.0-flash-preview-image-generation", alias="GOOGLE_GEMINI_IMAGE_MODEL")
    google_veo_video_model: str = Field(default="models/veo-experimental-v1", alias="GOOGLE_VEO_VIDEO_MODEL")
    
    # Tool Cooldowns & Resource Limits
    image_generation_cooldown_seconds: int = Field(default=120, alias="IMAGE_GENERATION_COOLDOWN_SECONDS")
    video_generation_cooldown_seconds: int = Field(default=600, alias="VIDEO_GENERATION_COOLDOWN_SECONDS")
    max_image_generations_per_hour: int = Field(default=15, alias="MAX_IMAGE_GENERATIONS_PER_HOUR")
    max_video_generations_per_hour: int = Field(default=5, alias="MAX_VIDEO_GENERATIONS_PER_HOUR")


class StorageConfig(BaseSettings):
    """Configuration for permanent storage services."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    # S3 Configuration (primary)
    s3_api_endpoint: Optional[str] = Field(default=None, alias="S3_API_ENDPOINT")
    s3_api_key: Optional[str] = Field(default=None, alias="S3_API_KEY")
    cloudfront_domain: Optional[str] = Field(default=None, alias="CLOUDFRONT_DOMAIN")
    
    # Legacy Arweave Configuration (backward compatibility)
    arweave_internal_uploader_service_url: str = Field(default="http://arweave-uploader:8001", alias="ARWEAVE_INTERNAL_UPLOADER_SERVICE_URL")
    arweave_gateway_url: str = Field(default="https://arweave.net", alias="ARWEAVE_GATEWAY_URL")
    
    # Memory Storage
    store_memory_cooldown_seconds: int = Field(default=60, alias="STORE_MEMORY_COOLDOWN_SECONDS")
    max_memories_stored_per_hour: int = Field(default=30, alias="MAX_MEMORIES_STORED_PER_HOUR")
    
    @model_validator(mode='after')
    def validate_storage_dependencies(self):
        """Validate that at least one storage backend is configured."""
        s3_configured = bool(self.s3_api_endpoint and self.s3_api_key)
        arweave_configured = bool(self.arweave_internal_uploader_service_url)
        
        if not (s3_configured or arweave_configured):
            raise ValueError(
                "At least one storage backend must be configured (S3 or Arweave)"
            )
        return self


class DeveloperToolsConfig(BaseSettings):
    """Configuration for developer tools and GitHub integration."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    developer_tools_enabled: bool = Field(default=False, alias="DEVELOPER_TOOLS_ENABLED")
    github_token: Optional[str] = Field(default=None, alias="GITHUB_TOKEN")
    github_username: Optional[str] = Field(default=None, alias="GITHUB_USERNAME")
    
    @model_validator(mode='after')
    def validate_developer_tools_dependencies(self):
        """Validate that if developer tools are enabled, required GitHub settings are present."""
        if self.developer_tools_enabled:
            if not self.github_token:
                raise ValueError(
                    "If DEVELOPER_TOOLS_ENABLED is True, GITHUB_TOKEN is required"
                )
        return self


class SecurityConfig(BaseSettings):
    """Security and authentication configuration."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    api_server_key: Optional[str] = Field(default=None, alias="API_SERVER_KEY")
    api_require_auth: bool = Field(default=True, alias="API_REQUIRE_AUTH")
    development_mode: bool = Field(default=False, alias="DEVELOPMENT_MODE")
    allowed_cors_origins: List[str] = Field(default=[], alias="ALLOWED_CORS_ORIGINS")
    max_auth_attempts_per_minute: int = Field(default=10, alias="MAX_AUTH_ATTEMPTS_PER_MINUTE")
    session_secret_key: Optional[str] = Field(default=None, alias="SESSION_SECRET_KEY")
    ratichat_encryption_key: Optional[str] = Field(default=None, alias="RATICHAT_ENCRYPTION_KEY")


class PostgresConfig(BaseSettings):
    """PostgreSQL database configuration."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8", 
        extra="ignore"
    )
    
    user: str = Field(default="ratichat", alias="POSTGRES_USER")
    password: str = Field(default="your_strong_password_here", alias="POSTGRES_PASSWORD")
    host: str = Field(default="localhost", alias="POSTGRES_HOST")
    port: int = Field(default=5432, alias="POSTGRES_PORT")
    dbname: str = Field(default="ratichat", alias="POSTGRES_DB")
    
    # Connection pool settings
    min_pool_size: int = Field(default=1, alias="POSTGRES_MIN_POOL_SIZE")
    max_pool_size: int = Field(default=10, alias="POSTGRES_MAX_POOL_SIZE")
    
    @property
    def dsn(self) -> str:
        """Data Source Name connection string."""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.dbname}"
    
    @property
    def external_dsn(self) -> str:
        """External Data Source Name for migration scripts (uses localhost)."""
        return f"postgresql://{self.user}:{self.password}@localhost:{self.port}/{self.dbname}"


class AppConfig(BaseSettings):
    """
    Centralized application configuration with nested validation.
    
    This configuration uses nested Pydantic models to organize settings logically
    and enforce dependencies between related configuration options.
    """

    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8", 
        extra="ignore",
        env_nested_delimiter="__"
    )

    # Core System Settings
    chatbot_db_path: str = Field(default="data/chatbot.db", alias="CHATBOT_DB_PATH")
    
    # Nested Configuration Sections
    processing: ProcessingConfig = Field(default_factory=ProcessingConfig)
    matrix: MatrixConfig = Field(default_factory=MatrixConfig)
    farcaster: FarcasterConfig = Field(default_factory=FarcasterConfig)
    media_generation: MediaGenerationConfig = Field(default_factory=MediaGenerationConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    developer_tools: DeveloperToolsConfig = Field(default_factory=DeveloperToolsConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    postgres: PostgresConfig = Field(default_factory=PostgresConfig)
    
    # Legacy flat configuration (to be migrated over time)
    # Ecosystem Token Tracking
    ecosystem_token_contract_address: Optional[str] = Field(default="Ci6Y1UX8bY4jxn6YiogJmdCxFEu2jmZhCcG65PStpump", alias="ECOSYSTEM_TOKEN_CONTRACT_ADDRESS")
    ecosystem_token_network: str = Field(default="solana", alias="ECOSYSTEM_TOKEN_NETWORK")
    num_top_holders_to_track: int = Field(default=10, alias="NUM_TOP_HOLDERS_TO_TRACK")
    top_holders_update_interval_minutes: int = Field(default=60, alias="TOP_HOLDERS_UPDATE_INTERVAL_MINUTES")
    holder_cast_history_length: int = Field(default=5, alias="HOLDER_CAST_HISTORY_LENGTH")

    # OpenRouter specific
    your_site_url: Optional[str] = Field(default=None, alias="YOUR_SITE_URL")
    your_site_name: Optional[str] = Field(default=None, alias="YOUR_SITE_NAME")

    # Ollama Configuration
    primary_llm_provider: str = Field(default="openrouter", alias="PRIMARY_LLM_PROVIDER")
    ollama_api_url: Optional[str] = Field(default="http://localhost:11434", alias="OLLAMA_API_URL")
    ollama_default_chat_model: Optional[str] = Field(default="llama3", alias="OLLAMA_DEFAULT_CHAT_MODEL")
    ollama_default_summary_model: Optional[str] = Field(default="llama3", alias="OLLAMA_DEFAULT_SUMMARY_MODEL")
    
    # AI payload truncation settings
    ai_conversation_history_length: int = Field(default=7, alias="AI_CONVERSATION_HISTORY_LENGTH")
    ai_action_history_length: int = Field(default=3, alias="AI_ACTION_HISTORY_LENGTH")
    ai_thread_history_length: int = Field(default=3, alias="AI_THREAD_HISTORY_LENGTH")
    ai_other_channels_summary_count: int = Field(default=2, alias="AI_OTHER_CHANNELS_SUMMARY_COUNT")
    ai_other_channels_message_snippet_length: int = Field(default=75, alias="AI_OTHER_CHANNELS_MESSAGE_SNIPPET_LENGTH")
    ai_include_detailed_user_info: bool = Field(default=False, alias="AI_INCLUDE_DETAILED_USER_INFO")

    # NFT & Airdrop Configuration
    nft_dev_wallet_private_key: Optional[str] = Field(default=None, alias="NFT_DEV_WALLET_PRIVATE_KEY")
    base_rpc_url: Optional[str] = Field(default=None, alias="BASE_RPC_URL")
    nft_collection_name: str = Field(default="AI Collective", alias="NFT_COLLECTION_NAME")
    nft_collection_symbol: str = Field(default="AIC", alias="NFT_COLLECTION_SYMBOL")
    nft_collection_address_base: Optional[str] = Field(default=None, alias="NFT_COLLECTION_ADDRESS_BASE")
    nft_metadata_upload_service: str = Field(default="arweave", alias="NFT_METADATA_UPLOAD_SERVICE")
    
    # Frame Server Configuration
    frames_base_url: Optional[str] = Field(default=None, alias="FRAMES_BASE_URL")
    frames_webhook_secret: Optional[str] = Field(default=None, alias="FRAMES_WEBHOOK_SECRET")
    
    # Airdrop Eligibility Criteria
    airdrop_min_ecosystem_token_balance_sol: float = Field(default=1000.0, alias="AIRDROP_MIN_ECOSYSTEM_TOKEN_BALANCE_SOL")
    airdrop_min_ecosystem_nft_count_base: int = Field(default=1, alias="AIRDROP_MIN_ECOSYSTEM_NFT_COUNT_BASE")
    airdrop_eligibility_check_interval_hours: int = Field(default=6, alias="AIRDROP_ELIGIBILITY_CHECK_INTERVAL_HOURS")

    # Popular Media Archival
    popular_media_archival_threshold_likes: int = Field(default=5, alias="POPULAR_MEDIA_ARCHIVAL_THRESHOLD_LIKES")
    popular_media_archival_interval_minutes: int = Field(default=30, alias="POPULAR_MEDIA_ARCHIVAL_INTERVAL_MINUTES")
    
    # Enhanced Channel Context Configuration
    expanded_channel_recent_messages: int = Field(default=15, alias="EXPANDED_CHANNEL_RECENT_MESSAGES")
    collapsed_channel_recent_messages: int = Field(default=5, alias="COLLAPSED_CHANNEL_RECENT_MESSAGES")
    expanded_channel_include_user_context: bool = Field(default=True, alias="EXPANDED_CHANNEL_INCLUDE_USER_CONTEXT")
    expanded_channel_include_thread_context: bool = Field(default=True, alias="EXPANDED_CHANNEL_INCLUDE_THREAD_CONTEXT")
    expanded_channel_include_activity_metrics: bool = Field(default=True, alias="EXPANDED_CHANNEL_INCLUDE_ACTIVITY_METRICS")
    expanded_channel_message_detail_level: str = Field(default="full", alias="EXPANDED_CHANNEL_MESSAGE_DETAIL_LEVEL")
    expanded_channel_include_sentiment: bool = Field(default=True, alias="EXPANDED_CHANNEL_INCLUDE_SENTIMENT")
    expanded_channel_lookback_hours: int = Field(default=6, alias="EXPANDED_CHANNEL_LOOKBACK_HOURS")

    @model_validator(mode='after')
    def validate_global_dependencies(self):
        """Validate global configuration dependencies."""
        # Validate that if mission delegation is enabled, the lightweight AI model is configured
        if self.processing.enable_mission_delegation and not self.processing.lightweight_ai_model:
            raise ValueError(
                "If ENABLE_MISSION_DELEGATION is True, LIGHTWEIGHT_AI_MODEL must be configured"
            )
        
        # Validate that if OpenRouter is the primary provider, API key is present
        if self.primary_llm_provider == "openrouter" and not self.processing.openrouter_api_key:
            raise ValueError(
                "If PRIMARY_LLM_PROVIDER is 'openrouter', OPENROUTER_API_KEY is required"
            )
        
        # Validate NFT configuration dependencies
        if self.nft_dev_wallet_private_key and not self.base_rpc_url:
            raise ValueError(
                "If NFT_DEV_WALLET_PRIVATE_KEY is set, BASE_RPC_URL is required"
            )
            
        return self


# Global settings instance
def create_settings() -> AppConfig:
    """
    Create settings instance with merged configuration from env and config.json.
    
    This function handles the complex mapping between flat environment variables
    and nested Pydantic models, ensuring backward compatibility while providing
    the new structured configuration.
    """
    # Load from config.json first
    json_config = load_config_json()
    
    # Set environment variables from config.json (they will override only if not already set)
    for key, value in json_config.items():
        if key not in os.environ:
            os.environ[key] = str(value)
    
    try:
        return AppConfig()
    except Exception as e:
        print(f"Configuration validation failed: {e}")
        print("Please check your environment variables and ensure all required dependencies are configured.")
        raise


settings = create_settings()
