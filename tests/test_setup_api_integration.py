"""
Integration tests for the Setup API endpoints.
Testing the FastAPI routers with dependency injection.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch

from chatbot.api_server.secure_server import create_secure_api_server
from chatbot.api_server.services.setup_manager import SetupManager


class TestSetupAPIEndpoints:
    """Test setup API endpoints with FastAPI TestClient."""
    
    def setup_method(self):
        """Set up test client and mock setup manager."""
        app = create_secure_api_server()
        self.client = TestClient(app)
        self.mock_setup_manager = Mock(spec=SetupManager)
    
    def test_start_setup_required(self):
        """Test starting setup when setup is required."""
        # Mock setup manager
        self.mock_setup_manager.is_setup_required.return_value = True
        self.mock_setup_manager.get_current_step.return_value = {
            "key": "openrouter_api_key",
            "question": "Please provide your OpenRouter API key:",
            "type": "password"
        }
        
        with patch('chatbot.api_server.dependencies.get_setup_manager', return_value=self.mock_setup_manager):
            response = self.client.get("/api/setup/start")
        
        assert response.status_code == 200
        data = response.json()
        assert data["complete"] is False
        assert "Welcome!" in data["message"]
        assert data["step"]["key"] == "openrouter_api_key"
    
    def test_start_setup_complete(self):
        """Test starting setup when setup is already complete."""
        self.mock_setup_manager.is_setup_required.return_value = False
        
        with patch('chatbot.api_server.dependencies.get_setup_manager', return_value=self.mock_setup_manager):
            response = self.client.get("/api/setup/start")
        
        assert response.status_code == 200
        data = response.json()
        assert data["complete"] is True
        assert "Setup is already complete" in data["message"]
        assert data["step"] is None
    
    def test_start_setup_error(self):
        """Test error handling in start setup endpoint."""
        self.mock_setup_manager.is_setup_required.side_effect = Exception("Database error")
        
        with patch('chatbot.api_server.dependencies.get_setup_manager', return_value=self.mock_setup_manager):
            response = self.client.get("/api/setup/start")
        
        assert response.status_code == 500
        assert "Database error" in response.json()["detail"]
    
    def test_submit_setup_step_success(self):
        """Test successful setup step submission."""
        self.mock_setup_manager.submit_step.return_value = {
            "success": True,
            "message": "Great! Moving to the next step...",
            "complete": False,
            "next_step": {
                "key": "matrix_homeserver",
                "question": "Next, I need your Matrix homeserver URL:",
                "type": "text"
            }
        }
        
        with patch('chatbot.api_server.dependencies.get_setup_manager', return_value=self.mock_setup_manager):
            response = self.client.post("/api/setup/submit", json={
                "step_key": "openrouter_api_key",
                "value": "sk-or-test-api-key-12345678901234567890123456789"
            })
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["complete"] is False
        assert "next_step" in data
        assert data["next_step"]["key"] == "matrix_homeserver"
    
    def test_submit_setup_step_validation_error(self):
        """Test setup step submission with validation error."""
        self.mock_setup_manager.submit_step.return_value = {
            "success": False,
            "message": "OpenRouter API keys should start with 'sk-or-'"
        }
        
        with patch('chatbot.api_server.dependencies.get_setup_manager', return_value=self.mock_setup_manager):
            response = self.client.post("/api/setup/submit", json={
                "step_key": "openrouter_api_key",
                "value": "invalid-key"
            })
        
        assert response.status_code == 400
        assert "should start with 'sk-or-'" in response.json()["detail"]
    
    def test_submit_setup_step_complete(self):
        """Test setup step submission that completes setup."""
        self.mock_setup_manager.submit_step.return_value = {
            "success": True,
            "message": "Perfect! All configurations are complete.",
            "complete": True
        }
        
        with patch('chatbot.api_server.dependencies.get_setup_manager', return_value=self.mock_setup_manager):
            response = self.client.post("/api/setup/submit", json={
                "step_key": "setup_farcaster",
                "value": "no"
            })
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["complete"] is True
        assert "next_step" not in data
    
    def test_submit_setup_step_server_error(self):
        """Test setup step submission with server error."""
        self.mock_setup_manager.submit_step.side_effect = Exception("Database connection failed")
        
        with patch('chatbot.api_server.dependencies.get_setup_manager', return_value=self.mock_setup_manager):
            response = self.client.post("/api/setup/submit", json={
                "step_key": "openrouter_api_key",
                "value": "sk-or-test-key"
            })
        
        assert response.status_code == 500
        assert "Database connection failed" in response.json()["detail"]
    
    def test_reset_setup_success(self):
        """Test successful setup reset."""
        with patch('chatbot.api_server.dependencies.get_setup_manager', return_value=self.mock_setup_manager):
            response = self.client.post("/api/setup/reset")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "reset" in data["message"]
        self.mock_setup_manager.reset_setup.assert_called_once()
    
    def test_reset_setup_error(self):
        """Test setup reset with error."""
        self.mock_setup_manager.reset_setup.side_effect = Exception("Reset failed")
        
        with patch('chatbot.api_server.dependencies.get_setup_manager', return_value=self.mock_setup_manager):
            response = self.client.post("/api/setup/reset")
        
        assert response.status_code == 500
        assert "Reset failed" in response.json()["detail"]
    
    def test_get_setup_status_success(self):
        """Test getting setup status successfully."""
        self.mock_setup_manager.get_setup_status.return_value = {
            "required": True,
            "current_step": {
                "key": "openrouter_api_key",
                "question": "Please provide your OpenRouter API key:",
                "type": "password"
            },
            "progress": {"current": 1, "total": 6},
            "completed_steps": []
        }
        
        with patch('chatbot.api_server.dependencies.get_setup_manager', return_value=self.mock_setup_manager):
            response = self.client.get("/api/setup/status")
        
        assert response.status_code == 200
        data = response.json()
        assert data["required"] is True
        assert data["current_step"]["key"] == "openrouter_api_key"
        assert data["progress"]["current"] == 1
        assert data["progress"]["total"] == 6
    
    def test_get_setup_status_error(self):
        """Test getting setup status with error."""
        self.mock_setup_manager.get_setup_status.side_effect = Exception("Status check failed")
        
        with patch('chatbot.api_server.dependencies.get_setup_manager', return_value=self.mock_setup_manager):
            response = self.client.get("/api/setup/status")
        
        assert response.status_code == 500
        assert "Status check failed" in response.json()["detail"]
    
    def test_invalid_json_payload(self):
        """Test submitting invalid JSON payload."""
        with patch('chatbot.api_server.dependencies.get_setup_manager', return_value=self.mock_setup_manager):
            response = self.client.post("/api/setup/submit", json={
                "invalid_field": "value"
            })
        
        assert response.status_code == 422  # Validation error
    
    def test_missing_required_fields(self):
        """Test submitting payload missing required fields."""
        with patch('chatbot.api_server.dependencies.get_setup_manager', return_value=self.mock_setup_manager):
            response = self.client.post("/api/setup/submit", json={
                "step_key": "openrouter_api_key"
                # Missing 'value' field
            })
        
        assert response.status_code == 422  # Validation error
    
    def test_empty_string_values(self):
        """Test submitting empty string values."""
        self.mock_setup_manager.submit_step.return_value = {
            "success": False,
            "message": "This field cannot be empty"
        }
        
        with patch('chatbot.api_server.dependencies.get_setup_manager', return_value=self.mock_setup_manager):
            response = self.client.post("/api/setup/submit", json={
                "step_key": "openrouter_api_key",
                "value": ""
            })
        
        assert response.status_code == 400
        assert "cannot be empty" in response.json()["detail"]
