"""
Shared image processing utilities.

This module consolidates common image processing patterns used across
preview generators and image processors.
"""

from __future__ import annotations

from PIL import Image


def paste_with_mode_handling(
    target: Image.Image,
    source: Image.Image,
    position: tuple[int, int],
) -> None:
    """Paste source image onto target with proper mode handling.

    Handles RGBA alpha compositing and mode conversion automatically.
    This is a common pattern used in sprite arrangement and preview generation.

    Args:
        target: Target image to paste onto (modified in place)
        source: Source image to paste
        position: (x, y) position for top-left corner
    """
    if target.mode == "RGBA" and source.mode == "RGBA":
        # RGBA to RGBA - use alpha compositing
        target.paste(source, position, source)
    elif target.mode == "RGBA" and source.mode != "RGBA":
        # Convert source to RGBA for alpha compositing
        rgba_source = source.convert("RGBA")
        target.paste(rgba_source, position, rgba_source)
    else:
        # Standard paste for grayscale/palette modes
        target.paste(source, position)


def ensure_rgba(image: Image.Image) -> Image.Image:
    """Ensure image is in RGBA mode.

    Args:
        image: Input image in any mode

    Returns:
        Image in RGBA mode (copy if conversion needed, original if already RGBA)
    """
    if image.mode == "RGBA":
        return image
    return image.convert("RGBA")


def create_output_image(
    width: int,
    height: int,
    use_rgba: bool = False,
    original_image: Image.Image | None = None,
) -> Image.Image:
    """Create an output image with appropriate mode.

    Args:
        width: Image width
        height: Image height
        use_rgba: If True, create RGBA image for colorized output
        original_image: If provided and not use_rgba, preserve palette mode

    Returns:
        New image with appropriate mode
    """
    if use_rgba:
        return Image.new("RGBA", (width, height), (0, 0, 0, 0))
    elif original_image is not None and original_image.mode == "P":
        # Preserve palette mode
        img = Image.new("P", (width, height))
        palette = original_image.getpalette()
        if palette is not None:
            img.putpalette(palette)
        return img
    else:
        # Default to grayscale
        return Image.new("L", (width, height), 0)


def bgr555_to_rgb888(bgr555: int) -> tuple[int, int, int]:
    """
    Convert BGR555 color to RGB888.

    Args:
        bgr555: 16-bit BGR555 color value

    Returns:
        Tuple of (r, g, b) values in 0-255 range
    """
    # Extract 5-bit components (SNES format: xBBBBBGGGGGRRRRR)
    r = bgr555 & 0x1F
    g = (bgr555 >> 5) & 0x1F
    b = (bgr555 >> 10) & 0x1F

    # Convert to 8-bit values using (val << 3) | (val >> 2) for accurate scaling
    r8 = (r << 3) | (r >> 2)
    g8 = (g << 3) | (g >> 2)
    b8 = (b << 3) | (b >> 2)

    return r8, g8, b8


def rgb888_to_bgr555(r: int, g: int, b: int) -> int:
    """
    Convert RGB888 color to BGR555.

    Args:
        r: Red component (0-255)
        g: Green component (0-255)
        b: Blue component (0-255)

    Returns:
        16-bit BGR555 color value
    """
    # Convert to 5-bit values
    r5 = r >> 3
    g5 = g >> 3
    b5 = b >> 3

    # Pack into BGR555
    return (b5 << 10) | (g5 << 5) | r5
