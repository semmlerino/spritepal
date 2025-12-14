"""
Qt worker thread for ROM injection process.

This module contains the Qt-specific worker thread for ROM injection.
Moved from ui/workers/ to core/workers/ to fix layer boundary violations.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal
from typing_extensions import override

from core.rom_injector import ROMInjector
from core.rom_validator import ROMValidator
from core.sprite_validator import SpriteValidator
from utils.logging_config import get_logger

logger = get_logger(__name__)


class ROMInjectionWorker(QThread):
    """Worker thread for ROM injection process with detailed progress"""

    progress: Signal = Signal(str)  # Status message
    progress_percent: Signal = Signal(int)  # Progress percentage (0-100)
    compression_info: Signal = Signal(dict)  # Compression statistics
    injection_finished: Signal = Signal(bool, str)  # Success, message

    def __init__(
        self,
        sprite_path: str,
        rom_input: str,
        rom_output: str,
        sprite_offset: int,
        fast_compression: bool = False,
        metadata_path: str | None = None,
    ):
        super().__init__()
        self.sprite_path: str = sprite_path
        self.rom_input: str = rom_input
        self.rom_output: str = rom_output
        self.sprite_offset: int = sprite_offset
        self.fast_compression: bool = fast_compression
        self.metadata_path: str | None = metadata_path
        self.injector: ROMInjector = ROMInjector()

        # Auto-register with WorkerManager for cleanup_all()
        from core.services.worker_lifecycle import WorkerManager
        WorkerManager._register_worker(self)

    @override
    def run(self) -> None:
        """Run the ROM injection process with detailed progress reporting"""
        logger.info(f"Starting ROM injection worker: sprite={self.sprite_path}, rom={self.rom_input}")
        logger.debug(f"Injection parameters: offset=0x{self.sprite_offset:X}, fast_compression={self.fast_compression}")
        try:
            # Validate output path early to prevent silent fallback to input path
            if not self.rom_output or not self.rom_output.strip():
                self.injection_finished.emit(False, "Output ROM path is required. Please specify an output file.")
                return

            output_path = Path(self.rom_output)
            if not output_path.parent.exists():
                self.injection_finished.emit(
                    False,
                    f"Output directory does not exist: {output_path.parent}"
                )
                return

            total_steps = 6
            current_step = 0

            # Step 1: Load metadata if available
            if self.metadata_path:
                self.progress.emit("Loading metadata...")
                self.progress_percent.emit(int((current_step / total_steps) * 100))
                logger.debug(f"Loading metadata from: {self.metadata_path}")
                self.injector.load_metadata(self.metadata_path)
            current_step += 1

            # Step 2: Validate sprite (enhanced validation)
            self.progress.emit("Validating sprite file...")
            self.progress_percent.emit(int((current_step / total_steps) * 100))

            # Basic validation
            valid, message = self.injector.validate_sprite(self.sprite_path)
            if not valid:
                self.injection_finished.emit(False, message)
                return

            # Enhanced validation
            logger.debug("Running comprehensive sprite validation")
            is_valid, errors, warnings = SpriteValidator.validate_sprite_comprehensive(
                self.sprite_path, self.metadata_path
            )
            if not is_valid:
                logger.error(f"Sprite validation failed with {len(errors)} errors")
                for error in errors:
                    logger.error(f"  - {error}")
                error_msg = "Sprite validation failed:\n" + "\n".join(errors)
                self.injection_finished.emit(False, error_msg)
                return
            if warnings:
                logger.warning(f"Sprite validation warnings ({len(warnings)}):")
                for warning in warnings:
                    logger.warning(f"  - {warning}")

            current_step += 1

            # Step 3: Test HAL compression tools
            self.progress.emit("Checking compression tools...")
            self.progress_percent.emit(int((current_step / total_steps) * 100))
            tools_ok, tools_msg = self.injector.hal_compressor.test_tools()
            if not tools_ok:
                self.injection_finished.emit(False, tools_msg)
                return
            current_step += 1

            # Step 4: Validate ROM
            self.progress.emit("Validating ROM file...")
            self.progress_percent.emit(int((current_step / total_steps) * 100))
            try:
                _header_info, header_offset = ROMValidator.validate_rom_for_injection(
                    self.rom_input, self.sprite_offset
                )
            except Exception as e:
                self.injection_finished.emit(False, f"ROM validation failed: {e}")
                return
            current_step += 1

            # Step 5: Read ROM header
            self.progress.emit("Reading ROM header...")
            self.progress_percent.emit(int((current_step / total_steps) * 100))
            header = self.injector.read_rom_header(self.rom_input)
            self.progress.emit(f"ROM: {header.title}")
            current_step += 1

            # Step 6: Inject sprite (handles compression, backup, checksum internally)
            self.progress.emit("Injecting sprite into ROM...")
            self.progress_percent.emit(int((current_step / total_steps) * 100))

            actual_offset = self.sprite_offset
            if header_offset > 0:
                actual_offset += header_offset
                logger.debug(f"Adjusted offset for header: 0x{actual_offset:X}")

            # inject_sprite_to_rom handles: compression, backup, PNG-to-4bpp, checksum
            # Note: rom_output is validated at start of run() - no fallback needed
            success, message = self.injector.inject_sprite_to_rom(
                sprite_path=self.sprite_path,
                rom_path=self.rom_input,
                output_path=self.rom_output,
                sprite_offset=actual_offset,
                fast_compression=self.fast_compression,
                create_backup=True,
            )

            if not success:
                self.injection_finished.emit(False, message)
                return

            logger.info("ROM injection completed successfully")
            self.injection_finished.emit(True, "Sprite injected successfully!")
            self.progress_percent.emit(100)

        except Exception as e:
            logger.error(f"ROM injection failed: {e}", exc_info=True)
            self.injection_finished.emit(False, f"Injection failed: {e}")
