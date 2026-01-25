"""Shared helper functions for frame mapping tests.

This module provides common helper functions for creating test data
in frame mapping controller and UI tests. Use these instead of
defining inline helpers in individual test files.

Usage:
    from tests.fixtures.frame_mapping_helpers import (
        create_test_capture,
        create_ai_frames,
        create_test_project,
    )
"""

from __future__ import annotations

from pathlib import Path

from core.frame_mapping_project import AIFrame, FrameMappingProject

# Minimal 1x1 transparent PNG data for test files
MINIMAL_PNG_DATA = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
    b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def create_test_capture(
    entry_ids: list[int],
    rom_offsets: list[int] | None = None,
) -> dict:
    """Create a minimal capture with entries having the given IDs.

    Args:
        entry_ids: List of entry IDs to create
        rom_offsets: Optional list of ROM offsets per entry. If not provided,
                     each entry gets a unique offset based on its index.

    Returns:
        Dictionary matching the Mesen capture JSON format.
    """
    entries = []
    if rom_offsets is None:
        rom_offsets = [0x100000 + i * 0x100 for i in range(len(entry_ids))]

    for i, entry_id in enumerate(entry_ids):
        rom_offset = rom_offsets[i] if i < len(rom_offsets) else 0x100000 + i * 0x100
        entries.append(
            {
                "id": entry_id,
                "x": 50 + i * 10,  # Small offset to stay within [-256, 255]
                "y": 100,
                "tile": i,
                "width": 8,  # Use 8x8 sprites to match single tile
                "height": 8,
                "palette": 7,
                "rom_offset": rom_offset,
                "tiles": [
                    {
                        "tile_index": 0,
                        "vram_addr": 0x1000 + i * 0x20,
                        "pos_x": 0,
                        "pos_y": 0,
                        "data_hex": "00" * 32,
                        "rom_offset": rom_offset,
                        "tile_index_in_block": 0,
                    }
                ],
            }
        )
    return {
        "frame": 1,
        "obsel": {},
        "entries": entries,
        "palettes": {7: [[0, 0, 0]] * 16},
    }


def create_ai_frames(tmp_path: Path, num_frames: int = 5) -> list[AIFrame]:
    """Create a list of AIFrame objects with minimal PNG files.

    Args:
        tmp_path: Temporary directory for test files.
        num_frames: Number of AI frames to create.

    Returns:
        List of AIFrame instances with PNG files on disk.
    """
    ai_frames_dir = tmp_path / "ai_frames"
    ai_frames_dir.mkdir(parents=True, exist_ok=True)

    frames: list[AIFrame] = []
    for i in range(num_frames):
        frame_path = ai_frames_dir / f"frame_{i:03d}.png"
        frame_path.write_bytes(MINIMAL_PNG_DATA)
        frames.append(AIFrame(path=frame_path, index=i, width=1, height=1))

    return frames


def create_test_project(tmp_path: Path, num_frames: int = 5) -> FrameMappingProject:
    """Create a test project with multiple AI frames.

    Args:
        tmp_path: Temporary directory for test files.
        num_frames: Number of AI frames to create.

    Returns:
        FrameMappingProject with the specified number of frames.
    """
    ai_frames_dir = tmp_path / "ai_frames"
    ai_frames_dir.mkdir(parents=True, exist_ok=True)

    # Create dummy AI frame image files
    ai_frames: list[AIFrame] = []
    for i in range(num_frames):
        frame_path = ai_frames_dir / f"frame_{i:03d}.png"
        frame_path.write_bytes(MINIMAL_PNG_DATA)
        ai_frames.append(AIFrame(path=frame_path, index=i, width=1, height=1))

    return FrameMappingProject(
        name="test_project",
        ai_frames_dir=ai_frames_dir,
        ai_frames=ai_frames,
        game_frames=[],
        mappings=[],
    )
