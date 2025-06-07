"""
FastAPI Backend for Chatbot Management UI - DEPRECATED

⚠️ DEPRECATION NOTICE ⚠️

This monolithic api_server.py file has been DEPRECATED and replaced with a modular 
architecture. Please use the new modular API server instead:

    from chatbot.api_server import create_api_server, ChatbotAPIServer

The new modular structure is located in:
- chatbot/api_server/main.py (main server class)
- chatbot/api_server/routers/ (organized route handlers)
- chatbot/api_server/services/ (shared services)
- chatbot/api_server/schemas.py (Pydantic models)

This file is kept for backwards compatibility only and will be removed in a future version.

---

Original monolithic implementation below (DO NOT USE):
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
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


class IntegrationConfig(BaseModel):
    integration_type: str
    display_name: str
    config: Dict[str, Any]
    credentials: Dict[str, str]


class IntegrationStatus(BaseModel):
    id: str
    integration_type: str
    display_name: str
    is_active: bool
    is_connected: bool
    status_details: Dict[str, Any]


class IntegrationTestRequest(BaseModel):
    integration_type: str
    config: Dict[str, Any]
    credentials: Dict[str, str]


class SetupStep(BaseModel):
    key: str
    question: str
    type: str = "text"  # text, password, select
    options: Optional[List[str]] = None
    validation: Optional[str] = None


class SetupSubmission(BaseModel):
    step_key: str
    value: str


class SetupManager:
    """Manages the conversational setup process."""
    
    def __init__(self):
        self.steps = [
            {
                "key": "openrouter_api_key",
                "question": "I need your OpenRouter API key to access language models. Please provide your OpenRouter API key:",
                "type": "password",
                "validation": "This should start with 'sk-or-' and be about 51 characters long"
            },
            {
                "key": "matrix_homeserver",
                "question": "Next, I need your Matrix homeserver URL (e.g., https://matrix.org):",
                "type": "text",
                "validation": "This should be a valid URL starting with https://"
            },
            {
                "key": "matrix_user_id",
                "question": "What is your Matrix user ID? (e.g., @username:matrix.org):",
                "type": "text",
                "validation": "This should start with @ and include your homeserver domain"
            },
            {
                "key": "matrix_password",
                "question": "Please provide your Matrix password:",
                "type": "password"
            },
            {
                "key": "matrix_room_id",
                "question": "What Matrix room should I join? Provide the room ID (e.g., !roomid:matrix.org):",
                "type": "text",
                "validation": "This should start with ! and include your homeserver domain"
            },
            {
                "key": "setup_farcaster",
                "question": "Would you like to configure Farcaster integration? (optional)",
                "type": "select",
                "options": ["yes", "no", "skip"]
            }
        ]
        self.current_step_index = 0
        self.completed_steps = {}
    
    def get_current_step(self):
        """Get the current setup step."""
        if self.current_step_index >= len(self.steps):
            return None
        return self.steps[self.current_step_index]
    
    def submit_step(self, step_key: str, value: str) -> dict:
        """Submit a step and advance to the next one."""
        current_step = self.get_current_step()
        if not current_step or current_step["key"] != step_key:
            return {"success": False, "message": "Invalid step"}
        
        # Validate the input
        validation_result = self._validate_input(current_step, value)
        if not validation_result["valid"]:
            return {"success": False, "message": validation_result["message"]}
        
        # Store the value
        self.completed_steps[step_key] = value
        
        # Handle special cases
        if step_key == "setup_farcaster" and value in ["no", "skip"]:
            # Skip farcaster steps and go to completion
            self.current_step_index = len(self.steps)
        else:
            self.current_step_index += 1
        
        # Check if setup is complete
        if self.current_step_index >= len(self.steps):
            self._save_configuration()
            return {
                "success": True,
                "message": "Perfect! All configurations are complete. Initializing systems...",
                "complete": True
            }
        
        # Return next step
        next_step = self.get_current_step()
        return {
            "success": True,
            "message": "Great! Moving to the next step...",
            "next_step": next_step,
            "complete": False
        }
    
    def _validate_input(self, step: dict, value: str) -> dict:
        """Validate user input for a step."""
        if not value.strip():
            return {"valid": False, "message": "This field cannot be empty"}
        
        step_key = step["key"]
        if step_key == "openrouter_api_key":
            if not value.startswith("sk-or-"):
                return {"valid": False, "message": "OpenRouter API keys should start with 'sk-or-'"}
            if len(value) < 40:
                return {"valid": False, "message": "This seems too short for an API key"}
        
        elif step_key == "matrix_homeserver":
            if not (value.startswith("http://") or value.startswith("https://")):
                return {"valid": False, "message": "Homeserver URL should start with http:// or https://"}
        
        elif step_key == "matrix_user_id":
            if not value.startswith("@"):
                return {"valid": False, "message": "Matrix user IDs should start with @"}
            if ":" not in value:
                return {"valid": False, "message": "Matrix user IDs should include the homeserver (e.g., @user:matrix.org)"}
        
        elif step_key == "matrix_room_id":
            if not value.startswith("!"):
                return {"valid": False, "message": "Matrix room IDs should start with !"}
        
        return {"valid": True, "message": "Valid"}
    
    def _save_configuration(self):
        """Save the configuration to a config file in the data directory."""
        # Use data directory for persistence instead of .env (which may be read-only in Docker)
        config_path = Path("data/config.json")
        config_path.parent.mkdir(exist_ok=True)
        
        # Map our step keys to environment variable names
        step_to_env = {
            "openrouter_api_key": "OPENROUTER_API_KEY",
            "matrix_homeserver": "MATRIX_HOMESERVER",
            "matrix_user_id": "MATRIX_USER_ID", 
            "matrix_password": "MATRIX_PASSWORD",
            "matrix_room_id": "MATRIX_ROOM_ID"
        }
        
        # Create config dictionary
        config = {}
        for step_key, env_key in step_to_env.items():
            if step_key in self.completed_steps:
                config[env_key] = self.completed_steps[step_key]
        
        # Add metadata
        config["_setup_completed"] = True
        config["_setup_timestamp"] = datetime.now().isoformat()
        
        # Save to JSON file
        try:
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
            logger.info(f"Configuration saved to {config_path}")
        except Exception as e:
            logger.error(f"Failed to save configuration: {e}")
            raise
    
    def is_setup_required(self) -> bool:
        """Check if setup is required by looking for essential environment variables or config file."""
        # First check if config file exists and has setup completion flag
        config_path = Path("data/config.json")
        if config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    if config.get("_setup_completed", False):
                        # Verify essential keys are present
                        required_keys = ["OPENROUTER_API_KEY", "MATRIX_USER_ID", "MATRIX_PASSWORD"]
                        if all(config.get(key) for key in required_keys):
                            return False
            except Exception as e:
                logger.warning(f"Error reading config file: {e}")
        
        # Fall back to checking environment variables
        required_vars = ["OPENROUTER_API_KEY", "MATRIX_USER_ID", "MATRIX_PASSWORD"]
        for var in required_vars:
            if not os.getenv(var):
                return True
        return False
    
    def get_setup_status(self) -> dict:
        """Get the current setup status."""
        return {
            "required": self.is_setup_required(),
            "current_step": self.get_current_step(),
            "progress": {
                "current": self.current_step_index + 1,
                "total": len(self.steps)
            },
            "completed_steps": list(self.completed_steps.keys())
        }
    
    def reset_setup(self):
        """Reset the setup process."""
        self.current_step_index = 0
        self.completed_steps = {}


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
        self._start_time = datetime.now()  # Track start time for uptime calculation
        self.app = FastAPI(
            title="Chatbot Management API",
            description="REST API for monitoring and controlling the chatbot system",
            version="1.0.0"
        )
        self.log_manager = LogWebSocketManager()
        self.setup_manager = SetupManager()
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
        
        # ===== HEALTH CHECK =====
        @self.app.get("/health")
        async def health_check():
            """Health check endpoint for container orchestration."""
            return {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "service": "chatbot_api"
            }
        
        # ===== SYSTEM STATUS & CONTROL =====
        @self.app.get("/api/status")
        async def get_system_status():
            """Get overall system status and metrics."""
            try:
                logger.info("Starting get_system_status")
                
                # Get processing hub status
                logger.info("Getting processing status")
                processing_status = self.orchestrator.processing_hub.get_processing_status()
                logger.info(f"Got processing status: {type(processing_status)}")
                
                # Get basic metrics
                logger.info("Getting world state metrics")
                world_state_metrics = {
                    "channels_count": len(self.orchestrator.world_state.state.channels),
                    "total_messages": sum(len(ch.recent_messages) for ch in self.orchestrator.world_state.state.channels.values()),
                    "action_history_count": len(self.orchestrator.world_state.state.action_history),
                    "pending_invites": len(self.orchestrator.world_state.get_pending_matrix_invites()),
                    "generated_media_count": len(self.orchestrator.world_state.state.generated_media_library),
                    "research_entries": len(self.orchestrator.world_state.state.research_database)
                }
                logger.info(f"Got world state metrics: {type(world_state_metrics)}")
                
                # Get tool stats
                logger.info("Getting tool stats")
                tool_stats = self.orchestrator.tool_registry.get_tool_stats()
                logger.info(f"Got tool stats: {type(tool_stats)}")
                
                # Rate limiter status
                logger.info("Getting rate limit status")
                rate_limit_status = self.orchestrator.rate_limiter.get_rate_limit_status(datetime.now().timestamp())
                logger.info(f"Got rate limit status: {type(rate_limit_status)}")
                
                # Setup status
                logger.info("Getting setup status")
                setup_status = self.setup_manager.get_setup_status()
                logger.info(f"Got setup status: {type(setup_status)}")
                
                # Determine system status for UI
                if setup_status.get("required", False):
                    system_status = "SETUP_REQUIRED"
                    setup_message = "Initial setup is required to configure the chatbot"
                else:
                    system_status = "OPERATIONAL"
                    setup_message = "System is ready and operational"
                
                return {
                    "status": system_status,  # Primary status for UI logic
                    "setup_status": setup_message,
                    "version": "1.0.0",  # TODO: Get from package/version file
                    "uptime": (datetime.now() - self._start_time).total_seconds(),
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
                    "setup": setup_status,
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
            # List of required settings that should not be None or empty
            required_settings = [
                "OPENROUTER_API_KEY", "MATRIX_HOMESERVER", "MATRIX_USER_ID",
                "MATRIX_PASSWORD", "NEYNAR_API_KEY", "FARCASTER_BOT_SIGNER_UUID",
                "GOOGLE_API_KEY", "ARWEAVE_WALLET_PATH", "ARWEAVE_GATEWAY_URL", "GITHUB_TOKEN"
            ]
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
                    
                    # Node-based processing settings
                    "MAX_EXPANDED_NODES": settings.MAX_EXPANDED_NODES,
                    "ENABLE_TWO_PHASE_AI_PROCESS": settings.ENABLE_TWO_PHASE_AI_PROCESS,
                    "MAX_EXPLORATION_ROUNDS": settings.MAX_EXPLORATION_ROUNDS,
                    
                    # Tool cooldowns
                    "IMAGE_GENERATION_COOLDOWN_SECONDS": settings.IMAGE_GENERATION_COOLDOWN_SECONDS,
                    "VIDEO_GENERATION_COOLDOWN_SECONDS": settings.VIDEO_GENERATION_COOLDOWN_SECONDS,
                    "STORE_MEMORY_COOLDOWN_SECONDS": settings.STORE_MEMORY_COOLDOWN_SECONDS,
                    
                    # Integration settings
                    "MATRIX_HOMESERVER": settings.MATRIX_HOMESERVER, # Sensitive, but useful for display
                    "FARCASTER_BOT_FID": settings.FARCASTER_BOT_FID,
                    "ECOSYSTEM_TOKEN_CONTRACT_ADDRESS": settings.ECOSYSTEM_TOKEN_CONTRACT_ADDRESS,
                    "ECOSYSTEM_TOKEN_NETWORK": settings.ECOSYSTEM_TOKEN_NETWORK,
                    "NUM_TOP_HOLDERS_TO_TRACK": settings.NUM_TOP_HOLDERS_TO_TRACK,
                    
                    # File paths
                    "CHATBOT_DB_PATH": settings.CHATBOT_DB_PATH,

                    # GitHub ACE Integration
                    "GITHUB_USERNAME": settings.GITHUB_USERNAME,
                    
                    # Processing config from orchestrator
                    "enable_node_based_processing": self.orchestrator.config.processing_config.enable_node_based_processing,
                }

                # Identify missing required settings
                missing_settings = [
                    key for key in required_settings
                    if not getattr(settings, key, None)
                ]
                
                return {
                    "config": config_dict,
                    "mutable_keys": [
                        "LOG_LEVEL", "OBSERVATION_INTERVAL", "MAX_CYCLES_PER_HOUR",
                        "AI_MODEL", "WEB_SEARCH_MODEL", "AI_SUMMARY_MODEL", "OPENROUTER_MULTIMODAL_MODEL",
                        "IMAGE_GENERATION_COOLDOWN_SECONDS", "VIDEO_GENERATION_COOLDOWN_SECONDS", "STORE_MEMORY_COOLDOWN_SECONDS",
                        "ECOSYSTEM_TOKEN_CONTRACT_ADDRESS", "ECOSYSTEM_TOKEN_NETWORK", "NUM_TOP_HOLDERS_TO_TRACK",
                        "MAX_EXPANDED_NODES", "ENABLE_TWO_PHASE_AI_PROCESS", "MAX_EXPLORATION_ROUNDS"
                    ],
                    "missing_required_settings": missing_settings,
                    "timestamp": datetime.now().isoformat()
                }
            except Exception as e:
                logger.error(f"Error getting configuration: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.put("/api/config")
        async def update_configuration(update: ConfigUpdate):
            """Update a configuration value."""
            # Note: This updates the live configuration. For persistence across restarts,
            # the .env file or a config database would need to be updated, which is
            # beyond the scope of this implementation for safety reasons.
            try:
                if not hasattr(settings, update.key):
                    raise HTTPException(status_code=400, detail=f"Unknown config key: {update.key}")
                
                # Update the global settings object
                setattr(settings, update.key, update.value)
                
                # Propagate the change to the relevant live component
                if update.key == "AI_MODEL":
                    self.orchestrator.ai_engine.model = update.value
                    self.orchestrator.config.ai_model = update.value
                    self.orchestrator.ai_engine.update_system_prompt_with_tools(self.orchestrator.tool_registry)
                elif update.key == "OBSERVATION_INTERVAL":
                    self.orchestrator.processing_hub.config.observation_interval = float(update.value)
                elif update.key == "MAX_CYCLES_PER_HOUR":
                    self.orchestrator.rate_limiter.config.max_cycles_per_hour = int(update.value)
                    self.orchestrator.rate_limiter.config.min_cycle_interval = 3600 / int(update.value)
                elif update.key == "LOG_LEVEL":
                    logging.getLogger().setLevel(getattr(logging, str(update.value).upper(), "INFO"))
                elif update.key == "MAX_EXPANDED_NODES":
                    if hasattr(self.orchestrator.processing_hub, 'node_manager'):
                        self.orchestrator.processing_hub.node_manager.max_expanded_nodes = int(update.value)
                
                # For other mutable keys, they are read directly from `settings` by their respective components,
                # so just updating the `settings` object is sufficient.
                
                return {
                    "success": True,
                    "message": f"Configuration {update.key} updated to {update.value}",
                    "restart_required": update.key in [
                         "MATRIX_HOMESERVER", "FARCASTER_BOT_FID", "CHATBOT_DB_PATH",
                         "GITHUB_USERNAME"
                    ]
                }
            except Exception as e:
                logger.error(f"Error updating configuration: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        # ===== INTEGRATION MANAGEMENT =====
        @self.app.get("/api/integrations")
        async def list_integrations():
            """List all configured integrations with their status."""
            try:
                integrations = await self.orchestrator.integration_manager.list_integrations()
                return integrations
            except Exception as e:
                logger.error(f"Error listing integrations: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/api/integrations")
        async def add_integration(config: IntegrationConfig):
            """Add a new integration configuration."""
            try:
                integration_id = await self.orchestrator.integration_manager.add_integration(
                    integration_type=config.integration_type,
                    display_name=config.display_name,
                    config=config.config,
                    credentials=config.credentials
                )
                return {"integration_id": integration_id, "message": "Integration added successfully"}
            except Exception as e:
                logger.error(f"Error adding integration: {e}")
                raise HTTPException(status_code=400, detail=str(e))
        
        @self.app.get("/api/integrations/{integration_id}")
        async def get_integration_status(integration_id: str):
            """Get detailed status of a specific integration."""
            try:
                status = await self.orchestrator.integration_manager.get_integration_status(integration_id)
                if status is None:
                    raise HTTPException(status_code=404, detail="Integration not found")
                return status
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error getting integration status: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/api/integrations/{integration_id}/connect")
        async def connect_integration(integration_id: str):
            """Manually trigger connection attempt for an integration."""
            try:
                success = await self.orchestrator.integration_manager.connect_integration(
                    integration_id, self.orchestrator.world_state
                )
                return {"success": success, "message": "Connection attempt completed"}
            except Exception as e:
                logger.error(f"Error connecting integration: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/api/integrations/{integration_id}/disconnect")
        async def disconnect_integration(integration_id: str):
            """Disconnect a specific integration."""
            try:
                await self.orchestrator.integration_manager.disconnect_integration(integration_id)
                return {"message": "Integration disconnected successfully"}
            except Exception as e:
                logger.error(f"Error disconnecting integration: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.delete("/api/integrations/{integration_id}")
        async def remove_integration(integration_id: str):
            """Remove an integration configuration."""
            try:
                # First disconnect if connected
                await self.orchestrator.integration_manager.disconnect_integration(integration_id)
                
                # TODO: Add remove_integration method to IntegrationManager
                return {"message": "Integration removed successfully"}
            except Exception as e:
                logger.error(f"Error removing integration: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/api/integrations/test")
        async def test_integration_config(test_request: IntegrationTestRequest):
            """Test an integration configuration without saving it."""
            try:
                result = await self.orchestrator.integration_manager.test_integration_config(
                    integration_type=test_request.integration_type,
                    config=test_request.config,
                    credentials=test_request.credentials
                )
                return result
            except Exception as e:
                logger.error(f"Error testing integration config: {e}")
                raise HTTPException(status_code=400, detail=str(e))
        
        @self.app.get("/api/integrations/types")
        async def get_available_integration_types():
            """Get list of available integration types."""
            try:
                types = self.orchestrator.integration_manager.get_available_integration_types()
                return {"integration_types": types}
            except Exception as e:
                logger.error(f"Error getting integration types: {e}")
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
                        "platform": channel.type,
                        "message_count": len(channel.recent_messages),
                        "recent_messages": [
                            {
                                "id": msg.id,
                                "content": msg.content[:100] + "..." if len(msg.content) > 100 else msg.content,
                                "author": msg.sender,
                                "timestamp": msg.timestamp,
                                "platform": msg.channel_type
                            }
                            for msg in channel.recent_messages[-5:]  # Last 5 messages
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
        
        @self.app.get("/api/worldstate/ai-payload")
        async def get_ai_world_state_payload():
            """Get the actual world state payload as used by the AI system."""
            try:
                # Get the payload builder from the orchestrator
                payload_builder = self.orchestrator.payload_builder
                world_state_data = self.orchestrator.world_state.state
                
                # Get the current primary channel (if any)
                primary_channel_id = getattr(self.orchestrator, 'current_primary_channel_id', None)
                
                # Build the actual AI payload
                ai_payload = payload_builder.build_full_payload(
                    world_state_data=world_state_data,
                    primary_channel_id=primary_channel_id,
                    config={
                        "optimize_for_size": False,  # Get full detail for API
                        "include_detailed_user_info": True,
                        "max_messages_per_channel": 10,
                        "max_action_history": 10,
                        "max_thread_messages": 10,
                        "max_other_channels": 10
                    }
                )
                
                return {
                    "ai_world_state": ai_payload,
                    "metadata": {
                        "primary_channel_id": primary_channel_id,
                        "payload_type": "full",
                        "optimization_enabled": False,
                        "timestamp": datetime.now().isoformat()
                    }
                }
            except Exception as e:
                logger.error(f"Error getting AI world state payload: {e}")
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
                    "last_sync_time": None,
                    "monitored_rooms": [],
                    "pending_invites": 0
                }
                if hasattr(self.orchestrator, 'matrix_observer') and self.orchestrator.matrix_observer:
                    client = self.orchestrator.matrix_observer.client
                    matrix_status["connected"] = client is not None and getattr(client, 'logged_in', False)
                    matrix_status["monitored_rooms"] = self.orchestrator.matrix_observer.channels_to_monitor
                    matrix_status["pending_invites"] = len(self.orchestrator.world_state.get_pending_matrix_invites())
                    if client:
                        matrix_status["last_sync_time"] = getattr(client, "last_sync", None)
                
                integrations["matrix"] = matrix_status
                
                # Farcaster integration
                farcaster_status = {
                    "connected": False,
                    "bot_fid": settings.FARCASTER_BOT_FID,
                    "rate_limit_remaining": None,
                    "rate_limit_resets": None,
                    "post_queue_size": 0,
                    "reply_queue_size": 0
                }
                if hasattr(self.orchestrator, 'farcaster_observer') and self.orchestrator.farcaster_observer:
                    fc_observer = self.orchestrator.farcaster_observer
                    farcaster_status["connected"] = fc_observer.api_client is not None
                    if fc_observer.scheduler:
                        scheduler = fc_observer.scheduler
                        farcaster_status["post_queue_size"] = getattr(scheduler.post_queue, 'qsize', lambda: 0)()
                        farcaster_status["reply_queue_size"] = getattr(scheduler.reply_queue, 'qsize', lambda: 0)()
                    if fc_observer.api_client and fc_observer.api_client.rate_limit_info:
                        rate_info = fc_observer.api_client.rate_limit_info
                        farcaster_status["rate_limit_remaining"] = rate_info.get("remaining")
                        if rate_info.get("reset"):
                            farcaster_status["rate_limit_resets"] = datetime.fromtimestamp(rate_info.get("reset")).isoformat()
                
                integrations["farcaster"] = farcaster_status
                
                # Ecosystem Token Service
                token_status = {
                    "active": False,
                    "monitored_holders": 0,
                    "last_holder_update": None,
                    "contract_address": None
                }
                if hasattr(self.orchestrator.farcaster_observer, 'ecosystem_token_service'):
                    token_service = self.orchestrator.farcaster_observer.ecosystem_token_service
                    if token_service and token_service._running:
                        token_status["active"] = True
                        token_status["monitored_holders"] = len(self.orchestrator.world_state.state.monitored_token_holders)
                        token_status["contract_address"] = token_service.token_contract
                        if token_service.last_metadata_update > 0:
                            token_status["last_holder_update"] = datetime.fromtimestamp(token_service.last_metadata_update).isoformat()
                
                integrations["ecosystem_token"] = token_status
                
                # Eligibility Service
                eligibility_status = {
                    "active": False,
                    "eligible_users_checked": 0,
                }
                if hasattr(self.orchestrator, 'eligibility_service') and self.orchestrator.eligibility_service:
                    eligibility_service = self.orchestrator.eligibility_service
                    if eligibility_service._running:
                        eligibility_status["active"] = True
                        summary = eligibility_service.get_eligibility_summary()
                        eligibility_status["eligible_users_checked"] = summary.get("eligible_users", 0)
                
                integrations["eligibility_service"] = eligibility_status
                
                return {
                    "integrations": integrations,
                    "timestamp": datetime.now().isoformat()
                }
            except Exception as e:
                logger.error(f"Error getting integrations status: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        # ===== SETUP ENDPOINTS =====
        @self.app.get("/api/setup/start")
        async def start_setup():
            """Start or get the current setup step."""
            try:
                if not self.setup_manager.is_setup_required():
                    return {
                        "message": "Setup is already complete!",
                        "complete": True,
                        "step": None
                    }
                
                current_step = self.setup_manager.get_current_step()
                if current_step:
                    return {
                        "message": f"Welcome! Let me help you configure your chatbot. {current_step['question']}",
                        "complete": False,
                        "step": current_step
                    }
                else:
                    return {
                        "message": "Setup is complete!",
                        "complete": True,
                        "step": None
                    }
            except Exception as e:
                logger.error(f"Error starting setup: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/api/setup/submit")
        async def submit_setup_step(submission: SetupSubmission):
            """Submit a step in the setup process."""
            try:
                result = self.setup_manager.submit_step(submission.step_key, submission.value)
                return result
            except Exception as e:
                logger.error(f"Error submitting setup step: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/api/setup/reset")
        async def reset_setup():
            """Reset the setup process."""
            try:
                self.setup_manager.reset_setup()
                return {"success": True, "message": "Setup process has been reset"}
            except Exception as e:
                logger.error(f"Error resetting setup: {e}")
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
        
        # NFT Frame Server Endpoints (v0.0.4)
        
        @self.app.get("/frames/mint/{frame_id}")
        async def serve_mint_frame(frame_id: str, claim_type: str = "public", max_mints: int = 1):
            """
            Serve the HTML for an NFT minting Farcaster Frame.
            
            Args:
                frame_id: Unique identifier for the frame
                claim_type: 'public' or 'gated' minting
                max_mints: Maximum number of mints allowed
                
            Returns:
                HTML response with Farcaster Frame meta tags
            """
            try:
                # Get frame metadata from world state
                world_state = self.orchestrator.world_state_manager.get_state()
                frame_metadata = getattr(world_state, 'nft_frames', {}).get(frame_id)
                
                if not frame_metadata:
                    raise HTTPException(status_code=404, detail="Frame not found")
                
                # Build frame HTML with meta tags
                title = frame_metadata.get('title', 'AI Art NFT')
                description = frame_metadata.get('description', 'Mint this AI-generated artwork as an NFT')
                image_url = frame_metadata.get('image_url', '')
                button_text = "Check Eligibility" if claim_type == "gated" else "Mint NFT"
                
                # Construct action URL
                action_url = f"{settings.FRAMES_BASE_URL or 'https://yourbot.com'}/frames/action/mint/{frame_id}"
                
                html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{title}</title>
    
    <!-- Farcaster Frame Meta Tags -->
    <meta property="fc:frame" content="vNext" />
    <meta property="fc:frame:image" content="{image_url}" />
    <meta property="fc:frame:image:aspect_ratio" content="1:1" />
    <meta property="fc:frame:button:1" content="{button_text}" />
    <meta property="fc:frame:post_url" content="{action_url}" />
    
    <!-- Open Graph for social sharing -->
    <meta property="og:title" content="{title}" />
    <meta property="og:description" content="{description}" />
    <meta property="og:image" content="{image_url}" />
    
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            min-height: 100vh;
        }}
        .frame-container {{
            background: rgba(255,255,255,0.1);
            border-radius: 20px;
            padding: 30px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.2);
        }}
        .artwork {{
            width: 100%;
            max-width: 400px;
            border-radius: 15px;
            margin: 20px 0;
        }}
        .mint-info {{
            background: rgba(0,0,0,0.3);
            padding: 20px;
            border-radius: 10px;
            margin: 20px 0;
        }}
        .status-badge {{
            display: inline-block;
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 0.9em;
            font-weight: bold;
            margin: 10px 0;
        }}
        .gated {{ background: #ff6b6b; }}
        .public {{ background: #51cf66; }}
    </style>
</head>
<body>
    <div class="frame-container">
        <h1>🎨 {title}</h1>
        <img src="{image_url}" alt="{title}" class="artwork">
        
        <div class="mint-info">
            <p>{description}</p>
            <div class="status-badge {'gated' if claim_type == 'gated' else 'public'}">
                {'🔒 Token Holders Only' if claim_type == 'gated' else '🎉 Open Mint'}
            </div>
            <p><strong>Max Mints:</strong> {max_mints}</p>
            <p><strong>Minted:</strong> {frame_metadata.get('mints_count', 0)} / {max_mints}</p>
        </div>
        
        <p>To mint this NFT, use the Farcaster app (Warpcast) and interact with the frame!</p>
    </div>
</body>
</html>"""
                
                from fastapi.responses import HTMLResponse
                return HTMLResponse(content=html_content, status_code=200)
                
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error serving mint frame {frame_id}: {e}")
                raise HTTPException(status_code=500, detail="Internal server error")
        
        @self.app.post("/frames/action/mint/{frame_id}")
        async def handle_mint_action(frame_id: str, request: dict):
            """
            Handle NFT minting action from Farcaster Frame interaction.
            
            Args:
                frame_id: Unique identifier for the frame
                request: Farcaster frame action request data
                
            Returns:
                Frame response with transaction or result
            """
            try:
                # Get frame metadata
                world_state = self.orchestrator.world_state_manager.get_state()
                frame_metadata = getattr(world_state, 'nft_frames', {}).get(frame_id)
                
                if not frame_metadata:
                    return {"error": "Frame not found"}
                
                # Extract user FID from Farcaster request
                # Note: In a real implementation, you'd validate the signature here
                user_fid = request.get('untrustedData', {}).get('fid')
                if not user_fid:
                    return {"error": "User FID not found"}
                
                user_fid = str(user_fid)
                claim_type = frame_metadata.get('claim_type', 'public')
                
                # Check eligibility if gated
                if claim_type == "gated":
                    eligibility_service = getattr(self.orchestrator, 'eligibility_service', None)
                    if eligibility_service:
                        is_eligible = await eligibility_service.check_user_eligibility_now(user_fid)
                        if not is_eligible:
                            # Return frame showing ineligibility
                            return {
                                "type": "frame",
                                "frameData": {
                                    "image": frame_metadata.get('image_url'),
                                    "button": {
                                        "title": "Not Eligible 😔",
                                        "action": "post",
                                        "target": f"{settings.FRAMES_BASE_URL}/frames/ineligible"
                                    },
                                    "post_url": f"{settings.FRAMES_BASE_URL}/frames/action/mint/{frame_id}"
                                }
                            }
                
                # Check mint limits
                max_mints = frame_metadata.get('max_mints', 1)
                current_mints = frame_metadata.get('mints_count', 0)
                
                if current_mints >= max_mints:
                    return {
                        "type": "frame", 
                        "frameData": {
                            "image": frame_metadata.get('image_url'),
                            "button": {
                                "title": "Sold Out! 🚫",
                                "action": "link",
                                "target": settings.FRAMES_BASE_URL or "https://yourbot.com"
                            }
                        }
                    }
                
                # Get user's verified addresses for minting
                user_details = world_state.farcaster_users.get(user_fid)
                if not user_details or not user_details.verified_addresses.get('evm'):
                    return {"error": "No verified EVM address found for user"}
                
                recipient_address = user_details.verified_addresses['evm'][0]
                metadata_uri = frame_metadata.get('metadata_uri')
                
                # Prepare minting transaction
                base_nft_service = getattr(self.orchestrator, 'base_nft_service', None)
                if not base_nft_service:
                    return {"error": "NFT service not available"}
                
                # For Frame transactions, we return transaction data for user to sign
                # In a full implementation, you'd build the transaction calldata here
                return {
                    "type": "frame",
                    "frameData": {
                        "chainId": "eip155:8453",  # Base mainnet
                        "method": "eth_sendTransaction",
                        "params": {
                            "abi": [],  # Your contract ABI
                            "to": settings.NFT_COLLECTION_ADDRESS_BASE,
                            "data": "0x...",  # Encoded mint function call
                            "value": "0"
                        }
                    }
                }
                
            except Exception as e:
                logger.error(f"Error handling mint action for frame {frame_id}: {e}")
                return {"error": "Internal server error"}
        
        @self.app.get("/frames/ineligible")
        async def serve_ineligible_frame():
            """Serve frame for users who are not eligible for gated drops."""
            html_content = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta property="fc:frame" content="vNext" />
    <meta property="fc:frame:image" content="https://via.placeholder.com/400x400/ff6b6b/white?text=Not+Eligible" />
    <meta property="fc:frame:button:1" content="Learn More" />
    <meta property="fc:frame:button:1:action" content="link" />
    <meta property="fc:frame:button:1:target" content="https://yourbot.com/eligibility" />
    <title>Not Eligible</title>
</head>
<body>
    <h1>🔒 Not Eligible</h1>
    <p>You need to hold ecosystem tokens or NFTs to claim this exclusive drop.</p>
</body>
</html>"""
            from fastapi.responses import HTMLResponse
            return HTMLResponse(content=html_content, status_code=200)


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
