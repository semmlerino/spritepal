#!/usr/bin/env python3
"""
Constants for the Unified Sprite Editor
Merged from sprite_editor and pixel_editor - centralizes all specifications
"""

from typing import TypeAlias

# =============================================================================
# VRAM ADDRESS TYPE ALIASES
# =============================================================================
# These clarify the difference between file offsets and SNES addresses.
#
# VRAMByteOffset: Byte offset into a VRAM dump file (0-131071 for 128KB file)
#   Used when: Reading/writing VRAM dump files, injection offset parameter
#   Example: 0xC000 means byte position 49152 in the dump file
#
# VRAMWordAddress: SNES VRAM word address (0x0000-0xFFFF)
#   Used when: OAM tile references, SNES hardware registers
#   Example: 0x6000 is the VRAM word address where Kirby sprites start
#
# Conversion: VRAMByteOffset = VRAMWordAddress * 2
#   SNES VRAM is word-addressed (16-bit), but dump files are byte-addressed.
#   So VRAM address $6000 corresponds to byte offset 0xC000 in the dump.

VRAMByteOffset: TypeAlias = int
VRAMWordAddress: TypeAlias = int

# =============================================================================
# SNES TILE SPECIFICATIONS
# =============================================================================
TILE_WIDTH = 8  # pixels
TILE_HEIGHT = 8  # pixels
BYTES_PER_TILE_4BPP = 32  # 4 bits per pixel, 8x8 pixels
PIXELS_PER_TILE = 64  # 8x8
BITS_PER_PIXEL = 4  # 4bpp indexed color format

# =============================================================================
# SNES MEMORY LIMITS
# =============================================================================
VRAM_SIZE_STANDARD = 65536  # 64KB
VRAM_SIZE_MAX = 131072  # 128KB max
VRAM_SIZE_ABSOLUTE_MAX = 0x20000  # 128KB absolute maximum
CGRAM_SIZE = 512  # Color RAM size in bytes
OAM_SIZE = 544  # Object Attribute Memory size (512 + 32 bytes)
TILE_DATA_MAX_SIZE = 0x10000  # 64KB max for tile data

# =============================================================================
# PALETTE SPECIFICATIONS
# =============================================================================
COLORS_PER_PALETTE = 16
PALETTE_COLORS_COUNT = 16  # Alias for backward compatibility
MAX_COLORS = 16  # Alias for backward compatibility
BYTES_PER_COLOR = 2  # BGR555 format
BYTES_PER_PALETTE = 32  # 16 colors * 2 bytes
MAX_PALETTES = 16  # Maximum number of palettes
PALETTE_SIZE_BYTES = 768  # 256 colors * 3 bytes (RGB) for PIL
PALETTE_ENTRIES = 256  # Total palette entries for PIL

# =============================================================================
# OAM SPECIFICATIONS
# =============================================================================
OAM_ENTRIES = 128  # Number of sprite entries
BYTES_PER_OAM_ENTRY = 4
OAM_HIGH_TABLE_OFFSET = 512  # Offset to high table
OAM_HIGH_TABLE_SIZE = 32

# =============================================================================
# FILE SIZE LIMITS (Security)
# =============================================================================
MAX_VRAM_FILE_SIZE = 128 * 1024  # 128KB
MAX_PNG_FILE_SIZE = 5 * 1024 * 1024  # 5MB
MAX_CGRAM_FILE_SIZE = 2048  # 2KB
MAX_OAM_FILE_SIZE = 2048  # 2KB

# =============================================================================
# DEFAULT VALUES
# =============================================================================
DEFAULT_TILES_PER_ROW = 16
DEFAULT_VRAM_OFFSET = 0xC000  # Common offset for sprite data
DEFAULT_IMAGE_WIDTH = 8  # Default new image width
DEFAULT_IMAGE_HEIGHT = 8  # Default new image height

# =============================================================================
# COLOR CONVERSION (BGR555)
# =============================================================================
BGR555_MAX_VALUE = 31  # 5 bits per color component
RGB888_MAX_VALUE = 255  # 8 bits per color component

# BGR555 color masks
BGR555_BLUE_MASK = 0x7C00  # Bits 14-10 for blue
BGR555_GREEN_MASK = 0x03E0  # Bits 9-5 for green
BGR555_RED_MASK = 0x001F  # Bits 4-0 for red

