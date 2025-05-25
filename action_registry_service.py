import json
import logging
from typing import Dict, List, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

class ActionRegistryService:
    """Service that manages the registry of available actions for AI planning."""
    
    def __init__(self, registry_file_path: str = "actions_registry.json"):
        self.registry_file_path = registry_file_path
        self.actions: Dict[str, Dict[str, Any]] = {}
        self._load_actions()
    
    def _load_actions(self) -> None:
        """Load actions from the registry JSON file."""
        try:
            registry_path = Path(self.registry_file_path)
            if not registry_path.exists():
                logger.error(f"ActionRegistry: Registry file not found: {self.registry_file_path}")
                return
            
            with open(registry_path, 'r', encoding='utf-8') as f:
                registry_data = json.load(f)
            
            actions_list = registry_data.get("actions", [])
            for action_def in actions_list:
                action_name = action_def.get("name")
                if action_name:
                    self.actions[action_name] = action_def
                    logger.debug(f"ActionRegistry: Loaded action '{action_name}'")
            
            logger.info(f"ActionRegistry: Successfully loaded {len(self.actions)} actions from {self.registry_file_path}")
            
        except Exception as e:
            logger.error(f"ActionRegistry: Failed to load actions from {self.registry_file_path}: {e}")
    
    def get_action_definition(self, action_name: str) -> Optional[Dict[str, Any]]:
        """Get the definition for a specific action."""
        return self.actions.get(action_name)
    
    def get_all_action_names(self) -> List[str]:
        """Get list of all available action names."""
        return list(self.actions.keys())
    
    def get_all_action_definitions(self) -> List[Dict[str, Any]]:
        """Get all action definitions."""
        return list(self.actions.values())
    
    def generate_planner_schema(self) -> Dict[str, Any]:
        """Generate the JSON schema for the AI Planner's response format."""
        # Create enum of all action names
        action_names = self.get_all_action_names()
        
        # Base schema structure
        schema = {
            "type": "object",
            "properties": {
                "channel_responses": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "channel_id": {
                                "type": "string",
                                "description": "The Matrix room/channel ID to respond to"
                            },
                            "actions": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "action_name": {
                                            "type": "string",
                                            "enum": action_names,
                                            "description": "The name of the action to execute"
                                        },
                                        "parameters": {
                                            "type": "object",
                                            "description": "Parameters specific to the chosen action"
                                        }
                                    },
                                    "required": ["action_name", "parameters"],
                                    "additionalProperties": False
                                }
                            }
                        },
                        "required": ["channel_id", "actions"],
                        "additionalProperties": False
                    }
                }
            },
            "required": ["channel_responses"],
            "additionalProperties": False
        }
        
        return schema
    
    def validate_action_parameters(self, action_name: str, parameters: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Validate parameters for a specific action."""
        action_def = self.get_action_definition(action_name)
        if not action_def:
            return False, f"Unknown action: {action_name}"
        
        param_schema = action_def.get("parameters", {})
        required_params = param_schema.get("required", [])
        properties = param_schema.get("properties", {})
        
        # Check required parameters
        for required_param in required_params:
            if required_param not in parameters:
                return False, f"Missing required parameter '{required_param}' for action '{action_name}'"
        
        # Check parameter types (basic validation)
        for param_name, param_value in parameters.items():
            if param_name in properties:
                expected_type = properties[param_name].get("type")
                if expected_type == "string" and not isinstance(param_value, str):
                    return False, f"Parameter '{param_name}' must be a string"
                elif expected_type == "array" and not isinstance(param_value, list):
                    return False, f"Parameter '{param_name}' must be an array"
                elif expected_type == "boolean" and not isinstance(param_value, bool):
                    return False, f"Parameter '{param_name}' must be a boolean"
        
        return True, None
    
    def get_action_descriptions_for_prompt(self) -> str:
        """Generate a formatted string of action descriptions for AI prompts."""
        descriptions = []
        for action_name, action_def in self.actions.items():
            description = action_def.get("description", "No description available")
            parameters = action_def.get("parameters", {}).get("properties", {})
            
            param_descriptions = []
            for param_name, param_info in parameters.items():
                param_desc = param_info.get("description", "No description")
                param_type = param_info.get("type", "unknown")
                param_descriptions.append(f"  - {param_name} ({param_type}): {param_desc}")
            
            param_text = "\n".join(param_descriptions) if param_descriptions else "  No parameters"
            
            action_text = f"• {action_name}: {description}\n{param_text}"
            descriptions.append(action_text)
        
        return "\n\n".join(descriptions)
    
    def reload_actions(self) -> None:
        """Reload actions from the registry file."""
        logger.info("ActionRegistry: Reloading actions from registry file...")
        self.actions.clear()
        self._load_actions()