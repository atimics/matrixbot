"""
FastAPI Backend for Chatbot Management UI

Provides comprehensive REST API endpoints for monitoring and controlling
the chatbot system, including tool management, configuration, world state,
and real-time status information.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from chatbot.config import settings
from chatbot.core.orchestration import MainOrchestrator, OrchestratorConfig, ProcessingConfig

logger = logging.getLogger(__name__)


# Pydantic models for API requests/responses
class ToolStatusUpdate(BaseModel):
    enabled: bool


class ConfigUpdate(BaseModel):
    key: str
    value: Any


class NodeAction(BaseModel):
    action: str  # expand, collapse, pin, unpin, refresh_summary
    node_id: str
    force: bool = False


class SystemCommand(BaseModel):
    command: str  # start, stop, restart, reset_processing_mode, force_processing_mode
    parameters: Optional[Dict[str, Any]] = None


class LogWebSocketManager:
    """Manages WebSocket connections for real-time log streaming."""
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.log_handler = None
        
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            
    async def broadcast(self, message: Dict[str, Any]):
        """Broadcast log message to all connected clients."""
        if self.active_connections:
            for connection in self.active_connections.copy():
                try:
                    await connection.send_json(message)
                except Exception:
                    # Remove disconnected clients
                    self.disconnect(connection)


class ChatbotAPIServer:
    """Main API server for chatbot management UI."""
    
    def __init__(self, orchestrator: MainOrchestrator):
        self.orchestrator = orchestrator
        self.app = FastAPI(
            title="Chatbot Management API",
            description="REST API for monitoring and controlling the chatbot system",
            version="1.0.0"
        )
        self.log_manager = LogWebSocketManager()
        self._setup_middleware()
        self._setup_routes()
        self._setup_log_handler()
        
    def _setup_middleware(self):
        """Configure CORS and other middleware."""
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],  # Configure appropriately for production
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
    def _setup_log_handler(self):
        """Set up log handler to stream logs to WebSocket clients."""
        class WebSocketLogHandler(logging.Handler):
            def __init__(self, log_manager):
                super().__init__()
                self.log_manager = log_manager
                
            def emit(self, record):
                log_data = {
                    "timestamp": datetime.fromtimestamp(record.created).isoformat(),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                    "module": record.module,
                    "function": record.funcName,
                    "line": record.lineno
                }
                # Use asyncio to broadcast the log message
                asyncio.create_task(self.log_manager.broadcast(log_data))
        
        # Add the WebSocket handler to the root logger
        websocket_handler = WebSocketLogHandler(self.log_manager)
        websocket_handler.setLevel(logging.INFO)
        logging.getLogger().addHandler(websocket_handler)
        
    def _setup_routes(self):
        """Set up all API routes."""
        
        # ===== SYSTEM STATUS & CONTROL =====
        @self.app.get("/api/status")
        async def get_system_status():
            """Get overall system status and metrics."""
            try:
                # Get processing hub status
                processing_status = await self.orchestrator.processing_hub.get_processing_status()
                
                # Get basic metrics
                world_state_metrics = {
                    "channels_count": len(self.orchestrator.world_state.state.channels),
                    "total_messages": sum(len(ch.messages) for ch in self.orchestrator.world_state.state.channels.values()),
                    "action_history_count": len(self.orchestrator.world_state.state.action_history.actions),
                    "pending_invites": len(self.orchestrator.world_state.get_pending_matrix_invites()),
                    "generated_media_count": len(self.orchestrator.world_state.state.generated_media_library),
                    "research_entries": len(self.orchestrator.world_state.state.research_database.entries)
                }
                
                # Get tool stats
                tool_stats = self.orchestrator.tool_registry.get_tool_stats()
                
                # Rate limiter status
                rate_limit_status = self.orchestrator.rate_limiter.get_status()
                
                return {
                    "system_running": True,  # If API is responding, system is running
                    "processing": processing_status,
                    "world_state": world_state_metrics,
                    "tools": tool_stats,
                    "rate_limits": rate_limit_status,
                    "config": {
                        "ai_model": self.orchestrator.config.ai_model,
                        "processing_mode": "node_based" if self.orchestrator.config.processing_config.enable_node_based_processing else "traditional",
                        "observation_interval": self.orchestrator.config.processing_config.observation_interval,
                        "max_cycles_per_hour": self.orchestrator.config.processing_config.max_cycles_per_hour
                    },
                    "timestamp": datetime.now().isoformat()
                }
            except Exception as e:
                logger.error(f"Error getting system status: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/api/system/command")
        async def execute_system_command(command: SystemCommand):
            """Execute system-level commands."""
            try:
                if command.command == "start":
                    await self.orchestrator.start()
                    return {"success": True, "message": "System started"}
                    
                elif command.command == "stop":
                    await self.orchestrator.stop()
                    return {"success": True, "message": "System stopped"}
                    
                elif command.command == "restart":
                    await self.orchestrator.stop()
                    await self.orchestrator.start()
                    return {"success": True, "message": "System restarted"}
                    
                elif command.command == "reset_processing_mode":
                    self.orchestrator.processing_hub.reset_processing_mode()
                    return {"success": True, "message": "Processing mode reset"}
                    
                elif command.command == "force_processing_mode":
                    mode = command.parameters.get("mode") if command.parameters else None
                    if mode not in ["traditional", "node_based"]:
                        raise HTTPException(status_code=400, detail="Invalid processing mode")
                    enable_node_based = (mode == "node_based")
                    self.orchestrator.processing_hub.force_processing_mode(enable_node_based)
                    return {"success": True, "message": f"Processing mode forced to {mode}"}
                    
                else:
                    raise HTTPException(status_code=400, detail=f"Unknown command: {command.command}")
                    
            except Exception as e:
                logger.error(f"Error executing system command {command.command}: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        # ===== CONFIGURATION MANAGEMENT =====
        @self.app.get("/api/config")
        async def get_configuration():
            """Get current system configuration."""
            try:
                # Get all settings from the config
                config_dict = {
                    # Core settings
                    "AI_MODEL": settings.AI_MODEL,
                    "WEB_SEARCH_MODEL": settings.WEB_SEARCH_MODEL,
                    "AI_SUMMARY_MODEL": settings.AI_SUMMARY_MODEL,
                    "OPENROUTER_MULTIMODAL_MODEL": settings.OPENROUTER_MULTIMODAL_MODEL,
                    
                    # Processing settings
                    "OBSERVATION_INTERVAL": settings.OBSERVATION_INTERVAL,
                    "MAX_CYCLES_PER_HOUR": settings.MAX_CYCLES_PER_HOUR,
                    "LOG_LEVEL": settings.LOG_LEVEL,
                    
                    # Tool cooldowns
                    "IMAGE_GENERATION_COOLDOWN_SECONDS": settings.IMAGE_GENERATION_COOLDOWN_SECONDS,
                    "RESEARCH_COOLDOWN_SECONDS": settings.RESEARCH_COOLDOWN_SECONDS,
                    "REPLY_COOLDOWN_SECONDS": settings.REPLY_COOLDOWN_SECONDS,
                    
                    # Integration settings
                    "MATRIX_HOMESERVER": settings.MATRIX_HOMESERVER,
                    "FARCASTER_BOT_FID": settings.FARCASTER_BOT_FID,
                    
                    # File paths
                    "CHATBOT_DB_PATH": settings.CHATBOT_DB_PATH,
                    "CONTEXT_STORAGE_PATH": settings.CONTEXT_STORAGE_PATH,
                    
                    # Processing config from orchestrator
                    "enable_node_based_processing": self.orchestrator.config.processing_config.enable_node_based_processing,
                }
                
                return {
                    "config": config_dict,
                    "mutable_keys": [
                        "LOG_LEVEL", "OBSERVATION_INTERVAL", "MAX_CYCLES_PER_HOUR",
                        "AI_MODEL", "WEB_SEARCH_MODEL", "AI_SUMMARY_MODEL", "OPENROUTER_MULTIMODAL_MODEL",
                        "IMAGE_GENERATION_COOLDOWN_SECONDS", "RESEARCH_COOLDOWN_SECONDS", "REPLY_COOLDOWN_SECONDS"
                    ],
                    "timestamp": datetime.now().isoformat()
                }
            except Exception as e:
                logger.error(f"Error getting configuration: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.put("/api/config")
        async def update_configuration(update: ConfigUpdate):
            """Update a configuration value."""
            try:
                # Note: This is a simplified implementation
                # In a real system, you'd want to validate the key and value,
                # and handle different types of config updates appropriately
                if not hasattr(settings, update.key):
                    raise HTTPException(status_code=400, detail=f"Unknown config key: {update.key}")
                
                # Update the setting (this is basic - in practice you'd want more validation)
                setattr(settings, update.key, update.value)
                
                # If it's an AI model setting, update the AI engine
                if update.key in ["AI_MODEL"]:
                    self.orchestrator.ai_engine.model = update.value
                    # Update system prompt with tools to reflect any changes
                    self.orchestrator.ai_engine.update_system_prompt_with_tools(self.orchestrator.tool_registry)
                
                return {
                    "success": True,
                    "message": f"Configuration {update.key} updated to {update.value}",
                    "restart_required": update.key in [
                        "MATRIX_HOMESERVER", "FARCASTER_BOT_FID", 
                        "CHATBOT_DB_PATH", "CONTEXT_STORAGE_PATH"
                    ]
                }
            except Exception as e:
                logger.error(f"Error updating configuration: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        # ===== TOOL MANAGEMENT =====
        @self.app.get("/api/tools")
        async def list_tools():
            """Get all tools with their status and metadata."""
            try:
                tools = self.orchestrator.tool_registry.get_all_tools_with_status()
                stats = self.orchestrator.tool_registry.get_tool_stats()
                
                return {
                    "tools": tools,
                    "stats": stats,
                    "timestamp": datetime.now().isoformat()
                }
            except Exception as e:
                logger.error(f"Error listing tools: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.put("/api/tools/{tool_name}/status")
        async def update_tool_status(tool_name: str, status_update: ToolStatusUpdate):
            """Enable or disable a specific tool."""
            try:
                success = self.orchestrator.tool_registry.set_tool_enabled(tool_name, status_update.enabled)
                if not success:
                    raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")
                
                # Update the AI engine's system prompt to reflect the change
                self.orchestrator.ai_engine.update_system_prompt_with_tools(self.orchestrator.tool_registry)
                
                return {
                    "success": True,
                    "tool_name": tool_name,
                    "enabled": status_update.enabled,
                    "message": f"Tool '{tool_name}' {'enabled' if status_update.enabled else 'disabled'}"
                }
            except Exception as e:
                logger.error(f"Error updating tool status: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/tools/{tool_name}")
        async def get_tool_details(tool_name: str):
            """Get detailed information about a specific tool."""
            try:
                tool = self.orchestrator.tool_registry.get_tool(tool_name)
                if not tool:
                    raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")
                
                return {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters_schema": tool.parameters_schema,
                    "enabled": self.orchestrator.tool_registry.is_tool_enabled(tool_name),
                    "class_name": tool.__class__.__name__,
                    "timestamp": datetime.now().isoformat()
                }
            except Exception as e:
                logger.error(f"Error getting tool details: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        # ===== AI ENGINE MONITORING =====
        @self.app.get("/api/ai/prompt")
        async def get_ai_prompt():
            """Get the current AI system prompt."""
            try:
                return {
                    "system_prompt": self.orchestrator.ai_engine.system_prompt,
                    "model": self.orchestrator.ai_engine.model,
                    "enabled_tools_count": len(self.orchestrator.tool_registry.get_enabled_tools()),
                    "timestamp": datetime.now().isoformat()
                }
            except Exception as e:
                logger.error(f"Error getting AI prompt: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/ai/models")
        async def get_ai_models():
            """Get available AI models and current selections."""
            try:
                return {
                    "current": {
                        "main": settings.AI_MODEL,
                        "web_search": settings.WEB_SEARCH_MODEL,
                        "summary": settings.AI_SUMMARY_MODEL,
                        "multimodal": settings.OPENROUTER_MULTIMODAL_MODEL
                    },
                    "available": [
                        "openai/gpt-4o-mini",
                        "openai/gpt-4o",
                        "anthropic/claude-3-sonnet",
                        "anthropic/claude-3-haiku",
                        "google/gemini-pro",
                        "meta-llama/llama-3.1-70b-instruct"
                    ],
                    "timestamp": datetime.now().isoformat()
                }
            except Exception as e:
                logger.error(f"Error getting AI models: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        # ===== WORLD STATE EXPLORER =====
        @self.app.get("/api/worldstate")
        async def get_world_state():
            """Get current world state information."""
            try:
                # Get traditional world state
                state_dict = self.orchestrator.world_state.to_dict()
                
                # Add node-based information if available
                node_info = {}
                if hasattr(self.orchestrator.processing_hub, 'node_manager') and self.orchestrator.processing_hub.node_manager:
                    node_manager = self.orchestrator.processing_hub.node_manager
                    node_info = {
                        "expanded_nodes": list(node_manager.expanded_nodes.keys()),
                        "collapsed_summaries": list(node_manager.collapsed_node_summaries.keys()),
                        "pinned_nodes": list(node_manager.pinned_nodes),
                        "system_events": node_manager.get_system_events()[-10:],  # Last 10 events
                        "expansion_status": node_manager.get_expansion_status_summary()
                    }
                
                return {
                    "traditional_state": state_dict,
                    "node_state": node_info,
                    "processing_mode": "node_based" if self.orchestrator.config.processing_config.enable_node_based_processing else "traditional",
                    "timestamp": datetime.now().isoformat()
                }
            except Exception as e:
                logger.error(f"Error getting world state: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/worldstate/channels")
        async def get_channels():
            """Get detailed channel information."""
            try:
                channels = {}
                for channel_id, channel in self.orchestrator.world_state.state.channels.items():
                    channels[channel_id] = {
                        "id": channel.id,
                        "name": channel.name,
                        "platform": channel.platform,
                        "message_count": len(channel.messages),
                        "recent_messages": [
                            {
                                "id": msg.id,
                                "content": msg.content[:100] + "..." if len(msg.content) > 100 else msg.content,
                                "author": msg.author,
                                "timestamp": msg.timestamp.isoformat() if msg.timestamp else None,
                                "platform": msg.platform
                            }
                            for msg in channel.messages[-5:]  # Last 5 messages
                        ]
                    }
                
                return {
                    "channels": channels,
                    "total_channels": len(channels),
                    "timestamp": datetime.now().isoformat()
                }
            except Exception as e:
                logger.error(f"Error getting channels: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/api/worldstate/node/action")
        async def execute_node_action(action: NodeAction):
            """Execute an action on a node (expand, collapse, pin, unpin, refresh)."""
            try:
                if not hasattr(self.orchestrator.processing_hub, 'node_manager') or not self.orchestrator.processing_hub.node_manager:
                    raise HTTPException(status_code=400, detail="Node-based processing not available")
                
                node_manager = self.orchestrator.processing_hub.node_manager
                
                if action.action == "expand":
                    await node_manager.expand_node(action.node_id, force=action.force)
                elif action.action == "collapse":
                    await node_manager.collapse_node(action.node_id)
                elif action.action == "pin":
                    node_manager.pin_node(action.node_id)
                elif action.action == "unpin":
                    node_manager.unpin_node(action.node_id)
                elif action.action == "refresh_summary":
                    # This would trigger the NodeSummaryService to refresh the summary
                    if hasattr(self.orchestrator.processing_hub, 'node_summary_service'):
                        await self.orchestrator.processing_hub.node_summary_service.refresh_summary(action.node_id)
                else:
                    raise HTTPException(status_code=400, detail=f"Unknown action: {action.action}")
                
                return {
                    "success": True,
                    "action": action.action,
                    "node_id": action.node_id,
                    "message": f"Action '{action.action}' executed on node '{action.node_id}'"
                }
            except Exception as e:
                logger.error(f"Error executing node action: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        # ===== INTEGRATIONS MONITORING =====
        @self.app.get("/api/integrations")
        async def get_integrations_status():
            """Get status of all integrations."""
            try:
                integrations = {}
                
                # Matrix integration
                matrix_status = {
                    "connected": False,
                    "monitored_rooms": [],
                    "pending_invites": 0
                }
                if hasattr(self.orchestrator, 'matrix_observer') and self.orchestrator.matrix_observer:
                    matrix_status["connected"] = getattr(self.orchestrator.matrix_observer.client, 'logged_in', False)
                    matrix_status["monitored_rooms"] = getattr(self.orchestrator.matrix_observer, 'channels_to_monitor', [])
                    matrix_status["pending_invites"] = len(self.orchestrator.world_state.get_pending_matrix_invites())
                
                integrations["matrix"] = matrix_status
                
                # Farcaster integration
                farcaster_status = {
                    "connected": False,
                    "bot_fid": settings.FARCASTER_BOT_FID,
                    "post_queue_size": 0,
                    "reply_queue_size": 0
                }
                if hasattr(self.orchestrator, 'farcaster_observer') and self.orchestrator.farcaster_observer:
                    farcaster_status["connected"] = True  # If observer exists, assume connected
                    if hasattr(self.orchestrator.farcaster_observer, 'scheduler'):
                        scheduler = self.orchestrator.farcaster_observer.scheduler
                        farcaster_status["post_queue_size"] = getattr(scheduler.post_queue, 'qsize', lambda: 0)()
                        farcaster_status["reply_queue_size"] = getattr(scheduler.reply_queue, 'qsize', lambda: 0)()
                
                integrations["farcaster"] = farcaster_status
                
                # Ecosystem Token Service
                token_status = {
                    "active": False,
                    "monitored_holders": 0,
                    "contract_address": None
                }
                if self.orchestrator.world_state.state.monitored_token_holders:
                    token_status["active"] = True
                    token_status["monitored_holders"] = len(self.orchestrator.world_state.state.monitored_token_holders)
                if self.orchestrator.world_state.state.token_metadata:
                    token_status["contract_address"] = getattr(self.orchestrator.world_state.state.token_metadata, 'contract_address', None)
                
                integrations["ecosystem_token"] = token_status
                
                return {
                    "integrations": integrations,
                    "timestamp": datetime.now().isoformat()
                }
            except Exception as e:
                logger.error(f"Error getting integrations status: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        # ===== LOGGING & HISTORY =====
        @self.app.websocket("/api/logs/stream")
        async def websocket_logs(websocket: WebSocket):
            """WebSocket endpoint for streaming live logs."""
            await self.log_manager.connect(websocket)
            try:
                while True:
                    # Keep the connection alive
                    await websocket.receive_text()
            except WebSocketDisconnect:
                self.log_manager.disconnect(websocket)
        
        @self.app.get("/api/logs/recent")
        async def get_recent_logs():
            """Get recent log entries."""
            try:
                # This is a simplified implementation
                # In a real system, you'd want to read from a log file or database
                return {
                    "logs": [
                        {
                            "timestamp": datetime.now().isoformat(),
                            "level": "INFO",
                            "logger": "chatbot.api",
                            "message": "Recent logs endpoint called",
                            "module": "api_server",
                            "function": "get_recent_logs",
                            "line": 0
                        }
                    ],
                    "count": 1,
                    "timestamp": datetime.now().isoformat()
                }
            except Exception as e:
                logger.error(f"Error getting recent logs: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/history/actions")
        async def get_action_history():
            """Get recent action history."""
            try:
                actions = []
                for action in self.orchestrator.world_state.state.action_history.actions[-20:]:  # Last 20 actions
                    actions.append({
                        "id": action.id,
                        "type": action.type,
                        "description": action.description,
                        "timestamp": action.timestamp.isoformat() if action.timestamp else None,
                        "channel_id": action.channel_id,
                        "status": action.status,
                        "metadata": action.metadata
                    })
                
                return {
                    "actions": actions,
                    "total_actions": len(self.orchestrator.world_state.state.action_history.actions),
                    "timestamp": datetime.now().isoformat()
                }
            except Exception as e:
                logger.error(f"Error getting action history: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        # ===== STATIC FILES (for UI) =====
        # Serve the UI from the ui directory
        from fastapi.responses import FileResponse
        import os
        
        @self.app.get("/")
        async def serve_root():
            """Redirect root to UI."""
            ui_file = os.path.join(os.getcwd(), "ui", "index.html")
            if os.path.exists(ui_file):
                return FileResponse(ui_file)
            else:
                raise HTTPException(status_code=404, detail="UI not found. Please ensure ui/index.html exists.")
            
        @self.app.get("/ui/{file_path:path}")
        async def serve_ui_files(file_path: str):
            """Serve UI static files."""
            ui_path = os.path.join(os.getcwd(), "ui", file_path)
            if os.path.exists(ui_path) and os.path.isfile(ui_path):
                return FileResponse(ui_path)
            else:
                # Fallback to index.html for SPA routing
                index_path = os.path.join(os.getcwd(), "ui", "index.html")
                if os.path.exists(index_path):
                    return FileResponse(index_path)
                else:
                    raise HTTPException(status_code=404, detail="File not found")


def create_api_server(orchestrator: MainOrchestrator) -> FastAPI:
    """
    Create and configure the FastAPI server for the chatbot management UI.
    
    Args:
        orchestrator: The main orchestrator instance to manage
        
    Returns:
        Configured FastAPI application
    """
    api_server = ChatbotAPIServer(orchestrator)
    return api_server.app


if __name__ == "__main__":
    import uvicorn
    from chatbot.core.orchestration import MainOrchestrator, OrchestratorConfig, ProcessingConfig
    
    # Create a test orchestrator for development
    config = OrchestratorConfig(
        processing_config=ProcessingConfig(
            enable_node_based_processing=False,
            observation_interval=30,
            max_cycles_per_hour=60
        )
    )
    
    test_orchestrator = MainOrchestrator(config)
    app = create_api_server(test_orchestrator)
    
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