# Bit shifts for BGR555
BGR555_BLUE_SHIFT = 10
BGR555_GREEN_SHIFT = 5
BGR555_RED_SHIFT = 0

# Pixel masks
PIXEL_4BPP_MASK = 0x0F  # Mask for 4-bit pixel values
MAX_COLOR_INDEX = 15  # Maximum color index (0-15 for 4bpp)
MIN_COLOR_INDEX = 0  # Minimum color index

# =============================================================================
# TILE ENCODING
# =============================================================================
TILE_BITPLANE_OFFSET = 16  # Offset between bitplane pairs in 4bpp tiles

# Kirby-specific tile ranges
KIRBY_TILE_START = 0x180  # Tile 384
KIRBY_TILE_END = 0x200  # Tile 512
KIRBY_VRAM_BASE = 0x6000  # VRAM word address

# Sprite size modes
SPRITE_SIZE_SMALL = "8x8"
SPRITE_SIZE_LARGE = "16x16"  # Can also be 32x32 or 64x64 depending on register

# =============================================================================
# UI DIMENSIONS
# =============================================================================
# Main window
MAIN_WINDOW_WIDTH = 1200
MAIN_WINDOW_HEIGHT = 800
MAIN_WINDOW_X = 100
MAIN_WINDOW_Y = 100

# Dialog windows
STARTUP_DIALOG_WIDTH = 500
STARTUP_DIALOG_HEIGHT = 400
PALETTE_SWITCHER_WIDTH = 400
PALETTE_SWITCHER_HEIGHT = 500

# Panel dimensions
LEFT_PANEL_MAX_WIDTH = 200
CANVAS_MIN_SIZE = 200
PREVIEW_MIN_HEIGHT = 100
RECENT_FILES_LIST_MAX_HEIGHT = 150
COLOR_PREVIEW_MIN_HEIGHT = 50

# Palette widget layout
PALETTE_GRID_COLUMNS = 4
PALETTE_GRID_ROWS = 4
PALETTE_CELL_SIZE = 32  # Size of each color cell in pixels
PALETTE_WIDGET_PADDING = 10
PALETTE_BORDER_WIDTH = 2
PALETTE_SELECTION_BORDER_WIDTH = 3
PALETTE_INDICATOR_SIZE = 8

# Palette color calculations
PALETTE_GRAY_INCREMENT = 17  # Grayscale step (255/15 = 17)
PALETTE_WHITE_TEXT_THRESHOLD = 384  # Sum of RGB below this = white text
PALETTE_DATA_SIZE = 768  # Full palette data size (256 colors * 3 channels)
PALETTE_CHANNEL_OFFSET = 3  # RGB channels per color

# Button sizes
ZOOM_BUTTON_MAX_WIDTH = 35

# =============================================================================
# ZOOM CONSTANTS
# =============================================================================
ZOOM_MIN = 1
ZOOM_MAX = 64
ZOOM_DEFAULT = 4  # Default zoom for sprite sheets
ZOOM_LEVELS = [1, 2, 4, 8, 16, 32, 64]  # Predefined zoom levels
ZOOM_PRESET_1X = 1
ZOOM_PRESET_2X = 2
ZOOM_PRESET_4X = 4
ZOOM_PRESET_8X = 8
ZOOM_PRESET_16X = 16

# Grid visibility
GRID_VISIBLE_THRESHOLD = 4  # Show grid when zoom > this value

# =============================================================================
# PREVIEW CONSTANTS
# =============================================================================
PREVIEW_MAX_SIZE = 100  # Maximum preview dimension
PREVIEW_MAX_SCALE = 8  # Maximum scale factor for preview
PREVIEW_VIEWPORT_PADDING = 20  # Padding when fitting to viewport

# =============================================================================
# FILE MANAGEMENT
# =============================================================================
MAX_RECENT_FILES = 10
MAX_RECENT_PALETTE_FILES = 10

# =============================================================================
# UNDO/REDO
# =============================================================================
UNDO_STACK_SIZE = 50
REDO_STACK_SIZE = 50

# =============================================================================
# TIMING
# =============================================================================
STATUS_MESSAGE_TIMEOUT = 3000  # Status bar message duration in milliseconds

# =============================================================================
# SPRITE PALETTE INDICES
# =============================================================================
PALETTE_INDEX_KIRBY = 8  # Kirby's default palette (Purple/Pink)
PALETTE_INDEX_COMMON = 11  # Common palette (Yellow/Brown)
PALETTE_INDEX_BLUE = 14  # Palette with blue colors
SPRITE_PALETTE_START = 8  # First sprite palette index
SPRITE_PALETTE_END = 15  # Last sprite palette index

