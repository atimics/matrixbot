"""
Performance Monitoring System

Comprehensive performance monitoring, metrics collection, and analysis
for the chatbot system.
"""

import asyncio
import logging
import time
import psutil
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, field
from collections import defaultdict, deque
import json
import statistics

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetric:
    """Individual performance metric data point."""
    metric_name: str
    value: float
    timestamp: datetime
    component: str
    operation: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ComponentStats:
    """Performance statistics for a component."""
    component_name: str
    total_operations: int = 0
    total_execution_time: float = 0.0
    avg_execution_time: float = 0.0
    min_execution_time: float = float('inf')
    max_execution_time: float = 0.0
    error_count: int = 0
    success_rate: float = 1.0
    last_updated: datetime = field(default_factory=datetime.now)


class PerformanceMonitor:
    """Centralized performance monitoring and metrics collection."""
    
    def __init__(self, retention_hours: int = 24):
        self.retention_hours = retention_hours
        self.metrics: List[PerformanceMetric] = []
        self.component_stats: Dict[str, ComponentStats] = {}
        self.running_operations: Dict[str, float] = {}  # operation_id -> start_time
        self.system_metrics = deque(maxlen=1440)  # Store 24 hours of minute-by-minute data
        self.is_monitoring = False
        self.monitor_task = None
        self.lock = threading.Lock()
        
        # Thresholds for alerting
        self.performance_thresholds = {
            'cpu_usage': 80.0,  # %
            'memory_usage': 85.0,  # %
            'avg_response_time': 5.0,  # seconds
            'error_rate': 0.1,  # 10%
        }
    
    async def start_monitoring(self):
        """Start the performance monitoring service."""
        if self.is_monitoring:
            logger.warning("Performance monitor is already running")
            return
        
        self.is_monitoring = True
        self.monitor_task = asyncio.create_task(self._monitoring_loop())
        logger.debug("Performance monitor started")
    
    async def stop_monitoring(self):
        """Stop the performance monitoring service."""
        self.is_monitoring = False
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
        logger.debug("Performance monitor stopped")
    
    def start_operation(self, operation_id: str, component: str, operation: str) -> str:
        """Start tracking an operation."""
        with self.lock:
            full_operation_id = f"{component}_{operation}_{operation_id}_{int(time.time())}"
            self.running_operations[full_operation_id] = time.time()
            return full_operation_id
    
    def end_operation(
        self,
        operation_id: str,
        success: bool = True,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[float]:
        """End tracking an operation and record metrics."""
        with self.lock:
            if operation_id not in self.running_operations:
                logger.warning(f"Operation {operation_id} not found in running operations")
                return None
            
            start_time = self.running_operations.pop(operation_id)
            execution_time = time.time() - start_time
            
            # Parse operation details
            parts = operation_id.split('_')
            if len(parts) >= 2:
                component = parts[0]
                operation = parts[1]
            else:
                component = "unknown"
                operation = "unknown"
            
            # Record metric
            self.record_metric(
                metric_name="operation_duration",
                value=execution_time,
                component=component,
                operation=operation,
                metadata=metadata or {}
            )
            
            # Update component stats
            self._update_component_stats(component, execution_time, success)
            
            return execution_time
    
    def record_metric(
        self,
        metric_name: str,
        value: float,
        component: str,
        operation: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Record a performance metric."""
        metric = PerformanceMetric(
            metric_name=metric_name,
            value=value,
            timestamp=datetime.now(),
            component=component,
            operation=operation,
            metadata=metadata or {}
        )
        
        with self.lock:
            self.metrics.append(metric)
            self._cleanup_old_metrics()
    
    def get_component_performance(self, component: str) -> Optional[ComponentStats]:
        """Get performance statistics for a specific component."""
        return self.component_stats.get(component)
    
    def get_system_performance(self, hours: int = 1) -> Dict[str, Any]:
        """Get system-wide performance summary."""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        recent_metrics = [
            metric for metric in self.metrics
            if metric.timestamp >= cutoff_time
        ]
        
        # Calculate averages by component
        component_metrics = defaultdict(list)
        for metric in recent_metrics:
            if metric.metric_name == "operation_duration":
                component_metrics[metric.component].append(metric.value)
        
        component_averages = {
            component: statistics.mean(values)
            for component, values in component_metrics.items()
            if values
        }
        
        # Get latest system metrics
        latest_system = self.system_metrics[-1] if self.system_metrics else {}
        
        return {
            "timestamp": datetime.now().isoformat(),
            "time_period_hours": hours,
            "total_operations": len(recent_metrics),
            "component_averages": component_averages,
            "system_metrics": latest_system,
            "component_stats": {
                name: {
                    "total_operations": stats.total_operations,
                    "avg_execution_time": stats.avg_execution_time,
                    "success_rate": stats.success_rate,
                    "error_count": stats.error_count
                }
                for name, stats in self.component_stats.items()
            },
            "performance_alerts": self._check_performance_alerts()
        }
    
    def get_performance_trends(self, component: str, hours: int = 24) -> Dict[str, Any]:
        """Get performance trends for a specific component."""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        component_metrics = [
            metric for metric in self.metrics
            if (metric.component == component and 
                metric.timestamp >= cutoff_time and
                metric.metric_name == "operation_duration")
        ]
        
        if not component_metrics:
            return {"error": f"No metrics found for component {component}"}
        
        # Group by hour
        hourly_data = defaultdict(list)
        for metric in component_metrics:
            hour_key = metric.timestamp.replace(minute=0, second=0, microsecond=0)
            hourly_data[hour_key].append(metric.value)
        
        # Calculate hourly averages
        hourly_averages = {
            hour.isoformat(): statistics.mean(values)
            for hour, values in hourly_data.items()
        }
        
        # Calculate overall statistics
        all_values = [metric.value for metric in component_metrics]
        
        return {
            "component": component,
            "time_period_hours": hours,
            "total_operations": len(component_metrics),
            "avg_duration": statistics.mean(all_values),
            "median_duration": statistics.median(all_values),
            "min_duration": min(all_values),
            "max_duration": max(all_values),
            "std_deviation": statistics.stdev(all_values) if len(all_values) > 1 else 0,
            "hourly_averages": hourly_averages,
            "trend": self._calculate_trend(list(hourly_averages.values()))
        }
    
    def export_performance_report(self, filepath: str, hours: int = 24) -> None:
        """Export comprehensive performance report to file."""
        
        system_perf = self.get_system_performance(hours)
        
        # Get trends for all components
        component_trends = {}
        for component in self.component_stats.keys():
            component_trends[component] = self.get_performance_trends(component, hours)
        
        report = {
            "report_timestamp": datetime.now().isoformat(),
            "system_performance": system_perf,
            "component_trends": component_trends,
            "configuration": {
                "retention_hours": self.retention_hours,
                "thresholds": self.performance_thresholds
            }
        }
        
        with open(filepath, 'w') as f:
            json.dump(report, f, indent=2)
        
        logger.debug(f"Performance report exported to {filepath}")
    
    async def _monitoring_loop(self):
        """Main monitoring loop for system metrics."""
        while self.is_monitoring:
            try:
                # Collect system metrics
                system_metrics = {
                    "timestamp": datetime.now().isoformat(),
                    "cpu_percent": psutil.cpu_percent(interval=1),
                    "memory_percent": psutil.virtual_memory().percent,
                    "disk_usage": psutil.disk_usage('/').percent,
                    "running_operations": len(self.running_operations),
                    "total_metrics": len(self.metrics)
                }
                
                self.system_metrics.append(system_metrics)
                
                # Check for performance alerts
                alerts = self._check_performance_alerts()
                if alerts:
                    logger.warning(f"Performance alerts: {alerts}")
                
                await asyncio.sleep(60)  # Collect every minute
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(60)
    
    def _update_component_stats(self, component: str, execution_time: float, success: bool):
        """Update component performance statistics."""
        if component not in self.component_stats:
            self.component_stats[component] = ComponentStats(component_name=component)
        
        stats = self.component_stats[component]
        stats.total_operations += 1
        stats.total_execution_time += execution_time
        stats.avg_execution_time = stats.total_execution_time / stats.total_operations
        stats.min_execution_time = min(stats.min_execution_time, execution_time)
        stats.max_execution_time = max(stats.max_execution_time, execution_time)
        
        if not success:
            stats.error_count += 1
        
        stats.success_rate = 1.0 - (stats.error_count / stats.total_operations)
        stats.last_updated = datetime.now()
    
    def _cleanup_old_metrics(self):
        """Remove metrics older than retention period."""
        cutoff_time = datetime.now() - timedelta(hours=self.retention_hours)
        self.metrics = [
            metric for metric in self.metrics
            if metric.timestamp >= cutoff_time
        ]
    
    def _check_performance_alerts(self) -> List[str]:
        """Check for performance threshold violations."""
        alerts = []
        
        # Check latest system metrics
        if self.system_metrics:
            latest = self.system_metrics[-1]
            
            if latest.get('cpu_percent', 0) > self.performance_thresholds['cpu_usage']:
                alerts.append(f"High CPU usage: {latest['cpu_percent']:.1f}%")
            
            if latest.get('memory_percent', 0) > self.performance_thresholds['memory_usage']:
                alerts.append(f"High memory usage: {latest['memory_percent']:.1f}%")
        
        # Check component performance
        for component, stats in self.component_stats.items():
            if stats.avg_execution_time > self.performance_thresholds['avg_response_time']:
                alerts.append(f"Slow response time in {component}: {stats.avg_execution_time:.2f}s")
            
            if stats.success_rate < (1.0 - self.performance_thresholds['error_rate']):
                alerts.append(f"High error rate in {component}: {(1.0 - stats.success_rate):.1%}")
        
        return alerts
    
    def _calculate_trend(self, values: List[float]) -> str:
        """Calculate trend direction from a series of values."""
        if len(values) < 2:
            return "insufficient_data"
        
        # Simple linear trend calculation
        n = len(values)
        x_mean = (n - 1) / 2
        y_mean = statistics.mean(values)
        
        numerator = sum((i - x_mean) * (values[i] - y_mean) for i in range(n))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        
        if denominator == 0:
            return "stable"
        
        slope = numerator / denominator
        
        if slope > 0.1:
            return "increasing"
        elif slope < -0.1:
            return "decreasing"
        else:
            return "stable"


class PerformanceTracker:
    """Context manager for tracking operation performance."""
    
    def __init__(self, monitor: PerformanceMonitor, component: str, operation: str):
        self.monitor = monitor
        self.component = component
        self.operation = operation
        self.operation_id = None
        self.success = True
    
    def __enter__(self):
        self.operation_id = self.monitor.start_operation(
            operation_id=f"{self.operation}_{int(time.time())}",
            component=self.component,
            operation=self.operation
        )
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.success = False
        
        if self.operation_id:
            self.monitor.end_operation(self.operation_id, self.success)
    
    async def __aenter__(self):
        return self.__enter__()
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return self.__exit__(exc_type, exc_val, exc_tb)


def performance_tracker(monitor: PerformanceMonitor, component: str):
    """Decorator for automatic performance tracking."""
    
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            async with PerformanceTracker(monitor, component, func.__name__):
                return await func(*args, **kwargs)
        
        def sync_wrapper(*args, **kwargs):
            with PerformanceTracker(monitor, component, func.__name__):
                return func(*args, **kwargs)
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


# Global performance monitor instance
performance_monitor = PerformanceMonitor()
