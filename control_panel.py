#!/usr/bin/env python3
"""
Context Management Control Panel

A web-based control panel for managing the context-aware orchestrator system.
Allows viewing state changes, managing contexts, exporting training data, and controlling the system.
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# Import our context management components
# Note: HistoryRecorder was consolidated into ContextManager for cleaner architecture
from chatbot.core.orchestration import MainOrchestrator
from chatbot.core.world_state import WorldStateManager

logger = logging.getLogger(__name__)

# Pydantic models for API
class StateChangeResponse(BaseModel):
    timestamp: float
    change_type: str
    source: str
    channel_id: Optional[str]
    observations: Optional[str]
    reasoning: Optional[str]
    formatted_time: str

class ContextSummaryResponse(BaseModel):
    channel_id: str
    user_message_count: int
    assistant_message_count: int
    last_update: float
    world_state_keys: List[str]
    formatted_last_update: str

class SystemStatusResponse(BaseModel):
    running: bool
    cycle_count: int
    active_channels: List[str]
    total_state_changes: int
    uptime_seconds: float

class MessageRequest(BaseModel):
    channel_id: str
    content: str
    sender: str = "@user:control-panel"

# Global orchestrator instance
orchestrator: Optional[MainOrchestrator] = None
start_time = time.time()

app = FastAPI(title="Context Management Control Panel", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    """Initialize the orchestrator"""
    global orchestrator
    from chatbot.core.orchestration import OrchestratorConfig, ProcessingConfig
    config = OrchestratorConfig(
        db_path="control_panel.db",
        processing_config=ProcessingConfig(enable_node_based_processing=False)
    )
    orchestrator = MainOrchestrator(config)
    logger.info("Control panel started")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    global orchestrator
    if orchestrator and orchestrator.running:
        await orchestrator.stop()

# API Routes

@app.get("/", response_class=HTMLResponse)
async def get_control_panel():
    """Serve the control panel HTML"""
    return HTMLResponse(content=get_control_panel_html())

@app.get("/api/status")
async def get_system_status() -> SystemStatusResponse:
    """Get current system status"""
    if not orchestrator:
        raise HTTPException(status_code=500, detail="Orchestrator not initialized")
    
    active_channels = []
    if orchestrator.world_state:
        world_state = orchestrator.world_state.to_dict()
        active_channels = list(world_state.get('channels', {}).keys())
    
    total_state_changes = len(orchestrator.context_manager.state_changes)
    
    return SystemStatusResponse(
        running=orchestrator.running,
        cycle_count=orchestrator.cycle_count,
        active_channels=active_channels,
        total_state_changes=total_state_changes,
        uptime_seconds=time.time() - start_time
    )

@app.get("/api/state-changes")
async def get_state_changes(
    channel_id: Optional[str] = None,
    change_type: Optional[str] = None,
    limit: int = 50
) -> List[StateChangeResponse]:
    """Get recent state changes with optional filtering"""
    if not orchestrator:
        raise HTTPException(status_code=500, detail="Orchestrator not initialized")
    
    state_changes = await orchestrator.context_manager.get_state_changes(
        channel_id=channel_id,
        change_type=change_type,
        limit=limit
    )
    
    return [
        StateChangeResponse(
            timestamp=change.timestamp,
            change_type=change.change_type,
            source=change.source,
            channel_id=change.channel_id,
            observations=change.observations,
            reasoning=change.reasoning,
            formatted_time=datetime.fromtimestamp(change.timestamp).strftime("%Y-%m-%d %H:%M:%S")
        )
        for change in state_changes
    ]

@app.get("/api/contexts")
async def get_all_contexts() -> List[ContextSummaryResponse]:
    """Get summaries of all conversation contexts"""
    if not orchestrator:
        raise HTTPException(status_code=500, detail="Orchestrator not initialized")
    
    contexts = []
    for channel_id in orchestrator.context_manager.contexts.keys():
        summary = await orchestrator.get_context_summary(channel_id)
        contexts.append(
            ContextSummaryResponse(
                channel_id=channel_id,
                user_message_count=summary.get("user_message_count", 0),
                assistant_message_count=summary.get("assistant_message_count", 0),
                last_update=summary.get("last_update", 0),
                world_state_keys=summary.get("world_state_keys", []),
                formatted_last_update=datetime.fromtimestamp(
                    summary.get("last_update", 0)
                ).strftime("%Y-%m-%d %H:%M:%S")
            )
        )
    
    return contexts

@app.get("/api/context/{channel_id}")
async def get_context_details(channel_id: str):
    """Get detailed context information for a specific channel"""
    if not orchestrator:
        raise HTTPException(status_code=500, detail="Orchestrator not initialized")
    
    try:
        summary = await orchestrator.get_context_summary(channel_id)
        messages = await orchestrator.context_manager.get_conversation_messages(channel_id, include_system=False)
        
        return {
            "summary": summary,
            "messages": messages[-20:],  # Last 20 messages
            "system_prompt_preview": summary.get("system_prompt", "")[:500] + "..." if len(summary.get("system_prompt", "")) > 500 else summary.get("system_prompt", "")
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Context not found: {str(e)}")

@app.post("/api/message")
async def send_message(message: MessageRequest):
    """Send a message to a channel (simulating user input)"""
    if not orchestrator:
        raise HTTPException(status_code=500, detail="Orchestrator not initialized")
    
    user_message = {
        "content": message.content,
        "sender": message.sender,
        "event_id": f"$control_panel_{int(time.time())}",
        "timestamp": time.time(),
        "room_id": message.channel_id
    }
    
    await orchestrator.context_manager.add_user_message(message.channel_id, user_message)
    
    return {"status": "success", "message": "Message added to context"}

@app.post("/api/start")
async def start_orchestrator(background_tasks: BackgroundTasks):
    """Start the orchestrator in the background"""
    if not orchestrator:
        raise HTTPException(status_code=500, detail="Orchestrator not initialized")
    
    if orchestrator.running:
        raise HTTPException(status_code=400, detail="Orchestrator already running")
    
    # Start in background
    background_tasks.add_task(orchestrator.start)
    
    return {"status": "success", "message": "Orchestrator started"}

@app.post("/api/stop")
async def stop_orchestrator():
    """Stop the orchestrator"""
    if not orchestrator:
        raise HTTPException(status_code=500, detail="Orchestrator not initialized")
    
    if not orchestrator.running:
        raise HTTPException(status_code=400, detail="Orchestrator not running")
    
    await orchestrator.stop()
    
    return {"status": "success", "message": "Orchestrator stopped"}

@app.post("/api/export")
async def export_training_data():
    """Export state changes for training"""
    if not orchestrator:
        raise HTTPException(status_code=500, detail="Orchestrator not initialized")
    
    timestamp = int(time.time())
    output_path = f"training_data_{timestamp}.jsonl"
    
    exported_file = await orchestrator.export_training_data(output_path)
    
    return {"status": "success", "file": exported_file}

@app.delete("/api/context/{channel_id}")
async def clear_context(channel_id: str):
    """Clear context for a specific channel"""
    if not orchestrator:
        raise HTTPException(status_code=500, detail="Orchestrator not initialized")
    
    await orchestrator.clear_context(channel_id)
    
    return {"status": "success", "message": f"Context cleared for {channel_id}"}

def get_control_panel_html() -> str:
    """Generate the HTML for the control panel"""
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Context Management Control Panel</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0d1117;
            color: #e6edf3;
            line-height: 1.6;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }
        
        .header {
            background: #161b22;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            border: 1px solid #30363d;
        }
        
        .header h1 {
            color: #58a6ff;
            margin-bottom: 10px;
        }
        
        .status-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }
        
        .status-card {
            background: #161b22;
            padding: 20px;
            border-radius: 8px;
            border: 1px solid #30363d;
            text-align: center;
        }
        
        .status-card h3 {
            color: #58a6ff;
            margin-bottom: 10px;
            font-size: 14px;
            text-transform: uppercase;
        }
        
        .status-value {
            font-size: 24px;
            font-weight: bold;
            color: #e6edf3;
        }
        
        .controls {
            background: #161b22;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            border: 1px solid #30363d;
        }
        
        .controls h2 {
            color: #58a6ff;
            margin-bottom: 15px;
        }
        
        .control-buttons {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }
        
        .btn {
            padding: 10px 20px;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-weight: 500;
            transition: all 0.2s;
        }
        
        .btn-primary {
            background: #238636;
            color: white;
        }
        
        .btn-primary:hover {
            background: #2ea043;
        }
        
        .btn-danger {
            background: #da3633;
            color: white;
        }
        
        .btn-danger:hover {
            background: #f85149;
        }
        
        .btn-secondary {
            background: #373e47;
            color: #e6edf3;
            border: 1px solid #30363d;
        }
        
        .btn-secondary:hover {
            background: #444c56;
        }
        
        .section {
            background: #161b22;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            border: 1px solid #30363d;
        }
        
        .section h2 {
            color: #58a6ff;
            margin-bottom: 15px;
        }
        
        .state-change {
            background: #0d1117;
            padding: 15px;
            border-radius: 6px;
            margin-bottom: 10px;
            border-left: 3px solid #58a6ff;
        }
        
        .state-change-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }
        
        .state-change-type {
            background: #58a6ff;
            color: #0d1117;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: bold;
        }
        
        .state-change-time {
            color: #7d8590;
            font-size: 12px;
        }
        
        .message-form {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
        }
        
        .form-group {
            flex: 1;
        }
        
        .form-group label {
            display: block;
            margin-bottom: 5px;
            color: #e6edf3;
            font-weight: 500;
        }
        
        .form-control {
            width: 100%;
            padding: 10px;
            background: #0d1117;
            border: 1px solid #30363d;
            border-radius: 6px;
            color: #e6edf3;
        }
        
        .form-control:focus {
            outline: none;
            border-color: #58a6ff;
        }
        
        .context-card {
            background: #0d1117;
            padding: 15px;
            border-radius: 6px;
            margin-bottom: 10px;
            border: 1px solid #30363d;
        }
        
        .context-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }
        
        .context-id {
            font-weight: bold;
            color: #58a6ff;
        }
        
        .context-stats {
            display: flex;
            gap: 15px;
            color: #7d8590;
            font-size: 14px;
        }
        
        .loading {
            text-align: center;
            color: #7d8590;
            padding: 40px;
        }
        
        .error {
            background: #da3633;
            color: white;
            padding: 10px;
            border-radius: 6px;
            margin-bottom: 20px;
        }
        
        .success {
            background: #238636;
            color: white;
            padding: 10px;
            border-radius: 6px;
            margin-bottom: 20px;
        }
        
        .refresh-btn {
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: #58a6ff;
            color: #0d1117;
            border: none;
            border-radius: 50%;
            width: 60px;
            height: 60px;
            cursor: pointer;
            font-size: 18px;
            box-shadow: 0 4px 12px rgba(88, 166, 255, 0.3);
        }
        
        .refresh-btn:hover {
            background: #79c0ff;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🤖 Context Management Control Panel</h1>
            <p>Monitor and control the context-aware AI orchestrator system</p>
        </div>
        
        <div id="status-section">
            <div class="status-grid">
                <div class="status-card">
                    <h3>System Status</h3>
                    <div class="status-value" id="system-status">Loading...</div>
                </div>
                <div class="status-card">
                    <h3>Cycle Count</h3>
                    <div class="status-value" id="cycle-count">-</div>
                </div>
                <div class="status-card">
                    <h3>Active Channels</h3>
                    <div class="status-value" id="active-channels">-</div>
                </div>
                <div class="status-card">
                    <h3>State Changes</h3>
                    <div class="status-value" id="state-changes-count">-</div>
                </div>
            </div>
        </div>
        
        <div class="controls">
            <h2>System Controls</h2>
            <div class="control-buttons">
                <button class="btn btn-primary" onclick="startOrchestrator()">Start Orchestrator</button>
                <button class="btn btn-danger" onclick="stopOrchestrator()">Stop Orchestrator</button>
                <button class="btn btn-secondary" onclick="exportTrainingData()">Export Training Data</button>
                <button class="btn btn-secondary" onclick="refreshData()">Refresh All</button>
            </div>
        </div>
        
        <div class="section">
            <h2>Send Test Message</h2>
            <div class="message-form">
                <div class="form-group">
                    <label for="channel-id">Channel ID</label>
                    <input type="text" id="channel-id" class="form-control" placeholder="!channel:matrix.example.com" value="!test:control-panel">
                </div>
                <div class="form-group">
                    <label for="message-content">Message</label>
                    <input type="text" id="message-content" class="form-control" placeholder="Hello, AI!">
                </div>
                <div class="form-group">
                    <label>&nbsp;</label>
                    <button class="btn btn-primary" onclick="sendMessage()">Send Message</button>
                </div>
            </div>
        </div>
        
        <div class="section">
            <h2>Recent State Changes</h2>
            <div id="state-changes">
                <div class="loading">Loading state changes...</div>
            </div>
        </div>
        
        <div class="section">
            <h2>Active Contexts</h2>
            <div id="contexts">
                <div class="loading">Loading contexts...</div>
            </div>
        </div>
    </div>
    
    <button class="refresh-btn" onclick="refreshData()" title="Refresh Data">
        🔄
    </button>
    
    <script>
        let refreshInterval;
        
        async function apiCall(url, method = 'GET', body = null) {
            try {
                const options = {
                    method,
                    headers: {
                        'Content-Type': 'application/json',
                    }
                };
                
                if (body) {
                    options.body = JSON.stringify(body);
                }
                
                const response = await fetch(url, options);
                
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }
                
                return await response.json();
            } catch (error) {
                console.error('API call failed:', error);
                showError(`API Error: ${error.message}`);
                throw error;
            }
        }
        
        function showError(message) {
            const existingError = document.querySelector('.error');
            if (existingError) {
                existingError.remove();
            }
            
            const errorDiv = document.createElement('div');
            errorDiv.className = 'error';
            errorDiv.textContent = message;
            
            document.querySelector('.container').insertBefore(errorDiv, document.querySelector('.header').nextSibling);
            
            setTimeout(() => errorDiv.remove(), 5000);
        }
        
        function showSuccess(message) {
            const existingSuccess = document.querySelector('.success');
            if (existingSuccess) {
                existingSuccess.remove();
            }
            
            const successDiv = document.createElement('div');
            successDiv.className = 'success';
            successDiv.textContent = message;
            
            document.querySelector('.container').insertBefore(successDiv, document.querySelector('.header').nextSibling);
            
            setTimeout(() => successDiv.remove(), 3000);
        }
        
        async function loadStatus() {
            try {
                const status = await apiCall('/api/status');
                
                document.getElementById('system-status').textContent = status.running ? 'Running' : 'Stopped';
                document.getElementById('system-status').style.color = status.running ? '#238636' : '#da3633';
                document.getElementById('cycle-count').textContent = status.cycle_count;
                document.getElementById('active-channels').textContent = status.active_channels.length;
                document.getElementById('state-changes-count').textContent = status.total_state_changes;
            } catch (error) {
                document.getElementById('system-status').textContent = 'Error';
                document.getElementById('system-status').style.color = '#da3633';
            }
        }
        
        async function loadStateChanges() {
            try {
                const changes = await apiCall('/api/state-changes?limit=10');
                const container = document.getElementById('state-changes');
                
                if (changes.length === 0) {
                    container.innerHTML = '<div class="loading">No state changes yet</div>';
                    return;
                }
                
                container.innerHTML = changes.map(change => `
                    <div class="state-change">
                        <div class="state-change-header">
                            <div>
                                <span class="state-change-type">${change.change_type}</span>
                                <span style="margin-left: 10px; color: #7d8590;">from ${change.source}</span>
                                ${change.channel_id ? `<span style="margin-left: 10px; color: #58a6ff;">${change.channel_id}</span>` : ''}
                            </div>
                            <div class="state-change-time">${change.formatted_time}</div>
                        </div>
                        ${change.observations ? `<div style="color: #e6edf3; margin-bottom: 8px;"><strong>Observations:</strong> ${change.observations}</div>` : ''}
                        ${change.reasoning ? `<div style="color: #e6edf3;"><strong>Reasoning:</strong> ${change.reasoning}</div>` : ''}
                    </div>
                `).join('');
            } catch (error) {
                document.getElementById('state-changes').innerHTML = '<div class="error">Failed to load state changes</div>';
            }
        }
        
        async function loadContexts() {
            try {
                const contexts = await apiCall('/api/contexts');
                const container = document.getElementById('contexts');
                
                if (contexts.length === 0) {
                    container.innerHTML = '<div class="loading">No active contexts</div>';
                    return;
                }
                
                container.innerHTML = contexts.map(context => `
                    <div class="context-card">
                        <div class="context-header">
                            <div class="context-id">${context.channel_id}</div>
                            <button class="btn btn-danger" style="padding: 5px 10px; font-size: 12px;" onclick="clearContext('${context.channel_id}')">Clear</button>
                        </div>
                        <div class="context-stats">
                            <span>👤 ${context.user_message_count} user messages</span>
                            <span>🤖 ${context.assistant_message_count} AI messages</span>
                            <span>🕒 Last update: ${context.formatted_last_update}</span>
                        </div>
                    </div>
                `).join('');
            } catch (error) {
                document.getElementById('contexts').innerHTML = '<div class="error">Failed to load contexts</div>';
            }
        }
        
        async function startOrchestrator() {
            try {
                await apiCall('/api/start', 'POST');
                showSuccess('Orchestrator started successfully');
                await loadStatus();
            } catch (error) {
                // Error already shown by apiCall
            }
        }
        
        async function stopOrchestrator() {
            try {
                await apiCall('/api/stop', 'POST');
                showSuccess('Orchestrator stopped successfully');
                await loadStatus();
            } catch (error) {
                // Error already shown by apiCall
            }
        }
        
        async function exportTrainingData() {
            try {
                const result = await apiCall('/api/export', 'POST');
                showSuccess(`Training data exported to: ${result.file}`);
            } catch (error) {
                // Error already shown by apiCall
            }
        }
        
        async function sendMessage() {
            const channelId = document.getElementById('channel-id').value;
            const content = document.getElementById('message-content').value;
            
            if (!channelId || !content) {
                showError('Please fill in both channel ID and message content');
                return;
            }
            
            try {
                await apiCall('/api/message', 'POST', {
                    channel_id: channelId,
                    content: content
                });
                
                showSuccess('Message sent successfully');
                document.getElementById('message-content').value = '';
                
                // Refresh data after sending message
                setTimeout(refreshData, 1000);
            } catch (error) {
                // Error already shown by apiCall
            }
        }
        
        async function clearContext(channelId) {
            if (!confirm(`Are you sure you want to clear the context for ${channelId}?`)) {
                return;
            }
            
            try {
                await apiCall(`/api/context/${encodeURIComponent(channelId)}`, 'DELETE');
                showSuccess(`Context cleared for ${channelId}`);
                await loadContexts();
            } catch (error) {
                // Error already shown by apiCall
            }
        }
        
        async function refreshData() {
            const refreshBtn = document.querySelector('.refresh-btn');
            refreshBtn.style.transform = 'rotate(360deg)';
            
            await Promise.all([
                loadStatus(),
                loadStateChanges(),
                loadContexts()
            ]);
            
            setTimeout(() => {
                refreshBtn.style.transform = 'rotate(0deg)';
            }, 500);
        }
        
        // Initialize the page
        document.addEventListener('DOMContentLoaded', function() {
            refreshData();
            
            // Auto-refresh every 10 seconds
            refreshInterval = setInterval(refreshData, 10000);
        });
        
        // Handle page visibility for battery saving
        document.addEventListener('visibilitychange', function() {
            if (document.hidden) {
                clearInterval(refreshInterval);
            } else {
                refreshData();
                refreshInterval = setInterval(refreshData, 10000);
            }
        });
    </script>
</body>
</html>
"""

def main():
    """Main entry point for the control panel."""
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    import argparse
    
    parser = argparse.ArgumentParser(description="Context Management Control Panel")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    
    args = parser.parse_args()
    
    print(f"""
🤖 Context Management Control Panel Starting...

Open your browser and go to:
http://localhost:{args.port}

Features:
- Monitor system status and state changes
- Start/stop the orchestrator
- Send test messages
- View conversation contexts
- Export training data
- Clear contexts

Press Ctrl+C to stop the server.
""")
    
    uvicorn.run(
        "control_panel:app",
        host=args.host,
        port=args.port,
        reload=args.reload
    )


if __name__ == "__main__":
    main()
