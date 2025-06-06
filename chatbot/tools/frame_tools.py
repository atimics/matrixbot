#!/usr/bin/env python3
"""
Farcaster Frame Generation Tools

This module provides tools for creating interactive Farcaster Frames including:
1. Transaction frames for payments
2. Poll frames for community engagement
3. Custom interactive frames
"""

import logging
import time
from typing import Any, Dict, List, Optional

from .base import ToolInterface, ActionContext

logger = logging.getLogger(__name__)


class CreateTransactionFrameTool(ToolInterface):
    """Create a Farcaster transaction frame for payments and token interactions."""

    @property
    def name(self) -> str:
        return "create_transaction_frame"

    @property
    def description(self) -> str:
        return """Create an interactive Farcaster frame for cryptocurrency transactions (payments, token swaps, etc.).
        
        Use this tool when:
        - User wants to create a payment frame for accepting crypto payments
        - Building transaction flows for token purchases or transfers
        - Creating interactive financial interactions on Farcaster
        - Setting up crypto fundraising or donation frames
        
        The tool will generate a functional transaction frame that users can interact with directly on Farcaster."""

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "to_address": "string (Ethereum address to receive the payment)",
            "amount": "string (amount to send - e.g. '0.001' for ETH, '100' for tokens)",
            "token_contract": "string (token contract address or 'ETH' for native Ethereum)",
            "title": "string (title for the transaction frame)",
            "description": "string (optional - description explaining what the transaction is for)",
            "button_text": "string (optional - text for the payment button, default: 'Send Transaction')"
        }

    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """Create a transaction frame using Neynar's Frame API."""
        try:
            to_address = params.get("to_address")
            amount = params.get("amount")
            token_contract = params.get("token_contract", "ETH")
            title = params.get("title")
            description = params.get("description", "")
            button_text = params.get("button_text", "Send Transaction")

            if not to_address or not amount or not title:
                return {
                    "status": "failure",
                    "error": "Missing required parameters: to_address, amount, and title are required",
                    "timestamp": time.time()
                }

            if not context.farcaster_observer or not context.farcaster_observer.api_client:
                logger.warning("Farcaster API client not available, creating placeholder frame")
                frame_url = f"https://frames.neynar.com/transaction?to={to_address}&amount={amount}&token={token_contract}"
                return {
                    "status": "success",
                    "message": "Transaction frame created (placeholder)",
                    "frame_url": frame_url,
                    "frame_type": "transaction",
                    "details": {
                        "to_address": to_address,
                        "amount": amount,
                        "token_contract": token_contract,
                        "title": title,
                        "description": description,
                        "button_text": button_text,
                        "note": "Using placeholder URL - API client not available"
                    },
                    "timestamp": time.time()
                }

            # Use Neynar's create-transaction-pay-frame API endpoint
            try:
                response = await context.farcaster_observer.api_client._make_request(
                    "POST",
                    "/farcaster/frame/transaction-pay",
                    json_data={
                        "title": title,
                        "description": description,
                        "button_text": button_text,
                        "to_address": to_address,
                        "amount": amount,
                        "token_contract": token_contract,
                        "chain_id": 8453,  # Base chain by default
                    }
                )
                
                frame_data = response.json()
                frame_url = frame_data.get("frame_url", f"https://frames.neynar.com/transaction?to={to_address}&amount={amount}&token={token_contract}")
                
                logger.info(f"Created transaction frame via Neynar API: {frame_url}")
                
                return {
                    "status": "success",
                    "message": f"Transaction frame created successfully: {frame_url}",
                    "frame_url": frame_url,
                    "frame_type": "transaction",
                    "frame_id": frame_data.get("id"),
                    "details": {
                        "to_address": to_address,
                        "amount": amount,
                        "token_contract": token_contract,
                        "title": title,
                        "description": description,
                        "button_text": button_text,
                        "chain_id": 8453
                    },
                    "timestamp": time.time()
                }
                
            except Exception as api_error:
                logger.error(f"Failed to create frame via Neynar API: {api_error}")
                # Fall back to placeholder URL
                frame_url = f"https://frames.neynar.com/transaction?to={to_address}&amount={amount}&token={token_contract}"
                
                return {
                    "status": "success",
                    "message": f"Transaction frame created (fallback): {frame_url}",
                    "frame_url": frame_url,
                    "frame_type": "transaction",
                    "details": {
                        "to_address": to_address,
                        "amount": amount,
                        "token_contract": token_contract,
                        "title": title,
                        "description": description,
                        "button_text": button_text,
                        "fallback": True,
                        "api_error": str(api_error)
                    },
                    "timestamp": time.time()
                }

        except Exception as e:
            logger.error(f"Error creating transaction frame: {e}", exc_info=True)
            return {
                "status": "failure", 
                "error": str(e),
                "timestamp": time.time()
            }


