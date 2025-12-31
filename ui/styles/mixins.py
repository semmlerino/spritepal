"""
Style mixins and utility functions for SpritePal UI
"""

from __future__ import annotations

from .theme import COLORS, DIMENSIONS


def combine_styles(*styles: str) -> str:
    """
    Combine multiple CSS style strings

    Args:
        *styles: Variable number of CSS style strings

    Returns:
        Combined CSS string
    """
    return "\n".join(style.strip() for style in styles if style.strip())


def create_hover_effect(base_color: str, hover_color: str, property_name: str = "background-color") -> str:
    """
    Create a CSS hover effect

    Args:
        base_color: Base color value
        hover_color: Hover state color value
        property_name: CSS property to modify

    Returns:
        CSS string with hover effect
    """
    return f"""
    {property_name}: {base_color};
    :hover {{
        {property_name}: {hover_color};
    }}
    """


def create_focus_effect(border_color: str = COLORS["border_focus"], outline: str = "none") -> str:
    """
    Create a CSS focus effect

    Args:
        border_color: Border color for focus state
        outline: Outline style for focus state

    Returns:
        CSS string with focus effect
    """
    return f"""
    :focus {{
        border-color: {border_color};
        outline: {outline};
    }}
    """


def create_shadow(shadow_type: str = "default", color: str = "rgba(0, 0, 0, 0.15)") -> str:
    """
    Create a box shadow effect

    Args:
        shadow_type: Shadow style - "default", "raised", "inset"
        color: Shadow color

    Returns:
        CSS box-shadow property
    """
    shadows = {
        "default": f"0 2px 4px {color}",
        "raised": f"0 4px 8px {color}",
        "inset": f"inset 0 2px 4px {color}",
        "none": "none",
    }

    return f"box-shadow: {shadows.get(shadow_type, shadows['default'])};"


def create_transition(properties: str = "all", duration: str = "0.2s", timing: str = "ease-in-out") -> str:
    """
    Create a CSS transition effect

    Args:
        properties: CSS properties to transition
        duration: Transition duration
        timing: Transition timing function

    Returns:
        CSS transition property
    """
    return f"transition: {properties} {duration} {timing};"


def apply_spacing(
    margin: int | None = None,
    padding: int | None = None,
    margin_top: int | None = None,
    margin_bottom: int | None = None,
    margin_left: int | None = None,
    margin_right: int | None = None,
    padding_top: int | None = None,
    padding_bottom: int | None = None,
    padding_left: int | None = None,
    padding_right: int | None = None,
) -> str:
    """
    Apply spacing CSS properties

    Args:
        margin: Uniform margin (overrides individual margins)
        padding: Uniform padding (overrides individual paddings)
        margin_*: Individual margin values
        padding_*: Individual padding values

    Returns:
        CSS string with spacing properties
    """
    styles = []

    if margin is not None:
        styles.append(f"margin: {margin}px;")
    else:
        if margin_top is not None:
            styles.append(f"margin-top: {margin_top}px;")
        if margin_bottom is not None:
            styles.append(f"margin-bottom: {margin_bottom}px;")
        if margin_left is not None:
            styles.append(f"margin-left: {margin_left}px;")
        if margin_right is not None:
            styles.append(f"margin-right: {margin_right}px;")

    if padding is not None:
        styles.append(f"padding: {padding}px;")
    else:
        if padding_top is not None:
            styles.append(f"padding-top: {padding_top}px;")
        if padding_bottom is not None:
            styles.append(f"padding-bottom: {padding_bottom}px;")
        if padding_left is not None:
            styles.append(f"padding-left: {padding_left}px;")
        if padding_right is not None:
            styles.append(f"padding-right: {padding_right}px;")

    return "\n".join(styles)


def create_layout_grid(columns: int = 2, gap: int = DIMENSIONS["spacing_md"]) -> str:
    """
    Create CSS for grid layout

    Args:
        columns: Number of grid columns
        gap: Gap between grid items

    Returns:
        CSS string for grid layout
    """
    return f"""
    display: grid;
    grid-template-columns: repeat({columns}, 1fr);
    gap: {gap}px;
    """


def create_flex_layout(
    direction: str = "row", justify: str = "flex-start", align: str = "stretch", gap: int = DIMENSIONS["spacing_md"]
) -> str:
    """
    Create CSS for flex layout

    Args:
        direction: Flex direction - "row", "column", "row-reverse", "column-reverse"
        justify: Justify content - "flex-start", "center", "flex-end", "space-between", etc.
        align: Align items - "stretch", "center", "flex-start", "flex-end"
        gap: Gap between flex items

    Returns:
        CSS string for flex layout
    """
    return f"""
    display: flex;
    flex-direction: {direction};
    justify-content: {justify};
    align-items: {align};
    gap: {gap}px;
    """


def create_responsive_breakpoints() -> dict[str, str]:
    """
    Create responsive design breakpoints

    Returns:
        Dictionary of media query breakpoints
    """
    return {
        "mobile": "@media (max-width: 768px)",
        "tablet": "@media (min-width: 769px) and (max-width: 1024px)",
        "desktop": "@media (min-width: 1025px)",
        "large": "@media (min-width: 1440px)",
    }


def create_animation_keyframes(name: str, keyframes: dict[str, str]) -> str:
    """
    Create CSS animation keyframes

    Args:
        name: Animation name
        keyframes: Dictionary of keyframe percentages to CSS properties

    Returns:
        CSS keyframes animation
    """
    keyframe_rules = []
    for percentage, properties in keyframes.items():
        keyframe_rules.append(f"    {percentage} {{ {properties} }}")

    return f"""
@keyframes {name} {{
{chr(10).join(keyframe_rules)}
}}
"""


def apply_typography(
    font_size: str | None = None,
    font_weight: str | None = None,
    font_family: str | None = None,
    color: str | None = None,
    line_height: str | None = None,
    text_align: str | None = None,
) -> str:
    """
    Apply typography CSS properties

    Args:
        font_size: Font size value
        font_weight: Font weight value
        font_family: Font family value
        color: Text color value
        line_height: Line height value
        text_align: Text alignment value

    Returns:
        CSS string with typography properties
    """
    styles = []

    if font_size is not None:
        styles.append(f"font-size: {font_size};")
    if font_weight is not None:
        styles.append(f"font-weight: {font_weight};")
    if font_family is not None:
        styles.append(f"font-family: {font_family};")
    if color is not None:
        styles.append(f"color: {color};")
    if line_height is not None:
        styles.append(f"line-height: {line_height};")
    if text_align is not None:
        styles.append(f"text-align: {text_align};")

    return "\n".join(styles)
