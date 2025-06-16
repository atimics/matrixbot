"""
Enhanced Integration Test Suite

Comprehensive integration tests for the improved chatbot system
focusing on error handling, performance monitoring, and configuration management.
"""

import asyncio
import pytest
import tempfile
import time
import json
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch

from tests.testing_framework import (
    TestEnvironment, IntegrationTestRunner, TestScenario,
    MockServices, TestDataFactory, PerformanceTestSuite
)
from chatbot.core.error_handling import error_handler, ChatbotError, PlatformError
from chatbot.core.performance_monitor import performance_monitor, PerformanceTracker
from chatbot.core.config_manager import config_manager, ConfigValidationLevel
from chatbot.core.orchestration.main_orchestrator import MainOrchestrator, OrchestratorConfig


class TestErrorHandlingIntegration:
    """Integration tests for the error handling system."""
    
    @pytest.mark.asyncio
    async def test_error_registration_and_tracking(self):
        """Test error registration and tracking functionality."""
        
        # Create test error
        test_error = ChatbotError(
            message="Test error message",
            severity=error_handler.ErrorSeverity.MEDIUM,
            recoverable=True
        )
        
        # Register error
        error_context = error_handler.register_error(
            test_error,
            component="test_component",
            operation="test_operation"
        )
        
        assert error_context.component == "test_component"
        assert error_context.operation == "test_operation"
        assert error_context.severity == error_handler.ErrorSeverity.MEDIUM
        assert error_context.recoverable is True
        
        # Test analytics
        analytics = error_handler.get_error_analytics(hours=1)
        assert analytics["total_errors"] >= 1
        assert "test_component" in analytics["by_component"]
    
    @pytest.mark.asyncio
    async def test_error_recovery_mechanism(self):
        """Test automatic error recovery mechanisms."""
        
        # Create recoverable error
        network_error = Exception("Connection timeout")
        
        # Handle error with recovery
        recovery_success = await error_handler.handle_error(
            network_error,
            component="network_service",
            operation="api_request"
        )
        
        # Should attempt recovery for network errors
        assert isinstance(recovery_success, bool)
        
        # Check error was recorded
        analytics = error_handler.get_error_analytics(hours=1)
        assert analytics["total_errors"] >= 1
    
    @pytest.mark.asyncio
    async def test_platform_error_handling(self):
        """Test platform-specific error handling."""
        
        # Create platform error
        matrix_error = PlatformError(
            message="Matrix connection failed",
            platform="matrix",
            severity=error_handler.ErrorSeverity.HIGH
        )
        
        # Register and handle error
        error_context = error_handler.register_error(
            matrix_error,
            component="matrix_observer",
            operation="connect"
        )
        
        assert error_context.category == error_handler.ErrorCategory.PLATFORM_CONNECTION
        assert error_context.metadata["platform"] == "matrix"
    
    def test_error_export_functionality(self):
        """Test error report export functionality."""
        
        # Create test errors
        for i in range(5):
            test_error = Exception(f"Test error {i}")
            error_handler.register_error(
                test_error,
                component="test_component",
                operation=f"test_operation_{i}"
            )
        
        # Export error report
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            export_path = f.name
        
        error_handler.export_error_report(export_path, hours=1)
        
        # Verify export file exists and contains data
        assert Path(export_path).exists()
        
        with open(export_path, 'r') as f:
            report_data = json.load(f)
        
        assert "analytics" in report_data
        assert "errors" in report_data
        assert len(report_data["errors"]) >= 5
        
        # Cleanup
        Path(export_path).unlink()


