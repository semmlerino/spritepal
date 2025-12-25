"""
Pure functions for formatting sprite display text.

These are stateless formatters that convert sprite data into display strings.
No Qt dependencies, no side effects, fully testable.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, cast

# Unicode cache indicator (floppy disk emoji)
CACHE_INDICATOR = " \U0001F4BE"


@dataclass(frozen=True)
class SpriteDisplayItem:
    """Formatted sprite item for display.

    Attributes:
        display_text: Human-readable display text
        data: Tuple of (sprite_name, offset) or None for header/separator
        is_header: Whether this is a header item
        is_separator: Whether this is a separator item
    """

    display_text: str
    data: tuple[str, int] | None
    is_header: bool = False
    is_separator: bool = False


@dataclass(frozen=True)
class FormattedSpriteList:
    """Collection of formatted sprite items.

    Attributes:
        items: List of display items
        has_sprites: Whether any actual sprites are present
        button_text: Suggested text for find button
        button_tooltip: Suggested tooltip for find button
    """

    items: list[SpriteDisplayItem]
    has_sprites: bool
    button_text: str
    button_tooltip: str


def format_sprite_name(internal_name: str) -> str:
    """Convert internal sprite name to display name.

    Replaces underscores with spaces and applies title case.

    Args:
        internal_name: Internal sprite name (e.g., "kirby_idle")

    Returns:
        Display name (e.g., "Kirby Idle")

    Examples:
        >>> format_sprite_name("kirby_idle")
        'Kirby Idle'
        >>> format_sprite_name("player_walking")
        'Player Walking'
    """
    return internal_name.replace("_", " ").title()


def format_offset(offset: int, *, pad_to: int = 6) -> str:
    """Format offset as hex string.

    Args:
        offset: The offset value
        pad_to: Number of hex digits to pad to (default 6)

    Returns:
        Hex string with 0x prefix

    Examples:
        >>> format_offset(0x123456)
        '0x123456'
        >>> format_offset(0x1000)
        '0x001000'
    """
    return f"0x{offset:0{pad_to}X}"


def format_sprite_display_text(
    name: str,
    offset: int,
    *,
    is_cached: bool = False,
) -> str:
    """Format a sprite for display in a selector.

    Args:
        name: Internal sprite name
        offset: Sprite offset
        is_cached: Whether sprite came from cache

    Returns:
        Formatted display string

    Examples:
        >>> format_sprite_display_text("kirby_idle", 0x100000)
        'Kirby Idle (0x100000)'
        >>> format_sprite_display_text("kirby_idle", 0x100000, is_cached=True)
        'Kirby Idle (0x100000) 💾'
    """
    display_name = format_sprite_name(name)
    offset_str = format_offset(offset)
    cache_suffix = CACHE_INDICATOR if is_cached else ""
    return f"{display_name} ({offset_str}){cache_suffix}"


def format_custom_sprite_text(offset: int) -> str:
    """Format a custom/scanner-found sprite for display.

    Args:
        offset: Sprite offset

    Returns:
        Formatted display string with cache indicator
    """
    return f"Custom Sprite ({format_offset(offset)}){CACHE_INDICATOR}"


def format_manual_sprite_text(offset: int) -> str:
    """Format a manually entered sprite offset for display.

    Args:
        offset: Sprite offset

    Returns:
        Formatted display string
    """
    return f"Manual Offset ({format_offset(offset)})"


def format_header_text(
    sprite_count: int,
    *,
    is_cached: bool = False,
) -> str:
    """Format the header text for the sprite selector.

    Args:
        sprite_count: Number of sprites available
        is_cached: Whether sprites came from cache

    Returns:
        Formatted header string
    """
    cache_text = " (cached)" if is_cached else ""
    return f"-- {sprite_count} Known Sprites Available{cache_text} --"


def format_sprite_list(
    locations: list[Mapping[str, object]],
    *,
    is_from_cache: bool = False,
) -> FormattedSpriteList:
    """Format a list of sprite locations for display.

    Converts raw sprite location data into formatted display items,
    including header and appropriate button text.

    Args:
        locations: List of sprite location dictionaries with 'name' and 'offset' keys
        is_from_cache: Whether the sprite data came from cache

    Returns:
        FormattedSpriteList with all display items and button configuration
    """
    items: list[SpriteDisplayItem] = []

    if not locations:
        # No sprites available
        items.append(
            SpriteDisplayItem(
                display_text="No known sprites - use scanner",
                data=None,
                is_header=True,
            )
        )
        return FormattedSpriteList(
            items=items,
            has_sprites=False,
            button_text="Find Sprites",
            button_tooltip="Scan ROM for valid sprite offsets (required for unknown ROMs)",
        )

    # Add header
    header_text = format_header_text(len(locations), is_cached=is_from_cache)
    items.append(
        SpriteDisplayItem(
            display_text=header_text,
            data=None,
            is_header=True,
        )
    )

    # Add separator
    items.append(
        SpriteDisplayItem(
            display_text="---",
            data=None,
            is_separator=True,
        )
    )

    # Add each sprite
    for loc in locations:
        # Extract offset first for use in default name
        offset = cast(int, loc.get("offset", 0))
        name = str(loc.get("name", f"sprite_0x{offset:X}"))

        display_text = format_sprite_display_text(name, offset, is_cached=is_from_cache)
        items.append(
            SpriteDisplayItem(
                display_text=display_text,
                data=(name, offset),
            )
        )

    return FormattedSpriteList(
        items=items,
        has_sprites=True,
        button_text="Scan for More Sprites",
        button_tooltip="Scan ROM for additional sprites not in the known list",
    )


def get_internal_name_from_offset(offset: int, *, prefix: str = "sprite") -> str:
    """Generate an internal name for a sprite at a given offset.

    Args:
        offset: Sprite offset
        prefix: Name prefix (default "sprite")

    Returns:
        Internal name like "sprite_0x100000"
    """
    return f"{prefix}_0x{offset:X}"


def get_custom_sprite_name(offset: int) -> str:
    """Generate internal name for a custom/scanner-found sprite.

    Args:
        offset: Sprite offset

    Returns:
        Internal name like "custom_0x100000"
    """
    return f"custom_0x{offset:X}"


def get_manual_sprite_name(offset: int) -> str:
    """Generate internal name for a manually entered sprite offset.

    Args:
        offset: Sprite offset

    Returns:
        Internal name like "manual_0x100000"
    """
    return f"manual_0x{offset:X}"
