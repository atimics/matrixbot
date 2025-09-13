"""
Monitoring dashboard that integrates all monitoring components.

Provides a unified interface for health checks, metrics, alerts,
and performance monitoring.
"""

import asyncio
import logging
import time
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict

from .health import health_checker
from .metrics import metrics_collector, app_metrics
from .alerts import alert_manager, AlertSeverity
from .profiler import performance_profiler

logger = logging.getLogger(__name__)


@dataclass
class SystemStatus:
    """Overall system status summary."""
    timestamp: float
    status: str  # healthy, degraded, unhealthy
    uptime_seconds: float
    active_alerts: int
    critical_alerts: int
    health_score: float  # 0-100
    last_health_check: Optional[float]
    performance_score: float  # 0-100
    memory_usage_mb: Optional[float]
    error_rate: float
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class MonitoringDashboard:
    """Main monitoring dashboard that aggregates all monitoring data."""
    
    def __init__(self):
        self.start_time = time.time()
        self.last_health_check = None
        self.health_check_interval = 60  # seconds
        self.metrics_retention_hours = 24
        self._background_task = None
        self._running = False
    
    async def start(self):
        """Start the monitoring dashboard background tasks."""
        if self._running:
            logger.warning("Monitoring dashboard already running")
            return
        
        self._running = True
        self._background_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Monitoring dashboard started")
    
    async def stop(self):
        """Stop the monitoring dashboard."""
        self._running = False
        if self._background_task:
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass
        logger.info("Monitoring dashboard stopped")
    
    async def get_system_status(self) -> SystemStatus:
        """Get comprehensive system status."""
        current_time = time.time()
        uptime = current_time - self.start_time
        
        # Get health data
        health_results = await health_checker.check_all()
        health_score = self._calculate_health_score(health_results)
        
        # Get alert data
        active_alerts = alert_manager.get_active_alerts()
        critical_alerts = [a for a in active_alerts if a.severity == AlertSeverity.CRITICAL]
        
        # Get metrics data
        all_metrics = metrics_collector.get_all_metrics()
        error_rate = self._calculate_error_rate()
        performance_score = self._calculate_performance_score()
        
        # Determine overall status
        status = self._determine_system_status(health_score, len(critical_alerts), error_rate)
        
        return SystemStatus(
            timestamp=current_time,
            status=status,
            uptime_seconds=uptime,
            active_alerts=len(active_alerts),
            critical_alerts=len(critical_alerts),
            health_score=health_score,
            last_health_check=self.last_health_check,
            performance_score=performance_score,
            memory_usage_mb=self._get_memory_usage(),
            error_rate=error_rate
        )
    
    async def get_dashboard_data(self) -> Dict[str, Any]:
        """Get comprehensive dashboard data."""
        system_status = await self.get_system_status()
        
        # Get health check results
        health_results = await health_checker.check_all()
        
        # Get metrics
        metrics_data = metrics_collector.get_all_metrics()
        
        # Get alerts
        active_alerts = [alert.to_dict() for alert in alert_manager.get_active_alerts()]
        alert_summary = alert_manager.get_alert_summary()
        
        # Get performance data
        performance_data = {
            "top_slow_operations": performance_profiler.get_top_slow_operations(10),
            "recent_slow_operations": performance_profiler.get_recent_slow_operations(20),
            "profile_summary": performance_profiler.get_all_profiles()
        }
        
        return {
            "system_status": system_status.to_dict(),
            "health": health_results,
            "metrics": metrics_data,
            "alerts": {
                "active": active_alerts,
                "summary": alert_summary
            },
            "performance": performance_data,
            "dashboard_info": {
                "last_updated": time.time(),
                "monitoring_uptime": time.time() - self.start_time,
                "background_task_running": self._running
            }
        }
    
    async def get_metrics_history(self, hours: int = 1) -> Dict[str, List[Dict[str, Any]]]:
        """Get historical metrics data."""
        # This is a simplified version - in production you'd want to store
        # metrics in a time-series database
        
        current_metrics = metrics_collector.get_all_metrics()
        
        # For now, return current state - extend this with actual historical data
        return {
            "current": [current_metrics]
            # Note: Historical data for specified hours not yet implemented
        }
    
    def export_monitoring_data(self, format: str = "json") -> str:
        """Export all monitoring data for analysis."""
        dashboard_data = asyncio.run(self.get_dashboard_data())
        
        if format.lower() == "json":
            return json.dumps(dashboard_data, indent=2, default=str)
        else:
            # Could add other formats like CSV, etc.
            return str(dashboard_data)
    
    async def run_health_checks(self) -> Dict[str, Any]:
        """Run all health checks and update metrics."""
        logger.debug("Running scheduled health checks")
        
        try:
            health_results = await health_checker.check_all()
            self.last_health_check = time.time()
            
            # Convert health results to dict format for metrics
            health_dict = {}
            for result in health_results:
                health_dict[result.service] = {
                    "status": result.status.value,
                    "response_time": result.response_time,
                    "message": result.message
                }
            
            # Update metrics based on health results
            for service, result in health_dict.items():
                if result["status"] == "healthy":
                    app_metrics.set_active_conversations(service, 1)  # Service is up
                else:
                    app_metrics.set_active_conversations(service, 0)  # Service is down
                    app_metrics.record_error("health_check", f"{service}_unhealthy")
            
            # Evaluate alert rules based on health
            await alert_manager.evaluate_rules({
                "service_health": health_dict,
                "timestamp": time.time()
            })
            
            return health_dict
            
        except Exception as e:
            logger.error(f"Error during health checks: {e}")
            app_metrics.record_error("health_check", "check_failed")
            return {}
    
    async def _monitoring_loop(self):
        """Background monitoring loop."""
        logger.info("Starting monitoring loop")
        
        while self._running:
            try:
                # Run health checks
                await self.run_health_checks()
                
                # Update system metrics
                self._update_system_metrics()
                
                # Evaluate alert rules
                await self._evaluate_alert_rules()
                
                # Clean up old data
                self._cleanup_old_data()
                
                # Wait for next cycle
                await asyncio.sleep(self.health_check_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                app_metrics.record_error("monitoring", "loop_error")
                await asyncio.sleep(10)  # Short sleep before retry
    
    def _calculate_health_score(self, health_results: List[Any]) -> float:
        """Calculate overall health score from individual service health."""
        if not health_results:
            return 0.0
        
        healthy_services = sum(1 for result in health_results 
                             if result.status.value == "healthy")
        
        return (healthy_services / len(health_results)) * 100
    
    def _calculate_error_rate(self) -> float:
        """Calculate current error rate."""
        try:
            error_count = metrics_collector.get_counter("errors.total")
            total_requests = metrics_collector.get_counter("messages.processed.total")
            
            if total_requests > 0:
                return (error_count / total_requests) * 100
            return 0.0
        except Exception:
            return 0.0
    
    def _calculate_performance_score(self) -> float:
        """Calculate performance score based on response times."""
        try:
            profiles = performance_profiler.get_all_profiles()
            if not profiles:
                return 100.0
            
            # Calculate score based on average response times
            total_score = 0
            count = 0
            
            for profile_data in profiles.values():
                avg_time = profile_data.get("avg_time", 0)
                
                # Score based on response time (lower is better)
                if avg_time < 0.1:  # < 100ms = excellent
                    score = 100
                elif avg_time < 0.5:  # < 500ms = good  
                    score = 80
                elif avg_time < 1.0:  # < 1s = fair
                    score = 60
                elif avg_time < 2.0:  # < 2s = poor
                    score = 40
                else:  # >= 2s = bad
                    score = 20
                
                total_score += score
                count += 1
            
            return total_score / count if count > 0 else 100.0
            
        except Exception:
            return 50.0  # Default neutral score
    
    def _determine_system_status(self, health_score: float, critical_alerts: int, error_rate: float) -> str:
        """Determine overall system status."""
        if critical_alerts > 0:
            return "unhealthy"
        elif health_score < 50 or error_rate > 10:
            return "degraded"
        elif health_score < 80 or error_rate > 5:
            return "degraded"
        else:
            return "healthy"
    
    def _get_memory_usage(self) -> Optional[float]:
        """Get current memory usage in MB."""
        try:
            import psutil
            process = psutil.Process()
            return process.memory_info().rss / 1024 / 1024  # Convert to MB
        except ImportError:
            return None
        except Exception as e:
            logger.debug(f"Could not get memory usage: {e}")
            return None
    
    def _update_system_metrics(self):
        """Update system-level metrics."""
        current_time = time.time()
        uptime = current_time - self.start_time
        
        # Update uptime metric
        metrics_collector.set_gauge("system.uptime.seconds", uptime)
        
        # Update memory usage if available
        memory_mb = self._get_memory_usage()
        if memory_mb:
            metrics_collector.set_gauge("system.memory.usage.mb", memory_mb)
        
        # Update active alerts count
        active_alerts = alert_manager.get_active_alerts()
        metrics_collector.set_gauge("system.alerts.active", len(active_alerts))
        
        critical_alerts = [a for a in active_alerts if a.severity == AlertSeverity.CRITICAL]
        metrics_collector.set_gauge("system.alerts.critical", len(critical_alerts))
    
    async def _evaluate_alert_rules(self):
        """Evaluate alert rules with current system state."""
        try:
            context = {
                "timestamp": time.time(),
                "uptime": time.time() - self.start_time,
                "error_count": metrics_collector.get_counter("errors.total"),
                "request_count": metrics_collector.get_counter("messages.processed.total"),
                "memory_usage_mb": self._get_memory_usage(),
                "active_alerts": len(alert_manager.get_active_alerts())
            }
            
            # Add memory usage percentage if available
            if context["memory_usage_mb"]:
                # Rough estimate - adjust based on your system
                context["memory_usage_percent"] = min(100, (context["memory_usage_mb"] / 1024) * 100)
            
            await alert_manager.evaluate_rules(context)
            
        except Exception as e:
            logger.error(f"Error evaluating alert rules: {e}")
    
    def _cleanup_old_data(self):
        """Clean up old monitoring data."""
        try:
            # Clean up old slow operations from profiler
            cutoff_time = time.time() - (self.metrics_retention_hours * 3600)
            
            # This is a placeholder - implement actual cleanup based on your needs
            logger.debug("Cleaned up old monitoring data")
            
        except Exception as e:
            logger.error(f"Error cleaning up old data: {e}")


# Global monitoring dashboard instance
monitoring_dashboard = MonitoringDashboard()
