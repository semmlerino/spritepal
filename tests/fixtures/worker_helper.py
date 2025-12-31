"""
Test worker helpers for injection tests.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

# Test characteristics: Thread safety concerns
pytestmark = [pytest.mark.headless]


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
