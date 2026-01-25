"""Unit tests for SheetPalette validation in from_dict()."""

from core.frame_mapping_project import SheetPalette


class TestSheetPaletteValidation:
    """Tests for SheetPalette validation in from_dict()."""

    def test_sheet_palette_clamps_rgb_bounds(self, caplog: object) -> None:
        """RGB values outside 0-255 should be clamped."""
        import logging

        # Cast caplog to proper type for type checker
        from _pytest.logging import LogCaptureFixture

        log = caplog if isinstance(caplog, LogCaptureFixture) else None

        # Create palette data with out-of-bounds RGB values
        data: dict[str, object] = {
            "colors": [
                [0, 0, 0],  # Valid - index 0 (transparent)
                [300, -10, 256],  # All out of bounds - should clamp to (255, 0, 255)
                [128, 128, 128],  # Valid
                *[[0, 0, 0]] * 13,  # Fill remaining
            ],
            "color_mappings": {},
        }

        if log:
            with caplog.at_level(logging.WARNING):
                palette = SheetPalette.from_dict(data)

            # Should have logged a warning about clamping
            assert any("RGB value clamped" in record.message for record in log.records)
        else:
            palette = SheetPalette.from_dict(data)

        # Verify RGB values are clamped
        assert palette.colors[0] == (0, 0, 0)
        assert palette.colors[1] == (255, 0, 255)  # Clamped from (300, -10, 256)
        assert palette.colors[2] == (128, 128, 128)

    def test_sheet_palette_clamps_mapping_indices(self, caplog: object) -> None:
        """Mapping indices outside 0-15 should be clamped."""
        import logging

        # Cast caplog to proper type for type checker
        from _pytest.logging import LogCaptureFixture

        log = caplog if isinstance(caplog, LogCaptureFixture) else None

        # Create palette data with out-of-bounds mapping indices
        data: dict[str, object] = {
            "colors": [[i * 16, i * 16, i * 16] for i in range(16)],
            "color_mappings": {
                "255,0,0": 20,  # Out of bounds - should clamp to 15
                "0,255,0": -5,  # Out of bounds - should clamp to 0
                "0,0,255": 8,  # Valid - should remain 8
            },
        }

        if log:
            with caplog.at_level(logging.WARNING):
                palette = SheetPalette.from_dict(data)

            # Should have logged warnings about clamping
            assert any("Mapping index clamped" in record.message for record in log.records)
        else:
            palette = SheetPalette.from_dict(data)

        # Verify mapping indices are clamped
        assert palette.color_mappings[(255, 0, 0)] == 15  # Clamped from 20
        assert palette.color_mappings[(0, 255, 0)] == 0  # Clamped from -5
        assert palette.color_mappings[(0, 0, 255)] == 8  # Valid

    def test_sheet_palette_valid_data_no_clamping(self) -> None:
        """Valid data should not be modified."""
        data: dict[str, object] = {
            "colors": [[i * 16, i * 16, i * 16] for i in range(16)],
            "color_mappings": {
                "255,0,0": 1,
                "0,255,0": 5,
                "0,0,255": 15,
            },
        }

        palette = SheetPalette.from_dict(data)

        # All values should match input
        for i in range(16):
            expected = (i * 16, i * 16, i * 16)
            assert palette.colors[i] == expected

        assert palette.color_mappings[(255, 0, 0)] == 1
        assert palette.color_mappings[(0, 255, 0)] == 5
        assert palette.color_mappings[(0, 0, 255)] == 15

    def test_sheet_palette_pads_missing_colors(self) -> None:
        """Palettes with fewer than 16 colors should be padded with black."""
        data: dict[str, object] = {
            "colors": [
                [255, 0, 0],  # Only one color
            ],
            "color_mappings": {},
        }

        palette = SheetPalette.from_dict(data)

        # Should have 16 colors
        assert len(palette.colors) == 16
        assert palette.colors[0] == (255, 0, 0)
        # Rest should be black
        for i in range(1, 16):
            assert palette.colors[i] == (0, 0, 0)