class TestPerformanceMonitoringIntegration:
    """Integration tests for the performance monitoring system."""
    
    @pytest.mark.asyncio
    async def test_performance_tracking_lifecycle(self):
        """Test complete performance tracking lifecycle."""
        
        # Start monitoring
        await performance_monitor.start_monitoring()
        
        # Start an operation
        operation_id = performance_monitor.start_operation(
            operation_id="test_op_1",
            component="test_component",
            operation="test_operation"
        )
        
        # Simulate some work
        await asyncio.sleep(0.1)
        
        # End operation
        execution_time = performance_monitor.end_operation(operation_id, success=True)
        
        assert execution_time is not None
        assert execution_time >= 0.1
        
        # Check component stats
        component_stats = performance_monitor.get_component_performance("test_component")
        assert component_stats is not None
        assert component_stats.total_operations >= 1
        assert component_stats.success_rate == 1.0
        
        # Stop monitoring
        await performance_monitor.stop_monitoring()
    
    @pytest.mark.asyncio
    async def test_performance_tracker_context_manager(self):
        """Test performance tracker context manager."""
        
        async with PerformanceTracker(performance_monitor, "test_component", "test_operation"):
            # Simulate work
            await asyncio.sleep(0.05)
        
        # Check that performance was recorded
        component_stats = performance_monitor.get_component_performance("test_component")
        assert component_stats is not None
        assert component_stats.total_operations >= 1
    
    @pytest.mark.asyncio
    async def test_performance_alerts_and_thresholds(self):
        """Test performance alerting and threshold checking."""
        
        # Record some slow operations to trigger alerts
        for i in range(3):
            performance_monitor.record_metric(
                metric_name="operation_duration",
                value=10.0,  # Very slow operation
                component="slow_component",
                operation="slow_operation"
            )
        
        # Get system performance with alerts
        system_perf = performance_monitor.get_system_performance(hours=1)
        
        # Should have performance data
        assert "component_averages" in system_perf
        assert "performance_alerts" in system_perf
    
    def test_performance_trends_analysis(self):
        """Test performance trends analysis."""
        
        # Record metrics over time
        component = "trending_component"
        
        for i in range(10):
            performance_monitor.record_metric(
                metric_name="operation_duration",
                value=0.1 + (i * 0.01),  # Gradually increasing times
                component=component,
                operation="trending_operation"
            )
        
        # Get trends
        trends = performance_monitor.get_performance_trends(component, hours=1)
        
        assert trends["component"] == component
        assert trends["total_operations"] >= 10
        assert "trend" in trends
        assert "hourly_averages" in trends
    
    def test_performance_export_functionality(self):
        """Test performance report export."""
        
        # Record some metrics
        for i in range(5):
            performance_monitor.record_metric(
                metric_name="operation_duration",
                value=0.1,
                component="export_test_component",
                operation="export_test_operation"
            )
        
        # Export performance report
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            export_path = f.name
        
        performance_monitor.export_performance_report(export_path, hours=1)
        
        # Verify export
        assert Path(export_path).exists()
        
        with open(export_path, 'r') as f:
            report_data = json.load(f)
        
        assert "system_performance" in report_data
        assert "component_trends" in report_data
        
        # Cleanup
        Path(export_path).unlink()


class TestConfigurationManagementIntegration:
    """Integration tests for configuration management."""
    
    def test_configuration_loading_and_validation(self):
        """Test configuration loading and validation."""
        
        # Create test configuration
        test_config = {
            "CHATBOT_DB_PATH": "test.db",
            "LOG_LEVEL": "INFO",
            "AI_MODEL": "test/model",
            "MATRIX_HOMESERVER": "https://matrix.example.com",
            "INVALID_SETTING": "invalid_value"
        }
        
        # Validate configuration
        is_valid = config_manager.validate_configuration(test_config)
        status = config_manager.get_configuration_status()
        
        assert isinstance(is_valid, bool)
        assert "validation_errors" in status or "errors" in status
        assert "warnings" in status
    
    def test_configuration_schema_generation(self):
        """Test configuration schema generation."""
        
        schema = config_manager.get_configuration_schema()
        
        assert "sections" in schema
        assert "validation_level" in schema
        assert "last_updated" in schema
        
        # Check that core sections exist
        assert "core" in schema["sections"]
        assert "ai" in schema["sections"]
        assert "matrix" in schema["sections"]
        
        # Check section structure
        core_section = schema["sections"]["core"]
        assert "name" in core_section
        assert "description" in core_section
        assert "rules" in core_section
    
    def test_configuration_template_export(self):
        """Test configuration template export."""
        
        # Export ENV template
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            env_export_path = f.name
        
        config_manager.export_configuration_template(env_export_path, format="env")
        
        # Verify ENV export
        assert Path(env_export_path).exists()
        
        with open(env_export_path, 'r') as f:
            env_content = f.read()
        
        assert "CHATBOT_DB_PATH" in env_content
        assert "LOG_LEVEL" in env_content
        
        # Export JSON template
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json_export_path = f.name
        
        config_manager.export_configuration_template(json_export_path, format="json")
        
        # Verify JSON export
        assert Path(json_export_path).exists()
        
        with open(json_export_path, 'r') as f:
            json_data = json.load(f)
        
        assert "_metadata" in json_data
        assert "core" in json_data
        
        # Cleanup
        Path(env_export_path).unlink()
        Path(json_export_path).unlink()
    
    def test_configuration_validation_levels(self):
        """Test different configuration validation levels."""
        
        # Test with strict validation
        strict_manager = config_manager.__class__(validation_level=ConfigValidationLevel.STRICT)
        
        # Test with invalid config
        invalid_config = {
            "LOG_LEVEL": "INVALID_LEVEL",
            "AI_MODEL": ""
        }
        
        is_valid = strict_manager.validate_configuration(invalid_config)
        assert not is_valid
        
        # Test with lenient validation
        lenient_manager = config_manager.__class__(validation_level=ConfigValidationLevel.LENIENT)
        
        is_valid_lenient = lenient_manager.validate_configuration(invalid_config)
        # Lenient mode might still pass some validations
        assert isinstance(is_valid_lenient, bool)


