"""
Constants for SpritePal
"""

from __future__ import annotations

from enum import Enum, auto

# =============================================================================
# SNES Video Memory Architecture
# =============================================================================
# The SNES Picture Processing Unit (PPU) has dedicated video RAM regions:
# - VRAM: 64KB for tile data and tilemaps (addresses $0000-$FFFF)
# - CGRAM: 512 bytes for color palettes (256 colors x 2 bytes BGR555)
# - OAM: 544 bytes for sprite attributes (128 sprites + high table)
#
# For sprites (OBJ layer), tile graphics are stored in VRAM starting at an
# address configured by the OBSEL register ($2101). Common base addresses:
# - $0000: First half of VRAM (banks 0-1)
# - $4000: Second quarter
# - $8000: Third quarter
# - $C000: Last quarter (most common for Kirby games)
#
# See: https://snes.nesdev.org/wiki/PPU_registers#OBSEL
# =============================================================================

# VRAM sprite base address - where sprite tiles begin in video memory
# Kirby Super Star uses $C000 as the sprite tile base address
VRAM_SPRITE_OFFSET = 0xC000

# Mapping from VRAM addresses to ROM file offsets (game-specific)
# NOTE: This maps where sprites appear in VRAM during gameplay (after DMA),
# NOT where compressed sprite data is stored in the ROM file.
# For actual ROM extraction offsets, see config/sprite_locations.json
# The 0x0C8000 offset does NOT contain valid HAL-compressed sprites.
VRAM_TO_ROM_MAPPING: dict[int, int] = {
    0xC000: 0x0C8000,  # Runtime VRAM to ROM mapping (LoROM) - not for extraction
}

VRAM_SPRITE_SIZE = 0x4000  # Default sprite data size (16KB = 512 tiles)
VRAM_MIN_SIZE = 0x10000  # 64KB minimum VRAM size
VRAM_MAX_SIZE = 0x100000  # 1MB maximum VRAM size (reasonable upper bound)
CGRAM_EXPECTED_SIZE = 512  # Standard CGRAM size in bytes
OAM_EXPECTED_SIZE = 544  # Standard OAM size in bytes

# HAL Compression limits
DATA_SIZE = 65536  # Maximum uncompressed data size for HAL compression (64KB)

# HAL Process Pool Configuration
HAL_POOL_SIZE_DEFAULT = 4  # Default number of HAL processes in pool
HAL_POOL_SIZE_MIN = 1  # Minimum pool size
HAL_POOL_SIZE_MAX = 16  # Maximum pool size
HAL_POOL_TIMEOUT_SECONDS = 30  # Pool process timeout in seconds
HAL_POOL_RETRY_ATTEMPTS = 3  # Number of retry attempts for failed operations
HAL_POOL_SHUTDOWN_TIMEOUT = 5  # Timeout for graceful pool shutdown
HAL_POOL_MIN_WORKER_RATIO = 0.75  # Minimum ratio of workers that must respond for valid result

# =============================================================================
# Worker Thread Timing Constants
# =============================================================================
# Centralized timing values for background workers. Change these to tune
# performance on different hardware.
#
# The idle detection loop polls at WORKER_IDLE_CHECK_INTERVAL_MS intervals.
# After WORKER_IDLE_RELEASE_SECONDS of no requests, ROM resources are released.
# After WORKER_MAX_IDLE_SECONDS of no requests, the worker shuts down entirely.
# =============================================================================

WORKER_IDLE_CHECK_INTERVAL_MS = 100  # Poll interval for idle detection
WORKER_IDLE_RELEASE_SECONDS = 2.0  # Release ROM handle after this idle time
WORKER_IDLE_ITERATIONS = int(
    WORKER_IDLE_RELEASE_SECONDS * 1000 / WORKER_IDLE_CHECK_INTERVAL_MS
)  # Derived: iterations before ROM release
WORKER_MAX_IDLE_SECONDS = 10.0  # Max idle time before full worker shutdown
WORKER_MAX_IDLE_ITERATIONS = int(
    WORKER_MAX_IDLE_SECONDS * 1000 / WORKER_IDLE_CHECK_INTERVAL_MS
)  # Derived: iterations before shutdown
THREAD_POOL_TIMEOUT_SECONDS = 2.0  # Timeout when waiting for thread pool tasks

