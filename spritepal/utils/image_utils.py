"""
Image utility functions for SpritePal.

DEPRECATED: This module re-exports from core.services.image_utils for backward
compatibility. New code should import directly from core.services.image_utils.
"""
from __future__ import annotations

# Re-export all from the canonical location
from core.services.image_utils import create_checkerboard_pattern, pil_to_qpixmap

__all__ = ["create_checkerboard_pattern", "pil_to_qpixmap"]