class TestSystemIntegrationScenarios:
    """Integration tests for complete system scenarios."""
    
    @pytest.mark.asyncio
    async def test_orchestrator_with_enhanced_monitoring(self):
        """Test orchestrator with enhanced monitoring and error handling."""
        
        # Create temporary database
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        
        try:
            # Create orchestrator config
            config = OrchestratorConfig(
                db_path=db_path,
                ai_model="test/model"
            )
            
            # Create orchestrator
            orchestrator = MainOrchestrator(config)
            
            # Start monitoring
            await performance_monitor.start_monitoring()
            
            # Test basic initialization
            assert orchestrator is not None
            assert orchestrator.world_state is not None
            
            # Test error handling integration
            try:
                # Trigger an error scenario
                raise Exception("Test integration error")
            except Exception as e:
                await error_handler.handle_error(
                    e,
                    component="orchestrator_test",
                    operation="integration_test"
                )
            
            # Check that error was recorded
            analytics = error_handler.get_error_analytics(hours=1)
            assert analytics["total_errors"] >= 1
            
            # Test performance tracking
            with PerformanceTracker(performance_monitor, "orchestrator", "integration_test"):
                # Simulate some orchestrator work
                state_data = orchestrator.world_state.to_dict()
                assert isinstance(state_data, dict)
            
            # Check performance was recorded
            component_stats = performance_monitor.get_component_performance("orchestrator")
            assert component_stats is not None
            
            # Stop monitoring
            await performance_monitor.stop_monitoring()
            
        finally:
            # Cleanup
            Path(db_path).unlink()
    
    @pytest.mark.asyncio
    async def test_stress_testing_framework(self):
        """Test the stress testing framework."""
        
        # Define a simple test function
        async def test_function():
            await asyncio.sleep(0.01)  # Simulate work
            return "success"
        
        # Run performance measurement
        perf_results = await PerformanceTestSuite.measure_function_performance(
            test_function,
            iterations=10
        )
        
        assert perf_results["iterations"] == 10
        assert "min_time" in perf_results
        assert "max_time" in perf_results
        assert "avg_time" in perf_results
        assert len(perf_results["times"]) == 10
        
        # Run stress test
        stress_results = await PerformanceTestSuite.stress_test_component(
            test_function,
            concurrent_requests=5,
            duration_seconds=2
        )
        
        assert stress_results["duration_seconds"] == 2
        assert stress_results["concurrent_requests"] == 5
        assert stress_results["total_requests"] > 0
        assert "requests_per_second" in stress_results
    
    @pytest.mark.asyncio
    async def test_end_to_end_monitoring_workflow(self):
        """Test complete end-to-end monitoring workflow."""
        
        # 1. Start all monitoring services
        await performance_monitor.start_monitoring()
        
        # 2. Simulate system activity with mixed success/failure
        for i in range(10):
            try:
                with PerformanceTracker(performance_monitor, "e2e_test", f"operation_{i}"):
                    if i % 3 == 0:  # Simulate some failures
                        raise Exception(f"Simulated error {i}")
                    await asyncio.sleep(0.01)  # Simulate work
            except Exception as e:
                await error_handler.handle_error(
                    e,
                    component="e2e_test",
                    operation=f"operation_{i}"
                )
        
        # 3. Collect and verify analytics
        error_analytics = error_handler.get_error_analytics(hours=1)
        perf_analytics = performance_monitor.get_system_performance(hours=1)
        
        # Verify error tracking
        assert error_analytics["total_errors"] >= 3  # At least the simulated errors
        assert "e2e_test" in error_analytics["by_component"]
        
        # Verify performance tracking
        assert "e2e_test" in perf_analytics["component_averages"]
        
        # 4. Test export functionality
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            error_export_path = f.name
        
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            perf_export_path = f.name
        
        error_handler.export_error_report(error_export_path, hours=1)
        performance_monitor.export_performance_report(perf_export_path, hours=1)
        
        # Verify exports
        assert Path(error_export_path).exists()
        assert Path(perf_export_path).exists()
        
        # 5. Cleanup
        await performance_monitor.stop_monitoring()
        Path(error_export_path).unlink()
        Path(perf_export_path).unlink()


