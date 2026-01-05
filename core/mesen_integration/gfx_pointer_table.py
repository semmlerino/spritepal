"""
Parser for Kirby Super Star GFX pointer table.

The GFX pointer table at ROM $3F0002 contains pointers to graphics header
blocks. This module parses the table to map graphics IDs to ROM offsets
where sprite/graphics data is stored.

Reference: Kirby Super Star uses SA-1 enhancement chip.
CPU bank $FF maps to ROM $3F0000.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from utils.logging_config import get_logger

logger = get_logger(__name__)

# ROM constants for Kirby Super Star (SA-1)
GFX_POINTER_TABLE_OFFSET = 0x3F0002  # $FF:0002 in CPU space
LEVEL_POINTER_TABLE_OFFSET = 0x3F000C  # $FF:000C in CPU space
ROM_HEADER_OFFSET = 0x7FC0  # SNES ROM header (LoROM location)
SA1_HEADER_OFFSET = 0xFFC0  # SNES ROM header (HiROM location)


@dataclass
class GFXPointer:
    """Single entry from the GFX pointer table."""

    index: int  # Index in the pointer table
    pointer_value: int  # Raw 24-bit pointer value
    rom_offset: int  # Calculated ROM offset
    is_valid: bool = True
    description: str = ""


@dataclass
class GraphicsHeader:
    """
    Parsed graphics header structure.

    Format observed: 4-byte headers like "4E 57 15 03"
    """

    rom_offset: int  # Where this header is in ROM
    raw_bytes: bytes  # Original 4-8 bytes
    decompressed_size: int = 0  # Expected size after decompression
    destination_vram: int = 0  # VRAM destination address
    compression_type: int = 0  # 0=HAL, 1=uncompressed, etc.
    data_offset: int = 0  # Offset to actual graphics data

    @property
    def data_rom_offset(self) -> int:
        """Calculate ROM offset where actual data starts."""
        return self.rom_offset + len(self.raw_bytes)


@dataclass
class GFXPointerTable:
    """Complete parsed GFX pointer table."""

    rom_path: Path
    table_offset: int
    entries: list[GFXPointer] = field(default_factory=list)
    headers: dict[int, GraphicsHeader] = field(default_factory=dict)

    def get_offset_for_id(self, gfx_id: int) -> int | None:
        """Get ROM offset for a graphics ID."""
        if 0 <= gfx_id < len(self.entries):
            entry = self.entries[gfx_id]
            if entry.is_valid:
                return entry.rom_offset
        return None

    def find_entry_by_offset(self, rom_offset: int, tolerance: int = 0x100) -> GFXPointer | None:
        """Find entry closest to a given ROM offset."""
        for entry in self.entries:
            if abs(entry.rom_offset - rom_offset) <= tolerance:
                return entry
        return None


def sa1_cpu_to_rom(cpu_addr: int) -> int:
    """
    Convert SA-1 CPU address to ROM offset.

    For banks $C0-$FF (linear ROM mapping):
    ROM_offset = ((bank - 0xC0) << 16) | addr_low16
    """
    bank = (cpu_addr >> 16) & 0xFF
    addr_low = cpu_addr & 0xFFFF

    if 0xC0 <= bank <= 0xFF:
        return ((bank - 0xC0) << 16) | addr_low
    elif bank <= 0x3F and addr_low >= 0x8000:
        # LoROM mapping for banks $00-$3F
        return (bank << 15) | (addr_low - 0x8000)
    else:
        logger.warning(f"Unknown SA-1 bank mapping for ${cpu_addr:06X}")
        return cpu_addr


def rom_to_sa1_cpu(rom_offset: int) -> int:
    """
    Convert ROM offset to SA-1 CPU address.

    Uses linear mapping via banks $C0-$FF.
    """
    bank = (rom_offset >> 16) + 0xC0
    addr_low = rom_offset & 0xFFFF
    return (bank << 16) | addr_low


class GFXPointerTableParser:
    """Parser for Kirby Super Star GFX pointer table."""

    def __init__(self, rom_path: str | Path):
        """
        Initialize parser with ROM path.

        Args:
            rom_path: Path to Kirby Super Star ROM file
        """
        self.rom_path = Path(rom_path)
        self._rom_data: bytes | None = None

    def _load_rom(self) -> bytes:
        """Load ROM data if not already loaded."""
        if self._rom_data is None:
            self._rom_data = self.rom_path.read_bytes()
            logger.info(f"Loaded ROM: {len(self._rom_data)} bytes")
        return self._rom_data

    def _read_bytes(self, offset: int, count: int) -> bytes:
        """Read bytes from ROM at given offset."""
        rom = self._load_rom()
        if offset + count > len(rom):
            raise ValueError(f"Read beyond ROM: offset {offset:X} + {count} > {len(rom):X}")
        return rom[offset : offset + count]

    def _read_word(self, offset: int) -> int:
        """Read 16-bit little-endian word from ROM."""
        data = self._read_bytes(offset, 2)
        return data[0] | (data[1] << 8)

    def _read_long(self, offset: int) -> int:
        """Read 24-bit little-endian address from ROM."""
        data = self._read_bytes(offset, 3)
        return data[0] | (data[1] << 8) | (data[2] << 16)

    def detect_rom_type(self) -> dict[str, object]:
        """
        Detect ROM type and mapping mode.

        Returns:
            Dict with 'is_sa1', 'map_mode', 'rom_type', 'rom_size'
        """
        rom = self._load_rom()
        result: dict[str, object] = {}

        # Try HiROM header location first (SA-1 games use this)
        if len(rom) >= SA1_HEADER_OFFSET + 32:
            header = self._read_bytes(SA1_HEADER_OFFSET, 32)
            map_mode = header[0x15]  # Offset $FFD5
            rom_type = header[0x16]  # Offset $FFD6
            rom_size = header[0x17]  # Offset $FFD7

            result["header_location"] = "HiROM ($FFC0)"
            result["map_mode"] = map_mode
            result["rom_type"] = rom_type
            result["rom_size_code"] = rom_size
            result["rom_size_bytes"] = 0x400 << rom_size if rom_size < 16 else 0
            result["is_sa1"] = map_mode == 0x23 or rom_type == 0x35

        # Check LoROM header location as fallback
        if len(rom) >= ROM_HEADER_OFFSET + 32:
            header = self._read_bytes(ROM_HEADER_OFFSET, 32)
            lo_map_mode = header[0x15]
            lo_rom_type = header[0x16]

            result["lorom_map_mode"] = lo_map_mode
            result["lorom_rom_type"] = lo_rom_type

        # Read title
        if result.get("is_sa1"):
            title_bytes = self._read_bytes(SA1_HEADER_OFFSET, 21)
        else:
            title_bytes = self._read_bytes(ROM_HEADER_OFFSET, 21)
        result["title"] = title_bytes.rstrip(b"\x00 ").decode("ascii", errors="replace")

        return result

    def parse_pointer_table(
        self,
        table_offset: int = GFX_POINTER_TABLE_OFFSET,
        max_entries: int = 256,
    ) -> GFXPointerTable:
        """
        Parse the GFX pointer table.

        Args:
            table_offset: ROM offset of pointer table (default: $3F0002)
            max_entries: Maximum entries to read

        Returns:
            GFXPointerTable with parsed entries
        """
        result = GFXPointerTable(
            rom_path=self.rom_path,
            table_offset=table_offset,
        )

        logger.info(f"Parsing GFX pointer table at ROM ${table_offset:06X}")

        rom = self._load_rom()
        offset = table_offset
        entries_read = 0

        while entries_read < max_entries and offset + 2 <= len(rom):
            # Read 16-bit pointer value
            ptr_value = self._read_word(offset)

            # Check for table terminator (usually 0x0000 or 0xFFFF)
            if ptr_value in {0x0000, 0xFFFF}:
                logger.info(f"Found table terminator at entry {entries_read}")
                break

            # Convert to full address (assume bank $3F for relative pointers)
            if ptr_value < 0x8000:
                # Absolute offset within current bank
                full_addr = (0x3F << 16) | ptr_value
            else:
                # Direct CPU address
                full_addr = ptr_value

            # Convert to ROM offset
            rom_offset = sa1_cpu_to_rom(full_addr) if full_addr > 0xFFFF else ptr_value

            entry = GFXPointer(
                index=entries_read,
                pointer_value=ptr_value,
                rom_offset=rom_offset,
                is_valid=rom_offset < len(rom),
            )

            result.entries.append(entry)
            entries_read += 1
            offset += 2

        logger.info(f"Parsed {len(result.entries)} pointer table entries")
        return result

    def scan_for_graphics_headers(
        self,
        start_offset: int = 0x180000,
        end_offset: int = 0x200000,
        step: int = 0x1000,
    ) -> list[GraphicsHeader]:
        """
        Scan ROM region for graphics header patterns.

        Graphics headers typically start with identifiable patterns.
        HAL compression headers often have specific byte sequences.

        Args:
            start_offset: Start of scan region
            end_offset: End of scan region
            step: Scan step size

        Returns:
            List of discovered headers
        """
        headers: list[GraphicsHeader] = []
        rom = self._load_rom()

        logger.info(f"Scanning for graphics headers: ${start_offset:06X}-${end_offset:06X}")

        for offset in range(start_offset, min(end_offset, len(rom)), step):
            # Read potential header bytes
            if offset + 8 > len(rom):
                break

            header_bytes = self._read_bytes(offset, 8)

            # Check for HAL compression marker
            # HAL compressed data often starts with specific patterns
            is_hal = self._check_hal_header(header_bytes)

            if is_hal:
                header = GraphicsHeader(
                    rom_offset=offset,
                    raw_bytes=header_bytes,
                    compression_type=0,  # HAL
                )
                headers.append(header)
                logger.debug(f"Found HAL header at ${offset:06X}: {header_bytes[:4].hex()}")

        logger.info(f"Found {len(headers)} potential graphics headers")
        return headers

    def _check_hal_header(self, data: bytes) -> bool:
        """
        Check if data looks like a HAL compression header.

        HAL compression uses a command byte system where:
        - Bits 4-7: Command type
        - Bits 0-3: Length (varies by command)

        Valid HAL headers typically have reasonable first command bytes.
        """
        if len(data) < 4:
            return False

        first_byte = data[0]

        # HAL command types (upper nibble):
        # 0x00-0x7F: Direct copy (length in lower bits + next byte)
        # 0x80-0xBF: RLE
        # 0xC0-0xDF: Pattern copy
        # 0xE0-0xFE: Back reference
        # 0xFF: End marker

        # Check for valid command byte range
        if first_byte == 0xFF:
            # End marker alone is not a valid header
            return False

        # Check for reasonable data following
        # (Avoid false positives from random data)
        cmd_type = first_byte & 0xE0

        if cmd_type == 0x00:
            # Direct copy - length should be reasonable
            length = first_byte & 0x1F
            if length == 0:
                return False
        elif cmd_type in (0x80, 0xA0):
            # RLE - should have valid run byte
            pass
        elif cmd_type == 0xE0:
            # Back reference - offset bytes should be reasonable
            pass

        return True

    def dump_table_region(
        self,
        offset: int,
        count: int = 64,
        words_per_line: int = 8,
    ) -> str:
        """
        Dump raw bytes from ROM as hex for inspection.

        Args:
            offset: ROM offset to start
            count: Number of bytes to dump
            words_per_line: 16-bit words per line

        Returns:
            Formatted hex dump string
        """
        rom = self._load_rom()
        lines: list[str] = []

        for i in range(0, count, words_per_line * 2):
            line_offset = offset + i
            words: list[str] = []

            for j in range(words_per_line):
                byte_offset = line_offset + j * 2
                if byte_offset + 2 <= len(rom):
                    word = self._read_word(byte_offset)
                    words.append(f"{word:04X}")
                else:
                    words.append("----")

            lines.append(f"${line_offset:06X}: {' '.join(words)}")

        return "\n".join(lines)

    def analyze_known_offsets(self) -> dict[int, dict[str, object]]:
        """
        Analyze known sprite ROM offsets.

        Cross-references known working offsets with the pointer table.

        Returns:
            Dict mapping ROM offset to analysis results
        """
        known_offsets = [
            (0x1B0000, "Kirby sprites"),
            (0x1A0000, "Enemy sprites"),
            (0x180000, "Items/UI"),
            (0x190000, "Background tiles"),
            (0x1C0000, "Background gradients"),
            (0x280000, "Additional sprites"),
            (0x0E0000, "Title screen/fonts"),
        ]

        results: dict[int, dict[str, object]] = {}
        rom = self._load_rom()

        for offset, description in known_offsets:
            result: dict[str, object] = {"description": description}

            if offset < len(rom):
                # Read first 16 bytes for analysis
                header = self._read_bytes(offset, min(16, len(rom) - offset))
                result["header_hex"] = header.hex()
                result["is_hal"] = self._check_hal_header(header)

                # Calculate SA-1 CPU address
                result["sa1_cpu_addr"] = f"${rom_to_sa1_cpu(offset):06X}"

                # Check if offset appears in pointer table
                result["in_pointer_table"] = False
            else:
                result["error"] = "Beyond ROM size"

            results[offset] = result

        return results


def create_gfx_offset_map(rom_path: str | Path) -> dict[str, object]:
    """
    Create a complete mapping of graphics IDs to ROM offsets.

    This is the main entry point for using the parser.

    Args:
        rom_path: Path to Kirby Super Star ROM

    Returns:
        Dict containing:
        - 'rom_info': ROM type detection results
        - 'pointer_table': Parsed pointer table
        - 'known_offsets': Analysis of known sprite offsets
        - 'discovered_headers': Graphics headers found by scanning
    """
    parser = GFXPointerTableParser(rom_path)

    result: dict[str, object] = {}

    # 1. Detect ROM type
    result["rom_info"] = parser.detect_rom_type()
    logger.info(f"ROM Info: {result['rom_info']}")

    # 2. Parse pointer table
    ptr_table = parser.parse_pointer_table()
    result["pointer_table"] = {
        "offset": ptr_table.table_offset,
        "entry_count": len(ptr_table.entries),
        "entries": [
            {
                "index": e.index,
                "pointer": f"${e.pointer_value:04X}",
                "rom_offset": f"${e.rom_offset:06X}",
                "valid": e.is_valid,
            }
            for e in ptr_table.entries[:50]  # First 50 for brevity
        ],
    }

    # 3. Analyze known offsets
    result["known_offsets"] = {f"${k:06X}": v for k, v in parser.analyze_known_offsets().items()}

    # 4. Dump raw pointer table region
    result["pointer_table_hex"] = parser.dump_table_region(GFX_POINTER_TABLE_OFFSET, 128)

    # 5. Scan for graphics headers
    discovered = parser.scan_for_graphics_headers()
    result["discovered_headers"] = [
        {"offset": f"${h.rom_offset:06X}", "header": h.raw_bytes[:4].hex()} for h in discovered
    ]

    return result
