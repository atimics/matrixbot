"""
Processing Hub - Commander/Sub-Agent Coordination Center

Central hub for the new Commander/Sub-Agent architecture where the system:
1. Routes channels with active missions to Sub-Agents (MissionProcessor)
2. Routes complex analysis and delegation to the Commander AI (AdaptiveProcessor)
3. Coordinates multiple concurrent processing streams
4. Manages mission lifecycle and Sub-Agent coordination
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..world_state.manager import WorldStateManager
    from ..world_state.payload_builder import PayloadBuilder
    from .rate_limiter import RateLimiter
    from ..processors.adaptive_processor import AdaptiveProcessor
    from ..processors.mission_processor import MissionProcessor
    from ..lightweight_ai_engine import LightweightAIEngine
    from ...tools.registry import ToolRegistry
    from ...tools.base import ActionContext

logger = logging.getLogger(__name__)


@dataclass
class ProcessingConfig:
    """Configuration for the Commander/Sub-Agent processing system."""
    
    # Core processing settings
    observation_interval: float = 2.0
    max_cycles_per_hour: int = 300
    
    # Commander/Sub-Agent settings
    enable_sub_agent_processing: bool = True
    max_concurrent_missions: int = 10
    mission_timeout_hours: int = 24


class ProcessingHub:
    """
    Central coordination hub for the Commander/Sub-Agent architecture.
    
    This hub revolutionizes processing by:
    1. Identifying channels with active missions and routing them to Sub-Agents
    2. Routing remaining channels to the Commander AI for strategic analysis
    3. Coordinating concurrent processing streams
    4. Managing mission lifecycle and Sub-Agent health
    5. Providing unified metrics and monitoring
    
    The new architecture eliminates the binary traditional/node-based choice,
    replacing it with intelligent per-channel routing.
    """
    
    def __init__(
        self,
        world_state_manager: "WorldStateManager",
        payload_builder: "PayloadBuilder", 
        rate_limiter: "RateLimiter",
        config: Optional[ProcessingConfig] = None,
        tool_registry: Optional["ToolRegistry"] = None,
        action_context: Optional["ActionContext"] = None
    ):
        self.world_state = world_state_manager
        self.payload_builder = payload_builder
        self.rate_limiter = rate_limiter
        self.config = config or ProcessingConfig()
        self.tool_registry = tool_registry
        self.action_context = action_context
        
        # Processing state
        self.running = False
        self.cycle_count = 0
        self.last_cycle_time = 0
        
        # Event coordination
        self.state_changed_event = asyncio.Event()
        
        # Commander/Sub-Agent components
        self.commander_processor: Optional["AdaptiveProcessor"] = None
        self.lightweight_ai_engine: Optional["LightweightAIEngine"] = None
        
        # Mission and Sub-Agent tracking
        self.active_sub_agents: Dict[str, "MissionProcessor"] = {}  # mission_id -> processor
        self.sub_agent_performance: Dict[str, Dict[str, Any]] = {}  # mission_id -> metrics
        
        # Processing metrics
        self.processing_metrics: List[Dict[str, Any]] = []
        
        logger.info("ProcessingHub initialized with Commander/Sub-Agent architecture")
        
    def set_commander_processor(self, processor: "AdaptiveProcessor"):
        """Set the Commander AI processor."""
        self.commander_processor = processor
        logger.info("Commander AI processor configured")
        
    def set_lightweight_ai_engine(self, engine: "LightweightAIEngine"):
        """Set the lightweight AI engine for Sub-Agents."""
        self.lightweight_ai_engine = engine
        logger.info("Lightweight AI engine configured")

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
        
    def trigger_state_change(self):
        """Trigger immediate processing when world state changes."""
        if self.state_changed_event and not self.state_changed_event.is_set():
            self.state_changed_event.set()
            logger.debug("State change event triggered")

    async def _main_event_loop(self) -> None:
        """Main event loop for processing world state changes."""
        logger.info("Starting main event loop...")
        last_state_hash = None

        while self.running:
            try:
                # Wait for state change event or timeout
                try:
                    await asyncio.wait_for(
                        self.state_changed_event.wait(),
                        timeout=self.config.observation_interval,
                    )
                    self.state_changed_event.clear()
                    logger.info("State change event triggered")
                except asyncio.TimeoutError:
                    # Periodic check even if no events
                    pass

                cycle_start = time.time()

                # Check rate limiting
                can_process, wait_time = self.rate_limiter.can_process_cycle(cycle_start)

                if not can_process:
                    if wait_time > 0:
                        logger.debug(f"Rate limiting: waiting {wait_time:.2f}s before next cycle")
                        await asyncio.sleep(min(wait_time, self.config.observation_interval))
                    continue

                # Record the cycle for rate limiting
                self.rate_limiter.record_cycle(cycle_start)

                # Get current world state
                current_state = self.world_state.to_dict()
                current_hash = self._hash_state(current_state)

                # Check if state has changed
                if current_hash != last_state_hash:
                    logger.info(f"World state changed, processing cycle {self.cycle_count}")

                    # Get active channels to determine primary focus
                    active_channels = self._get_active_channels(current_state)

                    # Process using Commander/Sub-Agent strategy
                    await self._process_world_state(active_channels)

                    # Update tracking
                    last_state_hash = current_hash
                    self.cycle_count += 1
                    self.last_cycle_time = cycle_start

                    cycle_duration = time.time() - cycle_start
                    logger.info(f"Cycle {self.cycle_count} completed in {cycle_duration:.2f}s")

                    # Log rate limiting status every 10 cycles for monitoring
                    if self.cycle_count % 10 == 0:
                        self._log_rate_limit_status()

            except Exception as e:
                logger.error(f"Error in event loop cycle {self.cycle_count}: {e}")
                await asyncio.sleep(5)

    async def _process_world_state(self, active_channels: List[str]) -> None:
        """
        Process world state using the Commander/Sub-Agent architecture.
        
        This method:
        1. Routes channels with active missions to Sub-Agents
        2. Routes strategic analysis to the Commander AI
        3. Manages concurrent processing streams
        4. Handles mission lifecycle and Sub-Agent coordination
        """
        try:
            # P0 FEATURE: Detect proactive opportunities at the beginning of each cycle
            await self._detect_proactive_opportunities()
            
            # Get mission-assigned channels and non-mission channels
            mission_channels, strategic_channels = await self._categorize_channels(active_channels)
            
            # Process concurrently
            tasks = []
            
            # 1. Process channels with active missions via Sub-Agents
            if mission_channels:
                tasks.append(self._process_mission_channels(mission_channels))
            
            # 2. Process strategic analysis and mission delegation via Commander
            if strategic_channels or not mission_channels:  # Always run Commander if no missions active
                tasks.append(self._process_strategic_channels(strategic_channels))
                
            # 3. Execute all processing streams concurrently
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
                
            # 4. Clean up completed missions and Sub-Agents
            await self._cleanup_completed_missions()
                
        except Exception as e:
            logger.error(f"Error in Commander/Sub-Agent processing: {e}")
            # Fallback: ensure Commander AI can handle critical situations
            if self.commander_processor:
                logger.warning("Falling back to Commander-only processing")
                await self._emergency_commander_processing(active_channels)

    async def _categorize_channels(self, active_channels: List[str]) -> tuple[List[str], List[str]]:
        """
        Categorize channels into mission-assigned vs strategic analysis.
        
        Returns:
            (mission_channels, strategic_channels)
        """
        mission_channels = []
        strategic_channels = []
        
        for channel_id in active_channels:
            channel_data = self.world_state.get_channel(channel_id)
            if channel_data and hasattr(channel_data, 'current_mission_id') and getattr(channel_data, 'current_mission_id', None):
                # Channel has an active mission - route to Sub-Agent
                mission_channels.append(channel_id)
            else:
                # Channel needs strategic analysis - route to Commander
                strategic_channels.append(channel_id)
        
        logger.debug(f"Categorized {len(mission_channels)} mission channels, {len(strategic_channels)} strategic channels")
        return mission_channels, strategic_channels

    async def _process_mission_channels(self, mission_channels: List[str]) -> None:
        """Process channels with active missions using Sub-Agents."""
        processing_tasks = []
        
        for channel_id in mission_channels:
            channel_data = self.world_state.get_channel(channel_id)
            if not channel_data or not hasattr(channel_data, 'current_mission_id'):
                continue
                
            mission_id = getattr(channel_data, 'current_mission_id', None)
            if not mission_id:
                continue
                
            # Get or create Sub-Agent for this mission
            sub_agent = await self._get_or_create_sub_agent(mission_id, channel_id)
            
            if sub_agent:
                # Process this mission-channel pair
                task = self._process_single_mission(sub_agent, mission_id, channel_id)
                processing_tasks.append(task)
        
        # Execute all Sub-Agent tasks concurrently
        if processing_tasks:
            results = await asyncio.gather(*processing_tasks, return_exceptions=True)
            
            # Log results and update performance metrics
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Sub-Agent task {i} failed: {result}")
                else:
                    logger.debug(f"Sub-Agent task {i} completed successfully")

    async def _process_strategic_channels(self, strategic_channels: List[str]) -> None:
        """Process strategic analysis and mission delegation via Commander AI."""
        if not self.commander_processor:
            logger.warning("Commander processor not available for strategic processing")
            return
            
        try:
            # Create comprehensive context for strategic analysis
            strategic_context = {
                "active_channels": strategic_channels,
                "active_missions": list(self.active_sub_agents.keys()),
                "sub_agent_performance": self.sub_agent_performance,
                "world_state_summary": self._get_world_state_summary(),
                "system_capacity": self._get_system_capacity_info()
            }
            
            # Commander AI processes strategic concerns and mission delegation
            result = await self.commander_processor.process_cycle(
                cycle_id=f"strategic_{int(time.time())}",
                primary_channel_id=strategic_channels[0] if strategic_channels else None,
                context=strategic_context
            )
            
            if result and len(result) > 0:
                # Look for mission assignment actions in the result
                mission_actions = [action for action in result if hasattr(action, 'action_type') and getattr(action, 'action_type') == 'assign_mission']
                if mission_actions:
                    logger.info(f"Commander assigned {len(mission_actions)} new missions")
                
        except Exception as e:
            logger.error(f"Error in strategic processing: {e}")

    async def _get_or_create_sub_agent(self, mission_id: str, channel_id: str) -> Optional["MissionProcessor"]:
        """Get existing or create new Sub-Agent for a mission."""
        if mission_id in self.active_sub_agents:
            return self.active_sub_agents[mission_id]
            
        # Create new Sub-Agent
        if not self.lightweight_ai_engine:
            logger.error("Lightweight AI engine not available for Sub-Agent creation")
            return None
            
        if not self.tool_registry:
            logger.error("Tool registry not available for Sub-Agent creation")
            return None
            
        try:
            from ..processors.mission_processor import MissionProcessor
            
            # Get mission data
            world_state_data = self.world_state.get_state_data()
            mission_data = world_state_data.missions.get(mission_id) if world_state_data.missions else None
            
            if not mission_data:
                logger.error(f"Mission {mission_id} not found in world state")
                return None
            
            sub_agent = MissionProcessor(
                mission=mission_data,
                lightweight_ai_engine=self.lightweight_ai_engine,
                world_state_data=world_state_data,
                tool_registry=self.tool_registry,
                action_context=self.action_context
            )
            
            self.active_sub_agents[mission_id] = sub_agent
            self.sub_agent_performance[mission_id] = {
                "created_at": time.time(),
                "tasks_completed": 0,
                "errors": 0,
                "channel_id": channel_id
            }
            
            logger.info(f"Created new Sub-Agent for mission {mission_id}")
            return sub_agent
            
        except Exception as e:
            logger.error(f"Failed to create Sub-Agent for mission {mission_id}: {e}")
            return None

    async def _process_single_mission(self, sub_agent: "MissionProcessor", mission_id: str, channel_id: str) -> None:
        """Process a single mission with its Sub-Agent."""
        try:
            start_time = time.time()
            
            # Get channel data for this mission
            channel_data = self.world_state.get_channel(channel_id)
            if not channel_data:
                logger.warning(f"Channel {channel_id} data not available for mission {mission_id}")
                return
                
            # Process the mission
            result = await sub_agent.process_cycle(
                cycle_id=f"mission_{mission_id}_{int(time.time())}",
                primary_channel_id=channel_id,
                context={"channel_data": channel_data}
            )
            
            # Update performance metrics
            duration = time.time() - start_time
            performance = self.sub_agent_performance.get(mission_id, {})
            performance["tasks_completed"] = performance.get("tasks_completed", 0) + 1
            performance["last_execution_duration"] = duration
            
            # Handle result properly - MissionProcessor returns List[ActionPlan], not dict
            if isinstance(result, list):
                # Success if we got results without exceptions
                if result:
                    logger.debug(f"Mission {mission_id} Sub-Agent completed {len(result)} actions successfully")
                else:
                    logger.debug(f"Mission {mission_id} Sub-Agent cycle completed with no actions")
            elif isinstance(result, dict) and result.get("status") == "success":
                logger.debug(f"Mission {mission_id} Sub-Agent completed task successfully")
            elif isinstance(result, dict):
                logger.warning(f"Mission {mission_id} Sub-Agent reported issues: {result.get('error', 'unknown')}")
                performance["errors"] = performance.get("errors", 0) + 1
            else:
                logger.warning(f"Mission {mission_id} Sub-Agent returned unexpected result type: {type(result)}")
                performance["errors"] = performance.get("errors", 0) + 1
                
            self.sub_agent_performance[mission_id] = performance
            
        except Exception as e:
            logger.error(f"Error processing mission {mission_id}: {e}")
            # Update error count
            performance = self.sub_agent_performance.get(mission_id, {})
            performance["errors"] = performance.get("errors", 0) + 1
            self.sub_agent_performance[mission_id] = performance

    async def _detect_proactive_opportunities(self) -> None:
        """Detect proactive engagement opportunities at the start of each cycle.""" 
        try:
            # Check if proactive engine is available via the dynamic attribute pattern
            if (hasattr(self.world_state, 'proactive_engine') and 
                getattr(self.world_state, 'proactive_engine', None)):
                
                # Trigger opportunity detection based on current world state
                proactive_engine = getattr(self.world_state, 'proactive_engine')
                await proactive_engine.on_world_state_change()
                logger.debug("Proactive opportunity detection completed")
            else:
                logger.debug("Proactive engine not available for opportunity detection")
                
        except Exception as e:
            logger.warning(f"Error detecting proactive opportunities: {e}")
            # Don't let proactive detection failures block normal processing

    async def _cleanup_completed_missions(self) -> None:
        """Clean up completed or timed-out missions and their Sub-Agents."""
        current_time = time.time()
        missions_to_remove = []
        
        for mission_id, sub_agent in self.active_sub_agents.items():
            performance = self.sub_agent_performance.get(mission_id, {})
            created_at = performance.get("created_at", current_time)
            
            # Check if mission has timed out
            if (current_time - created_at) > (self.config.mission_timeout_hours * 3600):
                logger.info(f"Mission {mission_id} timed out, removing Sub-Agent")
                missions_to_remove.append(mission_id)
                continue
                
            # Check if mission is marked as completed in world state
            world_state_data = self.world_state.get_state_data()
            mission_data = world_state_data.missions.get(mission_id) if world_state_data.missions else None
            
            if mission_data and hasattr(mission_data, 'status') and getattr(mission_data, 'status') == 'completed':
                logger.info(f"Mission {mission_id} completed, removing Sub-Agent")
                missions_to_remove.append(mission_id)
        
        # Remove completed/timed-out missions
        for mission_id in missions_to_remove:
            if mission_id in self.active_sub_agents:
                del self.active_sub_agents[mission_id]
            if mission_id in self.sub_agent_performance:
                del self.sub_agent_performance[mission_id]

    async def _emergency_commander_processing(self, active_channels: List[str]) -> None:
        """Emergency fallback: Commander-only processing for critical situations."""
        if not self.commander_processor:
            logger.error("Emergency processing failed: Commander processor not available")
            return
            
        try:
            logger.warning("Executing emergency Commander-only processing")
            await self.commander_processor.process_cycle(
                cycle_id=f"emergency_{int(time.time())}",
                primary_channel_id=active_channels[0] if active_channels else None,
                context={"emergency_mode": True, "active_channels": active_channels}
            )
        except Exception as e:
            logger.error(f"Emergency processing failed: {e}")

    def _get_primary_channel(self, active_channels: List[str]) -> Optional[str]:
        """Get the primary (most recently active) channel."""
        if not active_channels:
            return None
            
        # Sort by recent activity to get most active channel as primary
        channel_activity = []
        for channel_id in active_channels:
            channel_data = self.world_state.get_channel(channel_id)
            if channel_data and channel_data.recent_messages:
                last_msg_time = channel_data.recent_messages[-1].timestamp
                channel_activity.append((channel_id, last_msg_time))

        if channel_activity:
            # Primary channel is the one with most recent activity
            channel_activity.sort(key=lambda x: x[1], reverse=True)
            return channel_activity[0][0]
            
        return None

    def _get_active_channels(self, world_state_dict: Dict[str, Any]) -> List[str]:
        """Extract active channels from world state."""
        active_channels = []
        
        channels = world_state_dict.get("channels", {})
        current_time = time.time()
        
        for channel_id, channel_data in channels.items():
            # Consider channels with recent activity (last hour)
            recent_messages = channel_data.get("recent_messages", [])
            if recent_messages:
                last_message_time = recent_messages[-1].get("timestamp", 0)
                if current_time - last_message_time < 3600:  # 1 hour
                    active_channels.append(channel_id)
        
        return active_channels

    def _get_world_state_summary(self) -> Dict[str, Any]:
        """Get a summary of the current world state for strategic analysis."""
        return {
            "total_channels": len(self.world_state.get_state_data().channels),
            "active_missions": len(self.active_sub_agents),
            "system_uptime": time.time() - (self.last_cycle_time or time.time()),
            "cycle_count": self.cycle_count
        }
        
    def _get_system_capacity_info(self) -> Dict[str, Any]:
        """Get information about current system capacity and performance."""
        return {
            "max_concurrent_missions": self.config.max_concurrent_missions,
            "current_active_missions": len(self.active_sub_agents),
            "mission_capacity_used": len(self.active_sub_agents) / self.config.max_concurrent_missions,
            "recent_performance": self.processing_metrics[-5:] if self.processing_metrics else []
        }

    def _hash_state(self, state_dict: Dict[str, Any]) -> str:
        """Generate a hash of the world state for change detection."""
        import hashlib
        import json
        
        # Create a deterministic representation
        state_str = json.dumps(state_dict, sort_keys=True, default=str)
        return hashlib.md5(state_str.encode()).hexdigest()

    def _log_rate_limit_status(self):
        """Log current rate limiting status."""
        try:
            current_time = time.time()
            status = self.rate_limiter.get_rate_limit_status(current_time)
            logger.info(f"Rate limit status: {status['cycles_per_hour']}/{status['max_cycles_per_hour']} cycles/hour")
        except Exception as e:
            logger.error(f"Error logging rate limit status: {e}")

    def get_processing_status(self) -> Dict[str, Any]:
        """Get comprehensive processing status for the Commander/Sub-Agent architecture."""
        return {
            "running": self.running,
            "processing_mode": "commander_sub_agent",
            "cycle_count": self.cycle_count,
            "last_cycle_time": self.last_cycle_time,
            "commander_available": self.commander_processor is not None,
            "lightweight_ai_available": self.lightweight_ai_engine is not None,
            "active_missions": len(self.active_sub_agents),
            "mission_capacity_used": len(self.active_sub_agents) / self.config.max_concurrent_missions,
            "sub_agent_performance": {
                mission_id: {
                    "tasks_completed": perf.get("tasks_completed", 0),
                    "errors": perf.get("errors", 0),
                    "uptime_hours": (time.time() - perf.get("created_at", time.time())) / 3600
                } for mission_id, perf in self.sub_agent_performance.items()
            },
            "config": {
                "enable_sub_agent_processing": self.config.enable_sub_agent_processing,
                "max_concurrent_missions": self.config.max_concurrent_missions,
                "mission_timeout_hours": self.config.mission_timeout_hours,
                "observation_interval": self.config.observation_interval,
            }
        }

    def get_rate_limit_status(self) -> Dict[str, Any]:
        """Get current rate limiting status."""
        current_time = time.time()
        return self.rate_limiter.get_rate_limit_status(current_time)
