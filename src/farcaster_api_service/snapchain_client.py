"""
Snapchain gRPC Client

This module provides a Python gRPC client for communicating with a Farcaster Snapchain node.
It handles the conversion between gRPC protobufs and JSON for easy REST API integration.
"""

import logging
import grpc
from typing import Dict, Any, Optional, List
from datetime import datetime

# Import farcaster protobuf definitions
try:
    # Import the correct protobuf classes
    from farcaster.fcproto.message_pb2 import Message, CastAddBody, CastId, UserDataType
    from farcaster.fcproto.request_response_pb2 import HubInfoRequest, FidRequest
    from farcaster.fcproto.rpc_pb2_grpc import HubServiceStub
    GRPC_AVAILABLE = True
    logger = logging.getLogger(__name__)
    logger.info("Successfully imported farcaster-py protobuf classes")
except ImportError as e:
    logging.warning(f"farcaster-py gRPC not available: {e}")
    # Define minimal fallbacks
    class UserDataType:
        USER_DATA_TYPE_USERNAME = 1
        USER_DATA_TYPE_DISPLAY = 2
        USER_DATA_TYPE_BIO = 3
        USER_DATA_TYPE_PFP = 6
    HubServiceStub = None
    HubInfoRequest = None
    FidRequest = None
    CastId = None
    Message = None
    GRPC_AVAILABLE = False

logger = logging.getLogger(__name__)