# Empty Region Detection Configuration
EMPTY_REGION_ENTROPY_THRESHOLD = 0.1  # Shannon entropy threshold (0-8 scale)
EMPTY_REGION_ZERO_THRESHOLD = 0.9  # Percentage of zeros to consider empty
EMPTY_REGION_PATTERN_THRESHOLD = 0.85  # Repetition score to consider pattern
EMPTY_REGION_MAX_UNIQUE_BYTES = 4  # Max unique bytes to consider empty
EMPTY_REGION_SIZE = 4096  # Size of regions to analyze (4KB)

# =============================================================================
# SNES Sprite Tile Format (4bpp)
# =============================================================================
# SNES sprites use 4 bits per pixel (4bpp), allowing 16 colors per tile.
# Each 8x8 pixel tile is stored as 4 bitplanes in an interleaved format:
#
# Memory layout for one 8x8 tile (32 bytes):
#   Bytes 0-15:  Bitplanes 0 and 1 (interleaved, 2 bytes per row)
#   Bytes 16-31: Bitplanes 2 and 3 (interleaved, 2 bytes per row)
#
# Formula: 8 rows x 8 pixels x 4 bits / 8 bits per byte = 32 bytes
#
# This is why BYTES_PER_TILE = 32 appears throughout the codebase.
# =============================================================================

BYTES_PER_TILE = 32  # 4bpp format: 8x8 pixels x 4 bits = 32 bytes per tile
TILE_WIDTH = 8  # Pixels per tile row
TILE_HEIGHT = 8  # Pixels per tile column
DEFAULT_TILES_PER_ROW = 16  # Default layout for sprite sheets

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
BUFFER_SIZE_8KB = 8192  # 8KB sprite data size (256 tiles)
BUFFER_SIZE_4KB = 4096  # 4KB buffer size (128 tiles)
BUFFER_SIZE_2KB = 2048  # 2KB buffer size
BUFFER_SIZE_1KB = 1024  # 1KB buffer size and sample size
BUFFER_SIZE_512B = 512  # 512 byte test offset and SMC header size
BUFFER_SIZE_256B = 256  # 256 byte step size and sample size

# ROM format constants
SMC_HEADER_SIZE = 512  # SMC ROM header size
MAX_BYTE_VALUE = 255  # Maximum 8-bit value
PIXEL_SCALE_FACTOR = 17  # Scale 4-bit (0-15) to 8-bit (0-255): pixel * 17

# Sprite analysis constants
MIN_SPRITE_TILES = 4  # Minimum tiles for valid sprite (2x2 tiles = 128 bytes)
TYPICAL_SPRITE_MIN = 32  # Minimum tiles for typical Kirby sprite
TYPICAL_SPRITE_MAX = 256  # Maximum tiles for typical Kirby sprite
LARGE_SPRITE_MAX = 512  # Maximum tiles for large sprite
TILE_INTERLEAVE_SIZE = 16  # Bytes per tile plane interleaving

# Algorithm scoring and thresholds
SPRITE_QUALITY_THRESHOLD = 0.5  # Minimum quality score for sprite detection
SPRITE_QUALITY_BONUS = 0.15  # Quality bonus for good patterns
ENTROPY_ANALYSIS_SAMPLE = 1024  # Bytes to sample for entropy calculation
TILE_ANALYSIS_SAMPLE = 10  # Number of tiles to analyze for quality
MAX_ALIGNMENT_ERROR = 16  # Maximum bytes of misalignment allowed

# Sprite tile validation threshold
# This is a heuristic that reduces obvious garbage but does NOT guarantee
# real sprite content. Visual verification is essential.
# Tune LOWER if valid sprites are being rejected (false negatives).
# Tune HIGHER if garbage data is being accepted (false positives).
SPRITE_VALIDATION_THRESHOLD = 0.6  # 60% of tiles must pass validation

