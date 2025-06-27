"""
Tool execution framework for dynamic action handling.
"""

from .base import ActionContext, ToolInterface
from .core_tools import WaitTool
from .describe_image_tool import DescribeImageTool
from .farcaster import SendFarcasterPostTool, DeleteFarcasterPostTool, DeleteFarcasterReactionTool
from .frame_tools import CreateTransactionFrameTool, CreatePollFrameTool, CreateCustomFrameTool, SearchFramesTool, GetFrameCatalogTool
from .matrix import (
    SendMatrixMessageTool, 
    JoinMatrixRoomTool,
    LeaveMatrixRoomTool,
    AcceptMatrixInviteTool, 
    IgnoreMatrixInviteTool,
    ReactToMatrixMessageTool,
    SendMatrixImageTool,
    SendMatrixVideoTool
)
from .node_tools import ExpandNodeTool, CollapseNodeTool, PinNodeTool, UnpinNodeTool, RefreshSummaryTool, GetExpansionStatusTool
from .registry import ToolRegistry

__all__ = [
    "ActionContext",
    "ToolInterface", 
    "ToolRegistry",
    "WaitTool",
    "DescribeImageTool",
    # Matrix Tools (refactored to use ServiceRegistry)
    "SendMatrixMessageTool",
    "JoinMatrixRoomTool", 
    "LeaveMatrixRoomTool",
    "AcceptMatrixInviteTool",
    "IgnoreMatrixInviteTool",
    "ReactToMatrixMessageTool",
    "SendMatrixImageTool",
    "SendMatrixVideoTool",
    # Farcaster Tools
    "SendFarcasterPostTool",
    "DeleteFarcasterPostTool", 
    "DeleteFarcasterReactionTool",
    # Node Tools
    "ExpandNodeTool",
    "CollapseNodeTool",
    "PinNodeTool",
    "UnpinNodeTool",
    "RefreshSummaryTool",
    "GetExpansionStatusTool",
    # Frame Tools
    "CreateTransactionFrameTool",
    "CreatePollFrameTool",
    "CreateCustomFrameTool",
    "SearchFramesTool",
    "GetFrameCatalogTool",
]