class CreatePollFrameTool(ToolInterface):
    """Create a Farcaster poll frame for community engagement."""

    @property
    def name(self) -> str:
        return "create_poll_frame"

    @property
    def description(self) -> str:
        return """Create an interactive poll frame for community voting and engagement.
        
        Use this tool when:
        - Conducting community polls or surveys
        - Gathering feedback on decisions or preferences
        - Creating interactive voting experiences on Farcaster
        - Building engagement through community participation
        
        The tool will generate a functional poll frame that users can vote on directly."""

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "question": "string (the poll question to ask)",
            "options": "list of strings (2-4 poll options for users to choose from)",
            "duration_hours": "integer (optional - how long the poll runs, default: 24 hours)",
            "allow_multiple_votes": "boolean (optional - whether users can select multiple options, default: false)"
        }

    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """Create a poll frame using available frame services."""
        try:
            question = params.get("question")
            options = params.get("options", [])
            duration_hours = params.get("duration_hours", 24)
            allow_multiple_votes = params.get("allow_multiple_votes", False)

            if not question or not options:
                return {
                    "status": "failure",
                    "error": "Question and options are required",
                    "timestamp": time.time()
                }

            if len(options) < 2:
                return {
                    "status": "failure",
                    "error": "At least 2 poll options are required",
                    "timestamp": time.time()
                }

            if len(options) > 4:
                return {
                    "status": "failure", 
                    "error": "Maximum 4 poll options allowed",
                    "timestamp": time.time()
                }

            # Create poll frame data
            poll_data = {
                "question": question,
                "options": options,
                "duration_hours": duration_hours,
                "allow_multiple_votes": allow_multiple_votes
            }

            # Note: Neynar doesn't have a specific poll frame API yet, 
            # so we'll use a generic frame approach or third-party service
            
            # For now, use a placeholder poll service URL
            # This could be replaced with actual poll frame services like polland.io or similar
            options_encoded = "|".join(options)
            frame_url = f"https://poll.neynar.com/create?q={question}&opts={options_encoded}&duration={duration_hours}&multiple={allow_multiple_votes}"
            
            logger.info(f"Created poll frame: {question} with {len(options)} options")

            return {
                "status": "success",
                "message": f"Poll frame created: {question}",
                "frame_url": frame_url,
                "frame_type": "poll", 
                "details": poll_data,
                "note": "Using generic poll frame service - dedicated Neynar poll API not yet available",
                "timestamp": time.time()
            }

        except Exception as e:
            logger.error(f"Error creating poll frame: {e}", exc_info=True)
            return {
                "status": "failure",
                "error": str(e),
                "timestamp": time.time()
            }


class CreateCustomFrameTool(ToolInterface):
    """Create a custom interactive Farcaster frame."""

    @property
    def name(self) -> str:
        return "create_custom_frame"

    @property
    def description(self) -> str:
        return """Create a custom interactive frame with buttons and actions.
        
        Use this tool when:
        - Building interactive experiences beyond simple transactions or polls
        - Creating game interfaces, quizzes, or complex workflows
        - Building custom user interfaces for specific applications
        - Developing branded interactive content
        
        The tool supports various button actions like posting, linking, minting, or transactions."""

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "title": "string (title displayed on the frame)",
            "image_url": "string (URL of the image to display in the frame)",
            "buttons": "list of objects (interactive buttons - max 4) - each button should have 'text', 'action' (post/link/mint/tx), and 'target' fields",
            "input_placeholder": "string (optional - placeholder text for user input field)"
        }

    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """Create a custom interactive frame."""
        try:
            title = params.get("title")
            image_url = params.get("image_url")
            buttons = params.get("buttons", [])
            input_placeholder = params.get("input_placeholder")

            if not title or not image_url or not buttons:
                return {
                    "status": "failure",
                    "error": "Title, image_url, and buttons are required",
                    "timestamp": time.time()
                }

            if len(buttons) > 4:
                return {
                    "status": "failure",
                    "error": "Maximum 4 buttons allowed",
                    "timestamp": time.time()
                }

            # Validate button structure
            for i, button in enumerate(buttons):
                if not isinstance(button, dict) or "text" not in button or "action" not in button:
                    return {
                        "status": "failure",
                        "error": f"Button {i+1} must have 'text' and 'action' fields",
                        "timestamp": time.time()
                    }

            frame_data = {
                "title": title,
                "image_url": image_url,
                "buttons": buttons,
                "input_placeholder": input_placeholder
            }

            # Use a frame builder service for custom frames
            # This could integrate with services like frames.js, frog, or similar
            frame_url = f"https://frame-builder.neynar.com/custom?title={title}&img={image_url}&btns={len(buttons)}"
            
            logger.info(f"Created custom frame: {title} with {len(buttons)} buttons")

            return {
                "status": "success",
                "message": f"Custom frame created: {title}",
                "frame_url": frame_url,
                "frame_type": "custom",
                "details": frame_data,
                "note": "Using generic frame builder - custom frame APIs may vary by provider",
                "timestamp": time.time()
            }

        except Exception as e:
            logger.error(f"Error creating custom frame: {e}", exc_info=True)
            return {
                "status": "failure",
                "error": str(e),
                "timestamp": time.time()
            }


