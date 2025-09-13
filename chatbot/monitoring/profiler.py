"""
Performance profiling and bottleneck detection.

Provides tools for profiling application performance, detecting
bottlenecks, and collecting detailed timing information.
"""

import cProfile
import pstats
import time
import functools
import logging
import threading
import asyncio
import traceback
from typing import Dict, Any, List, Optional, Callable, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict, deque
from io import StringIO

logger = logging.getLogger(__name__)


@dataclass
class ProfileData:
    """Contains profiling data for a function or operation."""
    name: str
    call_count: int = 0
    total_time: float = 0.0
    min_time: float = float('inf')
    max_time: float = 0.0
    avg_time: float = 0.0
    last_called: Optional[float] = None
    recent_times: deque = field(default_factory=lambda: deque(maxlen=100))
    
    def add_timing(self, duration: float):
        """Add a new timing measurement."""
        self.call_count += 1
        self.total_time += duration
        self.min_time = min(self.min_time, duration)
        self.max_time = max(self.max_time, duration)
        self.avg_time = self.total_time / self.call_count
        self.last_called = time.time()
        self.recent_times.append(duration)
    
    def get_recent_avg(self, last_n: int = 10) -> float:
        """Get average of last N timings."""
        if not self.recent_times:
            return 0.0
        
        recent = list(self.recent_times)[-last_n:]
        return sum(recent) / len(recent)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "call_count": self.call_count,
            "total_time": self.total_time,
            "min_time": self.min_time if self.min_time != float('inf') else 0.0,
            "max_time": self.max_time,
            "avg_time": self.avg_time,
            "last_called": self.last_called,
            "recent_avg_10": self.get_recent_avg(10),
            "recent_avg_50": self.get_recent_avg(50)
        }


