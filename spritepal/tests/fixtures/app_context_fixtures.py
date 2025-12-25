# pyright: recommended
"""
Simplified AppContext fixtures for SpritePal tests.

These fixtures use the new AppContext pattern for simpler test isolation.
They can be used alongside or instead of the legacy session_managers/isolated_managers
fixtures in core_fixtures.py.

Key fixtures:
    - app_context: Function-scoped isolated AppContext (recommended default)
    - state_manager: Shortcut to get ApplicationStateManager from context
    - core_operations: Shortcut to get CoreOperationsManager from context

Migration Guide:
    Replace: isolated_managers -> app_context
    Replace: inject(ApplicationStateManager) -> state_manager fixture
    Replace: inject(CoreOperationsManager) -> core_operations fixture
"""
from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from core.app_context import AppContext
    from core.managers.application_state_manager import ApplicationStateManager
    from core.managers.core_operations_manager import CoreOperationsManager


@pytest.fixture
def app_context(tmp_path: Path) -> Generator[AppContext, None, None]:
    """
    Function-scoped isolated AppContext for clean test isolation.

    Creates a fresh AppContext with isolated settings for each test.
    Automatically cleans up after the test completes.

    This is the recommended fixture for most tests. It provides:
    - Complete isolation between tests
    - No global state pollution
    - Explicit dependency access via context attributes

    Usage:
        def test_something(app_context):
            manager = app_context.core_operations_manager
            # ... test code ...

        def test_with_state(app_context):
            state = app_context.application_state_manager
            state.update_settings(some_key="value")
            # ... test code ...
    """
    from PySide6.QtWidgets import QApplication

    from core.app_context import create_app_context, reset_app_context
    from core.configuration_service import ConfigurationService

    # Ensure Qt app exists
    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    # Create isolated settings
    settings_path = tmp_path / ".test_settings.json"

    # Create a minimal config service for tests
    config_service = ConfigurationService(
        app_name="TestApp",
        settings_file=settings_path,
    )

    # Create the context
    context = create_app_context(
        app_name="TestApp",
        settings_path=settings_path,
        configuration_service=config_service,
    )

    yield context

    # Cleanup
    reset_app_context()

    # Process events to ensure cleanup completes
    if app:
        app.processEvents()


@pytest.fixture
def state_manager(app_context: AppContext) -> ApplicationStateManager:
    """
    Get the ApplicationStateManager from the test context.

    This is a convenience fixture to avoid inject() calls in tests.

    Usage:
        def test_settings(state_manager):
            state_manager.update_settings(key="value")
            assert state_manager.settings.key == "value"
    """
    return app_context.application_state_manager


@pytest.fixture
def core_operations(app_context: AppContext) -> CoreOperationsManager:
    """
    Get the CoreOperationsManager from the test context.

    This is a convenience fixture to avoid inject() calls in tests.

    Usage:
        def test_extraction(core_operations, tmp_path):
            result = core_operations.extract_from_vram(...)
            assert result is not None
    """
    return app_context.core_operations_manager
