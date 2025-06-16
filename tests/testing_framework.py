"""
Comprehensive Testing Framework

Enhanced testing utilities and frameworks for the chatbot system
including integration tests, performance tests, and test data factories.
"""

import asyncio
import logging
import tempfile
import time
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable, AsyncGenerator
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, MagicMock
import pytest
import aiohttp
import sqlite3

logger = logging.getLogger(__name__)


@dataclass
class TestScenario:
    """Test scenario definition for integration testing."""
    name: str
    description: str
    setup_steps: List[Callable] = field(default_factory=list)
    test_steps: List[Callable] = field(default_factory=list)
    cleanup_steps: List[Callable] = field(default_factory=list)
    expected_outcomes: Dict[str, Any] = field(default_factory=dict)
    timeout_seconds: int = 30
    retry_count: int = 0


@dataclass
class TestResult:
    """Test execution result."""
    scenario_name: str
    success: bool
    execution_time: float
    error_message: Optional[str] = None
    outcomes: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


class TestDataFactory:
    """Factory for generating test data."""
    
    @staticmethod
    def create_test_message(
        content: str = "Test message",
        sender: str = "@testuser:matrix.org",
        platform: str = "matrix",
        channel_id: str = "!testroom:matrix.org",
        timestamp: Optional[float] = None
    ) -> Dict[str, Any]:
        """Create a test message object."""
        return {
            "content": content,
            "sender": sender,
            "platform": platform,
            "channel_id": channel_id,
            "timestamp": timestamp or time.time(),
            "message_id": f"test_msg_{int(time.time() * 1000)}"
        }
    
    @staticmethod
    def create_test_user(
        user_id: str = "@testuser:matrix.org",
        display_name: str = "Test User",
        platform: str = "matrix"
    ) -> Dict[str, Any]:
        """Create a test user object."""
        return {
            "user_id": user_id,
            "display_name": display_name,
            "platform": platform,
            "join_timestamp": time.time(),
            "is_bot": False
        }
    
    @staticmethod
    def create_test_channel(
        channel_id: str = "!testroom:matrix.org",
        name: str = "Test Room",
        platform: str = "matrix",
        member_count: int = 5
    ) -> Dict[str, Any]:
        """Create a test channel object."""
        return {
            "channel_id": channel_id,
            "name": name,
            "platform": platform,
            "member_count": member_count,
            "created_timestamp": time.time(),
            "topic": f"Test topic for {name}"
        }
    
    @staticmethod
    def create_test_action(
        tool_name: str = "test_tool",
        parameters: Optional[Dict[str, Any]] = None,
        success: bool = True
    ) -> Dict[str, Any]:
        """Create a test action object."""
        return {
            "tool_name": tool_name,
            "parameters": parameters or {"test_param": "test_value"},
            "timestamp": time.time(),
            "success": success,
            "result": {"status": "success" if success else "error"},
            "execution_time": 0.1
        }


class MockServices:
    """Collection of mock services for testing."""
    
    @staticmethod
    def create_mock_world_state_manager():
        """Create mock WorldStateManager."""
        mock = AsyncMock()
        mock.state = Mock()
        mock.state.channels = {}
        mock.state.users = {}
        mock.state.messages = {}
        mock.state.action_history = []
        
        # Mock methods
        mock.add_channel = Mock()
        mock.add_message = Mock()
        mock.get_recent_messages = Mock(return_value=[])
        mock.get_world_state_data = Mock()
        mock.update_system_status = Mock()
        
        return mock
    
    @staticmethod
    def create_mock_context_manager():
        """Create mock ContextManager."""
        mock = AsyncMock()
        mock.add_user_message = AsyncMock()
        mock.get_conversation_messages = AsyncMock(return_value=[])
        mock.get_context_summary = AsyncMock(return_value={})
        mock.clear_context = AsyncMock()
        
        return mock
    
    @staticmethod
    def create_mock_ai_engine():
        """Create mock AI engine."""
        mock = AsyncMock()
        mock.process_observations = AsyncMock(return_value={
            "actions": [],
            "reasoning": "Test reasoning",
            "observations": "Test observations"
        })
        mock.get_model_info = Mock(return_value={"model": "test-model"})
        
        return mock
    
    @staticmethod
    def create_mock_matrix_observer():
        """Create mock Matrix observer."""
        mock = AsyncMock()
        mock.connect = AsyncMock()
        mock.disconnect = AsyncMock()
        mock.send_message = AsyncMock(return_value=True)
        mock.get_status = AsyncMock(return_value={"connected": True})
        mock.get_room_list = AsyncMock(return_value=[])
        
        return mock
    
    @staticmethod
    def create_mock_action_context():
        """Create mock ActionContext."""
        mock = Mock()
        mock.world_state_manager = MockServices.create_mock_world_state_manager()
        mock.context_manager = MockServices.create_mock_context_manager()
        mock.arweave_service = Mock()
        mock.arweave_service.is_configured = Mock(return_value=True)
        mock.arweave_service.upload_image_data = AsyncMock(return_value="https://test.url")
        
        return mock


