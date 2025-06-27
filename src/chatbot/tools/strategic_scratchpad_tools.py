"""
Strategic Scratchpad Tools - Inner Monologue for Commander AI

This module implements the Strategic Scratchpad system described in the 
stabilization report. It provides a persistent "inner monologue" workspace
for the AdaptiveProcessor (Commander AI) to track complex, multi-step reasoning.

Key Benefits:
- Externalized thought process for complex task decomposition
- Persistent state across multiple event cycles
- Transparency and debuggability of AI reasoning
- Stateful reasoning that maintains context over time

These tools are restricted to strategic access level (Commander AI only).
"""

import logging
import time
from typing import Any, Dict

from .base import ToolInterface, ActionContext

logger = logging.getLogger(__name__)


class StrategicScratchpad:
    """
    Persistent key-value store for the Commander AI's strategic reasoning.
    
    This serves as the AI's "inner monologue" workspace, allowing it to:
    - Break down complex tasks into manageable steps
    - Track progress on multi-step operations
    - Maintain context across multiple processing cycles
    - Debug and analyze its own reasoning process
    """
    
    def __init__(self):
        self._notes: Dict[str, str] = {}
        self._metadata: Dict[str, Dict[str, Any]] = {}
        self._creation_time = time.time()
        logger.debug("StrategicScratchpad initialized")
    
    def write(self, key: str, value: str) -> Dict[str, Any]:
        """Add or update a note in the scratchpad."""
        old_value = self._notes.get(key)
        self._notes[key] = value
        self._metadata[key] = {
            "updated_at": time.time(),
            "character_count": len(value),
            "is_new": old_value is None
        }
        
        action = "created" if old_value is None else "updated"
        logger.debug(f"Scratchpad note '{key}' {action}")
        
        return {
            "status": "success",
            "action": action,
            "key": key,
            "character_count": len(value),
            "previous_value": old_value
        }
    
    def append(self, key: str, text_to_append: str, separator: str = "\n") -> Dict[str, Any]:
        """Append text to an existing note."""
        current_value = self._notes.get(key, "")
        
        if current_value:
            new_value = current_value + separator + text_to_append
        else:
            new_value = text_to_append
            
        return self.write(key, new_value)
    
    def read(self, key: str) -> Dict[str, Any]:
        """Read a note from the scratchpad."""
        if key not in self._notes:
            return {
                "status": "error",
                "error": f"Note '{key}' not found",
                "available_keys": list(self._notes.keys())
            }
        
        value = self._notes[key]
        metadata = self._metadata.get(key, {})
        
        return {
            "status": "success",
            "key": key,
            "value": value,
            "metadata": metadata,
            "character_count": len(value)
        }
    
    def list_notes(self) -> Dict[str, Any]:
        """List all notes with their metadata."""
        notes_summary = []
        
        for key, value in self._notes.items():
            metadata = self._metadata.get(key, {})
            notes_summary.append({
                "key": key,
                "character_count": len(value),
                "preview": value[:100] + "..." if len(value) > 100 else value,
                "updated_at": metadata.get("updated_at"),
                "is_recent": time.time() - metadata.get("updated_at", 0) < 300  # Last 5 minutes
            })
        
        # Sort by most recently updated
        notes_summary.sort(key=lambda x: x.get("updated_at", 0), reverse=True)
        
        return {
            "status": "success",
            "total_notes": len(notes_summary),
            "notes": notes_summary,
            "scratchpad_age_minutes": (time.time() - self._creation_time) / 60
        }
    
    def clear(self) -> Dict[str, Any]:
        """Clear all notes from the scratchpad."""
        cleared_count = len(self._notes)
        cleared_keys = list(self._notes.keys())
        
        self._notes.clear()
        self._metadata.clear()
        
        logger.info(f"Scratchpad cleared - removed {cleared_count} notes")
        
        return {
            "status": "success",
            "cleared_count": cleared_count,
            "cleared_keys": cleared_keys,
            "message": f"Cleared {cleared_count} notes from scratchpad"
        }
    
    def delete(self, key: str) -> Dict[str, Any]:
        """Delete a specific note from the scratchpad."""
        if key not in self._notes:
            return {
                "status": "error",
                "error": f"Note '{key}' not found",
                "available_keys": list(self._notes.keys())
            }
        
        deleted_value = self._notes.pop(key)
        self._metadata.pop(key, None)
        
        logger.debug(f"Scratchpad note '{key}' deleted")
        
        return {
            "status": "success",
            "key": key,
            "deleted_value": deleted_value,
            "message": f"Deleted note '{key}'"
        }


