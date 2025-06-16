import logging

class FarcasterService:
    # ...existing code...
    
    def is_available(self) -> bool:
        """Check if the Farcaster service is available and properly configured."""
        # Add debug logging to understand what's failing
        logger = logging.getLogger(__name__)
        
        try:
            # Check if we have the required configuration
            if not hasattr(self, 'config') or not self.config:
                logger.error("FarcasterService: No config available")
                return False
            
            # Check if we have required API keys/credentials
            if not hasattr(self.config, 'api_key') or not self.config.api_key:
                logger.error("FarcasterService: No API key configured")
                return False
            
            # Check if the client is initialized
            if not hasattr(self, 'client') or not self.client:
                logger.error("FarcasterService: Client not initialized")
                return False
            
            logger.info("FarcasterService: All availability checks passed")
            return True
            
        except Exception as e:
            logger.error(f"FarcasterService: Exception in is_available check: {e}")
            return False