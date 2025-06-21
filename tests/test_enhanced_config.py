"""
Tests for the enhanced configuration system.
"""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, mock_open
import json

from chatbot.config.enhanced_config import (
    CoreConfig, AIConfig, MatrixConfig, FarcasterConfig, 
    MediaConfig, SecurityConfig, PerformanceConfig, AppConfig
)
from chatbot.config.secret_manager import (
    SecretManager, SecretConfig, SecretBackend,
    EnvironmentSecretProvider, LocalEncryptedSecretProvider
)


class TestCoreConfig:
    """Test CoreConfig validation and defaults."""
    
    def test_defaults(self):
        """Test default values."""
        config = CoreConfig()
        assert config.db_path == "data/chatbot.db"
        assert config.log_level == "INFO"
        assert config.observation_interval == 2.0
        assert config.max_cycles_per_hour == 300
        assert config.device_name == "ratichat_bot"
    
    def test_log_level_validation(self):
        """Test log level validation."""
        config = CoreConfig(log_level="DEBUG")
        assert config.log_level == "DEBUG"
        
        config = CoreConfig(log_level="debug")  # Should be uppercased
        assert config.log_level == "DEBUG"
        
        with pytest.raises(ValueError, match="Log level must be one of"):
            CoreConfig(log_level="INVALID")
    
    def test_observation_interval_validation(self):
        """Test observation interval validation."""
        config = CoreConfig(observation_interval=5.0)
        assert config.observation_interval == 5.0
        
        with pytest.raises(ValueError, match="must be positive"):
            CoreConfig(observation_interval=0)
        
        with pytest.raises(ValueError, match="must be positive"):
            CoreConfig(observation_interval=-1)


class TestAIConfig:
    """Test AIConfig validation and defaults."""
    
    def test_defaults(self):
        """Test default values."""
        config = AIConfig()
        assert config.primary_model == "openai/gpt-4o-mini"
        assert config.conversation_history_length == 3
        assert config.enable_prompt_logging is True
        assert config.log_full_prompts is False
    
    def test_history_length_validation(self):
        """Test history length validation."""
        config = AIConfig(conversation_history_length=5)
        assert config.conversation_history_length == 5
        
        with pytest.raises(ValueError, match="must be at least 1"):
            AIConfig(conversation_history_length=0)
        
        with pytest.raises(ValueError, match="must be at least 1"):
            AIConfig(action_history_length=-1)


class TestMatrixConfig:
    """Test MatrixConfig validation."""
    
    def test_defaults(self):
        """Test default values."""
        config = MatrixConfig()
        assert config.homeserver is None
        assert config.user_id is None
        assert config.room_id == "#robot-laboratory:chat.ratimics.com"
    
    def test_homeserver_validation(self):
        """Test homeserver URL validation."""
        config = MatrixConfig(homeserver="https://matrix.org")
        assert config.homeserver == "https://matrix.org"
        
        config = MatrixConfig(homeserver="http://localhost:8008")
        assert config.homeserver == "http://localhost:8008"
        
        with pytest.raises(ValueError, match="must start with http"):
            MatrixConfig(homeserver="matrix.org")
    
    def test_user_id_validation(self):
        """Test Matrix user ID validation."""
        config = MatrixConfig(user_id="@user:matrix.org")
        assert config.user_id == "@user:matrix.org"
        
        with pytest.raises(ValueError, match="must start with @"):
            MatrixConfig(user_id="user:matrix.org")
        
        with pytest.raises(ValueError, match="must include homeserver domain"):
            MatrixConfig(user_id="@user")
    
    def test_room_id_validation(self):
        """Test Matrix room ID validation."""
        config = MatrixConfig(room_id="!room:matrix.org")
        assert config.room_id == "!room:matrix.org"
        
        config = MatrixConfig(room_id="#room:matrix.org")
        assert config.room_id == "#room:matrix.org"
        
        with pytest.raises(ValueError, match="must start with ! or #"):
            MatrixConfig(room_id="room:matrix.org")


class TestFarcasterConfig:
    """Test FarcasterConfig validation."""
    
    def test_defaults(self):
        """Test default values."""
        config = FarcasterConfig()
        assert config.min_post_interval_minutes == 1
        assert config.api_timeout == 30.0
        assert config.api_max_retries == 3
    
    def test_positive_integer_validation(self):
        """Test positive integer validation."""
        config = FarcasterConfig(min_post_interval_minutes=5)
        assert config.min_post_interval_minutes == 5
        
        config = FarcasterConfig(duplicate_check_hours=0)  # Zero should be allowed
        assert config.duplicate_check_hours == 0
        
        with pytest.raises(ValueError, match="must be non-negative"):
            FarcasterConfig(min_post_interval_minutes=-1)


