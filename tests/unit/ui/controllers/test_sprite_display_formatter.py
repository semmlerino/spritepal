"""Unit tests for sprite display formatter business rules.

Tests focus on business rules and behavioral contracts, not Python built-ins.
Removed tests:
- TestFormatSpriteName: Tests Python's .replace() and .title() methods
- TestFormatOffset: Tests Python f-string formatting
- TestInternalNameFunctions: Tests simple f-string concatenation

These functions are pure formatters with no complex logic - if they break,
the UI will obviously display wrong text everywhere.
"""

from __future__ import annotations

from ui.controllers.sprite_display_formatter import (
    CACHE_INDICATOR,
    FormattedSpriteList,
    SpriteDisplayItem,
    format_custom_sprite_text,
    format_header_text,
    format_manual_sprite_text,
    format_sprite_display_text,
    format_sprite_list,
)


class TestFormatSpriteDisplayText:
    """Tests for format_sprite_display_text function - business rules for display format."""

    def test_basic_format(self) -> None:
        """Should format name and offset in standard format."""
        result = format_sprite_display_text("kirby_idle", 0x100000)
        assert result == "Kirby Idle (0x100000)"

    def test_with_cache_indicator(self) -> None:
        """Business rule: cached sprites show indicator."""
        result = format_sprite_display_text("kirby_idle", 0x100000, is_cached=True)
        assert result == f"Kirby Idle (0x100000){CACHE_INDICATOR}"

    def test_without_cache_indicator(self) -> None:
        """Business rule: non-cached sprites don't show indicator."""
        result = format_sprite_display_text("kirby_idle", 0x100000, is_cached=False)
        assert CACHE_INDICATOR not in result


class TestFormatCustomSpriteText:
    """Tests for format_custom_sprite_text function."""

    def test_format(self) -> None:
        """Business rule: custom sprites always show cache indicator."""
        result = format_custom_sprite_text(0x200000)
        assert result == f"Custom Sprite (0x200000){CACHE_INDICATOR}"


class TestFormatManualSpriteText:
    """Tests for format_manual_sprite_text function."""

    def test_format(self) -> None:
        """Business rule: manual offsets never show cache indicator."""
        result = format_manual_sprite_text(0x300000)
        assert result == "Manual Offset (0x300000)"
        assert CACHE_INDICATOR not in result


class TestFormatHeaderText:
    """Tests for format_header_text function - header format rules."""

    def test_without_cache(self) -> None:
        """Should format header without cache suffix."""
        result = format_header_text(5)
        assert result == "-- 5 Known Sprites Available --"

    def test_with_cache(self) -> None:
        """Business rule: cached list shows suffix."""
        result = format_header_text(10, is_cached=True)
        assert result == "-- 10 Known Sprites Available (cached) --"


class TestFormatSpriteList:
    """Tests for format_sprite_list function - list structure and behavior."""

    def test_empty_list(self) -> None:
        """Should handle empty list with appropriate UI state."""
        result = format_sprite_list([])

        assert isinstance(result, FormattedSpriteList)
        assert result.has_sprites is False
        assert result.button_text == "Find Sprites"
        assert len(result.items) == 1
        assert result.items[0].is_header is True

    def test_with_sprites(self) -> None:
        """Should format sprite list with header, separator, and items."""
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
        """Business rule: cached list shows indicators."""
        locations = [{"name": "test", "offset": 0x100}]
        result = format_sprite_list(locations, is_from_cache=True)

        assert "(cached)" in result.items[0].display_text
        assert CACHE_INDICATOR in result.items[2].display_text

    def test_default_name(self) -> None:
        """Business rule: sprites without names get offset-based name."""
        locations = [{"offset": 0xABCDEF}]  # No name
        result = format_sprite_list(locations)

        assert result.items[2].data is not None
        assert result.items[2].data[0] == "sprite_0xABCDEF"


class TestSpriteDisplayItem:
    """Tests for SpriteDisplayItem dataclass structure."""

    def test_regular_item(self) -> None:
        """Should create regular sprite item with expected attributes."""
        item = SpriteDisplayItem(
            display_text="Test (0x100000)",
            data=("test", 0x100000),
        )
        assert item.display_text == "Test (0x100000)"
        assert item.data == ("test", 0x100000)
        assert item.is_header is False
        assert item.is_separator is False

    def test_header_item(self) -> None:
        """Should create header item with no data."""
        item = SpriteDisplayItem(
            display_text="-- Header --",
            data=None,
            is_header=True,
        )
        assert item.is_header is True
        assert item.data is None

    def test_separator_item(self) -> None:
        """Should create separator item with no data."""
        item = SpriteDisplayItem(
            display_text="---",
            data=None,
            is_separator=True,
        )
        assert item.is_separator is True
        assert item.data is None
