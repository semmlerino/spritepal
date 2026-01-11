"""
Fixtures for UI integration tests.

These fixtures support signal-centric testing where tests verify only
observable signal behavior, not internal state.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from PySide6.QtCore import QCoreApplication

from tests.ui.integration.helpers.signal_spy_utils import MultiSignalRecorder

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.fixture
def multi_signal_recorder() -> Callable[[], MultiSignalRecorder]:
    """Factory fixture for creating MultiSignalRecorder instances.

    Usage:
        def test_something(multi_signal_recorder):
            recorder = multi_signal_recorder()
            recorder.connect_signal(widget.clicked, "clicked")
            # ... drive UI ...
            recorder.assert_emitted("clicked", times=1)
    """
    recorders: list[MultiSignalRecorder] = []

    def _factory() -> MultiSignalRecorder:
        recorder = MultiSignalRecorder()
        recorders.append(recorder)
        return recorder

    yield _factory

    # Cleanup: Clear all recorders to avoid holding signal references
    for recorder in recorders:
        recorder.clear()


@pytest.fixture
def process_qt_events() -> Callable[[], None]:
    """Fixture that returns a function to process Qt events.

    Use after triggering actions that emit signals through the event loop:
        process_qt_events()
        assert spy.count() == 1
    """

    def _process() -> None:
        QCoreApplication.processEvents()

    return _process
