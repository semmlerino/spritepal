"""
Constants for SpritePal
"""
from __future__ import annotations

# SNES Memory offsets and sizes
VRAM_SPRITE_OFFSET = 0xC000  # Default sprite offset in VRAM
VRAM_SPRITE_SIZE = 0x4000  # Default sprite data size (16KB)
VRAM_MIN_SIZE = 0x10000  # 64KB minimum VRAM size
VRAM_MAX_SIZE = 0x100000  # 1MB maximum VRAM size (reasonable upper bound)
CGRAM_EXPECTED_SIZE = 512  # Standard CGRAM size in bytes
OAM_EXPECTED_SIZE = 544  # Standard OAM size in bytes

# HAL Compression limits
DATA_SIZE = 65536  # Maximum uncompressed data size for HAL compression (64KB)

# HAL Process Pool Configuration
HAL_POOL_SIZE_DEFAULT = 4            # Default number of HAL processes in pool
HAL_POOL_SIZE_MIN = 1                # Minimum pool size
HAL_POOL_SIZE_MAX = 16               # Maximum pool size
HAL_POOL_TIMEOUT_SECONDS = 30        # Pool process timeout in seconds
HAL_POOL_RETRY_ATTEMPTS = 3          # Number of retry attempts for failed operations
HAL_POOL_BATCH_SIZE_DEFAULT = 10     # Default batch size for bulk operations
HAL_POOL_SHUTDOWN_TIMEOUT = 5        # Timeout for graceful pool shutdown

# Empty Region Detection Configuration
EMPTY_REGION_ENTROPY_THRESHOLD = 0.1  # Shannon entropy threshold (0-8 scale)
EMPTY_REGION_ZERO_THRESHOLD = 0.9     # Percentage of zeros to consider empty
EMPTY_REGION_PATTERN_THRESHOLD = 0.85 # Repetition score to consider pattern
EMPTY_REGION_MAX_UNIQUE_BYTES = 4     # Max unique bytes to consider empty
EMPTY_REGION_SIZE = 4096              # Size of regions to analyze (4KB)
EMPTY_REGION_TIMEOUT_MS = 1.0         # Max time per region analysis (1ms)

# Sprite format
BYTES_PER_TILE = 32  # 4bpp format
TILE_WIDTH = 8  # Pixels
TILE_HEIGHT = 8  # Pixels
DEFAULT_TILES_PER_ROW = 16  # Default layout

# Palette information
COLORS_PER_PALETTE = 16
SPRITE_PALETTE_START = 8  # Sprite palettes start at index 8
SPRITE_PALETTE_END = 16  # Up to palette 15
CGRAM_PALETTE_SIZE = 32  # Bytes per palette in CGRAM (16 colors * 2 bytes)

# File formats
PALETTE_EXTENSION = ".pal.json"
METADATA_EXTENSION = ".metadata.json"
SPRITE_EXTENSION = ".png"

# Palette names and descriptions
PALETTE_INFO = {
    8: ("Kirby (Pink)", "Main character palette"),
    9: ("Kirby Alt", "Alternative Kirby palette"),
    10: ("Helper", "Helper character palette"),
    11: ("Enemy 1", "Common enemy palette"),
    12: ("UI/HUD", "User interface elements"),
    13: ("Enemy 2", "Special enemy palette"),
    14: ("Boss/Enemy", "Boss and large enemy palette"),
    15: ("Effects", "Special effects palette"),
}

# Common dump file patterns
VRAM_PATTERNS = ["*VRAM*.dmp", "*VideoRam*.dmp", "*vram*.dmp"]

CGRAM_PATTERNS = ["*CGRAM*.dmp", "*CgRam*.dmp", "*cgram*.dmp"]

OAM_PATTERNS = ["*OAM*.dmp", "*SpriteRam*.dmp", "*oam*.dmp"]

# Settings namespaces and keys
SETTINGS_NS_SESSION = "session"
SETTINGS_NS_WINDOW = "window"
SETTINGS_NS_DIRECTORIES = "directories"
SETTINGS_NS_ROM_INJECTION = "rom_injection"

# Session settings keys
SETTINGS_KEY_VRAM_PATH = "vram_path"
SETTINGS_KEY_CGRAM_PATH = "cgram_path"
SETTINGS_KEY_OAM_PATH = "oam_path"
SETTINGS_KEY_OUTPUT_BASE = "output_base"
SETTINGS_KEY_CREATE_GRAYSCALE = "create_grayscale"
SETTINGS_KEY_CREATE_METADATA = "create_metadata"
SETTINGS_KEY_VRAM_OFFSET = "vram_offset"

# Window settings keys
SETTINGS_KEY_GEOMETRY = "geometry"
SETTINGS_KEY_STATE = "state"

# Directory settings keys
SETTINGS_KEY_LAST_USED = "last_used"

