"""
Alert and notification system for critical events.

Provides centralized alerting for system failures, performance issues,
and operational problems.
"""

import logging
import asyncio
import time
from typing import Dict, Any, List, Optional, Callable, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertStatus(Enum):
    """Alert status."""
    ACTIVE = "active"
    RESOLVED = "resolved"
    SUPPRESSED = "suppressed"


@dataclass
class Alert:
    """Represents an alert."""
    id: str
    title: str
    description: str
    severity: AlertSeverity
    component: str
    status: AlertStatus = AlertStatus.ACTIVE
    created_at: float = field(default_factory=time.time)
    resolved_at: Optional[float] = None
    suppressed_until: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    occurrence_count: int = 1
    last_occurrence: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert alert to dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "severity": self.severity.value,
            "component": self.component,
            "status": self.status.value,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
            "suppressed_until": self.suppressed_until,
            "metadata": self.metadata,
            "occurrence_count": self.occurrence_count,
            "last_occurrence": self.last_occurrence
        }


class AlertRule:
    """Defines conditions that trigger alerts."""
    
    def __init__(
        self,
        rule_id: str,
        title: str,
        description: str,
        severity: AlertSeverity,
        component: str,
        condition: Callable[[Dict[str, Any]], bool],
        cooldown_seconds: int = 300,  # 5 minutes default
        max_occurrences: int = 10
    ):
        self.rule_id = rule_id
        self.title = title
        self.description = description
        self.severity = severity
        self.component = component
        self.condition = condition
        self.cooldown_seconds = cooldown_seconds
        self.max_occurrences = max_occurrences
        self.last_triggered = 0.0
        self.trigger_count = 0
    
    def should_trigger(self, context: Dict[str, Any]) -> bool:
        """Check if this rule should trigger given the context."""
        current_time = time.time()
        
        # Check cooldown
        if current_time - self.last_triggered < self.cooldown_seconds:
            return False
        
        # Check condition
        if not self.condition(context):
            return False
        
        # Check max occurrences
        if self.trigger_count >= self.max_occurrences:
            logger.warning(f"Alert rule {self.rule_id} has reached max occurrences ({self.max_occurrences})")
            return False
        
        return True
    
    def trigger(self) -> Alert:
        """Trigger this rule and create an alert."""
        current_time = time.time()
        self.last_triggered = current_time
        self.trigger_count += 1
        
        alert_id = f"{self.rule_id}_{int(current_time)}"
        
        return Alert(
            id=alert_id,
            title=self.title,
            description=self.description,
            severity=self.severity,
            component=self.component,
            metadata={
                "rule_id": self.rule_id,
                "trigger_count": self.trigger_count
            }
        )


