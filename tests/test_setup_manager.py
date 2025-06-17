"""
Unit tests for SetupManager service.
Testing the conversational setup process validation and workflow.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, mock_open

from chatbot.api_server.services.setup_manager import SetupManager


class TestSetupManager:
    """Test the SetupManager service."""
    
    def test_initialization(self):
        """Test SetupManager initialization."""
        manager = SetupManager()
        assert manager.current_step_index == 0
        assert manager.completed_steps == {}
        assert len(manager.steps) > 0
        assert manager.steps[0]["key"] == "openrouter_api_key"
    
    def test_get_current_step_first(self):
        """Test getting the first step."""
        manager = SetupManager()
        step = manager.get_current_step()
        
        assert step is not None
        assert step["key"] == "openrouter_api_key"
        assert step["type"] == "password"
        assert "OpenRouter API key" in step["question"]
    
    def test_get_current_step_completed(self):
        """Test getting current step when setup is complete."""
        manager = SetupManager()
        manager.current_step_index = len(manager.steps)  # Beyond all steps
        
        step = manager.get_current_step()
        assert step is None
    
    def test_validate_openrouter_api_key_valid(self):
        """Test validation of valid OpenRouter API key."""
        manager = SetupManager()
        step = {"key": "openrouter_api_key", "type": "password"}
        
        result = manager._validate_input(step, "sk-or-" + "x" * 45)
        assert result["valid"] is True
        assert result["message"] == "Valid"
    
    def test_validate_openrouter_api_key_invalid_prefix(self):
        """Test validation of OpenRouter API key with wrong prefix."""
        manager = SetupManager()
        step = {"key": "openrouter_api_key", "type": "password"}
        
        result = manager._validate_input(step, "sk-wrong-prefix")
        assert result["valid"] is False
        assert "should start with 'sk-or-'" in result["message"]
    
    def test_validate_openrouter_api_key_too_short(self):
        """Test validation of OpenRouter API key that's too short."""
        manager = SetupManager()
        step = {"key": "openrouter_api_key", "type": "password"}
        
        result = manager._validate_input(step, "sk-or-short")
        assert result["valid"] is False
        assert "too short" in result["message"]
    
    def test_validate_matrix_homeserver_valid(self):
        """Test validation of valid Matrix homeserver URL."""
        manager = SetupManager()
        step = {"key": "matrix_homeserver", "type": "text"}
        
        result = manager._validate_input(step, "https://matrix.org")
        assert result["valid"] is True
    
    def test_validate_matrix_homeserver_invalid(self):
        """Test validation of invalid Matrix homeserver URL."""
        manager = SetupManager()
        step = {"key": "matrix_homeserver", "type": "text"}
        
        result = manager._validate_input(step, "not-a-url")
        assert result["valid"] is False
        assert "should start with http" in result["message"]
    
    def test_validate_matrix_user_id_valid(self):
        """Test validation of valid Matrix user ID."""
        manager = SetupManager()
        step = {"key": "matrix_user_id", "type": "text"}
        
        result = manager._validate_input(step, "@user:matrix.org")
        assert result["valid"] is True
    
    def test_validate_matrix_user_id_invalid_no_at(self):
        """Test validation of Matrix user ID without @."""
        manager = SetupManager()
        step = {"key": "matrix_user_id", "type": "text"}
        
        result = manager._validate_input(step, "user:matrix.org")
        assert result["valid"] is False
        assert "should start with @" in result["message"]
    
    def test_validate_matrix_user_id_invalid_no_colon(self):
        """Test validation of Matrix user ID without homeserver."""
        manager = SetupManager()
        step = {"key": "matrix_user_id", "type": "text"}
        
        result = manager._validate_input(step, "@user")
        assert result["valid"] is False
        assert "should include the homeserver" in result["message"]
    
    def test_validate_matrix_room_id_valid(self):
        """Test validation of valid Matrix room ID."""
        manager = SetupManager()
        step = {"key": "matrix_room_id", "type": "text"}
        
        result = manager._validate_input(step, "!room:matrix.org")
        assert result["valid"] is True
    
    def test_validate_matrix_room_id_invalid(self):
        """Test validation of invalid Matrix room ID."""
        manager = SetupManager()
        step = {"key": "matrix_room_id", "type": "text"}
        
        result = manager._validate_input(step, "#room:matrix.org")
        assert result["valid"] is False
        assert "should start with !" in result["message"]
    
    def test_validate_empty_value(self):
        """Test validation of empty value."""
        manager = SetupManager()
        step = {"key": "test_key", "type": "text"}
        
        result = manager._validate_input(step, "")
        assert result["valid"] is False
        assert "cannot be empty" in result["message"]
    
    def test_submit_step_success(self):
        """Test successful step submission."""
        manager = SetupManager()
        
        result = manager.submit_step("openrouter_api_key", "sk-or-" + "x" * 45)
        
        assert result["success"] is True
        assert "openrouter_api_key" in manager.completed_steps
        assert manager.current_step_index == 1
        assert result["complete"] is False
        assert "next_step" in result
    
    def test_submit_step_invalid_key(self):
        """Test submitting step with wrong key."""
        manager = SetupManager()
        
        result = manager.submit_step("wrong_key", "some_value")
        
        assert result["success"] is False
        assert "Invalid step" in result["message"]
    
    def test_submit_step_validation_failure(self):
        """Test submitting step with invalid value."""
        manager = SetupManager()
        
        result = manager.submit_step("openrouter_api_key", "invalid-key")
        
        assert result["success"] is False
        assert "should start with 'sk-or-'" in result["message"]
    
    def test_submit_step_skip_farcaster(self):
        """Test skipping Farcaster setup."""
        manager = SetupManager()
        # Advance to farcaster step
        manager.current_step_index = 5  # setup_farcaster step
        
        result = manager.submit_step("setup_farcaster", "no")
        
        assert result["success"] is True
        assert result["complete"] is True
        assert manager.current_step_index >= len(manager.steps)
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.mkdir")
    @patch("json.dump")
    def test_save_configuration(self, mock_json_dump, mock_mkdir, mock_file):
        """Test saving configuration to file."""
        manager = SetupManager()
        manager.completed_steps = {
            "openrouter_api_key": "sk-or-test-key",
            "matrix_homeserver": "https://matrix.org",
            "matrix_user_id": "@test:matrix.org",
            "matrix_password": "password123",
            "matrix_room_id": "!room:matrix.org"
        }
        
        manager._save_configuration()
        
        # Verify file operations
        mock_mkdir.assert_called_once()
        mock_file.assert_called_once()
        mock_json_dump.assert_called_once()
        
        # Check the config structure
        saved_config = mock_json_dump.call_args[0][0]
        assert saved_config["OPENROUTER_API_KEY"] == "sk-or-test-key"
        assert saved_config["MATRIX_HOMESERVER"] == "https://matrix.org"
        assert saved_config["_setup_completed"] is True
        assert "_setup_timestamp" in saved_config
    
    @patch("pathlib.Path.exists")
    @patch("builtins.open", new_callable=mock_open)
    def test_is_setup_required_config_complete(self, mock_file, mock_exists):
        """Test setup not required when config file indicates completion."""
        mock_exists.return_value = True
        mock_file.return_value.read.return_value = json.dumps({
            "_setup_completed": True,
            "OPENROUTER_API_KEY": "sk-or-test",
            "MATRIX_USER_ID": "@test:matrix.org",
            "MATRIX_PASSWORD": "password"
        })
        
        manager = SetupManager()
        result = manager.is_setup_required()
        
        assert result is False
    
    @patch("pathlib.Path.exists")
    def test_is_setup_required_no_config(self, mock_exists):
        """Test setup required when no config file exists."""
        mock_exists.return_value = False
        
        with patch.dict('os.environ', {}, clear=True):
            manager = SetupManager()
            result = manager.is_setup_required()
            
            assert result is True
    
    @patch("pathlib.Path.exists")
    def test_is_setup_required_env_vars_present(self, mock_exists):
        """Test setup not required when environment variables are present."""
        mock_exists.return_value = False
        
        with patch.dict('os.environ', {
            'OPENROUTER_API_KEY': 'sk-or-test',
            'MATRIX_USER_ID': '@test:matrix.org',
            'MATRIX_PASSWORD': 'password'
        }):
            manager = SetupManager()
            result = manager.is_setup_required()
            
            assert result is False
    
    def test_get_setup_status(self):
        """Test getting setup status."""
        manager = SetupManager()
        manager.completed_steps = {"openrouter_api_key": "sk-or-test"}
        manager.current_step_index = 1
        
        status = manager.get_setup_status()
        
        assert "required" in status
        assert "current_step" in status
        assert "progress" in status
        assert status["progress"]["current"] == 2  # 1-indexed
        assert status["progress"]["total"] == len(manager.steps)
        assert "completed_steps" in status
        assert "openrouter_api_key" in status["completed_steps"]
    
    def test_reset_setup(self):
        """Test resetting setup process."""
        manager = SetupManager()
        manager.current_step_index = 3
        manager.completed_steps = {"key1": "value1", "key2": "value2"}
        
        manager.reset_setup()
        
        assert manager.current_step_index == 0
        assert manager.completed_steps == {}
