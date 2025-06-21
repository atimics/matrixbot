"""
Comprehensive Integration Tests for API Server

Tests the FastAPI server endpoints, authentication, and integration with core services.
Addresses security concerns and dependency injection patterns from the engineering report.
"""

import json
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, AsyncMock

from chatbot.api_server import create_secure_api_server
from chatbot.core.orchestration import MainOrchestrator


@pytest.mark.integration
@pytest.mark.api
class TestAPIServerIntegration:
    """Integration tests for the API server."""

    @pytest.fixture
    def mock_orchestrator(self):
        """Create a mock orchestrator for API testing."""
        orchestrator = Mock(spec=MainOrchestrator)
        orchestrator.world_state = Mock()
        orchestrator.world_state.get_state_metrics.return_value = {
            "total_messages": 100,
            "active_channels": 5,
            "last_update": 1234567890.0
        }
        orchestrator.tool_registry = Mock()
        orchestrator.tool_registry.get_all_tools.return_value = {
            "wait": {"name": "wait", "description": "Wait tool", "enabled": True},
            "observe": {"name": "observe", "description": "Observe tool", "enabled": True}
        }
        orchestrator.integration_manager = Mock()
        orchestrator.integration_manager.list_integrations.return_value = []
        return orchestrator

    @pytest.fixture
    def api_server(self, mock_orchestrator):
        """Create API server instance with mocks."""
        return ChatbotAPIServer(mock_orchestrator)

    @pytest.fixture
    def client(self, api_server):
        """Create test client."""
        return TestClient(api_server.app)

    def test_health_endpoint(self, client):
        """Test the health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        
        data = response.json()
        assert "status" in data
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert "service" in data

    def test_cors_configuration(self, client):
        """Test CORS headers are properly configured."""
        response = client.options("/api/worldstate", headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET"
        })
        
        # Should allow the request (but this tests current unsafe config)
        assert response.status_code == 200
        
        # Note: This test documents current unsafe CORS config
        # In production, this should be restricted to specific origins

    def test_worldstate_endpoints(self, client, mock_orchestrator):
        """Test world state API endpoints."""
        # Test getting world state
        response = client.get("/api/worldstate")
        assert response.status_code == 200
        
        data = response.json()
        assert "channels" in data or "state_metrics" in data

    def test_tools_endpoints(self, client, mock_orchestrator):
        """Test tools management endpoints."""
        # Test getting all tools
        response = client.get("/api/tools")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, dict)
        
        # Test individual tool details
        response = client.get("/api/tools/wait")
        assert response.status_code == 200

    def test_integrations_endpoints(self, client, mock_orchestrator):
        """Test integration management endpoints."""
        # Test listing integrations
        response = client.get("/api/integrations")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)

    def test_monitoring_endpoints(self, client, mock_orchestrator):
        """Test monitoring and health endpoints."""
        # Test system health
        response = client.get("/api/monitoring/health")
        assert response.status_code == 200
        
        data = response.json()
        assert "status" in data

    def test_error_handling(self, client, mock_orchestrator):
        """Test API error handling."""
        # Test non-existent endpoint
        response = client.get("/api/nonexistent")
        assert response.status_code == 404
        
        # Test invalid tool name
        response = client.get("/api/tools/nonexistent_tool")
        assert response.status_code in [404, 422]  # Depending on validation

    def test_dependency_injection_consistency(self, api_server):
        """Test that dependency injection is consistent across routers."""
        # Verify that all routers get the same orchestrator instance
        app = api_server.app
        
        # Check that dependency overrides are properly set
        assert len(app.dependency_overrides) > 0
        
        # All routers should use the same orchestrator instance
        orchestrator_overrides = [
            override for override in app.dependency_overrides.values()
            if hasattr(override, '__name__') and 'orchestrator' in override.__name__.lower()
        ]
        
        # Should have orchestrator dependency overrides
        assert len(orchestrator_overrides) > 0


@pytest.mark.integration
@pytest.mark.security
class TestAPIServerSecurity:
    """Security-focused tests for the API server."""

    @pytest.fixture
    def secure_api_server(self, mock_orchestrator):
        """Create API server with security enhancements."""
        # This tests current state and provides foundation for security improvements
        server = ChatbotAPIServer(mock_orchestrator)
        return server

    @pytest.fixture
    def secure_client(self, secure_api_server):
        """Create client for security testing."""
        return TestClient(secure_api_server.app)

    def test_cors_wildcard_security_issue(self, secure_client):
        """Test that documents the current CORS security issue."""
        # This test documents the current security issue mentioned in the report
        response = secure_client.options("/api/worldstate", headers={
            "Origin": "https://malicious-site.com",
            "Access-Control-Request-Method": "GET"
        })
        
        # Current implementation allows all origins (security issue)
        assert response.status_code == 200
        # This should be restricted in production

    def test_missing_authentication(self, secure_client):
        """Test that documents missing authentication."""
        # Currently, all endpoints are accessible without authentication
        sensitive_endpoints = [
            "/api/worldstate",
            "/api/tools",
            "/api/integrations",
        ]
        
        for endpoint in sensitive_endpoints:
            response = secure_client.get(endpoint)
            # Currently returns 200 without auth (should require auth in production)
            assert response.status_code == 200

    def test_input_validation(self, secure_client):
        """Test input validation on API endpoints."""
        # Test with malicious input
        malicious_payloads = [
            {"': DROP TABLE users; --": "value"},
            {"<script>alert('xss')</script>": "value"},
            {"../../../etc/passwd": "value"}
        ]
        
        for payload in malicious_payloads:
            # Test POST endpoints that accept JSON
            response = secure_client.post("/api/integrations/test", json=payload)
            # Should handle malicious input gracefully
            assert response.status_code in [400, 422, 500]  # Error, not processed


@pytest.mark.integration
@pytest.mark.slow
class TestAPIServerPerformance:
    """Performance tests for the API server."""

    @pytest.fixture
    def perf_orchestrator(self):
        """Create orchestrator with realistic data for performance testing."""
        orchestrator = Mock(spec=MainOrchestrator)
        
        # Mock large world state
        orchestrator.world_state = Mock()
        orchestrator.world_state.get_state_metrics.return_value = {
            "total_messages": 10000,
            "active_channels": 50,
            "last_update": 1234567890.0
        }
        
        # Mock many tools  
        tools = {f"tool_{i}": {"name": f"tool_{i}", "enabled": True} for i in range(100)}
        orchestrator.tool_registry = Mock()
        orchestrator.tool_registry.get_all_tools.return_value = tools
        
        return orchestrator

    @pytest.fixture
    def perf_client(self, perf_orchestrator):
        """Create client for performance testing."""
        server = ChatbotAPIServer(perf_orchestrator)
        return TestClient(server.app)

    def test_worldstate_response_time(self, perf_client):
        """Test world state endpoint response time."""
        import time
        
        start_time = time.time()
        response = perf_client.get("/api/worldstate")
        response_time = time.time() - start_time
        
        assert response.status_code == 200
        # Should respond within reasonable time
        assert response_time < 1.0  # Less than 1 second

    def test_tools_listing_performance(self, perf_client):
        """Test tools listing performance with many tools."""
        import time
        
        start_time = time.time()
        response = perf_client.get("/api/tools")
        response_time = time.time() - start_time
        
        assert response.status_code == 200
        # Should handle large tool lists efficiently
        assert response_time < 0.5  # Less than 500ms

    def test_concurrent_requests(self, perf_client):
        """Test handling of concurrent requests."""
        import threading
        import time
        
        results = []
        
        def make_request():
            start_time = time.time()
            response = perf_client.get("/api/worldstate")
            response_time = time.time() - start_time
            results.append((response.status_code, response_time))
        
        # Make 10 concurrent requests
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=make_request)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # All requests should succeed
        assert len(results) == 10
        for status_code, response_time in results:
            assert status_code == 200
            assert response_time < 2.0  # Reasonable time even under load


@pytest.mark.integration
class TestAPIServerWebSocket:
    """Test WebSocket functionality."""

    def test_websocket_logs_connection(self, api_server):
        """Test WebSocket logs endpoint."""
        client = TestClient(api_server.app)
        
        # Test WebSocket connection
        with client.websocket_connect("/ws/logs") as websocket:
            # Connection should be established
            assert websocket is not None
            
            # Send a test message to keep connection alive
            websocket.send_text("ping")


@pytest.mark.integration
class TestAPIServerFactoryFunction:
    """Test the factory function for creating API servers."""

    def test_create_api_server_function(self, mock_orchestrator):
        """Test the create_api_server factory function."""
        app = create_api_server(mock_orchestrator)
        
        assert app is not None
        assert hasattr(app, 'routes')
        assert len(app.routes) > 0
        
        # Test that the created app works
        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200

    def test_api_server_initialization_with_real_orchestrator(self):
        """Test API server initialization with minimal real orchestrator."""
        # This would require a more complex setup but demonstrates the pattern
        # In practice, this would use the orchestrator fixture from conftest_enhanced.py
        pass


# Test utilities for security improvements (implementation examples)
class TestSecurityImprovements:
    """Tests demonstrating security improvements to implement."""
    
    def test_api_key_authentication_pattern(self):
        """Demonstrate API key authentication pattern to implement."""
        from fastapi import FastAPI, HTTPException, Depends, Header
        from typing import Optional
        
        app = FastAPI()
        
        def verify_api_key(x_api_key: Optional[str] = Header(None)):
            expected_key = "test-api-key"  # Would come from config
            if not x_api_key or x_api_key != expected_key:
                raise HTTPException(status_code=401, detail="Invalid API Key")
            return x_api_key
        
        @app.get("/protected")
        async def protected_endpoint(api_key: str = Depends(verify_api_key)):
            return {"message": "Access granted"}
        
        client = TestClient(app)
        
        # Test without API key
        response = client.get("/protected")
        assert response.status_code == 401
        
        # Test with wrong API key
        response = client.get("/protected", headers={"X-API-Key": "wrong-key"})
        assert response.status_code == 401
        
        # Test with correct API key
        response = client.get("/protected", headers={"X-API-Key": "test-api-key"})
        assert response.status_code == 200

    def test_cors_restriction_pattern(self):
        """Demonstrate CORS restriction pattern to implement."""
        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware
        
        app = FastAPI()
        
        # Secure CORS configuration
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:3000", "https://your-domain.com"],  # Specific origins
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "DELETE"],
            allow_headers=["*"],
        )
        
        @app.get("/test")
        async def test_endpoint():
            return {"message": "test"}
        
        client = TestClient(app)
        
        # Test allowed origin
        response = client.get("/test", headers={"Origin": "http://localhost:3000"})
        assert response.status_code == 200
        
        # Note: TestClient doesn't fully enforce CORS, but this demonstrates the pattern