class AlertManager:
    """Manages alerts and notifications."""
    
    def __init__(self):
        self.alerts: Dict[str, Alert] = {}
        self.rules: Dict[str, AlertRule] = {}
        self.handlers: List[Callable[[Alert], None]] = []
        self.suppressed_components: Set[str] = set()
        self._lock = asyncio.Lock()
        
        # Register default alert rules
        self._register_default_rules()
    
    def register_rule(self, rule: AlertRule):
        """Register an alert rule."""
        self.rules[rule.rule_id] = rule
        logger.info(f"Registered alert rule: {rule.rule_id}")
    
    def register_handler(self, handler: Callable[[Alert], None]):
        """Register an alert handler."""
        self.handlers.append(handler)
        logger.info(f"Registered alert handler: {handler.__name__}")
    
    async def trigger_alert(
        self,
        title: str,
        description: str,
        severity: AlertSeverity,
        component: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Alert:
        """Manually trigger an alert."""
        async with self._lock:
            alert_id = f"manual_{component}_{int(time.time())}"
            
            alert = Alert(
                id=alert_id,
                title=title,
                description=description,
                severity=severity,
                component=component,
                metadata=metadata or {}
            )
            
            return await self._process_alert(alert)
    
    async def evaluate_rules(self, context: Dict[str, Any]):
        """Evaluate all rules against the given context."""
        async with self._lock:
            for rule in self.rules.values():
                try:
                    if rule.should_trigger(context):
                        alert = rule.trigger()
                        await self._process_alert(alert)
                except Exception as e:
                    logger.error(f"Error evaluating rule {rule.rule_id}: {e}")
    
    async def resolve_alert(self, alert_id: str, metadata: Optional[Dict[str, Any]] = None):
        """Resolve an active alert."""
        async with self._lock:
            if alert_id in self.alerts:
                alert = self.alerts[alert_id]
                if alert.status == AlertStatus.ACTIVE:
                    alert.status = AlertStatus.RESOLVED
                    alert.resolved_at = time.time()
                    if metadata:
                        alert.metadata.update(metadata)
                    
                    logger.info(f"Resolved alert: {alert_id}")
                    
                    # Notify handlers of resolution
                    for handler in self.handlers:
                        try:
                            handler(alert)
                        except Exception as e:
                            logger.error(f"Error in alert handler: {e}")
    
    async def suppress_alert(self, alert_id: str, duration_seconds: int):
        """Suppress an alert for a specified duration."""
        async with self._lock:
            if alert_id in self.alerts:
                alert = self.alerts[alert_id]
                alert.status = AlertStatus.SUPPRESSED
                alert.suppressed_until = time.time() + duration_seconds
                logger.info(f"Suppressed alert {alert_id} for {duration_seconds} seconds")
    
    def suppress_component(self, component: str):
        """Suppress all alerts for a component."""
        self.suppressed_components.add(component)
        logger.info(f"Suppressed alerts for component: {component}")
    
    def unsuppress_component(self, component: str):
        """Remove suppression for a component."""
        self.suppressed_components.discard(component)
        logger.info(f"Removed suppression for component: {component}")
    
    def get_active_alerts(self, severity: Optional[AlertSeverity] = None) -> List[Alert]:
        """Get currently active alerts."""
        current_time = time.time()
        active_alerts = []
        
        for alert in self.alerts.values():
            # Skip resolved alerts
            if alert.status == AlertStatus.RESOLVED:
                continue
            
            # Check if suppression has expired
            if (alert.status == AlertStatus.SUPPRESSED and 
                alert.suppressed_until and 
                current_time > alert.suppressed_until):
                alert.status = AlertStatus.ACTIVE
                alert.suppressed_until = None
            
            # Skip suppressed alerts
            if alert.status == AlertStatus.SUPPRESSED:
                continue
            
            # Skip suppressed components
            if alert.component in self.suppressed_components:
                continue
            
            # Filter by severity if specified
            if severity and alert.severity != severity:
                continue
            
            active_alerts.append(alert)
        
        return sorted(active_alerts, key=lambda a: (a.severity.value, a.created_at), reverse=True)
    
    def get_alert_summary(self) -> Dict[str, Any]:
        """Get summary of alert statistics."""
        active_alerts = self.get_active_alerts()
        
        severity_counts = {s.value: 0 for s in AlertSeverity}
        component_counts = {}
        
        for alert in active_alerts:
            severity_counts[alert.severity.value] += 1
            component_counts[alert.component] = component_counts.get(alert.component, 0) + 1
        
        return {
            "total_active": len(active_alerts),
            "by_severity": severity_counts,
            "by_component": component_counts,
            "suppressed_components": list(self.suppressed_components),
            "total_rules": len(self.rules),
            "total_handlers": len(self.handlers)
        }
    
    async def _process_alert(self, alert: Alert) -> Alert:
        """Process a new alert."""
        # Check for component suppression
        if alert.component in self.suppressed_components:
            logger.debug(f"Alert suppressed for component {alert.component}: {alert.id}")
            return alert
        
        # Check for duplicate alerts (same component and title)
        existing_alert = self._find_existing_alert(alert.component, alert.title)
        if existing_alert:
            # Update existing alert
            existing_alert.occurrence_count += 1
            existing_alert.last_occurrence = time.time()
            existing_alert.metadata.update(alert.metadata)
            alert = existing_alert
            logger.info(f"Updated existing alert: {alert.id} (count: {alert.occurrence_count})")
        else:
            # Store new alert
            self.alerts[alert.id] = alert
            logger.warning(f"New {alert.severity.value} alert: {alert.title} [{alert.component}]")
        
        # Notify handlers
        for handler in self.handlers:
            try:
                handler(alert)
            except Exception as e:
                logger.error(f"Error in alert handler: {e}")
        
        return alert
    
    def _find_existing_alert(self, component: str, title: str) -> Optional[Alert]:
        """Find existing active alert with same component and title."""
        for alert in self.alerts.values():
            if (alert.component == component and 
                alert.title == title and 
                alert.status == AlertStatus.ACTIVE):
                return alert
        return None
    
    def _register_default_rules(self):
        """Register default alert rules."""
        
        # High error rate rule
        def high_error_rate(context: Dict[str, Any]) -> bool:
            errors = context.get("error_count", 0)
            total = context.get("request_count", 1)
            error_rate = errors / total if total > 0 else 0
            return total > 10 and error_rate > 0.1  # 10% error rate with at least 10 requests
        
        self.register_rule(AlertRule(
            rule_id="high_error_rate",
            title="High Error Rate Detected",
            description="Error rate has exceeded 10% over recent requests",
            severity=AlertSeverity.HIGH,
            component="system",
            condition=high_error_rate,
            cooldown_seconds=600  # 10 minutes
        ))
        
        # Service unavailable rule
        def service_unavailable(context: Dict[str, Any]) -> bool:
            return context.get("service_health", {}).get("status") == "unhealthy"
        
        self.register_rule(AlertRule(
            rule_id="service_unavailable",
            title="Critical Service Unavailable",
            description="A critical service has become unavailable",
            severity=AlertSeverity.CRITICAL,
            component="health",
            condition=service_unavailable,
            cooldown_seconds=300  # 5 minutes
        ))
        
        # Memory usage rule
        def high_memory_usage(context: Dict[str, Any]) -> bool:
            memory_percent = context.get("memory_usage_percent", 0)
            return memory_percent > 90
        
        self.register_rule(AlertRule(
            rule_id="high_memory_usage",
            title="High Memory Usage",
            description="Memory usage has exceeded 90%",
            severity=AlertSeverity.HIGH,
            component="system",
            condition=high_memory_usage,
            cooldown_seconds=1800  # 30 minutes
        ))


class LogAlertHandler:
    """Logs alerts to the application logger."""
    
    def __call__(self, alert: Alert):
        level = logging.ERROR if alert.severity in [AlertSeverity.HIGH, AlertSeverity.CRITICAL] else logging.WARNING
        logger.log(level, f"ALERT [{alert.severity.value.upper()}] {alert.title}: {alert.description}")


class ConsoleAlertHandler:
    """Prints alerts to console with formatting."""
    
    def __call__(self, alert: Alert):
        timestamp = datetime.fromtimestamp(alert.created_at).strftime("%Y-%m-%d %H:%M:%S")
        severity_emoji = {
            AlertSeverity.LOW: "🔵",
            AlertSeverity.MEDIUM: "🟡",
            AlertSeverity.HIGH: "🟠",
            AlertSeverity.CRITICAL: "🔴"
        }
        
        emoji = severity_emoji.get(alert.severity, "⚪")
        print(f"\n{emoji} ALERT [{timestamp}] [{alert.component.upper()}]")
        print(f"   {alert.title}")
        print(f"   {alert.description}")
        if alert.occurrence_count > 1:
            print(f"   (Occurred {alert.occurrence_count} times)")
        print()


# Global alert manager instance
alert_manager = AlertManager()

# Register default handlers
alert_manager.register_handler(LogAlertHandler())
alert_manager.register_handler(ConsoleAlertHandler())