class SnapchainClient:
    """
    A gRPC client for communicating with a Farcaster Snapchain node.
    
    This client provides methods that mirror common Farcaster API operations,
    converting between gRPC protobufs and JSON dictionaries.
    """
    
    def __init__(self, host: str = "snapchain", port: int = 3383):
        """
        Initialize the Snapchain gRPC client.
        
        Args:
            host: Snapchain node hostname (default: "snapchain" for Docker)
            port: Snapchain gRPC port (default: 3383)
        """
        self.host = host
        self.port = port
        self.address = f"{host}:{port}"
        self._channel = None
        self._stub = None
        
        logger.info(f"SnapchainClient initialized for {self.address}")
    
    async def connect(self):
        """Establish gRPC connection to the Snapchain node."""
        if not GRPC_AVAILABLE:
            logger.warning("gRPC functionality not available - running in stub mode")
            return
            
        try:
            self._channel = grpc.aio.insecure_channel(self.address)
            self._stub = HubServiceStub(self._channel)
            
            # Test connection
            await self.get_info()
            logger.info(f"Successfully connected to Snapchain node at {self.address}")
            
        except Exception as e:
            logger.error(f"Failed to connect to Snapchain node at {self.address}: {e}")
            raise
    
    async def disconnect(self):
        """Close the gRPC connection."""
        if self._channel:
            await self._channel.close()
            logger.info("Disconnected from Snapchain node")
    
    def _ensure_connected(self):
        """Ensure we have an active connection."""
        if not self._stub:
            raise ConnectionError("Not connected to Snapchain node. Call connect() first.")
    
    async def get_info(self) -> Dict[str, Any]:
        """
        Get information about the Snapchain node.
        
        Returns:
            Dict containing node information
        """
        if not GRPC_AVAILABLE:
            return {"error": "gRPC not available", "version": "stub"}
            
        self._ensure_connected()
        
        try:
            request = HubInfoRequest()
            response = await self._stub.GetInfo(request)
            
            return {
                "version": response.version,
                "is_syncing": response.is_syncing,
                "nickname": response.nickname,
                "root_hash": response.root_hash.hex() if response.root_hash else None,
                "db_stats": {
                    "num_messages": response.db_stats.num_messages,
                    "num_fid_events": response.db_stats.num_fid_events,
                    "num_fname_events": response.db_stats.num_fname_events,
                } if response.db_stats else None
            }
            
        except grpc.RpcError as e:
            logger.error(f"gRPC error getting node info: {e.details()}")
            raise
    
    async def get_cast_by_hash(self, cast_hash: str) -> Optional[Dict[str, Any]]:
        """
        Get a cast by its hash.
        
        Args:
            cast_hash: The cast hash (with or without 0x prefix)
            
        Returns:
            Dict containing cast data, or None if not found
        """
        if not GRPC_AVAILABLE:
            return None
            
        self._ensure_connected()
        
        try:
            # Remove 0x prefix if present and convert to bytes
            hash_bytes = bytes.fromhex(cast_hash.replace('0x', ''))
            
            request = CastId(hash=hash_bytes)
            response = await self._stub.GetCast(request)
            
            return self._convert_cast_message_to_dict(response)
            
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                logger.debug(f"Cast not found: {cast_hash}")
                return None
            logger.error(f"gRPC error fetching cast {cast_hash}: {e.details()}")
            raise
    
    async def get_casts_by_fid(self, fid: int, limit: int = 25, reverse: bool = True) -> List[Dict[str, Any]]:
        """
        Get casts by a user's FID.
        
        Args:
            fid: The Farcaster ID
            limit: Maximum number of casts to return
            reverse: Whether to return newest first
            
        Returns:
            List of cast dictionaries
        """
        if not GRPC_AVAILABLE:
            return []
            
        self._ensure_connected()
        
        try:
            request = FidRequest(fid=fid)
            response = await self._stub.GetCastsByFid(request)
            
            casts = []
            for message in response.messages[:limit]:
                cast_dict = self._convert_cast_message_to_dict(message)
                if cast_dict:
                    casts.append(cast_dict)
            
            if reverse:
                casts.reverse()
                
            return casts
            
        except grpc.RpcError as e:
            logger.error(f"gRPC error fetching casts for FID {fid}: {e.details()}")
            raise
    
    async def submit_message(self, message_data: bytes) -> Dict[str, Any]:
        """
        Submit a message to the Snapchain node.
        
        Args:
            message_data: The serialized message bytes
            
        Returns:
            Dict containing submission result
        """
        if not GRPC_AVAILABLE:
            return {"success": False, "error": "gRPC not available"}
            
        self._ensure_connected()
        
        try:
            # Create message proto with dataBytes populated
            message = Message()
            message.data_bytes = message_data
            # Important: data field should be undefined/empty as per docs
            
            response = await self._stub.SubmitMessage(message)
            
            return {
                "success": True,
                "hash": response.hash.hex() if response.hash else None,
                "message": "Message submitted successfully"
            }
            
        except grpc.RpcError as e:
            logger.error(f"gRPC error submitting message: {e.details()}")
            return {
                "success": False,
                "error": e.details(),
                "code": e.code().name
            }
    
    def _convert_cast_message_to_dict(self, message) -> Optional[Dict[str, Any]]:
        """
        Convert a gRPC cast message to a dictionary format.
        
        This method converts the protobuf message structure to a JSON-friendly
        format similar to what Neynar would return.
        """
        try:
            if not message or not message.data:
                return None
            
            data = message.data
            cast_body = data.cast_add_body
            
            # Extract basic cast information
            cast_dict = {
                "hash": message.hash.hex() if message.hash else None,
                "thread_hash": cast_body.parent_cast_id.hash.hex() if cast_body.parent_cast_id and cast_body.parent_cast_id.hash else None,
                "parent_hash": cast_body.parent_cast_id.hash.hex() if cast_body.parent_cast_id and cast_body.parent_cast_id.hash else None,
                "parent_author": {
                    "fid": cast_body.parent_cast_id.fid if cast_body.parent_cast_id else None
                } if cast_body.parent_cast_id else None,
                "author": {
                    "fid": data.fid,
                    "username": None,  # Would need separate lookup
                    "display_name": None,  # Would need separate lookup
                },
                "text": cast_body.text,
                "timestamp": datetime.fromtimestamp(data.timestamp).isoformat(),
                "embeds": [
                    {"url": embed.url} for embed in cast_body.embeds
                ] if cast_body.embeds else [],
                "mentions": list(cast_body.mentions) if cast_body.mentions else [],
                "mentions_positions": list(cast_body.mentions_positions) if cast_body.mentions_positions else [],
                "replies": {
                    "count": 0  # Would need separate lookup
                },
                "reactions": {
                    "likes_count": 0,  # Would need separate lookup
                    "recasts_count": 0  # Would need separate lookup
                }
            }
            
            return cast_dict
            
        except Exception as e:
            logger.error(f"Error converting cast message to dict: {e}")
            return None
    
    async def get_user_by_fid(self, fid: int) -> Optional[Dict[str, Any]]:
        """
        Get user information by FID.
        
        Args:
            fid: The Farcaster ID
            
        Returns:
            Dict containing user data, or None if not found
        """
        if not GRPC_AVAILABLE:
            return None
            
        self._ensure_connected()
        
        try:
            request = FidRequest(fid=fid)
            response = await self._stub.GetUserData(request)
            
            user_data = {}
            for message in response.messages:
                if message.data.user_data_body.type == UserDataType.USER_DATA_TYPE_USERNAME:
                    user_data["username"] = message.data.user_data_body.value
                elif message.data.user_data_body.type == UserDataType.USER_DATA_TYPE_DISPLAY:
                    user_data["display_name"] = message.data.user_data_body.value
                elif message.data.user_data_body.type == UserDataType.USER_DATA_TYPE_BIO:
                    user_data["bio"] = message.data.user_data_body.value
                elif message.data.user_data_body.type == UserDataType.USER_DATA_TYPE_PFP:
                    user_data["pfp_url"] = message.data.user_data_body.value
            
            if user_data:
                user_data["fid"] = fid
                return user_data
            
            return None
            
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                logger.debug(f"User not found: {fid}")
                return None
            logger.error(f"gRPC error fetching user {fid}: {e.details()}")
            raise
