"""Tests for the main orchestrator functionality."""

import pytest
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from main_orchestrator import main, configure_logging
from tests.test_utils import ServiceTestBase, DatabaseTestHelper


@pytest.mark.integration
class TestMainOrchestrator(ServiceTestBase):
    """Test the main orchestrator service coordination."""

    @pytest.mark.asyncio
    async def test_configure_logging(self):
        """Test logging configuration."""
        configure_logging()
        
        import logging
        logger = logging.getLogger("test_logger")
        
        # Should be able to log without errors
        logger.info("Test log message")
        logger.error("Test error message")

    @pytest.mark.asyncio
    @patch('main_orchestrator.database.initialize_database')
    @patch('main_orchestrator.MatrixGatewayService')
    @patch('main_orchestrator.AIInferenceService')
    @patch('main_orchestrator.OllamaInferenceService')
    @patch('main_orchestrator.RoomLogicService')
    @patch('main_orchestrator.SummarizationService')
    @patch('main_orchestrator.ImageCaptionService')
    @patch('main_orchestrator.ImageAnalysisService')
    @patch('main_orchestrator.ImageCacheService')
    @patch('main_orchestrator.ToolExecutionService')
    @patch('main_orchestrator.ToolLoader')
    async def test_main_service_initialization(
        self,
        mock_tool_loader,
        mock_tool_execution,
        mock_image_cache,
        mock_image_analysis,
        mock_image_caption,
        mock_summarization,
        mock_room_logic,
        mock_ollama,
        mock_ai_inference,
        mock_matrix_gateway,
        mock_db_init
    ):
        """Test that all services are initialized correctly."""
        
        # Make database init return None directly
        mock_db_init.return_value = None
        
        # Mock tool loading
        mock_loader_instance = MagicMock()
        mock_loader_instance.load_tools.return_value = []
        mock_tool_loader.return_value = mock_loader_instance
        
        # Create simple service instances that never run
        for service_mock in [mock_ai_inference, mock_ollama, 
                           mock_room_logic, mock_summarization, mock_image_caption,
                           mock_image_analysis, mock_image_cache, mock_tool_execution]:
            service_instance = MagicMock()
            service_instance.get_client = MagicMock(return_value=MagicMock())
            service_instance.stop = AsyncMock()
            service_instance.set_matrix_client = MagicMock()
            service_instance.run = AsyncMock()
            service_mock.return_value = service_instance
        
        # Set up matrix gateway
        matrix_gateway_instance = MagicMock()
        matrix_gateway_instance.get_client = MagicMock(return_value=MagicMock())
        matrix_gateway_instance.stop = AsyncMock()
        matrix_gateway_instance.set_matrix_client = MagicMock()
        matrix_gateway_instance.run = AsyncMock()
        mock_matrix_gateway.return_value = matrix_gateway_instance
        
        # Mock environment variables
        test_env = {
            'DATABASE_PATH': 'test.db',
            'MATRIX_HOMESERVER': 'https://matrix.example.com',
            'MATRIX_USER_ID': '@bot:matrix.example.com'
        }
        
        # Mock the entire main loop to avoid actually running services
        with patch.dict(os.environ, test_env), \
             patch('main_orchestrator.prompt_constructor.set_message_bus'), \
             patch('main_orchestrator.asyncio.sleep'):
            
            # Mock asyncio.wait to return immediately with matrix_gateway as "done"
            async def mock_wait(tasks, **kwargs):
                # Return the first task as done (matrix_gateway)
                done = {list(tasks)[0]}
                pending = set(tasks) - done
                return done, pending
            
            with patch('main_orchestrator.asyncio.wait', side_effect=mock_wait):
                # This should complete without raising any exceptions
                await main()
            
            # Verify database initialization
            mock_db_init.assert_called_once_with('test.db')
            
            # Verify all services were created
            mock_matrix_gateway.assert_called_once()
            mock_ai_inference.assert_called_once()
            mock_ollama.assert_called_once()
            mock_room_logic.assert_called_once()
            mock_summarization.assert_called_once()
            mock_image_caption.assert_called_once()
            mock_image_analysis.assert_called_once()
            mock_image_cache.assert_called_once()
            mock_tool_execution.assert_called_once()

    @pytest.mark.asyncio
    @patch('main_orchestrator.database.initialize_database')
    @patch('main_orchestrator.MessageBus')
    async def test_message_bus_creation(self, mock_message_bus, mock_db_init):
        """Test that MessageBus is created and passed to services."""
        
        mock_bus_instance = AsyncMock()
        mock_bus_instance.shutdown = AsyncMock()
        mock_message_bus.return_value = mock_bus_instance
        
        # Mock database initialization
        mock_db_init.return_value = None
        
        with patch('main_orchestrator.MatrixGatewayService') as mock_gateway, \
             patch('main_orchestrator.AIInferenceService') as mock_ai, \
             patch('main_orchestrator.OllamaInferenceService') as mock_ollama, \
             patch('main_orchestrator.RoomLogicService') as mock_room_logic, \
             patch('main_orchestrator.SummarizationService') as mock_summarization, \
             patch('main_orchestrator.ImageCaptionService') as mock_image_caption, \
             patch('main_orchestrator.ImageAnalysisService') as mock_image_analysis, \
             patch('main_orchestrator.ImageCacheService') as mock_image_cache, \
             patch('main_orchestrator.ToolExecutionService') as mock_tool_execution, \
             patch('main_orchestrator.ToolLoader') as mock_tool_loader, \
             patch('main_orchestrator.prompt_constructor.set_message_bus'), \
             patch('main_orchestrator.asyncio.sleep'):
            
            # Mock tool loading
            mock_loader_instance = MagicMock()
            mock_loader_instance.load_tools.return_value = []
            mock_tool_loader.return_value = mock_loader_instance
            
            # Mock all service instances properly
            for service_mock in [mock_gateway, mock_ai, mock_ollama, mock_room_logic, 
                               mock_summarization, mock_image_caption, mock_image_analysis, 
                               mock_image_cache, mock_tool_execution]:
                service_instance = MagicMock()
                service_instance.run = AsyncMock()
                service_instance.get_client = MagicMock(return_value=MagicMock())
                service_instance.stop = AsyncMock()
                service_instance.set_matrix_client = MagicMock()
                service_mock.return_value = service_instance
            
            # Mock asyncio.wait to return immediately
            async def mock_wait(tasks, **kwargs):
                done = {list(tasks)[0]}
                pending = set(tasks) - done
                return done, pending
            
            with patch('main_orchestrator.asyncio.wait', side_effect=mock_wait):
                await main()
            
            # Verify MessageBus was created
            mock_message_bus.assert_called_once()
            
            # Verify services were initialized with the bus
            mock_gateway.assert_called_once_with(mock_bus_instance)
            mock_ai.assert_called_once_with(mock_bus_instance)

    @pytest.mark.asyncio
    async def test_database_path_configuration(self):
        """Test database path configuration from environment."""
        
        test_db_path = "/tmp/test_bot.db"
        
        with patch.dict(os.environ, {'DATABASE_PATH': test_db_path}), \
             patch('main_orchestrator.database.initialize_database') as mock_init, \
             patch('main_orchestrator.MatrixGatewayService') as mock_gateway, \
             patch('main_orchestrator.AIInferenceService') as mock_ai, \
             patch('main_orchestrator.OllamaInferenceService') as mock_ollama, \
             patch('main_orchestrator.RoomLogicService') as mock_room_logic, \
             patch('main_orchestrator.SummarizationService') as mock_summarization, \
             patch('main_orchestrator.ImageCaptionService') as mock_image_caption, \
             patch('main_orchestrator.ImageAnalysisService') as mock_image_analysis, \
             patch('main_orchestrator.ImageCacheService') as mock_image_cache, \
             patch('main_orchestrator.ToolExecutionService') as mock_tool_execution, \
             patch('main_orchestrator.ToolLoader') as mock_tool_loader, \
             patch('main_orchestrator.MessageBus') as mock_message_bus, \
             patch('main_orchestrator.prompt_constructor.set_message_bus'), \
             patch('main_orchestrator.asyncio.sleep'):
            
            # Mock database init
            mock_init.return_value = None
            
            # Mock MessageBus properly with AsyncMock shutdown
            mock_bus_instance = MagicMock()
            mock_bus_instance.shutdown = AsyncMock()
            mock_message_bus.return_value = mock_bus_instance
            
            # Mock tool loading
            mock_loader_instance = MagicMock()
            mock_loader_instance.load_tools.return_value = []
            mock_tool_loader.return_value = mock_loader_instance
            
            # Mock all service instances properly
            for service_mock in [mock_gateway, mock_ai, mock_ollama, mock_room_logic, 
                               mock_summarization, mock_image_caption, mock_image_analysis, 
                               mock_image_cache, mock_tool_execution]:
                service_instance = MagicMock()
                service_instance.run = AsyncMock()
                service_instance.get_client = MagicMock(return_value=MagicMock())
                service_instance.stop = AsyncMock()
                service_instance.set_matrix_client = MagicMock()
                service_mock.return_value = service_instance
            
            # Mock asyncio.wait to return immediately
            async def mock_wait(tasks, **kwargs):
                done = {list(tasks)[0]}
                pending = set(tasks) - done
                return done, pending
            
            with patch('main_orchestrator.asyncio.wait', side_effect=mock_wait):
                await main()
            
            mock_init.assert_called_once_with(test_db_path)

    @pytest.mark.asyncio
    @patch('main_orchestrator.ToolLoader')
    async def test_tool_loading_and_registry(self, mock_tool_loader):
        """Test tool loading and registry creation."""
        
        # Mock tools
        mock_tools = [MagicMock(), MagicMock()]
        mock_loader_instance = MagicMock()
        mock_loader_instance.load_tools.return_value = mock_tools
        mock_tool_loader.return_value = mock_loader_instance
        
        with patch('main_orchestrator.ToolRegistry') as mock_registry, \
             patch('main_orchestrator.MatrixGatewayService') as mock_gateway, \
             patch('main_orchestrator.AIInferenceService') as mock_ai, \
             patch('main_orchestrator.OllamaInferenceService') as mock_ollama, \
             patch('main_orchestrator.RoomLogicService') as mock_room_logic, \
             patch('main_orchestrator.SummarizationService') as mock_summarization, \
             patch('main_orchestrator.ImageCaptionService') as mock_image_caption, \
             patch('main_orchestrator.ImageAnalysisService') as mock_image_analysis, \
             patch('main_orchestrator.ImageCacheService') as mock_image_cache, \
             patch('main_orchestrator.ToolExecutionService') as mock_tool_execution, \
             patch('main_orchestrator.database.initialize_database'), \
             patch('main_orchestrator.MessageBus') as mock_message_bus, \
             patch('main_orchestrator.prompt_constructor.set_message_bus'), \
             patch('main_orchestrator.asyncio.sleep'):
            
            # Mock MessageBus properly with AsyncMock shutdown
            mock_bus_instance = MagicMock()
            mock_bus_instance.shutdown = AsyncMock()
            mock_message_bus.return_value = mock_bus_instance
            
            # Mock all service instances properly
            for service_mock in [mock_gateway, mock_ai, mock_ollama, mock_room_logic, 
                               mock_summarization, mock_image_caption, mock_image_analysis, 
                               mock_image_cache, mock_tool_execution]:
                service_instance = MagicMock()
                service_instance.run = AsyncMock()
                service_instance.get_client = MagicMock(return_value=MagicMock())
                service_instance.stop = AsyncMock()
                service_instance.set_matrix_client = MagicMock()
                service_mock.return_value = service_instance
            
            # Mock asyncio.wait to return immediately
            async def mock_wait(tasks, **kwargs):
                done = {list(tasks)[0]}
                pending = set(tasks) - done
                return done, pending
            
            with patch('main_orchestrator.asyncio.wait', side_effect=mock_wait):
                await main()
            
            # Verify tool loader was created and used
            mock_tool_loader.assert_called_once()
            mock_loader_instance.load_tools.assert_called_once()
            
            # Verify registry was created with loaded tools
            mock_registry.assert_called_once_with(mock_tools)

    @pytest.mark.asyncio
    @patch('main_orchestrator.logging.getLogger')
    async def test_logging_setup(self, mock_get_logger):
        """Test that logging is properly configured."""
        
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        
        with patch('main_orchestrator.database.initialize_database'), \
             patch('main_orchestrator.MatrixGatewayService') as mock_gateway, \
             patch('main_orchestrator.AIInferenceService') as mock_ai, \
             patch('main_orchestrator.OllamaInferenceService') as mock_ollama, \
             patch('main_orchestrator.RoomLogicService') as mock_room_logic, \
             patch('main_orchestrator.SummarizationService') as mock_summarization, \
             patch('main_orchestrator.ImageCaptionService') as mock_image_caption, \
             patch('main_orchestrator.ImageAnalysisService') as mock_image_analysis, \
             patch('main_orchestrator.ImageCacheService') as mock_image_cache, \
             patch('main_orchestrator.ToolExecutionService') as mock_tool_execution, \
             patch('main_orchestrator.ToolLoader') as mock_tool_loader, \
             patch('main_orchestrator.MessageBus') as mock_message_bus, \
             patch('main_orchestrator.prompt_constructor.set_message_bus'), \
             patch('main_orchestrator.asyncio.sleep'):
            
            # Mock MessageBus properly with AsyncMock shutdown
            mock_bus_instance = MagicMock()
            mock_bus_instance.shutdown = AsyncMock()
            mock_message_bus.return_value = mock_bus_instance
            
            # Mock tool loading
            mock_loader_instance = MagicMock()
            mock_loader_instance.load_tools.return_value = []
            mock_tool_loader.return_value = mock_loader_instance
            
            # Mock all service instances properly
            for service_mock in [mock_gateway, mock_ai, mock_ollama, mock_room_logic, 
                               mock_summarization, mock_image_caption, mock_image_analysis, 
                               mock_image_cache, mock_tool_execution]:
                service_instance = MagicMock()
                service_instance.run = AsyncMock()
                service_instance.get_client = MagicMock(return_value=MagicMock())
                service_instance.stop = AsyncMock()
                service_instance.set_matrix_client = MagicMock()
                service_mock.return_value = service_instance
            
            # Mock asyncio.wait to return immediately
            async def mock_wait(tasks, **kwargs):
                done = {list(tasks)[0]}
                pending = set(tasks) - done
                return done, pending
            
            with patch('main_orchestrator.asyncio.wait', side_effect=mock_wait):
                await main()
            
            # Verify logger was obtained and used
            mock_get_logger.assert_called()
            assert mock_logger.info.called


