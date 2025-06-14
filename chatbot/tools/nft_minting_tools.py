"""
NFT Minting Tools

Tools for minting NFTs from existing media stored in S3 or other storage.
Uses Arweave for permanent storage suitable for NFTs.
"""

import logging
from typing import Any, Dict, Optional

from .base import ActionContext, ToolInterface

logger = logging.getLogger(__name__)


class MintNFTFromMediaTool(ToolInterface):
    """Tool for minting NFTs from existing media by uploading to Arweave"""

    @property
    def name(self) -> str:
        return "mint_nft_from_media"

    @property
    def description(self) -> str:
        return (
            "Mint an NFT from existing media by uploading it to Arweave for permanent storage. "
            "This can be used to create NFTs from media currently stored in S3 or other temporary storage. "
            "The media is downloaded from the source URL and uploaded to Arweave with NFT-appropriate metadata."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "media_url": {
                    "type": "string",
                    "description": "URL of the existing media to mint as NFT (can be S3, CloudFront, etc.)",
                },
                "nft_title": {
                    "type": "string", 
                    "description": "Title for the NFT",
                },
                "nft_description": {
                    "type": "string",
                    "description": "Description for the NFT",
                },
                "creator": {
                    "type": "string",
                    "description": "Creator/artist name for the NFT",
                    "default": "RatiChat AI"
                },
                "tags": {
                    "type": "object",
                    "description": "Additional metadata tags for the NFT",
                    "default": {}
                }
            },
            "required": ["media_url", "nft_title", "nft_description"]
        }

    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """Execute NFT minting from existing media"""
        try:
            media_url = params.get("media_url")
            nft_title = params.get("nft_title")
            nft_description = params.get("nft_description")
            creator = params.get("creator", "RatiChat AI")
            custom_tags = params.get("tags", {})

            if not media_url or not nft_title or not nft_description:
                return {
                    "status": "error",
                    "message": "Missing required parameters: media_url, nft_title, nft_description"
                }

            # Check if dual storage manager is available
            if not context.dual_storage_manager:
                return {
                    "status": "error", 
                    "message": "Dual storage manager not available for NFT minting"
                }

            if not context.dual_storage_manager.is_arweave_available():
                return {
                    "status": "error",
                    "message": "Arweave service not configured - required for NFT minting"
                }

            logger.info(f"Minting NFT from media: {media_url}")

            # Download the media from the source URL
            media_data = None
            if context.dual_storage_manager.is_s3_available():
                # Try S3 service first for downloads
                media_data = await context.dual_storage_manager.s3_service.download_media(media_url)
            
            if not media_data and context.dual_storage_manager.is_arweave_available():
                # Try Arweave service as fallback
                # Note: ArweaveService might not have download capability, this is a fallback attempt
                try:
                    import httpx
                    async with httpx.AsyncClient(timeout=60.0) as client:
                        response = await client.get(media_url)
                        if response.status_code == 200:
                            media_data = response.content
                except Exception as e:
                    logger.warning(f"Failed to download media via fallback method: {e}")

            if not media_data:
                return {
                    "status": "error",
                    "message": f"Failed to download media from URL: {media_url}"
                }

            # Determine content type and filename from URL
            import os
            from urllib.parse import urlparse
            parsed_url = urlparse(media_url)
            filename = os.path.basename(parsed_url.path) or "nft_media"
            
            # Ensure filename has extension
            if '.' not in filename:
                # Try to guess from content or default to png
                filename += ".png"
            
            # Determine content type
            ext = filename.split('.')[-1].lower()
            content_type_map = {
                'png': 'image/png',
                'jpg': 'image/jpeg', 
                'jpeg': 'image/jpeg',
                'gif': 'image/gif',
                'mp4': 'video/mp4',
                'webm': 'video/webm',
                'mov': 'video/quicktime'
            }
            content_type = content_type_map.get(ext, 'image/png')

            # Prepare NFT metadata tags
            nft_tags = {
                "Title": nft_title,
                "Description": nft_description,
                "Creator": creator,
                "Type": "NFT",
                "Content-Type": content_type,
                "App": "RatiChat",
                **custom_tags
            }

            logger.info(f"Uploading {len(media_data)} bytes to Arweave for NFT: {nft_title}")

            # Upload to Arweave with NFT metadata
            arweave_url = await context.dual_storage_manager.mint_nft_from_media(
                media_data, filename, content_type, nft_tags
            )

            if not arweave_url:
                return {
                    "status": "error",
                    "message": "Failed to upload media to Arweave for NFT minting"
                }

            # Record the NFT in world state
            if context.world_state_manager:
                context.world_state_manager.record_generated_media(
                    media_url=arweave_url,
                    media_type="nft",
                    prompt=f"NFT: {nft_title} - {nft_description}",
                    service_used="arweave_nft",
                    metadata={
                        "nft_title": nft_title,
                        "nft_description": nft_description,
                        "creator": creator,
                        "source_url": media_url,
                        "arweave_tags": nft_tags
                    }
                )

            logger.info(f"Successfully minted NFT on Arweave: {arweave_url}")

            return {
                "status": "success",
                "message": f"Successfully minted NFT '{nft_title}' on Arweave",
                "nft_arweave_url": arweave_url,
                "nft_title": nft_title,
                "nft_description": nft_description,
                "creator": creator,
                "source_url": media_url,
                "content_type": content_type,
                "metadata_tags": nft_tags,
                "next_actions_suggestion": f"NFT is now permanently stored on Arweave: {arweave_url}"
            }

        except Exception as e:
            logger.error(f"NFT minting failed: {e}", exc_info=True)
            return {
                "status": "error", 
                "message": f"NFT minting failed: {str(e)}"
            }


