"""
UI widget components for SpritePal
"""

from __future__ import annotations

from .drop_zone import DropZone
from .fullscreen_sprite_viewer import FullscreenSpriteViewer
from .paged_tile_view import PagedTileViewWidget
from .segmented_toggle import SegmentedToggle
from .sprite_gallery_widget import SpriteGalleryWidget
from .sprite_preview_widget import SpritePreviewWidget
from .sprite_thumbnail_widget import SpriteThumbnailWidget

__all__ = [
    "DropZone",
    "FullscreenSpriteViewer",
    "PagedTileViewWidget",
    "SegmentedToggle",
    "SpriteGalleryWidget",
    "SpritePreviewWidget",
    "SpriteThumbnailWidget",
]
