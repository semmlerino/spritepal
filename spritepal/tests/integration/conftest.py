"""
Integration test fixtures that use real components without mocking.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

# NOTE: pythonpath configured in pyproject.toml - no sys.path manipulation needed

# NOTE: qt_app fixture is provided by root conftest.py (session-scoped)
# Do not redefine it here to avoid fixture shadowing issues.

# NOTE: Wait helpers (wait_for, wait_for_condition, etc.) are provided by
# root conftest.py which imports from tests.fixtures.qt_waits


@pytest.fixture(scope="function")
def managers_initialized(qt_app, request, tmp_path):
    """Initialize managers for integration tests.

    If session_managers is already active, this fixture is a no-op to avoid
    conflicting cleanup.

    Uses isolated settings path to avoid polluting repository root.
    """
    from core.managers.registry import ManagerRegistry, cleanup_managers, initialize_managers
    from tests.fixtures.core_fixtures import is_session_managers_active

    registry = ManagerRegistry()
    was_already_initialized = registry.is_initialized()

    if not was_already_initialized:
        # Use isolated temp settings path - CRITICAL for preventing repo pollution
        settings_path = tmp_path / ".test_integration_settings.json"
        initialize_managers("TestApp_Integration", settings_path=settings_path)

        # Register UI factories with DI container (after managers are initialized)
        from ui import register_ui_factories
        register_ui_factories()

    yield

    # Only cleanup if WE initialized AND session_managers is NOT active
    # If session_managers is active, let it own the lifecycle
    if not was_already_initialized and not is_session_managers_active():
        cleanup_managers()


# NOTE: temp_dir fixture removed - use pytest's built-in tmp_path fixture instead
# All fixtures below have been updated to accept tmp_path


@pytest.fixture
def test_rom_data():
    """Generate test ROM data with known content."""
    # Create a 1MB test ROM
    rom_size = 1024 * 1024
    rom_data = bytearray(rom_size)

    # Add some recognizable patterns at known offsets
    # Pattern 1: Simple incrementing bytes at 0x1000
    for i in range(256):
        rom_data[0x1000 + i] = i % 256

    # Pattern 2: Tile-like data at 0x2000 (32 bytes per tile)
    for tile in range(16):
        for byte_idx in range(32):
            rom_data[0x2000 + tile * 32 + byte_idx] = (tile * 2 + byte_idx) % 256

    # Pattern 3: Sprite-like data at 0x10000
    for i in range(8192):  # 256 tiles
        rom_data[0x10000 + i] = (i % 16) * 16 + (i // 16) % 16

    return bytes(rom_data)


@pytest.fixture
def test_rom_with_sprites(tmp_path, test_rom_data, real_kirby_rom):
    """Create a test ROM for integration tests.

    PRIORITY: Uses real Kirby ROM if available (has real HAL-compressed sprites).
    FALLBACK: Uses synthetic test data (no valid HAL sprites - tests will skip).

    Tests that require HAL decompression should check `if not rom_info['sprites']`
    and skip appropriately.

    For tests that MUST have real sprites, use the test_rom_with_real_sprites
    fixture instead (it calls pytest.skip() automatically if ROM unavailable).
    """
    rom_path = tmp_path / "test_rom.sfc"

    if real_kirby_rom is not None:
        # Use real Kirby ROM - has actual HAL-compressed sprites
        rom_data = real_kirby_rom.read_bytes()
        rom_path.write_bytes(rom_data)

        # Known sprite locations in Kirby Super Star (USA)
        return {
            'path': rom_path,
            'sprites': [
                {
                    'offset': 0x200000,
                    'compressed_size': 65464,
                    'decompressed_size': 7744,
                    'tile_count': 242,
                },
                {
                    'offset': 0x206000,
                    'compressed_size': 40888,
                    'decompressed_size': 832,
                    'tile_count': 26,
                },
            ],
        }
    else:
        # Use synthetic data - NO valid HAL-compressed sprites
        # Tests that need HAL decompression should skip via:
        #   if not rom_info['sprites']: pytest.skip("No sprites...")
        rom_path.write_bytes(test_rom_data)

        return {
            'path': rom_path,
            'sprites': [],  # Empty: synthetic data has no valid HAL sprites
        }


@pytest.fixture
def real_kirby_rom():
    """Provide path to real Kirby ROM if available for integration testing.

    Returns None if ROM not available. Tests using this MUST handle None case
    by calling pytest.skip() or using test_rom_with_real_sprites fixture.

    FIX T2.1: Uses multiple candidate paths for robustness under xdist.
    Set SPRITEPAL_KIRBY_ROM env var in CI to specify exact location.
    """
    # Try multiple locations in order of preference
    candidates = [
        # Environment variable (CI/CD can set this)
        Path(os.environ.get("SPRITEPAL_KIRBY_ROM", "")),
        # Relative to this file (integration/conftest.py -> spritepal/ -> exhal-master/)
        Path(__file__).parent.parent.parent.parent / "Kirby Super Star (USA).sfc",
        # Relative to spritepal/ (legacy location)
        Path(__file__).parent.parent.parent / "Kirby Super Star (USA).sfc",
        # Legacy relative path (may work in some working directories)
        Path("../Kirby Super Star (USA).sfc"),
    ]

    for path in candidates:
        # Check path string is non-empty AND path exists AND is a file (not directory)
        if str(path) and path.exists() and path.is_file():
            return path.resolve()  # Return absolute path for reliability

    return None


@pytest.fixture
def test_rom_with_real_sprites(tmp_path, real_kirby_rom):
    """Create a test ROM using REAL Kirby ROM data.

    Use this fixture for tests that specifically need real compressed sprite data.
    The fixture calls pytest.skip() automatically if the ROM is unavailable.
    """
    if real_kirby_rom is None:
        pytest.skip("Real Kirby ROM required but not available")

    rom_path = tmp_path / "test_rom.sfc"
    rom_data = real_kirby_rom.read_bytes()
    rom_path.write_bytes(rom_data)

    # Known sprite locations in Kirby ROM
    return {
        'path': rom_path,
        'sprites': [
            {
                'offset': 0x200000,
                'compressed_size': 65464,
                'decompressed_size': 7744,
                'tile_count': 242,
            },
            {
                'offset': 0x206000,
                'compressed_size': 40888,
                'decompressed_size': 832,
                'tile_count': 26,
            },
        ],
    }


@pytest.fixture
def rom_extraction_panel(qtbot, managers_initialized):
    """Create a real ROM extraction panel for testing.

    Includes cleanup to reset the dialog singleton to prevent
    test pollution when multiple tests open the manual offset dialog.
    """
    from core.di_container import inject
    from core.managers.core_operations_manager import CoreOperationsManager
    from ui.rom_extraction.offset_dialog_manager import OffsetDialogManager
    from ui.rom_extraction_panel import ROMExtractionPanel

    extraction_manager = inject(CoreOperationsManager)
    panel = ROMExtractionPanel(extraction_manager=extraction_manager)
    qtbot.addWidget(panel)
    panel.show()

    yield panel

    # Cleanup: Reset the singleton to prevent test pollution
    # This is critical for tests that call panel._open_manual_offset_dialog()
    OffsetDialogManager.reset_singleton()


@pytest.fixture
def manual_offset_dialog(qtbot, managers_initialized):
    """Create a real manual offset dialog for testing.

    This fixture provides a real UnifiedManualOffsetDialog instance for integration
    tests that need to verify actual dialog behavior.

    Important: We don't use qtbot.addWidget() because the dialog may be destroyed by
    managers_initialized cleanup before pytest-qt teardown runs, causing
    "Internal C++ object already deleted" errors.
    """
    import shiboken6

    from core.di_container import inject
    from core.managers.application_state_manager import ApplicationStateManager
    from core.managers.core_operations_manager import CoreOperationsManager
    from core.services.rom_cache import ROMCache
    from ui.dialogs.manual_offset_dialog import UnifiedManualOffsetDialog

    dialog = UnifiedManualOffsetDialog(
        rom_cache=inject(ROMCache),
        settings_manager=inject(ApplicationStateManager),
        extraction_manager=inject(CoreOperationsManager),
    )
    # Don't use qtbot.addWidget() - we manage cleanup ourselves to avoid
    # double-delete when managers_initialized cleanup runs first

    yield dialog

    # Explicitly close dialog if still valid (may already be deleted by manager cleanup)
    try:
        if shiboken6.isValid(dialog):
            dialog.close()
            dialog.deleteLater()
    except RuntimeError:
        pass  # Already deleted, that's fine


@pytest.fixture
def loaded_rom_panel(rom_extraction_panel, test_rom_with_sprites, qtbot):
    """Provide a ROM extraction panel with a test ROM already loaded."""
    rom_info = test_rom_with_sprites
    rom_path = str(rom_info['path'])

    # Load the ROM (method is _load_rom_file, not load_rom)
    rom_extraction_panel._load_rom_file(rom_path)

    # Wait for loading to complete
    qtbot.waitUntil(lambda: rom_extraction_panel.rom_path == rom_path and rom_extraction_panel.rom_size > 0, timeout=1000)

    # Verify ROM is loaded
    assert rom_extraction_panel.rom_path == rom_path
    assert rom_extraction_panel.rom_size > 0

    return rom_extraction_panel, rom_info


# Markers are registered in pyproject.toml and main conftest.py

# NOTE: Wait helpers (wait_for, wait_for_condition, wait_for_widget_ready,
# wait_for_signal_processed, wait_for_layout_update, process_events)
# are now provided by tests.fixtures.qt_waits via pytest_plugins