# =============================================================================
# DEFAULT PALETTES
# =============================================================================
DEFAULT_GRAYSCALE_PALETTE = [
    (0, 0, 0),  # 0 - Black (transparent)
    (17, 17, 17),  # 1
    (34, 34, 34),  # 2
    (51, 51, 51),  # 3
    (68, 68, 68),  # 4
    (85, 85, 85),  # 5
    (102, 102, 102),  # 6
    (119, 119, 119),  # 7
    (136, 136, 136),  # 8
    (153, 153, 153),  # 9
    (170, 170, 170),  # 10
    (187, 187, 187),  # 11
    (204, 204, 204),  # 12
    (221, 221, 221),  # 13
    (238, 238, 238),  # 14
    (255, 255, 255),  # 15 - White
]

DEFAULT_COLOR_PALETTE = [
    (0, 0, 0),  # 0 - Black (transparent)
    (255, 183, 197),  # 1 - Kirby pink
    (255, 255, 255),  # 2 - White
    (64, 64, 64),  # 3 - Dark gray (outline)
    (255, 0, 0),  # 4 - Red
    (0, 0, 255),  # 5 - Blue
    (255, 220, 220),  # 6 - Light pink
    (200, 120, 150),  # 7 - Dark pink
    (255, 255, 0),  # 8 - Yellow
    (0, 255, 0),  # 9 - Green
    (255, 128, 0),  # 10 - Orange
    (128, 0, 255),  # 11 - Purple
    (0, 128, 128),  # 12 - Teal
    (128, 128, 0),  # 13 - Olive
    (128, 128, 128),  # 14 - Gray
    (192, 192, 192),  # 15 - Light gray
]

# Special colors
COLOR_INVALID_INDEX = (255, 0, 255)  # Magenta for invalid palette indices
COLOR_GRID_LINES = (128, 128, 128, 128)  # Semi-transparent gray for grid

# =============================================================================
# TOOL CONSTANTS
# =============================================================================
TOOL_PENCIL = "pencil"
TOOL_FILL = "fill"
TOOL_PICKER = "picker"

# Tool indices (for button group)
TOOL_INDEX_PENCIL = 0
TOOL_INDEX_FILL = 1
TOOL_INDEX_PICKER = 2

# =============================================================================
# FILE EXTENSIONS
# =============================================================================
IMAGE_EXTENSION_PNG = ".png"
PALETTE_EXTENSION_JSON = ".pal.json"
METADATA_EXTENSION_JSON = "_metadata.json"

# File filters
PNG_FILE_FILTER = "PNG Files (*.png);;All Files (*)"
PALETTE_FILE_FILTER = "Palette Files (*.pal.json);;JSON Files (*.json);;All Files (*)"
VRAM_FILE_FILTER = "VRAM Dumps (*.dmp *.bin);;All Files (*)"
CGRAM_FILE_FILTER = "CGRAM Dumps (*.dmp *.bin);;All Files (*)"
OAM_FILE_FILTER = "OAM Dumps (*.dmp *.bin);;All Files (*)"

# =============================================================================
# KEYBOARD SHORTCUTS
# =============================================================================
KEY_TOGGLE_COLOR_MODE = "C"
KEY_TOGGLE_GRID = "G"
KEY_COLOR_PICKER = "I"
KEY_PALETTE_SWITCHER = "P"
KEY_ZOOM_RESET = "Ctrl+0"
KEY_ZOOM_FIT = "Ctrl+Shift+0"
KEY_ZOOM_FIT_F = "F"

# =============================================================================
# UI STYLING
# =============================================================================
TITLE_FONT_SIZE = 18
BUTTON_PADDING = 8

# Colors (as style strings)
STYLE_COLOR_SUBTITLE = "#666"
STYLE_COLOR_DISABLED = "#888"
STYLE_COLOR_PREVIEW_BG = "#202020"
STYLE_COLOR_PREVIEW_BORDER = "#666"

# =============================================================================
# VALIDATION CONSTRAINTS
# =============================================================================
MIN_IMAGE_WIDTH = 1
MIN_IMAGE_HEIGHT = 1
MAX_IMAGE_WIDTH = 1024
MAX_IMAGE_HEIGHT = 1024
