"""Pytest configuration for sprite_editor tests.

This file ensures fixtures from the root tests/ directory are available
in the sprite_editor test suite.
"""

# Import fixtures from root tests/ directory
pytest_plugins = [
    "tests.fixtures.app_context_fixtures",
    "tests.fixtures.core_fixtures",
    "tests.fixtures.qt_fixtures",
]
