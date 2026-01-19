"""VRAM Attribution Loader.

Loads VRAM→ROM attribution data exported by sprite_rom_finder.lua (E key).
This allows tracing captured VRAM tiles back to their source ROM offsets.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class VRAMAttribution:
    """Attribution data for a single VRAM tile."""

    vram_word: int  # VRAM word address
    vram_byte: int  # VRAM byte address (vram_word * 2)
    idx: int | None  # FE52 pointer table index
    ptr: int | None  # CPU pointer (e.g., 0xE96553)
    file_offset: int | None  # ROM file offset
    frame: int | None  # Frame when this was captured


@dataclass
class VRAMAttributionMap:
    """Complete VRAM→ROM attribution map from sprite_rom_finder.lua export."""

    export_frame: int
    export_time: str
    entries: dict[int, VRAMAttribution]  # Keyed by vram_word

    def get_by_vram_addr(self, vram_addr: int) -> VRAMAttribution | None:
        """Get attribution by VRAM byte address (as used in captures)."""
        # Convert byte address to word address
        vram_word = vram_addr // 2
        return self.entries.get(vram_word)

    def get_rom_offset(self, vram_addr: int) -> int | None:
        """Get ROM file offset for a VRAM address, or None if not found."""
        attr = self.get_by_vram_addr(vram_addr)
        return attr.file_offset if attr else None

    def get_unique_rom_offsets(self) -> set[int]:
        """Get all unique ROM offsets in this attribution map."""
        offsets = set()
        for entry in self.entries.values():
            if entry.file_offset is not None:
                offsets.add(entry.file_offset)
        return offsets


def load_vram_attribution(path: str | Path) -> VRAMAttributionMap | None:
    """Load VRAM attribution data from JSON file.

    Args:
        path: Path to vram_attribution.json (or directory containing it)

    Returns:
        VRAMAttributionMap or None if file not found/invalid
    """
    path = Path(path)

    # If path is a directory, look for vram_attribution.json inside
    if path.is_dir():
        path = path / "vram_attribution.json"

    if not path.exists():
        logger.debug(f"VRAM attribution file not found: {path}")
        return None

    try:
        with open(path) as f:
            data = json.load(f)

        entries: dict[int, VRAMAttribution] = {}
        for entry_data in data.get("entries", []):
            vram_word = entry_data.get("vram_word")
            if vram_word is None:
                continue

            entries[vram_word] = VRAMAttribution(
                vram_word=vram_word,
                vram_byte=entry_data.get("vram_byte", vram_word * 2),
                idx=entry_data.get("idx"),
                ptr=entry_data.get("ptr"),
                file_offset=entry_data.get("file_offset"),
                frame=entry_data.get("frame"),
            )

        result = VRAMAttributionMap(
            export_frame=data.get("export_frame", 0),
            export_time=data.get("export_time", ""),
            entries=entries,
        )

        logger.info(
            f"Loaded VRAM attribution: {len(entries)} entries, "
            f"{len(result.get_unique_rom_offsets())} unique ROM offsets"
        )
        return result

    except (json.JSONDecodeError, KeyError) as e:
        logger.warning(f"Failed to parse VRAM attribution file: {e}")
        return None


def find_attribution_file(capture_path: str | Path) -> Path | None:
    """Find the VRAM attribution file for a capture.

    Searches in order:
    1. Same directory as capture file
    2. mesen2_exchange directory

    Args:
        capture_path: Path to the capture JSON file

    Returns:
        Path to vram_attribution.json if found, None otherwise
    """
    capture_path = Path(capture_path)

    # Check same directory as capture
    same_dir = capture_path.parent / "vram_attribution.json"
    if same_dir.exists():
        return same_dir

    # Check mesen2_exchange directory
    exchange_dir = Path(__file__).parent.parent.parent / "mesen2_exchange"
    exchange_file = exchange_dir / "vram_attribution.json"
    if exchange_file.exists():
        return exchange_file

    return None
