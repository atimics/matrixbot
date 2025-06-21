"""
ActionExecutor - Centralized Tool Execution

This module provides centralized execution logic for all tools in the system,
implementing consistent error handling, logging, and state management.
"""
import logging
import time
import traceback
import hashlib
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

# Try to import HistoryRecorder, but make it optional since it doesn't exist yet
try:
    from ..history_recorder import HistoryRecorder
except ImportError:
    HistoryRecorder = None

from ...tools.base import ActionContext
from ...tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


@dataclass
class CircuitBreakerConfig:
    """Configuration for the circuit breaker pattern."""
    failure_threshold: int = 3  # Number of failures before tripping
    time_window_seconds: int = 300  # 5 minutes
    reset_timeout_seconds: int = 600  # 10 minutes before attempting reset


class CircuitBreakerTracker:
    """
    Tracks tool failures and implements circuit breaker pattern.
    
    For each combination of (tool_name, parameters_hash), tracks recent failures.
    If failures exceed threshold within time window, the circuit "trips" and 
    temporarily blocks that specific tool+params combination.
    """
    
    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        # Format: {(tool_name, params_hash): deque of failure timestamps}
        self.failure_history = defaultdict(deque)
        # Format: {(tool_name, params_hash): trip_timestamp}
        self.tripped_circuits = {}
    
    def _get_params_hash(self, parameters: Dict[str, Any]) -> str:
        """Generate a hash for parameters to create a unique key."""
        # Sort parameters to ensure consistent hashing
        sorted_params = str(sorted(parameters.items()))
        return hashlib.md5(sorted_params.encode()).hexdigest()[:8]
    
    def should_allow_execution(self, tool_name: str, parameters: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Check if a tool execution should be allowed.
        
        Returns:
            (should_allow, reason_if_blocked)
        """
        params_hash = self._get_params_hash(parameters)
        circuit_key = (tool_name, params_hash)
        current_time = time.time()
        
        # Check if circuit is currently tripped
        if circuit_key in self.tripped_circuits:
            trip_time = self.tripped_circuits[circuit_key]
            
            # Check if enough time has passed to reset
            if current_time - trip_time > self.config.reset_timeout_seconds:
                logger.debug(f"Circuit breaker reset for {tool_name} with params hash {params_hash}")
                del self.tripped_circuits[circuit_key]
                # Clear old failure history
                if circuit_key in self.failure_history:
                    self.failure_history[circuit_key].clear()
            else:
                remaining_time = self.config.reset_timeout_seconds - (current_time - trip_time)
                reason = f"Circuit breaker tripped for {tool_name}. Reset in {remaining_time:.0f}s"
                return False, reason
        
        return True, None
    
    def record_failure(self, tool_name: str, parameters: Dict[str, Any]) -> bool:
        """
        Record a failure for the given tool and parameters.
        
        Returns:
            True if this failure caused the circuit to trip
        """
        params_hash = self._get_params_hash(parameters)
        circuit_key = (tool_name, params_hash)
        current_time = time.time()
        
        # Add this failure to history
        failure_queue = self.failure_history[circuit_key]
        failure_queue.append(current_time)
        
        # Remove failures outside the time window
        cutoff_time = current_time - self.config.time_window_seconds
        while failure_queue and failure_queue[0] < cutoff_time:
            failure_queue.popleft()
        
        # Check if we should trip the circuit
        if len(failure_queue) >= self.config.failure_threshold:
            self.tripped_circuits[circuit_key] = current_time
            logger.warning(
                f"Circuit breaker TRIPPED for {tool_name} with params hash {params_hash}. "
                f"{len(failure_queue)} failures in {self.config.time_window_seconds}s"
            )
            return True
        
        return False
    
    def get_circuit_status(self) -> Dict[str, Any]:
        """Get current status of all circuits for monitoring."""
        current_time = time.time()
        
        active_circuits = {}
        for (tool_name, params_hash), trip_time in self.tripped_circuits.items():
            remaining_time = self.config.reset_timeout_seconds - (current_time - trip_time)
            active_circuits[f"{tool_name}:{params_hash}"] = {
                "tripped_at": trip_time,
                "reset_in_seconds": max(0, remaining_time)
            }
        
        failure_counts = {}
        for (tool_name, params_hash), failures in self.failure_history.items():
            if failures:  # Only include tools with recent failures
                failure_counts[f"{tool_name}:{params_hash}"] = len(failures)
        
        return {
            "tripped_circuits": active_circuits,
            "recent_failure_counts": failure_counts,
            "config": {
                "failure_threshold": self.config.failure_threshold,
                "time_window_seconds": self.config.time_window_seconds,
                "reset_timeout_seconds": self.config.reset_timeout_seconds
            }
        }


class ActionPlan:
    """
    Represents a planned action with its tool name and parameters.
    """
    
    def __init__(self, tool_name: str, parameters: Dict[str, Any], action_id: Optional[str] = None):
        self.tool_name = tool_name
        self.parameters = parameters
        self.action_id = action_id or f"action_{int(time.time() * 1000)}"
        self.timestamp = time.time()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "tool_name": self.tool_name,
            "parameters": self.parameters,
            "timestamp": self.timestamp
        }


class ActionExecutor:
    """
    Centralized executor for all tool actions in the system.
    
    This class provides:
    - Unified tool execution workflow
    - Consistent error handling and logging
    - Integration with HistoryRecorder
    - Parameter validation
    - Execution metrics and timing
    - Circuit breaker pattern for failure prevention
    """
    
    def __init__(self, tool_registry: ToolRegistry, history_recorder = None):
        self.tool_registry = tool_registry
        self.history_recorder = history_recorder
        self._execution_count = 0
        self._total_execution_time = 0.0
        
        # Initialize circuit breaker
        self.circuit_breaker = CircuitBreakerTracker(CircuitBreakerConfig())
    
    async def execute_action(self, action_plan: ActionPlan, context: ActionContext) -> Dict[str, Any]:
        """
        Execute a single action using the appropriate tool.
        
        Args:
            action_plan: The action to execute
            context: ActionContext providing access to services and state
            
        Returns:
            Dictionary containing execution result with:
            - status: "success", "failure", or "skipped"  
            - message/error: Description of result
            - timestamp: Execution timestamp
            - execution_time: Time taken to execute
            - Additional tool-specific data
        """
        execution_start = time.time()
        self._execution_count += 1
        
        try:
            logger.debug(f"Executing action {action_plan.action_id}: {action_plan.tool_name} with params: {action_plan.parameters}")
            
            # Get the tool from registry
            tool = self.tool_registry.get_tool(action_plan.tool_name)
            if not tool:
                error_msg = f"Tool '{action_plan.tool_name}' not found in registry"
                logger.error(error_msg)
                return self._create_failure_result(error_msg, action_plan, execution_start)
            
            # Validate parameters against tool schema
            validation_result = self._validate_parameters(tool, action_plan.parameters)
            if not validation_result["valid"]:
                error_msg = f"Parameter validation failed for tool '{action_plan.tool_name}': {validation_result['error']}"
                logger.error(error_msg)
                return self._create_failure_result(error_msg, action_plan, execution_start)
            
            # Check circuit breaker before executing
            allowed, reason = self.circuit_breaker.should_allow_execution(action_plan.tool_name, action_plan.parameters)
            if not allowed:
                return self._create_failure_result(reason, action_plan, execution_start)
            
            # Execute the tool
            try:
                result = await tool.execute(action_plan.parameters, context)
                execution_time = time.time() - execution_start
                self._total_execution_time += execution_time
                
                # Ensure result has required fields
                if not isinstance(result, dict):
                    logger.warning(f"Tool {action_plan.tool_name} returned non-dict result: {result}")
                    result = {"status": "success", "result": result}
                
                # Add execution metadata
                result.update({
                    "action_id": action_plan.action_id,
                    "tool_name": action_plan.tool_name,
                    "execution_time": execution_time,
                    "timestamp": result.get("timestamp", time.time())
                })
                
                # Record in history if available
                if self.history_recorder:
                    await self._record_action_history(action_plan, result)
                
                logger.debug(f"Action {action_plan.action_id} completed with status: {result.get('status', 'unknown')}")
                return result
                
            except Exception as tool_error:
                execution_time = time.time() - execution_start
                error_msg = f"Tool '{action_plan.tool_name}' execution failed: {str(tool_error)}"
                logger.exception(f"Tool execution error for {action_plan.action_id}: {error_msg}")
                
                # Record failure in circuit breaker
                self.circuit_breaker.record_failure(action_plan.tool_name, action_plan.parameters)
                
                return self._create_failure_result(
                    error_msg, 
                    action_plan, 
                    execution_start,
                    exception_details=traceback.format_exc()
                )
                
        except Exception as executor_error:
            execution_time = time.time() - execution_start
            error_msg = f"ActionExecutor internal error: {str(executor_error)}"
            logger.exception(f"Executor error for {action_plan.action_id}: {error_msg}")
            
            return self._create_failure_result(
                error_msg, 
                action_plan, 
                execution_start,
                exception_details=traceback.format_exc()
            )
    
    def _validate_parameters(self, tool, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate tool parameters against the tool's schema.
        
        Args:
            tool: The tool instance
            parameters: Parameters to validate
            
        Returns:
            Dict with 'valid' boolean and optional 'error' message
        """
        try:
            schema = tool.parameters_schema
            
            # Basic validation - check required parameters
            if isinstance(schema, dict) and "required" in schema:
                required_params = schema["required"]
                missing_params = [param for param in required_params if param not in parameters]
                if missing_params:
                    return {
                        "valid": False,
                        "error": f"Missing required parameters: {', '.join(missing_params)}"
                    }
            
            # TODO: Add more sophisticated JSON schema validation if needed
            return {"valid": True}
            
        except Exception as e:
            logger.warning(f"Parameter validation error for tool {tool.name}: {e}")
            return {"valid": True}  # Be permissive if validation fails
    
    def _create_failure_result(
        self, 
        error_msg: str, 
        action_plan: ActionPlan, 
        execution_start: float,
        exception_details: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a standardized failure result dictionary."""
        execution_time = time.time() - execution_start
        self._total_execution_time += execution_time
        
        result = {
            "status": "failure",
            "error": error_msg,
            "action_id": action_plan.action_id,
            "tool_name": action_plan.tool_name,
            "execution_time": execution_time,
            "timestamp": time.time()
        }
        
        if exception_details:
            result["exception_details"] = exception_details
        
        return result
    
    async def _record_action_history(self, action_plan: ActionPlan, result: Dict[str, Any]):
        """Record the action execution in the history recorder."""
        try:
            if self.history_recorder:
                await self.history_recorder.record_action(
                    action_id=action_plan.action_id,
                    tool_name=action_plan.tool_name,
                    parameters=action_plan.parameters,
                    result=result,
                    timestamp=action_plan.timestamp
                )
        except Exception as e:
            logger.warning(f"Failed to record action history for {action_plan.action_id}: {e}")
    
    def get_execution_stats(self) -> Dict[str, Any]:
        """Get execution statistics for monitoring and debugging."""
        avg_execution_time = self._total_execution_time / self._execution_count if self._execution_count > 0 else 0
        
        return {
            "total_executions": self._execution_count,
            "total_execution_time": self._total_execution_time,
            "average_execution_time": avg_execution_time,
            "available_tools": list(self.tool_registry.get_all_tool_names()),
            "circuit_breaker_status": self.circuit_breaker.get_circuit_status()
        }
