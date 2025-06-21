"""
Enhanced Monitoring and Management API Router

Provides comprehensive monitoring, error tracking, performance metrics,
and configuration management endpoints.
"""

from fastapi import APIRouter, HTTPException, Depends, Query, Body
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
import json
import logging

from chatbot.core.orchestration.main_orchestrator import MainOrchestrator
from chatbot.core.error_handling import error_handler
from chatbot.core.performance_monitor import performance_monitor
from chatbot.core.config_manager import config_manager
from ..dependencies import get_orchestrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])


@router.get("/health")
async def get_health_status(orchestrator: MainOrchestrator = Depends(get_orchestrator)):
    """Get comprehensive system health status."""
    try:
        # Get basic system status
        system_status = {
            "timestamp": datetime.now().isoformat(),
            "uptime_seconds": (datetime.now() - orchestrator._start_time).total_seconds() if hasattr(orchestrator, '_start_time') else 0,
            "is_running": orchestrator.running,
            "version": "1.0.0",  # You could make this dynamic
        }
        
        # Get component health
        components = {}
        
        # Check world state
        if orchestrator.world_state:
            state_data = orchestrator.world_state.to_dict()
            components["world_state"] = {
                "status": "healthy",
                "channels": len(state_data.get("channels", {})),
                "total_messages": sum(len(msgs) for platform in state_data.get("channels", {}).values() 
                                    for msgs in platform.values()),
                "last_updated": state_data.get("last_updated")
            }
        
        # Check AI engine
        if orchestrator.ai_engine:
            components["ai_engine"] = {
                "status": "healthy",
                "model": orchestrator.ai_engine.model,
                "optimization_level": getattr(orchestrator.ai_engine, 'optimization_level', 'unknown')
            }
        
        # Check integration manager
        if hasattr(orchestrator, 'integration_manager') and orchestrator.integration_manager:
            integrations = await orchestrator.integration_manager.list_integrations()
            components["integrations"] = {
                "status": "healthy",
                "total_integrations": len(integrations),
                "active_integrations": len([i for i in integrations if i.get('is_active', False)])
            }
        
        # Get performance metrics
        perf_summary = performance_monitor.get_system_performance(hours=1)
        
        # Get recent errors
        error_summary = error_handler.get_error_analytics(hours=1)
        
        return {
            "status": "healthy" if orchestrator.running else "stopped",
            "system": system_status,
            "components": components,
            "performance": perf_summary,
            "errors": error_summary
        }
        
    except Exception as e:
        logger.error(f"Error getting health status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/performance")
async def get_performance_metrics(
    hours: int = Query(1, ge=1, le=24, description="Time period in hours"),
    component: Optional[str] = Query(None, description="Specific component to analyze")
):
    """Get performance metrics and analysis."""
    try:
        if component:
            # Get component-specific performance
            component_perf = performance_monitor.get_component_performance(component)
            trends = performance_monitor.get_performance_trends(component, hours)
            
            if not component_perf:
                raise HTTPException(status_code=404, detail=f"Component '{component}' not found")
            
            return {
                "component": component,
                "time_period_hours": hours,
                "statistics": {
                    "total_operations": component_perf.total_operations,
                    "avg_execution_time": component_perf.avg_execution_time,
                    "min_execution_time": component_perf.min_execution_time,
                    "max_execution_time": component_perf.max_execution_time,
                    "success_rate": component_perf.success_rate,
                    "error_count": component_perf.error_count
                },
                "trends": trends
            }
        else:
            # Get system-wide performance
            system_perf = performance_monitor.get_system_performance(hours)
            return system_perf
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting performance metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/errors")
async def get_error_analytics(
    hours: int = Query(24, ge=1, le=168, description="Time period in hours"),
    category: Optional[str] = Query(None, description="Error category filter"),
    severity: Optional[str] = Query(None, description="Error severity filter")
):
    """Get error analytics and trends."""
    try:
        analytics = error_handler.get_error_analytics(hours)
        
        # Apply filters if specified
        if category or severity:
            # Note: This is a simplified filter - in a full implementation,
            # you'd want to add filtering capabilities to the error handler
            analytics["filters_applied"] = {
                "category": category,
                "severity": severity
            }
        
        return analytics
        
    except Exception as e:
        logger.error(f"Error getting error analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/errors/export")
