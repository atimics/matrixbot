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
    security: SecurityConfig = SecurityConfig()
    ecosystem: EcosystemConfig = EcosystemConfig()
    node_system: NodeSystemConfig = NodeSystemConfig()


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
