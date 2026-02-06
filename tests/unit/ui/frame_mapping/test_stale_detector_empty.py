"""Tests for stale detector empty-list emission fix and handler guard."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class TestStaleDetectorEmptyEmission:
    """Test that detect_stale_entries([]) does NOT emit the signal."""

    def test_detect_stale_entries_empty_does_not_emit(self, qtbot) -> None:
        """Calling detect_stale_entries with empty list should not emit signal."""
        from core.repositories.capture_result_repository import CaptureResultRepository
        from ui.frame_mapping.services.stale_entry_detector import AsyncStaleEntryDetector

        repository = CaptureResultRepository()
        detector = AsyncStaleEntryDetector(capture_repository=repository)

        signal_emitted = False

        def on_signal(ids: list[str]) -> None:
            nonlocal signal_emitted
            signal_emitted = True

        detector.stale_entries_detected.connect(on_signal)
        detector.detect_stale_entries([])

        # Process events to give any signal a chance to be delivered
        from PySide6.QtWidgets import QApplication

        QApplication.processEvents()

        assert not signal_emitted, "Signal should NOT be emitted for empty frame list"


class TestStaleEntriesOnLoadGuard:
    """Test that handle_stale_entries_on_load handles empty list gracefully."""

    def test_handle_stale_entries_on_load_empty_list_no_message(self) -> None:
        """Calling handle_stale_entries_on_load([]) should not show a message."""
        coordinator = InjectionCoordinator()
        message_service = MagicMock()
        coordinator.set_message_service(message_service)

        coordinator.handle_stale_entries_on_load([])

        message_service.show_message.assert_not_called()


# Import at the bottom to avoid potential circular import issues
from ui.frame_mapping.injection_coordinator import InjectionCoordinator
