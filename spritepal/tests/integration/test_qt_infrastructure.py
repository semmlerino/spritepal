"""
Test Qt infrastructure smoke test.

Most tests removed as they just verify Qt framework behavior.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

pytest_plugins = ["pytestqt"]

pytestmark = [
    pytest.mark.usefixtures("session_app_context"),
    pytest.mark.shared_state_safe,
    pytest.mark.skip_thread_cleanup(reason="Thread tests may intentionally leave threads running"),
    pytest.mark.parallel_unsafe,
    pytest.mark.integration,
]


def test_qapplication_singleton(qapp):
    """Verify single QApplication instance across test session - smoke test."""
    try:
        from PySide6.QtWidgets import QApplication

        app1 = QApplication.instance()
        app2 = QApplication.instance()

        assert app1 is app2
        assert app1 is not None
        assert app1 is qapp

    except ImportError:
        # In environments without Qt, should get mock
        assert isinstance(qapp, Mock)
