"""
Extraction panel with drag & drop zones for dump files.

Uses DropZone widget for file input with visual state feedback.
"""

from __future__ import annotations

import builtins
import contextlib
from pathlib import Path
from typing import TYPE_CHECKING, Any, override

from PySide6.QtCore import Qt, Signal

if TYPE_CHECKING:
    from PySide6.QtGui import QKeyEvent

    from core.managers.application_state_manager import ApplicationStateManager
else:
    from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.services.dump_file_detection_service import (
    DetectedFiles,
    auto_detect_all,
    detect_related_files,
)
from ui.common.spacing_constants import (
    COMBO_BOX_MIN_WIDTH,
    OFFSET_LABEL_MIN_WIDTH,
    OFFSET_SPINBOX_MIN_WIDTH,
    SPACING_MEDIUM,
    SPACING_TINY,
)
from ui.controllers.offset_controller import OffsetController
from ui.styles import (
    get_hex_label_style,
    get_link_text_style,
    get_muted_text_style,
    get_slider_style,
    get_success_text_style,
)
from ui.widgets.drop_zone import DropZone
from utils.constants import VRAM_SPRITE_OFFSET
from utils.logging_config import get_logger

logger = get_logger(__name__)


class ExtractionPanel(QGroupBox):
    """
    Panel for managing VRAM extraction inputs.
    Now accepts `ApplicationStateManager` via dependency injection.
    """

    files_changed = Signal()
    extraction_ready = Signal(bool, str)  # (ready, reason_if_not_ready)
    offset_changed = Signal(int)  # Emitted when VRAM offset changes
    mode_changed = Signal(int)  # Emitted when extraction mode changes

    def __init__(self, settings_manager: ApplicationStateManager, parent: QWidget | None = None) -> None:
        super().__init__("Input Files", parent)
        # Offset controller handles debouncing and state
        self._offset_controller = OffsetController(parent=self)

        # Injected dependencies
        self.settings_manager = settings_manager

        self._setup_ui()
        self._connect_signals()

        # Connect controller signals to panel signals
        _ = self._offset_controller.offset_changed.connect(self._on_controller_offset_changed)
        _ = self._offset_controller.offset_changing.connect(self._on_controller_offset_changing)
        _ = self._offset_controller.step_changed.connect(self._on_controller_step_changed)

        # Enable keyboard focus for shortcuts
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _setup_ui(self):
        """Set up the UI"""
        layout = QVBoxLayout()

        # Preset selector
        preset_layout = QHBoxLayout()
        preset_layout.addWidget(QLabel("Preset:", self))

        self.preset_combo = QComboBox(self)
        self.preset_combo.addItems(["Kirby Sprites (0xC000)", "Custom Range"])
        _ = self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        preset_layout.addWidget(self.preset_combo)
        preset_layout.addStretch()

        layout.addLayout(preset_layout)

        # Custom offset controls (hidden by default)
        self.offset_widget = QWidget(self)
        offset_layout = QVBoxLayout(self.offset_widget)

        # Simplified offset label - just the hex value
        offset_label_layout = QHBoxLayout()
        offset_label_layout.addWidget(QLabel("VRAM Offset:"))

        # Enhanced hex label with better styling
        self.offset_hex_label = QLabel("0xC000")
        if self.offset_hex_label:
            self.offset_hex_label.setStyleSheet(get_hex_label_style(background=True, color="extract"))
        self.offset_hex_label.setMinimumWidth(OFFSET_LABEL_MIN_WIDTH)
        # Enhanced tooltip with tile info and position
        self.offset_hex_label.setToolTip("Current offset in VRAM\nTile #1536 | 75.0%")
        offset_label_layout.addWidget(self.offset_hex_label)

        offset_label_layout.addStretch()
        offset_layout.addLayout(offset_label_layout)

        # Offset slider with fine control
        self.offset_slider = QSlider(Qt.Orientation.Horizontal)
        self.offset_slider.setObjectName("vram_offset_slider")  # Unique identifier
        self.offset_slider.setMinimum(0)
        self.offset_slider.setMaximum(0x10000)  # 64KB max
        self.offset_slider.setValue(VRAM_SPRITE_OFFSET)
        self.offset_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.offset_slider.setTickInterval(0x1000)  # Visual ticks at 4KB intervals
        self.offset_slider.setSingleStep(0x20)  # Single tile step
        self.offset_slider.setPageStep(0x100)  # Page step
        _ = self.offset_slider.valueChanged.connect(self._on_offset_slider_changed)
        if self.offset_slider:
            self.offset_slider.setStyleSheet(get_slider_style("extract"))
        self.offset_slider.setToolTip(
            "VRAM Offset: Drag to adjust position (0x0000-0x10000)\n\n"
            "Keyboard shortcuts (Custom Range mode):\n"
            "  Ctrl+←/→  Step by current step size\n"
            "  Page Up/Down  Jump by 0x1000\n"
            "  1-9  Jump to 10%-90% of range"
        )
        offset_layout.addWidget(self.offset_slider)

        # Primary offset control row (always visible)
        offset_controls_layout = QHBoxLayout()

        # Offset spinbox with hex input
        self.offset_spinbox = QSpinBox(self)
        self.offset_spinbox.setMinimum(0)
        self.offset_spinbox.setMaximum(0x10000)
        self.offset_spinbox.setValue(VRAM_SPRITE_OFFSET)
        self.offset_spinbox.setSingleStep(0x20)  # Default to tile-aligned
        self.offset_spinbox.setDisplayIntegerBase(16)
        self.offset_spinbox.setPrefix("0x")
        self.offset_spinbox.setMinimumWidth(OFFSET_SPINBOX_MIN_WIDTH)
        _ = self.offset_spinbox.valueChanged.connect(self._on_offset_spinbox_changed)
        self.offset_spinbox.setToolTip(
            "VRAM Offset (hex or decimal)\n\n"
            "Keyboard shortcuts (Custom Range mode):\n"
            "  Ctrl+←/→  Step by current step size\n"
            "  Page Up/Down  Jump by 0x1000\n"
            "  1-9  Jump to 10%-90% of range"
        )
        offset_controls_layout.addWidget(self.offset_spinbox)

        offset_controls_layout.addStretch()

        # Advanced toggle button
        self.advanced_toggle = QPushButton("Advanced...")
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setChecked(False)
        self.advanced_toggle.setMaximumWidth(100)
        _ = self.advanced_toggle.clicked.connect(self._toggle_advanced_controls)
        self.advanced_toggle.setToolTip("Show step size and quick jump options")
        offset_controls_layout.addWidget(self.advanced_toggle)

        offset_layout.addLayout(offset_controls_layout)

        # Advanced controls section (hidden by default)
        self.advanced_controls = QWidget(self)
        advanced_layout = QHBoxLayout(self.advanced_controls)
        advanced_layout.setContentsMargins(0, SPACING_TINY, 0, 0)

        # Step size selector
        advanced_layout.addWidget(QLabel("Step:"))
        self.step_combo = QComboBox(self)
        self.step_combo.addItems(["0x20 (1 tile)", "0x100 (8 tiles)", "0x1000 (128 tiles)", "0x4000 (512 tiles)"])
        if self.step_combo:
            self.step_combo.setCurrentIndex(0)  # Default to tile-aligned
        _ = self.step_combo.currentIndexChanged.connect(self._on_step_changed)
        self.step_combo.setToolTip("Select step size for navigation")
        advanced_layout.addWidget(self.step_combo)

        advanced_layout.addSpacing(SPACING_MEDIUM)

        # Quick jump dropdown
        advanced_layout.addWidget(QLabel("Quick Jump:"))
        self.jump_combo = QComboBox(self)
        self.jump_combo.addItems(
            [
                "Select...",
                "0x0000 - Start",
                "0x4000 - Lower sprites",
                "0x8000 - Alt sprites",
                "0xC000 - Kirby sprites",
                "0x10000 - End",
            ]
        )
        _ = self.jump_combo.currentIndexChanged.connect(self._on_jump_selected)
        self.jump_combo.setMinimumWidth(COMBO_BOX_MIN_WIDTH)
        advanced_layout.addWidget(self.jump_combo)

        advanced_layout.addStretch()
        self.advanced_controls.setVisible(False)
        offset_layout.addWidget(self.advanced_controls)

        # Hide by default
        self.offset_widget.setVisible(False)
        layout.addWidget(self.offset_widget)

        # Extraction mode selector
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("Extraction Mode:"))

        self.mode_combo = QComboBox(self)
        self.mode_combo.addItems(["Full Color (requires CGRAM)", "Grayscale Only"])
        _ = self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        mode_layout.addWidget(self.mode_combo)
        mode_layout.addStretch()
        layout.addLayout(mode_layout)

        # Drop zones - with clear required/optional states
        self.vram_drop = DropZone("VRAM", settings_manager=self.settings_manager, required=True)
        self.vram_drop.setToolTip("Contains sprite graphics data (required for any extraction)")
        layout.addWidget(self.vram_drop)

        # CGRAM required in Full Color mode, optional in Grayscale mode
        self.cgram_drop = DropZone("CGRAM", settings_manager=self.settings_manager, required=True)
        self.cgram_drop.setToolTip("Contains color palette data (required for full color, optional for grayscale)")
        layout.addWidget(self.cgram_drop)

        # Optional OAM section (collapsed by default)
        self.oam_toggle = QPushButton("+ Show OAM input (optional)")
        self.oam_toggle.setCheckable(True)
        self.oam_toggle.setChecked(False)
        self.oam_toggle.setFlat(True)
        if self.oam_toggle:
            self.oam_toggle.setStyleSheet(get_link_text_style("extract"))
        _ = self.oam_toggle.clicked.connect(self._toggle_oam_input)
        self.oam_toggle.setToolTip("OAM improves palette selection but is not required")
        layout.addWidget(self.oam_toggle)

        self.oam_drop = DropZone("OAM", settings_manager=self.settings_manager, required=False)
        self.oam_drop.setToolTip("Shows active sprites and palettes (optional - improves palette selection)")
        self.oam_drop.setVisible(False)
        layout.addWidget(self.oam_drop)

        # Auto-detect button
        self.auto_detect_button = QPushButton("Auto-detect Files")
        _ = self.auto_detect_button.clicked.connect(self._auto_detect_files)
        layout.addWidget(self.auto_detect_button)

        self.setLayout(layout)

    def _connect_signals(self):
        """Connect internal signals"""
        _ = self.vram_drop.file_dropped.connect(self._on_file_changed)
        _ = self.cgram_drop.file_dropped.connect(self._on_file_changed)
        _ = self.oam_drop.file_dropped.connect(self._on_file_changed)

    def _on_file_changed(self, file_path: str) -> None:
        """Handle when a file is dropped"""
        self.files_changed.emit()
        self._check_extraction_ready()

        # Try to auto-detect related files
        self._auto_detect_related(file_path)

        # Update mode visuals if CGRAM was added/removed
        if file_path == self.cgram_drop.get_file_path():
            self._on_mode_changed(self.mode_combo.currentIndex())

        # Trigger preview update if VRAM was just loaded
        if self.has_vram() and file_path == self.vram_drop.get_file_path():
            self.offset_changed.emit(self.get_vram_offset())

    def _check_extraction_ready(self):
        """Check if we're ready to extract with validation feedback"""
        reasons: list[str] = []

        # Always need VRAM
        if not self.vram_drop.has_file():
            reasons.append("Load a VRAM file")
            self.extraction_ready.emit(False, " | ".join(reasons))
            return

        # Check mode - grayscale doesn't need CGRAM
        if self.mode_combo.currentIndex() == 1:  # Grayscale Only
            self.extraction_ready.emit(True, "")
        else:  # Full Color mode
            if not self.cgram_drop.has_file():
                reasons.append("Load a CGRAM file (or use Grayscale mode)")
            ready = self.cgram_drop.has_file()
            self.extraction_ready.emit(ready, " | ".join(reasons))

    def _auto_detect_related(self, file_path: str) -> None:
        """Try to auto-detect related dump files using detection service."""
        path = Path(file_path)
        existing = self._get_existing_files()
        detected = detect_related_files(path, existing)
        self._apply_detected_files(detected)

    def _get_existing_files(self) -> DetectedFiles:
        """Get currently loaded files as DetectedFiles for skip detection."""
        return DetectedFiles(
            vram_path=Path(self.vram_drop.file_path) if self.vram_drop.has_file() else None,
            cgram_path=Path(self.cgram_drop.file_path) if self.cgram_drop.has_file() else None,
            oam_path=Path(self.oam_drop.file_path) if self.oam_drop.has_file() else None,
        )

    def _apply_detected_files(self, detected: DetectedFiles) -> None:
        """Apply detected files to drop zones."""
        if detected.vram_path and not self.vram_drop.has_file():
            self.vram_drop.set_file(str(detected.vram_path))
        if detected.cgram_path and not self.cgram_drop.has_file():
            self.cgram_drop.set_file(str(detected.cgram_path))
        if detected.oam_path and not self.oam_drop.has_file():
            self.oam_drop.set_file(str(detected.oam_path))

    def _auto_detect_files(self) -> None:
        """Auto-detect dump files in default directory using detection service."""
        settings = self.settings_manager

        # Build search directories in priority order: default (Mesen2), last used, current
        directories_to_try_raw: list[object] = [
            settings.get("paths", "default_dumps_dir", ""),
            settings.get("paths", "last_used_dir", ""),
            str(Path.cwd()),
        ]
        search_dirs = [Path(d) for d in directories_to_try_raw if isinstance(d, str) and d and Path(d).exists()]

        existing = self._get_existing_files()
        detected = auto_detect_all(
            trigger_file=None,
            search_directories=search_dirs,
            existing=existing,
        )

        if detected.has_any():
            self._apply_detected_files(detected)
            self.files_changed.emit()
            self._check_extraction_ready()

    def _on_preset_changed(self, index: int) -> None:
        """Handle preset change - delegate to controller"""
        try:
            is_custom = index == 1
            self.offset_widget.setVisible(is_custom)

            if is_custom:
                current_offset = self.offset_spinbox.value()
                self._update_offset_display(current_offset)
            else:
                # Reset to Kirby sprite offset
                self.offset_slider.setValue(VRAM_SPRITE_OFFSET)
                self.offset_spinbox.setValue(VRAM_SPRITE_OFFSET)

            # Delegate mode switching to controller (will emit offset_changed if needed)
            self._offset_controller.set_preset_mode(is_custom=is_custom)
        except Exception:
            logger.exception("Error in preset change handler")

    def _on_offset_slider_changed(self, value: int) -> None:
        """Handle offset slider change - delegate to controller"""
        try:
            # Sync spinbox
            self.offset_spinbox.blockSignals(True)
            self.offset_spinbox.setValue(value)
            self.offset_spinbox.blockSignals(False)

            self._update_offset_display(value)

            # Delegate to controller (emits offset_changing for real-time updates)
            self._offset_controller.on_slider_change(value)
        except Exception:
            logger.exception("Error in offset slider change handler")
            with contextlib.suppress(builtins.BaseException):
                self.offset_spinbox.blockSignals(False)

    def _on_offset_spinbox_changed(self, value: int) -> None:
        """Handle offset spinbox change - delegate to controller"""
        try:
            # Sync slider
            self.offset_slider.blockSignals(True)
            self.offset_slider.setValue(value)
            self.offset_slider.blockSignals(False)

            self._update_offset_display(value)

            # Delegate to controller (handles debouncing)
            self._offset_controller.on_spinbox_change(value)
        except Exception:
            logger.exception("Error in offset spinbox change handler")
            with contextlib.suppress(builtins.BaseException):
                self.offset_slider.blockSignals(False)

    def _toggle_advanced_controls(self, checked: bool) -> None:
        """Toggle visibility of advanced offset controls"""
        self.advanced_controls.setVisible(checked)
        if checked:
            self.advanced_toggle.setText("Hide Advanced")
        else:
            self.advanced_toggle.setText("Advanced...")

    def _toggle_oam_input(self, checked: bool) -> None:
        """Toggle visibility of OAM drop zone"""
        self.oam_drop.setVisible(checked)
        if checked:
            self.oam_toggle.setText("- Hide OAM input")
        else:
            self.oam_toggle.setText("+ Show OAM input (optional)")

    def _update_offset_display(self, value: int) -> None:
        """Update all offset display elements using controller's display info"""
        # Update controller's max offset for percentage calculation
        self._offset_controller.set_max_offset(self.offset_slider.maximum())

        # Get formatted display info from controller
        info = self._offset_controller.get_display_info(value)

        if self.offset_hex_label:
            self.offset_hex_label.setText(info.hex_text)
            self.offset_hex_label.setToolTip(info.tooltip)

    def _on_step_changed(self, index: int) -> None:
        """Handle step size change - delegate to controller"""
        # Delegate to controller (will emit step_changed signal)
        self._offset_controller.set_step_index(index)

    def _on_jump_selected(self, index: int) -> None:
        """Handle quick jump selection - delegate to controller"""
        if index > 0:
            jump_text = self.jump_combo.currentText()
            offset = self._offset_controller.parse_jump_text(jump_text)

            if offset is not None:
                self.offset_spinbox.setValue(offset)
                logger.debug(f"Jumped to offset: 0x{offset:04X}")

            # Reset combo to "Select..."
            if self.jump_combo:
                self.jump_combo.setCurrentIndex(0)

    def _on_controller_offset_changed(self, offset: int) -> None:
        """Handle debounced offset change from controller"""
        if self.has_vram():
            logger.debug(f"Controller offset changed: {offset} (0x{offset:04X})")
            self.offset_changed.emit(offset)

    def _on_controller_offset_changing(self, offset: int) -> None:
        """Handle real-time offset change from controller (slider drag)"""
        if self.has_vram():
            self.offset_changed.emit(offset)

    def _on_controller_step_changed(self, step: int, page_step: int) -> None:
        """Handle step size change from controller"""
        self.offset_spinbox.setSingleStep(step)
        self.offset_slider.setSingleStep(step)
        self.offset_slider.setPageStep(page_step)

    def clear_files(self):
        """Clear all loaded files"""
        if self.vram_drop:
            self.vram_drop.clear()
        if self.cgram_drop:
            self.cgram_drop.clear()
        if self.oam_drop:
            self.oam_drop.clear()
        self._check_extraction_ready()

    def has_vram(self):
        """Check if VRAM is loaded"""
        return self.vram_drop.has_file()

    def has_cgram(self):
        """Check if CGRAM is loaded"""
        return self.cgram_drop.has_file()

    def has_oam(self):
        """Check if OAM is loaded"""
        return self.oam_drop.has_file()

    def get_vram_path(self):
        """Get VRAM file path"""
        return self.vram_drop.get_file_path()

    def get_cgram_path(self):
        """Get CGRAM file path"""
        return self.cgram_drop.get_file_path()

    def get_oam_path(self):
        """Get OAM file path"""
        return self.oam_drop.get_file_path()

    def get_vram_offset(self):
        """Get the current VRAM offset value"""
        # Use the preset to determine offset
        if self.preset_combo.currentIndex() == 0:  # Kirby Sprites
            return VRAM_SPRITE_OFFSET
        # Custom Range
        return self.offset_spinbox.value()

    def restore_session_files(self, file_paths: dict[str, Any]) -> None:  # pyright: ignore[reportExplicitAny] - File path configuration
        """Restore file paths from session data"""
        # Restore extraction mode first
        if "extraction_mode" in file_paths:
            mode_index = file_paths.get("extraction_mode", 0)
            if 0 <= mode_index < self.mode_combo.count():
                if self.mode_combo:
                    self.mode_combo.setCurrentIndex(mode_index)

        if file_paths.get("vram_path") and Path(file_paths["vram_path"]).exists():
            self.vram_drop.set_file(file_paths["vram_path"])

        if file_paths.get("cgram_path") and Path(file_paths["cgram_path"]).exists():
            self.cgram_drop.set_file(file_paths["cgram_path"])

        if file_paths.get("oam_path") and Path(file_paths["oam_path"]).exists():
            self.oam_drop.set_file(file_paths["oam_path"])

        self.files_changed.emit()
        self._check_extraction_ready()

    def get_session_data(self):
        """Get current session data for saving"""
        return {
            "vram_path": self.get_vram_path(),
            "cgram_path": self.get_cgram_path(),
            "oam_path": self.get_oam_path(),
            "extraction_mode": self.mode_combo.currentIndex(),
        }

    def _on_mode_changed(self, index: int) -> None:
        """Handle extraction mode change"""
        logger.debug(f"Extraction mode changed to: {self.mode_combo.currentText()}")

        # Update CGRAM required state based on mode
        is_grayscale = index == 1
        self.cgram_drop.set_required(not is_grayscale)

        # Update CGRAM drop zone label based on mode and file state
        if is_grayscale:
            if not self.cgram_drop.has_file():
                self.cgram_drop.label.setText("CGRAM (optional for grayscale)")
                self.cgram_drop.label.setStyleSheet(get_muted_text_style(color_level="dark"))
        elif self.cgram_drop.has_file():
            self.cgram_drop.label.setText("✓ CGRAM")
            self.cgram_drop.label.setStyleSheet(get_success_text_style())
        else:
            self.cgram_drop.label.setText("Drop CGRAM file here")
            self.cgram_drop.label.setStyleSheet(get_muted_text_style(color_level="light"))

        # Re-check extraction readiness
        self._check_extraction_ready()

        # Emit mode changed signal
        self.mode_changed.emit(index)

    def is_grayscale_mode(self):
        """Check if grayscale extraction mode is selected"""
        return self.mode_combo.currentIndex() == 1

    @override
    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle keyboard shortcuts for offset navigation"""
        # Only handle shortcuts in custom range mode
        if self.preset_combo.currentIndex() != 1:
            super().keyPressEvent(event)
            return

        current = self.offset_spinbox.value()
        step = self.offset_spinbox.singleStep()

        # Ctrl + Arrow keys for fine stepping
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            if event.key() == Qt.Key.Key_Left:
                self.offset_spinbox.setValue(max(0, current - step))
                event.accept()
                return
            if event.key() == Qt.Key.Key_Right:
                self.offset_spinbox.setValue(min(self.offset_spinbox.maximum(), current + step))
                event.accept()
                return

        # Page Up/Down for larger jumps
        if event.key() == Qt.Key.Key_PageUp:
            self.offset_spinbox.setValue(max(0, current - 0x1000))
            event.accept()
            return
        if event.key() == Qt.Key.Key_PageDown:
            self.offset_spinbox.setValue(min(self.offset_spinbox.maximum(), current + 0x1000))
            event.accept()
            return

        # Number keys for percentage jumps (1-9 = 10%-90%)
        if event.key() >= Qt.Key.Key_1 and event.key() <= Qt.Key.Key_9:
            percentage = (event.key() - Qt.Key.Key_1 + 1) * 10
            offset = int(self.offset_spinbox.maximum() * percentage / 100)
            self.offset_spinbox.setValue(offset)
            event.accept()
            return

        super().keyPressEvent(event)