# HAL compression ratio thresholds (empirically chosen)
# These filter extreme cases but valid sprites may fall outside this range,
# and invalid data may fall within it. Not a reliable indicator on its own.
HAL_MIN_COMPRESSION_RATIO = 0.10  # Very low ratio may indicate parser issues
HAL_MAX_COMPRESSION_RATIO = 0.90  # Very high ratio may indicate uncompressed data

# Tile pattern thresholds for false positive reduction
# Reject data where too many tiles are blank (all zeros or all 0xFF)
MAX_BLANK_TILE_RATIO = 0.50  # Max 50% of tiles can be blank
MIN_UNIQUE_TILE_PATTERNS = 2  # Require at least 2 distinct tile patterns

# Sprite entropy thresholds (empirically chosen, not proven)
# These filter obvious extremes but structured noise may still pass.
# Entropy alone cannot distinguish real sprites from random structured data.
SPRITE_ENTROPY_MIN = 2.5  # Minimum entropy for sprite data
SPRITE_ENTROPY_MAX = 7.0  # Maximum entropy for sprite data

# Progress reporting intervals
PROGRESS_LOG_INTERVAL = 100  # Log progress every 100 operations
PROGRESS_SAVE_INTERVAL = 50  # Save progress every 50 operations
PROGRESS_DISPLAY_INTERVAL = 100  # Display progress every 100 operations

# Tile format constants
TILE_PLANE_SIZE = 16  # Bytes per tile bitplane
TILE_PLANES_PER_TILE = 2  # Number of bitplane pairs (2 pairs = 4 planes total)
BITS_PER_PLANE = 1  # Bits contributed by each plane to pixel value

# Preview and UI dimensions
DEFAULT_PREVIEW_WIDTH = 128  # Default preview width in pixels
DEFAULT_PREVIEW_HEIGHT = 128  # Default preview height in pixels
PREVIEW_TILES_PER_ROW = 8  # Maximum tiles per row in preview
MAX_SPRITE_DIMENSION = 256  # Maximum sprite width/height in pixels
PREVIEW_SCALE_FACTOR = 2  # Preview image scale factor

# ROM scanning parameters
ROM_SCAN_START_DEFAULT = 0x40000  # Default scan start (skip headers/early data, 256KB)
ROM_SCAN_STEP_DEFAULT = 0x10  # Default ROM scan step (16 bytes = thorough)
ROM_SCAN_STEP_FAST = 0x80  # Fast scan step (128 bytes = 4 tiles, legacy default)
ROM_SCAN_STEP_QUICK = 0x1000  # Quick scan step (4KB)
ROM_SCAN_STEP_TILE = 0x20  # Tile-aligned step (32 bytes = 1 tile)
ROM_SCAN_STEP_FINE = 0x10  # Fine scan step (16 bytes, half a tile)
ROM_SEARCH_RANGE_DEFAULT = 0x1000  # Default search range around sprite (4KB)
ROM_ALIGNMENT_GAP_THRESHOLD = 0x10000  # Gap threshold for region detection (64KB)
ROM_MIN_REGION_SIZE = 0x1000  # Minimum region size (4KB)
MAX_ROM_SIZE = 0x800000  # Maximum ROM file size (8MB) - largest reasonable SNES ROM

# Common ROM sprite areas (legacy constants for backward compatibility)
ROM_SPRITE_AREA_1_START = 0x80000  # Common sprite area 1 start
ROM_SPRITE_AREA_1_END = 0x100000  # Common sprite area 1 end
ROM_SPRITE_AREA_2_START = 0x100000  # Common sprite area 2 start
ROM_SPRITE_AREA_2_END = 0x180000  # Common sprite area 2 end
ROM_SPRITE_AREA_3_START = 0x180000  # Common sprite area 3 start
ROM_SPRITE_AREA_3_END = 0x200000  # Common sprite area 3 end
ROM_SPRITE_AREA_4_START = 0x200000  # Extended sprite area start
ROM_SPRITE_AREA_4_END = 0x280000  # Extended sprite area end
ROM_SPRITE_AREA_5_START = 0x280000  # Additional sprites start
ROM_SPRITE_AREA_5_END = 0x300000  # Additional sprites end
# Extended areas for larger ROMs (4MB+)
ROM_SPRITE_AREA_6_START = 0x300000  # 4MB ROM area 1 start
ROM_SPRITE_AREA_6_END = 0x380000  # 4MB ROM area 1 end
ROM_SPRITE_AREA_7_START = 0x380000  # 4MB ROM area 2 start
ROM_SPRITE_AREA_7_END = 0x400000  # 4MB ROM area 2 end