class PerformanceProfiler:
    """Main performance profiler class."""
    
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.profiles: Dict[str, ProfileData] = {}
        self.active_profiles: Dict[str, float] = {}  # Currently running profiles
        self.slow_operations: List[Dict[str, Any]] = []
        self.slow_threshold = 1.0  # seconds
        self._lock = threading.RLock()
        
        # Stack tracking for nested operations
        self._call_stack = threading.local()
    
    def profile_function(self, name: Optional[str] = None, threshold: Optional[float] = None):
        """Decorator to profile function execution."""
        def decorator(func):
            profile_name = name or f"{func.__module__}.{func.__name__}"
            
            if asyncio.iscoroutinefunction(func):
                @functools.wraps(func)
                async def async_wrapper(*args, **kwargs):
                    if not self.enabled:
                        return await func(*args, **kwargs)
                    
                    start_time = time.time()
                    try:
                        result = await func(*args, **kwargs)
                        return result
                    finally:
                        duration = time.time() - start_time
                        self._record_timing(profile_name, duration, threshold)
                
                return async_wrapper
            else:
                @functools.wraps(func)
                def sync_wrapper(*args, **kwargs):
                    if not self.enabled:
                        return func(*args, **kwargs)
                    
                    start_time = time.time()
                    try:
                        result = func(*args, **kwargs)
                        return result
                    finally:
                        duration = time.time() - start_time
                        self._record_timing(profile_name, duration, threshold)
                
                return sync_wrapper
        
        return decorator
    
    def start_profile(self, name: str) -> str:
        """Start profiling an operation."""
        if not self.enabled:
            return name
        
        profile_id = f"{name}_{id(threading.current_thread())}_{time.time()}"
        self.active_profiles[profile_id] = time.time()
        
        # Track call stack
        if not hasattr(self._call_stack, 'stack'):
            self._call_stack.stack = []
        self._call_stack.stack.append((name, time.time()))
        
        return profile_id
    
    def end_profile(self, profile_id: str, threshold: Optional[float] = None):
        """End profiling an operation."""
        if not self.enabled or profile_id not in self.active_profiles:
            return
        
        start_time = self.active_profiles.pop(profile_id)
        duration = time.time() - start_time
        
        # Extract name from profile_id
        name = profile_id.split('_')[0]
        self._record_timing(name, duration, threshold)
        
        # Update call stack
        if hasattr(self._call_stack, 'stack') and self._call_stack.stack:
            self._call_stack.stack.pop()
    
    def profile_context(self, name: str, threshold: Optional[float] = None):
        """Context manager for profiling operations."""
        return ProfileContext(self, name, threshold)
    
    def get_profile_data(self, name: str) -> Optional[ProfileData]:
        """Get profile data for a specific operation."""
        return self.profiles.get(name)
    
    def get_all_profiles(self) -> Dict[str, Dict[str, Any]]:
        """Get all profile data."""
        with self._lock:
            return {name: profile.to_dict() for name, profile in self.profiles.items()}
    
    def get_top_slow_operations(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get the slowest operations by average time."""
        with self._lock:
            sorted_profiles = sorted(
                self.profiles.items(),
                key=lambda x: x[1].avg_time,
                reverse=True
            )
            
            return [
                {
                    "name": name,
                    **profile.to_dict()
                }
                for name, profile in sorted_profiles[:limit]
            ]
    
    def get_recent_slow_operations(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent operations that exceeded the slow threshold."""
        with self._lock:
            return self.slow_operations[-limit:]
    
    def reset_profiles(self):
        """Reset all profile data."""
        with self._lock:
            self.profiles.clear()
            self.slow_operations.clear()
            self.active_profiles.clear()
            logger.info("Performance profiles reset")
    
    def generate_report(self) -> str:
        """Generate a comprehensive performance report."""
        with self._lock:
            report = StringIO()
            report.write("PERFORMANCE PROFILING REPORT\n")
            report.write("=" * 50 + "\n\n")
            
            # Summary
            total_operations = sum(p.call_count for p in self.profiles.values())
            total_time = sum(p.total_time for p in self.profiles.values())
            
            report.write(f"Total Operations: {total_operations:,}\n")
            report.write(f"Total Time: {total_time:.3f} seconds\n")
            report.write(f"Active Profiles: {len(self.active_profiles)}\n")
            report.write(f"Slow Operations: {len(self.slow_operations)}\n\n")
            
            # Top slow operations
            report.write("TOP 10 SLOWEST OPERATIONS (by average time)\n")
            report.write("-" * 50 + "\n")
            
            for i, op in enumerate(self.get_top_slow_operations(10), 1):
                report.write(f"{i:2d}. {op['name']}\n")
                report.write(f"    Calls: {op['call_count']:,} | ")
                report.write(f"Avg: {op['avg_time']:.3f}s | ")
                report.write(f"Max: {op['max_time']:.3f}s | ")
                report.write(f"Total: {op['total_time']:.3f}s\n")
            
            report.write("\n")
            
            # Recent slow operations
            recent_slow = self.get_recent_slow_operations(10)
            if recent_slow:
                report.write("RECENT SLOW OPERATIONS\n")
                report.write("-" * 30 + "\n")
                
                for op in recent_slow[-10:]:
                    timestamp = datetime.fromtimestamp(op['timestamp']).strftime("%H:%M:%S")
                    report.write(f"{timestamp} | {op['name']} | {op['duration']:.3f}s\n")
            
            # Call stack analysis
            report.write("\nCALL STACK ANALYSIS\n")
            report.write("-" * 20 + "\n")
            
            if hasattr(self._call_stack, 'stack') and self._call_stack.stack:
                for i, (name, start_time) in enumerate(self._call_stack.stack):
                    indent = "  " * i
                    current_duration = time.time() - start_time
                    report.write(f"{indent}{name} (running: {current_duration:.3f}s)\n")
            else:
                report.write("No active call stack\n")
            
            return report.getvalue()
    
    def _record_timing(self, name: str, duration: float, threshold: Optional[float] = None):
        """Record timing data for an operation."""
        with self._lock:
            # Update profile data
            if name not in self.profiles:
                self.profiles[name] = ProfileData(name)
            
            self.profiles[name].add_timing(duration)
            
            # Check for slow operation
            slow_threshold = threshold or self.slow_threshold
            if duration > slow_threshold:
                slow_op = {
                    "name": name,
                    "duration": duration,
                    "timestamp": time.time(),
                    "call_stack": self._get_current_call_stack()
                }
                self.slow_operations.append(slow_op)
                
                # Keep only recent slow operations
                if len(self.slow_operations) > 1000:
                    self.slow_operations = self.slow_operations[-500:]
                
                logger.warning(f"Slow operation detected: {name} took {duration:.3f}s")
    
    def _get_current_call_stack(self) -> List[str]:
        """Get current call stack for debugging."""
        if not hasattr(self._call_stack, 'stack'):
            return []
        
        return [name for name, _ in self._call_stack.stack]


class ProfileContext:
    """Context manager for profiling operations."""
    
    def __init__(self, profiler: PerformanceProfiler, name: str, threshold: Optional[float] = None):
        self.profiler = profiler
        self.name = name
        self.threshold = threshold
        self.profile_id = None
    
    def __enter__(self):
        self.profile_id = self.profiler.start_profile(self.name)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.profile_id:
            self.profiler.end_profile(self.profile_id, self.threshold)


class SystemProfiler:
    """Profiles system-level operations using cProfile."""
    
    def __init__(self):
        self.profiler = None
        self.stats = None
        self.active = False
    
    def start_system_profiling(self):
        """Start system-wide profiling."""
        if self.active:
            logger.warning("System profiling already active")
            return
        
        self.profiler = cProfile.Profile()
        self.profiler.enable()
        self.active = True
        logger.info("Started system profiling")
    
    def stop_system_profiling(self) -> Optional[pstats.Stats]:
        """Stop system profiling and return stats."""
        if not self.active or not self.profiler:
            logger.warning("No active system profiling")
            return None
        
        self.profiler.disable()
        self.stats = pstats.Stats(self.profiler)
        self.active = False
        logger.info("Stopped system profiling")
        
        return self.stats
    
    def get_profile_report(self, sort_by: str = 'cumulative', limit: int = 20) -> str:
        """Generate a profile report from system profiling."""
        if not self.stats:
            return "No profiling data available"
        
        # Redirect stdout to capture print_stats output
        import sys
        old_stdout = sys.stdout
        try:
            sys.stdout = output = StringIO()
            self.stats.sort_stats(sort_by)
            self.stats.print_stats(limit)
            result = output.getvalue()
        finally:
            sys.stdout = old_stdout
        
        return result
    
    def get_top_functions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top functions by cumulative time."""
        if not self.stats:
            return []
        
        try:
            # Simple approach - parse the text output
            report = self.get_profile_report('cumulative', limit * 2)
            lines = report.split('\n')
            
            stats_data = []
            parsing_data = False
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                    
                # Look for the data section
                if 'ncalls' in line and 'tottime' in line:
                    parsing_data = True
                    continue
                
                if parsing_data and len(stats_data) < limit:
                    # Parse data lines
                    parts = line.split()
                    if len(parts) >= 6:
                        try:
                            ncalls = parts[0]
                            tottime = float(parts[1])
                            cumtime = float(parts[3])
                            filename = ' '.join(parts[5:]) if len(parts) > 5 else 'unknown'
                            
                            stats_data.append({
                                "function": filename,
                                "call_count": ncalls,
                                "total_time": tottime,
                                "cumulative_time": cumtime,
                                "per_call": tottime / float(ncalls.split('/')[0]) if '/' not in ncalls and float(ncalls) > 0 else 0
                            })
                        except (ValueError, IndexError):
                            continue
            
            return stats_data
            
        except Exception as e:
            logger.error(f"Error extracting profile data: {e}")
            return []


# Global profiler instances
performance_profiler = PerformanceProfiler()
system_profiler = SystemProfiler()

# Convenience decorator for common use cases
profile = performance_profiler.profile_function
