"""
Browse tab widget for manual offset dialog.

Provides ROM navigation controls including slider, manual offset entry,
navigation buttons, and sprite search capabilities.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QKeySequence
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ui.common.spacing_constants import (
    SPACING_MEDIUM,
    SPACING_SMALL,
    SPACING_STANDARD,
)
from ui.styles import get_prominent_action_button_style
from ui.styles.theme import COLORS

# Import AdvancedSearchDialog lazily to avoid circular imports
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from ui.common.simple_preview_coordinator import SimplePreviewCoordinator
    from ui.dialogs.advanced_search_dialog import AdvancedSearchDialog

logger = get_logger(__name__)

class SimpleBrowseTab(QWidget):
    """
    Browse tab with essential navigation controls for ROM exploration.

    Signals:
        offset_changed: Emitted when the current offset changes
        find_next_clicked: Request to find next sprite
        find_prev_clicked: Request to find previous sprite
        advanced_search_requested: Request to open advanced search
        find_sprites_requested: Request to scan ROM for sprites
    """

    offset_changed = Signal(int)
    find_next_clicked = Signal()
    find_prev_clicked = Signal()
    advanced_search_requested = Signal()
    find_sprites_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """
        Initialize the browse tab.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)

        # State
        self._current_offset: int = 0x200000
        self._rom_size: int = 0x400000
        self._step_size: int = 0x1000
        self._rom_path: str = ""
        self._advanced_search_dialog: AdvancedSearchDialog | None = None
        self._smart_preview_coordinator: SimplePreviewCoordinator | None = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the browse tab UI with improved layout and spacing."""
        layout = QVBoxLayout(self)
        layout.setSpacing(SPACING_SMALL)  # Better spacing between sections
        layout.setContentsMargins(SPACING_STANDARD, SPACING_STANDARD, SPACING_STANDARD, SPACING_STANDARD)  # More comfortable margins

        # Main control section with improved styling
        controls_frame = QFrame()
        controls_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        controls_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS["input_background"]};
                border: 1px solid {COLORS["panel_background"]};
                border-radius: 6px;
            }}
        """)
        controls_layout = QVBoxLayout(controls_frame)
        controls_layout.setSpacing(SPACING_STANDARD)  # Better spacing between controls
        controls_layout.setContentsMargins(SPACING_MEDIUM, SPACING_MEDIUM, SPACING_MEDIUM, SPACING_MEDIUM)  # Comfortable padding

        # Section title with better styling
        title = self._create_section_title("ROM Offset Control")
        title.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {COLORS['highlight']};")
        controls_layout.addWidget(title)

        # Slider with smart preview support and type-safe range checking
        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.setObjectName("manual_offset_rom_slider")  # Unique identifier
        # Ensure values fit in 32-bit signed int range (QSlider limitation)
        max_slider_value = min(self._rom_size, 0x7FFFFFFF)  # 2^31 - 1
        self.position_slider.setMinimum(0)
        self.position_slider.setMaximum(max_slider_value)
        safe_current_offset = min(self._current_offset, max_slider_value)
        self.position_slider.setValue(safe_current_offset)
        self.position_slider.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        # Connect to valueChanged for compatibility (used by smart coordinator)
        self.position_slider.valueChanged.connect(self._on_slider_changed)

        # Debug: Add direct connections to track what signals are firing
        self.position_slider.sliderPressed.connect(lambda: logger.debug("[TRACE_SIGNAL] Slider pressed"))
        self.position_slider.sliderMoved.connect(lambda v: logger.debug(f"[TRACE_SIGNAL] Slider moved to 0x{v:06X}"))
        self.position_slider.sliderReleased.connect(lambda: logger.debug("[TRACE_SIGNAL] Slider released"))

        # Apply distinct styling for ROM offset slider
        if self.position_slider:
            self.position_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                border: 2px solid {COLORS["highlight"]};
                height: 8px;
                background: {COLORS["input_background"]};
                border-radius: 4px;
            }}
            QSlider::handle:horizontal {{
                background: {COLORS["highlight"]};
                border: 2px solid {COLORS["highlight_hover"]};
                width: 18px;
                margin: -5px 0;
                border-radius: 9px;
            }}
            QSlider::handle:horizontal:hover {{
                background: {COLORS["highlight_hover"]};
                border: 2px solid {COLORS["highlight_hover"]};
            }}
            QSlider::sub-page:horizontal {{
                background: {COLORS["browse_pressed"]};
                border-radius: 4px;
            }}
        """)
        controls_layout.addWidget(self.position_slider)

        # Position info row with improved layout
        info_row = QHBoxLayout()
        info_row.setSpacing(SPACING_MEDIUM)  # Better spacing between labels

        self.position_label = QLabel(self._format_position(self._current_offset))
        position_font = QFont()
        position_font.setBold(True)
        position_font.setPointSize(11)  # More readable size
        self.position_label.setFont(position_font)
        info_row.addWidget(self.position_label)

        info_row.addStretch()  # Push offset label to the right

        self.offset_label = QLabel(f"0x{self._current_offset:06X}")
        if self.offset_label:
            self.offset_label.setStyleSheet(f"font-family: monospace; color: {COLORS['text_muted']}; font-size: 12px;")
        info_row.addWidget(self.offset_label)

        controls_layout.addLayout(info_row)

        # Add separator line for visual clarity
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet(f"background-color: {COLORS['panel_background']}; max-height: 1px;")
        controls_layout.addWidget(separator)

        # Navigation controls section with better grouping
        nav_row = QHBoxLayout()
        nav_row.setSpacing(SPACING_SMALL)  # Better button spacing

        # Navigation buttons with improved styling
        button_style = f"""
            QPushButton {{
                padding: 6px 12px;
                background-color: {COLORS["panel_background"]};
                border: 1px solid {COLORS["border"]};
                border-radius: 4px;
                color: {COLORS["text_secondary"]};
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {COLORS["focus_background_subtle"]};
                border-color: {COLORS["highlight"]};
            }}
            QPushButton:pressed {{
                background-color: {COLORS["input_background"]};
            }}
        """

        self.prev_button = QPushButton("◀ Previous")
        if self.prev_button:
            self.prev_button.setStyleSheet(button_style)
        self.prev_button.setToolTip("Find previous sprite (skip empty areas)")
        self.prev_button.clicked.connect(self.find_prev_clicked.emit)
        nav_row.addWidget(self.prev_button)

        self.next_button = QPushButton("Next ▶")
        if self.next_button:
            self.next_button.setStyleSheet(button_style)
        self.next_button.setToolTip("Find next sprite (skip empty areas)")
        self.next_button.clicked.connect(self.find_next_clicked.emit)
        nav_row.addWidget(self.next_button)

        # Clipboard paste button
        self.paste_button = QPushButton("📋 Paste")
        if self.paste_button:
            self.paste_button.setStyleSheet(button_style)
        self.paste_button.setToolTip("Paste offset from Mesen2 (Key 0 in Lua script)")
        self.paste_button.clicked.connect(self._paste_from_clipboard)
        nav_row.addWidget(self.paste_button)

        nav_row.addStretch()  # Add space between navigation and action buttons

        # Find Sprites button - prominent styling for discoverability
        self.find_sprites_button = QPushButton("🔍 Find Sprites (Ctrl+F)")
        self.find_sprites_button.setStyleSheet(get_prominent_action_button_style())
        self.find_sprites_button.setShortcut(QKeySequence("Ctrl+F"))
        self.find_sprites_button.setToolTip("Scan ROM for HAL-compressed sprites\n\nKeyboard shortcut: Ctrl+F")
        self.find_sprites_button.clicked.connect(self._on_find_sprites)
        nav_row.addWidget(self.find_sprites_button)

        # Advanced Search button
        self.advanced_search_button = QPushButton("⚙️ Advanced")
        if self.advanced_search_button:
            self.advanced_search_button.setStyleSheet(button_style)
        self.advanced_search_button.setToolTip("Open advanced search dialog with filtering and batch operations")
        self.advanced_search_button.clicked.connect(self._open_advanced_search)
        nav_row.addWidget(self.advanced_search_button)

        controls_layout.addLayout(nav_row)

        # Add another separator for the manual controls section
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.Shape.HLine)
        separator2.setStyleSheet(f"background-color: {COLORS['panel_background']}; max-height: 1px;")
        controls_layout.addWidget(separator2)

        # Manual input section with better organization
        manual_section = QVBoxLayout()
        manual_section.setSpacing(SPACING_SMALL)

        # Manual navigation row
        manual_row = QHBoxLayout()
        manual_row.setSpacing(SPACING_STANDARD)

        # Go to offset group
        goto_group = QHBoxLayout()
        goto_group.setSpacing(SPACING_SMALL)

        goto_label = QLabel("Jump to Offset:")
        goto_label.setStyleSheet(f"font-weight: bold; color: {COLORS['text_secondary']};")
        goto_group.addWidget(goto_label)

        self.manual_spinbox = QSpinBox()
        self.manual_spinbox.setMinimum(0)
        self.manual_spinbox.setMaximum(self._rom_size)
        self.manual_spinbox.setValue(self._current_offset)
        self.manual_spinbox.setDisplayIntegerBase(16)
        self.manual_spinbox.setPrefix("0x")
        self.manual_spinbox.setMinimumWidth(120)
        if self.manual_spinbox:
            self.manual_spinbox.setStyleSheet(f"""
            QSpinBox {{
                padding: 4px;
                background-color: {COLORS["panel_background"]};
                border: 1px solid {COLORS["border"]};
                border-radius: 4px;
                font-family: monospace;
            }}
        """)
        self.manual_spinbox.valueChanged.connect(self._on_manual_changed)
        goto_group.addWidget(self.manual_spinbox)

        go_button = QPushButton("Go")
        go_button.setStyleSheet(button_style)
        go_button.clicked.connect(self._on_go_button_clicked)
        goto_group.addWidget(go_button)

        manual_row.addLayout(goto_group)
        manual_row.addStretch()

        # Step size control - moved to separate group
        step_group = QHBoxLayout()
        step_group.setSpacing(SPACING_SMALL)

        step_label = QLabel("Step Size:")
        step_label.setStyleSheet(f"font-weight: bold; color: {COLORS['text_muted']};")
        step_group.addWidget(step_label)

        self.step_spinbox = QSpinBox()
        self.step_spinbox.setMinimum(0x100)
        self.step_spinbox.setMaximum(0x100000)
        self.step_spinbox.setValue(self._step_size)
        self.step_spinbox.setDisplayIntegerBase(16)
        self.step_spinbox.setPrefix("0x")
        self.step_spinbox.setMinimumWidth(100)
        if self.step_spinbox:
            self.step_spinbox.setStyleSheet(f"""
            QSpinBox {{
                padding: 4px;
                background-color: {COLORS["panel_background"]};
                border: 1px solid {COLORS["border"]};
                border-radius: 4px;
                font-family: monospace;
            }}
        """)
        step_group.addWidget(self.step_spinbox)

        manual_row.addLayout(step_group)

        manual_section.addLayout(manual_row)
        controls_layout.addLayout(manual_section)

        layout.addWidget(controls_frame)
        layout.addStretch()  # Push content to top

    def _format_position(self, offset: int) -> str:
        """
        Format position as human-readable text.

        Args:
            offset: Current offset in ROM

        Returns:
            Formatted position string
        """
        if self._rom_size > 0:
            mb_position = offset / (1024 * 1024)
            percentage = (offset / self._rom_size) * 100
            return f"{mb_position:.1f}MB through ROM ({percentage:.0f}%)"
        return "Unknown position"

    def _on_slider_changed(self, value: int) -> None:
        """Handle slider changes - smart preview coordinator handles preview updates automatically."""
        logger.debug(f"[TRACE_SIGNAL] _on_slider_changed (valueChanged) called with value: 0x{value:06X}")
        self._current_offset = value
        self._update_displays()

        # Update manual spinbox without triggering signal
        self.manual_spinbox.blockSignals(True)
        self.manual_spinbox.setValue(value)
        self.manual_spinbox.blockSignals(False)

        # CRITICAL: Emit offset_changed signal so dialog can request preview
        logger.debug(f"[DEBUG] Emitting offset_changed signal with value: 0x{value:06X}")
        self.offset_changed.emit(value)

        # Note: SmartPreviewCoordinator handles preview updates automatically via
        # sliderMoved signal - no need to manually request here
        logger.debug("[DEBUG] _on_slider_changed complete, offset_changed signal emitted")

    def _on_manual_changed(self, value: int) -> None:
        """Handle manual spinbox changes."""
        self._current_offset = value
        self._update_displays()

        # Update slider without triggering signal
        self.position_slider.blockSignals(True)
        self.position_slider.setValue(value)
        self.position_slider.blockSignals(False)

        self.offset_changed.emit(value)

        # Request immediate high-quality preview for manual changes
        if self._smart_preview_coordinator is not None:
            self._smart_preview_coordinator.request_manual_preview(value)

    def _update_displays(self) -> None:
        """Update position displays."""
        if self.position_label:
            self.position_label.setText(self._format_position(self._current_offset))
        if self.offset_label:
            self.offset_label.setText(f"0x{self._current_offset:06X}")

    def _on_go_button_clicked(self) -> None:
        """Handle go button click without lambda."""
        self.set_offset(self.manual_spinbox.value())

    def get_current_offset(self) -> int:
        """
        Get current offset.

        Returns:
            Current offset value
        """
        return self._current_offset

    def set_offset(self, offset: int) -> None:
        """
        Set current offset.

        Args:
            offset: New offset value
        """
        if offset != self._current_offset:
            self._current_offset = offset

            # Update controls without triggering signals
            self.position_slider.blockSignals(True)
            self.manual_spinbox.blockSignals(True)

            self.position_slider.setValue(offset)
            self.manual_spinbox.setValue(offset)

            self.position_slider.blockSignals(False)
            self.manual_spinbox.blockSignals(False)

            self._update_displays()

            # Emit the offset_changed signal for programmatic changes
            # This ensures the dialog gets notified
            self.offset_changed.emit(offset)

            # Note: Preview will be requested by the dialog's _on_offset_changed handler
            # No need to request it here to avoid duplicates

    def get_step_size(self) -> int:
        """
        Get step size.

        Returns:
            Current step size value
        """
        return self.step_spinbox.value()

    def set_rom_size(self, size: int) -> None:
        """
        Set ROM size.

        Args:
            size: Size of ROM in bytes
        """
        self._rom_size = size
        self.position_slider.setMaximum(size)
        self.manual_spinbox.setMaximum(size)
        self._update_displays()

    def set_navigation_enabled(self, enabled: bool) -> None:
        """
        Enable/disable navigation buttons.

        Args:
            enabled: Whether navigation should be enabled
        """
        if self.prev_button:
            self.prev_button.setEnabled(enabled)
        if self.next_button:
            self.next_button.setEnabled(enabled)

    def connect_smart_preview_coordinator(self, coordinator: SimplePreviewCoordinator) -> None:
        """
        Connect smart preview coordinator for enhanced preview updates.

        Args:
            coordinator: Preview coordinator instance
        """
        self._smart_preview_coordinator = coordinator
        if coordinator:
            # Connect coordinator to slider for drag detection
            coordinator.connect_slider(self.position_slider)

            # Setup UI update callback for immediate feedback
            coordinator.set_ui_update_callback(self._on_smart_ui_update)

            logger.debug("Smart preview coordinator connected to browse tab")

    def set_rom_path(self, rom_path: str) -> None:
        """
        Set ROM path for advanced search.

        Args:
            rom_path: Path to ROM file
        """
        self._rom_path = rom_path

    def _open_advanced_search(self) -> None:
        """Open the advanced search dialog."""
        if not self._rom_path:
            logger.warning("No ROM path available for advanced search")
            return

        # Lazy import to avoid circular dependencies
        from ui.dialogs.advanced_search_dialog import AdvancedSearchDialog

        # Create or reuse advanced search dialog
        if self._advanced_search_dialog is None:
            self._advanced_search_dialog = AdvancedSearchDialog(self._rom_path, self)
            # Connect sprite selection signal
            self._advanced_search_dialog.sprite_selected.connect(self._on_advanced_search_sprite_selected)

        # Show the dialog
        self._advanced_search_dialog.show()
        self._advanced_search_dialog.raise_()
        self._advanced_search_dialog.activateWindow()

    def _on_advanced_search_sprite_selected(self, offset: int) -> None:
        """Handle sprite selection from advanced search dialog."""
        # Update the manual offset dialog's position
        self.set_offset(offset)

        # Log the action
        logger.debug(f"Advanced search selected sprite at offset 0x{offset:06X}")

    def _paste_from_clipboard(self) -> None:
        """Read offset from Mesen2 clipboard file and navigate to it."""
        # Try multiple possible locations for the clipboard file
        possible_paths = [
            Path.home() / "Mesen2" / "sprite_clipboard.txt",
            Path.home() / "Documents" / "Mesen2" / "sprite_clipboard.txt",
            Path.cwd() / "sprite_clipboard.txt",
        ]

        for clipboard_file in possible_paths:
            if clipboard_file.exists():
                try:
                    with clipboard_file.open() as f:
                        offset_str = f.read().strip()

                    # Parse offset (handles both 0x and $ prefix)
                    if offset_str.startswith("0x"):
                        offset = int(offset_str, 16)
                    elif offset_str.startswith("$"):
                        offset = int(offset_str[1:], 16)
                    else:
                        offset = int(offset_str, 16)

                    # Navigate to the offset
                    logger.info(f"Pasting offset from clipboard: 0x{offset:06X}")
                    self.set_offset(offset)
                    return

                except (OSError, ValueError) as e:
                    logger.error(f"Error reading clipboard file: {e}")

        logger.warning("No clipboard file found. Press 0 in Mesen2 to copy sprite offset.")

    def _on_find_sprites(self) -> None:
        """Handle Find Sprites button click - emit signal for parent to handle."""
        logger.debug("Find Sprites button clicked - emitting signal")
        self.find_sprites_requested.emit()

    def _on_smart_ui_update(self, offset: int) -> None:
        """
        Handle immediate UI updates from smart coordinator.

        Args:
            offset: New offset value
        """
        if offset != self._current_offset:
            # Update displays without triggering signals
            self._current_offset = offset

            self.position_slider.blockSignals(True)
            self.manual_spinbox.blockSignals(True)

            self.position_slider.setValue(offset)
            self.manual_spinbox.setValue(offset)
            self._update_displays()

            self.position_slider.blockSignals(False)
            self.manual_spinbox.blockSignals(False)

    def _create_section_title(self, text: str) -> QLabel:
        """
        Create a styled section title label.

        Args:
            text: Title text

        Returns:
            Styled label widget
        """
        title = QLabel(text)
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(11)
        title.setFont(title_font)
        title.setStyleSheet(f"color: {COLORS['highlight']}; padding: 2px 4px; border-radius: 3px;")
        return title
