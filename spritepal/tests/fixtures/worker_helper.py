"""
Test worker helpers for synchronous execution in tests
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from core.workers import ROMExtractionWorker, VRAMExtractionWorker

# Test characteristics: Thread safety concerns
pytestmark = [pytest.mark.headless]

class SyncWorkerMixin:
    """Mixin for test workers that run synchronously instead of in a thread.

    Provides common overrides for QThread methods to enable synchronous
    execution in tests. Classes using this mixin must have a run() method.
    """

    def start(self) -> None:
        """Override start to run synchronously for tests."""
        self.run()  # type: ignore[attr-defined]

    def isRunning(self) -> bool:
        """Override for test compatibility - always returns False."""
        return False

    def quit(self) -> None:
        """Override for test compatibility - no-op."""

    def wait(self, timeout: int = 0) -> bool:
        """Override for test compatibility - always returns True."""
        return True


class SyncExtractionWorker(SyncWorkerMixin, VRAMExtractionWorker):
    """Test-specific ExtractionWorker that runs synchronously."""


class SyncROMExtractionWorker(SyncWorkerMixin, ROMExtractionWorker):
    """Test-specific ROMExtractionWorker that runs synchronously."""

class SyncExtractionController:
    """Test-specific controller that uses synchronous workers"""

    def __init__(self, main_window: Any) -> None:
        self.main_window = main_window
        self.worker: SyncExtractionWorker | None = None
        self.rom_worker: SyncROMExtractionWorker | None = None

        # Get managers
        from core.managers import (
            get_extraction_manager,
            get_injection_manager,
            get_session_manager,
        )
        self.session_manager = get_session_manager()
        self.extraction_manager = get_extraction_manager()
        self.injection_manager = get_injection_manager()

    def start_extraction(self) -> None:
        """Start extraction with test worker"""
        # Get parameters from UI
        params = self.main_window.get_extraction_params()

        # Validate parameters using extraction manager
        try:
            self.extraction_manager.validate_extraction_params(params)
        except Exception as e:
            self.main_window.extraction_failed(str(e))
            return

        # Create test worker (synchronous)
        self.worker = SyncExtractionWorker(params)
        self.worker.progress.connect(self._on_progress)
        self.worker.preview_ready.connect(self._on_preview_ready)
        self.worker.preview_image_ready.connect(self._on_preview_image_ready)
        self.worker.palettes_ready.connect(self._on_palettes_ready)
        self.worker.active_palettes_ready.connect(self._on_active_palettes_ready)
        self.worker.extraction_finished.connect(self._on_extraction_finished)
        self.worker.error.connect(self._on_extraction_error)

        # Start worker (will run synchronously)
        self.worker.start()

    def _on_progress(self, message: str) -> None:
        """Handle progress updates"""
        self.main_window.status_bar.showMessage(message)

    def _on_preview_ready(self, pixmap: Any, tile_count: int) -> None:
        """Handle preview ready"""
        self.main_window.sprite_preview.set_preview(pixmap, tile_count)
        self.main_window.preview_info.setText(f"Tiles: {tile_count}")

    def _on_preview_image_ready(self, pil_image: Any) -> None:
        """Handle preview PIL image ready"""
        self.main_window.sprite_preview.set_grayscale_image(pil_image)

    def _on_palettes_ready(self, palettes: dict[str, list[tuple[int, int, int]]]) -> None:
        """Handle palettes ready"""
        self.main_window.palette_preview.set_all_palettes(palettes)
        self.main_window.sprite_preview.set_palettes(palettes)

    def _on_active_palettes_ready(self, active_palettes: list[int]) -> None:
        """Handle active palettes ready"""
        self.main_window.palette_preview.highlight_active_palettes(active_palettes)

    def _on_extraction_finished(self, extracted_files: list[str]) -> None:
        """Handle extraction finished"""
        self.main_window.extraction_complete(extracted_files)
        self._cleanup_worker()

    def _on_extraction_error(self, error_message: str) -> None:
        """Handle extraction error"""
        self.main_window.extraction_failed(error_message)
        self._cleanup_worker()

    def _cleanup_worker(self) -> None:
        """Cleanup worker (simplified for test)"""
        self.worker = None

class WorkerHelper:
    """Helper for creating test injection workers and scenarios"""

    def __init__(self, temp_dir: str) -> None:
        from tests.fixtures.test_data_factory import TestDataFactory

        self.temp_dir = Path(temp_dir)

        # Use TestDataFactory for file creation (DRY consolidation)
        paths = TestDataFactory.create_test_files(self.temp_dir, minimal=True)
        self.sprite_file = paths.sprite_path
        self.vram_file = paths.vram_path
        self.rom_file = paths.rom_path

    def create_vram_injection_worker(self) -> Any:
        """Create VRAM injection worker"""
        worker = self._create_base_worker()
        worker.vram_input = str(self.vram_file)
        worker.offset = 0xC000
        return worker

    def create_rom_injection_worker(self) -> Any:
        """Create ROM injection worker"""
        from unittest.mock import Mock

        worker = self._create_base_worker()
        worker.rom_path = str(self.rom_file)
        worker.offset = 0x1000
        worker.compression_info = Mock()
        return worker

    def _create_base_worker(self) -> Any:
        """Create base mock worker with common QThread setup."""
        from unittest.mock import Mock

        from PySide6.QtCore import QThread

        worker = Mock(spec=QThread)
        worker.sprite_path = str(self.sprite_file)

        # Add required signal attributes
        worker.progress = Mock()
        worker.progress_percent = Mock()
        worker.finished = Mock()

        # Add QThread methods with proper return values
        worker.isRunning.return_value = False
        worker.quit.return_value = None
        worker.wait.return_value = True

        return worker

    def create_vram_injection_params(self) -> dict[str, Any]:
        """Create VRAM injection parameters"""
        return {
            "mode": "vram",
            "sprite_path": str(self.sprite_file),
            "vram_input": str(self.vram_file),
            "vram_output": str(self.temp_dir / "output_VRAM.dmp"),
            "offset": 0xC000,
        }

    def create_rom_injection_params(self) -> dict[str, Any]:
        """Create ROM injection parameters"""
        return {
            "mode": "rom",
            "sprite_path": str(self.sprite_file),
            "rom_path": str(self.rom_file),
            "sprite_offset": 0x1000,
            "output_rom": str(self.temp_dir / "output_ROM.smc"),
        }

    def cleanup(self) -> None:
        """Cleanup test files"""
        import shutil
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
