"""
Farcaster Client Factory

This module provides a factory for creating the appropriate Farcaster API client
based on configuration settings.
"""

import logging
from typing import Optional, Union

from ...config import settings
from .neynar_api_client import NeynarAPIClient
from .internal_api_client import InternalFarcasterAPIClient

logger = logging.getLogger(__name__)

# Type alias for any Farcaster client
FarcasterClient = Union[NeynarAPIClient, InternalFarcasterAPIClient]


def create_farcaster_client(
    api_key: Optional[str] = None,
    signer_uuid: Optional[str] = None,
    bot_fid: Optional[str] = None,
    client_type: Optional[str] = None,
    **kwargs
) -> Optional[FarcasterClient]:
    """
    Create a Farcaster API client based on configuration.
    
    Args:
        api_key: Neynar API key (for Neynar client)
        signer_uuid: Signer UUID for posting
        bot_fid: Bot's Farcaster ID
        client_type: Override client type ('neynar', 'internal_api', 'snapchain')
        **kwargs: Additional client-specific parameters
        
    Returns:
        Configured Farcaster client instance or None if not configured
    """
    # Determine client type from config or parameter
    client_type = client_type or settings.farcaster.client_type
    
    logger.info(f"Creating Farcaster client of type: {client_type}")
    
    try:
        if client_type == "neynar":
            return _create_neynar_client(api_key, signer_uuid, bot_fid, **kwargs)
        elif client_type == "internal_api":
            return _create_internal_api_client(signer_uuid, bot_fid, **kwargs)
        elif client_type == "snapchain":
            # Note: Direct Snapchain client would be complex to implement here
            # For now, we recommend using the internal_api approach
            logger.warning(
                "Direct Snapchain client not implemented. "
                "Use 'internal_api' client type with farcaster-api-service instead."
            )
            return None
        else:
            logger.error(f"Unknown Farcaster client type: {client_type}")
            return None
            
    except Exception as e:
        logger.error(f"Failed to create Farcaster client: {e}")
        return None


def _create_neynar_client(
    api_key: Optional[str],
    signer_uuid: Optional[str],
    bot_fid: Optional[str],
    **kwargs
) -> Optional[NeynarAPIClient]:
    """Create a Neynar API client."""
    # Use provided API key or fall back to config
    api_key = api_key or settings.farcaster.neynar_api_key
    
    if not api_key:
        logger.warning("No Neynar API key available - Farcaster integration will be disabled")
        return None
    
    # Use provided values or fall back to config
    signer_uuid = signer_uuid or settings.farcaster.bot_signer_uuid
    bot_fid = bot_fid or settings.farcaster.bot_fid
    
    logger.info("Creating Neynar API client")
    return NeynarAPIClient(
        api_key=api_key,
        signer_uuid=signer_uuid,
        bot_fid=bot_fid,
        **kwargs
    )


def _create_internal_api_client(
    signer_uuid: Optional[str],
    bot_fid: Optional[str],
    **kwargs
) -> Optional[InternalFarcasterAPIClient]:
    """Create an internal API client."""
    # Get internal API URL from config
    base_url = settings.farcaster.internal_api_url
    
    if not base_url:
        logger.error("No internal API URL configured - cannot create internal API client")
        return None
    
    # Use provided values or fall back to config
    signer_uuid = signer_uuid or settings.farcaster.bot_signer_uuid
    bot_fid = bot_fid or settings.farcaster.bot_fid
    
    # Get Neynar API key for fallback operations
    neynar_api_key = settings.farcaster.neynar_api_key
    
    logger.info(f"Creating internal API client for: {base_url}")
    if neynar_api_key:
        logger.info("Neynar fallback enabled for unsupported operations")
    else:
        logger.warning("No Neynar API key - some operations will not be available")
    
    return InternalFarcasterAPIClient(
        base_url=base_url,
        api_key=neynar_api_key,  # Pass Neynar key for fallback
        signer_uuid=signer_uuid,
        bot_fid=bot_fid,
        **kwargs
    )


def get_client_info(client: Optional[FarcasterClient]) -> dict:
    """
    Get information about a Farcaster client.
    
    Args:
        client: The client instance
        
    Returns:
        Dictionary containing client information
    """
    if not client:
        return {"type": "none", "status": "not_configured"}
    
    if isinstance(client, NeynarAPIClient):
        return {
            "type": "neynar",
            "status": "configured",
            "base_url": getattr(client, 'base_url', 'unknown'),
            "has_api_key": bool(getattr(client, 'api_key', None)),
            "signer_uuid": getattr(client, 'signer_uuid', None),
            "bot_fid": getattr(client, 'bot_fid', None)
        }
    elif isinstance(client, InternalFarcasterAPIClient):
        return {
            "type": "internal_api",
            "status": "configured", 
            "base_url": getattr(client, 'base_url', 'unknown'),
            "signer_uuid": getattr(client, 'signer_uuid', None),
            "bot_fid": getattr(client, 'bot_fid', None)
        }
    else:
        return {
            "type": "unknown",
            "status": "configured",
            "class": client.__class__.__name__
        }
