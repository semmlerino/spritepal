#!/usr/bin/env python3
"""
Unified Sprite Editor for SpritePal.

A consolidated editor combining sprite extraction/injection
and pixel-level editing capabilities.
"""

__version__ = "0.1.0"

# Core utilities
from .core import (
    bgr555_to_rgb888,
    calculate_tile_grid_exact,
    calculate_tile_grid_padded,
    decode_4bpp_tile,
    decode_tiles,
    encode_4bpp_tile,
    encode_tiles,
    get_grayscale_palette,
    read_cgram_palette,
    rgb888_to_bgr555,
)

# Managers
from .managers import ToolManager, ToolType, UndoManager

# Models
from .models import (
    ImageModel,
    PaletteCollection,
    PaletteModel,
    ProjectModel,
)

# Services
from .services import (
    ImageConverter,
    OAMPaletteMapper,
    SpriteRenderer,
    VRAMService,
    create_tile_palette_map,
)

# Workers (import only when Qt is available)
try:
    # Application
    from .application import SpriteEditorApplication, main

    # Controllers
    from .controllers import (
        BaseController,
        EditingController,
        ExtractionController,
        InjectionController,
        MainController,
    )

    # Views
    from .views import (
        ColorPaletteWidget,
        EditTab,
        ExtractTab,
        HexLineEdit,
        InjectTab,
        MultiPaletteTab,
        OptionsPanel,
        PalettePanel,
        PixelCanvas,
        PreviewPanel,
        SpriteEditorMainWindow,
        ToolPanel,
    )
    from .workers import (
        BaseWorker,
        ExtractWorker,
        InjectWorker,
        MultiPaletteExtractWorker,
    )
except ImportError:
    # Qt not available
    pass

__all__ = [
    # Controllers
    "BaseController",
    # Workers
    "BaseWorker",
    # Views - Widgets
    "ColorPaletteWidget",
    # Views - Tabs
    "EditTab",
    "EditingController",
    "ExtractTab",
    "ExtractWorker",
    "ExtractionController",
    "HexLineEdit",
    # Services
    "ImageConverter",
    # Models
    "ImageModel",
    "InjectTab",
    "InjectWorker",
    "InjectionController",
    "MainController",
    "MultiPaletteExtractWorker",
    "MultiPaletteTab",
    "OAMPaletteMapper",
    # Views - Panels
    "OptionsPanel",
    "PaletteCollection",
    "PaletteModel",
    "PalettePanel",
    "PixelCanvas",
    "PreviewPanel",
    "ProjectModel",
    # Application
    "SpriteEditorApplication",
    # Views - Main Window
    "SpriteEditorMainWindow",
    "SpriteRenderer",
    "ToolManager",
    "ToolPanel",
    "ToolType",
    "UndoManager",
    "VRAMService",
    # Version
    "__version__",
    # Core utilities
    "bgr555_to_rgb888",
    "calculate_tile_grid_exact",
    "calculate_tile_grid_padded",
    "create_tile_palette_map",
    "decode_4bpp_tile",
    "decode_tiles",
    "encode_4bpp_tile",
    "encode_tiles",
    "get_grayscale_palette",
    "main",
    "read_cgram_palette",
    "rgb888_to_bgr555",
]
