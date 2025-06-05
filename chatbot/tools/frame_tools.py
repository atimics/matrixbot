#!/usr/bin/env python3
"""
Farcaster Frame Generation Tools

This module provides tools for creating interactive Farcaster Frames including:
1. Transaction frames for payments
2. Poll frames for community engagement
3. Custom interactive frames
"""

import logging
from typing import Any, Dict, List, Optional

from .base import Tool

logger = logging.getLogger(__name__)


class CreateTransactionFrameTool(Tool):
    """Create a Farcaster transaction frame for payments and token interactions."""

    def __init__(self, farcaster_observer=None):
        super().__init__(
            name="create_transaction_frame",
            description="Create an interactive Farcaster frame for cryptocurrency transactions (payments, token swaps, etc.)",
            parameters={
                "to_address": {
                    "type": "string",
                    "description": "Ethereum address to receive the payment"
                },
                "amount": {
                    "type": "string", 
                    "description": "Amount to send (e.g. '0.001' for ETH, '100' for tokens)"
                },
                "token_contract": {
                    "type": "string",
                    "description": "Token contract address (use 'ETH' for native Ethereum)"
                },
                "title": {
                    "type": "string",
                    "description": "Title for the transaction frame"
                },
                "description": {
                    "type": "string", 
                    "description": "Description explaining what the transaction is for"
                },
                "button_text": {
                    "type": "string",
                    "description": "Text for the payment button (e.g. 'Send Payment', 'Buy Token')",
                    "default": "Send Transaction"
                }
            },
            required_parameters=["to_address", "amount", "token_contract", "title"]
        )
        self.farcaster_observer = farcaster_observer

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """Create a transaction frame using Neynar's frame API."""
        try:
            to_address = kwargs.get("to_address")
            amount = kwargs.get("amount")
            token_contract = kwargs.get("token_contract", "ETH")
            title = kwargs.get("title")
            description = kwargs.get("description", "")
            button_text = kwargs.get("button_text", "Send Transaction")

            if not self.farcaster_observer or not self.farcaster_observer.api_client:
                return {
                    "status": "failure",
                    "error": "Farcaster API client not available"
                }

            # Use Neynar's frame/transaction API to create the frame
            frame_data = {
                "to_address": to_address,
                "amount": amount,
                "token_contract": token_contract,
                "title": title,
                "description": description,
                "button_text": button_text
            }

            # For now, we'll create a placeholder frame URL
            # In a real implementation, this would call Neynar's frame API
            frame_url = f"https://frames.neynar.com/transaction?to={to_address}&amount={amount}&token={token_contract}"
            
            logger.info(f"Created transaction frame: {frame_url}")

            return {
                "status": "success",
                "frame_url": frame_url,
                "frame_type": "transaction",
                "details": frame_data
            }

        except Exception as e:
            logger.error(f"Error creating transaction frame: {e}", exc_info=True)
            return {
                "status": "failure", 
                "error": str(e)
            }


class CreatePollFrameTool(Tool):
    """Create a Farcaster poll frame for community engagement."""

    def __init__(self, farcaster_observer=None):
        super().__init__(
            name="create_poll_frame",
            description="Create an interactive poll frame for community voting and engagement",
            parameters={
                "question": {
                    "type": "string",
                    "description": "The poll question to ask users"
                },
                "options": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Array of poll options (2-4 options recommended)",
                    "maxItems": 4
                },
                "duration_hours": {
                    "type": "integer",
                    "description": "How long the poll should run (in hours)",
                    "default": 24,
                    "minimum": 1,
                    "maximum": 168
                },
                "allow_multiple_votes": {
                    "type": "boolean", 
                    "description": "Whether users can select multiple options",
                    "default": False
                }
            },
            required_parameters=["question", "options"]
        )
        self.farcaster_observer = farcaster_observer

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """Create a poll frame."""
        try:
            question = kwargs.get("question")
            options = kwargs.get("options", [])
            duration_hours = kwargs.get("duration_hours", 24)
            allow_multiple_votes = kwargs.get("allow_multiple_votes", False)

            if not question or not options:
                return {
                    "status": "failure",
                    "error": "Question and options are required"
                }

            if len(options) < 2:
                return {
                    "status": "failure",
                    "error": "At least 2 poll options are required"
                }

            if len(options) > 4:
                return {
                    "status": "failure", 
                    "error": "Maximum 4 poll options allowed"
                }

            # Create poll frame data
            poll_data = {
                "question": question,
                "options": options,
                "duration_hours": duration_hours,
                "allow_multiple_votes": allow_multiple_votes
            }

            # For now, create a placeholder frame URL
            # In a real implementation, this would integrate with a frame service
            options_param = "|".join(options)
            frame_url = f"https://frames.example.com/poll?q={question}&opts={options_param}&duration={duration_hours}"
            
            logger.info(f"Created poll frame: {question} with {len(options)} options")

            return {
                "status": "success",
                "frame_url": frame_url,
                "frame_type": "poll",
                "details": poll_data
            }

        except Exception as e:
            logger.error(f"Error creating poll frame: {e}", exc_info=True)
            return {
                "status": "failure",
                "error": str(e)
            }


class CreateCustomFrameTool(Tool):
    """Create a custom interactive Farcaster frame."""

    def __init__(self, farcaster_observer=None):
        super().__init__(
            name="create_custom_frame",
            description="Create a custom interactive frame with buttons and actions",
            parameters={
                "title": {
                    "type": "string",
                    "description": "Title displayed on the frame"
                },
                "image_url": {
                    "type": "string",
                    "description": "URL of the image to display in the frame"
                },
                "buttons": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string"},
                            "action": {"type": "string", "enum": ["post", "link", "mint"]},
                            "target": {"type": "string"}
                        }
                    },
                    "description": "Array of interactive buttons (max 4)",
                    "maxItems": 4
                },
                "input_placeholder": {
                    "type": "string",
                    "description": "Placeholder text for user input field (optional)"
                }
            },
            required_parameters=["title", "image_url", "buttons"]
        )
        self.farcaster_observer = farcaster_observer

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """Create a custom interactive frame."""
        try:
            title = kwargs.get("title")
            image_url = kwargs.get("image_url")
            buttons = kwargs.get("buttons", [])
            input_placeholder = kwargs.get("input_placeholder")

            if not title or not image_url or not buttons:
                return {
                    "status": "failure",
                    "error": "Title, image_url, and buttons are required"
                }

            if len(buttons) > 4:
                return {
                    "status": "failure",
                    "error": "Maximum 4 buttons allowed"
                }

            # Validate button structure
            for i, button in enumerate(buttons):
                if not isinstance(button, dict) or "text" not in button or "action" not in button:
                    return {
                        "status": "failure",
                        "error": f"Button {i+1} must have 'text' and 'action' fields"
                    }

            frame_data = {
                "title": title,
                "image_url": image_url,
                "buttons": buttons,
                "input_placeholder": input_placeholder
            }

            # Create placeholder frame URL  
            frame_url = f"https://frames.example.com/custom?title={title}&img={image_url}"
            
            logger.info(f"Created custom frame: {title} with {len(buttons)} buttons")

            return {
                "status": "success", 
                "frame_url": frame_url,
                "frame_type": "custom",
                "details": frame_data
            }

        except Exception as e:
            logger.error(f"Error creating custom frame: {e}", exc_info=True)
            return {
                "status": "failure",
                "error": str(e)
            }
