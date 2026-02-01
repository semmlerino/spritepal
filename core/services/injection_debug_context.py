"""Context manager for injection debug mode.

Centralizes debug-mode behavior for the injection pipeline:
- Debug directory creation and cleanup
- File logging with automatic handler management
- Debug image saving
- Environment variable configuration

This removes scattered debug code from the critical path in inject_mapping().
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING

from utils.logging_config import get_logger

if TYPE_CHECKING:
    from PIL import Image

logger = get_logger(__name__)


class InjectionDebugContext:
    """Context manager for debug-mode injection behavior.

    Handles:
    - Creating debug output directory
    - Setting up file-based logging with DEBUG level
    - Saving debug images with consistent naming
    - Automatic cleanup on exit (normal or exception)

    Usage:
        with InjectionDebugContext.from_env() as debug_ctx:
            debug_ctx.log("Starting injection")
            debug_ctx.save_debug_image("step1", some_image)
            # ... injection code ...

    When debug is disabled, all methods are no-ops for minimal overhead.
    """

    def __init__(self, enabled: bool = False) -> None:
        """Initialize debug context.

        Args:
            enabled: Whether debug mode is active. When False, all
                    methods become no-ops.
        """
        self._enabled = enabled
        self._debug_dir: Path | None = None
        self._log_handler: logging.FileHandler | None = None
        self._original_log_level: int | None = None
        self._entered = False

    @classmethod
    def from_env(cls) -> InjectionDebugContext:
        """Create debug context from SPRITEPAL_INJECT_DEBUG env var.

        Returns:
            InjectionDebugContext with enabled=True if env var is "true",
            otherwise enabled=False.
        """
        env_value = os.environ.get("SPRITEPAL_INJECT_DEBUG", "").lower()
        enabled = env_value == "true"
        return cls(enabled=enabled)

    @property
    def enabled(self) -> bool:
        """Return True if debug mode is active."""
        return self._enabled

    @property
    def debug_dir(self) -> Path | None:
        """Return debug output directory, or None if disabled.

        Only valid after entering the context manager.
        """
        return self._debug_dir

    @property
    def force_raw(self) -> bool:
        """Return True if RAW compression should be forced in debug mode.

        Debug mode forces RAW to avoid HAL corruption during debugging.
        """
        return self._enabled

    def __enter__(self) -> InjectionDebugContext:
        """Enter debug context, setting up directory and logging."""
        self._entered = True

        if not self._enabled:
            return self

        # Create debug directory inside spritepal/logs/inject_debug/
        spritepal_root = Path(__file__).parent.parent.parent
        self._debug_dir = spritepal_root / "logs" / "inject_debug"
        self._debug_dir.mkdir(parents=True, exist_ok=True)

        # Set up file handler for debug logging
        log_path = self._debug_dir / "inject_debug.log"
        self._log_handler = logging.FileHandler(log_path, mode="w")
        self._log_handler.setLevel(logging.DEBUG)
        self._log_handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))

        # Temporarily elevate logger level to DEBUG
        self._original_log_level = logger.level
        logger.setLevel(logging.DEBUG)
        logger.addHandler(self._log_handler)

        logger.info("=== INJECTION DEBUG MODE ===")
        logger.info("Debug output directory: %s", self._debug_dir)
        logger.info("Debug log file: %s", log_path)
        logger.info("Force RAW mode: %s", self.force_raw)

        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit debug context, cleaning up logging handlers."""
        if not self._enabled:
            return

        # Log exit status
        if exc_type is not None:
            logger.info("=== INJECTION DEBUG FAILED (exception) ===")
            logger.info("Exception: %s: %s", exc_type.__name__, exc_val)
        else:
            logger.info("=== INJECTION DEBUG COMPLETE ===")

        if self._debug_dir is not None:
            logger.info("Debug output saved to: %s", self._debug_dir)

        # Clean up file handler
        if self._log_handler is not None:
            self._log_handler.flush()
            self._log_handler.close()
            logger.removeHandler(self._log_handler)
            self._log_handler = None

        # Restore original log level
        if self._original_log_level is not None:
            logger.setLevel(self._original_log_level)
            self._original_log_level = None

    def log(self, message: str, *args: object) -> None:
        """Log a debug message if debug mode is enabled.

        Args:
            message: Log message (may contain % formatting)
            *args: Arguments for % formatting
        """
        if self._enabled:
            logger.info(message, *args)

    def save_debug_image(self, name: str, image: Image.Image) -> None:
        """Save a debug image if debug mode is enabled.

        Args:
            name: Image name (without extension). Will be saved as PNG.
            image: PIL Image to save.
        """
        if not self._enabled or self._debug_dir is None:
            return

        try:
            output_path = self._debug_dir / f"{name}.png"
            image.save(output_path)
            logger.info("Saved debug image: %s", output_path.name)
        except Exception as e:
            logger.warning("Failed to save debug image '%s': %s", name, e)

    def log_tile_details(
        self,
        rom_offset: int,
        entry_id: int,
        tile_pos: tuple[int, int],
        local_pos: tuple[int, int],
        screen_pos: tuple[int, int],
        flip_h: bool,
        vram_addr: int,
    ) -> None:
        """Log detailed tile information for debugging.

        Args:
            rom_offset: Tile's ROM offset
            entry_id: OAM entry ID
            tile_pos: Tile position within entry (x, y)
            local_pos: Local position after flip (x, y)
            screen_pos: Screen position (x, y)
            flip_h: Horizontal flip flag
            vram_addr: VRAM address
        """
        if not self._enabled:
            return

        logger.info(
            "  Entry %d tile (%d,%d): local=(%d,%d) screen=(%d,%d) flip_h=%s rom=0x%X vram=0x%X",
            entry_id,
            tile_pos[0],
            tile_pos[1],
            local_pos[0],
            local_pos[1],
            screen_pos[0],
            screen_pos[1],
            flip_h,
            rom_offset,
            vram_addr,
        )

    def log_bounding_box(self, x: int, y: int, width: int, height: int) -> None:
        """Log bounding box dimensions.

        Args:
            x, y: Top-left corner
            width, height: Dimensions
        """
        if self._enabled:
            logger.info("Bounding box: x=%d, y=%d, w=%d, h=%d", x, y, width, height)

    def log_entry_count(self, count: int) -> None:
        """Log number of entries being processed.

        Args:
            count: Number of relevant entries
        """
        if self._enabled:
            logger.info("Processing %d relevant entries", count)

    def log_injection_results(self, messages: list[str]) -> None:
        """Log final injection results.

        Args:
            messages: List of result messages for each offset
        """
        if self._enabled:
            logger.info("Injection results:\n%s", "\n".join(messages))

    def log_canvas_info(
        self,
        ai_frame_name: str,
        ai_frame_index: int,
        game_frame_id: str,
        rom_offsets: list[int],
        canvas_width: int,
        canvas_height: int,
        offset_x: int,
        offset_y: int,
        flip_h: bool,
        flip_v: bool,
        scale: float,
    ) -> None:
        """Log AI frame and canvas information.

        Args:
            ai_frame_name: AI frame filename
            ai_frame_index: AI frame index
            game_frame_id: Game frame ID
            rom_offsets: List of ROM offsets
            canvas_width, canvas_height: Canvas dimensions
            offset_x, offset_y: Alignment offsets
            flip_h, flip_v: Flip flags
            scale: Scale factor
        """
        if not self._enabled:
            return

        logger.info("AI frame: %s (index %d)", ai_frame_name, ai_frame_index)
        logger.info("Game frame: %s", game_frame_id)
        logger.info("ROM offsets: %s", [f"0x{o:X}" for o in rom_offsets])
        logger.info(
            "Canvas size: %dx%d, AI alignment: offset=(%d,%d) flip_h=%s flip_v=%s scale=%.2f",
            canvas_width,
            canvas_height,
            offset_x,
            offset_y,
            flip_h,
            flip_v,
            scale,
        )

    def log_offset_correction(self, old_offset: int, new_offset: int) -> None:
        """Log a ROM offset correction.

        Args:
            old_offset: Original offset
            new_offset: Corrected offset
        """
        if self._enabled:
            logger.info("Correcting tile rom_offset: 0x%X → 0x%X", old_offset, new_offset)

    def log_extraction_details(
        self,
        vram_addr: int,
        canvas_pos: tuple[int, int],
        flip_h: bool,
        grid_pos: tuple[int, int],
    ) -> None:
        """Log tile extraction details.

        Args:
            vram_addr: VRAM address
            canvas_pos: Position in canvas (x, y)
            flip_h: Horizontal flip flag
            grid_pos: Position in output grid (x, y)
        """
        if self._enabled:
            logger.info(
                "  Extracted vram=0x%X: canvas=(%d,%d) flip_h=%s → grid=(%d,%d)",
                vram_addr,
                canvas_pos[0],
                canvas_pos[1],
                flip_h,
                grid_pos[0],
                grid_pos[1],
            )

    def log_rom_write_verification(
        self,
        rom_offset: int,
        compression_used: str,
        tile_count: int,
        first_bytes_hex: str,
    ) -> None:
        """Log ROM write verification details.

        Args:
            rom_offset: ROM offset written to
            compression_used: "HAL" or "RAW"
            tile_count: Number of tiles written
            first_bytes_hex: Hex string of first 32 bytes written
        """
        if self._enabled:
            logger.info(
                "ROM 0x%X [%s]: wrote %d tiles, first 32 bytes: %s",
                rom_offset,
                compression_used,
                tile_count,
                first_bytes_hex,
            )

    def log_verification_summary(
        self,
        corrections: dict[int, int | None],
        matched_hal: int,
        matched_raw: int,
        not_found: int,
    ) -> None:
        """Log full verification summary with all corrections.

        Args:
            corrections: Dict of capture_offset -> rom_offset mappings
            matched_hal: Tiles found via HAL index
            matched_raw: Tiles found via raw search
            not_found: Tiles not found in ROM
        """
        if not self._enabled:
            return

        logger.info("=== VERIFICATION SUMMARY ===")
        logger.info("HAL matches: %d, RAW matches: %d, Not found: %d", matched_hal, matched_raw, not_found)
        logger.info("All corrections:")

        # Group by whether offset changed
        unchanged = []
        changed = []
        missing = []

        for capture_off, rom_off in sorted(corrections.items()):
            if rom_off is None:
                missing.append(capture_off)
            elif rom_off == capture_off:
                unchanged.append(capture_off)
            else:
                changed.append((capture_off, rom_off))

        if unchanged:
            logger.info("  Unchanged offsets: %s", [f"0x{o:X}" for o in unchanged])

        if changed:
            logger.info("  Changed offsets:")
            for cap_off, rom_off in changed:
                delta = cap_off - rom_off
                logger.info("    0x%06X -> 0x%05X (delta=0x%X)", cap_off, rom_off, delta)

        if missing:
            logger.info("  Missing offsets: %s", [f"0x{o:X}" for o in missing])

    def log_tile_occurrences(
        self,
        capture_offset: int,
        tile_data_preview: str,
        occurrences: list[int],
        chosen: int | None,
    ) -> None:
        """Log all occurrences found for a tile in ROM.

        Args:
            capture_offset: Original capture offset
            tile_data_preview: First 8 bytes of tile as hex
            occurrences: All ROM offsets where tile was found
            chosen: The offset that was chosen (or None if not found)
        """
        if not self._enabled:
            return

        if len(occurrences) > 1:
            logger.info(
                "  Tile 0x%06X (%s...): found at %s, chose 0x%05X",
                capture_offset,
                tile_data_preview,
                [f"0x{o:X}" for o in occurrences],
                chosen if chosen is not None else 0,
            )
        elif len(occurrences) == 1:
            logger.info(
                "  Tile 0x%06X (%s...): unique at 0x%05X",
                capture_offset,
                tile_data_preview,
                occurrences[0],
            )