class BatchMintNFTsTool(ToolInterface):
    """Tool for batch minting NFTs from multiple media URLs"""

    @property
    def name(self) -> str:
        return "batch_mint_nfts"

    @property
    def description(self) -> str:
        return (
            "Mint multiple NFTs from a list of media URLs. "
            "Each media item will be uploaded to Arweave with individual NFT metadata. "
            "Useful for creating NFT collections from existing media."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "media_items": {
                    "type": "array",
                    "description": "List of media items to mint as NFTs",
                    "items": {
                        "type": "object",
                        "properties": {
                            "media_url": {"type": "string", "description": "URL of the media"},
                            "nft_title": {"type": "string", "description": "Title for this NFT"},
                            "nft_description": {"type": "string", "description": "Description for this NFT"},
                        },
                        "required": ["media_url", "nft_title", "nft_description"]
                    }
                },
                "creator": {
                    "type": "string",
                    "description": "Creator name for all NFTs",
                    "default": "RatiChat AI"
                },
                "collection_name": {
                    "type": "string",
                    "description": "Name of the NFT collection",
                    "default": "RatiChat Collection"
                }
            },
            "required": ["media_items"]
        }

    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """Execute batch NFT minting"""
        try:
            media_items = params.get("media_items", [])
            creator = params.get("creator", "RatiChat AI")
            collection_name = params.get("collection_name", "RatiChat Collection")

            if not media_items:
                return {
                    "status": "error",
                    "message": "No media items provided for batch minting"
                }

            if not context.dual_storage_manager or not context.dual_storage_manager.is_arweave_available():
                return {
                    "status": "error",
                    "message": "Arweave service not configured - required for NFT minting"
                }

            logger.info(f"Starting batch NFT minting for {len(media_items)} items")

            minted_nfts = []
            failed_items = []

            # Use the single NFT minting tool for each item
            mint_tool = MintNFTFromMediaTool()

            for i, item in enumerate(media_items):
                try:
                    # Add collection metadata
                    nft_params = {
                        **item,
                        "creator": creator,
                        "tags": {
                            "Collection": collection_name,
                            "Collection-Index": str(i + 1),
                            "Collection-Total": str(len(media_items))
                        }
                    }

                    result = await mint_tool.execute(nft_params, context)
                    
                    if result.get("status") == "success":
                        minted_nfts.append({
                            "index": i + 1,
                            "title": item.get("nft_title"),
                            "arweave_url": result.get("nft_arweave_url"),
                            "source_url": item.get("media_url")
                        })
                        logger.info(f"Successfully minted NFT {i+1}/{len(media_items)}: {item.get('nft_title')}")
                    else:
                        failed_items.append({
                            "index": i + 1,
                            "title": item.get("nft_title"),
                            "error": result.get("message", "Unknown error")
                        })
                        logger.error(f"Failed to mint NFT {i+1}/{len(media_items)}: {result.get('message')}")

                except Exception as e:
                    failed_items.append({
                        "index": i + 1,
                        "title": item.get("nft_title", "Unknown"),
                        "error": str(e)
                    })
                    logger.error(f"Exception minting NFT {i+1}: {e}")

            success_count = len(minted_nfts)
            failure_count = len(failed_items)

            return {
                "status": "success" if success_count > 0 else "error",
                "message": f"Batch minting completed: {success_count} successful, {failure_count} failed",
                "collection_name": collection_name,
                "creator": creator,
                "total_items": len(media_items),
                "successful_mints": success_count,
                "failed_mints": failure_count,
                "minted_nfts": minted_nfts,
                "failed_items": failed_items,
                "next_actions_suggestion": f"Successfully minted {success_count} NFTs in the '{collection_name}' collection"
            }

        except Exception as e:
            logger.error(f"Batch NFT minting failed: {e}", exc_info=True)
            return {
                "status": "error",
                "message": f"Batch NFT minting failed: {str(e)}"
            }
