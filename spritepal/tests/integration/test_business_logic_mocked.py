"""
Mock-based integration tests that work in any environment.
These tests mock Qt components to test business logic without requiring a display.

MODERNIZED: Uses consolidated mock infrastructure from conftest.py
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

# Import business logic components - no more manual path setup needed
from core.extractor import SpriteExtractor
from core.palette_manager import PaletteManager
from ui.extraction_controller import ExtractionController

# Test categorization
pytestmark = [
    pytest.mark.headless,
    pytest.mark.integration,
]


class TestVRAMExtractionWorkerMocked:
    """Test VRAMExtractionWorker with mocked Qt components using modern fixtures."""

    @patch("core.services.image_utils.QPixmap")
    def test_pixmap_creation_mocked(self, mock_qpixmap):
        """Test pixmap creation with mocked QPixmap"""
        from PIL import Image

        # Create test image
        test_image = Image.new("P", (128, 128), 0)

        # Mock QPixmap
        mock_pixmap_instance = Mock()
        mock_pixmap_instance.loadFromData = Mock(return_value=True)
        mock_qpixmap.return_value = mock_pixmap_instance

        # Import and test the pil_to_qpixmap function
        from core.services.image_utils import pil_to_qpixmap

        # Test pixmap creation
        result = pil_to_qpixmap(test_image)

        # Verify
        assert result == mock_pixmap_instance
        assert mock_pixmap_instance.loadFromData.called

        # Check that PNG data was passed
        call_args = mock_pixmap_instance.loadFromData.call_args[0][0]
        assert isinstance(call_args, bytes)
        assert len(call_args) > 0  # Should have PNG data


class TestBusinessLogicOnly:
    """Test pure business logic without Qt dependencies"""

    def test_extraction_workflow_no_qt(self, standard_test_params):
        """Test the extraction workflow without any Qt components"""
        # Use centralized test data and file paths

        # Test extraction using centralized test files
        extractor = SpriteExtractor()
        output_png = standard_test_params["output_base"] + ".png"
        img, num_tiles = extractor.extract_sprites_grayscale(
            standard_test_params["vram_path"], output_png
        )

        assert Path(output_png).exists()
        assert num_tiles > 0

        # Test palette extraction using centralized test files
        palette_manager = PaletteManager()
        palette_manager.load_cgram(standard_test_params["cgram_path"])

        palettes = palette_manager.get_sprite_palettes()
        assert len(palettes) == 8  # Palettes 8-15

        # Test palette file creation
        pal_file = standard_test_params["output_base"] + ".pal.json"
        palette_manager.create_palette_json(8, pal_file, output_png)
        assert Path(pal_file).exists()