class TestEnvironment:
    """Isolated test environment for integration testing."""
    
    def __init__(self, name: str):
        self.name = name
        self.temp_dir: Optional[Path] = None
        self.db_path: Optional[str] = None
        self.config_overrides: Dict[str, Any] = {}
        self.mock_services: Dict[str, Any] = {}
        self.cleanup_tasks: List[Callable] = []
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.setup()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.cleanup()
    
    async def setup(self):
        """Set up test environment."""
        # Create temporary directory
        self.temp_dir = Path(tempfile.mkdtemp(prefix=f"test_{self.name}_"))
        
        # Create temporary database
        self.db_path = str(self.temp_dir / "test.db")
        
        # Initialize test database
        await self._setup_test_database()
        
        logger.info(f"Test environment '{self.name}' set up at {self.temp_dir}")
    
    async def cleanup(self):
        """Clean up test environment."""
        # Run cleanup tasks
        for cleanup_task in reversed(self.cleanup_tasks):
            try:
                if asyncio.iscoroutinefunction(cleanup_task):
                    await cleanup_task()
                else:
                    cleanup_task()
            except Exception as e:
                logger.warning(f"Error in cleanup task: {e}")
        
        # Remove temporary directory
        if self.temp_dir and self.temp_dir.exists():
            import shutil
            shutil.rmtree(self.temp_dir)
        
        logger.info(f"Test environment '{self.name}' cleaned up")
    
    def add_cleanup_task(self, task: Callable):
        """Add a cleanup task to be executed during teardown."""
        self.cleanup_tasks.append(task)
    
    def set_config_override(self, key: str, value: Any):
        """Override configuration for testing."""
        self.config_overrides[key] = value
    
    def get_config_value(self, key: str, default: Any = None) -> Any:
        """Get configuration value with overrides."""
        return self.config_overrides.get(key, default)
    
    async def _setup_test_database(self):
        """Set up test database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create basic tables for testing
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS test_messages (
                id INTEGER PRIMARY KEY,
                channel_id TEXT,
                content TEXT,
                sender TEXT,
                timestamp REAL
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS test_actions (
                id INTEGER PRIMARY KEY,
                tool_name TEXT,
                parameters TEXT,
                timestamp REAL,
                success BOOLEAN
            )
        """)
        
        conn.commit()
        conn.close()


class IntegrationTestRunner:
    """Runner for integration test scenarios."""
    
    def __init__(self):
        self.scenarios: List[TestScenario] = []
        self.results: List[TestResult] = []
    
    def add_scenario(self, scenario: TestScenario):
        """Add a test scenario."""
        self.scenarios.append(scenario)
    
    async def run_all_scenarios(self) -> List[TestResult]:
        """Run all registered test scenarios."""
        self.results = []
        
        for scenario in self.scenarios:
            result = await self.run_scenario(scenario)
            self.results.append(result)
        
        return self.results
    
    async def run_scenario(self, scenario: TestScenario) -> TestResult:
        """Run a single test scenario."""
        start_time = time.time()
        
        logger.info(f"Running test scenario: {scenario.name}")
        
        try:
            # Run setup steps
            for setup_step in scenario.setup_steps:
                if asyncio.iscoroutinefunction(setup_step):
                    await setup_step()
                else:
                    setup_step()
            
            # Run test steps
            outcomes = {}
            for test_step in scenario.test_steps:
                if asyncio.iscoroutinefunction(test_step):
                    step_result = await test_step()
                else:
                    step_result = test_step()
                
                if isinstance(step_result, dict):
                    outcomes.update(step_result)
            
            # Validate expected outcomes
            success = self._validate_outcomes(outcomes, scenario.expected_outcomes)
            
            execution_time = time.time() - start_time
            
            result = TestResult(
                scenario_name=scenario.name,
                success=success,
                execution_time=execution_time,
                outcomes=outcomes
            )
            
            logger.info(f"Scenario '{scenario.name}' {'PASSED' if success else 'FAILED'} in {execution_time:.2f}s")
            
        except Exception as e:
            execution_time = time.time() - start_time
            result = TestResult(
                scenario_name=scenario.name,
                success=False,
                execution_time=execution_time,
                error_message=str(e)
            )
            
            logger.error(f"Scenario '{scenario.name}' FAILED with error: {e}")
        
        finally:
            # Run cleanup steps
            for cleanup_step in scenario.cleanup_steps:
                try:
                    if asyncio.iscoroutinefunction(cleanup_step):
                        await cleanup_step()
                    else:
                        cleanup_step()
                except Exception as e:
                    logger.warning(f"Error in cleanup step: {e}")
        
        return result
    
    def _validate_outcomes(self, actual: Dict[str, Any], expected: Dict[str, Any]) -> bool:
        """Validate test outcomes against expectations."""
        for key, expected_value in expected.items():
            if key not in actual:
                logger.error(f"Expected outcome '{key}' not found in results")
                return False
            
            actual_value = actual[key]
            if actual_value != expected_value:
                logger.error(f"Outcome mismatch for '{key}': expected {expected_value}, got {actual_value}")
                return False
        
        return True
    
    def get_test_summary(self) -> Dict[str, Any]:
        """Get summary of test results."""
        if not self.results:
            return {"total": 0, "passed": 0, "failed": 0, "success_rate": 0.0}
        
        total = len(self.results)
        passed = sum(1 for result in self.results if result.success)
        failed = total - passed
        
        return {
            "total": total,
            "passed": passed,
            "failed": failed,
            "success_rate": passed / total,
            "total_execution_time": sum(result.execution_time for result in self.results),
            "avg_execution_time": sum(result.execution_time for result in self.results) / total,
            "failed_scenarios": [result.scenario_name for result in self.results if not result.success]
        }
    
    def export_test_report(self, filepath: str):
        """Export detailed test report."""
        summary = self.get_test_summary()
        
        report = {
            "report_timestamp": datetime.now().isoformat(),
            "summary": summary,
            "scenarios": [
                {
                    "name": result.scenario_name,
                    "success": result.success,
                    "execution_time": result.execution_time,
                    "error_message": result.error_message,
                    "outcomes": result.outcomes,
                    "timestamp": result.timestamp.isoformat()
                }
                for result in self.results
            ]
        }
        
        with open(filepath, 'w') as f:
            json.dump(report, f, indent=2)
        
        logger.info(f"Test report exported to {filepath}")