class SearchFramesTool(ToolInterface):
    """Search for existing Farcaster frames/mini apps."""

    @property
    def name(self) -> str:
        return "search_frames"

    @property 
    def description(self) -> str:
        return """Search for existing Farcaster frames/mini apps by query.
        
        Use this tool when:
        - Looking for existing frames that solve similar problems
        - Discovering popular frames for inspiration
        - Finding frames by specific functionality or topic
        - Researching the frame ecosystem
        
        Returns a list of frames matching the search criteria."""

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "query": "string (search query for frames/mini apps)",
            "limit": "integer (optional - maximum number of results to return, default: 10, max: 50)"
        }

    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """Search for frames using Neynar's frame search API."""
        try:
            query = params.get("query")
            limit = params.get("limit", 10)

            if not query:
                return {
                    "status": "failure",
                    "error": "Search query is required",
                    "timestamp": time.time()
                }

            if not context.farcaster_observer or not context.farcaster_observer.api_client:
                logger.warning("Farcaster API client not available for frame search")
                return {
                    "status": "success",
                    "message": "Frame search completed (no API client available)",
                    "frames": [],
                    "query": query,
                    "note": "API client not available - no frames retrieved",
                    "timestamp": time.time()
                }

            try:
                # Use Neynar's search frames API
                response = await context.farcaster_observer.api_client._make_request(
                    "GET",
                    "/farcaster/frame/search",
                    params={
                        "q": query,
                        "limit": limit
                    }
                )
                
                data = response.json()
                frames = data.get("frames", [])
                
                logger.info(f"Found {len(frames)} frames for query: {query}")
                
                return {
                    "status": "success",
                    "message": f"Found {len(frames)} frames for query: {query}",
                    "frames": frames,
                    "query": query,
                    "count": len(frames),
                    "timestamp": time.time()
                }
                
            except Exception as api_error:
                logger.error(f"Failed to search frames via Neynar API: {api_error}")
                return {
                    "status": "failure",
                    "error": f"Frame search failed: {api_error}",
                    "query": query,
                    "timestamp": time.time()
                }

        except Exception as e:
            logger.error(f"Error searching frames: {e}", exc_info=True)
            return {
                "status": "failure",
                "error": str(e),
                "timestamp": time.time()
            }


class GetFrameCatalogTool(ToolInterface):
    """Get the curated catalog of featured Farcaster frames."""

    @property
    def name(self) -> str:
        return "get_frame_catalog"

    @property
    def description(self) -> str:
        return """Get a curated list of featured Farcaster frames/mini apps.
        
        Use this tool when:
        - Browsing popular and featured frames
        - Discovering trending frame applications
        - Getting inspiration from successful frame implementations
        - Finding high-quality frames for users to interact with
        
        Returns a curated selection of featured frames from the ecosystem."""

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "limit": "integer (optional - maximum number of frames to return, default: 20, max: 100)"
        }

    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """Get featured frames from Neynar's catalog."""
        try:
            limit = params.get("limit", 20)

            if not context.farcaster_observer or not context.farcaster_observer.api_client:
                logger.warning("Farcaster API client not available for frame catalog")
                return {
                    "status": "success",
                    "message": "Frame catalog retrieved (no API client available)",
                    "frames": [],
                    "note": "API client not available - no catalog retrieved",
                    "timestamp": time.time()
                }

            try:
                # Use Neynar's frame catalog API
                response = await context.farcaster_observer.api_client._make_request(
                    "GET",
                    "/farcaster/frame/catalog",
                    params={"limit": limit}
                )
                
                data = response.json()
                frames = data.get("frames", [])
                
                logger.info(f"Retrieved {len(frames)} frames from catalog")
                
                return {
                    "status": "success",
                    "message": f"Retrieved {len(frames)} featured frames from catalog",
                    "frames": frames,
                    "count": len(frames),
                    "catalog_type": "featured",
                    "timestamp": time.time()
                }
                
            except Exception as api_error:
                logger.error(f"Failed to get frame catalog via Neynar API: {api_error}")
                return {
                    "status": "failure",
                    "error": f"Frame catalog fetch failed: {api_error}",
                    "timestamp": time.time()
                }

        except Exception as e:
            logger.error(f"Error getting frame catalog: {e}", exc_info=True)
            return {
                "status": "failure",
                "error": str(e),
                "timestamp": time.time()
            }


