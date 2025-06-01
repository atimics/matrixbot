"""
Enhanced Context-Aware Orchestrator with JSON Observer Support

Extends the existing orchestrator to support both traditional and node-based AI processing
for solving the 413 Payload Too Large problem through interactive exploration.
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional

from ..config import settings
from .json_observer_orchestrator import JsonObserverOrchestrator
from .orchestrator import ContextAwareOrchestrator, OrchestratorConfig

logger = logging.getLogger(__name__)


class EnhancedOrchestratorConfig(OrchestratorConfig):
    """Enhanced configuration that includes JSON Observer settings."""
    
    # JSON Observer specific settings
    enable_json_observer: bool = True
    use_node_based_processing: bool = True
    force_traditional_fallback: bool = False
    max_traditional_payload_size: int = 80000  # Bytes
    json_observer_model: str = "openai/gpt-4o-mini"
    
    def __init__(self, **kwargs):
        # Extract JSON Observer specific settings
        self.enable_json_observer = kwargs.pop('enable_json_observer', True)
        self.use_node_based_processing = kwargs.pop('use_node_based_processing', True)
        self.force_traditional_fallback = kwargs.pop('force_traditional_fallback', False)
        self.max_traditional_payload_size = kwargs.pop('max_traditional_payload_size', 80000)
        self.json_observer_model = kwargs.pop('json_observer_model', "openai/gpt-4o-mini")
        
        # Initialize parent with remaining kwargs
        super().__init__(**kwargs)


class EnhancedContextAwareOrchestrator(ContextAwareOrchestrator):
    """
    Enhanced orchestrator that supports both traditional and JSON Observer processing.
    
    This orchestrator can:
    1. Use traditional full WorldState dumps for small payloads
    2. Switch to JSON Observer node-based processing for large payloads
    3. Provide seamless integration between both approaches
    4. Fallback mechanisms for reliability
    """

    def __init__(self, config: Optional[EnhancedOrchestratorConfig] = None):
        self.enhanced_config = config or EnhancedOrchestratorConfig()
        
        # Initialize parent orchestrator
        super().__init__(self.enhanced_config)
        
        # Initialize JSON Observer orchestrator if enabled
        self.json_observer: Optional[JsonObserverOrchestrator] = None
        self.node_processing_enabled = False
        
        if self.enhanced_config.enable_json_observer:
            self._initialize_json_observer()
            
        # Track processing mode for this session
        self.current_processing_mode = "traditional"  # or "node_based"
        self.payload_size_history = []
        self.last_mode_switch_time = 0
        
        logger.info(f"Enhanced orchestrator initialized with JSON Observer: {self.enhanced_config.enable_json_observer}")

    def _initialize_json_observer(self):
        """Initialize the JSON Observer orchestrator."""
        try:
            self.json_observer = JsonObserverOrchestrator(
                world_state_manager=self.world_state,
                ai_engine=self.ai_engine,
                api_key=settings.OPENROUTER_API_KEY
            )
            
            # Register node interaction tools with the main tool registry
            self._register_node_tools()
            
            self.node_processing_enabled = True
            logger.info("JSON Observer orchestrator initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize JSON Observer orchestrator: {e}")
            self.json_observer = None
            self.node_processing_enabled = False

    def _register_node_tools(self):
        """Register node interaction tools with the main tool registry."""
        if not self.json_observer:
            return
            
        try:
            # Get node tools from JSON Observer
            node_tools = self.json_observer.get_node_tools()
            
            for tool in node_tools:
                self.tool_registry.register_tool(tool)
                logger.debug(f"Registered node tool: {tool.__class__.__name__}")
            
            # Update AI engine with new tools
            self.ai_engine.update_system_prompt_with_tools(self.tool_registry)
            
            logger.info(f"Registered {len(node_tools)} node interaction tools")
            
        except Exception as e:
            logger.error(f"Failed to register node tools: {e}")

    async def _process_world_state(self, active_channels: List[str]) -> None:
        """
        Enhanced world state processing that chooses between traditional and node-based processing.
        """
        try:
            # Determine processing mode based on configuration and conditions
            processing_mode = self._determine_processing_mode(active_channels)
            
            if processing_mode == "node_based" and self.node_processing_enabled:
                await self._process_with_json_observer(active_channels)
            else:
                await self._process_with_traditional_approach(active_channels)
                
        except Exception as e:
            logger.error(f"Error in enhanced world state processing: {e}")
            # Fallback to traditional processing
            if self.current_processing_mode != "traditional":
                logger.warning("Falling back to traditional processing")
                await self._process_with_traditional_approach(active_channels)

    def _determine_processing_mode(self, active_channels: List[str]) -> str:
        """
        Determine whether to use traditional or node-based processing.
        
        Returns: "traditional" or "node_based"
        """
        # Force traditional fallback if configured
        if self.enhanced_config.force_traditional_fallback:
            return "traditional"
        
        # Use traditional if JSON Observer is disabled
        if not self.enhanced_config.enable_json_observer or not self.node_processing_enabled:
            return "traditional"
        
        # Force node-based if explicitly configured
        if self.enhanced_config.use_node_based_processing:
            return "node_based"
        
        # Dynamic decision based on estimated payload size
        try:
            # Get a quick estimate of payload size without generating full payload
            estimated_size = self._estimate_payload_size(active_channels)
            
            # Track payload size history
            self.payload_size_history.append(estimated_size)
            if len(self.payload_size_history) > 10:
                self.payload_size_history.pop(0)
            
            # Use node-based if payload is likely to be too large
            if estimated_size > self.enhanced_config.max_traditional_payload_size:
                logger.info(f"Switching to node-based processing (estimated size: {estimated_size} bytes)")
                return "node_based"
            
            # Use traditional for smaller payloads
            logger.debug(f"Using traditional processing (estimated size: {estimated_size} bytes)")
            return "traditional"
            
        except Exception as e:
            logger.error(f"Error estimating payload size: {e}")
            # Default to traditional on estimation error
            return "traditional"

    def _estimate_payload_size(self, active_channels: List[str]) -> int:
        """
        Estimate the size of the AI payload without generating it.
        
        This is a quick heuristic based on world state metrics.
        """
        try:
            # Get world state metrics
            state_metrics = self.world_state.get_state_metrics()
            
            # Rough estimation formula based on observed patterns
            base_size = 2000  # Base system information
            
            # Channel data estimation
            channels_size = state_metrics.get('total_channels', 0) * 1500  # ~1.5KB per channel
            
            # Message data estimation
            total_messages = state_metrics.get('total_messages', 0)
            messages_size = min(total_messages * 800, 50000)  # Cap at 50KB for messages
            
            # User data estimation
            total_users = state_metrics.get('total_users', 0)
            users_size = min(total_users * 300, 20000)  # Cap at 20KB for users
            
            # System state estimation
            system_size = 3000  # System status, rate limits, etc.
            
            estimated_size = base_size + channels_size + messages_size + users_size + system_size
            
            logger.debug(f"Payload size estimation: base={base_size}, channels={channels_size}, "
                        f"messages={messages_size}, users={users_size}, system={system_size}, "
                        f"total={estimated_size}")
            
            return estimated_size
            
        except Exception as e:
            logger.error(f"Error in payload size estimation: {e}")
            # Conservative estimate that triggers node-based processing
            return self.enhanced_config.max_traditional_payload_size + 1000

    async def _process_with_traditional_approach(self, active_channels: List[str]) -> None:
        """Process using the traditional full WorldState approach."""
        self.current_processing_mode = "traditional"
        
        # Call parent's original processing method
        await super()._process_world_state(active_channels)
        
        logger.debug("Processed with traditional approach")

    async def _process_with_json_observer(self, active_channels: List[str]) -> None:
        """Process using the JSON Observer node-based approach."""
        self.current_processing_mode = "node_based"
        
        if not self.json_observer:
            logger.error("JSON Observer not available, falling back to traditional")
            await self._process_with_traditional_approach(active_channels)
            return
        
        try:
            # Determine primary channel
            primary_channel_id = None
            if active_channels:
                channel_activity = []
                for channel_id in active_channels:
                    channel_data = self.world_state.get_channel(channel_id)
                    if channel_data and channel_data.recent_messages:
                        last_msg_time = channel_data.recent_messages[-1].timestamp
                        channel_activity.append((channel_id, last_msg_time))

                if channel_activity:
                    channel_activity.sort(key=lambda x: x[1], reverse=True)
                    primary_channel_id = channel_activity[0][0]
            
            # Process with JSON Observer
            cycle_id = f"enhanced_cycle_{self.cycle_count}"
            
            # Execute JSON Observer processing cycle
            result = await self.json_observer.process_cycle(
                cycle_id=cycle_id,
                primary_channel_id=primary_channel_id,
                context={
                    "active_channels": active_channels,
                    "cycle_count": self.cycle_count,
                    "processing_mode": "node_based"
                }
            )
            
            if result.get("actions_executed", 0) > 0:
                logger.info(f"JSON Observer executed {result['actions_executed']} actions in cycle {self.cycle_count}")
            else:
                logger.debug(f"JSON Observer found no actions to execute in cycle {self.cycle_count}")
                
        except Exception as e:
            logger.error(f"Error in JSON Observer processing: {e}")
            # Fallback to traditional approach
            logger.warning("Falling back to traditional processing due to JSON Observer error")
            await self._process_with_traditional_approach(active_channels)

    async def get_processing_status(self) -> Dict[str, Any]:
        """Get comprehensive status of the enhanced orchestrator."""
        status = {
            "current_mode": self.current_processing_mode,
            "json_observer_enabled": self.enhanced_config.enable_json_observer,
            "node_processing_available": self.node_processing_enabled,
            "cycle_count": self.cycle_count,
            "payload_size_history": self.payload_size_history[-5:],  # Last 5 estimates
        }
        
        # Add JSON Observer status if available
        if self.json_observer:
            try:
                json_observer_status = await self.json_observer.get_status()
                status["json_observer_status"] = json_observer_status
            except Exception as e:
                status["json_observer_status"] = {"error": str(e)}
        
        # Add traditional orchestrator status
        status["rate_limits"] = self.get_rate_limit_status()
        
        return status

    async def force_processing_mode(self, mode: str) -> bool:
        """
        Force a specific processing mode for testing/debugging.
        
        Args:
            mode: "traditional" or "node_based"
            
        Returns:
            bool: True if mode was set successfully
        """
        if mode not in ["traditional", "node_based"]:
            logger.error(f"Invalid processing mode: {mode}")
            return False
        
        if mode == "node_based" and not self.node_processing_enabled:
            logger.error("Cannot force node-based mode: JSON Observer not available")
            return False
        
        # Update configuration
        if mode == "traditional":
            self.enhanced_config.force_traditional_fallback = True
            self.enhanced_config.use_node_based_processing = False
        else:
            self.enhanced_config.force_traditional_fallback = False
            self.enhanced_config.use_node_based_processing = True
        
        self.last_mode_switch_time = time.time()
        logger.info(f"Forced processing mode to: {mode}")
        return True

    async def reset_processing_mode(self):
        """Reset to automatic processing mode selection."""
        self.enhanced_config.force_traditional_fallback = False
        self.enhanced_config.use_node_based_processing = True  # Default preference
        self.last_mode_switch_time = time.time()
        logger.info("Reset to automatic processing mode selection")

    def get_enhanced_metrics(self) -> Dict[str, Any]:
        """Get enhanced metrics including both traditional and JSON Observer metrics."""
        metrics = {
            "orchestrator_type": "enhanced",
            "current_processing_mode": self.current_processing_mode,
            "node_processing_enabled": self.node_processing_enabled,
            "cycle_count": self.cycle_count,
            "payload_size_estimates": {
                "recent": self.payload_size_history[-5:] if self.payload_size_history else [],
                "average": sum(self.payload_size_history) / len(self.payload_size_history) if self.payload_size_history else 0,
                "max_threshold": self.enhanced_config.max_traditional_payload_size
            }
        }
        
        # Add JSON Observer metrics if available
        if self.json_observer:
            try:
                node_metrics = self.json_observer.get_metrics()
                metrics["node_manager"] = node_metrics
            except Exception as e:
                metrics["node_manager"] = {"error": str(e)}
        
        return metrics