class TestIntegrationTestFramework:
    """Test the integration test framework itself."""
    
    @pytest.mark.asyncio
    async def test_test_environment_lifecycle(self):
        """Test test environment setup and cleanup."""
        
        async with TestEnvironment("framework_test") as env:
            # Test environment should be set up
            assert env.temp_dir is not None
            assert env.temp_dir.exists()
            assert env.db_path is not None
            
            # Test configuration overrides
            env.set_config_override("TEST_SETTING", "test_value")
            assert env.get_config_value("TEST_SETTING") == "test_value"
            
            # Test cleanup task registration
            cleanup_called = False
            
            def cleanup_task():
                nonlocal cleanup_called
                cleanup_called = True
            
            env.add_cleanup_task(cleanup_task)
        
        # After exiting context, cleanup should have run
        assert cleanup_called
    
    def test_mock_services_functionality(self):
        """Test mock services creation and functionality."""
        
        # Test mock world state manager
        mock_world_state = MockServices.create_mock_world_state_manager()
        assert mock_world_state is not None
        assert hasattr(mock_world_state, 'add_channel')
        assert hasattr(mock_world_state, 'get_recent_messages')
        
        # Test mock context manager
        mock_context = MockServices.create_mock_context_manager()
        assert mock_context is not None
        assert hasattr(mock_context, 'add_user_message')
        assert hasattr(mock_context, 'get_conversation_messages')
        
        # Test mock action context
        mock_action_context = MockServices.create_mock_action_context()
        assert mock_action_context is not None
        assert hasattr(mock_action_context, 'world_state_manager')
        assert hasattr(mock_action_context, 'context_manager')
    
    def test_test_data_factory(self):
        """Test test data factory functionality."""
        
        # Test message creation
        test_message = TestDataFactory.create_test_message(
            content="Test content",
            sender="@test:example.com"
        )
        
        assert test_message["content"] == "Test content"
        assert test_message["sender"] == "@test:example.com"
        assert "timestamp" in test_message
        assert "message_id" in test_message
        
        # Test user creation
        test_user = TestDataFactory.create_test_user(
            user_id="@test:example.com",
            display_name="Test User"
        )
        
        assert test_user["user_id"] == "@test:example.com"
        assert test_user["display_name"] == "Test User"
        assert "join_timestamp" in test_user
        
        # Test channel creation
        test_channel = TestDataFactory.create_test_channel(
            channel_id="!test:example.com",
            name="Test Channel"
        )
        
        assert test_channel["channel_id"] == "!test:example.com"
        assert test_channel["name"] == "Test Channel"
        assert "created_timestamp" in test_channel
    
    @pytest.mark.asyncio
    async def test_integration_test_runner(self):
        """Test the integration test runner functionality."""
        
        runner = IntegrationTestRunner()
        
        # Create a simple test scenario
        test_executed = False
        
        async def test_step():
            nonlocal test_executed
            test_executed = True
            return {"test_result": "success"}
        
        scenario = TestScenario(
            name="runner_test",
            description="Test scenario for runner",
            test_steps=[test_step],
            expected_outcomes={"test_result": "success"}
        )
        
        runner.add_scenario(scenario)
        
        # Run scenarios
        results = await runner.run_all_scenarios()
        
        assert len(results) == 1
        assert results[0].success
        assert test_executed
        
        # Test summary
        summary = runner.get_test_summary()
        assert summary["total"] == 1
        assert summary["passed"] == 1
        assert summary["failed"] == 0
        assert summary["success_rate"] == 1.0


# Run integration tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