# ROM injection settings keys
SETTINGS_KEY_LAST_INPUT_ROM = "last_input_rom"
SETTINGS_KEY_LAST_SPRITE_LOCATION = "last_sprite_location"
SETTINGS_KEY_LAST_CUSTOM_OFFSET = "last_custom_offset"
SETTINGS_KEY_FAST_COMPRESSION = "fast_compression"
SETTINGS_KEY_LAST_INPUT_VRAM = "last_input_vram"  # Used for injection dialog

# Data buffer sizes and limits
BUFFER_SIZE_64KB = 65536  # 64KB absolute maximum for HAL compression
BUFFER_SIZE_16KB = 16384  # 16KB buffer size
BUFFER_SIZE_8KB = 8192    # 8KB sprite data size (256 tiles)
BUFFER_SIZE_4KB = 4096    # 4KB buffer size (128 tiles)
BUFFER_SIZE_2KB = 2048    # 2KB buffer size
BUFFER_SIZE_1KB = 1024    # 1KB buffer size and sample size
BUFFER_SIZE_512B = 512    # 512 byte test offset and SMC header size
BUFFER_SIZE_256B = 256    # 256 byte step size and sample size

# ROM format constants
SMC_HEADER_SIZE = 512     # SMC ROM header size
MAX_BYTE_VALUE = 255      # Maximum 8-bit value
PIXEL_SCALE_FACTOR = 17   # Scale 4-bit (0-15) to 8-bit (0-255): pixel * 17

# Sprite analysis constants
MIN_SPRITE_TILES = 16     # Minimum tiles for valid sprite
TYPICAL_SPRITE_MIN = 32   # Minimum tiles for typical Kirby sprite
TYPICAL_SPRITE_MAX = 256  # Maximum tiles for typical Kirby sprite
LARGE_SPRITE_MAX = 512    # Maximum tiles for large sprite
TILE_INTERLEAVE_SIZE = 16 # Bytes per tile plane interleaving

# Algorithm scoring and thresholds
SPRITE_QUALITY_THRESHOLD = 0.5      # Minimum quality score for sprite detection
SPRITE_QUALITY_BONUS = 0.15         # Quality bonus for good patterns
ENTROPY_ANALYSIS_SAMPLE = 1024      # Bytes to sample for entropy calculation
TILE_ANALYSIS_SAMPLE = 10           # Number of tiles to analyze for quality
MAX_ALIGNMENT_ERROR = 16            # Maximum bytes of misalignment allowed

# Progress reporting intervals
PROGRESS_LOG_INTERVAL = 100         # Log progress every 100 operations
PROGRESS_SAVE_INTERVAL = 50         # Save progress every 50 operations
PROGRESS_DISPLAY_INTERVAL = 100     # Display progress every 100 operations

# Tile format constants
TILE_PLANE_SIZE = 16                # Bytes per tile bitplane
TILE_PLANES_PER_TILE = 2            # Number of bitplane pairs (2 pairs = 4 planes total)
BITS_PER_PLANE = 1                  # Bits contributed by each plane to pixel value

# Preview and UI dimensions
DEFAULT_PREVIEW_WIDTH = 128         # Default preview width in pixels
DEFAULT_PREVIEW_HEIGHT = 128        # Default preview height in pixels
PREVIEW_TILES_PER_ROW = 8          # Maximum tiles per row in preview
MAX_SPRITE_DIMENSION = 256         # Maximum sprite width/height in pixels
PREVIEW_SCALE_FACTOR = 2           # Preview image scale factor

# ROM scanning parameters
ROM_SCAN_STEP_DEFAULT = 0x100      # Default ROM scan step (256 bytes)
ROM_SCAN_STEP_QUICK = 0x1000       # Quick scan step (4KB)
ROM_SCAN_STEP_FINE = 0x10          # Fine scan step (16 bytes)
ROM_SEARCH_RANGE_DEFAULT = 0x1000  # Default search range around sprite (4KB)
ROM_ALIGNMENT_GAP_THRESHOLD = 0x10000  # Gap threshold for region detection (64KB)
ROM_MIN_REGION_SIZE = 0x1000       # Minimum region size (4KB)
MAX_ROM_SIZE = 0x800000            # Maximum ROM file size (8MB) - largest reasonable SNES ROM

# Common ROM sprite areas
ROM_SPRITE_AREA_1_START = 0x80000   # Common sprite area 1 start
ROM_SPRITE_AREA_1_END = 0x100000    # Common sprite area 1 end
ROM_SPRITE_AREA_2_START = 0x100000  # Common sprite area 2 start
ROM_SPRITE_AREA_2_END = 0x180000    # Common sprite area 2 end
ROM_SPRITE_AREA_3_START = 0x180000  # Common sprite area 3 start
ROM_SPRITE_AREA_3_END = 0x200000    # Common sprite area 3 end
ROM_SPRITE_AREA_4_START = 0x200000  # Extended sprite area start
ROM_SPRITE_AREA_4_END = 0x280000    # Extended sprite area end
ROM_SPRITE_AREA_5_START = 0x280000  # Additional sprites start
ROM_SPRITE_AREA_5_END = 0x300000    # Additional sprites end