class PerformanceTestSuite:
    """Performance testing utilities."""
    
    @staticmethod
    async def measure_function_performance(
        func: Callable,
        args: tuple = (),
        kwargs: Dict[str, Any] = None,
        iterations: int = 10
    ) -> Dict[str, Any]:
        """Measure function performance over multiple iterations."""
        kwargs = kwargs or {}
        execution_times = []
        
        for _ in range(iterations):
            start_time = time.time()
            
            if asyncio.iscoroutinefunction(func):
                await func(*args, **kwargs)
            else:
                func(*args, **kwargs)
            
            execution_times.append(time.time() - start_time)
        
        return {
            "iterations": iterations,
            "min_time": min(execution_times),
            "max_time": max(execution_times),
            "avg_time": sum(execution_times) / len(execution_times),
            "total_time": sum(execution_times),
            "times": execution_times
        }
    
    @staticmethod
    async def stress_test_component(
        component_func: Callable,
        concurrent_requests: int = 10,
        duration_seconds: int = 30
    ) -> Dict[str, Any]:
        """Stress test a component with concurrent requests."""
        start_time = time.time()
        end_time = start_time + duration_seconds
        
        request_count = 0
        error_count = 0
        response_times = []
        
        async def make_request():
            nonlocal request_count, error_count
            try:
                request_start = time.time()
                if asyncio.iscoroutinefunction(component_func):
                    await component_func()
                else:
                    component_func()
                response_times.append(time.time() - request_start)
                request_count += 1
            except Exception:
                error_count += 1
        
        # Run concurrent requests
        while time.time() < end_time:
            tasks = [make_request() for _ in range(concurrent_requests)]
            await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.sleep(0.1)  # Brief pause between batches
        
        return {
            "duration_seconds": duration_seconds,
            "concurrent_requests": concurrent_requests,
            "total_requests": request_count,
            "total_errors": error_count,
            "error_rate": error_count / (request_count + error_count) if (request_count + error_count) > 0 else 0,
            "requests_per_second": request_count / duration_seconds,
            "avg_response_time": sum(response_times) / len(response_times) if response_times else 0,
            "max_response_time": max(response_times) if response_times else 0
        }


# Pytest fixtures for integration testing
@pytest.fixture
async def test_environment():
    """Pytest fixture for test environment."""
    async with TestEnvironment("pytest") as env:
        yield env


@pytest.fixture
def mock_world_state():
    """Pytest fixture for mock world state."""
    return MockServices.create_mock_world_state_manager()


@pytest.fixture
def mock_context_manager():
    """Pytest fixture for mock context manager."""
    return MockServices.create_mock_context_manager()


@pytest.fixture
def mock_action_context():
    """Pytest fixture for mock action context."""
    return MockServices.create_mock_action_context()


@pytest.fixture
def test_data_factory():
    """Pytest fixture for test data factory."""
    return TestDataFactory()


# Example test scenarios
def create_basic_integration_scenarios() -> List[TestScenario]:
    """Create basic integration test scenarios."""
    
    scenarios = []
    
    # World State Integration Test
    async def test_world_state_integration():
        from chatbot.core.world_state import WorldStateManager
        
        manager = WorldStateManager()
        
        # Test adding channel
        manager.add_channel("test_room", "matrix", "Test Room")
        
        # Test adding message
        test_message = TestDataFactory.create_test_message()
        manager.add_message(test_message)
        
        # Validate state
        state = manager.to_dict()
        assert "matrix" in state["channels"]
        assert "test_room" in state["channels"]["matrix"]
        
        return {"world_state_test": "passed"}
    
    world_state_scenario = TestScenario(
        name="world_state_integration",
        description="Test WorldStateManager integration",
        test_steps=[test_world_state_integration],
        expected_outcomes={"world_state_test": "passed"}
    )
    scenarios.append(world_state_scenario)
    
    return scenarios


# Global test runner instance
integration_test_runner = IntegrationTestRunner()
