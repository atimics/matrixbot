"""
Processing Hub

Central hub for state-driven processing. This replaces the complex trigger-based system
with a simple state-driven loop that processes when the world state becomes stale.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..world_state.manager import WorldStateManager
    from ..world_state.payload_builder import PayloadBuilder
    from .rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


@dataclass
class ProcessingConfig:
    """Configuration for the processing hub."""
    enable_node_based_processing: bool = True
    processing_interval: float = 5.0  # seconds - how often to check for stale state
    max_cycles_per_hour: int = 30
    rate_limit_window: int = 3600  # seconds
    max_queue_size: int = 1000


class ProcessingHub:
    """
    State-driven processing hub.
    
    Instead of complex trigger-based processing, this hub simply waits for the
    world state to become "stale" and then processes the current state holistically.
    """

    def __init__(
        self,
        world_state_manager: "WorldStateManager",
        payload_builder: "PayloadBuilder",
        rate_limiter: "RateLimiter",
        config: ProcessingConfig
    ):
        self.config = config
        self.world_state = world_state_manager
        self.payload_builder = payload_builder
        self.rate_limiter = rate_limiter
        
        # Processing state
        self.running = False
        self._processing_lock = asyncio.Lock()
        
        # State-driven architecture: simple event to signal when world state is stale
        self._world_state_is_stale = asyncio.Event()
        self.processing_interval = config.processing_interval
        
        # Component availability tracking
        self.node_processor = None
        
        # Processing statistics
        self.total_cycles_processed = 0
        self.processing_errors = 0
        self.last_cycle_time = None
        
    def set_node_processor(self, processor):
        """Set the node-based processing component."""
        self.node_processor = processor
        
    def start_processing_loop(self) -> Optional[asyncio.Task]:
        """Start the main processing loop as a background task."""
        if self.running:
            logger.warning("Processing hub already running")
            return None

        logger.debug("Starting state-driven processing hub...")
        self.running = True
        
        # Start the main processing loop as a background task
        logger.debug("Creating background task for main processing loop...")
        task = asyncio.create_task(self._main_processing_loop())
        logger.debug(f"Background task created successfully: {task}")
        
        # Mark state as stale for initial startup
        self.mark_state_as_stale("initial_startup")
        
        return task

    def stop_processing_loop(self):
        """Stop the processing loop."""
        self.running = False
        
    def mark_state_as_stale(self, reason: str, details: Optional[Dict] = None):
        """
        Mark the world state as stale, triggering a processing cycle.
        
        This is the primary interface for signaling that something has changed
        and the bot should re-evaluate the current state.
        
        Args:
            reason: Human-readable reason for the state change
            details: Optional additional details about the change
        """
        logger.debug(f"World state marked as stale: {reason}" + 
                    (f" (details: {details})" if details else ""))
        self._world_state_is_stale.set()

    async def _main_processing_loop(self) -> None:
        """
        Main state-driven processing loop.
        
        This loop waits for the world state to become stale, then processes
        the current state holistically. It also runs on a regular interval
        to ensure periodic processing even if no events occur.
        """
        try:
            logger.debug("Starting main state-driven processing loop...")
            
            while self.running:
                try:
                    # Wait for either:
                    # 1. World state to become stale (someone called mark_state_as_stale)
                    # 2. Processing interval timeout (periodic processing)
                    try:
                        await asyncio.wait_for(
                            self._world_state_is_stale.wait(), 
                            timeout=self.processing_interval
                        )
                    except asyncio.TimeoutError:
                        # Timeout is normal - just continue the loop for periodic processing
                        continue
                    except asyncio.CancelledError:
                        logger.debug("Main processing loop cancelled.")
                        break

                    # If processing is already locked, skip this cycle
                    if self._processing_lock.locked():
                        logger.debug("Processing already in progress, skipping cycle")
                        continue

                    # Execute a full processing cycle
                    async with self._processing_lock:
                        # Clear the stale flag before processing
                        self._world_state_is_stale.clear()
                        await self._execute_full_cycle()
                        
                except asyncio.CancelledError:
                    logger.debug("Main processing loop cancelled.")
                    break
                except Exception as e:
                    logger.error(f"Error in main processing loop: {e}", exc_info=True)
                    await asyncio.sleep(5)  # Cooldown on error
                    
        except asyncio.CancelledError:
            logger.debug("Main processing loop cancelled.")
        except Exception as e:
            logger.error(f"Fatal error in main processing loop: {e}", exc_info=True)
        finally:
            self.running = False
            logger.debug("Processing hub main loop stopped")

    async def _execute_full_cycle(self):
        """
        Execute a complete processing cycle.
        
        This method handles rate limiting and delegates to the node processor
        for the actual AI processing work.
        """
        # Check rate limiting
        current_time = time.time()
        if not self.rate_limiter.can_process_cycle(current_time):
            rate_status = self.rate_limiter.get_rate_limit_status(current_time)
            logger.warning(f"Rate limit exceeded, skipping cycle. Status: {rate_status}")
            return

        # Validate node processor is available
        if not self.node_processor:
            logger.warning("Node processor not available - cannot execute cycle")
            return

        try:
            # Record the processing cycle start
            self.rate_limiter.record_cycle(current_time)
            
            # Log rate limit status
            self._log_rate_limit_status()
            
            # Execute node-based processing with holistic evaluation
            if self.config.enable_node_based_processing:
                logger.debug("Executing full processing cycle (holistic state evaluation)")
                
                # Generate a unique cycle ID
                cycle_id = f"cycle_{int(current_time * 1000)}"
                
                # Call process_cycle with primary_channel_id=None to force holistic evaluation
                await self.node_processor.process_cycle(
                    cycle_id=cycle_id,
                    primary_channel_id=None,  # None = holistic evaluation of all channels
                    context={}  # Additional context can be added here if needed
                )
                
                # Update processing statistics
                self.total_cycles_processed += 1
                self.last_cycle_time = time.time()
                
                logger.debug(f"Processing cycle {cycle_id} completed successfully")
            else:
                logger.debug("Node-based processing disabled, skipping cycle")
                
        except Exception as e:
            logger.error(f"Error during processing cycle execution: {e}", exc_info=True)
            self.processing_errors += 1

    def get_status(self) -> Dict[str, Any]:
        """Get current processing hub status."""
        return {
            "running": self.running,
            "world_state_is_stale": self._world_state_is_stale.is_set(),
            "processing_locked": self._processing_lock.locked(),
            "total_cycles_processed": self.total_cycles_processed,
            "processing_errors": self.processing_errors,
            "last_cycle_time": self.last_cycle_time,
            "config": {
                "enable_node_based_processing": self.config.enable_node_based_processing,
                "processing_interval": self.processing_interval,
            }
        }

    def get_rate_limit_status(self) -> Dict[str, Any]:
        """Get current rate limiting status."""
        current_time = time.time()
        return self.rate_limiter.get_rate_limit_status(current_time)

    def get_processing_status(self) -> Dict[str, Any]:
        """
        Get the current processing status for API reporting.
        
        Returns:
            Dict containing processing hub status information
        """
        import datetime
        
        last_cycle_str = None
        if self.last_cycle_time:
            last_cycle_str = datetime.datetime.fromtimestamp(self.last_cycle_time).isoformat()
            
        return {
            "running": self.running,
            "last_cycle": last_cycle_str,
            "world_state_stale": self._world_state_is_stale.is_set(),
            "total_processed": self.total_cycles_processed,
            "errors": self.processing_errors,
            "locked": self._processing_lock.locked()
        }
        
    def _log_rate_limit_status(self):
        """Log current rate limiting status."""
        current_time = time.time()
        status = self.rate_limiter.get_rate_limit_status(current_time)
        logger.debug(f"Rate limit status: {status['cycles_per_hour']}/{status['max_cycles_per_hour']} cycles/hour")

    # Legacy methods for backward compatibility during transition
    # These will be removed in cleanup phase
    def add_trigger(self, trigger):
        """Legacy method - converts trigger to state change signal."""
        logger.warning(f"Legacy add_trigger called with {getattr(trigger, 'type', 'unknown')} - converting to mark_state_as_stale")
        reason = getattr(trigger, 'type', 'legacy_trigger')
        details = getattr(trigger, 'data', None)
        self.mark_state_as_stale(reason, details)

    def add_generic_trigger(self, trigger_type: str = "new_message", priority: int = 5):
        """Legacy method - converts to state change signal."""
        logger.warning(f"Legacy add_generic_trigger called with {trigger_type} - converting to mark_state_as_stale")
        self.mark_state_as_stale(trigger_type)
