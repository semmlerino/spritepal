"""
Test dependency injection functionality for ExtractionController.

These tests verify that:
1. Backward compatibility is maintained (using global registry)
2. Dependency injection works with custom managers
3. The controller properly uses injected managers
"""
from __future__ import annotations

from unittest.mock import Mock

import pytest

from core.controller import ExtractionController
from core.managers.core_operations_manager import CoreOperationsManager
from core.protocols.dialog_protocols import DialogFactoryProtocol
from core.protocols.manager_protocols import ApplicationStateManagerProtocol

# Systematic pytest markers applied based on test content analysis
# NOTE: parallel_safe removed - tests use isolated_managers fixture and mocks
pytestmark = [pytest.mark.headless]

class TestControllerDependencyInjection:
    """Test dependency injection functionality for ExtractionController."""

    def test_dependency_injection_with_custom_managers(self, isolated_managers):
        """Test that controller uses injected managers when provided."""
        mock_main_window = Mock()

        # Create mock managers that satisfy the protocol
        mock_extraction_manager = Mock(spec=CoreOperationsManager)
        mock_session_manager = Mock(spec=ApplicationStateManagerProtocol)
        mock_injection_manager = Mock(spec=CoreOperationsManager)
        mock_settings_manager = Mock(spec=ApplicationStateManagerProtocol)
        mock_dialog_factory = Mock(spec=DialogFactoryProtocol)

        # Create controller with injected managers
        controller = ExtractionController(
            mock_main_window,
            extraction_manager=mock_extraction_manager,
            session_manager=mock_session_manager,
            injection_manager=mock_injection_manager,
            settings_manager=mock_settings_manager,
            dialog_factory=mock_dialog_factory,
        )

        # Verify the exact same objects are used
        assert controller.extraction_manager is mock_extraction_manager
        assert controller.session_manager is mock_session_manager
        assert controller.injection_manager is mock_injection_manager

    def test_controller_signals_connected_with_injected_managers(self, isolated_managers):
        """Test that controller properly connects signals with injected managers."""
        mock_main_window = Mock()

        # Create mock managers with signal attributes
        mock_extraction_manager = Mock(spec=CoreOperationsManager)
        mock_injection_manager = Mock(spec=CoreOperationsManager)
        mock_session_manager = Mock(spec=ApplicationStateManagerProtocol)
        mock_settings_manager = Mock(spec=ApplicationStateManagerProtocol)
        mock_dialog_factory = Mock(spec=DialogFactoryProtocol)

        # Set up signals as Mock objects
        mock_extraction_manager.cache_operation_started = Mock()
        mock_extraction_manager.cache_hit = Mock()
        mock_extraction_manager.cache_miss = Mock()
        mock_extraction_manager.cache_saved = Mock()

        mock_injection_manager.injection_progress = Mock()
        mock_injection_manager.injection_finished = Mock()
        mock_injection_manager.cache_saved = Mock()

        # Create controller with injected managers
        ExtractionController(
            mock_main_window,
            extraction_manager=mock_extraction_manager,
            session_manager=mock_session_manager,
            injection_manager=mock_injection_manager,
            settings_manager=mock_settings_manager,
            dialog_factory=mock_dialog_factory,
        )

        # Verify signals were connected
        assert mock_extraction_manager.cache_operation_started.connect.called
        assert mock_extraction_manager.cache_hit.connect.called
        assert mock_injection_manager.injection_progress.connect.called
        assert mock_injection_manager.injection_finished.connect.called

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
