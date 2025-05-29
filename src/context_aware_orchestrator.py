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
            logger.info("Farcaster observer started")\n    \n    async def _main_event_loop(self):\n        """Main event loop with context-aware decision making"""\n        logger.info("Starting main event loop...")\n        \n        while self.running:\n            try:\n                cycle_start = time.time()\n                \n                # Check if enough time has passed since last cycle (rate limiting)\n                if cycle_start - getattr(self, 'last_cycle_time', 0) < self.min_cycle_interval:\n                    await asyncio.sleep(1)\n                    continue\n                \n                # Get current world state\n                current_state = self.world_state.get_state()\n                \n                # Check if state has changed\n                current_hash = self._hash_state(current_state)\n                if current_hash == self.last_state_hash:\n                    await asyncio.sleep(self.observation_interval)\n                    continue\n                \n                logger.info(f"World state changed, triggering AI decision cycle {self.cycle_count}")\n                \n                # Get active channels with recent activity\n                active_channels = self._get_active_channels(current_state)\n                \n                # Process each active channel\n                for channel_id in active_channels:\n                    await self._process_channel_cycle(channel_id, current_state)\n                \n                # Update state tracking\n                self.last_state_hash = current_hash\n                self.cycle_count += 1\n                self.last_cycle_time = cycle_start\n                \n                # Log cycle completion\n                cycle_duration = time.time() - cycle_start\n                logger.info(f"Cycle {self.cycle_count} completed in {cycle_duration:.2f}s")\n                \n            except Exception as e:\n                logger.error(f"Error in event loop cycle {self.cycle_count}: {e}")\n                await asyncio.sleep(5)  # Brief pause before retrying\n    \n    async def _process_channel_cycle(self, channel_id: str, world_state: Dict[str, Any]):\n        """Process a single channel's decision cycle"""\n        try:\n            # Get conversation messages with evolving world state system prompt\n            messages = await self.context_manager.get_conversation_messages(channel_id)\n            \n            # Make AI decision using context-aware prompt\n            decision_result = await self._make_ai_decision(channel_id, messages, world_state)\n            \n            if decision_result:\n                # Add AI response to context\n                ai_response = {\n                    "content": json.dumps({\n                        "observations": decision_result.observations,\n                        "potential_actions": decision_result.potential_actions,\n                        "selected_actions": decision_result.selected_actions,\n                        "reasoning": decision_result.reasoning\n                    }),\n                    "timestamp": decision_result.timestamp,\n                    "channel_id": channel_id\n                }\n                await self.context_manager.add_assistant_message(channel_id, ai_response)\n                \n                # Execute selected actions\n                await self._execute_selected_actions(decision_result)\n                \n        except Exception as e:\n            logger.error(f"Error processing channel {channel_id}: {e}")\n    \n    async def _make_ai_decision(self, channel_id: str, messages: List[Dict[str, Any]], world_state: Dict[str, Any]) -> Optional[EnhancedDecisionResult]:\n        """Make AI decision using the context manager's structured prompts"""\n        try:\n            # Use the AI engine with the context-aware messages\n            # The context manager already provides the system prompt with embedded world state\n            decision = await self.ai_engine.make_decision(messages)\n            \n            if decision:\n                # Parse the structured response\n                response_content = decision.selected_actions[0].parameters.get('content', '') if decision.selected_actions else ''\n                \n                try:\n                    structured_response = json.loads(response_content)\n                    \n                    # Convert to enhanced format\n                    enhanced_result = EnhancedDecisionResult(\n                        observations=structured_response.get('observations', decision.observations),\n                        potential_actions=[\n                            {\n                                "action_type": action.action_type,\n                                "parameters": action.parameters,\n                                "reasoning": action.reasoning,\n                                "priority": action.priority\n                            } for action in getattr(decision, 'potential_actions', [])\n                        ],\n                        selected_actions=[\n                            {\n                                "action_type": action.action_type,\n                                "parameters": action.parameters\n                            } for action in decision.selected_actions\n                        ],\n                        reasoning=structured_response.get('reasoning', decision.reasoning),\n                        channel_id=channel_id,\n                        timestamp=time.time()\n                    )\n                    \n                    return enhanced_result\n                    \n                except json.JSONDecodeError:\n                    # Fall back to basic decision format\n                    logger.debug("AI response not in structured format, using basic decision")\n                    \n            return None\n            \n        except Exception as e:\n            logger.error(f"Error making AI decision for {channel_id}: {e}")\n            return None\n    \n    async def _execute_selected_actions(self, decision_result: EnhancedDecisionResult):\n        """Execute the selected actions and record results"""\n        for action in decision_result.selected_actions:\n            try:\n                action_type = action["action_type"]\n                parameters = action["parameters"]\n                \n                # Execute the action\n                result = await self.action_executor.execute_action(action_type, parameters)\n                \n                # Record the tool execution result\n                tool_result = {\n                    "action_type": action_type,\n                    "parameters": parameters,\n                    "result": result,\n                    "status": "success",\n                    "timestamp": time.time()\n                }\n                \n                await self.context_manager.add_tool_result(\n                    decision_result.channel_id, \n                    action_type, \n                    tool_result\n                )\n                \n                logger.info(f"Executed action {action_type} successfully")\n                \n            except Exception as e:\n                logger.error(f"Error executing action {action.get('action_type', 'unknown')}: {e}")\n                \n                # Record the failed execution\n                error_result = {\n                    "action_type": action.get("action_type", "unknown"),\n                    "parameters": action.get("parameters", {}),\n                    "error": str(e),\n                    "status": "failed",\n                    "timestamp": time.time()\n                }\n                \n                await self.context_manager.add_tool_result(\n                    decision_result.channel_id,\n                    action.get("action_type", "unknown"),\n                    error_result\n                )\n    \n    def _get_active_channels(self, world_state: Dict[str, Any]) -> List[str]:\n        """Get list of channels with recent activity"""\n        active_channels = []\n        \n        # Get channels from world state\n        channels = world_state.get('channels', {})\n        current_time = time.time()\n        \n        for channel_id, channel_data in channels.items():\n            # Check if channel has had recent activity (last 10 minutes)\n            last_activity = channel_data.get('last_message_time', 0)\n            if current_time - last_activity < 600:  # 10 minutes\n                active_channels.append(channel_id)\n        \n        # If no channels have recent activity, include all monitored channels\n        if not active_channels and channels:\n            active_channels = list(channels.keys())\n        \n        return active_channels\n    \n    def _hash_state(self, state: Dict[str, Any]) -> str:\n        """Generate a hash of the current state for change detection"""\n        import hashlib\n        state_str = json.dumps(state, sort_keys=True)\n        return hashlib.sha256(state_str.encode()).hexdigest()\n    \n    async def stop(self):\n        """Stop the orchestrator and cleanup"""\n        logger.info("Stopping context-aware orchestrator...")\n        self.running = False\n        \n        if self.matrix_observer:\n            await self.matrix_observer.stop()\n        \n        if self.farcaster_observer:\n            await self.farcaster_observer.stop()\n        \n        logger.info("Context-aware orchestrator stopped")\n    \n    async def export_training_data(self, output_path: str) -> str:\n        """Export all state changes for training purposes"""\n        return await self.context_manager.export_state_changes_for_training(output_path)\n    \n    async def get_context_summary(self, channel_id: str) -> Dict[str, Any]:\n        """Get summary of context for a specific channel"""\n        return await self.context_manager.get_context_summary(channel_id)\n    \n    async def clear_context(self, channel_id: str):\n        """Clear conversation context for a channel"""\n        await self.context_manager.clear_context(channel_id)\n\nif __name__ == "__main__":\n    import argparse\n    \n    parser = argparse.ArgumentParser(description="Context-Aware Event Orchestrator")\n    parser.add_argument("--db-path", default="matrix_bot.db", help="Database path")\n    parser.add_argument("--export", help="Export training data to specified path")\n    parser.add_argument("--summary", help="Get context summary for channel ID")\n    parser.add_argument("--clear", help="Clear context for channel ID")\n    \n    args = parser.parse_args()\n    \n    async def main():\n        orchestrator = ContextAwareOrchestrator(args.db_path)\n        \n        if args.export:\n            result = await orchestrator.export_training_data(args.export)\n            print(f"Exported training data to: {result}")\n        elif args.summary:\n            summary = await orchestrator.get_context_summary(args.summary)\n            print(f"Context summary for {args.summary}:")\n            print(json.dumps(summary, indent=2))\n        elif args.clear:\n            await orchestrator.clear_context(args.clear)\n            print(f"Cleared context for {args.clear}")\n        else:\n            await orchestrator.start()\n    \n    # Set up logging\n    logging.basicConfig(\n        level=logging.INFO,\n        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'\n    )\n    \n    asyncio.run(main())
