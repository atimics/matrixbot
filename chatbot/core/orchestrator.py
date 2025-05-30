"""
Context-Aware Orchestrator

The main orchestrator that coordinates all chatbot components with context management.
"""

import asyncio
import logging
import os
import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from pathlib import Path

from ..core.world_state import WorldStateManager
from ..core.ai_engine import AIDecisionEngine
from ..core.context import ContextManager
from ..tools.executor import ActionExecutor
from ..integrations.matrix.observer import MatrixObserver
from ..integrations.farcaster.observer import FarcasterObserver

logger = logging.getLogger(__name__)


@dataclass
class OrchestratorConfig:
    """Configuration for the orchestrator."""
    db_path: str = "chatbot.db"
    observation_interval: float = 2.0  # More responsive default
    max_cycles_per_hour: int = 300  # Allow up to 5 responses per minute
    ai_model: str = "openai/gpt-4o-mini"  # More reliable default model


class ContextAwareOrchestrator:
    """Main orchestrator for the context-aware chatbot system."""
    
    def __init__(self, config: Optional[OrchestratorConfig] = None):
        self.config = config or OrchestratorConfig()
        
        # Initialize core components
        self.world_state = WorldStateManager()
        self.context_manager = ContextManager(self.world_state, self.config.db_path)
        self.ai_engine = AIDecisionEngine(
            api_key=os.getenv("OPENROUTER_API_KEY"),
            model=self.config.ai_model
        )
        self.action_executor = ActionExecutor()
        
        # Observers (initialized when credentials available)
        self.matrix_observer: Optional[MatrixObserver] = None
        self.farcaster_observer: Optional[FarcasterObserver] = None
        
        # State tracking
        self.running = False
        self.cycle_count = 0
        self.last_cycle_time = 0
        self.min_cycle_interval = 3600 / self.config.max_cycles_per_hour
        
        # Event-driven processing
        self.state_changed_event = asyncio.Event()
        
        logger.info("Context-aware orchestrator initialized")
    
    async def start(self) -> None:
        """Start the orchestrator system."""
        if self.running:
            logger.warning("Orchestrator already running")
            return
            
        logger.info("Starting context-aware orchestrator...")
        self.running = True
        
        try:
            await self._initialize_observers()
            await self._main_event_loop()
        except Exception as e:
            logger.error(f"Error in orchestrator: {e}")
            raise
        finally:
            await self.stop()
    
    async def stop(self) -> None:
        """Stop the orchestrator system."""
        if not self.running:
            return
            
        logger.info("Stopping context-aware orchestrator...")
        self.running = False
        
        if self.matrix_observer:
            await self.matrix_observer.stop()
        
        if self.farcaster_observer:
            await self.farcaster_observer.stop()
        
        logger.info("Context-aware orchestrator stopped")
    
    async def _initialize_observers(self) -> None:
        """Initialize available observers based on environment configuration."""
        # Initialize Matrix observer if credentials available
        if os.getenv("MATRIX_USER_ID") and os.getenv("MATRIX_PASSWORD"):
            try:
                self.matrix_observer = MatrixObserver(self.world_state)
                room_id = os.getenv("MATRIX_ROOM_ID", "#robot-laboratory:chat.ratimics.com")
                self.matrix_observer.add_channel(room_id, "Robot Laboratory")
                await self.matrix_observer.start()
                self.action_executor.set_matrix_observer(self.matrix_observer)
                logger.info("Matrix observer initialized and started")
            except Exception as e:
                logger.error(f"Failed to initialize Matrix observer: {e}")
        
        # Initialize Farcaster observer if credentials available
        if os.getenv("NEYNAR_API_KEY"):
            try:
                self.farcaster_observer = FarcasterObserver(self.world_state)
                await self.farcaster_observer.start()
                self.action_executor.set_farcaster_observer(self.farcaster_observer)
                logger.info("Farcaster observer initialized and started")
            except Exception as e:
                logger.error(f"Failed to initialize Farcaster observer: {e}")
    
    async def _main_event_loop(self) -> None:
        """Main event loop for processing world state changes."""
        logger.info("Starting main event loop...")
        last_state_hash = None
        
        while self.running:
            try:
                # Wait for state change event or timeout
                try:
                    await asyncio.wait_for(self.state_changed_event.wait(), timeout=self.config.observation_interval)
                    self.state_changed_event.clear()
                    logger.info("State change event triggered")
                except asyncio.TimeoutError:
                    # Periodic check even if no events
                    pass
                
                cycle_start = time.time()
                
                # Rate limiting
                if cycle_start - self.last_cycle_time < self.min_cycle_interval:
                    logger.debug(f"Rate limiting: {cycle_start - self.last_cycle_time:.2f}s < {self.min_cycle_interval:.2f}s")
                    remaining_time = self.min_cycle_interval - (cycle_start - self.last_cycle_time)
                    if remaining_time > 0:
                        await asyncio.sleep(remaining_time)
                    continue
                
                # Get current world state
                current_state = self.world_state.to_dict()
                current_hash = self._hash_state(current_state)
                
                # Check if state has changed
                if current_hash != last_state_hash:
                    logger.info(f"World state changed, processing cycle {self.cycle_count}")
                    
                    # Get active channels
                    active_channels = self._get_active_channels(current_state)
                    
                    # Process each active channel
                    for channel_id in active_channels:
                        await self._process_channel(channel_id)
                    
                    # Update tracking
                    last_state_hash = current_hash
                    self.cycle_count += 1
                    self.last_cycle_time = cycle_start
                    
                    cycle_duration = time.time() - cycle_start
                    logger.info(f"Cycle {self.cycle_count} completed in {cycle_duration:.2f}s")
                
            except Exception as e:
                logger.error(f"Error in event loop cycle {self.cycle_count}: {e}")
                await asyncio.sleep(5)
    
    def trigger_state_change(self):
        """Trigger immediate processing when world state changes"""
        if self.state_changed_event and not self.state_changed_event.is_set():
            self.state_changed_event.set()
            logger.debug("State change event triggered by external caller")
    
    async def _process_channel(self, channel_id: str) -> None:
        """Process a single channel for AI decision making."""
        try:
            # Get conversation messages with world state in system prompt
            messages = await self.context_manager.get_conversation_messages(channel_id)
            
            # Get current world state for AI decision making
            world_state = self.world_state.to_dict()
            cycle_id = f"cycle_{self.cycle_count}_{channel_id}"
            
            # Make AI decision
            decision = await self.ai_engine.make_decision(world_state, cycle_id)
            
            if decision and decision.selected_actions:
                # Record AI response in context
                ai_response = {
                    "content": f"Decision: {decision.reasoning}",
                    "timestamp": time.time(),
                    "channel_id": channel_id
                }
                await self.context_manager.add_assistant_message(channel_id, ai_response)
                
                # Execute selected actions
                for action in decision.selected_actions:
                    await self._execute_action(channel_id, action)
                    
        except Exception as e:
            logger.error(f"Error processing channel {channel_id}: {e}")
    
    async def _execute_action(self, channel_id: str, action: Any) -> None:
        """Execute a single action and record the result."""
        try:
            result = await self.action_executor.execute_action(
                action.action_type, 
                action.parameters
            )
            
            # Record successful execution
            tool_result = {
                "action_type": action.action_type,
                "parameters": action.parameters,
                "result": result,
                "status": "success",
                "timestamp": time.time()
            }
            
            await self.context_manager.add_tool_result(
                channel_id, 
                action.action_type, 
                tool_result
            )
            
            logger.info(f"Executed action {action.action_type} successfully")
            
        except Exception as e:
            logger.error(f"Error executing action {action.action_type}: {e}")
            
            # Record failed execution
            error_result = {
                "action_type": action.action_type,
                "parameters": getattr(action, 'parameters', {}),
                "error": str(e),
                "status": "failed",
                "timestamp": time.time()
            }
            
            await self.context_manager.add_tool_result(
                channel_id,
                action.action_type,
                error_result
            )
    
    def _get_active_channels(self, world_state: Dict[str, Any]) -> List[str]:
        """Get list of channels with recent activity."""
        active_channels = []
        channels = world_state.get('channels', {})
        current_time = time.time()
        
        for channel_id, channel_data in channels.items():
            # Check for recent activity (last 10 minutes)
            last_activity = channel_data.get('last_checked', 0)
            if current_time - last_activity < 600:
                active_channels.append(channel_id)
        
        # If no recent activity, include all monitored channels
        if not active_channels and channels:
            active_channels = list(channels.keys())
        
        return active_channels
    
    def _hash_state(self, state: Dict[str, Any]) -> str:
        """Generate hash of current state for change detection."""
        import hashlib
        import json
        state_str = json.dumps(state, sort_keys=True, default=str)
        return hashlib.sha256(state_str.encode()).hexdigest()
    
    # Public API methods
    async def add_user_message(self, channel_id: str, message: Dict[str, Any]) -> None:
        """Add a user message to the context."""
        await self.context_manager.add_user_message(channel_id, message)
    
    async def get_context_summary(self, channel_id: str) -> Dict[str, Any]:
        """Get context summary for a channel."""
        return await self.context_manager.get_context_summary(channel_id)
    
    async def clear_context(self, channel_id: str) -> None:
        """Clear context for a channel."""
        await self.context_manager.clear_context(channel_id)
    
    async def export_training_data(self, output_path: str) -> str:
        """Export state changes for training."""
        return await self.context_manager.export_state_changes_for_training(output_path)
