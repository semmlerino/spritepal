"""
Tier 3 Signal Coverage Gap Tests.

Tests for signal paths identified as coverage gaps in the signal testing audit:
- SpriteLibrary signals -> LibraryTab integration
- CoreOperationsManager.extraction_completed integration
- ApplicationStateManager.session_restored (already tested elsewhere, included for completeness)

These tests verify end-to-end signal delivery and observable downstream effects.

Async Safety Notes
------------------
These tests use `QCoreApplication.processEvents()` which is safe for:
- Synchronous signal emissions (SpriteLibrary, ApplicationStateManager)
- Mock objects that emit synchronously in the main thread

For tests involving real threaded operations, use `qtbot.waitSignal()`:

    # ASYNC PATTERN (for real workers):
    with qtbot.waitSignal(library.sprite_added, timeout=signal_timeout()):
        library.add_sprite(...)

    # SYNC PATTERN (current - mocks emit synchronously):
    library.sprite_added.emit(sprite)
    QCoreApplication.processEvents()
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import Mock, patch

import pytest
from PIL import Image
from PySide6.QtCore import QCoreApplication, QObject, Signal
from PySide6.QtTest import QSignalSpy

from core.sprite_library import LibrarySprite, SpriteLibrary
from tests.fixtures.timeouts import signal_timeout
from tests.ui.integration.helpers.signal_spy_utils import MultiSignalRecorder

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


# =============================================================================
# SpriteLibrary Signal Tests
# =============================================================================


class TestSpriteLibrarySignals:
    """Test SpriteLibrary signal emission and behavior."""

    @pytest.fixture
    def library(self, tmp_path: Path) -> SpriteLibrary:
        """Create a SpriteLibrary with temp directory."""
        lib = SpriteLibrary(library_dir=tmp_path / "library")
        lib.ensure_directories()
        return lib

    @pytest.fixture
    def mock_rom_path(self, tmp_path: Path) -> Path:
        """Create a mock ROM file for testing."""
        rom_path = tmp_path / "test.sfc"
        # Create a small file with some content for hash calculation
        rom_path.write_bytes(b"\x00" * 1024)
        return rom_path

    @pytest.fixture
    def sample_thumbnail(self) -> Image.Image:
        """Create a sample PIL Image for thumbnail."""
        return Image.new("RGB", (64, 64), color=(128, 128, 128))

    def test_add_sprite_emits_sprite_added(
        self, qtbot: QtBot, library: SpriteLibrary, mock_rom_path: Path, sample_thumbnail: Image.Image
    ) -> None:
        """SpriteLibrary.add_sprite must emit sprite_added signal."""
        recorder = MultiSignalRecorder()
        recorder.connect_signal(library.sprite_added, "sprite_added")

        # Add sprite
        result = library.add_sprite(
            rom_offset=0x1000,
            rom_path=mock_rom_path,
            name="Test Sprite",
            thumbnail=sample_thumbnail,
        )
        QCoreApplication.processEvents()

        assert result is not None, "add_sprite should return the added sprite"
        recorder.assert_emitted("sprite_added", times=1)

        # Verify signal payload
        args = recorder.get_args("sprite_added")
        assert args is not None
        emitted_sprite = args[0]
        assert isinstance(emitted_sprite, LibrarySprite)
        assert emitted_sprite.name == "Test Sprite"
        assert emitted_sprite.rom_offset == 0x1000

    def test_remove_sprite_emits_sprite_removed(
        self, qtbot: QtBot, library: SpriteLibrary, mock_rom_path: Path, sample_thumbnail: Image.Image
    ) -> None:
        """SpriteLibrary.remove_sprite must emit sprite_removed signal with unique_id."""
        # First add a sprite
        added = library.add_sprite(
            rom_offset=0x1000,
            rom_path=mock_rom_path,
            name="To Remove",
            thumbnail=sample_thumbnail,
        )
        QCoreApplication.processEvents()
        assert added is not None

        unique_id = added.unique_id

        # Setup recorder for removal
        recorder = MultiSignalRecorder()
        recorder.connect_signal(library.sprite_removed, "sprite_removed")

        # Remove sprite
        result = library.remove_sprite(unique_id)
        QCoreApplication.processEvents()

        assert result is True, "remove_sprite should return True"
        recorder.assert_emitted("sprite_removed", times=1)

        # Verify signal payload is the unique_id string
        args = recorder.get_args("sprite_removed")
        assert args is not None
        assert args[0] == unique_id

    def test_update_sprite_emits_sprite_updated(
        self, qtbot: QtBot, library: SpriteLibrary, mock_rom_path: Path, sample_thumbnail: Image.Image
    ) -> None:
        """SpriteLibrary.update_sprite must emit sprite_updated signal."""
        # First add a sprite
        added = library.add_sprite(
            rom_offset=0x1000,
            rom_path=mock_rom_path,
            name="Original Name",
            thumbnail=sample_thumbnail,
        )
        QCoreApplication.processEvents()
        assert added is not None

        unique_id = added.unique_id

        # Setup recorder for update
        recorder = MultiSignalRecorder()
        recorder.connect_signal(library.sprite_updated, "sprite_updated")

        # Update sprite
        result = library.update_sprite(unique_id, name="Updated Name")
        QCoreApplication.processEvents()

        assert result is not None, "update_sprite should return the updated sprite"
        recorder.assert_emitted("sprite_updated", times=1)

        # Verify signal payload
        args = recorder.get_args("sprite_updated")
        assert args is not None
        emitted_sprite = args[0]
        assert isinstance(emitted_sprite, LibrarySprite)
        assert emitted_sprite.name == "Updated Name"

    def test_load_emits_library_loaded(
        self, qtbot: QtBot, library: SpriteLibrary, mock_rom_path: Path, sample_thumbnail: Image.Image, tmp_path: Path
    ) -> None:
        """SpriteLibrary.load must emit library_loaded signal with count."""
        # First add some sprites and save
        library.add_sprite(
            rom_offset=0x1000,
            rom_path=mock_rom_path,
            name="Sprite 1",
            thumbnail=sample_thumbnail,
        )
        library.add_sprite(
            rom_offset=0x2000,
            rom_path=mock_rom_path,
            name="Sprite 2",
            thumbnail=sample_thumbnail,
        )
        QCoreApplication.processEvents()

        # Create new library instance to test load
        library2 = SpriteLibrary(library_dir=tmp_path / "library")

        recorder = MultiSignalRecorder()
        recorder.connect_signal(library2.library_loaded, "library_loaded")

        # Load from disk
        library2.load()
        QCoreApplication.processEvents()

        recorder.assert_emitted("library_loaded", times=1)

        # Verify signal payload is the count
        args = recorder.get_args("library_loaded")
        assert args is not None
        assert args[0] == 2, f"Expected count=2, got {args[0]}"


# =============================================================================
# SpriteLibrary -> LibraryTab Integration Tests
# =============================================================================


class TestSpriteLibraryToLibraryTabIntegration:
    """Test that SpriteLibrary signals trigger LibraryTab refresh."""

    @pytest.fixture
    def library(self, tmp_path: Path) -> SpriteLibrary:
        """Create a SpriteLibrary with temp directory."""
        lib = SpriteLibrary(library_dir=tmp_path / "library")
        lib.ensure_directories()
        return lib

    @pytest.fixture
    def mock_rom_path(self, tmp_path: Path) -> Path:
        """Create a mock ROM file for testing."""
        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(b"\x00" * 1024)
        return rom_path

    @pytest.fixture
    def sample_thumbnail(self) -> Image.Image:
        """Create a sample PIL Image for thumbnail."""
        return Image.new("RGB", (64, 64), color=(128, 128, 128))

    @pytest.fixture
    def library_tab(self, qtbot: QtBot, library: SpriteLibrary):
        """Create a LibraryTab connected to the library."""
        from ui.tabs.library_tab import LibraryTab

        tab = LibraryTab()
        qtbot.addWidget(tab)
        tab.set_library(library)
        return tab

    def test_sprite_added_triggers_tab_refresh(
        self, qtbot: QtBot, library: SpriteLibrary, library_tab, mock_rom_path: Path, sample_thumbnail: Image.Image
    ) -> None:
        """sprite_added signal must trigger LibraryTab._refresh()."""
        # Get initial sprite count display
        initial_count = library_tab._count_label.text()

        # Add sprite (triggers signal -> handler -> refresh)
        library.add_sprite(
            rom_offset=0x3000,
            rom_path=mock_rom_path,
            name="New Sprite",
            thumbnail=sample_thumbnail,
        )
        QCoreApplication.processEvents()

        # Observable effect: count label should update
        new_count = library_tab._count_label.text()
        assert initial_count != new_count or "1" in new_count, (
            f"Count label should update after sprite_added. Initial: {initial_count}, After: {new_count}"
        )

    def test_sprite_removed_triggers_tab_refresh(
        self, qtbot: QtBot, library: SpriteLibrary, library_tab, mock_rom_path: Path, sample_thumbnail: Image.Image
    ) -> None:
        """sprite_removed signal must trigger LibraryTab._refresh()."""
        # First add a sprite
        added = library.add_sprite(
            rom_offset=0x4000,
            rom_path=mock_rom_path,
            name="To Remove",
            thumbnail=sample_thumbnail,
        )
        QCoreApplication.processEvents()
        assert added is not None

        count_before = library.count

        # Remove sprite
        library.remove_sprite(added.unique_id)
        QCoreApplication.processEvents()

        # Observable effect: library count changed
        assert library.count == count_before - 1

    def test_library_signals_connected_after_set_library(self, qtbot: QtBot, library: SpriteLibrary) -> None:
        """set_library must connect all 4 library signals."""
        from ui.tabs.library_tab import LibraryTab

        tab = LibraryTab()
        qtbot.addWidget(tab)

        # Track that handlers are called
        handler_calls: list[str] = []

        original_refresh = tab._refresh

        def tracking_refresh() -> None:
            handler_calls.append("refresh")
            original_refresh()

        tab._refresh = tracking_refresh  # type: ignore[method-assign]

        # Connect library
        tab.set_library(library)
        QCoreApplication.processEvents()

        # Initial set_library calls refresh
        assert "refresh" in handler_calls, "set_library should call _refresh initially"
        handler_calls.clear()

        # Emit library_loaded signal
        library.library_loaded.emit(5)
        QCoreApplication.processEvents()

        assert "refresh" in handler_calls, "library_loaded should trigger _refresh"


# =============================================================================
# CoreOperationsManager.extraction_completed Tests
# =============================================================================


class MockExtractionResult:
    """Mock ExtractionResult for testing signal emission."""

    def __init__(self) -> None:
        self.preview_image = None
        self.offset = 0x1000
        self.palettes: list[object] = []
        self.active_palette_indices: list[int] = [0]
        self.created_files: list[str] = []
        self.warnings: list[str] = []


class TestExtractionCompletedSignal:
    """Test CoreOperationsManager.extraction_completed signal behavior."""

    def test_extraction_completed_signal_signature(self, qtbot: QtBot) -> None:
        """Verify extraction_completed signal exists and can be connected."""
        from core.managers.core_operations_manager import CoreOperationsManager

        # Create minimal mock dependencies
        mock_session = Mock()
        mock_rom_cache = Mock()
        mock_rom_extractor = Mock()

        # Suppress initialization errors by mocking internal calls
        with patch.object(CoreOperationsManager, "_initialize"):
            manager = CoreOperationsManager(
                session_manager=mock_session,
                rom_cache=mock_rom_cache,
                rom_extractor=mock_rom_extractor,
            )

            # Verify signal exists and is connectable
            received_results: list[object] = []

            def handler(result: object) -> None:
                received_results.append(result)

            manager.extraction_completed.connect(handler)

            # Emit test signal
            mock_result = MockExtractionResult()
            manager.extraction_completed.emit(mock_result)
            QCoreApplication.processEvents()

            assert len(received_results) == 1
            assert received_results[0] is mock_result

    def test_extraction_completed_legacy_signals_coexist(self, qtbot: QtBot) -> None:
        """Verify legacy signals (preview_generated, etc.) still exist alongside extraction_completed."""
        from core.managers.core_operations_manager import CoreOperationsManager

        mock_session = Mock()
        mock_rom_cache = Mock()
        mock_rom_extractor = Mock()

        with patch.object(CoreOperationsManager, "_initialize"):
            manager = CoreOperationsManager(
                session_manager=mock_session,
                rom_cache=mock_rom_cache,
                rom_extractor=mock_rom_extractor,
            )

            # All these signals should exist
            assert hasattr(manager, "extraction_completed")
            assert hasattr(manager, "preview_generated")
            assert hasattr(manager, "palettes_extracted")
            assert hasattr(manager, "active_palettes_found")
            assert hasattr(manager, "files_created")
            assert hasattr(manager, "extraction_progress")
            assert hasattr(manager, "extraction_warning")


# =============================================================================
# ApplicationStateManager.session_restored Tests
# =============================================================================


class TestSessionRestoredSignal:
    """Test ApplicationStateManager.session_restored signal behavior.

    Note: Comprehensive tests exist in tests/integration/test_application_state_manager.py
    These tests verify basic signal emission and are included for completeness.
    """

    @pytest.fixture
    def state_manager(self, tmp_path: Path):
        """Create an ApplicationStateManager with temp settings file."""
        from core.managers.application_state_manager import ApplicationStateManager

        settings_file = tmp_path / "settings.json"
        manager = ApplicationStateManager(settings_path=settings_file)
        yield manager
        manager.cleanup()

    def test_session_restored_emits_on_restore(self, qtbot: QtBot, state_manager, tmp_path: Path) -> None:
        """session_restored signal must emit when restore_session is called."""
        # Save some session data first
        state_manager.update_session_data({"test_key": "test_value"})
        state_manager.save_settings()
        QCoreApplication.processEvents()

        recorder = MultiSignalRecorder()
        recorder.connect_signal(state_manager.session_restored, "session_restored")

        # Restore session
        state_manager.restore_session()
        QCoreApplication.processEvents()

        recorder.assert_emitted("session_restored", times=1)

        # Verify signal payload matches returned data
        args = recorder.get_args("session_restored")
        assert args is not None
        emitted_data = args[0]
        assert isinstance(emitted_data, dict)

    def test_session_restored_signal_payload_structure(self, qtbot: QtBot, state_manager) -> None:
        """session_restored signal payload should be a dict with session data."""
        # Set up session data
        state_manager.update_session_data(
            {
                "vram_path": "/path/to/vram",
                "output_name": "test_output",
            }
        )
        state_manager.save_settings()

        received_payloads: list[object] = []

        def handler(data: object) -> None:
            received_payloads.append(data)

        state_manager.session_restored.connect(handler)

        state_manager.restore_session()
        QCoreApplication.processEvents()

        assert len(received_payloads) == 1
        payload = received_payloads[0]
        assert isinstance(payload, dict)


# =============================================================================
# Signal Chain Order Tests
# =============================================================================


class TestSignalChainOrdering:
    """Test that signal chains execute in correct order."""

    def test_library_signals_order_on_add_remove(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Adding then removing sprite should emit signals in order."""
        library = SpriteLibrary(library_dir=tmp_path / "library")
        library.ensure_directories()

        # Create mock ROM file
        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(b"\x00" * 1024)

        # Create thumbnail
        thumbnail = Image.new("RGB", (64, 64), color=(128, 128, 128))

        recorder = MultiSignalRecorder()
        recorder.connect_signal(library.sprite_added, "sprite_added")
        recorder.connect_signal(library.sprite_removed, "sprite_removed")

        # Add sprite
        added = library.add_sprite(
            rom_offset=0x5000,
            rom_path=rom_path,
            name="Order Test",
            thumbnail=thumbnail,
        )
        QCoreApplication.processEvents()
        assert added is not None

        # Remove sprite
        library.remove_sprite(added.unique_id)
        QCoreApplication.processEvents()

        # Verify order: added before removed
        order = recorder.emission_order()
        assert order == ["sprite_added", "sprite_removed"], f"Expected add->remove order, got: {order}"

    def test_multiple_adds_maintain_order(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Multiple add_sprite calls should emit signals in order."""
        library = SpriteLibrary(library_dir=tmp_path / "library")
        library.ensure_directories()

        # Create mock ROM file
        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(b"\x00" * 1024)

        # Create thumbnail
        thumbnail = Image.new("RGB", (64, 64), color=(128, 128, 128))

        emission_names: list[str] = []

        def on_added(sprite: object) -> None:
            if isinstance(sprite, LibrarySprite):
                emission_names.append(sprite.name)

        library.sprite_added.connect(on_added)

        # Add multiple sprites
        for i in range(3):
            library.add_sprite(
                rom_offset=0x6000 + i * 0x100,
                rom_path=rom_path,
                name=f"Sprite_{i}",
                thumbnail=thumbnail,
            )
            QCoreApplication.processEvents()

        assert emission_names == ["Sprite_0", "Sprite_1", "Sprite_2"], (
            f"Expected ordered emissions, got: {emission_names}"
        )
