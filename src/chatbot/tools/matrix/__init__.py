"""
Matrix Tools Module - Modular Matrix Platform Tools

This module contains all Matrix-specific tools, each in its own file for better
maintainability and clear separation of concerns. All tools use the ServiceRegistry
abstraction for clean platform integration.

Tools:
- SendMatrixMessageTool: Unified messaging (regular messages and replies)
- JoinMatrixRoomTool: Join Matrix rooms
- LeaveMatrixRoomTool: Leave Matrix rooms  
- AcceptMatrixInviteTool: Accept room invitations
- IgnoreMatrixInviteTool: Ignore/decline invitations
- ReactToMatrixMessageTool: React to messages with emoji
- SendMatrixImageTool: Send images to rooms
- SendMatrixVideoTool: Send videos to rooms
"""

from .send_message import SendMatrixMessageTool
from .join_room import JoinMatrixRoomTool
from .leave_room import LeaveMatrixRoomTool
from .accept_invite import AcceptMatrixInviteTool
from .ignore_invite import IgnoreMatrixInviteTool
from .react_to_message import ReactToMatrixMessageTool
from .send_image import SendMatrixImageTool
from .send_video import SendMatrixVideoTool

# Export all Matrix tools
__all__ = [
    "SendMatrixMessageTool",
    "JoinMatrixRoomTool", 
    "LeaveMatrixRoomTool",
    "AcceptMatrixInviteTool",
    "IgnoreMatrixInviteTool",
    "ReactToMatrixMessageTool",
    "SendMatrixImageTool",
    "SendMatrixVideoTool",
]