# ROM header offsets
ROM_HEADER_OFFSET_LOROM = 0x7FC0  # LoROM header offset
ROM_HEADER_OFFSET_HIROM = 0xFFC0  # HiROM header offset
ROM_HEADER_OFFSET_EXHIROM = 0x40FFC0  # ExHiROM header offset (extended HiROM)
ROM_CHECKSUM_COMPLEMENT_MASK = 0xFFFF  # Checksum complement verification mask

# ROM type values indicating special chips (byte at header offset +0x15)
# SA-1 chip games: Kirby Super Star, Super Mario RPG, etc.
ROM_TYPE_SA1_MIN = 0x34  # SA-1 chip type range start
ROM_TYPE_SA1_MAX = 0x36  # SA-1 chip type range end


class RomMappingType(Enum):
    """
    ROM memory mapping type for SNES address translation.

    Different SNES cartridge types use different address mapping schemes:
    - LOROM: Standard low ROM mapping (32KB per bank)
    - HIROM: High ROM mapping (64KB per bank, linear addressing)
    - SA1: SA-1 coprocessor mapping (Kirby Super Star, Super Mario RPG)
          Uses simple offset: ROM = Mesen2_address - 0x300000
    """

    LOROM = auto()
    HIROM = auto()
    SA1 = auto()


def is_snes_address(address: int) -> bool:
    """
    Check if an address looks like an SNES address vs a file offset.

    SNES addresses have the format: bank (8 bits) + address (16 bits)
    - LoROM: banks $00-$7D or $80-$FF with addresses $8000-$FFFF
    - File offsets are typically < 0x800000 (8MB max ROM)

    Args:
        address: The address to check

    Returns:
        True if this looks like an SNES address, False if file offset
    """
    # If address has bits set above 0x7FFFFF, it's likely SNES
    if address > 0x7FFFFF:
        return True

    # Check for LoROM pattern: addresses $8000-$FFFF in low 16 bits
    low_16 = address & 0xFFFF
    if low_16 >= 0x8000:
        # Could be SNES if bank portion exists
        bank = address >> 16
        if bank > 0:
            return True

    return False


def snes_to_file_offset(snes_addr: int, *, has_smc_header: bool = False) -> int:
    """
    Convert SNES LoROM address to file offset.

    LoROM mapping:
    - Banks $00-$7D, addresses $8000-$FFFF → file offset
    - Banks $80-$FF mirror $00-$7F

    Args:
        snes_addr: SNES address (e.g., 0x808000, 0xC08000)
        has_smc_header: Whether ROM has 512-byte SMC header

    Returns:
        File offset in the ROM file
    """
    bank = (snes_addr >> 16) & 0xFF
    addr = snes_addr & 0xFFFF

    # Mirror banks $80-$FF to $00-$7F
    if bank >= 0x80:
        bank &= 0x7F

    # LoROM: each bank maps 32KB from $8000-$FFFF
    if addr >= 0x8000:
        file_offset = (bank * 0x8000) + (addr - 0x8000)
    else:
        # Addresses below $8000 don't map to ROM in LoROM
        file_offset = bank * 0x8000

    # Add SMC header offset if present
    if has_smc_header:
        file_offset += 512

    return file_offset


