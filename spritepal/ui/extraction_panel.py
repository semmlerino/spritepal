"""
Extraction panel with drag & drop zones for dump files
"""
from __future__ import annotations

import builtins
import contextlib
from pathlib import Path
from typing import TYPE_CHECKING, Any, override

from PySide6.QtCore import Qt, QTimer, Signal

if TYPE_CHECKING:
    from PySide6.QtGui import (
        QColor,
        QDragEnterEvent,
        QDragLeaveEvent,
        QDropEvent,
        QKeyEvent,
        QPainter,
        QPaintEvent,
        QPen,
    )

    from core.managers.application_state_manager import ApplicationStateManager
else:
    from PySide6.QtGui import (
        QColor,
        QDragEnterEvent,
        QDragLeaveEvent,
        QDropEvent,
        QKeyEvent,
        QPainter,
        QPaintEvent,
        QPen,
    )
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

from ui.common.file_dialogs import browse_for_open_file
from ui.common.spacing_constants import (
    BORDER_THICK,
    BROWSE_BUTTON_MAX_WIDTH,
    CHECKMARK_OFFSET,
    CIRCLE_INDICATOR_MARGIN,
    CIRCLE_INDICATOR_SIZE,
    COMBO_BOX_MIN_WIDTH,
    DROP_ZONE_MIN_HEIGHT,
    LINE_THICK,
    OFFSET_LABEL_MIN_WIDTH,
    OFFSET_SPINBOX_MIN_WIDTH,
    SPACING_MEDIUM,
    SPACING_SMALL,
    SPACING_TINY,
    TOGGLE_BUTTON_SIZE,
)
from ui.common.timing_constants import REFRESH_RATE_60FPS
from ui.styles import (
    get_drop_zone_badge_style,
    get_drop_zone_style,
    get_hex_label_style,
    get_link_text_style,
    get_muted_text_style,
    get_slider_style,
    get_success_text_style,
)
from ui.styles.theme import COLORS
from utils.constants import VRAM_SPRITE_OFFSET
from utils.logging_config import get_logger

logger = get_logger(__name__)