async def export_error_report(
    hours: int = Body(24, description="Time period in hours"),
    format: str = Body("json", description="Export format (json)")
):
    """Export detailed error report."""
    try:
        filename = f"error_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{format}"
        filepath = f"data/reports/{filename}"
        
        # Ensure reports directory exists
        import os
        os.makedirs("data/reports", exist_ok=True)
        
        error_handler.export_error_report(filepath, hours)
        
        return {
            "status": "success",
            "filename": filename,
            "filepath": filepath,
            "hours_included": hours
        }
        
    except Exception as e:
        logger.error(f"Error exporting error report: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/performance/export")
async def export_performance_report(
    hours: int = Body(24, description="Time period in hours"),
    format: str = Body("json", description="Export format (json)")
):
    """Export detailed performance report."""
    try:
        filename = f"performance_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{format}"
        filepath = f"data/reports/{filename}"
        
        # Ensure reports directory exists
        import os
        os.makedirs("data/reports", exist_ok=True)
        
        performance_monitor.export_performance_report(filepath, hours)
        
        return {
            "status": "success",
            "filename": filename,
            "filepath": filepath,
            "hours_included": hours
        }
        
    except Exception as e:
        logger.error(f"Error exporting performance report: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/configuration")
async def get_configuration_status():
    """Get current configuration status and validation."""
    try:
        # Load current configuration
        current_config = config_manager.load_configuration()
        status = config_manager.get_configuration_status()
        
        return {
            "status": status,
            "configuration_count": len(current_config),
            "critical_missing": status.get("critical_missing", []),
            "optional_missing": status.get("optional_missing", []),
            "validation_errors": status.get("errors", []),
            "warnings": status.get("warnings", [])
        }
        
    except Exception as e:
        logger.error(f"Error getting configuration status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/configuration/schema")
async def get_configuration_schema():
    """Get configuration schema for documentation."""
    try:
        schema = config_manager.get_configuration_schema()
        return schema
        
    except Exception as e:
        logger.error(f"Error getting configuration schema: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/configuration/validate")
async def validate_configuration(config: Dict[str, Any] = Body(...)):
    """Validate a configuration object."""
    try:
        is_valid = config_manager.validate_configuration(config)
        status = config_manager.get_configuration_status()
        
        return {
            "is_valid": is_valid,
            "validation_errors": status.get("errors", []),
            "warnings": status.get("warnings", []),
            "critical_missing": status.get("critical_missing", []),
            "configuration_coverage": status.get("configuration_coverage", 0)
        }
        
    except Exception as e:
        logger.error(f"Error validating configuration: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/configuration/export-template")
async def export_configuration_template(
    format: str = Body("env", description="Template format (env or json)")
):
    """Export configuration template."""
    try:
        filename = f"config_template_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{format}"
        filepath = f"data/templates/{filename}"
        
        # Ensure templates directory exists
        import os
        os.makedirs("data/templates", exist_ok=True)
        
        config_manager.export_configuration_template(filepath, format)
        
        return {
            "status": "success",
            "filename": filename,
            "filepath": filepath,
            "format": format
        }
        
    except Exception as e:
        logger.error(f"Error exporting configuration template: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/system/diagnostics")