def sa1_to_file_offset(mesen2_addr: int, *, has_smc_header: bool = False) -> int:
    """
    Convert Mesen2 SA-1 runtime address to file offset.

    SA-1 games (Kirby Super Star, Super Mario RPG, etc.) use the SA-1
    coprocessor which has a different memory mapping than standard LoROM.
    Mesen2 emulator uses addresses starting at 0x300000 for SA-1 ROM space.

    The translation is: file_offset = mesen2_address - 0x300000

    Examples from docs/mesen2/03_GAME_MAPPING_KIRBY_SA1.md:
    - Mesen2 $3D2238 → ROM $0D2238
    - Mesen2 $57D800 → ROM $27D800
    - Mesen2 $580000 → ROM $280000

    Args:
        mesen2_addr: Mesen2 runtime address (e.g., 0x3D2238)
        has_smc_header: Whether ROM has 512-byte SMC header

    Returns:
        File offset in the ROM file
    """
    # SA-1 offset formula verified from Mesen2 testing
    SA1_BASE_OFFSET = 0x300000

    if mesen2_addr >= SA1_BASE_OFFSET:
        file_offset = mesen2_addr - SA1_BASE_OFFSET
    else:
        # Address is below SA-1 range, treat as direct file offset
        file_offset = mesen2_addr

    # Add SMC header offset if present
    if has_smc_header:
        file_offset += 512

    return file_offset


def hirom_to_file_offset(snes_addr: int, *, has_smc_header: bool = False) -> int:
    """
    Convert SNES HiROM address to file offset.

    HiROM mapping uses linear addressing where the ROM appears at
    banks $C0-$FF (and mirrors at $40-$7D for addresses $0000-$FFFF).
    The simple conversion masks off the upper bits.

    Args:
        snes_addr: SNES HiROM address (e.g., 0xC08000)
        has_smc_header: Whether ROM has 512-byte SMC header

    Returns:
        File offset in the ROM file
    """
    # HiROM uses linear mapping - mask to 22-bit address space (4MB max)
    file_offset = snes_addr & 0x3FFFFF

    # Add SMC header offset if present
    if has_smc_header:
        file_offset += 512

    return file_offset


def detect_mapping_type(rom_type: int, header_offset: int) -> RomMappingType:
    """
    Detect ROM mapping type from header information.

    Uses the ROM type byte (header offset +0x15) and header location
    to determine the appropriate address mapping scheme.

    Args:
        rom_type: ROM type byte from header (at offset 0x15 within header)
        header_offset: Header location in file (0x7FC0=LoROM, 0xFFC0=HiROM)

    Returns:
        RomMappingType enum value
    """
    # SA-1 chip detection (Kirby Super Star, Super Mario RPG, etc.)
    if ROM_TYPE_SA1_MIN <= rom_type <= ROM_TYPE_SA1_MAX:
        return RomMappingType.SA1

    # HiROM detection based on header location
    if header_offset == ROM_HEADER_OFFSET_HIROM:
        return RomMappingType.HIROM

    # ExHiROM is also HiROM mapping
    if header_offset == ROM_HEADER_OFFSET_EXHIROM:
        return RomMappingType.HIROM

    # Default to LoROM
    return RomMappingType.LOROM


def normalize_address(
    address: int,
    rom_size: int,
    *,
    mapping_type: RomMappingType | None = None,
) -> int:
    """
    Normalize an address to a file offset.

    Handles SNES addresses (various mapping types) and direct file offsets.
    Automatically detects SMC headers based on ROM size.

    Args:
        address: Address that may be SNES or file offset
        rom_size: Size of the ROM file in bytes
        mapping_type: Optional ROM mapping type. If None, defaults to LoROM.
            Pass RomMappingType.SA1 for Kirby Super Star and similar games.

    Returns:
        File offset suitable for ROM access
    """
    has_smc_header = rom_size % 1024 == 512

    # SA-1 addresses (Mesen2 format) start at 0x300000 and don't follow
    # the traditional LoROM pattern, so handle them specially
    SA1_BASE_OFFSET = 0x300000
    if mapping_type == RomMappingType.SA1 and address >= SA1_BASE_OFFSET:
        return sa1_to_file_offset(address, has_smc_header=has_smc_header)

    if is_snes_address(address):
        if mapping_type == RomMappingType.SA1:
            return sa1_to_file_offset(address, has_smc_header=has_smc_header)
        elif mapping_type == RomMappingType.HIROM:
            return hirom_to_file_offset(address, has_smc_header=has_smc_header)
        else:
            # Default to LoROM for backwards compatibility
            return snes_to_file_offset(address, has_smc_header=has_smc_header)

    # Already a file offset - just add SMC header offset if needed
    if has_smc_header:
        return address + 512

    return address


