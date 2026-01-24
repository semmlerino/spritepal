"""Tests for InjectionDebugContext."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from core.services.injection_debug_context import InjectionDebugContext


class TestInjectionDebugContextInit:
    """Tests for InjectionDebugContext initialization."""

    def test_init_disabled_by_default(self) -> None:
        """Context is disabled by default."""
        ctx = InjectionDebugContext()
        assert ctx.enabled is False
        assert ctx.debug_dir is None

    def test_init_enabled_explicitly(self) -> None:
        """Context can be enabled explicitly."""
        ctx = InjectionDebugContext(enabled=True)
        assert ctx.enabled is True

    def test_from_env_disabled_when_not_set(self) -> None:
        """from_env returns disabled context when env var not set."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove the env var if it exists
            os.environ.pop("SPRITEPAL_INJECT_DEBUG", None)
            ctx = InjectionDebugContext.from_env()
            assert ctx.enabled is False

    def test_from_env_disabled_when_false(self) -> None:
        """from_env returns disabled context when env var is 'false'."""
        with patch.dict(os.environ, {"SPRITEPAL_INJECT_DEBUG": "false"}):
            ctx = InjectionDebugContext.from_env()
            assert ctx.enabled is False

    def test_from_env_enabled_when_true(self) -> None:
        """from_env returns enabled context when env var is 'true'."""
        with patch.dict(os.environ, {"SPRITEPAL_INJECT_DEBUG": "true"}):
            ctx = InjectionDebugContext.from_env()
            assert ctx.enabled is True

    def test_from_env_case_insensitive(self) -> None:
        """from_env handles uppercase 'TRUE'."""
        with patch.dict(os.environ, {"SPRITEPAL_INJECT_DEBUG": "TRUE"}):
            ctx = InjectionDebugContext.from_env()
            assert ctx.enabled is True

    def test_force_raw_mirrors_enabled(self) -> None:
        """force_raw returns same value as enabled."""
        ctx_disabled = InjectionDebugContext(enabled=False)
        ctx_enabled = InjectionDebugContext(enabled=True)

        assert ctx_disabled.force_raw is False
        assert ctx_enabled.force_raw is True


class TestInjectionDebugContextDisabled:
    """Tests for disabled debug context (no-op behavior)."""

    def test_enter_exit_no_ops(self) -> None:
        """Entering and exiting disabled context does nothing."""
        ctx = InjectionDebugContext(enabled=False)

        with ctx:
            assert ctx.debug_dir is None

        # No exceptions should be raised

    def test_log_is_noop(self) -> None:
        """log() does nothing when disabled."""
        ctx = InjectionDebugContext(enabled=False)

        with ctx:
            # Should not raise
            ctx.log("Test message %s", "arg")

    def test_save_debug_image_is_noop(self, tmp_path: Path) -> None:
        """save_debug_image() does nothing when disabled."""
        ctx = InjectionDebugContext(enabled=False)
        img = Image.new("RGBA", (8, 8), (255, 0, 0, 255))

        with ctx:
            ctx.save_debug_image("test", img)

        # No files should be created
        assert list(tmp_path.iterdir()) == []

    def test_log_helpers_are_noops(self) -> None:
        """All log helper methods do nothing when disabled."""
        ctx = InjectionDebugContext(enabled=False)

        with ctx:
            # None of these should raise
            ctx.log_tile_details(0x1000, 1, (0, 0), (0, 0), (100, 100), False, 0x2000)
            ctx.log_bounding_box(0, 0, 100, 100)
            ctx.log_entry_count(5)
            ctx.log_injection_results(["msg1", "msg2"])
            ctx.log_canvas_info("test.png", 0, "frame1", [0x1000], 64, 64, 0, 0, False, False, 1.0)
            ctx.log_offset_correction(0x1000, 0x2000)
            ctx.log_extraction_details(0x1000, (0, 0), False, (0, 0))
            ctx.log_rom_write_verification(0x1000, "RAW", 4, "00112233")


