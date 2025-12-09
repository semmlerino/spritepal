"""
Test worker helpers for synchronous execution in tests
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from core.workers import ROMExtractionWorker, VRAMExtractionWorker

# Test characteristics: Thread safety concerns
pytestmark = [
    pytest.mark.file_io,
    pytest.mark.headless,
    pytest.mark.mock_only,
    pytest.mark.qt_mock,
    pytest.mark.rom_data,
    pytest.mark.serial,
    pytest.mark.worker_threads,
    pytest.mark.ci_safe,
    pytest.mark.signals_slots,
]

class SyncExtractionWorker(VRAMExtractionWorker):
    """Test-specific ExtractionWorker that runs synchronously"""

    def start(self) -> None:
        """Override start to run synchronously for tests"""
        # Don't start a thread, just run directly
        self.run()

    def isRunning(self) -> bool:
        """Override for test compatibility"""
        return False

    def quit(self) -> None:
        """Override for test compatibility"""

    def wait(self, timeout: int = 0) -> bool:
        """Override for test compatibility"""
        return True

class SyncROMExtractionWorker(ROMExtractionWorker):
    """Test-specific ROMExtractionWorker that runs synchronously"""

    def start(self) -> None:
        """Override start to run synchronously for tests"""
        # Don't start a thread, just run directly
        self.run()

    def isRunning(self) -> bool:
        """Override for test compatibility"""
        return False

    def quit(self) -> None:
        """Override for test compatibility"""

    def wait(self, timeout: int = 0) -> bool:
        """Override for test compatibility"""
        return True

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
        self.temp_dir = Path(temp_dir)
        self.sprite_file = self.temp_dir / "test_sprite.png"
        self.vram_file = self.temp_dir / "test_VRAM.dmp"
        self.rom_file = self.temp_dir / "test_ROM.smc"

        # Create minimal test files
        self._create_test_files()

    def _create_test_files(self) -> None:
        """Create minimal test files"""
        # Create minimal PNG file (1x1 pixel)
        png_data = (
            b"\x89PNG\r\n\x1a\n"  # PNG signature
            b"\x00\x00\x00\rIHDR"  # IHDR chunk
            b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"  # 1x1 RGB
            b"\x00\x00\x00\x0cIDATx\x9cc```\x00\x00\x00\x04\x00\x01\xdd\x8d\xb4\x1c"  # Minimal data
            b"\x00\x00\x00\x00IEND\xaeB`\x82"  # IEND
        )
        self.sprite_file.write_bytes(png_data)

        # Create minimal VRAM file (64KB)
        vram_data = bytearray(0x10000)
        self.vram_file.write_bytes(vram_data)

        # Create minimal ROM file (32KB)
        rom_data = bytearray(0x8000)
        self.rom_file.write_bytes(rom_data)

    def create_vram_injection_worker(self) -> Any:
        """Create VRAM injection worker"""
        # Create mock worker that looks like real one
        from unittest.mock import Mock

        from PySide6.QtCore import QThread

        worker = Mock(spec=QThread)
        worker.sprite_path = str(self.sprite_file)
        worker.vram_input = str(self.vram_file)
        worker.offset = 0xC000

        # Add required signal attributes
        worker.progress = Mock()
        worker.progress_percent = Mock()
        worker.finished = Mock()

        # Add QThread methods with proper return values
        worker.isRunning.return_value = False
        worker.quit.return_value = None
        worker.wait.return_value = True

        return worker

    def create_rom_injection_worker(self) -> Any:
        """Create ROM injection worker"""
        from unittest.mock import Mock

        from PySide6.QtCore import QThread

        worker = Mock(spec=QThread)
        worker.sprite_path = str(self.sprite_file)
        worker.rom_path = str(self.rom_file)
        worker.offset = 0x1000

        # Add required signal attributes
        worker.progress = Mock()
        worker.progress_percent = Mock()
        worker.compression_info = Mock()
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
