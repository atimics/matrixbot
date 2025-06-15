"""
Processing Hub

Central hub for handling different processing strategies (traditional event-based and node-based)
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


@dataclass
class ProcessingConfig:
    """Configuration for the processing hub."""
    enable_node_based_processing: bool = True
    observation_interval: float = 60.0  # seconds
    max_cycles_per_hour: int = 30
    rate_limit_window: int = 3600  # seconds
    max_queue_size: int = 1000


@dataclass
class Trigger:
    """Represents a trigger for processing."""
    type: str
    priority: int = 0  # Higher values = higher priority
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class ProcessingHub:
    """
    Central hub for managing processing workflows.
    
    Coordinates between traditional event-based processing and the new node-based system.
    Manages triggers, rate limiting, and processing cycles.
    """
    
    def __init__(
        self,
        config: ProcessingConfig,
        world_state_manager: "WorldStateManager",
        payload_builder: "PayloadBuilder",
        rate_limiter: "RateLimiter"
    ):
        self.config = config
        self.world_state_manager = world_state_manager
        self.payload_builder = payload_builder
        self.rate_limiter = rate_limiter
        
        # Processing state
        self.running = False
        self._processing_lock = asyncio.Lock()
        
        # Trigger queue for event-driven processing
        self.trigger_queue = asyncio.Queue(maxsize=config.max_queue_size)
        
        # Component availability tracking
        self.node_processor = None
        
    def set_node_processor(self, processor):
        """Set the node-based processing component."""
        self.node_processor = processor
        
    def start_processing_loop(self) -> asyncio.Task:
        """Start the main processing loop as a background task."""
        if self.running:
            logger.warning("Processing hub already running")
            return None

        logger.info("Starting processing hub...")
        self.running = True
        
        # Start the event loop as a background task
        task = asyncio.create_task(self._main_event_loop())
        return task

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

    def add_generic_trigger(self, trigger_type: str, priority: int = 0, data: Optional[Dict] = None):
        """Add a generic trigger to the queue."""
        generic_trigger = Trigger(
            type=trigger_type,
            priority=priority,
            data=data or {}
        )
        self.add_trigger(generic_trigger)

    async def _main_event_loop(self) -> None:
        """Main event loop for processing triggers from the queue."""
        logger.info("Starting trigger-based event loop...")
        
        try:
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
                    
        except asyncio.CancelledError:
            logger.info("Main event loop cancelled.")
        finally:
            self.running = False
            logger.info("Processing hub event loop stopped")

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

        # Check rate limiting
        current_time = time.time()
        if not self.rate_limiter.can_process_cycle(current_time):
            rate_status = self.rate_limiter.get_rate_limit_status(current_time)
            logger.warning(f"Rate limit exceeded. Status: {rate_status}")
            return

        async with self._processing_lock:
            try:
                # Record the processing cycle start
                self.rate_limiter.record_cycle(current_time)
                
                # Log rate limit status
                self._log_rate_limit_status()
                
                # Dispatch to node-based processing
                if self.config.enable_node_based_processing:
                    await self._process_with_node_system(triggers)
                else:
                    logger.info("Node-based processing disabled, skipping trigger processing")
                    
            except Exception as e:
                logger.error(f"Error during trigger processing: {e}", exc_info=True)

    async def _process_with_node_system(self, triggers: Set[Trigger]):
        """Process triggers using the node-based system."""
        try:
            # Convert triggers to node processor format if needed
            trigger_data = []
            for trigger in triggers:
                trigger_data.append({
                    'type': trigger.type,
                    'priority': trigger.priority,
                    'data': trigger.data,
                    'timestamp': trigger.timestamp
                })
            
            # Execute node-based processing
            logger.info(f"Executing node-based processing for {len(trigger_data)} triggers")
            await self.node_processor.process_triggers(trigger_data)
            
        except Exception as e:
            logger.error(f"Error in node-based processing: {e}", exc_info=True)

    def get_status(self) -> Dict[str, Any]:
        """Get current processing hub status."""
        return {
            "running": self.running,
            "queue_size": self.trigger_queue.qsize(),
            "max_queue_size": self.config.max_queue_size,
            "processing_locked": self._processing_lock.locked(),
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
