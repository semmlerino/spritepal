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
from core.managers import ExtractionManager, InjectionManager, SessionManager

# Systematic pytest markers applied based on test content analysis
pytestmark = [
    pytest.mark.headless,
    pytest.mark.mock_only,
    pytest.mark.no_qt,
    pytest.mark.parallel_safe,
    pytest.mark.rom_data,
    pytest.mark.unit,
    pytest.mark.cache,
    pytest.mark.ci_safe,
    pytest.mark.signals_slots,
]

class TestControllerDependencyInjection:
    """Test dependency injection functionality for ExtractionController."""

    def test_dependency_injection_with_custom_managers(self, isolated_managers):
        """Test that controller uses injected managers when provided."""
        mock_main_window = Mock()

        # Create mock managers that satisfy the protocol
        mock_extraction_manager = Mock(spec=ExtractionManager)
        mock_session_manager = Mock(spec=SessionManager)
        mock_injection_manager = Mock(spec=InjectionManager)

        # Create controller with injected managers
        controller = ExtractionController(
            mock_main_window,
            extraction_manager=mock_extraction_manager,
            session_manager=mock_session_manager,
            injection_manager=mock_injection_manager
        )

        # Verify the exact same objects are used
        assert controller.extraction_manager is mock_extraction_manager
        assert controller.session_manager is mock_session_manager
        assert controller.injection_manager is mock_injection_manager

    def test_controller_signals_connected_with_injected_managers(self, isolated_managers):
        """Test that controller properly connects signals with injected managers."""
        mock_main_window = Mock()

        # Create mock managers with signal attributes
        mock_extraction_manager = Mock(spec=ExtractionManager)
        mock_injection_manager = Mock(spec=InjectionManager)
        mock_session_manager = Mock(spec=SessionManager)

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
            injection_manager=mock_injection_manager
        )

        # Verify signals were connected
        assert mock_extraction_manager.cache_operation_started.connect.called
        assert mock_extraction_manager.cache_hit.connect.called
        assert mock_injection_manager.injection_progress.connect.called
        assert mock_injection_manager.injection_finished.connect.called

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
