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
from ui.common.widget_helpers import create_styled_label
from ui.styles import get_prominent_action_button_style
from ui.styles.theme import COLORS
from utils.constants import (
    MIN_SPRITE_SIZE,
    ROM_MIN_REGION_SIZE,
    ROM_SIZE_1MB,
    ROM_SIZE_2MB,
    ROM_SIZE_4MB,
    RomMappingType,
    normalize_address,
    parse_address_string,
)

# Import AdvancedSearchDialog lazily to avoid circular imports
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from ui.common.smart_preview_coordinator import SmartPreviewCoordinator
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
    navigate_step_requested = Signal(int)  # Request to navigate by step amount
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
        self._current_offset: int = ROM_SIZE_2MB
        self._rom_size: int = ROM_SIZE_4MB
        self._step_size: int = ROM_MIN_REGION_SIZE
        self._rom_path: str = ""
        self._header_offset: int = 0  # SMC header size
        self._mapping_type: RomMappingType = RomMappingType.LOROM  # ROM mapping type for SNES addresses
        self._advanced_search_dialog: AdvancedSearchDialog | None = None
        self._smart_preview_coordinator: SmartPreviewCoordinator | None = None
        self._focus_mode_active: bool = False  # Track if slider is in focus mode (zoomed)
        self._focus_window_size: int = 0x8000  # 32KB window for focus mode (±16KB)

        self._setup_ui()

    def set_header_offset(self, offset: int) -> None:
        """Set SMC header offset for file offset conversion."""
        self._header_offset = offset

    def set_mapping_type(self, mapping_type: RomMappingType) -> None:
        """Set ROM mapping type for SNES address conversion (LoROM, HiROM, SA-1)."""
        self._mapping_type = mapping_type

    def _setup_ui(self) -> None:
        """Set up the browse tab UI with improved layout and spacing."""
        from PySide6.QtWidgets import QCheckBox

        layout = QVBoxLayout(self)
        layout.setSpacing(SPACING_SMALL)  # Better spacing between sections
        layout.setContentsMargins(
            SPACING_STANDARD, SPACING_STANDARD, SPACING_STANDARD, SPACING_STANDARD
        )  # More comfortable margins

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
        controls_layout.setSpacing(SPACING_STANDARD)
        controls_layout.setContentsMargins(
            SPACING_MEDIUM, SPACING_MEDIUM, SPACING_MEDIUM, SPACING_MEDIUM
        )

        # --- 1. Primary Navigation Bar (Top) ---
        # Offset Spinbox | Go | Divider | Step Size | Next/Prev Step
        primary_nav_row = QHBoxLayout()
        primary_nav_row.setSpacing(SPACING_SMALL)

        # Offset Input Group
        offset_label = QLabel("Offset:")
        offset_label.setStyleSheet(f"font-weight: bold; color: {COLORS['text_secondary']};")
        primary_nav_row.addWidget(offset_label)

        self.manual_spinbox = QSpinBox()
        self.manual_spinbox.setMinimum(0)
        # QSpinBox has 32-bit signed int limit; clamp like slider does
        max_spinbox_value = min(self._rom_size, 0x7FFFFFFF)
        self.manual_spinbox.setMaximum(max_spinbox_value)
        self.manual_spinbox.setValue(self._current_offset)
        self.manual_spinbox.setDisplayIntegerBase(16)
        self.manual_spinbox.setPrefix("0x")
        self.manual_spinbox.setMinimumWidth(120)
        self.manual_spinbox.setFixedHeight(28)  # Slightly larger for touch targets
        if self.manual_spinbox:
            self.manual_spinbox.setStyleSheet(f"""
            QSpinBox {{
                padding: 4px;
                background-color: {COLORS["panel_background"]};
                border: 1px solid {COLORS["border"]};
                border-radius: 4px;
                font-family: monospace;
                font-size: 13px;
                font-weight: bold;
            }}
        """)
        # Defer valueChanged to avoid spamming while typing, rely on returnPressed or Go button
        # But we also want arrow keys to work immediately.
        # Let's use returnPressed for navigation, and valueChanged only updates internal state without navigation?
        # Actually, standard behavior is valueChanged updates immediately. Let's stick to that but ensure debouncing elsewhere if needed.
        self.manual_spinbox.valueChanged.connect(self._on_manual_changed)
        primary_nav_row.addWidget(self.manual_spinbox)

        go_button = QPushButton("Go")
        go_button.setFixedHeight(28)
        go_button.setStyleSheet(f"""
            QPushButton {{
                padding: 4px 12px;
                background-color: {COLORS["highlight"]};
                border: 1px solid {COLORS["highlight_hover"]};
                border-radius: 4px;
                color: white;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {COLORS["highlight_hover"]};
            }}
        """)
        go_button.clicked.connect(self._on_go_button_clicked)
        primary_nav_row.addWidget(go_button)

        # Spacer / Divider
        primary_nav_row.addSpacing(SPACING_STANDARD)
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.VLine)
        divider.setStyleSheet(f"background-color: {COLORS['border']}; max-width: 1px; height: 20px;")
        primary_nav_row.addWidget(divider)
        primary_nav_row.addSpacing(SPACING_STANDARD)

        # Step Size Group
        step_label = QLabel("Step:")
        step_label.setStyleSheet(f"color: {COLORS['text_muted']};")
        primary_nav_row.addWidget(step_label)

        self.step_spinbox = QSpinBox()
        self.step_spinbox.setMinimum(MIN_SPRITE_SIZE)
        self.step_spinbox.setMaximum(ROM_SIZE_1MB)
        self.step_spinbox.setValue(self._step_size)
        self.step_spinbox.setDisplayIntegerBase(16)
        self.step_spinbox.setPrefix("0x")
        self.step_spinbox.setMinimumWidth(80)
        self.step_spinbox.setFixedHeight(28)
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
        primary_nav_row.addWidget(self.step_spinbox)

        # Step Navigation Buttons
        step_btn_style = f"""
            QPushButton {{
                padding: 4px 8px;
                background-color: {COLORS["panel_background"]};
                border: 1px solid {COLORS["border"]};
                border-radius: 4px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                border-color: {COLORS["highlight"]};
                background-color: {COLORS["focus_background_subtle"]};
            }}
        """

        step_prev_btn = QPushButton("◀")
        step_prev_btn.setToolTip("Move backward by step size")
        step_prev_btn.setFixedWidth(30)
        step_prev_btn.setFixedHeight(28)
        step_prev_btn.setStyleSheet(step_btn_style)
        step_prev_btn.clicked.connect(self._on_prev_step_clicked)
        primary_nav_row.addWidget(step_prev_btn)

        step_next_btn = QPushButton("▶")
        step_next_btn.setToolTip("Move forward by step size")
        step_next_btn.setFixedWidth(30)
        step_next_btn.setFixedHeight(28)
        step_next_btn.setStyleSheet(step_btn_style)
        step_next_btn.clicked.connect(self._on_next_step_clicked)
        primary_nav_row.addWidget(step_next_btn)

        primary_nav_row.addStretch()

        # Clipboard Paste (moved to top right)
        self.paste_button = QPushButton("📋")
        self.paste_button.setToolTip(
            "Paste offset from clipboard\n\n"
            "Supports:\n"
            "• Mesen2 log format: 'FILE OFFSET: 0x3C6EF1'\n"
            "• SNES addresses: $98:8000 or $988000\n"
            "• Hex: 0x0C3000\n"
            "• Mesen2 clipboard file (Key 0 in Lua script)"
        )
        self.paste_button.setFixedSize(30, 28)
        self.paste_button.setStyleSheet(step_btn_style)
        self.paste_button.clicked.connect(self._paste_from_clipboard)
        primary_nav_row.addWidget(self.paste_button)

        controls_layout.addLayout(primary_nav_row)

        # Add separator
        separator1 = QFrame()
        separator1.setFrameShape(QFrame.Shape.HLine)
        separator1.setStyleSheet(f"background-color: {COLORS['panel_background']}; max-height: 1px;")
        controls_layout.addWidget(separator1)

        # --- 2. Seek/Scan Bar (Middle) ---
        # Seek Prev Sprite | Find All Sprites | Advanced | Seek Next Sprite
        seek_row = QHBoxLayout()
        seek_row.setSpacing(SPACING_SMALL)

        action_btn_style = f"""
            QPushButton {{
                padding: 6px 12px;
                background-color: {COLORS["panel_background"]};
                border: 1px solid {COLORS["border"]};
                border-radius: 4px;
                color: {COLORS["text_secondary"]};
            }}
            QPushButton:hover {{
                background-color: {COLORS["focus_background_subtle"]};
                border-color: {COLORS["highlight"]};
            }}
        """

        self.prev_button = QPushButton("⏮ Seek Prev Sprite")
        self.prev_button.setStyleSheet(action_btn_style)
        self.prev_button.setToolTip("Scan backward for next valid HAL-compressed sprite")
        self.prev_button.clicked.connect(self.find_prev_clicked.emit)
        seek_row.addWidget(self.prev_button)

        # Central Action Group
        self.find_sprites_button = QPushButton("🔍 Find All Sprites")
        self.find_sprites_button.setStyleSheet(action_btn_style)
        self.find_sprites_button.setToolTip("Scan entire ROM for HAL-compressed sprites\n\nKeyboard shortcut: Ctrl+F")
        self.find_sprites_button.clicked.connect(self._on_find_sprites)
        seek_row.addWidget(self.find_sprites_button)

        self.advanced_search_button = QPushButton("⚙️ Advanced")
        self.advanced_search_button.setStyleSheet(action_btn_style)
        self.advanced_search_button.setToolTip("Open advanced search dialog with filtering and batch operations")
        self.advanced_search_button.clicked.connect(self._open_advanced_search)
        seek_row.addWidget(self.advanced_search_button)

        self.next_button = QPushButton("Seek Next Sprite ⏭")
        self.next_button.setStyleSheet(action_btn_style)
        self.next_button.setToolTip("Scan forward for next valid HAL-compressed sprite")
        self.next_button.clicked.connect(self.find_next_clicked.emit)
        seek_row.addWidget(self.next_button)

        controls_layout.addLayout(seek_row)

        # Add separator
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.Shape.HLine)
        separator2.setStyleSheet(f"background-color: {COLORS['panel_background']}; max-height: 1px;")
        controls_layout.addWidget(separator2)

        # --- 3. Context & Coarse Nav (Bottom) ---
        # Slider with Focus Mode | Position Info
        
        # Header for slider section
        slider_header = QHBoxLayout()
        slider_title = QLabel("ROM Navigation")
        slider_title.setStyleSheet(f"font-weight: bold; color: {COLORS['text_muted']}; font-size: 11px; text-transform: uppercase;")
        slider_header.addWidget(slider_title)
        
        slider_header.addStretch()
        
        # Focus Mode Toggle
        self.focus_mode_check = QCheckBox("Focus Mode (Zoom)")
        self.focus_mode_check.setToolTip("Zoom slider to a smaller range around current offset for fine-tuning")
        self.focus_mode_check.setStyleSheet(f"""
            QCheckBox {{ color: {COLORS['text_secondary']}; }}
            QCheckBox::indicator:checked {{ background-color: {COLORS['highlight']}; border-color: {COLORS['highlight']}; }}
        """)
        self.focus_mode_check.toggled.connect(self._on_focus_toggled)
        slider_header.addWidget(self.focus_mode_check)
        
        controls_layout.addLayout(slider_header)

        # Slider with smart preview support and type-safe range checking
        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.setObjectName("manual_offset_rom_slider")
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

        # Position info row
        info_row = QHBoxLayout()
        info_row.setSpacing(SPACING_MEDIUM)

        self.position_label = QLabel(self._format_position(self._current_offset))
        position_font = QFont()
        position_font.setBold(True)
        position_font.setPointSize(10)
        self.position_label.setFont(position_font)
        self.position_label.setStyleSheet(f"color: {COLORS['text_muted']};")
        info_row.addWidget(self.position_label)

        info_row.addStretch()

        # ROM Range Label (e.g. "0x000000 - 0x400000")
        self.range_label = QLabel(f"0x0 - 0x{self._rom_size:X}")
        self.range_label.setStyleSheet(f"font-family: monospace; color: {COLORS['text_muted']}; font-size: 10px;")
        info_row.addWidget(self.range_label)

        controls_layout.addLayout(info_row)

        layout.addWidget(controls_frame)
        layout.addStretch()  # Push content to top

    def _on_next_step_clicked(self) -> None:
        """Handle next step button click."""
        step = self.get_step_size()
        self.navigate_step_requested.emit(step)

    def _on_prev_step_clicked(self) -> None:
        """Handle prev step button click."""
        step = self.get_step_size()
        self.navigate_step_requested.emit(-step)

    def _on_focus_toggled(self, checked: bool) -> None:
        """Handle Focus Mode toggle."""
        self._focus_mode_active = checked
        self._update_slider_range()
        
        # Update styling to indicate focus mode
        if checked:
            self.position_slider.setStyleSheet(f"""
                QSlider::groove:horizontal {{
                    border: 2px solid {COLORS["highlight"]};
                    height: 8px;
                    background: {COLORS["focus_background_subtle"]};
                    border-radius: 4px;
                }}
                QSlider::handle:horizontal {{
                    background: {COLORS["highlight"]};
                    border: 2px solid white;
                    width: 18px;
                    margin: -5px 0;
                    border-radius: 9px;
                }}
                QSlider::sub-page:horizontal {{
                    background: {COLORS["highlight_hover"]};
                    border-radius: 4px;
                }}
            """)
        else:
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
                QSlider::sub-page:horizontal {{
                    background: {COLORS["browse_pressed"]};
                    border-radius: 4px;
                }}
            """)

    def _update_slider_range(self) -> None:
        """Update slider min/max/value based on focus mode."""
        self.position_slider.blockSignals(True)
        
        if self._focus_mode_active:
            # Focus Mode: Slider represents a window around current offset
            # We want the slider to be centered if possible
            # Range: current - window/2 to current + window/2
            
            # Note: We can't actually change the range dynamically while dragging without jumping.
            # Instead, when focus is enabled, we set the range relative to the *current* offset.
            # As the user moves the slider, the offset changes within that fixed window.
            # If they want to move the window, they must exit focus mode or use step buttons.
            
            # Actually, better behavior: When focus enabled, set range to window around CURRENT.
            # When slider moves, offset updates.
            # If offset is updated externally (e.g. step buttons), does the window move?
            # Yes, if we recenter the window on external updates.
            
            center = self._current_offset
            half_window = self._focus_window_size // 2
            
            min_val = max(0, center - half_window)
            max_val = min(self._rom_size, center + half_window)
            
            self.position_slider.setMinimum(min_val)
            self.position_slider.setMaximum(max_val)
            self.position_slider.setValue(self._current_offset)
            
            self.range_label.setText(f"Focus: 0x{min_val:X} - 0x{max_val:X}")
            
        else:
            # Full ROM Mode
            max_val = min(self._rom_size, 0x7FFFFFFF)
            self.position_slider.setMinimum(0)
            self.position_slider.setMaximum(max_val)
            self.position_slider.setValue(self._current_offset)
            
            self.range_label.setText(f"0x0 - 0x{self._rom_size:X}")
            
        self.position_slider.blockSignals(False)

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
            return f"{mb_position:.2f}MB / {percentage:.1f}%"
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
        
        # If in focus mode, we might need to recenter the window if the value went out of bounds,
        # or just update the slider value.
        if self._focus_mode_active:
            # Check if within current slider range
            if value < self.position_slider.minimum() or value > self.position_slider.maximum():
                # Re-center window around new value
                self._update_slider_range()
            else:
                self.position_slider.blockSignals(True)
                self.position_slider.setValue(value)
                self.position_slider.blockSignals(False)
        else:
            # Update slider without triggering signal
            self.position_slider.blockSignals(True)
            self.position_slider.setValue(value)
            self.position_slider.blockSignals(False)

        self.offset_changed.emit(value)
        # Preview is requested by dialog's _on_offset_changed handler

    def _update_displays(self) -> None:
        """Update position displays."""
        if self.position_label:
            self.position_label.setText(self._format_position(self._current_offset))

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
        logger.debug("BrowseTab.set_offset called: 0x%06X (current: 0x%06X)", offset, self._current_offset)
        if offset != self._current_offset:
            self._current_offset = offset

            # Update controls without triggering signals
            self.manual_spinbox.blockSignals(True)
            self.manual_spinbox.setValue(offset)
            self.manual_spinbox.blockSignals(False)
            
            # Handle slider update (with focus mode logic)
            if self._focus_mode_active:
                # Always recenter on external offset set
                self._update_slider_range()
            else:
                self.position_slider.blockSignals(True)
                self.position_slider.setValue(offset)
                self.position_slider.blockSignals(False)

            self._update_displays()

            # Emit the offset_changed signal for programmatic changes
            # This ensures the dialog gets notified
            self.offset_changed.emit(offset)
            logger.debug("BrowseTab.set_offset: emitted offset_changed for 0x%06X", offset)

            # Note: Preview will be requested by the dialog's _on_offset_changed handler
            # No need to request it here to avoid duplicates
        else:
            logger.debug("BrowseTab.set_offset: offset unchanged, skipping update")

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
        # QSlider and QSpinBox have 32-bit signed int limit
        max_value = min(size, 0x7FFFFFFF)
        # Update manual spinbox max
        self.manual_spinbox.setMaximum(max_value)
        # Update slider range (respecting focus mode)
        self._update_slider_range()
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

    def connect_smart_preview_coordinator(self, coordinator: SmartPreviewCoordinator) -> None:
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
        """Read offset from system clipboard or Mesen2 clipboard file.

        Supports multiple address formats from emulators:
        - Mesen2 log format: "FILE OFFSET: 0x3C6EF1" (parsed from sprite_rom_finder.lua output)
        - SNES bank:offset: $98:8000 or 98:8000 (auto-converted to file offset)
        - SNES combined: $988000
        - Hex: 0x0C3000 or 0C3000
        - Decimal: 123456
        """
        import re

        from PySide6.QtWidgets import QApplication

        # First, try the system clipboard for Mesen2 log format
        clipboard = QApplication.clipboard()
        if clipboard is not None:  # type: ignore[reportUnnecessaryComparison]
            text = clipboard.text().strip()
            if text:
                # Try Mesen2 "FILE OFFSET: 0xNNNNNN" format first
                mesen2_pattern = re.compile(r"FILE OFFSET:\s*0x([0-9A-Fa-f]{6})")
                match = mesen2_pattern.search(text)
                if match:
                    file_offset = int(match.group(1), 16)
                    offset = max(0, file_offset - self._header_offset)
                    logger.info(
                        f"Pasted Mesen2 offset from clipboard: 0x{file_offset:06X} (adjusted to 0x{offset:06X})"
                    )
                    self.set_offset(offset)
                    return

                # Try other address formats from clipboard
                try:
                    raw_value, fmt = parse_address_string(text)
                    offset = normalize_address(raw_value, self._rom_size, mapping_type=self._mapping_type)
                    if fmt.startswith("snes"):
                        logger.info(f"Converted SNES ${raw_value:06X} → File 0x{offset:06X}")
                    else:
                        logger.info(f"Pasting offset from clipboard: 0x{offset:06X}")
                    self.set_offset(offset)
                    return
                except ValueError:
                    pass  # Fall through to file-based clipboard

        # Fall back to file-based clipboard locations
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

                    # Parse address in various formats (hex, decimal, SNES bank:offset)
                    raw_value, fmt = parse_address_string(offset_str)

                    # Normalize SNES addresses to file offsets
                    offset = normalize_address(raw_value, self._rom_size, mapping_type=self._mapping_type)

                    # Log conversion info for SNES addresses
                    if fmt.startswith("snes"):
                        logger.info(f"Converted SNES ${raw_value:06X} → File 0x{offset:06X}")
                    else:
                        logger.info(f"Pasting offset from clipboard file: 0x{offset:06X}")

                    self.set_offset(offset)
                    return

                except (OSError, ValueError) as e:
                    logger.error(f"Error reading clipboard file: {e}")

        logger.warning("No valid offset found in clipboard. Copy 'FILE OFFSET: 0xNNNNNN' from Mesen2 log.")

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