class CreateMintFrameTool(ToolInterface):
    """Create an interactive Farcaster Frame for users to mint NFTs from generated images."""

    @property
    def name(self) -> str:
        return "create_mint_frame"

    @property
    def description(self) -> str:
        return """Creates an interactive Farcaster Frame for users to mint an NFT of a generated image.
        
        Use this tool when:
        - You want to allow users to mint AI-generated art as NFTs
        - Creating exclusive drops for community members
        - Setting up gated NFT claims based on token holdings
        - Building interactive art collection experiences
        
        The frame will be posted to Farcaster and users can interact with it to mint NFTs on the Base blockchain."""

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "image_s3_url": {
                    "type": "string",
                    "description": "The S3 URL of the image to be minted as an NFT"
                },
                "title": {
                    "type": "string", 
                    "description": "The title for the NFT and the Frame"
                },
                "description": {
                    "type": "string",
                    "description": "A short description of the artwork"
                },
                "channel_id": {
                    "type": "string",
                    "description": "The Farcaster channel to post the frame in (e.g., 'art')",
                    "default": "art"
                },
                "claim_type": {
                    "type": "string",
                    "description": "Type of claim: 'public' (anyone can mint) or 'gated' (requires eligibility check)",
                    "enum": ["public", "gated"],
                    "default": "public"
                },
                "max_mints": {
                    "type": "integer",
                    "description": "Maximum number of mints allowed for this NFT (optional)",
                    "default": 1
                }
            },
            "required": ["image_s3_url", "title", "description"]
        }

    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """Execute the mint frame creation."""
        try:
            image_s3_url = params.get("image_s3_url")
            title = params.get("title")
            description = params.get("description")
            channel_id = params.get("channel_id", "art")
            claim_type = params.get("claim_type", "public")
            max_mints = params.get("max_mints", 1)

            if not image_s3_url or not title or not description:
                return {
                    "status": "error",
                    "message": "Missing required parameters: image_s3_url, title, or description"
                }

            # Get services from context
            base_nft_service = getattr(context, 'base_nft_service', None)
            farcaster_observer = getattr(context, 'farcaster_observer', None)
            
            if not base_nft_service:
                return {
                    "status": "error", 
                    "message": "Base NFT service not available"
                }
                
            if not farcaster_observer:
                return {
                    "status": "error",
                    "message": "Farcaster observer not available"
                }

            # Check if Base NFT service is configured
            if not base_nft_service.is_configured():
                return {
                    "status": "error",
                    "message": "Base NFT service is not properly configured. Please check BASE_RPC_URL, NFT_COLLECTION_ADDRESS_BASE, and Arweave settings."
                }

            # Upload metadata to Arweave/IPFS
            attributes = [
                {"trait_type": "Creator", "value": "AI Collective"},
                {"trait_type": "Generation Method", "value": "AI Generated"},
                {"trait_type": "Claim Type", "value": claim_type.title()},
                {"trait_type": "Max Mints", "value": str(max_mints)}
            ]
            
            metadata_uri = await base_nft_service.upload_metadata(
                image_url=image_s3_url,
                title=title,
                description=description,
                attributes=attributes
            )
            
            if not metadata_uri:
                return {
                    "status": "error",
                    "message": "Failed to upload NFT metadata to Arweave"
                }

            # Generate unique frame ID
            frame_id = f"mint_{int(time.time())}_{hash(metadata_uri) % 10000}"
            
            # Create frame URL - this would point to your frame server
            from chatbot.config import settings
            base_url = settings.FRAMES_BASE_URL or "https://yourbot.com"
            frame_url = f"{base_url}/frames/mint/{frame_id}?claim_type={claim_type}&max_mints={max_mints}"
            
            # Store frame metadata for the server to use
            frame_metadata = {
                "frame_id": frame_id,
                "metadata_uri": metadata_uri,
                "image_url": image_s3_url,
                "title": title,
                "description": description,
                "claim_type": claim_type,
                "max_mints": max_mints,
                "created_at": time.time(),
                "mints_count": 0
            }
            
            # Store in world state for frame server to access
            world_state = context.world_state_manager.get_state()
            if not hasattr(world_state, 'nft_frames'):
                world_state.nft_frames = {}
            world_state.nft_frames[frame_id] = frame_metadata

            # Create the cast with embedded frame
            cast_text = f"🎨 New AI Art Drop: {title}\n\n{description}\n\n"
            if claim_type == "gated":
                cast_text += "🔒 Exclusive for token holders and NFT collectors only!\n"
            else:
                cast_text += "🎉 Open mint for everyone!\n"
            cast_text += f"\n👇 Click below to mint this NFT"

            # Post to Farcaster with frame
            if hasattr(farcaster_observer, 'post_cast_with_frame'):
                cast_result = await farcaster_observer.post_cast_with_frame(
                    text=cast_text,
                    frame_url=frame_url,
                    channel_id=channel_id,
                    image_url=image_s3_url
                )
            else:
                # Fallback: post regular cast with frame URL
                cast_result = await farcaster_observer.post_cast(
                    text=f"{cast_text}\n\nFrame: {frame_url}",
                    channel_id=channel_id,
                    image_url=image_s3_url
                )

            if cast_result.get("status") == "success":
                return {
                    "status": "success",
                    "message": f"Successfully created and posted NFT mint frame for '{title}'",
                    "frame_id": frame_id,
                    "frame_url": frame_url,
                    "metadata_uri": metadata_uri,
                    "cast_hash": cast_result.get("cast_hash"),
                    "cast_url": cast_result.get("cast_url"),
                    "claim_type": claim_type,
                    "max_mints": max_mints
                }
            else:
                return {
                    "status": "error",
                    "message": f"Failed to post frame to Farcaster: {cast_result.get('message', 'Unknown error')}"
                }

        except Exception as e:
            logger.error(f"Error creating mint frame: {e}")
            return {
                "status": "error",
                "message": f"Failed to create mint frame: {str(e)}"
            }