# ROM header offsets
ROM_HEADER_OFFSET_LOROM = 0x7FC0   # LoROM header offset
ROM_HEADER_OFFSET_HIROM = 0xFFC0   # HiROM header offset
ROM_CHECKSUM_COMPLEMENT_MASK = 0xFFFF  # Checksum complement verification mask

# Valid ROM sizes (in bytes)
ROM_SIZE_512KB = 0x80000   # 512KB (4 Mbit)
ROM_SIZE_1MB = 0x100000    # 1MB (8 Mbit)
ROM_SIZE_1_5MB = 0x180000  # 1.5MB (12 Mbit)
ROM_SIZE_2MB = 0x200000    # 2MB (16 Mbit)
ROM_SIZE_2_5MB = 0x280000  # 2.5MB (20 Mbit)
ROM_SIZE_3MB = 0x300000    # 3MB (24 Mbit)
ROM_SIZE_4MB = 0x400000    # 4MB (32 Mbit)
ROM_SIZE_6MB = 0x600000    # 6MB (48 Mbit)

# Checksum values (examples - replace with actual)
ROM_CHECKSUM_PAL_USA = 0x8A5C
ROM_CHECKSUM_PAL_JAPAN = 0x7F4C
ROM_CHECKSUM_PAL_EUROPE = 0x8B5C
ROM_CHECKSUM_OTHER_USA = 0x1234  # Example, replace with actual

# Sprite quality thresholds
MAX_SPRITE_COUNT_HEADER = 50       # Maximum sprites in header region
MAX_SPRITE_COUNT_MAIN = 200        # Maximum sprites in main region
SPRITE_DENSITY_THRESHOLD = 0.1     # Sprites per KB threshold

# Color and palette bit masks
COLOR_MASK_RED = 0x001F            # 5-bit red mask for BGR555
COLOR_MASK_GREEN = 0x03E0          # 5-bit green mask for BGR555
COLOR_MASK_BLUE = 0x7C00           # 5-bit blue mask for BGR555
COLOR_SHIFT_GREEN = 5              # Bit shift for green component
COLOR_SHIFT_BLUE = 10              # Bit shift for blue component
PALETTE_ATTR_MASK = 0x07           # OAM palette attribute mask (bits 0-2)
OAM_Y_VISIBLE_THRESHOLD = 0xE0     # Y position threshold for visible sprites (224)

# Pixel operations
PIXEL_MASK_4BIT = 0x0F             # Mask for 4-bit pixel values
PIXEL_GRAY_SCALE = 17              # Scale factor for 4-bit to 8-bit gray (0-15 -> 0-255)

# Image validation
IMAGE_DIMENSION_MULTIPLE = 8       # Image dimensions must be multiples of 8
MIN_IMAGE_DIMENSION = 8            # Minimum image dimension (1 tile)
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # Maximum image file size (10MB)
MAX_JSON_SIZE = 1 * 1024 * 1024    # Maximum JSON file size (1MB)

# Cache settings
CACHE_SIZE_MIN_MB = 10             # Minimum cache size in MB
CACHE_SIZE_MAX_MB = 10000          # Maximum cache size in MB (10GB)
CACHE_EXPIRATION_MIN_DAYS = 1      # Minimum cache expiration in days
CACHE_EXPIRATION_MAX_DAYS = 365    # Maximum cache expiration in days
CACHE_EXPIRATION_TO_SECONDS = 24 * 3600  # Convert days to seconds multiplier

# Sprite size constraints for advanced search
MIN_SPRITE_SIZE = 0x100            # Minimum sprite size (256 bytes, 8 tiles)
MAX_SPRITE_SIZE = 0x10000          # Maximum sprite size (64KB, 2048 tiles)
DEFAULT_SCAN_STEP = ROM_SCAN_STEP_DEFAULT  # Default scan step for sprite finding

# Miscellaneous
FILE_READ_HEADER_SIZE = 16         # Bytes to read for file header validation
TILE_VALIDITY_THRESHOLD = 10       # Minimum valid tiles for sprite detection
BYTE_FREQUENCY_SAMPLE_SIZE = 256   # Sample size for byte frequency analysis
MAX_TILE_COUNT_DEFAULT = 8192      # Default maximum tile count validation

# Worker thread timing constants (in seconds)
# These are used by core/ layer and should not depend on ui/
SLEEP_WORKER = 0.1                 # 100ms sleep for worker threads
SLEEP_BATCH = 0.05                 # 50ms sleep for batch processing