def parse_address_string(text: str) -> tuple[int, str]:
    """
    Parse address string in various formats used by emulators and hex editors.

    Supported formats:
    - $98:8000 or 98:8000 (SNES bank:offset, Mesen style)
    - $988000 (SNES combined with $ prefix)
    - 0x988000 or 988000 (hex)
    - Pure decimal if no hex chars present

    Args:
        text: Address string to parse

    Returns:
        Tuple of (parsed_value, format_detected)
        format_detected is one of: "snes_banked", "snes", "hex", "decimal"

    Raises:
        ValueError: If the string cannot be parsed as an address
    """
    text = text.strip()
    if not text:
        raise ValueError("Empty address string")

    # Check for SNES bank:offset format (e.g., $98:8000 or 98:8000)
    # This is the Mesen emulator style
    if ":" in text:
        # Remove $ prefix if present
        clean = text.lstrip("$")
        try:
            bank_str, addr_str = clean.split(":", 1)
            bank = int(bank_str, 16)
            addr = int(addr_str, 16)

            # Validate ranges
            if bank > 0xFF:
                raise ValueError(f"Bank value 0x{bank:X} exceeds 0xFF")
            if addr > 0xFFFF:
                raise ValueError(f"Address value 0x{addr:X} exceeds 0xFFFF")

            # Combine into SNES address: bank in high byte, address in low 16 bits
            return (bank << 16) | addr, "snes_banked"
        except ValueError as e:
            if "exceeds" in str(e):
                raise
            raise ValueError(f"Invalid bank:offset format: {text}") from e

    # Check for $ prefix (SNES style without colon)
    if text.startswith("$"):
        try:
            value = int(text[1:], 16)
            return value, "snes"
        except ValueError as e:
            raise ValueError(f"Invalid SNES address: {text}") from e

    # Check for 0x prefix (standard hex)
    if text.lower().startswith("0x"):
        try:
            value = int(text, 16)
            return value, "hex"
        except ValueError as e:
            raise ValueError(f"Invalid hex address: {text}") from e

    # Try to determine if it's hex or decimal
    # If it contains a-f characters, it's hex
    has_hex_chars = any(c in text.lower() for c in "abcdef")

    try:
        if has_hex_chars:
            value = int(text, 16)
            return value, "hex"
        else:
            # Could be either hex or decimal - try decimal first
            # for numbers that could reasonably be decimal (< 1000000)
            value = int(text)
            # If the value looks like it could be a ROM offset (large number),
            # and has no hex chars, still treat as decimal
            return value, "decimal"
    except ValueError as e:
        raise ValueError(f"Cannot parse address: {text}") from e


# Valid ROM sizes (in bytes)
ROM_SIZE_512KB = 0x80000  # 512KB (4 Mbit)
ROM_SIZE_1MB = 0x100000  # 1MB (8 Mbit)
ROM_SIZE_1_5MB = 0x180000  # 1.5MB (12 Mbit)
ROM_SIZE_2MB = 0x200000  # 2MB (16 Mbit)
ROM_SIZE_2_5MB = 0x280000  # 2.5MB (20 Mbit)
ROM_SIZE_3MB = 0x300000  # 3MB (24 Mbit)
ROM_SIZE_4MB = 0x400000  # 4MB (32 Mbit)
ROM_SIZE_6MB = 0x600000  # 6MB (48 Mbit)

# Checksum values for Kirby Super Star (verified from actual ROM dumps)
ROM_CHECKSUM_PAL_USA = 0x8A5C
ROM_CHECKSUM_PAL_JAPAN = 0x7F4C
ROM_CHECKSUM_PAL_EUROPE = 0x8B5C