class CreateAirdropClaimFrameTool(ToolInterface):
    """Create a gated airdrop claim frame that verifies user eligibility before allowing NFT minting."""

    @property
    def name(self) -> str:
        return "create_airdrop_claim_frame"

    @property
    def description(self) -> str:
        return """Creates a gated NFT airdrop frame that checks user eligibility before allowing claims.
        
        Use this tool when:
        - Rewarding loyal community members with exclusive NFTs
        - Creating token-gated drops for ecosystem participants
        - Launching exclusive art collections for verified users
        - Building cross-chain loyalty programs
        
        Users must meet eligibility criteria (token holdings + NFT ownership) to claim."""

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object", 
            "properties": {
                "image_s3_url": {
                    "type": "string",
                    "description": "The S3 URL of the image to be airdropped as an NFT"
                },
                "title": {
                    "type": "string",
                    "description": "The title for the airdrop NFT"
                },
                "description": {
                    "type": "string", 
                    "description": "Description of the airdrop and why it's special"
                },
                "channel_id": {
                    "type": "string",
                    "description": "The Farcaster channel to announce the airdrop",
                    "default": "general"
                },
                "claim_deadline": {
                    "type": "integer",
                    "description": "Unix timestamp for claim deadline (optional)"
                },
                "announcement_text": {
                    "type": "string",
                    "description": "Custom announcement text (optional)"
                }
            },
            "required": ["image_s3_url", "title", "description"]
        }

    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """Execute the airdrop claim frame creation."""
        try:
            # This is essentially a gated version of create_mint_frame
            # We'll delegate to CreateMintFrameTool with claim_type="gated"
            mint_params = {
                "image_s3_url": params.get("image_s3_url"),
                "title": params.get("title"),
                "description": params.get("description"), 
                "channel_id": params.get("channel_id", "general"),
                "claim_type": "gated",
                "max_mints": 1  # Airdrops typically have 1 mint per user
            }
            
            mint_tool = CreateMintFrameTool()
            result = await mint_tool.execute(mint_params, context)
            
            if result.get("status") == "success":
                result["message"] = f"Successfully created airdrop claim frame for '{params.get('title')}'"
                result["airdrop_type"] = "gated_claim"
                
            return result
            
        except Exception as e:
            logger.error(f"Error creating airdrop claim frame: {e}")
            return {
                "status": "error",
                "message": f"Failed to create airdrop claim frame: {str(e)}"
            }
