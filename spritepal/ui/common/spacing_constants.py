"""
Consistent UI spacing and sizing constants for SpritePal.

Provides standardized measurements for creating visually coherent interfaces
following modern UI design principles.
"""

# Base spacing unit (8px grid system)
BASE_UNIT = 8

# Spacing values (8px grid system)
SPACING_TINY = BASE_UNIT // 2       # 4px - for very tight spacing
SPACING_SMALL = BASE_UNIT           # 8px - for compact layouts
SPACING_STANDARD = 12               # 12px - dialog/section spacing
SPACING_MEDIUM = BASE_UNIT * 2      # 16px - standard spacing
SPACING_LARGE = BASE_UNIT * 3       # 24px - generous spacing
SPACING_XLARGE = BASE_UNIT * 4      # 32px - section separation

# Compact spacing values (for dense widget areas like extraction panels)
SPACING_COMPACT_SMALL = 6           # 6px - tight spacing for dense UIs
SPACING_COMPACT_MEDIUM = 10         # 10px - compact standard spacing
SPACING_COMPACT_LARGE = 16          # 16px - compact generous spacing
SPACING_COMPACT_XLARGE = 20         # 20px - compact section separation

# Extraction panel widget sizes
EXTRACTION_BUTTON_MIN_HEIGHT = 32   # Minimum button height for extraction widgets
EXTRACTION_COMBO_MIN_WIDTH = 200    # Minimum combo box width
EXTRACTION_BUTTON_MAX_WIDTH = 150   # Maximum button width
EXTRACTION_LABEL_MIN_WIDTH = 120    # Minimum label width for alignment

# Control panel sizing (uniform for visual consistency)
CONTROL_PANEL_LABEL_WIDTH = 60       # Uniform label width for control panels
CONTROL_PANEL_BUTTON_WIDTH = 180     # Uniform button width (fits "Find Sprites (Ctrl+F)")

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

# Control indentation (for sub-controls under radio buttons/checkboxes)
INDENT_UNDER_CONTROL = 20            # Left indent for dependent controls

# Fullscreen viewer margins
FULLSCREEN_MARGINS = 20              # Uniform margins for fullscreen displays

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

# Toggle/Collapse widget sizing
TOGGLE_BUTTON_SIZE = 20               # Size for toggle/collapse buttons (square)

# ROM Map widget sizing
ROM_MAP_HEIGHT_MIN = 40               # Minimum height for compact ROM map
ROM_MAP_HEIGHT_DEFAULT = 60           # Default minimum height for ROM map
ROM_MAP_HEIGHT_MAX = 80               # Maximum height for ROM map

# Progress bar sizing
LOADING_PROGRESS_HEIGHT = 4           # Thin loading progress bar height

# Preview panel sizing
PREVIEW_GROUP_MIN_HEIGHT = 200        # Minimum height for sprite preview groups
PALETTE_GROUP_MIN_HEIGHT = 80         # Minimum height for palette groups
PALETTE_GROUP_MAX_HEIGHT = 120        # Maximum height for palette groups

# Palette display sizing
PALETTE_LABEL_HEIGHT = 20             # Fixed height for palette labels

# Path input field sizing
PATH_EDIT_MIN_WIDTH = 250             # Minimum width for path input fields

# Sprite selector sizing
SPRITE_COMBO_MIN_WIDTH = 300          # Minimum width for sprite combo boxes

# Thumbnail sizing
THUMBNAIL_SIZE = 80                   # Standard thumbnail size (80x80)

# Dialog sizing
ADVANCED_SEARCH_MIN_SIZE = (800, 600)  # Minimum size for advanced search dialog

# Qt maximum (use instead of magic number 16777215)
QWIDGETSIZE_MAX = 16777215            # Qt's maximum widget size constant
