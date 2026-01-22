"""Integration tests for workers with mocked dependencies."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from PIL import Image

from core.extractor import VramSpriteExtractor
from core.palette_manager import PaletteManager
from core.workers import VRAMExtractionWorker
from utils.constants import (
    BYTES_PER_TILE,
    COLORS_PER_PALETTE,
    SPRITE_PALETTE_END,
    SPRITE_PALETTE_START,
    VRAM_SPRITE_OFFSET,
)

# Serial execution required: Thread safety concerns
pytestmark = [
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.no_manager_setup,
]


class TestVRAMExtractionWorkerHeadless:
    """Test VRAMExtractionWorker with mocked dependencies.

    Note: These tests still require Qt because VRAMExtractionWorker inherits
    from QThread. The 'headless' aspect refers to mocked extraction managers,
    not absence of Qt.
    """

    @pytest.fixture
    def worker_params(self, tmp_path):
        """Create parameters for VRAMExtractionWorker"""
        # Create minimal test files
        vram_data = bytearray(0x10000)
        # Add test tiles
        for i in range(5):
            for j in range(32):
                vram_data[VRAM_SPRITE_OFFSET + i * 32 + j] = (i * 32 + j) % 256

        cgram_data = bytearray(512)
        # Add test colors
        for i in range(256, 512, 2):
            cgram_data[i] = 0x1F
            cgram_data[i + 1] = 0x00

        vram_path = tmp_path / "test.vram"
        cgram_path = tmp_path / "test.cgram"

        vram_path.write_bytes(vram_data)
        cgram_path.write_bytes(cgram_data)

        return {
            "vram_path": str(vram_path),
            "cgram_path": str(cgram_path),
            "output_base": str(tmp_path / "output"),
            "create_grayscale": True,
            "create_metadata": False,
            "oam_path": None,
        }

    def test_worker_logic_without_qt(self, worker_params, qapp):
        """Test worker logic with mocked manager (Qt required for worker instantiation).

        Note: Despite the name, Qt is still required because VRAMExtractionWorker
        inherits from QThread. This test verifies worker logic with a mocked
        extraction manager, not true headless operation.
        """
        # Create mock manager and pass directly to worker
        mock_manager = Mock()

        # Create worker with mocked manager passed directly
        worker = VRAMExtractionWorker(worker_params, extraction_manager=mock_manager)

        # Create test image
        Image.new("P", (128, 64), 0)

        # Mock manager signals to return Mock connections
        mock_connection = Mock()

        mock_manager.extraction_progress = Mock()
        mock_manager.extraction_progress.connect = Mock(return_value=mock_connection)
        mock_manager.palettes_extracted = Mock()
        mock_manager.palettes_extracted.connect = Mock(return_value=mock_connection)
        mock_manager.active_palettes_found = Mock()
        mock_manager.active_palettes_found.connect = Mock(return_value=mock_connection)
        mock_manager.preview_generated = Mock()
        mock_manager.preview_generated.connect = Mock(return_value=mock_connection)

        # Mock the extraction result
        output_path = worker_params["output_base"] + ".png"
        mock_manager.extract_from_vram.return_value = [output_path]

        # Create proper mocks for signals
        progress_mock = Mock()
        progress_mock.emit = Mock()
        preview_mock = Mock()
        preview_mock.emit = Mock()
        preview_image_mock = Mock()
        preview_image_mock.emit = Mock()
        palettes_mock = Mock()
        palettes_mock.emit = Mock()
        active_palettes_mock = Mock()
        active_palettes_mock.emit = Mock()
        finished_mock = Mock()
        finished_mock.emit = Mock()
        error_mock = Mock()
        error_mock.emit = Mock()

        # Replace signals
        worker.progress = progress_mock
        worker.preview_ready = preview_mock
        worker.preview_image_ready = preview_image_mock
        worker.palettes_ready = palettes_mock
        worker.active_palettes_ready = active_palettes_mock
        worker.extraction_finished = finished_mock
        worker.error = error_mock

        # Mock disconnect to avoid signal cleanup issues
        with patch.object(worker, "disconnect_manager_signals") as mock_disconnect:
            mock_disconnect.return_value = None

            # Run the worker logic directly (not as thread)
            worker.run()

        # Check if error was emitted
        if error_mock.emit.called:
            error_msg = error_mock.emit.call_args[0][0]
            print(f"Error emitted: {error_msg}")

        # Verify the key behaviors:
        # 1. Manager was called to extract from VRAM
        assert mock_manager.extract_from_vram.called
        call_kwargs = mock_manager.extract_from_vram.call_args[1]
        assert call_kwargs["vram_path"] == worker_params["vram_path"]
        assert call_kwargs["output_base"] == worker_params["output_base"]

        # 2. Finished signal was emitted with the files
        assert finished_mock.emit.called
        assert finished_mock.emit.call_args[0][0] == [output_path]

        # 3. No error was emitted
        assert not error_mock.emit.called


class TestWorkerBusinessLogic:
    """Test worker business logic extracted from Qt dependencies"""

    def test_extraction_workflow_logic(self, tmp_path):
        """Test the extraction workflow without threading"""
        # Create test files
        vram_data = bytearray(0x10000)
        cgram_data = bytearray(512)

        # Add sprite data
        for i in range(10):
            tile_offset = VRAM_SPRITE_OFFSET + i * BYTES_PER_TILE
            for j in range(BYTES_PER_TILE):
                vram_data[tile_offset + j] = (i + j) % 256

        # Add palette data
        for pal_idx in range(SPRITE_PALETTE_START, SPRITE_PALETTE_END):
            for color_idx in range(COLORS_PER_PALETTE):
                offset = (pal_idx * COLORS_PER_PALETTE + color_idx) * 2
                # Simple color pattern
                color = ((pal_idx << 10) | (color_idx << 5) | color_idx) & 0x7FFF
                cgram_data[offset] = color & 0xFF
                cgram_data[offset + 1] = (color >> 8) & 0xFF

        vram_path = tmp_path / "test.vram"
        cgram_path = tmp_path / "test.cgram"
        output_base = tmp_path / "output"

        vram_path.write_bytes(vram_data)
        cgram_path.write_bytes(cgram_data)

        # Simulate worker workflow
        extractor = VramSpriteExtractor()
        palette_manager = PaletteManager()

        # Extract sprites
        output_file = f"{output_base}.png"
        img, num_tiles = extractor.extract_sprites_grayscale(str(vram_path), output_file)

        assert Path(output_file).exists()
        # Default extraction uses VRAM_SPRITE_SIZE (0x4000 bytes = 512 tiles)
        assert num_tiles == 512

        # Extract palettes
        palette_manager.load_cgram(str(cgram_path))
        sprite_palettes = palette_manager.get_sprite_palettes()
        assert len(sprite_palettes) == 8

        # Create palette files
        main_pal_file = f"{output_base}.pal.json"
        palette_manager.create_palette_json(8, main_pal_file, output_file)
        assert Path(main_pal_file).exists()

        # Create individual palette files
        for pal_idx in range(SPRITE_PALETTE_START, SPRITE_PALETTE_END):
            pal_file = f"{output_base}_pal{pal_idx}.pal.json"
            palette_manager.create_palette_json(pal_idx, pal_file, output_file)
            assert Path(pal_file).exists()

    def test_pixmap_creation_mocked(self, tmp_path):
        """Test pixmap creation can be mocked for headless"""
        # Create a test image
        test_img = Image.new("P", (128, 128), 0)

        # Mock QPixmap in the correct location (core/services/image_utils.py)
        with patch("core.services.image_utils.QPixmap") as mock_pixmap_class:
            mock_pixmap = Mock()
            mock_pixmap.loadFromData.return_value = True
            mock_pixmap_class.return_value = mock_pixmap

            # Import and test the pil_to_qpixmap function
            from core.services.image_utils import pil_to_qpixmap

            # Test pixmap creation
            result = pil_to_qpixmap(test_img)

            # Verify mock was used
            assert mock_pixmap.loadFromData.called
            assert result == mock_pixmap
