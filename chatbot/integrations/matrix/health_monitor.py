#!/usr/bin/env python3
"""
Matrix Health Monitor

This service continuously monitors the Matrix connection health
and provides alerts/recovery mechanisms when issues are detected.
"""

import asyncio
import logging
import time
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class MatrixHealthMonitor:
    """Monitors Matrix connection health and provides recovery mechanisms."""
    
    def __init__(self, matrix_observer, check_interval: int = 30):
        self.matrix_observer = matrix_observer
        self.check_interval = check_interval
        self.last_successful_send = datetime.now()
        self.consecutive_failures = 0
        self.health_history = []
        self.is_monitoring = False
        self.monitor_task = None
        
    async def start_monitoring(self):
        """Start the health monitoring service."""
        if self.is_monitoring:
            logger.warning("Health monitor is already running")
            return
            
        self.is_monitoring = True
        self.monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("Matrix health monitor started")
        
    async def stop_monitoring(self):
        """Stop the health monitoring service."""
        self.is_monitoring = False
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("Matrix health monitor stopped")
        
    async def _monitor_loop(self):
        """Main monitoring loop."""
        while self.is_monitoring:
            try:
                health_status = await self._check_health()
                self._record_health_status(health_status)
                
                if not health_status["is_healthy"]:
                    await self._handle_unhealthy_connection(health_status)
                else:
                    # Reset failure counter on successful health check
                    self.consecutive_failures = 0
                
                await asyncio.sleep(self.check_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health monitor error: {e}")
                await asyncio.sleep(self.check_interval)
    
    async def _check_health(self) -> Dict[str, Any]:
        """Perform comprehensive health check."""
        health_status = {
            "timestamp": datetime.now().isoformat(),
            "is_healthy": False,
            "connection_ok": False,
            "can_send_messages": False,
            "response_time": None,
            "error": None
        }
        
        try:
            # Check basic connection
            start_time = time.time()
            connection_healthy = await self.matrix_observer.check_connection_health()
            response_time = time.time() - start_time
            
            health_status["connection_ok"] = connection_healthy
            health_status["response_time"] = response_time
            
            if connection_healthy:
                # Test message sending capability (dry run)
                test_room = getattr(self.matrix_observer, '_health_check_room', None)
                if test_room:
                    # Don't actually send, just check permissions
                    permissions = await self.matrix_observer.check_room_permissions(test_room)
                    health_status["can_send_messages"] = permissions.get("can_send", False)
                else:
                    health_status["can_send_messages"] = True  # Assume OK if no test room
                
                health_status["is_healthy"] = True
            
        except Exception as e:
            health_status["error"] = str(e)
            logger.error(f"Health check failed: {e}")
        
        return health_status
    
    def _record_health_status(self, status: Dict[str, Any]):
        """Record health status for trend analysis."""
        self.health_history.append(status)
        
        # Keep only last 100 entries
        if len(self.health_history) > 100:
            self.health_history = self.health_history[-100:]
        
        # Update failure counter
        if not status["is_healthy"]:
            self.consecutive_failures += 1
        else:
            self.last_successful_send = datetime.now()
    
    async def _handle_unhealthy_connection(self, status: Dict[str, Any]):
        """Handle unhealthy connection state."""
        logger.warning(f"Unhealthy Matrix connection detected: {status}")
        
        # Alert on consecutive failures
        if self.consecutive_failures >= 3:
            logger.critical(f"Matrix connection unhealthy for {self.consecutive_failures} consecutive checks")
            await self._send_alert(status)
        
        # Attempt recovery
        if self.consecutive_failures >= 5:
            logger.info("Attempting Matrix connection recovery...")
            try:
                await self.matrix_observer.ensure_connection()
                logger.debug("Connection recovery attempt completed")
            except Exception as e:
                logger.error(f"Connection recovery failed: {e}")
    
    async def _send_alert(self, status: Dict[str, Any]):
        """Send alert about connection issues."""
        alert_msg = f"""
🚨 Matrix Connection Alert 🚨

Status: UNHEALTHY
Consecutive Failures: {self.consecutive_failures}
Last Successful Send: {self.last_successful_send}
Error: {status.get('error', 'Unknown')}
Response Time: {status.get('response_time', 'N/A')}s

This is an automated alert from the Matrix Health Monitor.
        """.strip()
        
        logger.critical(alert_msg)
        
        # Could implement additional alerting mechanisms here:
        # - Send to admin channel
        # - Email alerts
        # - Webhook notifications
        # - etc.
    
    def get_health_summary(self) -> Dict[str, Any]:
        """Get current health summary."""
        if not self.health_history:
            return {"status": "no_data"}
        
        recent_checks = self.health_history[-10:]  # Last 10 checks
        healthy_count = sum(1 for check in recent_checks if check["is_healthy"])
        
        avg_response_time = None
        response_times = [
            check["response_time"] 
            for check in recent_checks 
            if check["response_time"] is not None
        ]
        if response_times:
            avg_response_time = sum(response_times) / len(response_times)
        
        return {
            "status": "healthy" if self.consecutive_failures == 0 else "unhealthy",
            "consecutive_failures": self.consecutive_failures,
            "last_successful_send": self.last_successful_send.isoformat(),
            "recent_success_rate": f"{(healthy_count / len(recent_checks)) * 100:.1f}%",
            "average_response_time": f"{avg_response_time:.3f}s" if avg_response_time else "N/A",
            "total_checks": len(self.health_history),
            "monitoring_since": self.health_history[0]["timestamp"] if self.health_history else None
        }
    
    def export_health_data(self, filepath: str):
        """Export health monitoring data to file."""
        health_data = {
            "export_timestamp": datetime.now().isoformat(),
            "summary": self.get_health_summary(),
            "history": self.health_history
        }
        
        with open(filepath, 'w') as f:
            json.dump(health_data, f, indent=2)
        
        logger.debug(f"Health data exported to {filepath}")