class DropZone(QWidget):
    """Drag and drop zone for file input with visual state feedback"""

    file_dropped = Signal(str)

    def __init__(
        self,
        file_type: str,
        parent: QWidget | None = None,
        *,
        settings_manager: ApplicationStateManager,
        required: bool = True,
    ) -> None:
        super().__init__(parent)
        self.file_type = file_type
        self.file_path = ""
        self._required = required
        self.setAcceptDrops(True)
        self.setMinimumHeight(DROP_ZONE_MIN_HEIGHT)

        # Apply initial styling based on required state
        self._update_style()

        # Store injected dependency
        self.settings_manager = settings_manager

        # Layout
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(SPACING_TINY)

        # Top row with badge
        top_row = QHBoxLayout()
        top_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top_row.setSpacing(SPACING_SMALL)

        # Status badge (Required/Optional/Loaded)
        self.status_badge = QLabel("Required" if required else "Optional")
        self._update_badge_style()
        top_row.addWidget(self.status_badge)

        layout.addLayout(top_row)

        # Icon and label
        self.label = QLabel(f"Drop {file_type} file here")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if self.label:
            self.label.setStyleSheet(get_muted_text_style(color_level="light"))
        layout.addWidget(self.label)

        # File path row with clear button
        path_row = QHBoxLayout()
        path_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        path_row.setSpacing(SPACING_TINY)

        self.path_label = QLabel("")
        self.path_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if self.path_label:
            self.path_label.setStyleSheet(get_link_text_style("extract"))
        self.path_label.setWordWrap(True)
        path_row.addWidget(self.path_label)

        # Clear button - small "×" to clear file selection  # noqa: RUF003
        self.clear_btn = QPushButton("×")  # noqa: RUF001
        self.clear_btn.setFixedSize(TOGGLE_BUTTON_SIZE, TOGGLE_BUTTON_SIZE)
        self.clear_btn.setToolTip("Clear selected file")
        self.clear_btn.setStyleSheet(
            f"""
            QPushButton {{
                border: none;
                border-radius: 10px;
                background-color: {COLORS["text_muted"]};
                color: white;
                font-weight: bold;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {COLORS["danger"]};
            }}
            """
        )
        _ = self.clear_btn.clicked.connect(self.clear)
        self.clear_btn.setVisible(False)
        path_row.addWidget(self.clear_btn)

        layout.addLayout(path_row)

        # Browse button
        self.browse_button = QPushButton("Browse")
        self.browse_button.setMaximumWidth(BROWSE_BUTTON_MAX_WIDTH)
        _ = self.browse_button.clicked.connect(self._browse_file)
        layout.addWidget(self.browse_button, alignment=Qt.AlignmentFlag.AlignCenter)

    def _update_style(self) -> None:
        """Update the drop zone styling based on current state"""
        if self.file_path:
            self.setStyleSheet(get_drop_zone_style("loaded"))
        else:
            self.setStyleSheet(get_drop_zone_style("empty", required=self._required))

    def _update_badge_style(self) -> None:
        """Update the badge styling based on current state"""
        if self.file_path:
            self.status_badge.setText("✓ Loaded")
            self.status_badge.setStyleSheet(get_drop_zone_badge_style("loaded"))
        elif self._required:
            self.status_badge.setText("Required")
            self.status_badge.setStyleSheet(get_drop_zone_badge_style("required"))
        else:
            self.status_badge.setText("Optional")
            self.status_badge.setStyleSheet(get_drop_zone_badge_style("optional"))

    def set_required(self, required: bool) -> None:
        """Update whether this drop zone is required"""
        self._required = required
        self._update_style()
        self._update_badge_style()

    @override
    def dragEnterEvent(self, event: QDragEnterEvent | None):
        """Handle drag enter events"""
        if event:
            mime_data = event.mimeData()
            if mime_data and mime_data.hasUrls():
                event.acceptProposedAction()
                self.setStyleSheet(get_drop_zone_style("hover"))

    @override
    def dragLeaveEvent(self, event: QDragLeaveEvent | None):
        """Handle drag leave events"""
        # Restore appropriate style based on current state
        self._update_style()

    @override
    def dropEvent(self, event: QDropEvent | None):
        """Handle drop events"""
        if event:
            mime_data = event.mimeData()
            if mime_data:
                files = [url.toLocalFile() for url in mime_data.urls()]
                if files:
                    self.set_file(files[0])
        self.dragLeaveEvent(None)  # Just reset the style

    @override
    def paintEvent(self, event: QPaintEvent | None) -> None:
        """Custom paint event to show status"""
        if event:
            super().paintEvent(event)

        if self.file_path:
            # Draw green checkmark
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            # Draw circle
            painter.setPen(QPen(QColor(16, 124, 65), BORDER_THICK))
            painter.setBrush(QColor(16, 124, 65, 30))
            painter.drawEllipse(self.width() - CIRCLE_INDICATOR_MARGIN, CHECKMARK_OFFSET, CIRCLE_INDICATOR_SIZE, CIRCLE_INDICATOR_SIZE)

            # Draw checkmark
            painter.setPen(QPen(QColor(16, 124, 65), LINE_THICK))
            painter.drawLine(self.width() - 28, 22, self.width() - 23, 27)
            painter.drawLine(self.width() - 23, 27, self.width() - 15, 19)

    def _browse_file(self):
        """Browse for file"""
        file_filter = f"{self.file_type} Files (*.dmp);;All Files (*)"
        filename = browse_for_open_file(
            self, f"Select {self.file_type} File", file_filter
        )

        if filename:
            self.set_file(filename)

    def set_file(self, file_path: str):
        """Set the file path"""
        if Path(file_path).exists():
            self.file_path = file_path
            if self.label:
                self.label.setText(f"✓ {self.file_type}")
            if self.label:
                self.label.setStyleSheet(get_success_text_style())

            # Show filename with full path in tooltip
            filename = Path(file_path).name
            if self.path_label:
                self.path_label.setText(filename)
                self.path_label.setToolTip(file_path)  # Full path on hover

            # Show clear button
            if self.clear_btn:
                self.clear_btn.setVisible(True)

            # Update visual state
            self._update_style()
            self._update_badge_style()

            self.file_dropped.emit(file_path)
            self.update()  # Trigger repaint

    def clear(self):
        """Clear the current file"""
        old_path = self.file_path
        self.file_path = ""
        if self.label:
            self.label.setText(f"Drop {self.file_type} file here")
        if self.label:
            self.label.setStyleSheet(get_muted_text_style(color_level="light"))
        if self.path_label:
            self.path_label.setText("")
            self.path_label.setToolTip("")  # Clear tooltip

        # Hide clear button
        if self.clear_btn:
            self.clear_btn.setVisible(False)

        # Update visual state
        self._update_style()
        self._update_badge_style()

        self.update()

        # Emit file_dropped signal with empty path to trigger UI updates
        if old_path:
            self.file_dropped.emit("")

    def has_file(self):
        """Check if a file is loaded"""
        return bool(self.file_path)

    def get_file_path(self):
        """Get the current file path"""
        return self.file_path

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
        # Timer for debouncing offset changes
        self._offset_timer = QTimer(self)  # Parent this timer to prevent crashes
        self._offset_timer.setInterval(REFRESH_RATE_60FPS)  # 16ms delay for ~60fps updates
        self._offset_timer.setSingleShot(True)
        self._pending_offset: int | None = None
        self._slider_changing = False  # Track if change is from slider

        # Injected dependencies
        self.settings_manager = settings_manager

        self._setup_ui()
        self._connect_signals()

        # Connect timer after UI setup
        _ = self._offset_timer.timeout.connect(self._emit_offset_changed)

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
        self.step_combo.addItems([
            "0x20 (1 tile)",
            "0x100 (8 tiles)",
            "0x1000 (128 tiles)",
            "0x4000 (512 tiles)"
        ])
        if self.step_combo:
            self.step_combo.setCurrentIndex(0)  # Default to tile-aligned
        _ = self.step_combo.currentIndexChanged.connect(self._on_step_changed)
        self.step_combo.setToolTip("Select step size for navigation")
        advanced_layout.addWidget(self.step_combo)

        advanced_layout.addSpacing(SPACING_MEDIUM)

        # Quick jump dropdown
        advanced_layout.addWidget(QLabel("Quick Jump:"))
        self.jump_combo = QComboBox(self)
        self.jump_combo.addItems([
            "Select...",
            "0x0000 - Start",
            "0x4000 - Lower sprites",
            "0x8000 - Alt sprites",
            "0xC000 - Kirby sprites",
            "0x10000 - End"
        ])
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
        self.vram_drop = DropZone(
            "VRAM", settings_manager=self.settings_manager, required=True
        )
        self.vram_drop.setToolTip("Contains sprite graphics data (required for any extraction)")
        layout.addWidget(self.vram_drop)

        # CGRAM required in Full Color mode, optional in Grayscale mode
        self.cgram_drop = DropZone(
            "CGRAM", settings_manager=self.settings_manager, required=True
        )
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

        self.oam_drop = DropZone(
            "OAM", settings_manager=self.settings_manager, required=False
        )
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
        """Try to auto-detect related dump files"""
        path = Path(file_path)
        directory = path.parent
        base_name = path.stem

        # Remove common suffixes to get base name
        for suffix in [
            "_VRAM",
            "_CGRAM",
            "_OAM",
            ".SnesVideoRam",
            ".SnesCgRam",
            ".SnesSpriteRam",
        ]:
            if base_name.endswith(suffix):
                base_name = base_name[: -len(suffix)]
                break

        # Look for related files
        patterns = [
            # Standard patterns
            (f"{base_name}_VRAM.dmp", self.vram_drop),
            (f"{base_name}_CGRAM.dmp", self.cgram_drop),
            (f"{base_name}_OAM.dmp", self.oam_drop),
            # SNES patterns
            (f"{base_name}.SnesVideoRam.dmp", self.vram_drop),
            (f"{base_name}.SnesCgRam.dmp", self.cgram_drop),
            (f"{base_name}.SnesSpriteRam.dmp", self.oam_drop),
            # Simple patterns
            (f"{base_name}.VRAM.dmp", self.vram_drop),
            (f"{base_name}.CGRAM.dmp", self.cgram_drop),
            (f"{base_name}.OAM.dmp", self.oam_drop),
        ]

        for filename, drop_zone in patterns:
            candidate_path = directory / filename
            if candidate_path.exists() and not drop_zone.has_file():
                drop_zone.set_file(str(candidate_path))

    def _find_files_for_type(
        self, directory: Path, patterns: list[str], drop_zone: DropZone
    ) -> bool:
        """Helper method to find and set files for a specific dump type"""
        if drop_zone.has_file():
            return False

        for pattern in patterns:
            files = list(directory.glob(pattern))
            if files:
                drop_zone.set_file(str(files[0]))
                return True
        return False

    def _auto_detect_files(self) -> None:
        """Auto-detect dump files in default directory (Mesen2 Debugger first, then current directory)"""
        settings = self.settings_manager

        # Define file type configurations
        file_configs = [
            (["*VRAM*.dmp", "*VideoRam*.dmp"], self.vram_drop),
            (["*CGRAM*.dmp", "*CgRam*.dmp"], self.cgram_drop),
            (["*OAM*.dmp", "*SpriteRam*.dmp"], self.oam_drop),
        ]

        found_any = False

        # Try directories in order: default (Mesen2), last used, current
        directories_to_try_raw: list[object] = [
            settings.get("paths", "default_dumps_dir", ""),
            settings.get("paths", "last_used_dir", ""),
            str(Path.cwd()),
        ]
        directories_to_try = [d for d in directories_to_try_raw if isinstance(d, str)]

        for directory_str in directories_to_try:
            if not directory_str or not Path(directory_str).exists():
                continue

            directory = Path(directory_str)

            # Try to find files in this directory
            for patterns, drop_zone in file_configs:
                if self._find_files_for_type(directory, patterns, drop_zone):
                    found_any = True

            # If we found any files in this directory, stop searching
            if found_any:
                break

        if found_any:
            self.files_changed.emit()
            self._check_extraction_ready()

    def _on_preset_changed(self, index: int) -> None:
        """Handle preset change"""
        try:
            # Show/hide custom offset controls based on preset
            if index == 1:  # Custom Range
                self.offset_widget.setVisible(True)
                current_offset = self.offset_spinbox.value()
                self._update_offset_display(current_offset)
                if self.has_vram():
                    self.offset_changed.emit(current_offset)
            else:  # Kirby Sprites
                self.offset_widget.setVisible(False)
                self.offset_slider.setValue(VRAM_SPRITE_OFFSET)
                self.offset_spinbox.setValue(VRAM_SPRITE_OFFSET)
                if self.has_vram():
                    self.offset_changed.emit(VRAM_SPRITE_OFFSET)
        except Exception:
            logger.exception("Error in preset change handler")

    def _on_offset_slider_changed(self, value: int) -> None:
        """Handle offset slider change"""
        try:
            self._slider_changing = True
            self.offset_spinbox.setValue(value)

            # Emit change immediately for smooth real-time updates when dragging
            if self.preset_combo.currentIndex() == 1 and self.has_vram():
                self.offset_changed.emit(value)

            self._slider_changing = False
        except Exception:
            logger.exception("Error in offset slider change handler")
            self._slider_changing = False

    def _on_offset_spinbox_changed(self, value: int) -> None:
        """Handle offset spinbox change"""
        try:
            # Update slider without triggering its handler
            self.offset_slider.blockSignals(True)
            self.offset_slider.setValue(value)
            self.offset_slider.blockSignals(False)

            self._update_offset_display(value)

            # Only use debounce for direct spinbox changes (not from slider)
            if self.preset_combo.currentIndex() == 1 and not self._slider_changing:
                self._pending_offset = value
                self._offset_timer.stop()
                self._offset_timer.start()
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
        """Update all offset display elements"""
        # Update hex label
        hex_text = f"0x{value:04X}"
        if self.offset_hex_label:
            self.offset_hex_label.setText(hex_text)

        # Update tooltip with tile info and position percentage
        tile_number = value // 32  # 32 bytes per tile
        max_val = self.offset_slider.maximum()
        if max_val > 0:
            percentage = (value / max_val) * 100
        else:
            percentage = 0.0

        tooltip = f"Current offset in VRAM\nTile #{tile_number} | {percentage:.1f}%"
        if self.offset_hex_label:
            self.offset_hex_label.setToolTip(tooltip)

    def _on_step_changed(self, index: int) -> None:
        """Handle step size change"""
        step_sizes = [0x20, 0x100, 0x1000, 0x4000]
        step_size = step_sizes[index]

        # Update spinbox step
        self.offset_spinbox.setSingleStep(step_size)

        # Update slider step
        self.offset_slider.setSingleStep(step_size)
        self.offset_slider.setPageStep(step_size * 4)

        logger.debug(f"Step size changed to: 0x{step_size:04X}")

    def _on_jump_selected(self, index: int) -> None:
        """Handle quick jump selection"""
        if index > 0:
            jump_text = self.jump_combo.currentText()
            # Extract hex value from text like "0xC000 - Kirby sprites"
            hex_part = jump_text.split(" - ")[0]
            try:
                offset = int(hex_part, 16)
                self.offset_spinbox.setValue(offset)
                logger.debug(f"Jumped to offset: 0x{offset:04X}")
            except ValueError:
                logger.exception("Invalid jump offset: %s", hex_part)

            # Reset combo to "Select..."
            if self.jump_combo:
                self.jump_combo.setCurrentIndex(0)

    def _emit_offset_changed(self):
        """Emit the pending offset change after debounce"""
        # Check if widget is still valid
        try:
            if not hasattr(self, "_pending_offset"):
                return
        except (RuntimeError, AttributeError):
            # Widget may have been deleted
            return

        logger.debug(f"Timer triggered - emitting pending offset: {self._pending_offset}")
        try:
            if self._pending_offset is not None:
                offset_value = self._pending_offset
                logger.debug(f"Emitting debounced offset change: {offset_value} (0x{offset_value:04X})")
                self.offset_changed.emit(offset_value)
                logger.debug("Debounced offset change signal emitted successfully")
            else:
                logger.debug("No pending offset to emit")

        except Exception:
            logger.exception("Error in debounced offset emission")
            # Don't re-raise to prevent crash, just log the error

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