# Global scratchpad instance for the Commander AI
_commander_scratchpad = StrategicScratchpad()


class ScratchpadWriteTool(ToolInterface):
    """Tool for writing notes to the strategic scratchpad."""
    
    @property
    def name(self) -> str:
        return "scratchpad_write"
    
    @property
    def description(self) -> str:
        return (
            "Add or update a note in your strategic scratchpad. Use this to track "
            "complex multi-step tasks, reasoning processes, or important insights "
            "that should persist across processing cycles. Perfect for breaking down "
            "large problems into manageable steps."
        )
    
    @property
    def access_level(self) -> str:
        return 'strategic'
    
    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "Unique identifier for the note (e.g., 'plan', 'progress', 'analysis')"
                },
                "value": {
                    "type": "string", 
                    "description": "Content to write to the note"
                }
            },
            "required": ["key", "value"]
        }
    
    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """Execute the scratchpad write operation."""
        key = params.get("key", "").strip()
        value = params.get("value", "").strip()
        
        if not key:
            return {
                "status": "error",
                "error": "Key parameter is required and cannot be empty"
            }
        
        if not value:
            return {
                "status": "error",
                "error": "Value parameter is required and cannot be empty"
            }
        
        try:
            result = _commander_scratchpad.write(key, value)
            logger.info(f"Commander AI wrote to scratchpad: {key} ({result.get('character_count', 0)} chars)")
            return result
        except Exception as e:
            logger.error(f"ScratchpadWriteTool error: {e}")
            return {
                "status": "error",
                "error": f"Failed to write to scratchpad: {str(e)}"
            }


class ScratchpadAppendTool(ToolInterface):
    """Tool for appending text to existing scratchpad notes."""
    
    @property
    def name(self) -> str:
        return "scratchpad_append"
    
    @property
    def description(self) -> str:
        return (
            "Append text to an existing note in your strategic scratchpad. "
            "Useful for adding progress updates, new insights, or additional "
            "steps to an existing plan without overwriting previous content."
        )
    
    @property
    def access_level(self) -> str:
        return 'strategic'
    
    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "Key of the existing note to append to"
                },
                "text_to_append": {
                    "type": "string",
                    "description": "Text to append to the existing note"
                },
                "separator": {
                    "type": "string",
                    "description": "Separator between existing and new text (default: newline)",
                    "default": "\n"
                }
            },
            "required": ["key", "text_to_append"]
        }
    
    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """Execute the scratchpad append operation."""
        key = params.get("key", "").strip()
        text_to_append = params.get("text_to_append", "").strip()
        separator = params.get("separator", "\n")
        
        if not key:
            return {
                "status": "error",
                "error": "Key parameter is required and cannot be empty"
            }
        
        if not text_to_append:
            return {
                "status": "error",
                "error": "Text to append parameter is required and cannot be empty"
            }
        
        try:
            result = _commander_scratchpad.append(key, text_to_append, separator)
            logger.info(f"Commander AI appended to scratchpad: {key}")
            return result
        except Exception as e:
            logger.error(f"ScratchpadAppendTool error: {e}")
            return {
                "status": "error",
                "error": f"Failed to append to scratchpad: {str(e)}"
            }


