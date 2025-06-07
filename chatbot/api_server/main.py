"""
Main FastAPI server with modular router architecture.

This is the refactored version of the original api_server.py, broken down into
organized routers for better maintainability and separation of concerns.
"""

import logging
from datetime import datetime
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from chatbot.core.orchestration import MainOrchestrator
from .services import SetupManager, LogWebSocketManager
from .routers import system, tools, config, integrations, ai, worldstate, setup, logs, ui_frames
from .schemas import StatusResponse

logger = logging.getLogger(__name__)


class ChatbotAPIServer:
    """Main API server for chatbot management UI with modular router architecture."""
    
    def __init__(self, orchestrator: MainOrchestrator):
        self.orchestrator = orchestrator
        self._start_time = datetime.now()
        
        self.app = FastAPI(
            title="Chatbot Management API",
            description="REST API for monitoring and controlling the chatbot system",
            version="1.0.0"
        )
        
        self.log_manager = LogWebSocketManager()
        self.setup_manager = SetupManager()
        
        self._setup_middleware()
        self._setup_dependency_overrides()
        self._setup_routers()
        self._setup_websocket_routes()
        self._setup_static_files()
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
    
    def _setup_dependency_overrides(self):
        """Set up dependency injection overrides for routers."""
        def get_orchestrator():
            return self.orchestrator
        
        def get_setup_manager():
            return self.setup_manager
        
        # Override the get_orchestrator dependency in all routers
        self.app.dependency_overrides[system.get_orchestrator] = get_orchestrator
        self.app.dependency_overrides[tools.get_orchestrator] = get_orchestrator
        self.app.dependency_overrides[config.get_orchestrator] = get_orchestrator
        self.app.dependency_overrides[integrations.get_orchestrator] = get_orchestrator
        self.app.dependency_overrides[ai.get_orchestrator] = get_orchestrator
        self.app.dependency_overrides[worldstate.get_orchestrator] = get_orchestrator
        self.app.dependency_overrides[setup.get_orchestrator] = get_orchestrator
        self.app.dependency_overrides[setup.get_setup_manager] = get_setup_manager
        self.app.dependency_overrides[logs.get_orchestrator] = get_orchestrator
        self.app.dependency_overrides[ui_frames.get_orchestrator] = get_orchestrator
        
    def _setup_routers(self):
        """Include all modular routers."""
        self.app.include_router(system.router)
        self.app.include_router(tools.router)
        self.app.include_router(config.router)
        self.app.include_router(integrations.router, prefix="/api")
        self.app.include_router(ai.router, prefix="/api")
        self.app.include_router(worldstate.router, prefix="/api")
        self.app.include_router(setup.router, prefix="/api")
        self.app.include_router(logs.router)  # already has /api prefix
        
        # UI and frames routers (no prefix)
        self.app.include_router(ui_frames.ui_router)
        self.app.include_router(ui_frames.frames_router)
        
    def _setup_websocket_routes(self):
        """Set up WebSocket routes for real-time features."""
        @self.app.websocket("/ws/logs")
        async def websocket_logs(websocket: WebSocket):
            """WebSocket endpoint for real-time log streaming."""
            await self.log_manager.connect(websocket)
            try:
                while True:
                    # Keep connection alive and handle client messages if needed
                    await websocket.receive_text()
            except WebSocketDisconnect:
                self.log_manager.disconnect(websocket)
                
    def _setup_static_files(self):
        """Set up static file serving for the UI."""
        # Check if UI directory exists
        import os
        ui_path = "ui"
        ui_nextjs_path = "ui-nextjs/dist"
        
        if os.path.exists(ui_nextjs_path):
            # Serve Next.js built assets if available
            self.app.mount("/", StaticFiles(directory=ui_nextjs_path, html=True), name="ui")
            logger.info(f"Serving UI from {ui_nextjs_path}")
        elif os.path.exists(ui_path):
            # Fallback to basic UI
            self.app.mount("/", StaticFiles(directory=ui_path, html=True), name="ui")
            logger.info(f"Serving UI from {ui_path}")
        else:
            logger.warning("No UI directory found - UI will not be available")
        
    def _setup_log_handler(self):
        """Set up log handler to stream logs to WebSocket clients."""
        websocket_handler = self.log_manager.create_log_handler()
        websocket_handler.setLevel(logging.INFO)
        logging.getLogger().addHandler(websocket_handler)


def create_api_server(orchestrator: MainOrchestrator) -> FastAPI:
    """Factory function to create the API server."""
    server = ChatbotAPIServer(orchestrator)
    return server.app
