# pyright: basic  # Test protocol definitions
# pyright: reportUnusedImport=false  # Protocols may appear unused but are used in TYPE_CHECKING

"""
Test protocol definitions for type-safe mock objects.

These protocols define the interfaces that mock objects should implement,
ensuring type safety while maintaining the flexibility needed for testing.

Usage:
from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from tests.infrastructure.test_protocols import MockMainWindowProtocol

    @pytest.fixture
    def mock_window() -> "MockMainWindowProtocol":
        return MockFactory.create_main_window()
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable
from unittest.mock import Mock

import pytest

from .qt_mocks import MockSignal

# This file defines Protocol type interfaces only - no actual tests
# Markers removed to avoid distorting -m selection and test reporting
pytestmark = []

@runtime_checkable
class MockMainWindowProtocol(Protocol):
    """Protocol for mock main window objects."""

    # Signals
    extract_requested: MockSignal
    open_in_editor_requested: MockSignal
    arrange_rows_requested: MockSignal
    arrange_grid_requested: MockSignal
    inject_requested: MockSignal

    # UI Components
    status_bar: Mock
    sprite_preview: Mock
    palette_preview: Mock
    preview_info: Mock
    output_name_edit: Mock

    # Methods
    get_extraction_params: Mock
    extraction_complete: Mock
    extraction_failed: Mock
    show: Mock
    close: Mock

@runtime_checkable
class MockExtractionWorkerProtocol(Protocol):
    """Protocol for mock extraction worker objects."""

    # Signals (created dynamically by create_mock_signals)
    progress: MockSignal
    finished: MockSignal
    error: MockSignal

    # Worker control methods
    start: Mock
    run: Mock
    quit: Mock
    wait: Mock
    isRunning: Mock

@runtime_checkable
class MockExtractionManagerProtocol(Protocol):
    """Protocol for mock extraction manager objects."""

    # Core methods
    extract_sprites: Mock
    get_rom_extractor: Mock
    validate_extraction_params: Mock
    create_worker: Mock

    # Signals (created dynamically by create_mock_signals)
    progress: MockSignal
    finished: MockSignal
    error: MockSignal

@runtime_checkable
class MockInjectionManagerProtocol(Protocol):
    """Protocol for mock injection manager objects."""

    # Core methods
    inject_sprite: Mock
    validate_injection_params: Mock
    create_worker: Mock

    # Standard signals
    injection_started: MockSignal
    injection_progress: MockSignal
    injection_complete: MockSignal
    injection_failed: MockSignal

@runtime_checkable
class MockSessionManagerProtocol(Protocol):
    """Protocol for mock session manager objects."""

    # Persistence methods
    save_settings: Mock
    load_settings: Mock
    get_recent_files: Mock
    add_recent_file: Mock

@runtime_checkable
class MockQtBotProtocol(Protocol):
    """Protocol for Qt test bot objects (real or mock)."""

    wait: Callable[[int], None]
    waitSignal: Callable[..., Any]
    waitUntil: Callable[..., Any]
    addWidget: Callable[[Any], None]

@runtime_checkable
class MockDialogServicesProtocol(Protocol):
    """Protocol for unified dialog services collection."""

    preview_generator: Mock
    error_handler: Mock
    offset_navigator: Mock
    preview_coordinator: Mock
    sprites_registry: Mock
    worker_manager: Mock

@runtime_checkable
class MockPreviewGeneratorProtocol(Protocol):
    """Protocol for preview generator service."""

    create_preview_request: Mock
    generate_preview: Mock
    preview_ready: MockSignal
    preview_error: MockSignal

@runtime_checkable
class MockErrorHandlerProtocol(Protocol):
    """Protocol for error handler service."""

    handle_error: Mock
    handle_exception: Mock
    report_warning: Mock

@runtime_checkable
class MockOffsetNavigatorProtocol(Protocol):
    """Protocol for offset navigator service."""

    # Signals
    offset_changed: MockSignal
    navigation_bounds_changed: MockSignal
    step_size_changed: MockSignal

    # Methods
    get_current_state: Mock
    set_offset: Mock
    set_rom_size: Mock
    set_step_size: Mock
    move_forward: Mock
    move_backward: Mock
    validate_offset: Mock
    get_valid_range: Mock

@runtime_checkable
class MockPreviewCoordinatorProtocol(Protocol):
    """Protocol for preview coordinator service."""

    # Signals
    preview_requested: MockSignal
    preview_ready: MockSignal
    preview_error: MockSignal
    preview_cleared: MockSignal

    # Methods
    request_preview: Mock
    request_preview_with_debounce: Mock
    clear_preview: Mock
    cancel_pending_previews: Mock
    set_preview_widget: Mock
    cleanup_workers: Mock

@runtime_checkable
class MockSpritesRegistryProtocol(Protocol):
    """Protocol for sprites registry service."""

    # Signals
    sprite_added: MockSignal
    sprite_removed: MockSignal
    sprites_cleared: MockSignal
    sprites_imported: MockSignal

    # Methods
    add_sprite: Mock
    remove_sprite: Mock
    get_sprite: Mock
    get_all_sprites: Mock
    get_sprite_count: Mock
    clear_sprites: Mock
    import_sprites: Mock
    export_sprites: Mock
    has_sprite_at: Mock
    get_sprites_in_range: Mock

@runtime_checkable
class MockWorkerManagerProtocol(Protocol):
    """Protocol for worker manager service."""

    # Signals
    worker_started: MockSignal
    worker_finished: MockSignal
    worker_error: MockSignal

    # Methods
    create_worker: Mock
    cleanup_worker: Mock
    cleanup_all_workers: Mock
    get_active_workers: Mock

@runtime_checkable
class MockSignalCoordinatorProtocol(Protocol):
    """Protocol for signal coordinator."""

    # External compatibility signals
    offset_changed: MockSignal
    sprite_found: MockSignal
    preview_requested: MockSignal
    search_started: MockSignal
    search_completed: MockSignal

    # Internal coordination signals
    tab_switch_requested: MockSignal
    update_title_requested: MockSignal
    status_message: MockSignal
    navigation_enabled: MockSignal
    step_size_synchronized: MockSignal
    preview_update_queued: MockSignal
    preview_generation_started: MockSignal
    preview_generation_completed: MockSignal

    # Methods
    queue_offset_update: Mock
    queue_preview_update: Mock
    coordinate_preview_update: Mock
    block_signals_temporarily: Mock
    register_worker: Mock
    unregister_worker: Mock
    is_searching: Mock
    get_current_offset: Mock
    cleanup: Mock

@runtime_checkable
class MockDialogTabsProtocol(Protocol):
    """Protocol for manual offset dialog tabs collection."""

    browse_tab: Mock
    smart_tab: Mock
    history_tab: Mock

@runtime_checkable
class MockBrowseTabProtocol(Protocol):
    """Protocol for browse tab."""

    # Signals
    offset_changed: MockSignal
    find_next_clicked: MockSignal
    find_prev_clicked: MockSignal

    # Methods
    get_offset: Mock
    set_offset: Mock
    set_rom_size: Mock

    # Widgets
    slider: Mock

@runtime_checkable
class MockSmartTabProtocol(Protocol):
    """Protocol for smart tab."""

    # Signals
    smart_mode_changed: MockSignal
    offset_requested: MockSignal

    # Widgets
    smart_checkbox: Mock
    locations_combo: Mock

@runtime_checkable
class MockHistoryTabProtocol(Protocol):
    """Protocol for history tab."""

    # Signals
    sprite_selected: MockSignal
    clear_requested: MockSignal

    # Methods
    add_sprite: Mock
    clear_sprites: Mock

    # Widgets
    list_widget: Mock
    summary_label: Mock
    clear_button: Mock
