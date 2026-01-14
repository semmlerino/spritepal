import pytest

pytestmark = [pytest.mark.integration]
import os
import shutil
import struct
import tempfile
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pytest
from PIL import Image

from core.hal_compression import HALCompressor
from core.rom_extractor import ROMExtractor
from core.rom_injector import ROMInjector
from utils.constants import BYTES_PER_TILE


class TestSpriteWorkflowEndToEnd:
    @pytest.fixture
    def workspace(self):
        # Create temp dir
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        # Cleanup
        shutil.rmtree(temp_dir)

    def test_workflow_cycle(self, workspace):
        print(f"\nRunning End-to-End Workflow Test in {workspace}")

        # --- 1. SETUP ---
        rom_path = workspace / "test_rom.sfc"
        sprite_offset = 0x10000  # Move away from header

        # Create dummy 4bpp data (4 tiles)
        raw_sprite_data = bytearray()
        for i in range(4):
            tile = bytearray(32)
            for b in range(32):
                tile[b] = (i + b) % 256
            raw_sprite_data.extend(tile)

        # Compress it
        compressor = HALCompressor()
        compressed_path = workspace / "temp_compressed.bin"

        try:
            compressor.compress_to_file(raw_sprite_data, str(compressed_path))
        except Exception as e:
            pytest.skip(f"HAL Tools not available or failed: {e}")

        with open(compressed_path, "rb") as f:
            compressed_data = f.read()

        # Create ROM with valid SNES Header
        rom_size = 0x200000  # 2MB
        rom_data = bytearray(rom_size)

        # Write valid header at LoROM location (0x7FC0)
        header_offset = 0x7FC0
        # Title (21 bytes)
        title = b"TEST ROM".ljust(21, b" ")
        rom_data[header_offset : header_offset + 21] = title
        # ROM Type (LoROM, FastROM)
        rom_data[header_offset + 21] = 0x30
        # ROM Size (2MB = 0x0B)
        rom_data[header_offset + 23] = 0x0B
        # Checksum (will be calculated later by injector, but we need something for initial validation)
        # For simplicity, we'll set a placeholder and hope the mock/lenient mode handles it
        # or we calculate a real one.

        # Actually, ROMValidator.validate_rom_header checks (checksum ^ complement) == 0xFFFF
        checksum = 0x1234
        complement = 0x1234 ^ 0xFFFF
        struct.pack_into("<H", rom_data, header_offset + 28, complement)
        struct.pack_into("<H", rom_data, header_offset + 30, checksum)

        # Write compressed data at offset
        rom_data[sprite_offset : sprite_offset + len(compressed_data)] = compressed_data

        # Write ROM file
        with open(rom_path, "wb") as f:
            f.write(rom_data)

        # --- 2. EXTRACTION ---
        mock_cache = Mock()
        extractor = ROMExtractor(mock_cache)

        # Use real injector for extraction but mock config
        extractor.sprite_config_loader.find_game_config = Mock(return_value=(None, None))

        output_base = str(workspace / "extracted_sprite")

        png_path, info = extractor.extract_sprite_from_rom(str(rom_path), sprite_offset, output_base, "test_sprite")

        assert Path(png_path).exists()

        # Verify indices 0-15 (The FIX Check)
        with Image.open(png_path) as img:
            assert img.mode == "P"
            data = np.array(img)
            assert data.max() <= 15
            print("Extraction produced valid Indexed PNG (0-15).")

        # --- 3. EDIT (Simulate User Error) ---
        # Open PNG, save as RGB
        edited_png_path = workspace / "edited_sprite.png"
        with Image.open(png_path) as img:
            rgb_img = img.convert("RGB")
            rgb_img.save(edited_png_path)

        # --- 4. INJECTION ---
        injector = ROMInjector()

        output_rom_path = workspace / "output_rom.sfc"

        # Use lenient mode for checksum because our placeholder header isn't perfect
        success, msg = injector.inject_sprite_to_rom(
            str(edited_png_path), str(rom_path), str(output_rom_path), sprite_offset, ignore_checksum=True, force=True
        )

        assert success, f"Injection failed: {msg}"
        print(f"Injection successful: {msg}")

        # Verify output ROM exists
        assert output_rom_path.exists()