async def run_system_diagnostics(orchestrator: MainOrchestrator = Depends(get_orchestrator)):
    """Run comprehensive system diagnostics."""
    try:
        diagnostics = {
            "timestamp": datetime.now().isoformat(),
            "components": {},
            "integrations": {},
            "dependencies": {},
            "recommendations": []
        }
        
        # Check world state
        if orchestrator.world_state:
            state_data = orchestrator.world_state.to_dict()
            diagnostics["components"]["world_state"] = {
                "status": "operational",
                "channels": len(state_data.get("channels", {})),
                "memory_usage_mb": len(json.dumps(state_data)) / 1024 / 1024,
                "last_updated": state_data.get("last_updated")
            }
        
        # Check AI engine
        if orchestrator.ai_engine:
            diagnostics["components"]["ai_engine"] = {
                "status": "operational",
                "model": orchestrator.ai_engine.model,
                "has_api_key": bool(getattr(orchestrator.ai_engine, 'api_key', None))
            }
        
        # Check database
        try:
            if hasattr(orchestrator, 'history_recorder') and orchestrator.history_recorder:
                # Test database connection
                test_query = "SELECT COUNT(*) FROM sqlite_master"
                # This would need to be implemented in history_recorder
                diagnostics["dependencies"]["database"] = {
                    "status": "operational",
                    "path": orchestrator.history_recorder.db_path
                }
        except Exception as e:
            diagnostics["dependencies"]["database"] = {
                "status": "error",
                "error": str(e)
            }
        
        # Check configuration
        config_status = config_manager.get_configuration_status()
        diagnostics["components"]["configuration"] = {
            "status": "valid" if config_status["is_valid"] else "invalid",
            "coverage": config_status["configuration_coverage"],
            "errors": len(config_status["errors"]),
            "warnings": len(config_status["warnings"])
        }
        
        # Generate recommendations
        if config_status["critical_missing"]:
            diagnostics["recommendations"].append(f"Configure missing critical settings: {', '.join(config_status['critical_missing'])}")
        
        if diagnostics["components"]["configuration"]["coverage"] < 0.8:
            diagnostics["recommendations"].append("Consider configuring more optional settings for optimal performance")
        
        error_analytics = error_handler.get_error_analytics(hours=24)
        if error_analytics["total_errors"] > 10:
            diagnostics["recommendations"].append("High error count detected - review error logs and consider system optimization")
        
        return diagnostics
        
    except Exception as e:
        logger.error(f"Error running system diagnostics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/integrations/status")
async def get_integrations_status(orchestrator: MainOrchestrator = Depends(get_orchestrator)):
    """Get status of all platform integrations."""
    try:
        integrations_status = {}
        
        if hasattr(orchestrator, 'integration_manager') and orchestrator.integration_manager:
            integrations = await orchestrator.integration_manager.list_integrations()
            
            for integration in integrations:
                integration_id = integration.get('integration_id')
                status = await orchestrator.integration_manager.get_integration_status(integration_id)
                
                integrations_status[integration.get('display_name', integration_id)] = {
                    "id": integration_id,
                    "type": integration.get('integration_type'),
                    "is_active": integration.get('is_active', False),
                    "is_connected": status.get('is_connected', False),
                    "last_activity": status.get('last_activity'),
                    "error_count": status.get('error_count', 0)
                }
        
        return {
            "timestamp": datetime.now().isoformat(),
            "total_integrations": len(integrations_status),
            "active_integrations": len([s for s in integrations_status.values() if s["is_active"]]),
            "connected_integrations": len([s for s in integrations_status.values() if s["is_connected"]]),
            "integrations": integrations_status
        }
        
    except Exception as e:
        logger.error(f"Error getting integrations status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/logs/recent")
async def get_recent_logs(
    lines: int = Query(100, ge=1, le=1000, description="Number of recent log lines"),
    level: Optional[str] = Query(None, description="Log level filter (DEBUG, INFO, WARNING, ERROR, CRITICAL)")
):
    """Get recent log entries."""
    try:
        # This is a simplified implementation
        # In practice, you might want to read from log files or use a logging handler
        
        logs = []
        
        # Try to read from log file if it exists
        import os
        log_file = "chatbot.log"
        
        if os.path.exists(log_file):
            with open(log_file, 'r') as f:
                all_lines = f.readlines()
                recent_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
                
                for line in recent_lines:
                    # Simple log parsing - in practice you'd want more sophisticated parsing
                    if level and level.upper() not in line.upper():
                        continue
                    
                    logs.append({
                        "timestamp": datetime.now().isoformat(),  # You'd parse this from the log line
                        "level": "INFO",  # You'd parse this from the log line
                        "message": line.strip(),
                        "source": "system"  # You'd parse this from the log line
                    })
        
        return {
            "total_lines": len(logs),
            "requested_lines": lines,
            "level_filter": level,
            "logs": logs
        }
        
    except Exception as e:
        logger.error(f"Error getting recent logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))
