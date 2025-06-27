"""
Farcaster Webhook Handler

Handles incoming webhook events from Farcaster (via Neynar) for real-time notifications.
This provides faster response to mentions, follows, and other events.
"""

import asyncio
import json
import logging
from typing import Any, Dict, Optional

from fastapi import HTTPException, Request

from ...core.world_state import WorldStateManager

logger = logging.getLogger(__name__)


class FarcasterWebhookHandler:
    """Handles incoming Farcaster webhook events"""

    def __init__(self, world_state_manager: WorldStateManager):
        self.world_state = world_state_manager
        self.webhook_secret: Optional[str] = None  # For verifying webhook authenticity

    def set_webhook_secret(self, secret: str):
        """Set the webhook secret for verification"""
        self.webhook_secret = secret

    async def handle_webhook(self, request: Request) -> Dict[str, str]:
        """
        Handle incoming webhook from Farcaster/Neynar
        
        Args:
            request: FastAPI request object containing webhook payload
            
        Returns:
            Dict with status response
            
        Raises:
            HTTPException: If webhook verification fails or payload is invalid
        """
        try:
            # Get raw body for signature verification
            body = await request.body()
            headers = request.headers
            
            # Verify webhook signature if secret is configured
            if self.webhook_secret:
                await self._verify_webhook_signature(body, headers)
            
            # Parse JSON payload
            try:
                payload = json.loads(body.decode('utf-8'))
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in webhook payload: {e}")
                raise HTTPException(status_code=400, detail="Invalid JSON payload")
            
            # Process the webhook event
            await self._process_webhook_event(payload)
            
            return {"status": "success", "message": "Webhook processed"}
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error processing Farcaster webhook: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    async def _verify_webhook_signature(self, body: bytes, headers: Dict[str, str]):
        """
        Verify webhook signature using HMAC-SHA256
        
        Args:
            body: Raw request body
            headers: Request headers containing signature
            
        Raises:
            HTTPException: If signature verification fails
        """
        import hmac
        import hashlib
        
        # Get signature from headers (Neynar uses 'x-neynar-signature')
        signature_header = headers.get('x-neynar-signature') or headers.get('x-hub-signature-256')
        
        if not signature_header:
            logger.warning("Webhook received without signature header")
            raise HTTPException(status_code=401, detail="Missing signature header")
        
        # Remove 'sha256=' prefix if present
        if signature_header.startswith('sha256='):
            signature_header = signature_header[7:]
        
        # Calculate expected signature
        expected_signature = hmac.new(
            self.webhook_secret.encode('utf-8'),
            body,
            hashlib.sha256
        ).hexdigest()
        
        # Compare signatures
        if not hmac.compare_digest(signature_header, expected_signature):
            logger.warning("Webhook signature verification failed")
            raise HTTPException(status_code=401, detail="Invalid signature")

    async def _process_webhook_event(self, payload: Dict[str, Any]):
        """
        Process the webhook event and update world state
        
        Args:
            payload: Parsed webhook payload
        """
        event_type = payload.get('type')
        data = payload.get('data', {})
        
        logger.info(f"Processing Farcaster webhook event: {event_type}")
        
        try:
            if event_type == 'cast.created':
                await self._handle_cast_created(data)
            elif event_type == 'cast.mention':
                await self._handle_mention(data)
            elif event_type == 'reaction.created':
                await self._handle_reaction_created(data)
            elif event_type == 'follow.created':
                await self._handle_follow_created(data)
            elif event_type == 'cast.reply':
                await self._handle_cast_reply(data)
            else:
                logger.info(f"Unhandled webhook event type: {event_type}")
                
        except Exception as e:
            logger.error(f"Error processing webhook event {event_type}: {e}")

    async def _handle_cast_created(self, data: Dict[str, Any]):
        """Handle new cast creation event"""
        cast = data.get('cast', {})
        author = cast.get('author', {})
        
        # Update world state with new cast
        if cast.get('hash'):
            # Add to timeline or update user activity
            logger.info(f"New cast from {author.get('username', 'unknown')}: {cast.get('text', '')[:100]}")
            
            # Trigger world state update
            # Note: This should integrate with your existing world state update mechanism
            # For now, we'll just log the event

    async def _handle_mention(self, data: Dict[str, Any]):
        """Handle mention event - high priority for bot responses"""
        cast = data.get('cast', {})
        author = cast.get('author', {})
        
        logger.info(f"Bot mentioned by {author.get('username', 'unknown')} in cast {cast.get('hash')}")
        
        # This is high priority - the bot should respond to mentions quickly
        # Mark this for immediate processing in next cycle
        if hasattr(self.world_state, 'mark_high_priority_event'):
            await self.world_state.mark_high_priority_event({
                'type': 'mention',
                'cast_hash': cast.get('hash'),
                'author': author.get('username'),
                'text': cast.get('text'),
                'timestamp': cast.get('timestamp')
            })

    async def _handle_reaction_created(self, data: Dict[str, Any]):
        """Handle reaction (like) event"""
        reaction = data.get('reaction', {})
        cast = data.get('cast', {})
        
        logger.info(f"Reaction on cast {cast.get('hash')}: {reaction.get('reaction_type')}")

    async def _handle_follow_created(self, data: Dict[str, Any]):
        """Handle new follow event"""
        follower = data.get('follower', {})
        following = data.get('following', {})
        
        logger.info(f"{follower.get('username')} followed {following.get('username')}")

    async def _handle_cast_reply(self, data: Dict[str, Any]):
        """Handle reply to cast event"""
        reply_cast = data.get('cast', {})
        parent_cast = data.get('parent_cast', {})
        
        logger.info(f"Reply to cast {parent_cast.get('hash')} from {reply_cast.get('author', {}).get('username')}")


# Convenience function for FastAPI integration
async def handle_farcaster_webhook(
    request: Request, 
    webhook_handler: FarcasterWebhookHandler
) -> Dict[str, str]:
    """
    FastAPI endpoint handler for Farcaster webhooks
    
    Usage:
        @app.post("/webhooks/farcaster")
        async def farcaster_webhook(request: Request):
            return await handle_farcaster_webhook(request, webhook_handler_instance)
    """
    return await webhook_handler.handle_webhook(request)
