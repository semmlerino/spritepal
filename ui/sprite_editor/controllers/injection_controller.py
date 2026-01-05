#!/usr/bin/env python3
"""
Injection controller for sprite injection into VRAM dumps.
"""

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QFileDialog

from ui.common.signal_utils import safe_disconnect

from ..services import ImageConverter
from ..workers import InjectWorker

if TYPE_CHECKING:
    from ..views.tabs import InjectTab


class InjectionController(QObject):
    """Controller for sprite injection operations."""

    # Signals
    injection_completed = Signal(str)  # output file path
    injection_failed = Signal(str)  # error message
    progress_updated = Signal(int, str)  # percent, message
    validation_completed = Signal(bool, str)  # is_valid, message

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._view: InjectTab | None = None
        self._worker: InjectWorker | None = None
        self.converter = ImageConverter()

        # File paths
        self.png_file: str = ""
        self.vram_file: str = ""

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

    def _connect_view_signals(self) -> None:
        """Connect view signals to controller methods."""
        if not self._view:
            return

        self._view.inject_requested.connect(self.inject_sprites)
        self._view.browse_png_requested.connect(self.browse_png_file)
        self._view.browse_vram_requested.connect(self.browse_vram_file)

    def browse_png_file(self) -> None:
        """Open file dialog to select PNG file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self._view,
            "Open PNG File",
            "",
            "PNG Files (*.png);;All Files (*)",
        )
        if file_path:
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
        self.png_file = png_path
        if self._view:
            self._view.set_png_file(png_path)
        self._validate_png(png_path)

    def _validate_png(self, file_path: str) -> None:
        """Validate PNG file for SNES compatibility."""
        is_valid, issues = self.converter.validate_png(file_path)

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

        # Validate parameters first
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

        from typing import cast

        # Determine output path
        output_file = cast(str, params["output_file"])
        if not Path(output_file).is_absolute():
            # Make relative to VRAM file directory
            vram_dir = Path(cast(str, params["vram_file"])).parent
            output_file = str(vram_dir / output_file)

        # Clean up any existing worker before creating new one
        self._cleanup_worker()

        # Create and start worker
        self._worker = InjectWorker(
            png_file=cast(str, params["png_file"]),
            vram_file=cast(str, params["vram_file"]),
            offset=cast(int, params["offset"]),
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
