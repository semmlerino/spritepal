#!/usr/bin/env python3
"""
Injection controller for sprite injection into VRAM dumps.
"""

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QFileDialog

from core.rom_injector import ROMInjector
from ui.common.signal_utils import safe_disconnect

from ..services import ImageConverter
from ..workers import InjectWorker

if TYPE_CHECKING:
    from ..views.tabs import InjectTab


class InjectionController(QObject):
    """Controller for sprite injection operations.

    Signal Flow:
        InjectWorker signals → this controller → view updates

    Consumers:
        - InjectTab: Receives progress_updated, injection_failed, validation_completed
        - SpriteEditorWorkspace: Connects injection_completed for temp file cleanup
    """

    # Signals (originate here, consumed by views)
    injection_completed = Signal(str)  # output path → InjectTab, SpriteEditorWorkspace cleanup
    injection_failed = Signal(str)  # error message → InjectTab.append_output
    progress_updated = Signal(int, str)  # percent, message → InjectTab.append_output
    validation_completed = Signal(bool, str)  # is_valid, message → InjectTab.set_validation_text

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._view: InjectTab | None = None
        self._worker: InjectWorker | None = None
        self.converter = ImageConverter()
        self.rom_injector = ROMInjector()
        self._mode = "vram"

        # File paths
        self.png_file: str = ""
        self.vram_file: str = ""
        self.rom_file: str = ""

        # Validation state
        self._png_validation_passed: bool = False

    def _cleanup_worker(self) -> None:
        """Clean up existing worker before creating new one."""
        if self._worker is not None:
            safe_disconnect(self._worker.progress)
            safe_disconnect(self._worker.error)
            safe_disconnect(self._worker.result)
            safe_disconnect(self._worker.finished_signal)
            self._worker = None

    def cleanup(self) -> None:
        """Clean up resources before destruction."""
        self._cleanup_worker()
        if self._view is not None:
            safe_disconnect(self._view.inject_requested)
            safe_disconnect(self._view.browse_png_requested)
            safe_disconnect(self._view.browse_vram_requested)

    def set_view(self, view: "InjectTab") -> None:
        """Set the inject tab view."""
        self._view = view
        self._connect_view_signals()
        # Connect validation signal to view
        view.set_controller(self)

    def _connect_view_signals(self) -> None:
        """Connect view signals to controller methods."""
        if not self._view:
            return

        self._view.inject_requested.connect(self.inject_sprites)
        self._view.save_rom_requested.connect(self.inject_sprite_to_rom)
        self._view.browse_png_requested.connect(self.browse_png_file)
        self._view.browse_vram_requested.connect(self.browse_vram_file)
        self._view.browse_rom_requested.connect(self.browse_rom_file)

    def set_mode(self, mode: str) -> None:
        """Set the injection mode ('vram' or 'rom')."""
        self._mode = mode
        if self._view:
            self._view.set_mode(mode)

    def set_rom_file(self, file_path: str) -> None:
        """Set the ROM file path."""
        self.rom_file = file_path
        if self._view:
            self._view.set_rom_file(file_path)

    def browse_rom_file(self) -> None:
        """Open file dialog to select ROM file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self._view,
            "Open ROM File",
            "",
            "SNES ROMs (*.sfc *.smc);;All Files (*)",
        )
        if file_path:
            self.rom_file = file_path
            if self._view:
                self._view.set_rom_file(file_path)

    def inject_sprite_to_rom(self) -> None:
        """Inject sprite directly to ROM."""
        if not self._view:
            return

        params = self._view.get_injection_params()
        rom_file = str(params.get("rom_file", ""))
        png_file = str(params.get("png_file", ""))
        offset = int(params["offset"])

        if not rom_file or not png_file:
            self._view.append_output("ERROR: ROM and PNG files required")
            return

        # Output to same file (or backup handled by injector)
        # Using same file for 'Save to ROM' logic

        self._view.append_output(f"Saving to ROM: {rom_file} at 0x{offset:X}")

        try:
            success, message = self.rom_injector.inject_sprite_to_rom(
                sprite_path=png_file,
                rom_path=rom_file,
                output_path=rom_file,  # Overwrite
                sprite_offset=offset,
                create_backup=True,
            )

            if not success and "ROM checksum mismatch" in message:
                from PySide6.QtWidgets import QMessageBox

                reply = QMessageBox.question(
                    self._view,
                    "ROM Checksum Mismatch",
                    f"Validation failed: {message}\n\n"
                    "This usually happens with modified/patched ROMs.\n"
                    "Do you want to ignore this warning and proceed anyway?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )

                if reply == QMessageBox.StandardButton.Yes:
                    self._view.append_output("Retrying with lenient checksum validation...")
                    success, message = self.rom_injector.inject_sprite_to_rom(
                        sprite_path=png_file,
                        rom_path=rom_file,
                        output_path=rom_file,
                        sprite_offset=offset,
                        create_backup=True,
                        ignore_checksum=True,
                    )

            if success:
                self._view.append_output("Success!")
                self._view.append_output(message)
                self.injection_completed.emit(rom_file)
            else:
                self._view.append_output(f"Failed: {message}")
                self.injection_failed.emit(message)

        except Exception as e:
            self._view.append_output(f"ERROR: {e}")
            self.injection_failed.emit(str(e))

    def browse_png_file(self) -> None:
        """Open file dialog to select PNG file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self._view,
            "Open PNG File",
            "",
            "PNG Files (*.png);;All Files (*)",
        )
        if file_path:
            # Reset validation state before setting new file
            self._png_validation_passed = False
            self.png_file = file_path
            if self._view:
                self._view.set_png_file(file_path)
            self._validate_png(file_path)

    def browse_vram_file(self) -> None:
        """Open file dialog to select VRAM dump."""
        file_path, _ = QFileDialog.getOpenFileName(
            self._view,
            "Open VRAM Dump",
            "",
            "VRAM Dumps (*.dmp *.bin);;All Files (*)",
        )
        if file_path:
            self.vram_file = file_path
            if self._view:
                self._view.set_vram_file(file_path)

    def set_source_image(self, png_path: str) -> None:
        """Set the source PNG file (called from edit workflow)."""
        # Reset validation state before setting new file
        self._png_validation_passed = False
        self.png_file = png_path
        if self._view:
            self._view.set_png_file(png_path)
        self._validate_png(png_path)

    def _validate_png(self, file_path: str) -> None:
        """Validate PNG file for SNES compatibility."""
        is_valid, issues = self.converter.validate_png(file_path)

        # Store validation result
        self._png_validation_passed = is_valid

        message_lines = []
        if is_valid:
            message_lines.append("✓ PNG is valid for SNES injection")
        else:
            message_lines.append("✗ PNG validation failed:")
            message_lines.extend(f"  • {issue}" for issue in issues)

        message = "\n".join(message_lines)

        if self._view:
            self._view.set_validation_text(message, is_valid)

        self.validation_completed.emit(is_valid, message)

    def inject_sprites(self) -> None:
        """Start sprite injection."""
        if not self._view:
            return

        # Check PNG validation status first
        if not self._png_validation_passed:
            error_msg = "Cannot inject: PNG validation has not passed"
            self._view.append_output(f"ERROR: {error_msg}")
            self.injection_failed.emit(error_msg)
            return

        # Validate parameters
        is_valid, error_msg = self._view.validate_params()
        if not is_valid:
            self._view.append_output(f"Validation failed:\n{error_msg}")
            return

        params = self._view.get_injection_params()

        # Clear output
        self._view.clear_output()
        self._view.set_inject_enabled(False)
        self._view.append_output(f"Injecting: {params['png_file']}")
        self._view.append_output(f"Into: {params['vram_file']}")

        # Determine output path
        output_file = params["output_file"]
        if not Path(output_file).is_absolute():
            # Make relative to VRAM file directory
            vram_dir = Path(params["vram_file"]).parent
            output_file = str(vram_dir / output_file)

        # Clean up any existing worker before creating new one
        self._cleanup_worker()

        # Create and start worker
        self._worker = InjectWorker(
            png_file=params["png_file"],
            vram_file=params["vram_file"],
            offset=params["offset"],
            output_file=output_file,
        )

        self._worker.progress.connect(self._on_progress)
        self._worker.error.connect(self._on_error)
        self._worker.result.connect(self._on_injection_complete)
        self._worker.finished_signal.connect(self._on_worker_finished)

        self._worker.start()

    def _on_progress(self, percent: int, message: str) -> None:
        """Handle progress updates."""
        self.progress_updated.emit(percent, message)
        if self._view:
            self._view.append_output(f"[{percent}%] {message}")

    def _on_error(self, error: str) -> None:
        """Handle injection error."""
        self.injection_failed.emit(error)
        if self._view:
            self._view.append_output(f"ERROR: {error}")
            self._view.set_inject_enabled(True)

    def _on_injection_complete(self, output_path: str) -> None:
        """Handle successful injection."""
        if self._view:
            self._view.append_output(f"Injection complete: {output_path}")
        self.injection_completed.emit(output_path)

    def _on_worker_finished(self) -> None:
        """Handle worker completion."""
        if self._view:
            self._view.set_inject_enabled(True)
        self._worker = None
