"""
DI unit tests for ExtractionController.

Verifies that the controller uses injected managers rather than
falling back to the global DI container.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest

from core.managers.application_state_manager import ApplicationStateManager
from core.managers.core_operations_manager import CoreOperationsManager
from core.services.preview_generator import PreviewGenerator
from ui.extraction_controller import ExtractionController

if TYPE_CHECKING:
    from core.app_context import AppContext

pytestmark = [pytest.mark.headless]


class TestExtractionControllerDI:
    """Test dependency injection for ExtractionController."""

    def test_uses_injected_managers_not_global(self, app_context: AppContext) -> None:
        """Verify controller uses provided managers, not DI fallback."""
        mock_main_window = Mock()

        mock_extraction_manager = Mock(spec=CoreOperationsManager)
        mock_session_manager = Mock(spec=ApplicationStateManager)
        mock_injection_manager = Mock(spec=CoreOperationsManager)
        mock_settings_manager = Mock(spec=ApplicationStateManager)
        mock_preview_generator = Mock(spec=PreviewGenerator)

        controller = ExtractionController(
            mock_main_window,
            extraction_manager=mock_extraction_manager,
            session_manager=mock_session_manager,
            injection_manager=mock_injection_manager,
            settings_manager=mock_settings_manager,
            preview_generator=mock_preview_generator,
        )

        assert controller.extraction_manager is mock_extraction_manager
        assert controller.injection_manager is mock_injection_manager
        assert controller.session_manager is mock_session_manager
        assert controller.preview_generator is mock_preview_generator
