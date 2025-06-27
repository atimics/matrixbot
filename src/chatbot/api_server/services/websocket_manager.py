"""
WebSocket Log Manager service for real-time log streaming.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List

from fastapi import WebSocket


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

    def create_log_handler(self):
        """Create a logging handler that streams to WebSocket clients."""
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
        
        return WebSocketLogHandler(self)
