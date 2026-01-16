"""AppContext Error Behavior Tests.

Tests for AppContext behavior when not initialized or when accessing
deprecated functions. Extracted from test_di_migration_readiness.py
during test suite consolidation.

Source: tests/integration/test_di_migration_readiness.py::TestAppContextErrorBehavior
"""

from __future__ import annotations

import pytest

from core.app_context import get_app_context, get_app_context_optional

pytestmark = [
    pytest.mark.headless,
    pytest.mark.unit,
]


class TestAppContextErrorBehavior:
    """Test behavior when AppContext is not initialized.

    Source: tests/integration/test_di_migration_readiness.py::TestAppContextErrorBehavior
    These tests verify critical error handling paths for AppContext initialization.
    """

    def test_get_app_context_before_init_raises(self, clean_registry_state):
        """Test that get_app_context() raises clear error if not initialized."""
        from core.app_context import reset_app_context

        reset_app_context()

        with pytest.raises(RuntimeError, match="AppContext not initialized"):
            get_app_context()

    def test_get_app_context_optional_returns_none(self, clean_registry_state):
        """Test that get_app_context_optional() returns None if not initialized."""
        from core.app_context import reset_app_context

        reset_app_context()

        ctx = get_app_context_optional()
        assert ctx is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
