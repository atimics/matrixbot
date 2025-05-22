import logging
import uuid
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, ValidationError

from tool_base import AbstractTool, ToolResult
from event_definitions import RequestMatrixRoomInfoCommand

logger = logging.getLogger(__name__)

class GetRoomInfoTool(AbstractTool):
    class ArgsModel(BaseModel):
        info_type: str

    def get_definition(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_room_info",
                "description": "Fetches information about the current Matrix room (name, topic, members).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "info_type": {
                            "type": "string",
                            "enum": ["name", "topic", "members", "all"],
                            "description": "Which information to fetch."
                        }
                    },
                    "required": ["info_type"]
                }
            }
        }

    async def execute(
        self,
        room_id: str,
        arguments: Dict[str, Any],
        tool_call_id: Optional[str],
        llm_provider_info: Dict[str, Any],
        conversation_history_snapshot: List[Dict[str, Any]],
        last_user_event_id: Optional[str],
        db_path: Optional[str] = None
    ) -> ToolResult:
        try:
            args = self.ArgsModel(**arguments)
        except ValidationError as ve:
            return ToolResult(status="failure", result_for_llm_history="[Invalid arguments for get_room_info]", error_message=str(ve))

        aspects_map = {
            "name": ["name"],
            "topic": ["topic"],
            "members": ["members"],
            "all": ["name", "topic", "members"]
        }
        aspects = aspects_map.get(args.info_type, [args.info_type])
        response_topic = f"room_info_response_{tool_call_id or uuid.uuid4()}"
        command = RequestMatrixRoomInfoCommand(
            room_id=room_id,
            aspects=aspects,
            response_event_topic=response_topic,
            original_tool_call_id=tool_call_id or "unknown"
        )
        return ToolResult(
            status="requires_llm_followup",
            result_for_llm_history="[Fetching room information...]",
            commands_to_publish=[command]
        )