class ScratchpadReadTool(ToolInterface):
    """Tool for reading notes from the strategic scratchpad."""
    
    @property
    def name(self) -> str:
        return "scratchpad_read"
    
    @property
    def description(self) -> str:
        return (
            "Read a specific note from your strategic scratchpad. Use this to "
            "review previous analysis, check progress on tasks, or recall "
            "important insights from earlier processing cycles."
        )
    
    @property
    def access_level(self) -> str:
        return 'strategic'
    
    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "Key of the note to read"
                }
            },
            "required": ["key"]
        }
    
    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """Execute the scratchpad read operation."""
        key = params.get("key", "").strip()
        
        if not key:
            return {
                "status": "error",
                "error": "Key parameter is required and cannot be empty"
            }
        
        try:
            result = _commander_scratchpad.read(key)
            if result.get("status") == "success":
                logger.debug(f"Commander AI read from scratchpad: {key}")
            return result
        except Exception as e:
            logger.error(f"ScratchpadReadTool error: {e}")
            return {
                "status": "error",
                "error": f"Failed to read from scratchpad: {str(e)}"
            }


class ScratchpadListTool(ToolInterface):
    """Tool for listing all notes in the strategic scratchpad."""
    
    @property
    def name(self) -> str:
        return "scratchpad_list"
    
    @property
    def description(self) -> str:
        return (
            "List all notes in your strategic scratchpad with previews and metadata. "
            "Use this to get an overview of your current reasoning state, see what "
            "tasks are being tracked, and identify areas that need attention."
        )
    
    @property
    def access_level(self) -> str:
        return 'strategic'
    
    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": []
        }
    
    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """Execute the scratchpad list operation."""
        try:
            result = _commander_scratchpad.list_notes()
            logger.debug(f"Commander AI listed scratchpad contents: {result.get('total_notes', 0)} notes")
            return result
        except Exception as e:
            logger.error(f"ScratchpadListTool error: {e}")
            return {
                "status": "error",
                "error": f"Failed to list scratchpad contents: {str(e)}"
            }


class ScratchpadClearTool(ToolInterface):
    """Tool for clearing all notes from the strategic scratchpad."""
    
    @property
    def name(self) -> str:
        return "scratchpad_clear"
    
    @property
    def description(self) -> str:
        return (
            "Clear all notes from your strategic scratchpad. Use this when starting "
            "a new task or when you want to reset your reasoning workspace. "
            "This action cannot be undone."
        )
    
    @property
    def access_level(self) -> str:
        return 'strategic'
    
    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": []
        }
    
    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """Execute the scratchpad clear operation."""
        try:
            result = _commander_scratchpad.clear()
            logger.info(f"Commander AI cleared scratchpad: {result.get('cleared_count', 0)} notes removed")
            return result
        except Exception as e:
            logger.error(f"ScratchpadClearTool error: {e}")
            return {
                "status": "error",
                "error": f"Failed to clear scratchpad: {str(e)}"
            }


class ScratchpadDeleteTool(ToolInterface):
    """Tool for deleting specific notes from the strategic scratchpad."""
    
    @property
    def name(self) -> str:
        return "scratchpad_delete"
    
    @property
    def description(self) -> str:
        return (
            "Delete a specific note from your strategic scratchpad. Use this to "
            "remove outdated analysis, completed tasks, or incorrect reasoning "
            "that is no longer relevant."
        )
    
    @property
    def access_level(self) -> str:
        return 'strategic'
    
    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "Key of the note to delete"
                }
            },
            "required": ["key"]
        }
    
    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """Execute the scratchpad delete operation."""
        key = params.get("key", "").strip()
        
        if not key:
            return {
                "status": "error",
                "error": "Key parameter is required and cannot be empty"
            }
        
        try:
            result = _commander_scratchpad.delete(key)
            if result.get("status") == "success":
                logger.info(f"Commander AI deleted from scratchpad: {key}")
            return result
        except Exception as e:
            logger.error(f"ScratchpadDeleteTool error: {e}")
            return {
                "status": "error",
                "error": f"Failed to delete from scratchpad: {str(e)}"
            }
