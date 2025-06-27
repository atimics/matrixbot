#!/usr/bin/env python3
"""
Performance Monitoring System

This module tracks key performance indicators for the AI engine and provides
monitoring capabilities as outlined in the engineering report.
"""

import logging
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from collections import deque, defaultdict
from datetime import datetime
import threading

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Container for performance metrics"""
    json_parse_success_rate: float = 0.0
    average_payload_size_kb: float = 0.0
    response_time_p95_ms: float = 0.0
    tool_execution_success_rate: float = 0.0
    ai_loop_detection_count: int = 0
    total_cycles: int = 0
    successful_cycles: int = 0
    error_recovery_usage: int = 0
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class CycleMetrics:
    """Metrics for a single AI decision cycle"""
    cycle_id: str
    timestamp: datetime
    payload_size_kb: float
    response_time_ms: float
    json_parse_success: bool
    selected_actions_count: int
    error_type: Optional[str] = None
    recovery_used: bool = False
    loop_detected: bool = False


class PerformanceMonitor:
    """Tracks and analyzes AI engine performance metrics."""
    
    def __init__(self, history_size: int = 1000):
        self.history_size = history_size
        self.cycle_history: deque = deque(maxlen=history_size)
        self.json_parse_attempts = deque(maxlen=history_size)
        self.response_times = deque(maxlen=history_size)
        self.tool_executions = defaultdict(lambda: {"success": 0, "failure": 0})
        
        # Counters
        self.total_cycles = 0
        self.successful_cycles = 0
        self.json_parse_successes = 0
        self.json_parse_failures = 0
        self.loop_detections = 0
        self.error_recoveries = 0
        
        # Thread safety
        self._lock = threading.Lock()
        
        logger.info("PerformanceMonitor: Initialized")
    
    def record_cycle_start(self, cycle_id: str, payload_size_kb: float) -> float:
        """
        Record the start of an AI decision cycle.
        
        Args:
            cycle_id: Unique identifier for the cycle
            payload_size_kb: Size of the payload in KB
            
        Returns:
            Start timestamp for measuring duration
        """
        with self._lock:
            self.total_cycles += 1
            return time.time()
    
    def record_cycle_complete(
        self, 
        cycle_id: str, 
        start_time: float, 
        payload_size_kb: float,
        json_parse_success: bool,
        selected_actions_count: int,
        error_type: Optional[str] = None,
        recovery_used: bool = False,
        loop_detected: bool = False
    ):
        """
        Record the completion of an AI decision cycle.
        
        Args:
            cycle_id: Unique identifier for the cycle
            start_time: Start timestamp from record_cycle_start
            payload_size_kb: Size of the payload in KB
            json_parse_success: Whether JSON parsing succeeded
            selected_actions_count: Number of actions selected
            error_type: Type of error if any occurred
            recovery_used: Whether error recovery was used
            loop_detected: Whether an infinite loop was detected
        """
        with self._lock:
            response_time_ms = (time.time() - start_time) * 1000
            
            # Create cycle metrics
            cycle_metrics = CycleMetrics(
                cycle_id=cycle_id,
                timestamp=datetime.now(),
                payload_size_kb=payload_size_kb,
                response_time_ms=response_time_ms,
                json_parse_success=json_parse_success,
                selected_actions_count=selected_actions_count,
                error_type=error_type,
                recovery_used=recovery_used,
                loop_detected=loop_detected
            )
            
            # Update collections
            self.cycle_history.append(cycle_metrics)
            self.response_times.append(response_time_ms)
            
            # Update counters
            if json_parse_success and not error_type:
                self.successful_cycles += 1
            
            if json_parse_success:
                self.json_parse_successes += 1
            else:
                self.json_parse_failures += 1
                
            if loop_detected:
                self.loop_detections += 1
                
            if recovery_used:
                self.error_recoveries += 1
            
            logger.debug(f"PerformanceMonitor: Recorded cycle {cycle_id} - "
                        f"Success: {json_parse_success}, Time: {response_time_ms:.1f}ms")
    
    def record_json_parse_attempt(self, success: bool, error_type: Optional[str] = None):
        """Record a JSON parsing attempt."""
        with self._lock:
            self.json_parse_attempts.append({
                "success": success,
                "timestamp": datetime.now(),
                "error_type": error_type
            })
    
    def record_tool_execution(self, tool_name: str, success: bool):
        """Record tool execution result."""
        with self._lock:
            if success:
                self.tool_executions[tool_name]["success"] += 1
            else:
                self.tool_executions[tool_name]["failure"] += 1
    
    def get_performance_snapshot(self) -> PerformanceMetrics:
        """
        Get current performance metrics snapshot.
        
        Returns:
            PerformanceMetrics with current statistics
        """
        with self._lock:
            # Calculate JSON parse success rate
            total_parse_attempts = self.json_parse_successes + self.json_parse_failures
            json_parse_rate = (
                self.json_parse_successes / total_parse_attempts 
                if total_parse_attempts > 0 else 0.0
            )
            
            # Calculate average payload size
            if self.cycle_history:
                avg_payload_size = sum(cycle.payload_size_kb for cycle in self.cycle_history) / len(self.cycle_history)
            else:
                avg_payload_size = 0.0
            
            # Calculate 95th percentile response time
            if self.response_times:
                sorted_times = sorted(self.response_times)
                p95_index = int(0.95 * len(sorted_times))
                response_time_p95 = sorted_times[p95_index] if p95_index < len(sorted_times) else sorted_times[-1]
            else:
                response_time_p95 = 0.0
            
            # Calculate tool execution success rate
            total_tool_successes = sum(data["success"] for data in self.tool_executions.values())
            total_tool_failures = sum(data["failure"] for data in self.tool_executions.values())
            total_tool_executions = total_tool_successes + total_tool_failures
            tool_success_rate = (
                total_tool_successes / total_tool_executions 
                if total_tool_executions > 0 else 0.0
            )
            
            return PerformanceMetrics(
                json_parse_success_rate=json_parse_rate,
                average_payload_size_kb=avg_payload_size,
                response_time_p95_ms=response_time_p95,
                tool_execution_success_rate=tool_success_rate,
                ai_loop_detection_count=self.loop_detections,
                total_cycles=self.total_cycles,
                successful_cycles=self.successful_cycles,
                error_recovery_usage=self.error_recoveries,
                timestamp=datetime.now()
            )
    
    def get_detailed_stats(self) -> Dict[str, Any]:
        """Get detailed performance statistics."""
        with self._lock:
            metrics = self.get_performance_snapshot()
            
            # Recent cycle stats (last 10 cycles)
            recent_cycles = list(self.cycle_history)[-10:]
            recent_errors = [cycle for cycle in recent_cycles if cycle.error_type]
            
            # Tool usage statistics
            tool_stats = {}
            for tool_name, data in self.tool_executions.items():
                total = data["success"] + data["failure"]
                success_rate = data["success"] / total if total > 0 else 0.0
                tool_stats[tool_name] = {
                    "total_executions": total,
                    "success_rate": success_rate,
                    "successes": data["success"],
                    "failures": data["failure"]
                }
            
            # Error type breakdown
            error_breakdown = defaultdict(int)
            for cycle in self.cycle_history:
                if cycle.error_type:
                    error_breakdown[cycle.error_type] += 1
            
            return {
                "overall_metrics": {
                    "json_parse_success_rate": metrics.json_parse_success_rate,
                    "average_payload_size_kb": metrics.average_payload_size_kb,
                    "response_time_p95_ms": metrics.response_time_p95_ms,
                    "tool_execution_success_rate": metrics.tool_execution_success_rate,
                    "loop_detection_count": metrics.ai_loop_detection_count,
                    "total_cycles": metrics.total_cycles,
                    "successful_cycles": metrics.successful_cycles,
                    "error_recovery_usage": metrics.error_recovery_usage
                },
                "recent_performance": {
                    "recent_cycles_count": len(recent_cycles),
                    "recent_errors_count": len(recent_errors),
                    "recent_error_rate": len(recent_errors) / len(recent_cycles) if recent_cycles else 0.0
                },
                "tool_statistics": tool_stats,
                "error_breakdown": dict(error_breakdown),
                "timestamp": metrics.timestamp.isoformat()
            }
    
    def get_health_status(self) -> Dict[str, Any]:
        """
        Get system health status based on performance metrics.
        
        Returns:
            Health status dict with overall status and issues
        """
        metrics = self.get_performance_snapshot()
        
        issues = []
        warning_level = "healthy"
        
        # Check JSON parse success rate
        if metrics.json_parse_success_rate < 0.90:
            issues.append(f"Low JSON parse success rate: {metrics.json_parse_success_rate:.1%}")
            warning_level = "degraded" if metrics.json_parse_success_rate > 0.70 else "critical"
        
        # Check response times
        if metrics.response_time_p95_ms > 10000:  # 10 seconds
            issues.append(f"High response times: {metrics.response_time_p95_ms:.0f}ms P95")
            warning_level = max(warning_level, "degraded", key=lambda x: ["healthy", "degraded", "critical"].index(x))
        
        # Check tool execution success rate
        if metrics.tool_execution_success_rate < 0.95:
            issues.append(f"Low tool success rate: {metrics.tool_execution_success_rate:.1%}")
            warning_level = max(warning_level, "degraded", key=lambda x: ["healthy", "degraded", "critical"].index(x))
        
        # Check for frequent loops
        if metrics.ai_loop_detection_count > metrics.total_cycles * 0.1:  # More than 10% of cycles
            issues.append(f"Frequent AI loops detected: {metrics.ai_loop_detection_count} in {metrics.total_cycles} cycles")
            warning_level = "critical"
        
        # Check payload sizes
        if metrics.average_payload_size_kb > 200:  # Large payloads
            issues.append(f"Large payload sizes: {metrics.average_payload_size_kb:.1f}KB average")
            warning_level = max(warning_level, "degraded", key=lambda x: ["healthy", "degraded", "critical"].index(x))
        
        return {
            "status": warning_level,
            "issues": issues,
            "metrics_summary": {
                "json_parse_rate": f"{metrics.json_parse_success_rate:.1%}",
                "response_time_p95": f"{metrics.response_time_p95_ms:.0f}ms",
                "tool_success_rate": f"{metrics.tool_execution_success_rate:.1%}",
                "total_cycles": metrics.total_cycles,
                "error_recoveries": metrics.error_recovery_usage
            },
            "timestamp": metrics.timestamp.isoformat()
        }
    
    def export_metrics_for_api(self) -> Dict[str, Any]:
        """Export metrics in format suitable for API responses."""
        return {
            "performance": self.get_performance_snapshot().__dict__,
            "health": self.get_health_status(),
            "detailed_stats": self.get_detailed_stats()
        }
    
    def reset_metrics(self):
        """Reset all metrics (useful for testing or manual resets)."""
        with self._lock:
            self.cycle_history.clear()
            self.json_parse_attempts.clear()
            self.response_times.clear()
            self.tool_executions.clear()
            
            self.total_cycles = 0
            self.successful_cycles = 0
            self.json_parse_successes = 0
            self.json_parse_failures = 0
            self.loop_detections = 0
            self.error_recoveries = 0
            
            logger.info("PerformanceMonitor: Metrics reset")


# Global performance monitor instance
performance_monitor = PerformanceMonitor()
