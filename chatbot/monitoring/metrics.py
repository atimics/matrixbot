"""
Metrics collection and monitoring system.

Provides comprehensive metrics collection for monitoring system
performance, errors, and usage patterns.
"""

import time
import logging
from typing import Dict, Any, Optional, List
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import threading

logger = logging.getLogger(__name__)


@dataclass
class MetricPoint:
    """A single metric data point."""
    timestamp: float
    value: float
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass 
class MetricSummary:
    """Summary statistics for a metric."""
    name: str
    count: int
    sum: float
    min: float
    max: float
    avg: float
    last_value: float
    last_timestamp: float


class MetricsCollector:
    """Collects and aggregates metrics."""
    
    def __init__(self, max_points_per_metric: int = 1000):
        self.max_points_per_metric = max_points_per_metric
        self._counters: Dict[str, float] = defaultdict(float)
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_points_per_metric))
        self._timers: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_points_per_metric))
        self._labels: Dict[str, Dict[str, str]] = {}
        self._lock = threading.RLock()
        
        # Built-in metrics
        self._start_time = time.time()
        self.increment_counter("system.start", 1, {"timestamp": str(datetime.now())})
    
    def increment_counter(self, name: str, value: float = 1.0, labels: Optional[Dict[str, str]] = None):
        """Increment a counter metric."""
        with self._lock:
            full_name = self._get_labeled_name(name, labels)
            self._counters[full_name] += value
            self._labels[full_name] = labels or {}
            logger.debug(f"Counter {full_name} incremented by {value}")
    
    def set_gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """Set a gauge metric value."""
        with self._lock:
            full_name = self._get_labeled_name(name, labels)
            self._gauges[full_name] = value
            self._labels[full_name] = labels or {}
            logger.debug(f"Gauge {full_name} set to {value}")
    
    def record_histogram(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """Record a value in a histogram."""
        with self._lock:
            full_name = self._get_labeled_name(name, labels)
            self._histograms[full_name].append(MetricPoint(time.time(), value, labels or {}))
            self._labels[full_name] = labels or {}
            logger.debug(f"Histogram {full_name} recorded value {value}")
    
    def record_timer(self, name: str, duration: float, labels: Optional[Dict[str, str]] = None):
        """Record a timing measurement."""
        with self._lock:
            full_name = self._get_labeled_name(name, labels)
            self._timers[full_name].append(MetricPoint(time.time(), duration, labels or {}))
            self._labels[full_name] = labels or {}
            logger.debug(f"Timer {full_name} recorded {duration:.3f}s")
    
    def time_operation(self, name: str, labels: Optional[Dict[str, str]] = None):
        """Context manager for timing operations."""
        return TimerContext(self, name, labels)
    
    def get_counter(self, name: str, labels: Optional[Dict[str, str]] = None) -> float:
        """Get current counter value."""
        full_name = self._get_labeled_name(name, labels)
        return self._counters.get(full_name, 0.0)
    
    def get_gauge(self, name: str, labels: Optional[Dict[str, str]] = None) -> Optional[float]:
        """Get current gauge value."""
        full_name = self._get_labeled_name(name, labels)
        return self._gauges.get(full_name)
    
    def get_histogram_summary(self, name: str, labels: Optional[Dict[str, str]] = None) -> Optional[MetricSummary]:
        """Get histogram summary statistics."""
        full_name = self._get_labeled_name(name, labels)
        points = self._histograms.get(full_name, deque())
        
        if not points:
            return None
        
        values = [p.value for p in points]
        return MetricSummary(
            name=full_name,
            count=len(values),
            sum=sum(values),
            min=min(values),
            max=max(values),
            avg=sum(values) / len(values),
            last_value=values[-1],
            last_timestamp=points[-1].timestamp
        )
    
    def get_timer_summary(self, name: str, labels: Optional[Dict[str, str]] = None) -> Optional[MetricSummary]:
        """Get timer summary statistics."""
        full_name = self._get_labeled_name(name, labels)
        points = self._timers.get(full_name, deque())
        
        if not points:
            return None
        
        values = [p.value for p in points]
        return MetricSummary(
            name=full_name,
            count=len(values),
            sum=sum(values),
            min=min(values),
            max=max(values),
            avg=sum(values) / len(values),
            last_value=values[-1],
            last_timestamp=points[-1].timestamp
        )
    
    def get_all_metrics(self) -> Dict[str, Any]:
        """Get all current metrics."""
        with self._lock:
            current_time = time.time()
            uptime = current_time - self._start_time
            
            return {
                "timestamp": current_time,
                "uptime_seconds": uptime,
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "histograms": {
                    name: self._summarize_points(points)
                    for name, points in self._histograms.items()
                },
                "timers": {
                    name: self._summarize_points(points)
                    for name, points in self._timers.items()
                }
            }
    
    def get_metrics_for_export(self) -> List[Dict[str, Any]]:
        """Get metrics in export format (e.g., for Prometheus)."""
        metrics = []
        current_time = time.time()
        
        with self._lock:
            # Export counters
            for name, value in self._counters.items():
                metrics.append({
                    "name": name,
                    "type": "counter",
                    "value": value,
                    "timestamp": current_time,
                    "labels": self._labels.get(name, {})
                })
            
            # Export gauges
            for name, value in self._gauges.items():
                metrics.append({
                    "name": name,
                    "type": "gauge", 
                    "value": value,
                    "timestamp": current_time,
                    "labels": self._labels.get(name, {})
                })
            
            # Export histogram summaries
            for name, points in self._histograms.items():
                if points:
                    summary = self._summarize_points(points)
                    metrics.append({
                        "name": f"{name}_count",
                        "type": "gauge",
                        "value": summary["count"],
                        "timestamp": current_time,
                        "labels": self._labels.get(name, {})
                    })
                    metrics.append({
                        "name": f"{name}_avg",
                        "type": "gauge",
                        "value": summary["avg"],
                        "timestamp": current_time,
                        "labels": self._labels.get(name, {})
                    })
        
        return metrics
    
    def reset_metrics(self):
        """Reset all metrics (use with caution)."""
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()
            self._timers.clear()
            self._labels.clear()
            self._start_time = time.time()
            logger.info("All metrics reset")
    
    def _get_labeled_name(self, name: str, labels: Optional[Dict[str, str]]) -> str:
        """Generate a full metric name including labels."""
        if not labels:
            return name
        
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"
    
    def _summarize_points(self, points: deque) -> Dict[str, Any]:
        """Summarize a collection of metric points."""
        if not points:
            return {"count": 0}
        
        values = [p.value for p in points]
        return {
            "count": len(values),
            "sum": sum(values),
            "min": min(values),
            "max": max(values),
            "avg": sum(values) / len(values),
            "last": values[-1],
            "last_timestamp": points[-1].timestamp
        }


class TimerContext:
    """Context manager for timing operations."""
    
    def __init__(self, collector: MetricsCollector, name: str, labels: Optional[Dict[str, str]] = None):
        self.collector = collector
        self.name = name
        self.labels = labels
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time:
            duration = time.time() - self.start_time
            self.collector.record_timer(self.name, duration, self.labels)


class ApplicationMetrics:
    """High-level application metrics facade."""
    
    def __init__(self, collector: MetricsCollector):
        self.collector = collector
    
    # Message processing metrics
    def record_message_processed(self, platform: str, message_type: str, status: str):
        """Record a processed message."""
        self.collector.increment_counter(
            "messages.processed.total",
            labels={"platform": platform, "type": message_type, "status": status}
        )
    
    def record_message_processing_time(self, platform: str, duration: float):
        """Record message processing time."""
        self.collector.record_timer(
            "messages.processing.duration",
            duration,
            labels={"platform": platform}
        )
    
    # AI engine metrics
    def record_ai_request(self, model: str, status: str, tokens: Optional[int] = None):
        """Record an AI API request."""
        self.collector.increment_counter(
            "ai.requests.total",
            labels={"model": model, "status": status}
        )
        
        if tokens:
            self.collector.record_histogram(
                "ai.tokens.used",
                tokens,
                labels={"model": model}
            )
    
    def record_ai_response_time(self, model: str, duration: float):
        """Record AI response time."""
        self.collector.record_timer(
            "ai.response.duration",
            duration,
            labels={"model": model}
        )
    
    # Tool execution metrics
    def record_tool_execution(self, tool_name: str, status: str, duration: float):
        """Record tool execution."""
        self.collector.increment_counter(
            "tools.executions.total",
            labels={"tool": tool_name, "status": status}
        )
        
        self.collector.record_timer(
            "tools.execution.duration",
            duration,
            labels={"tool": tool_name, "status": status}
        )
    
    # Error tracking
    def record_error(self, component: str, error_type: str):
        """Record an error occurrence."""
        self.collector.increment_counter(
            "errors.total",
            labels={"component": component, "type": error_type}
        )
    
    # System metrics
    def set_active_conversations(self, platform: str, count: int):
        """Set the number of active conversations."""
        self.collector.set_gauge(
            "conversations.active",
            count,
            labels={"platform": platform}
        )
    
    def set_memory_usage(self, component: str, bytes_used: int):
        """Set memory usage for a component."""
        self.collector.set_gauge(
            "memory.usage.bytes",
            bytes_used,
            labels={"component": component}
        )
    
    def record_database_operation(self, operation: str, duration: float, status: str):
        """Record database operation."""
        self.collector.increment_counter(
            "database.operations.total",
            labels={"operation": operation, "status": status}
        )
        
        self.collector.record_timer(
            "database.operation.duration",
            duration,
            labels={"operation": operation}
        )


# Global metrics instances
metrics_collector = MetricsCollector()
app_metrics = ApplicationMetrics(metrics_collector)