# Sprite quality thresholds
MAX_SPRITE_COUNT_HEADER = 50  # Maximum sprites in header region
MAX_SPRITE_COUNT_MAIN = 200  # Maximum sprites in main region
SPRITE_DENSITY_THRESHOLD = 0.1  # Sprites per KB threshold

# Color and palette bit masks
COLOR_MASK_RED = 0x001F  # 5-bit red mask for BGR555
COLOR_MASK_GREEN = 0x03E0  # 5-bit green mask for BGR555
COLOR_MASK_BLUE = 0x7C00  # 5-bit blue mask for BGR555
COLOR_SHIFT_GREEN = 5  # Bit shift for green component
COLOR_SHIFT_BLUE = 10  # Bit shift for blue component
PALETTE_ATTR_MASK = 0x07  # OAM palette attribute mask (bits 0-2)
OAM_Y_VISIBLE_THRESHOLD = 0xE0  # Y position threshold for visible sprites (224)

# Pixel operations
PIXEL_MASK_4BIT = 0x0F  # Mask for 4-bit pixel values
PIXEL_GRAY_SCALE = 17  # Scale factor for 4-bit to 8-bit gray (0-15 -> 0-255)

# Image validation
IMAGE_DIMENSION_MULTIPLE = 8  # Image dimensions must be multiples of 8
MIN_IMAGE_DIMENSION = 8  # Minimum image dimension (1 tile)
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # Maximum image file size (10MB)
MAX_JSON_SIZE = 1 * 1024 * 1024  # Maximum JSON file size (1MB)

# Cache settings
CACHE_SIZE_MIN_MB = 10  # Minimum cache size in MB
CACHE_SIZE_MAX_MB = 10000  # Maximum cache size in MB (10GB)
CACHE_EXPIRATION_MIN_DAYS = 1  # Minimum cache expiration in days
CACHE_EXPIRATION_MAX_DAYS = 365  # Maximum cache expiration in days
CACHE_EXPIRATION_TO_SECONDS = 24 * 3600  # Convert days to seconds multiplier

# Sprite size constraints for advanced search
MIN_SPRITE_SIZE = 0x100  # Minimum sprite size (256 bytes, 8 tiles)
MAX_SPRITE_SIZE = 0x10000  # Maximum sprite size (64KB, 2048 tiles)
DEFAULT_SCAN_STEP = ROM_SCAN_STEP_DEFAULT  # Default scan step for sprite finding

# Miscellaneous
BYTE_FREQUENCY_SAMPLE_SIZE = 256  # Sample size for byte frequency analysis
MAX_TILE_COUNT_DEFAULT = 8192  # Default maximum tile count validation

# Worker thread timing constants (in seconds)
# These are used by core/ layer and should not depend on ui/
SLEEP_WORKER = 0.1  # 100ms sleep for worker threads
SLEEP_BATCH = 0.05  # 50ms sleep for batch processing

# Preview cache configuration
PREVIEW_CACHE_DEFAULT_MAX_ITEMS = 50  # Maximum items in preview cache
PREVIEW_CACHE_DEFAULT_MAX_MB = 32  # Maximum cache size in MB
PREVIEW_CACHE_MIN_MB = 8  # Minimum cache size in MB
PREVIEW_CACHE_MAX_MB = 256  # Maximum cache size in MB
PREVIEW_CACHE_STATS_LOG_INTERVAL = 60.0  # Seconds between stats logs

# Parallel processing chunk sizes
CHUNK_SIZE_PARALLEL = 0x40000  # 256KB chunks for parallel sprite finding
DECOMPRESSION_WINDOW_SIZE = 0x20000  # 128KB window for ROM decompression

# Scan size limits
MAX_SAFE_SCAN_SIZE = ROM_SIZE_4MB  # 4MB - Safe scan limit for performance
MAX_SCAN_SIZE = 0x2000000  # 32MB - Absolute maximum scan size