@pytest.mark.integration 
class TestOrchestratorIntegration:
    """Integration tests for orchestrator with real components."""

    @pytest.mark.asyncio
    async def test_database_initialization_real(self, tmp_path):
        """Test real database initialization."""
        
        db_path = tmp_path / "test_integration.db"
        
        with patch.dict(os.environ, {'DATABASE_PATH': str(db_path)}), \
             patch('main_orchestrator.MatrixGatewayService') as mock_gateway, \
             patch('main_orchestrator.AIInferenceService') as mock_ai, \
             patch('main_orchestrator.OllamaInferenceService') as mock_ollama, \
             patch('main_orchestrator.RoomLogicService') as mock_room_logic, \
             patch('main_orchestrator.SummarizationService') as mock_summarization, \
             patch('main_orchestrator.ImageCaptionService') as mock_image_caption, \
             patch('main_orchestrator.ImageAnalysisService') as mock_image_analysis, \
             patch('main_orchestrator.ImageCacheService') as mock_image_cache, \
             patch('main_orchestrator.ToolExecutionService') as mock_tool_execution, \
             patch('main_orchestrator.ToolLoader') as mock_tool_loader, \
             patch('main_orchestrator.MessageBus') as mock_message_bus, \
             patch('main_orchestrator.prompt_constructor.set_message_bus'), \
             patch('main_orchestrator.asyncio.sleep'):
            
            # Mock MessageBus properly with AsyncMock shutdown
            mock_bus_instance = MagicMock()
            mock_bus_instance.shutdown = AsyncMock()
            mock_message_bus.return_value = mock_bus_instance
            
            # Mock tool loading
            mock_loader_instance = MagicMock()
            mock_loader_instance.load_tools.return_value = []
            mock_tool_loader.return_value = mock_loader_instance
            
            # Mock all service instances properly
            for service_mock in [mock_gateway, mock_ai, mock_ollama, mock_room_logic, 
                               mock_summarization, mock_image_caption, mock_image_analysis, 
                               mock_image_cache, mock_tool_execution]:
                service_instance = MagicMock()
                service_instance.run = AsyncMock()
                service_instance.get_client = MagicMock(return_value=MagicMock())
                service_instance.stop = AsyncMock()
                service_instance.set_matrix_client = MagicMock()
                service_mock.return_value = service_instance
            
            # Mock asyncio.wait to return immediately
            async def mock_wait(tasks, **kwargs):
                done = {list(tasks)[0]}
                pending = set(tasks) - done
                return done, pending
            
            with patch('main_orchestrator.asyncio.wait', side_effect=mock_wait):
                await main()
            
            # Verify database file was created
            assert db_path.exists()
            
            # Verify database structure
            import sqlite3
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            
            # Check that required tables exist
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            
            assert 'channel_summaries' in tables
            assert 'prompts' in tables
            
            conn.close()

    @pytest.mark.asyncio
    async def test_service_lifecycle_management(self):
        """Test that services are properly started and stopped."""
        
        service_states = {
            'matrix_gateway': {'started': False, 'stopped': False},
            'ai_inference': {'started': False, 'stopped': False}
        }
        
        async def mock_gateway_run():
            service_states['matrix_gateway']['started'] = True
            await asyncio.sleep(0.01)
            return
        
        async def mock_ai_run():
            service_states['ai_inference']['started'] = True
            await asyncio.sleep(0.01)
            return
        
        with patch('main_orchestrator.MatrixGatewayService') as mock_gateway, \
             patch('main_orchestrator.AIInferenceService') as mock_ai, \
             patch('main_orchestrator.OllamaInferenceService') as mock_ollama, \
             patch('main_orchestrator.RoomLogicService') as mock_room_logic, \
             patch('main_orchestrator.SummarizationService') as mock_summarization, \
             patch('main_orchestrator.ImageCaptionService') as mock_image_caption, \
             patch('main_orchestrator.ImageAnalysisService') as mock_image_analysis, \
             patch('main_orchestrator.ImageCacheService') as mock_image_cache, \
             patch('main_orchestrator.ToolExecutionService') as mock_tool_execution, \
             patch('main_orchestrator.database.initialize_database'), \
             patch('main_orchestrator.ToolLoader') as mock_tool_loader, \
             patch('main_orchestrator.MessageBus') as mock_message_bus, \
             patch('main_orchestrator.prompt_constructor.set_message_bus'), \
             patch('main_orchestrator.asyncio.sleep'):
            
            # Mock MessageBus properly with AsyncMock shutdown
            mock_bus_instance = MagicMock()
            mock_bus_instance.shutdown = AsyncMock()
            mock_message_bus.return_value = mock_bus_instance
            
            # Mock tool loading
            mock_loader_instance = MagicMock()
            mock_loader_instance.load_tools.return_value = []
            mock_tool_loader.return_value = mock_loader_instance
            
            # Setup mock services - use the specific async functions
            mock_gateway_instance = MagicMock()
            mock_gateway_instance.run = AsyncMock(side_effect=mock_gateway_run)
            mock_gateway_instance.get_client = MagicMock(return_value=MagicMock())
            mock_gateway_instance.stop = AsyncMock()
            mock_gateway_instance.set_matrix_client = MagicMock()
            mock_gateway.return_value = mock_gateway_instance
            
            mock_ai_instance = MagicMock()
            mock_ai_instance.run = AsyncMock(side_effect=mock_ai_run)
            mock_ai_instance.stop = AsyncMock()
            mock_ai_instance.set_matrix_client = MagicMock()
            mock_ai.return_value = mock_ai_instance
            
            # Mock all other services with proper AsyncMock
            for service_mock in [mock_ollama, mock_room_logic, mock_summarization, 
                               mock_image_caption, mock_image_analysis, mock_image_cache, 
                               mock_tool_execution]:
                service_instance = MagicMock()
                service_instance.run = AsyncMock()
                service_instance.get_client = MagicMock(return_value=MagicMock())
                service_instance.stop = AsyncMock()
                service_instance.set_matrix_client = MagicMock()
                service_mock.return_value = service_instance
            
            # Mock asyncio.wait to return services as done
            async def mock_wait(tasks, **kwargs):
                # Run all service tasks to completion
                await asyncio.gather(*tasks, return_exceptions=True)
                return set(tasks), set()
            
            with patch('main_orchestrator.asyncio.wait', side_effect=mock_wait):
                await main()
            
            # Verify services were started
            assert service_states['matrix_gateway']['started']
            assert service_states['ai_inference']['started']