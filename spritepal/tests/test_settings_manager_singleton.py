"""Tests for settings manager singleton behavior.

Extracted from test_settings_manager.py because these tests require isolated_managers
(fresh manager state) to properly verify singleton initialization behavior, while the
rest of test_settings_manager.py uses session_managers for performance.

See CLAUDE.md 'Test Fixture Selection Guide' - do not mix session_managers and
isolated_managers in the same module.
"""
from __future__ import annotations

import pytest

from core.di_container import inject
from core.protocols.manager_protocols import SettingsManagerProtocol
from core.services.settings_manager import SettingsManager


def get_settings_manager():
    """Get settings manager from DI container (replaces deprecated function)."""
    return inject(SettingsManagerProtocol)


# These tests need isolated_managers because they verify singleton initialization
# behavior, which requires fresh manager state each test
pytestmark = [
    pytest.mark.headless,
    pytest.mark.integration,
]


class TestGlobalSettingsInstance:
    """Test the global settings instance singleton behavior."""

    def test_get_settings_manager_singleton(self, isolated_managers):
        """Test that get_settings_manager returns singleton."""
        # Get instance twice - should return same object
        manager1 = get_settings_manager()
        manager2 = get_settings_manager()

        assert manager1 is manager2
        assert isinstance(manager1, SettingsManager)

    def test_get_settings_manager_preserves_state(self, isolated_managers):
        """Test that singleton preserves state."""
        manager1 = get_settings_manager()
        manager1.set("custom", "key", "value")

        manager2 = get_settings_manager()
        assert manager2.get("custom", "key") == "value"
