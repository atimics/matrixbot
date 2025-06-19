"""
Matrix Authentication Handler

Handles Matrix client authentication, token management, and session persistence.
"""

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

from nio import AsyncClient, LoginResponse

logger = logging.getLogger(__name__)


class MatrixAuthHandler:
    """Handles Matrix authentication and token management."""
    
    def __init__(self, homeserver: str, user_id: str, password: str, store_path: Path):
        self.homeserver = homeserver
        self.user_id = user_id
        self.password = password
        self.store_path = store_path
        self.token_file = store_path / "matrix_token.json"
    
    async def load_token(self) -> Optional[str]:
        """Load access token from file if it exists and is valid."""
        if not self.token_file.exists():
            logger.debug("MatrixAuthHandler: No token file found")
            return None
            
        try:
            with open(self.token_file, 'r') as f:
                token_data = json.load(f)
            
            access_token = token_data.get('access_token')
            device_id = token_data.get('device_id')
            
            if not access_token:
                logger.warning("MatrixAuthHandler: Token file exists but no access_token found")
                return None
                
            logger.debug("MatrixAuthHandler: Loaded existing token")
            return access_token
            
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"MatrixAuthHandler: Error loading token file: {e}")
            return None
    
    async def verify_token_with_backoff(self, client: AsyncClient, max_retries: int = 3) -> bool:
        """Verify token is valid with exponential backoff."""
        for attempt in range(max_retries):
            try:
                # Test the token by making a simple API call
                response = await client.whoami()
                if hasattr(response, 'user_id') and response.user_id == self.user_id:
                    logger.debug("MatrixAuthHandler: Token verification successful")
                    return True
                else:
                    logger.warning("MatrixAuthHandler: Token verification failed - user mismatch")
                    return False
                    
            except Exception as e:
                delay = 2 ** attempt  # Exponential backoff
                logger.warning(
                    f"MatrixAuthHandler: Token verification attempt {attempt + 1} failed: {e}. "
                    f"Retrying in {delay}s..."
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(delay)
                else:
                    logger.error("MatrixAuthHandler: Token verification failed after all retries")
                    return False
        
        return False
    
    async def save_token(self, access_token: str, device_id: str):
        """Save access token and device ID to file."""
        try:
            token_data = {
                'access_token': access_token,
                'device_id': device_id,
                'user_id': self.user_id,
                'homeserver': self.homeserver,
                'saved_at': time.time()
            }
            
            # Ensure directory exists
            self.token_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.token_file, 'w') as f:
                json.dump(token_data, f, indent=2)
                
            # Set restrictive permissions
            os.chmod(self.token_file, 0o600)
            logger.info("MatrixAuthHandler: Token saved successfully")
            
        except Exception as e:
            logger.error(f"MatrixAuthHandler: Error saving token: {e}")
    
    async def login_with_retry(self, client: AsyncClient, max_attempts: int = 3) -> Optional[str]:
        """Attempt login with retry logic and rate limit handling."""
        for attempt in range(max_attempts):
            try:
                logger.info(f"MatrixAuthHandler: Login attempt {attempt + 1} for {self.user_id}")
                
                response = await client.login(self.password)
                
                if isinstance(response, LoginResponse):
                    logger.info("MatrixAuthHandler: Login successful")
                    await self.save_token(response.access_token, response.device_id)
                    return response.access_token
                else:
                    logger.error(f"MatrixAuthHandler: Login failed: {response}")
                    return None
                    
            except Exception as login_error:
                error_str = str(login_error)
                
                # Handle rate limiting
                if '429' in error_str or 'rate' in error_str.lower():
                    delay = min(60, 2 ** attempt * 5)  # Cap at 60 seconds
                    logger.warning(
                        f"MatrixAuthHandler: Rate limited on attempt {attempt + 1}. "
                        f"Waiting {delay}s before retry..."
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"MatrixAuthHandler: Login attempt {attempt + 1} failed: {login_error}")
                    
                if attempt == max_attempts - 1:
                    raise login_error
        
        return None
    
    async def handle_auth_error(self, error: Exception) -> bool:
        """Handle authentication errors and attempt recovery."""
        error_str = str(error)
        
        # Check for token expiration
        if any(keyword in error_str.lower() for keyword in ['token', 'auth', 'unauthorized', '401']):
            logger.warning("MatrixAuthHandler: Authentication error detected, clearing saved token")
            
            # Remove invalid token
            if self.token_file.exists():
                try:
                    self.token_file.unlink()
                    logger.info("MatrixAuthHandler: Cleared invalid token file")
                except Exception as e:
                    logger.error(f"MatrixAuthHandler: Error removing token file: {e}")
            
            return True  # Indicate that re-authentication should be attempted
        
        return False  # Other types of errors
    
    def clear_token(self):
        """Clear saved token file."""
        if self.token_file.exists():
            try:
                self.token_file.unlink()
                logger.info("MatrixAuthHandler: Cleared token file")
            except Exception as e:
                logger.error(f"MatrixAuthHandler: Error clearing token file: {e}")
