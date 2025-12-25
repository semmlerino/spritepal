"""Unit tests for sprite display formatter functions."""
from __future__ import annotations

from ui.controllers.sprite_display_formatter import (
    CACHE_INDICATOR,
    FormattedSpriteList,
    SpriteDisplayItem,
    format_custom_sprite_text,
    format_header_text,
    format_manual_sprite_text,
    format_offset,
    format_sprite_display_text,
    format_sprite_list,
    format_sprite_name,
    get_custom_sprite_name,
    get_internal_name_from_offset,
    get_manual_sprite_name,
)


class TestFormatSpriteName:
    """Tests for format_sprite_name function."""

    def test_replaces_underscores(self) -> None:
        """Should replace underscores with spaces."""
        assert format_sprite_name("kirby_idle") == "Kirby Idle"

    def test_title_case(self) -> None:
        """Should apply title case."""
        assert format_sprite_name("player") == "Player"
        assert format_sprite_name("player_walking") == "Player Walking"

    def test_multiple_underscores(self) -> None:
        """Should handle multiple underscores."""
        assert format_sprite_name("some_long_sprite_name") == "Some Long Sprite Name"

    def test_no_underscores(self) -> None:
        """Should handle names without underscores."""
        assert format_sprite_name("kirby") == "Kirby"


class TestFormatOffset:
    """Tests for format_offset function."""

    def test_default_padding(self) -> None:
        """Should pad to 6 digits by default."""
        assert format_offset(0x1000) == "0x001000"
        assert format_offset(0x123456) == "0x123456"

    def test_custom_padding(self) -> None:
        """Should support custom padding."""
        assert format_offset(0x100, pad_to=4) == "0x0100"
        assert format_offset(0x100, pad_to=8) == "0x00000100"

    def test_zero(self) -> None:
        """Should handle zero."""
        assert format_offset(0) == "0x000000"

    def test_large_values(self) -> None:
        """Should handle large values."""
        assert format_offset(0xFFFFFF) == "0xFFFFFF"


class TestFormatSpriteDisplayText:
    """Tests for format_sprite_display_text function."""

    def test_basic_format(self) -> None:
        """Should format name and offset."""
        result = format_sprite_display_text("kirby_idle", 0x100000)
        assert result == "Kirby Idle (0x100000)"

    def test_with_cache_indicator(self) -> None:
        """Should add cache indicator when cached."""
        result = format_sprite_display_text("kirby_idle", 0x100000, is_cached=True)
        assert result == f"Kirby Idle (0x100000){CACHE_INDICATOR}"

    def test_without_cache_indicator(self) -> None:
        """Should not add cache indicator when not cached."""
        result = format_sprite_display_text("kirby_idle", 0x100000, is_cached=False)
        assert CACHE_INDICATOR not in result


class TestFormatCustomSpriteText:
    """Tests for format_custom_sprite_text function."""

    def test_format(self) -> None:
        """Should format with cache indicator."""
        result = format_custom_sprite_text(0x200000)
        assert result == f"Custom Sprite (0x200000){CACHE_INDICATOR}"


class TestFormatManualSpriteText:
    """Tests for format_manual_sprite_text function."""

    def test_format(self) -> None:
        """Should format manual offset."""
        result = format_manual_sprite_text(0x300000)
        assert result == "Manual Offset (0x300000)"
        assert CACHE_INDICATOR not in result


class TestFormatHeaderText:
    """Tests for format_header_text function."""

    def test_without_cache(self) -> None:
        """Should format without cache suffix."""
        result = format_header_text(5)
        assert result == "-- 5 Known Sprites Available --"

    def test_with_cache(self) -> None:
        """Should add cached suffix."""
        result = format_header_text(10, is_cached=True)
        assert result == "-- 10 Known Sprites Available (cached) --"

    def test_singular_plural(self) -> None:
        """Should handle various counts."""
        assert "1 Known Sprites" in format_header_text(1)
        assert "100 Known Sprites" in format_header_text(100)


class TestFormatSpriteList:
    """Tests for format_sprite_list function."""

    def test_empty_list(self) -> None:
        """Should handle empty list."""
        result = format_sprite_list([])

        assert isinstance(result, FormattedSpriteList)
        assert result.has_sprites is False
        assert result.button_text == "Find Sprites"
        assert len(result.items) == 1
        assert result.items[0].is_header is True

    def test_with_sprites(self) -> None:
        """Should format sprite list with header and separator."""
        locations = [
            {"name": "kirby_idle", "offset": 0x100000},
            {"name": "kirby_walk", "offset": 0x200000},
        ]
        result = format_sprite_list(locations)

        assert result.has_sprites is True
        assert result.button_text == "Scan for More Sprites"
        # Header, separator, 2 sprites
        assert len(result.items) == 4
        assert result.items[0].is_header is True
        assert result.items[1].is_separator is True
        assert result.items[2].data == ("kirby_idle", 0x100000)
        assert result.items[3].data == ("kirby_walk", 0x200000)

    def test_with_cache(self) -> None:
        """Should add cache indicators when cached."""
        locations = [{"name": "test", "offset": 0x100}]
        result = format_sprite_list(locations, is_from_cache=True)

        assert "(cached)" in result.items[0].display_text
        assert CACHE_INDICATOR in result.items[2].display_text

    def test_default_name(self) -> None:
        """Should generate default name from offset."""
        locations = [{"offset": 0xABCDEF}]  # No name
        result = format_sprite_list(locations)

        assert result.items[2].data is not None
        assert result.items[2].data[0] == "sprite_0xABCDEF"


class TestSpriteDisplayItem:
    """Tests for SpriteDisplayItem dataclass."""

    def test_regular_item(self) -> None:
        """Should create regular sprite item."""
        item = SpriteDisplayItem(
            display_text="Test (0x100000)",
            data=("test", 0x100000),
        )
        assert item.display_text == "Test (0x100000)"
        assert item.data == ("test", 0x100000)
        assert item.is_header is False
        assert item.is_separator is False

    def test_header_item(self) -> None:
        """Should create header item."""
        item = SpriteDisplayItem(
            display_text="-- Header --",
            data=None,
            is_header=True,
        )
        assert item.is_header is True
        assert item.data is None

    def test_separator_item(self) -> None:
        """Should create separator item."""
        item = SpriteDisplayItem(
            display_text="---",
            data=None,
            is_separator=True,
        )
        assert item.is_separator is True
        assert item.data is None


class TestInternalNameFunctions:
    """Tests for internal name generation functions."""

    def test_get_internal_name_from_offset(self) -> None:
        """Should generate name with prefix."""
        assert get_internal_name_from_offset(0x100000) == "sprite_0x100000"
        assert get_internal_name_from_offset(0x100000, prefix="custom") == "custom_0x100000"

    def test_get_custom_sprite_name(self) -> None:
        """Should generate custom sprite name."""
        assert get_custom_sprite_name(0x200000) == "custom_0x200000"

    def test_get_manual_sprite_name(self) -> None:
        """Should generate manual sprite name."""
        assert get_manual_sprite_name(0x300000) == "manual_0x300000"
