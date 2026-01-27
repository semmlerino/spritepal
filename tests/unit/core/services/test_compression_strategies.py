"""Tests for compression strategies."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from core.services.compression_strategies import (
    HALCompressionStrategy,
    RawCompressionStrategy,
    get_compression_strategy,
)
from core.types import CompressionType


class TestHALCompressionStrategy:
    """Tests for HAL compression strategy."""

    def test_compression_type_is_hal(self) -> None:
        strategy = HALCompressionStrategy()
        assert strategy.get_compression_type() == CompressionType.HAL

    def test_should_pad_tiles_true(self) -> None:
        """HAL should pad tiles to clear unused VRAM slots."""
        strategy = HALCompressionStrategy()
        assert strategy.should_pad_tiles() is True

    def test_grid_position_uses_tile_index(self) -> None:
        """HAL uses tile_index_in_block for positioning."""
        strategy = HALCompressionStrategy()
        grid_width = 4

        # Tile with index 5 should go to position (1, 1) * 8 = (8, 8)
        grid_x, grid_y = strategy.get_grid_position(tile_idx=5, sequential_idx=0, grid_width=grid_width)
        assert grid_x == 8  # (5 % 4) * 8
        assert grid_y == 8  # (5 // 4) * 8

    def test_grid_position_fallback_when_no_tile_index(self) -> None:
        """HAL falls back to sequential index when tile_idx is None."""
        strategy = HALCompressionStrategy()
        grid_width = 4

        grid_x, grid_y = strategy.get_grid_position(tile_idx=None, sequential_idx=3, grid_width=grid_width)
        assert grid_x == 24  # (3 % 4) * 8
        assert grid_y == 0  # (3 // 4) * 8

    def test_detect_original_tile_count_from_decompression(self) -> None:
        """HAL decompresses to detect tile count."""
        strategy = HALCompressionStrategy()

        mock_staging = MagicMock()
        mock_injector = MagicMock()
        # 96 bytes = 3 tiles (32 bytes each)
        mock_injector.find_compressed_sprite.return_value = (0, b"\x00" * 96, 0)

        count = strategy.detect_original_tile_count(
            rom_data=b"\x00" * 1000,
            rom_offset=0x100,
            captured_tile_count=5,
            staging_manager=mock_staging,
            rom_injector=mock_injector,
        )

        assert count == 3
        mock_injector.find_compressed_sprite.assert_called_once()

    def test_detect_original_tile_count_fallback_on_error(self) -> None:
        """HAL falls back to captured count on decompression error."""
        strategy = HALCompressionStrategy()

        mock_staging = MagicMock()
        mock_injector = MagicMock()
        mock_injector.find_compressed_sprite.side_effect = Exception("Decompress failed")

        count = strategy.detect_original_tile_count(
            rom_data=b"\x00" * 1000,
            rom_offset=0x100,
            captured_tile_count=5,
            staging_manager=mock_staging,
            rom_injector=mock_injector,
        )

        assert count == 5  # Falls back to captured


class TestRawCompressionStrategy:
    """Tests for RAW compression strategy."""

    def test_compression_type_is_raw(self) -> None:
        strategy = RawCompressionStrategy()
        assert strategy.get_compression_type() == CompressionType.RAW

    def test_should_pad_tiles_false(self) -> None:
        """RAW should not pad (would overwrite adjacent tiles)."""
        strategy = RawCompressionStrategy()
        assert strategy.should_pad_tiles() is False

    def test_grid_position_uses_sequential_index(self) -> None:
        """RAW always uses sequential index regardless of tile_idx."""
        strategy = RawCompressionStrategy()
        grid_width = 4

        # Even with tile_idx=5, should use sequential_idx=2
        grid_x, grid_y = strategy.get_grid_position(tile_idx=5, sequential_idx=2, grid_width=grid_width)
        assert grid_x == 16  # (2 % 4) * 8
        assert grid_y == 0  # (2 // 4) * 8

    def test_detect_original_tile_count_with_slot_detected(self) -> None:
        """RAW uses slot detection when boundary found."""
        strategy = RawCompressionStrategy()

        mock_staging = MagicMock()
        mock_staging.detect_raw_slot_size.return_value = 8
        mock_injector = MagicMock()

        count = strategy.detect_original_tile_count(
            rom_data=b"\x00" * 1000,
            rom_offset=0x100,
            captured_tile_count=5,
            staging_manager=mock_staging,
            rom_injector=mock_injector,
        )

        assert count == 8
        mock_staging.detect_raw_slot_size.assert_called_once()

    def test_detect_original_tile_count_without_slot(self) -> None:
        """RAW falls back to captured count when no slot boundary."""
        strategy = RawCompressionStrategy()

        mock_staging = MagicMock()
        mock_staging.detect_raw_slot_size.return_value = None
        mock_injector = MagicMock()

        count = strategy.detect_original_tile_count(
            rom_data=b"\x00" * 1000,
            rom_offset=0x100,
            captured_tile_count=5,
            staging_manager=mock_staging,
            rom_injector=mock_injector,
        )

        assert count == 5  # Falls back to captured


class TestGetCompressionStrategy:
    """Tests for strategy factory function."""

    def test_returns_raw_when_is_raw_true(self) -> None:
        strategy = get_compression_strategy(is_raw=True)
        assert isinstance(strategy, RawCompressionStrategy)

    def test_returns_hal_when_is_raw_false(self) -> None:
        strategy = get_compression_strategy(is_raw=False)
        assert isinstance(strategy, HALCompressionStrategy)
