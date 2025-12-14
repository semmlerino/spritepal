"""
Consistent UI spacing and sizing constants for SpritePal.

Provides standardized measurements for creating visually coherent interfaces
following modern UI design principles.
"""

# Base spacing unit (8px grid system)
BASE_UNIT = 8

# Spacing values
SPACING_TINY = BASE_UNIT // 2       # 4px - for very tight spacing
SPACING_SMALL = BASE_UNIT           # 8px - for compact layouts
SPACING_MEDIUM = BASE_UNIT * 2      # 16px - standard spacing
SPACING_LARGE = BASE_UNIT * 3       # 24px - generous spacing
SPACING_XLARGE = BASE_UNIT * 4      # 32px - section separation

# Widget heights
BUTTON_HEIGHT = BASE_UNIT * 5       # 40px - standard button height
COMPACT_BUTTON_HEIGHT = BASE_UNIT * 4  # 32px - compact button height
INPUT_HEIGHT = BASE_UNIT * 4        # 32px - input field height
SLIDER_HEIGHT = BASE_UNIT * 8       # 64px - prominent slider height

# Widget widths
COMPACT_WIDTH = BASE_UNIT * 15      # 120px - compact widget width
MEDIUM_WIDTH = BASE_UNIT * 25       # 200px - medium widget width
WIDE_WIDTH = BASE_UNIT * 35         # 280px - wide widget width

# Container measurements
PANEL_PADDING = SPACING_MEDIUM      # 16px - standard panel padding
GROUP_PADDING = SPACING_SMALL       # 8px - group box internal padding
CONTENT_MARGIN = SPACING_LARGE      # 24px - content margins

# Tab-specific constants
TAB_CONTENT_PADDING = SPACING_LARGE # 24px - padding inside tab content
TAB_SECTION_SPACING = SPACING_LARGE # 24px - spacing between tab sections
TAB_MIN_WIDTH = BASE_UNIT * 50      # 400px - minimum tab content width
TAB_MAX_WIDTH = BASE_UNIT * 75      # 600px - maximum tab content width

# Font sizes (relative to default)
FONT_SIZE_SMALL = "11px"
FONT_SIZE_NORMAL = "12px"
FONT_SIZE_MEDIUM = "14px"
FONT_SIZE_LARGE = "16px"
FONT_SIZE_XLARGE = "18px"

# NOTE: Color constants moved to ui/styles/theme.py - use COLORS dict instead
# Import from: from ui.styles.theme import COLORS

# Widget specific dimensions
PALETTE_PREVIEW_SIZE = 32            # 32x32 pixel palette preview widgets
PREVIEW_MIN_SIZE = 256               # 256x256 minimum size for preview widgets
MAX_ZOOM = 20.0                      # Maximum zoom level for preview widgets

# Button and control sizes
BROWSE_BUTTON_MAX_WIDTH = 100        # Maximum width for browse buttons
OFFSET_LABEL_MIN_WIDTH = 80          # Minimum width for offset hex labels
OFFSET_SPINBOX_MIN_WIDTH = 100       # Minimum width for offset spinboxes
COMBO_BOX_MIN_WIDTH = 150           # Minimum width for combo boxes
PALETTE_SELECTOR_MIN_WIDTH = 80      # Minimum width for palette selectors

# Layout positioning and margins
DROP_ZONE_MIN_HEIGHT = 80            # Minimum height for drag-drop zones
CIRCLE_INDICATOR_SIZE = 25           # Size of circular status indicators
CIRCLE_INDICATOR_MARGIN = 35         # Distance from edge for indicators
CHECKMARK_OFFSET = 10                # Position offset for checkmark indicators

# Border and line widths
BORDER_THIN = 1                      # Thin border (1px)
BORDER_THICK = 2                     # Thick border (2px)
LINE_NORMAL = 1                      # Normal line width
LINE_THICK = 3                       # Thick line width

# Grid and tile display
TILE_GRID_THICKNESS = 0.5           # Grid line thickness for tile display
CHECKER_FADE_OPACITY = 30           # Opacity for background checker pattern

# Progressive disclosure helpers
COLLAPSIBLE_ANIMATION_DURATION = 150  # ms - for smooth transitions
COLLAPSIBLE_EASING = "ease-in-out"     # CSS easing function
