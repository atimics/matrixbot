"""
Setup Manager service for handling the conversational setup process.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from chatbot.core.secrets import get_secret_manager

logger = logging.getLogger(__name__)


class SetupManager:
    """Manages the conversational setup process."""
    
    def __init__(self):
        self.steps = [
            {
                "key": "openrouter_api_key",
                "question": "I need your OpenRouter API key to access language models. Please provide your OpenRouter API key:",
                "type": "password",
                "validation": "This should start with 'sk-or-' and be about 51 characters long"
            },
            {
                "key": "matrix_homeserver",
                "question": "Next, I need your Matrix homeserver URL (e.g., https://matrix.org):",
                "type": "text",
                "validation": "This should be a valid URL starting with https://"
            },
            {
                "key": "matrix_user_id",
                "question": "What is your Matrix user ID? (e.g., @username:matrix.org):",
                "type": "text",
                "validation": "This should start with @ and include your homeserver domain"
            },
            {
                "key": "matrix_password",
                "question": "Please provide your Matrix password:",
                "type": "password"
            },
            {
                "key": "matrix_room_id",
                "question": "What Matrix room should I join? Provide the room ID (e.g., !roomid:matrix.org):",
                "type": "text",
                "validation": "This should start with ! and include your homeserver domain"
            },
            {
                "key": "setup_farcaster",
                "question": "Would you like to configure Farcaster integration? (optional)",
                "type": "select",
                "options": ["yes", "no", "skip"]
            }
        ]
        self.current_step_index = 0
        self.completed_steps = {}
    
    def get_current_step(self) -> Optional[Dict]:
        """Get the current setup step."""
        if self.current_step_index >= len(self.steps):
            return None
        return self.steps[self.current_step_index]
    
    async def submit_step(self, step_key: str, value: str) -> dict:
        """Submit a step and advance to the next one."""
        current_step = self.get_current_step()
        if not current_step or current_step["key"] != step_key:
            return {"success": False, "message": "Invalid step"}
        
        # Validate the input
        validation_result = self._validate_input(current_step, value)
        if not validation_result["valid"]:
            return {"success": False, "message": validation_result["message"]}
        
        # Store the value
        self.completed_steps[step_key] = value
        
        # Handle special cases
        if step_key == "setup_farcaster" and value in ["no", "skip"]:
            # Skip farcaster steps and go to completion
            self.current_step_index = len(self.steps)
        else:
            self.current_step_index += 1
        
        # Check if setup is complete
        if self.current_step_index >= len(self.steps):
            try:
                await self._save_configuration()
                return {
                    "success": True,
                    "message": "Perfect! All configurations are complete. Initializing systems...",
                    "complete": True
                }
            except Exception as e:
                return {
                    "success": False,
                    "message": f"Failed to save configuration: {str(e)}",
                    "complete": False
                }
        
        # Return next step
        next_step = self.get_current_step()
        return {
            "success": True,
            "message": "Great! Moving to the next step...",
            "next_step": next_step,
            "complete": False
        }
    
    def _validate_input(self, step: dict, value: str) -> dict:
        """Validate user input for a step."""
        if not value.strip():
            return {"valid": False, "message": "This field cannot be empty"}
        
        step_key = step["key"]
        if step_key == "openrouter_api_key":
            if not value.startswith("sk-or-"):
                return {"valid": False, "message": "OpenRouter API keys should start with 'sk-or-'"}
            if len(value) < 40:
                return {"valid": False, "message": "This seems too short for an API key"}
        
        elif step_key == "matrix_homeserver":
            if not (value.startswith("http://") or value.startswith("https://")):
                return {"valid": False, "message": "Homeserver URL should start with http:// or https://"}
        
        elif step_key == "matrix_user_id":
            if not value.startswith("@"):
                return {"valid": False, "message": "Matrix user IDs should start with @"}
            if ":" not in value:
                return {"valid": False, "message": "Matrix user IDs should include the homeserver (e.g., @user:matrix.org)"}
        
        elif step_key == "matrix_room_id":
            if not value.startswith("!"):
                return {"valid": False, "message": "Matrix room IDs should start with !"}
        
        return {"valid": True, "message": "Valid"}
    
    async def _save_configuration(self):
        """Save the configuration securely using the SecretManager."""
        try:
            # Get the secret manager
            secret_manager = get_secret_manager()
            
            # Map our step keys to secret keys
            step_to_secret = {
                "openrouter_api_key": "OPENROUTER_API_KEY",
                "matrix_homeserver": "MATRIX_HOMESERVER",
                "matrix_user_id": "MATRIX_USER_ID", 
                "matrix_password": "MATRIX_PASSWORD",
                "matrix_room_id": "MATRIX_ROOM_ID"
            }
            
            # Save each secret securely
            for step_key, secret_key in step_to_secret.items():
                if step_key in self.completed_steps:
                    await secret_manager.set_secret(secret_key, self.completed_steps[step_key])
                    logger.info(f"Securely stored {secret_key}")
            
            # Save setup completion flag
            await secret_manager.set_secret("SETUP_COMPLETED", "true")
            await secret_manager.set_secret("SETUP_TIMESTAMP", datetime.now().isoformat())
            
            logger.info("Configuration saved securely using SecretManager")
            
        except Exception as e:
            logger.error(f"Failed to save configuration securely: {e}")
            raise
    
    async def is_setup_required(self) -> bool:
        """Check if setup is required by looking for essential secrets."""
        try:
            # Get the secret manager
            secret_manager = get_secret_manager()
            
            # Check if setup was completed
            setup_completed = await secret_manager.get_secret("SETUP_COMPLETED")
            if setup_completed == "true":
                # Verify essential secrets are present
                required_secrets = ["OPENROUTER_API_KEY", "MATRIX_USER_ID", "MATRIX_PASSWORD"]
                for secret_key in required_secrets:
                    secret_value = await secret_manager.get_secret(secret_key)
                    if not secret_value:
                        return True
                return False
            
            # Fall back to checking environment variables
            required_vars = ["OPENROUTER_API_KEY", "MATRIX_USER_ID", "MATRIX_PASSWORD"]
            for var in required_vars:
                if not os.getenv(var):
                    return True
            return False
            
        except Exception as e:
            logger.warning(f"Error checking setup requirements: {e}")
            # Fall back to environment variable check
            required_vars = ["OPENROUTER_API_KEY", "MATRIX_USER_ID", "MATRIX_PASSWORD"]
            for var in required_vars:
                if not os.getenv(var):
                    return True
            return False
    
    def get_setup_status(self) -> dict:
        """Get the current setup status."""
        return {
            "required": self.is_setup_required(),
            "current_step": self.get_current_step(),
            "progress": {
                "current": self.current_step_index + 1,
                "total": len(self.steps)
            },
            "completed_steps": list(self.completed_steps.keys())
        }
    
    def reset_setup(self):
        """Reset the setup process."""
        self.current_step_index = 0
        self.completed_steps = {}
