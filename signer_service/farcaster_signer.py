"""
Farcaster Message Signing Service

This module provides functionality to create and sign Farcaster protobuf messages
using the secure key manager.
"""

import logging
import time
from typing import Optional, Dict, Any, List
from key_manager import SecureKeyManager

logger = logging.getLogger(__name__)


class FarcasterSigner:
    """
    Handles creation and signing of Farcaster protobuf messages.
    """
    
    def __init__(self, key_manager: SecureKeyManager):
        self.key_manager = key_manager
        
        # Import farcaster protobuf definitions
        try:
            # Note: These imports will fail in the current environment
            # but would work in the Docker container with farcaster-py installed
            from farcaster.fcproto import message_pb2 as message_pb2
            from farcaster.fcproto import username_proof_pb2 as username_proof_pb2
            from farcaster.fcproto import hub_event_pb2 as hub_event_pb2
            
            self.message_pb2 = message_pb2
            self.username_proof_pb2 = username_proof_pb2
            self.hub_event_pb2 = hub_event_pb2
            
            logger.info("Farcaster protobuf modules loaded successfully")
            
        except ImportError as e:
            logger.warning(f"Failed to import farcaster protobuf modules: {e}")
            logger.warning("Signing functionality will be limited")
            self.message_pb2 = None
            self.username_proof_pb2 = None
            self.hub_event_pb2 = None
    
    def _get_current_timestamp(self) -> int:
        """Get current timestamp in Farcaster format (Unix timestamp)."""
        return int(time.time())
    
    def create_cast_add_message(
        self,
        text: str,
        parent_cast_id: Optional[Dict[str, Any]] = None,
        parent_url: Optional[str] = None,
        embeds: Optional[List[Dict[str, Any]]] = None,
        mentions: Optional[List[int]] = None,
        mentions_positions: Optional[List[int]] = None
    ) -> bytes:
        """
        Create a signed CastAdd message.
        
        Args:
            text: The cast text content
            parent_cast_id: Parent cast for replies ({"fid": int, "hash": bytes})
            parent_url: Parent URL for URL replies
            embeds: List of embeds (URLs, etc.)
            mentions: List of mentioned FIDs
            mentions_positions: Positions of mentions in text
            
        Returns:
            Serialized signed message bytes
        """
        if not self.message_pb2:
            raise RuntimeError("Farcaster protobuf modules not available")
        
        if not self.key_manager.is_key_loaded():
            raise RuntimeError("No signing key loaded")
        
        fid = self.key_manager.get_fid()
        if not fid:
            raise RuntimeError("No FID associated with signing key")
        
        # Create CastAddBody
        cast_add_body = self.message_pb2.CastAddBody()
        cast_add_body.text = text
        
        # Add parent if specified
        if parent_cast_id:
            cast_add_body.parent_cast_id.fid = parent_cast_id["fid"]
            cast_add_body.parent_cast_id.hash = parent_cast_id["hash"]
        elif parent_url:
            cast_add_body.parent_url = parent_url
        
        # Add embeds
        if embeds:
            for embed in embeds:
                embed_msg = cast_add_body.embeds.add()
                if "url" in embed:
                    embed_msg.url = embed["url"]
                # Add other embed types as needed
        
        # Add mentions
        if mentions:
            cast_add_body.mentions.extend(mentions)
        if mentions_positions:
            cast_add_body.mentions_positions.extend(mentions_positions)
        
        # Create MessageData
        message_data = self.message_pb2.MessageData()
        message_data.type = self.message_pb2.MessageType.MESSAGE_TYPE_CAST_ADD
        message_data.fid = fid
        message_data.timestamp = self._get_current_timestamp()
        message_data.network = self.message_pb2.FarcasterNetwork.FARCASTER_NETWORK_MAINNET
        message_data.cast_add_body.CopyFrom(cast_add_body)
        
        # Serialize MessageData for signing
        message_data_bytes = message_data.SerializeToString()
        
        # Sign the message data
        signature = self.key_manager.sign_message(message_data_bytes)
        
        # Create the final Message
        message = self.message_pb2.Message()
        message.data_bytes = message_data_bytes  # Important: use data_bytes, not data
        message.hash = self._compute_message_hash(message_data_bytes)
        message.hash_scheme = self.message_pb2.HashScheme.HASH_SCHEME_BLAKE3
        message.signature = signature
        message.signature_scheme = self.message_pb2.SignatureScheme.SIGNATURE_SCHEME_ED25519
        message.signer = bytes.fromhex(self.key_manager.get_public_key_hex())
        
        return message.SerializeToString()
    
    def create_reaction_add_message(
        self,
        target_cast_id: Dict[str, Any],
        reaction_type: int = 1  # 1 = like, 2 = recast
    ) -> bytes:
        """
        Create a signed ReactionAdd message.
        
        Args:
            target_cast_id: Target cast {"fid": int, "hash": bytes}
            reaction_type: Type of reaction (1=like, 2=recast)
            
        Returns:
            Serialized signed message bytes
        """
        if not self.message_pb2:
            raise RuntimeError("Farcaster protobuf modules not available")
        
        if not self.key_manager.is_key_loaded():
            raise RuntimeError("No signing key loaded")
        
        fid = self.key_manager.get_fid()
        if not fid:
            raise RuntimeError("No FID associated with signing key")
        
        # Create ReactionBody
        reaction_body = self.message_pb2.ReactionBody()
        reaction_body.type = reaction_type
        reaction_body.target_cast_id.fid = target_cast_id["fid"]
        reaction_body.target_cast_id.hash = target_cast_id["hash"]
        
        # Create MessageData
        message_data = self.message_pb2.MessageData()
        message_data.type = self.message_pb2.MessageType.MESSAGE_TYPE_REACTION_ADD
        message_data.fid = fid
        message_data.timestamp = self._get_current_timestamp()
        message_data.network = self.message_pb2.FarcasterNetwork.FARCASTER_NETWORK_MAINNET
        message_data.reaction_body.CopyFrom(reaction_body)
        
        # Serialize and sign
        message_data_bytes = message_data.SerializeToString()
        signature = self.key_manager.sign_message(message_data_bytes)
        
        # Create final message
        message = self.message_pb2.Message()
        message.data_bytes = message_data_bytes
        message.hash = self._compute_message_hash(message_data_bytes)
        message.hash_scheme = self.message_pb2.HashScheme.HASH_SCHEME_BLAKE3
        message.signature = signature
        message.signature_scheme = self.message_pb2.SignatureScheme.SIGNATURE_SCHEME_ED25519
        message.signer = bytes.fromhex(self.key_manager.get_public_key_hex())
        
        return message.SerializeToString()
    
    def _compute_message_hash(self, message_data_bytes: bytes) -> bytes:
        """
        Compute Blake3 hash of message data.
        
        Args:
            message_data_bytes: Serialized MessageData
            
        Returns:
            Blake3 hash bytes
        """
        try:
            import blake3
            hasher = blake3.blake3()
            hasher.update(message_data_bytes)
            return hasher.digest()[:20]  # Farcaster uses 20-byte hashes
        except ImportError:
            # Fallback to SHA256 if blake3 not available (not recommended for production)
            import hashlib
            return hashlib.sha256(message_data_bytes).digest()[:20]
    
    def get_signer_info(self) -> Dict[str, Any]:
        """Get information about the current signer."""
        return {
            "fid": self.key_manager.get_fid(),
            "public_key_hex": self.key_manager.get_public_key_hex(),
            "is_key_loaded": self.key_manager.is_key_loaded(),
            "protobuf_available": self.message_pb2 is not None
        }