class TestUnifiedSettings:
    """Test the unified settings system."""
    
    def test_initialization(self):
        """Test basic initialization."""
        settings = UnifiedSettings()
        assert isinstance(settings.core, CoreConfig)
        assert isinstance(settings.ai, AIConfig)
        assert isinstance(settings.matrix, MatrixConfig)
        assert isinstance(settings.farcaster, FarcasterConfig)
        assert isinstance(settings.media, MediaConfig)
        assert isinstance(settings.security, SecurityConfig)
        assert isinstance(settings.performance, PerformanceConfig)
    
    @patch('pathlib.Path.exists')
    @patch('builtins.open', new_callable=mock_open)
    def test_config_json_loading(self, mock_file, mock_exists):
        """Test loading configuration from config.json."""
        mock_exists.return_value = True
        mock_file.return_value.read.return_value = json.dumps({
            "openrouter_api_key": "sk-or-test-key",
            "matrix_password": "test-password",
            "MATRIX_USER_ID": "@test:matrix.org",
            "_setup_completed": True,
            "_setup_timestamp": "2023-10-26T10:00:00"
        })
        
        settings = UnifiedSettings()
        
        # Verify secrets are loaded
        assert settings.openrouter_api_key == "sk-or-test-key"
        assert settings.matrix.password == "test-password"
        
        # Verify metadata is filtered out
        assert not hasattr(settings, '_setup_completed')
    
    def test_config_status(self):
        """Test configuration status reporting."""
        settings = UnifiedSettings(
            openrouter_api_key="sk-or-test",
            matrix_password="test-pass",
            neynar_api_key="test-neynar"
        )
        settings.matrix.user_id = "@test:matrix.org"
        settings.farcaster.bot_fid = "12345"
        
        status = settings.get_config_status()
        
        assert status["ai_configured"] is True
        assert status["matrix_configured"] is True
        assert status["farcaster_configured"] is True
        assert status["secrets_configured"] == 3
        assert status["security_hardened"] is True  # Default CORS origins are restrictive
    
    def test_legacy_format_conversion(self):
        """Test conversion to legacy format."""
        settings = UnifiedSettings(
            openrouter_api_key="sk-or-test",
            matrix_password="test-pass"
        )
        settings.core.db_path = "custom/path.db"
        settings.ai.primary_model = "custom/model"
        settings.matrix.user_id = "@test:matrix.org"
        
        legacy = settings.to_legacy_format()
        
        assert legacy["CHATBOT_DB_PATH"] == "custom/path.db"
        assert legacy["AI_MODEL"] == "custom/model"
        assert legacy["MATRIX_USER_ID"] == "@test:matrix.org"
        assert legacy["OPENROUTER_API_KEY"] == "sk-or-test"
        assert legacy["MATRIX_PASSWORD"] == "test-pass"
    
    def test_environment_override(self):
        """Test environment variable override."""
        with patch.dict(os.environ, {
            'OPENROUTER_API_KEY': 'env-key',
            'MATRIX_PASSWORD': 'env-password'
        }):
            settings = UnifiedSettings()
            assert settings.openrouter_api_key == 'env-key'
            assert settings.matrix.password == 'env-password'


class TestSecretManager:
    """Test the secret management system."""
    
    def test_environment_provider(self):
        """Test environment variable provider."""
        provider = EnvironmentSecretProvider()
        
        with patch.dict(os.environ, {'TEST_SECRET': 'test-value'}):
            secret = provider.get_secret('TEST_SECRET')
            assert secret == 'test-value'
            
            # Test setting
            provider.set_secret('NEW_SECRET', 'new-value')
            assert os.environ['NEW_SECRET'] == 'new-value'
            
            # Test listing
            secrets = provider.list_secrets()
            assert 'TEST_SECRET' in secrets
            assert 'NEW_SECRET' in secrets
    
    def test_local_encrypted_provider(self):
        """Test local encrypted file provider."""
        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_path = Path(tmpdir) / "secrets.enc"
            key_path = Path(tmpdir) / "secrets.key"
            
            provider = LocalEncryptedSecretProvider(str(secrets_path), str(key_path))
            
            # Test key and file creation
            assert key_path.exists()
            assert secrets_path.exists()
            
            # Test setting and getting
            result = provider.set_secret('TEST_KEY', 'test-value')
            assert result is True
            
            secret = provider.get_secret('TEST_KEY')
            assert secret == 'test-value'
            
            # Test listing
            secrets = provider.list_secrets()
            assert 'TEST_KEY' in secrets
            
            # Test deletion
            result = provider.delete_secret('TEST_KEY')
            assert result is True
            
            secret = provider.get_secret('TEST_KEY')
            assert secret is None
    
    def test_secret_manager_creation(self):
        """Test secret manager creation."""
        config = SecretConfig(backend=SecretBackend.ENVIRONMENT)
        manager = SecretManager(config)
        
        assert isinstance(manager.provider, EnvironmentSecretProvider)
        
        backend_info = manager.get_backend_info()
        assert backend_info["backend"] == "environment"
        assert backend_info["provider_type"] == "EnvironmentSecretProvider"
    
    def test_secret_manager_multiple_secrets(self):
        """Test getting multiple secrets."""
        config = SecretConfig(backend=SecretBackend.ENVIRONMENT)
        manager = SecretManager(config)
        
        with patch.dict(os.environ, {
            'SECRET1': 'value1',
            'SECRET2': 'value2',
            'SECRET3': 'value3'
        }):
            secrets = manager.get_multiple_secrets(['SECRET1', 'SECRET2', 'MISSING'])
            
            assert secrets['SECRET1'] == 'value1'
            assert secrets['SECRET2'] == 'value2'
            assert secrets['MISSING'] is None
    
    def test_invalid_backend(self):
        """Test invalid backend configuration."""
        config = SecretConfig(backend="invalid")
        
        with pytest.raises(ValueError, match="Unsupported secret backend"):
            SecretManager(config)
    
    def test_vault_config_validation(self):
        """Test Vault configuration validation."""
        config = SecretConfig(backend=SecretBackend.VAULT)
        
        with pytest.raises(ValueError, match="Vault URL and token required"):
            SecretManager(config)
