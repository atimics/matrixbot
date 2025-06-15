"""
Processing Hub

Central hub for handling different processing strategies (traditional vs node-based)
and managing the main event loop logic.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from ..world_state.manager import WorldStateManager
    from ..world_state.payload_builder import PayloadBuilder
    from .rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


@dataclass(frozen=True, eq=True)  # frozen=True makes it hashable for sets
class Trigger:
    """Represents an important event that should prompt the bot to act."""
    type: str  # e.g., 'new_message', 'mention', 'reaction', 'system_event'
    priority: int  # 1 (low) to 10 (high)
    channel_id: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict, hash=False, compare=False)


@dataclass
class ProcessingConfig:
    """Configuration for processing strategy selection."""
    
    # Processing mode settings
    enable_node_based_processing: bool = True
    
    # Observation settings
    observation_interval: float = 10.0  # Polling interval for trigger queue
    max_cycles_per_hour: int = 300


class ProcessingHub:
    """
    Central processing hub that coordinates different processing strategies.
    
    This class is responsible for:
    1. Managing the main event loop
    2. Selecting between traditional and node-based processing
    3. Coordinating rate limiting and state change detection
    4. Providing unified status and metrics
    """
    
    def __init__(
        self,
        world_state_manager: "WorldStateManager",
        payload_builder: "PayloadBuilder", 
        rate_limiter: "RateLimiter",
        config: Optional[ProcessingConfig] = None
    ):
        self.world_state = world_state_manager
        self.payload_builder = payload_builder
        self.rate_limiter = rate_limiter
        self.config = config or ProcessingConfig()
        
        # Processing state
        self.running = False
        self.cycle_count = 0
        self.last_cycle_time = 0
        self.current_processing_mode = "node_based"
        self.payload_size_history: List[int] = []
        
        # Trigger-based processing
        self.trigger_queue = asyncio.Queue()
        
        # Processing coordination - prevent overlapping cycles
        self._processing_lock = asyncio.Lock()
        self._current_cycle_id = None
        
        # Component availability tracking
        self.node_processor = None
        
    def set_node_processor(self, processor):
        """Set the node-based processing component."""
        self.node_processor = processor
        
    async def start_processing_loop(self) -> None:
        """Start the main processing event loop."""
        if self.running:
            logger.warning("Processing hub already running")
            return

        logger.info("Starting processing hub...")
        self.running = True
        
        try:
            await self._main_event_loop()
        except Exception as e:
            logger.error(f"Error in processing hub: {e}")
            raise
        finally:
            self.running = False
            logger.info("Processing hub stopped")

    def stop_processing_loop(self):
        """Stop the processing loop."""
        self.running = False
        
    def add_trigger(self, trigger: Trigger):
        """Add a trigger to the processing queue."""
        try:
            self.trigger_queue.put_nowait(trigger)
            logger.info(f"Trigger added to queue: {trigger.type} (Priority: {trigger.priority})")
        except asyncio.QueueFull:
            logger.warning(f"Trigger queue full, dropping trigger: {trigger.type}")
    
    def trigger_state_change(self):
        """Trigger immediate processing when world state changes (legacy compatibility)."""
        # For backward compatibility, generate a generic state change trigger
        generic_trigger = Trigger(
            type='state_change',
            priority=5,
            context={'source': 'legacy_trigger'}
        )
        self.add_trigger(generic_trigger)

    async def _main_event_loop(self) -> None:
        """Main event loop for processing triggers from the queue."""
        logger.info("Starting trigger-based event loop...")
        
        while self.running:
            try:
                # Wait for triggers or poll interval timeout
                try:
                    # Wait for the first trigger with a timeout
                    first_trigger = await asyncio.wait_for(
                        self.trigger_queue.get(),
                        timeout=self.config.observation_interval
                    )
                    triggers = {first_trigger}  # Use a set to auto-deduplicate
                except asyncio.TimeoutError:
                    # Polling interval reached, no triggers. Continue to next iteration.
                    continue

                # Drain any other triggers that arrived in the meantime
                while not self.trigger_queue.empty():
                    try:
                        triggers.add(self.trigger_queue.get_nowait())
                    except asyncio.QueueEmpty:
                        break
                
                # Now, process the collected triggers
                await self._process_triggers(triggers)

            except asyncio.CancelledError:
                logger.info("Event loop cancelled.")
                break
            except Exception as e:
                logger.error(f"Error in event loop cycle: {e}", exc_info=True)
                await asyncio.sleep(5)  # Cooldown on error

    async def _process_triggers(self, triggers: Set[Trigger]):
        """Deduplicates and processes a batch of triggers."""
        if not triggers:
            return

        # Sort by priority to determine the primary reason for this cycle
        highest_priority_trigger = max(triggers, key=lambda t: t.priority)
        logger.info(f"Processing {len(triggers)} triggers. Highest priority: {highest_priority_trigger.type}")

        # Prevent re-processing if a cycle is already locked
        if self._processing_lock.locked():
            logger.warning(f"Processing lock is active. Skipping trigger batch.")
            return

        # Validate node processor is available
        if not self.node_processor:
            logger.warning("Node processor not available - cannot process triggers")
            return

        async with self._processing_lock:
            self.cycle_count += 1
            self._current_cycle_id = f"cycle_{self.cycle_count}"
            
            # Check rate limiting
            cycle_start = time.time()
            can_process, wait_time = self.rate_limiter.can_process_cycle(cycle_start)

            if not can_process:
                if wait_time > 0:
                    logger.debug(f"Rate limiting: waiting {wait_time:.2f}s before next cycle")
                    await asyncio.sleep(min(wait_time, self.config.observation_interval))
                return

            # Record the cycle for rate limiting
            self.rate_limiter.record_cycle(cycle_start)
            
            # The primary channel is determined by the highest priority trigger
            primary_channel_id = highest_priority_trigger.channel_id

            # Pass all trigger data to the processor for full context
            trigger_context = [
                {
                    'type': t.type,
                    'priority': t.priority,
                    'channel_id': t.channel_id,
                    'context': t.context
                } for t in triggers
            ]
            
            logger.info(f"Starting {self._current_cycle_id} triggered by {highest_priority_trigger.type}")
            
            try:
                await self.node_processor.process_cycle(
                    cycle_id=self._current_cycle_id,
                    primary_channel_id=primary_channel_id,
                    context={"triggers": trigger_context}
                )

                # Update final tracking
                self.last_cycle_time = cycle_start
                
                cycle_duration = time.time() - cycle_start
                logger.info(f"{self._current_cycle_id} completed in {cycle_duration:.2f}s")
                
                # Log rate limiting status every 10 cycles for monitoring
                if self.cycle_count % 10 == 0:
                    self._log_rate_limit_status()
                    
            except Exception as e:
                logger.error(f"Error in {self._current_cycle_id}: {e}", exc_info=True)
            finally:
                self._current_cycle_id = None

    def get_processing_status(self) -> Dict[str, Any]:
        """Get comprehensive processing status."""
        return {
            "running": self.running,
            "current_mode": self.current_processing_mode,
            "cycle_count": self.cycle_count,
            "last_cycle_time": self.last_cycle_time,
            "processing_in_progress": self._processing_lock.locked(),
            "current_cycle_id": self._current_cycle_id,
            "pending_triggers": self.trigger_queue.qsize(),
            "payload_size_history": self.payload_size_history[-5:],  # Last 5 estimates
            "node_processor_available": self.node_processor is not None,
            "config": {
                "enable_node_based_processing": self.config.enable_node_based_processing,
                "observation_interval": self.config.observation_interval,
            }
        }

    def get_rate_limit_status(self) -> Dict[str, Any]:
        """Get current rate limiting status."""
        current_time = time.time()
        return self.rate_limiter.get_rate_limit_status(current_time)

    def _log_rate_limit_status(self):
        """Log current rate limiting status."""
        try:
            current_time = time.time()
            status = self.rate_limiter.get_rate_limit_status(current_time)
            logger.info(f"Rate limit status: {status['cycles_per_hour']}/{status['max_cycles_per_hour']} cycles/hour")
        except Exception as e:
            logger.error(f"Error logging rate limit status: {e}")
