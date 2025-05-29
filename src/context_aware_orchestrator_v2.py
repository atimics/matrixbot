#!/usr/bin/env python3
"""
Context-Aware Event Orchestrator

This enhanced orchestrator integrates the ContextManager with the existing event-driven architecture
to manage evolving world state in system prompts while permanently storing all state change blocks.
"""

import asyncio
import logging
import os
import time
import json
from typing import Dict, List, Any, Optional
from dataclasses import asdict, dataclass
from dotenv import load_dotenv

from world_state import WorldStateManager
from ai_engine import AIDecisionEngine, DecisionResult, ActionPlan
from action_executor import ActionExecutor
from matrix_observer import MatrixObserver
from farcaster_observer import FarcasterObserver
from context_manager import ContextManager

logger = logging.getLogger(__name__)

@dataclass
class EnhancedDecisionResult:
    """Enhanced decision result with context tracking"""
    observations: str
    potential_actions: List[Dict[str, Any]]
    selected_actions: List[Dict[str, Any]]
    reasoning: str
    channel_id: str
    timestamp: float

class ContextAwareOrchestrator:
    """Context-aware event orchestrator with persistent state change tracking"""
    
    def __init__(self, db_path: str = "matrix_bot.db"):
        # Load environment variables
        load_dotenv()
        
        # Initialize core components
        self.world_state = WorldStateManager()
        self.ai_engine = AIDecisionEngine(
            api_key=os.getenv("OPENROUTER_API_KEY"),
            model=os.getenv("AI_MODEL", "anthropic/claude-3-5-sonnet-20241022")
        )
        self.action_executor = ActionExecutor()
        
        # Initialize context manager
        self.context_manager = ContextManager(self.world_state, db_path)
        
        # Observers (will be initialized if credentials are available)
        self.matrix_observer = None
        self.farcaster_observer = None
        
        # State tracking
        self.running = False
        self.last_state_hash = None
        self.cycle_count = 0
        
        # Configuration
        self.observation_interval = float(os.getenv("OBSERVATION_INTERVAL", "30"))
        self.max_cycles_per_hour = int(os.getenv("MAX_CYCLES_PER_HOUR", "60"))
        self.min_cycle_interval = 3600 / self.max_cycles_per_hour
        
        logger.info("Context-aware orchestrator initialized")
    
    async def start(self):
        """Start the context-aware orchestration system"""
        logger.info("Starting context-aware orchestrator...")
        self.running = True
        
        try:
            # Initialize observers if credentials are available
            await self._initialize_observers()
            
            # Start the main event loop
            await self._main_event_loop()
            
        except Exception as e:
            logger.error(f"Error in context-aware orchestrator: {e}")
            raise
        finally:
            await self.stop()
    
    async def _initialize_observers(self):
        """Initialize Matrix and Farcaster observers if credentials are available"""
        if os.getenv("MATRIX_USER_ID") and os.getenv("MATRIX_PASSWORD"):
            self.matrix_observer = MatrixObserver(self.world_state)
            
            # Add the configured room to monitor
            room_id = os.getenv("MATRIX_ROOM_ID", "#robot-laboratory:chat.ratimics.com")
            self.matrix_observer.add_channel(room_id, "Robot Laboratory")
            
            # Set up message handler to integrate with context manager
            original_handle_message = self.matrix_observer.handle_message
            
            async def enhanced_handle_message(room_id: str, sender_id: str, message_content: str, event_id: str, timestamp: float):
                # Call original handler
                await original_handle_message(room_id, sender_id, message_content, event_id, timestamp)
                
                # Add to context manager
                user_message = {
                    "content": message_content,
                    "sender": sender_id,
                    "event_id": event_id,
                    "timestamp": timestamp,
                    "room_id": room_id
                }
                await self.context_manager.add_user_message(room_id, user_message)
                logger.debug(f"Added user message to context: {room_id}")
            
            # Replace the handler
            self.matrix_observer.handle_message = enhanced_handle_message
            
            await self.matrix_observer.start()
            self.action_executor.set_matrix_observer(self.matrix_observer)
            logger.info("Enhanced Matrix observer started")
        
        if os.getenv("NEYNAR_API_KEY"):
            self.farcaster_observer = FarcasterObserver(self.world_state)
            await self.farcaster_observer.start()
            self.action_executor.set_farcaster_observer(self.farcaster_observer)
            logger.info("Farcaster observer started")
    
    async def _main_event_loop(self):
        """Main event loop with context-aware decision making"""
        logger.info("Starting main event loop...")
        
        while self.running:
            try:
                cycle_start = time.time()
                
                # Check if enough time has passed since last cycle (rate limiting)
                if cycle_start - getattr(self, 'last_cycle_time', 0) < self.min_cycle_interval:
                    await asyncio.sleep(1)
                    continue
                
                # Get current world state
                current_state = self.world_state.get_state()
                
                # Check if state has changed
                current_hash = self._hash_state(current_state)
                if current_hash == self.last_state_hash:
                    await asyncio.sleep(self.observation_interval)
                    continue
                
                logger.info(f"World state changed, triggering AI decision cycle {self.cycle_count}")
                
                # Get active channels with recent activity
                active_channels = self._get_active_channels(current_state)
                
                # Process each active channel
                for channel_id in active_channels:
                    await self._process_channel_cycle(channel_id, current_state)
                
                # Update state tracking
                self.last_state_hash = current_hash
                self.cycle_count += 1
                self.last_cycle_time = cycle_start
                
                # Log cycle completion
                cycle_duration = time.time() - cycle_start
                logger.info(f"Cycle {self.cycle_count} completed in {cycle_duration:.2f}s")
                
            except Exception as e:
                logger.error(f"Error in event loop cycle {self.cycle_count}: {e}")
                await asyncio.sleep(5)  # Brief pause before retrying
    
    async def _process_channel_cycle(self, channel_id: str, world_state: Dict[str, Any]):
        """Process a single channel's decision cycle"""
        try:
            # Get conversation messages with evolving world state system prompt
            messages = await self.context_manager.get_conversation_messages(channel_id)
            
            # Make AI decision using context-aware prompt
            decision_result = await self._make_ai_decision(channel_id, messages, world_state)
            
            if decision_result:
                # Add AI response to context
                ai_response = {
                    "content": json.dumps({
                        "observations": decision_result.observations,
                        "potential_actions": decision_result.potential_actions,
                        "selected_actions": decision_result.selected_actions,
                        "reasoning": decision_result.reasoning
                    }),
                    "timestamp": decision_result.timestamp,
                    "channel_id": channel_id
                }
                await self.context_manager.add_assistant_message(channel_id, ai_response)
                
                # Execute selected actions
                await self._execute_selected_actions(decision_result)
                
        except Exception as e:
            logger.error(f"Error processing channel {channel_id}: {e}")
    
    async def _make_ai_decision(self, channel_id: str, messages: List[Dict[str, Any]], world_state: Dict[str, Any]) -> Optional[EnhancedDecisionResult]:
        """Make AI decision using the context manager's structured prompts"""
        try:
            # Use the AI engine with the context-aware messages
            # The context manager already provides the system prompt with embedded world state
            decision = await self.ai_engine.make_decision(messages)
            
            if decision:
                # Parse the structured response
                response_content = decision.selected_actions[0].parameters.get('content', '') if decision.selected_actions else ''
                
                try:
                    structured_response = json.loads(response_content)
                    
                    # Convert to enhanced format
                    enhanced_result = EnhancedDecisionResult(
                        observations=structured_response.get('observations', decision.observations),
                        potential_actions=[
                            {
                                "action_type": action.action_type,
                                "parameters": action.parameters,
                                "reasoning": action.reasoning,
                                "priority": action.priority
                            } for action in getattr(decision, 'potential_actions', [])
                        ],
                        selected_actions=[
                            {
                                "action_type": action.action_type,
                                "parameters": action.parameters
                            } for action in decision.selected_actions
                        ],
                        reasoning=structured_response.get('reasoning', decision.reasoning),
                        channel_id=channel_id,
                        timestamp=time.time()
                    )
                    
                    return enhanced_result
                    
                except json.JSONDecodeError:
                    # Fall back to basic decision format
                    logger.debug("AI response not in structured format, using basic decision")
                    
            return None
            
        except Exception as e:
            logger.error(f"Error making AI decision for {channel_id}: {e}")
            return None
    
    async def _execute_selected_actions(self, decision_result: EnhancedDecisionResult):
        """Execute the selected actions and record results"""
        for action in decision_result.selected_actions:
            try:
                action_type = action["action_type"]
                parameters = action["parameters"]
                
                # Execute the action
                result = await self.action_executor.execute_action(action_type, parameters)
                
                # Record the tool execution result
                tool_result = {
                    "action_type": action_type,
                    "parameters": parameters,
                    "result": result,
                    "status": "success",
                    "timestamp": time.time()
                }
                
                await self.context_manager.add_tool_result(
                    decision_result.channel_id, 
                    action_type, 
                    tool_result
                )
                
                logger.info(f"Executed action {action_type} successfully")
                
            except Exception as e:
                logger.error(f"Error executing action {action.get('action_type', 'unknown')}: {e}")
                
                # Record the failed execution
                error_result = {
                    "action_type": action.get("action_type", "unknown"),
                    "parameters": action.get("parameters", {}),
                    "error": str(e),
                    "status": "failed",
                    "timestamp": time.time()
                }
                
                await self.context_manager.add_tool_result(
                    decision_result.channel_id,
                    action.get("action_type", "unknown"),
                    error_result
                )
    
    def _get_active_channels(self, world_state: Dict[str, Any]) -> List[str]:
        """Get list of channels with recent activity"""
        active_channels = []
        
        # Get channels from world state
        channels = world_state.get('channels', {})
        current_time = time.time()
        
        for channel_id, channel_data in channels.items():
            # Check if channel has had recent activity (last 10 minutes)
            last_activity = channel_data.get('last_message_time', 0)
            if current_time - last_activity < 600:  # 10 minutes
                active_channels.append(channel_id)
        
        # If no channels have recent activity, include all monitored channels
        if not active_channels and channels:
            active_channels = list(channels.keys())
        
        return active_channels
    
    def _hash_state(self, state: Dict[str, Any]) -> str:
        """Generate a hash of the current state for change detection"""
        import hashlib
        state_str = json.dumps(state, sort_keys=True)
        return hashlib.sha256(state_str.encode()).hexdigest()
    
    async def stop(self):
        """Stop the orchestrator and cleanup"""
        logger.info("Stopping context-aware orchestrator...")
        self.running = False
        
        if self.matrix_observer:
            await self.matrix_observer.stop()
        
        if self.farcaster_observer:
            await self.farcaster_observer.stop()
        
        logger.info("Context-aware orchestrator stopped")
    
    async def export_training_data(self, output_path: str) -> str:
        """Export all state changes for training purposes"""
        return await self.context_manager.export_state_changes_for_training(output_path)
    
    async def get_context_summary(self, channel_id: str) -> Dict[str, Any]:
        """Get summary of context for a specific channel"""
        return await self.context_manager.get_context_summary(channel_id)
    
    async def clear_context(self, channel_id: str):
        """Clear conversation context for a channel"""
        await self.context_manager.clear_context(channel_id)

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Context-Aware Event Orchestrator")
    parser.add_argument("--db-path", default="matrix_bot.db", help="Database path")
    parser.add_argument("--export", help="Export training data to specified path")
    parser.add_argument("--summary", help="Get context summary for channel ID")
    parser.add_argument("--clear", help="Clear context for channel ID")
    
    args = parser.parse_args()
    
    async def main():
        orchestrator = ContextAwareOrchestrator(args.db_path)
        
        if args.export:
            result = await orchestrator.export_training_data(args.export)
            print(f"Exported training data to: {result}")
        elif args.summary:
            summary = await orchestrator.get_context_summary(args.summary)
            print(f"Context summary for {args.summary}:")
            print(json.dumps(summary, indent=2))
        elif args.clear:
            await orchestrator.clear_context(args.clear)
            print(f"Cleared context for {args.clear}")
        else:
            await orchestrator.start()
    
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    asyncio.run(main())
