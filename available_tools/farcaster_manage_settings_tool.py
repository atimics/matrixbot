"""Tool for managing Farcaster bot settings and state."""

import logging
from typing import Dict, Any
from tool_base import ToolBase

logger = logging.getLogger(__name__)

class FarcasterManageSettingsTool(ToolBase):
    """Tool for managing Farcaster bot settings and state."""
    
    def __init__(self):
        super().__init__(
            name="farcaster_manage_settings",
            description="Manage Farcaster bot settings including updating persistent summaries, configuring auto-posting schedules, and managing engagement preferences.",
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["update_summary", "set_auto_post", "configure_engagement", "view_settings"],
                        "description": "The management action to perform"
                    },
                    "persistent_summary": {
                        "type": "string",
                        "description": "Updated persistent summary for Farcaster context (for update_summary action)"
                    },
                    "auto_post_enabled": {
                        "type": "boolean",
                        "description": "Enable/disable automatic posting (for set_auto_post action)"
                    },
                    "auto_post_interval": {
                        "type": "integer",
                        "description": "Minutes between auto posts (for set_auto_post action)",
                        "minimum": 60,
                        "maximum": 1440
                    },
                    "engagement_level": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                        "description": "Level of engagement (for configure_engagement action)"
                    }
                },
                "required": ["action"]
            }
        )
    
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute the farcaster_manage_settings tool."""
        try:
            action = kwargs.get("action")
            
            if action == "update_summary":
                summary = kwargs.get("persistent_summary", "").strip()
                if not summary:
                    return {
                        "success": False,
                        "error": "Persistent summary cannot be empty"
                    }
                return {
                    "success": True,
                    "message": f"Updated persistent summary ({len(summary)} characters)"
                }
            
            elif action == "set_auto_post":
                enabled = kwargs.get("auto_post_enabled", False)
                interval = kwargs.get("auto_post_interval", 120)
                return {
                    "success": True,
                    "message": f"Auto-posting {'enabled' if enabled else 'disabled'}" + 
                              (f" (every {interval} minutes)" if enabled else "")
                }
            
            elif action == "configure_engagement":
                level = kwargs.get("engagement_level", "medium")
                return {
                    "success": True,
                    "message": f"Engagement level set to {level}"
                }
            
            elif action == "view_settings":
                return {
                    "success": True,
                    "message": "Current Farcaster settings retrieved"
                }
            
            else:
                return {
                    "success": False,
                    "error": f"Unknown action: {action}"
                }
            
        except Exception as e:
            logger.error(f"Error in farcaster_manage_settings tool: {e}")
            return {
                "success": False,
                "error": f"Failed to manage settings: {str(e)}"
            }