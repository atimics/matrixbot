#!/usr/bin/env python3
"""
Event-Driven Orchestrator

This is the main orchestrator that implements an event-driven architecture:
1. Observes world state changes
2. Triggers AI decision making when changes occur
3. Executes selected actions
4. Updates world state with results
5. Repeats the cycle when new changes are detected

The system follows this pattern:
world_state -> AI_decision -> action_execution -> world_state_update -> (repeat on changes)
"""

import asyncio
import logging
import os
import time
from typing import Set, Optional, List
from dataclasses import asdict
from dotenv import load_dotenv

from world_state import WorldState, WorldStateManager
from ai_engine import AIDecisionEngine
from action_executor import ActionExecutor
from matrix_observer import MatrixObserver
from farcaster_observer import FarcasterObserver

logger = logging.getLogger(__name__)

class EventOrchestrator:
    """Main event-driven orchestrator for the AI system"""
    
    def __init__(self):
        # Load environment variables
        load_dotenv()
        
    def __init__(self):
        # Load environment variables
        load_dotenv()
        
        # Initialize components
        self.world_state = WorldStateManager()
        self.ai_engine = AIDecisionEngine(
            api_key=os.getenv("OPENROUTER_API_KEY"),
            model=os.getenv("AI_MODEL", "anthropic/claude-3-5-sonnet-20241022")
        )
        self.action_executor = ActionExecutor()
        
        # Note: Observers will be created later when we have proper credentials
        self.matrix_observer = None
        self.farcaster_observer = None
        
        # State tracking
        self.running = False
        self.last_state_hash = None
        self.cycle_count = 0
        self.last_observation_time = 0
        
        # Configuration
        self.observation_interval = float(os.getenv("OBSERVATION_INTERVAL", "30"))  # seconds
        self.max_cycles_per_hour = int(os.getenv("MAX_CYCLES_PER_HOUR", "60"))
        self.min_cycle_interval = 3600 / self.max_cycles_per_hour  # Rate limiting
        
        logger.info("Event orchestrator initialized")
    
    async def start(self):
        """Start the event-driven orchestration loop"""
        logger.info("Starting event-driven orchestrator...")
        self.running = True
        
        try:
            # Initialize observers if credentials are available
            if os.getenv("MATRIX_USER_ID") and os.getenv("MATRIX_PASSWORD"):
                self.matrix_observer = MatrixObserver(self.world_state)
                
                # Add the configured room to monitor
                room_id = os.getenv("MATRIX_ROOM_ID", "#robot-laboratory:chat.ratimics.com")
                self.matrix_observer.add_channel(room_id, "Robot Laboratory")
                
                await self.matrix_observer.start()
                self.action_executor.set_matrix_observer(self.matrix_observer)
                logger.info("Matrix observer started")
            
            if os.getenv("NEYNAR_API_KEY"):
                self.farcaster_observer = FarcasterObserver(self.world_state)
                await self.farcaster_observer.start()
                self.action_executor.set_farcaster_observer(self.farcaster_observer)
                logger.info("Farcaster observer started")
            
            # Start the main event loop
            await self._main_event_loop()
            
        except Exception as e:
            logger.error(f"Error in orchestrator: {e}")
            raise
        finally:
            await self.stop()
    
    async def stop(self):
        """Stop the orchestrator and cleanup"""
        logger.info("Stopping event orchestrator...")
        self.running = False
        
        try:
            if self.matrix_observer:
                await self.matrix_observer.stop()
                logger.info("Matrix observer stopped")
            if self.farcaster_observer:
                await self.farcaster_observer.stop()
                logger.info("Farcaster observer stopped")
        except Exception as e:
            logger.error(f"Error stopping observers: {e}")
    
    async def _main_event_loop(self):
        """Main event loop - responds to world state changes"""
        logger.info("Starting main event loop...")
        
        while self.running:
            try:
                # Check if it's time for scheduled observation
                current_time = time.time()
                if current_time - self.last_observation_time >= self.observation_interval:
                    await self._trigger_observation_cycle()
                    self.last_observation_time = current_time
                
                # Check for world state changes
                current_state_hash = self._calculate_state_hash()
                if current_state_hash != self.last_state_hash:
                    logger.info(f"World state change detected (hash: {current_state_hash[:8]}...)")
                    await self._trigger_decision_cycle()
                    self.last_state_hash = current_state_hash
                
                # Small sleep to prevent busy waiting
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Error in main event loop: {e}")
                await asyncio.sleep(5)  # Wait before retrying
    
    async def _trigger_observation_cycle(self):
        """Trigger scheduled observations to gather new world state"""
        logger.info("Triggering scheduled observation cycle...")
        
        try:
            # Observe Matrix channels (Matrix observer handles this automatically via sync)
            if self.matrix_observer:
                logger.debug("Matrix observer active and syncing")
            
            # Observe Farcaster feeds
            if self.farcaster_observer:
                farcaster_fids = self._get_farcaster_fids()
                farcaster_channels = self._get_farcaster_channels()
                if farcaster_fids or farcaster_channels:
                    farcaster_messages = await self.farcaster_observer.observe_feeds(
                        fids=farcaster_fids,
                        channels=farcaster_channels
                    )
                    if farcaster_messages:
                        logger.info(f"Observed {len(farcaster_messages)} new Farcaster messages")
                        for message in farcaster_messages:
                            self.world_state.add_message(message.channel_id, message)
            
            # Update system status
            self.world_state.update_system_status({
                "last_observation": time.time(),
                "matrix_connected": getattr(self.matrix_observer, 'client', None) is not None if self.matrix_observer else False,
                "farcaster_connected": getattr(self.farcaster_observer, 'running', False) if self.farcaster_observer else False,
                "cycle_count": self.cycle_count
            })
            
        except Exception as e:
            logger.error(f"Error in observation cycle: {e}")
    
    async def _trigger_decision_cycle(self):
        """Trigger AI decision making and action execution"""
        logger.info("Triggering AI decision cycle...")
        
        try:
            # Rate limiting check
            if not self._should_run_cycle():
                logger.info("Skipping cycle due to rate limiting")
                return
            
            self.cycle_count += 1
            cycle_start = time.time()
            
            # Get current world state for AI
            world_state_json = self.world_state.to_json()
            logger.debug(f"World state size: {len(world_state_json)} characters")
            
            # AI decision making
            logger.info("Running AI decision engine...")
            world_state_dict = self.world_state.to_dict()
            decision_result = await self.ai_engine.make_decision(world_state_dict, f"cycle_{self.cycle_count}")
            
            if not decision_result.selected_actions:
                logger.info("AI selected no actions to take")
                return
            
            logger.info(f"AI selected {len(decision_result.selected_actions)} actions")
            logger.info(f"AI reasoning: {decision_result.reasoning}")
            
            # Execute selected actions
            execution_results = []
            for action_plan in decision_result.selected_actions:
                try:
                    logger.info(f"Executing action: {action_plan.action_type}")
                    result = await self.action_executor.execute_action(
                        action_plan.action_type,
                        action_plan.parameters
                    )
                    execution_results.append({
                        "action": action_plan.action_type,
                        "parameters": action_plan.parameters,
                        "result": result,
                        "success": True
                    })
                    logger.info(f"Action {action_plan.action_type} completed successfully")
                    
                except Exception as e:
                    logger.error(f"Action {action_plan.action_type} failed: {e}")
                    execution_results.append({
                        "action": action_plan.action_type,
                        "parameters": action_plan.parameters,
                        "result": str(e),
                        "success": False
                    })
            
            # Update world state with action history
            for result in execution_results:
                self.world_state.add_action_history({
                    "action_type": result["action"],
                    "parameters": result["parameters"],
                    "result": result["result"],
                    "timestamp": time.time()
                })
            
            cycle_duration = time.time() - cycle_start
            logger.info(f"Decision cycle {self.cycle_count} completed in {cycle_duration:.2f}s")
            
        except Exception as e:
            logger.error(f"Error in decision cycle: {e}")
    
    def _calculate_state_hash(self) -> str:
        """Calculate a hash of the current world state to detect changes"""
        try:
            # Create a simple hash based on message count and recent activity
            all_messages = self.world_state.get_all_messages()
            state_data = {
                "message_count": len(all_messages),
                "channel_count": len(self.world_state.state.channels),
                "last_message_time": max([msg.timestamp for msg in all_messages], default=0),
                "action_count": len(self.world_state.state.action_history)
            }
            return str(hash(str(sorted(state_data.items()))))
        except Exception as e:
            logger.error(f"Error calculating state hash: {e}")
            return str(time.time())  # Fallback to timestamp
    
    def _should_run_cycle(self) -> bool:
        """Check if we should run a decision cycle based on rate limiting"""
        if not hasattr(self, '_last_cycle_time'):
            self._last_cycle_time = 0
        
        current_time = time.time()
        time_since_last = current_time - self._last_cycle_time
        
        if time_since_last < self.min_cycle_interval:
            return False
        
        self._last_cycle_time = current_time
        return True
    
    def _get_farcaster_fids(self) -> List[int]:
        """Get list of Farcaster user IDs to monitor from environment"""
        fids_env = os.getenv("FARCASTER_FIDS", "")
        if not fids_env:
            return []
        
        try:
            return [int(fid.strip()) for fid in fids_env.split(",") if fid.strip()]
        except Exception as e:
            logger.error(f"Error parsing Farcaster FIDs: {e}")
            return []
    
    def _get_farcaster_channels(self) -> List[str]:
        """Get list of Farcaster channels to monitor from environment"""
        channels_env = os.getenv("FARCASTER_CHANNELS", "")
        if not channels_env:
            return []
        
        return [channel.strip() for channel in channels_env.split(",") if channel.strip()]
    
    def get_status(self) -> dict:
        """Get current orchestrator status"""
        return {
            "running": self.running,
            "cycle_count": self.cycle_count,
            "last_observation_time": self.last_observation_time,
            "world_state_hash": self.last_state_hash,
            "message_count": len(self.world_state.get_all_messages()),
            "channel_count": len(self.world_state.channels),
            "action_history_count": len(self.world_state.action_history),
            "matrix_connected": self.matrix_observer.is_connected() if self.matrix_observer and hasattr(self.matrix_observer, 'is_connected') else False,
            "farcaster_connected": self.farcaster_observer.is_connected() if self.farcaster_observer and hasattr(self.farcaster_observer, 'is_connected') else False,
            "farcaster_fids": self._get_farcaster_fids(),
            "farcaster_channels": self._get_farcaster_channels()
        }
    
    def _get_farcaster_fids(self) -> List[int]:
        """Get list of Farcaster user IDs to monitor from environment"""
        fids_str = os.getenv("FARCASTER_FIDS", "")
        if not fids_str:
            return []
        try:
            return [int(fid.strip()) for fid in fids_str.split(",") if fid.strip()]
        except ValueError:
            logger.warning("Invalid FARCASTER_FIDS format, expected comma-separated integers")
            return []
    
    def _get_farcaster_channels(self) -> List[str]:
        """Get list of Farcaster channels to monitor from environment"""
        channels_str = os.getenv("FARCASTER_CHANNELS", "")
        if not channels_str:
            return []
        return [channel.strip() for channel in channels_str.split(",") if channel.strip()]

async def main():
    """Main entry point for the event-driven orchestrator"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    orchestrator = EventOrchestrator()
    
    try:
        await orchestrator.start()
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise
    finally:
        await orchestrator.stop()

if __name__ == "__main__":
    asyncio.run(main())