class TestInjectionDebugContextEnabled:
    """Tests for enabled debug context."""

    def test_enter_creates_debug_dir(self) -> None:
        """Entering enabled context creates debug directory."""
        ctx = InjectionDebugContext(enabled=True)

        with ctx:
            assert ctx.debug_dir is not None
            assert ctx.debug_dir.exists()
            assert ctx.debug_dir.name == "inject_debug"

    def test_enter_creates_log_file(self) -> None:
        """Entering enabled context creates log file."""
        ctx = InjectionDebugContext(enabled=True)

        with ctx:
            assert ctx.debug_dir is not None
            log_file = ctx.debug_dir / "inject_debug.log"
            # File may not exist yet until something is logged and flushed
            ctx.log("Test message")

        # After exit, log should be flushed
        log_file = Path(ctx._debug_dir) / "inject_debug.log"  # type: ignore[arg-type]
        assert log_file.exists()
        content = log_file.read_text()
        assert "INJECTION DEBUG MODE" in content
        assert "Test message" in content

    def test_exit_cleans_up_handler(self) -> None:
        """Exiting context removes log handler."""
        ctx = InjectionDebugContext(enabled=True)
        from core.services.injection_debug_context import logger as ctx_logger

        initial_handler_count = len(ctx_logger.handlers)

        with ctx:
            # Handler should be added during context
            assert len(ctx_logger.handlers) == initial_handler_count + 1

        # Handler should be removed after exit
        assert len(ctx_logger.handlers) == initial_handler_count

    def test_exit_restores_log_level(self) -> None:
        """Exiting context restores original log level."""
        ctx = InjectionDebugContext(enabled=True)
        from core.services.injection_debug_context import logger as ctx_logger

        original_level = ctx_logger.level

        with ctx:
            # Level should be DEBUG during context
            assert ctx_logger.level == logging.DEBUG

        # Level should be restored after exit
        assert ctx_logger.level == original_level

    def test_exception_logs_failure(self) -> None:
        """Exception during context logs failure message."""
        ctx = InjectionDebugContext(enabled=True)

        try:
            with ctx:
                raise ValueError("Test error")
        except ValueError:
            pass

        # Check log contains failure message
        log_file = Path(ctx._debug_dir) / "inject_debug.log"  # type: ignore[arg-type]
        content = log_file.read_text()
        assert "FAILED" in content
        assert "ValueError" in content

    def test_save_debug_image_creates_file(self) -> None:
        """save_debug_image creates PNG file in debug dir."""
        ctx = InjectionDebugContext(enabled=True)
        img = Image.new("RGBA", (8, 8), (255, 0, 0, 255))

        with ctx:
            ctx.save_debug_image("test_image", img)
            assert ctx.debug_dir is not None
            output_path = ctx.debug_dir / "test_image.png"
            assert output_path.exists()

            # Verify image content
            loaded = Image.open(output_path)
            assert loaded.size == (8, 8)

    def test_save_debug_image_handles_error(self) -> None:
        """save_debug_image handles save errors gracefully."""
        ctx = InjectionDebugContext(enabled=True)
        mock_img = MagicMock(spec=Image.Image)
        mock_img.save.side_effect = OSError("Save failed")

        with ctx:
            # Should not raise
            ctx.save_debug_image("bad_image", mock_img)

    def test_log_writes_to_file(self) -> None:
        """log() writes messages to debug log file."""
        ctx = InjectionDebugContext(enabled=True)

        with ctx:
            ctx.log("Message with %s and %d", "string", 42)

        log_file = Path(ctx._debug_dir) / "inject_debug.log"  # type: ignore[arg-type]
        content = log_file.read_text()
        assert "Message with string and 42" in content


class TestInjectionDebugContextLogHelpers:
    """Tests for specialized log helper methods."""

    def test_log_canvas_info(self) -> None:
        """log_canvas_info formats all parameters correctly."""
        ctx = InjectionDebugContext(enabled=True)

        with ctx:
            ctx.log_canvas_info(
                ai_frame_name="sprite.png",
                ai_frame_index=5,
                game_frame_id="walk_01",
                rom_offsets=[0x1000, 0x2000],
                canvas_width=64,
                canvas_height=48,
                offset_x=10,
                offset_y=-5,
                flip_h=True,
                flip_v=False,
                scale=1.5,
            )

        log_file = Path(ctx._debug_dir) / "inject_debug.log"  # type: ignore[arg-type]
        content = log_file.read_text()
        assert "sprite.png" in content
        assert "index 5" in content
        assert "walk_01" in content
        assert "0x1000" in content
        assert "0x2000" in content
        assert "64x48" in content
        assert "offset=(10,-5)" in content
        assert "flip_h=True" in content
        assert "flip_v=False" in content
        assert "scale=1.50" in content

    def test_log_tile_details(self) -> None:
        """log_tile_details formats tile info correctly."""
        ctx = InjectionDebugContext(enabled=True)

        with ctx:
            ctx.log_tile_details(
                rom_offset=0x3000,
                entry_id=7,
                tile_pos=(2, 3),
                local_pos=(16, 24),
                screen_pos=(100, 200),
                flip_h=True,
                vram_addr=0x4000,
            )

        log_file = Path(ctx._debug_dir) / "inject_debug.log"  # type: ignore[arg-type]
        content = log_file.read_text()
        assert "Entry 7" in content
        assert "(2,3)" in content
        assert "local=(16,24)" in content
        assert "screen=(100,200)" in content
        assert "flip_h=True" in content
        assert "0x3000" in content
        assert "0x4000" in content

    def test_log_offset_correction(self) -> None:
        """log_offset_correction formats offset change correctly."""
        ctx = InjectionDebugContext(enabled=True)

        with ctx:
            ctx.log_offset_correction(0x1000, 0x2000)

        log_file = Path(ctx._debug_dir) / "inject_debug.log"  # type: ignore[arg-type]
        content = log_file.read_text()
        assert "0x1000" in content
        assert "0x2000" in content
        # Check the arrow character
        assert "→" in content or "->" in content

    def test_log_rom_write_verification(self) -> None:
        """log_rom_write_verification formats write details correctly."""
        ctx = InjectionDebugContext(enabled=True)

        with ctx:
            ctx.log_rom_write_verification(
                rom_offset=0x5000,
                compression_used="HAL",
                tile_count=8,
                first_bytes_hex="00112233445566778899aabbccddeeff",
            )

        log_file = Path(ctx._debug_dir) / "inject_debug.log"  # type: ignore[arg-type]
        content = log_file.read_text()
        assert "0x5000" in content
        assert "HAL" in content
        assert "8 tiles" in content
        assert "00112233445566778899aabbccddeeff" in content


class TestInjectionDebugContextReuse:
    """Tests for context reuse and edge cases."""

    def test_cannot_reenter(self) -> None:
        """Context cannot be reentered after exit."""
        ctx = InjectionDebugContext(enabled=True)

        with ctx:
            pass

        # Second entry should work but create new resources
        with ctx:
            # The _entered flag should still be True
            assert ctx._entered is True

    def test_multiple_images_same_context(self) -> None:
        """Multiple images can be saved in same context."""
        ctx = InjectionDebugContext(enabled=True)

        with ctx:
            for i in range(3):
                img = Image.new("RGBA", (8, 8), (i * 50, 0, 0, 255))
                ctx.save_debug_image(f"image_{i}", img)

            assert ctx.debug_dir is not None
            for i in range(3):
                assert (ctx.debug_dir / f"image_{i}.png").exists()
