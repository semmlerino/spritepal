#!/usr/bin/env python3
"""
Icon toolbar widget for the sprite editor.
Provides horizontal toolbar with tool selection, zoom controls, and grid toggles.
"""

from PySide6.QtCore import QSignalBlocker, QSize, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QToolButton,
    QWidget,
)

from ui.common.spacing_constants import SPACING_SMALL


class IconToolbar(QWidget):
    """
    Horizontal toolbar with tool selection, zoom, and display toggle buttons.
    Replaces ToolPanel for a more compact UI in the sprite editor.
    """

    # Signals - Tool selection
    toolChanged = Signal(str)  # "pencil", "fill", "picker", "eraser"

    # Signals - Zoom controls
    zoomInClicked = Signal()
    zoomOutClicked = Signal()

    # Signals - Display toggles
    gridToggled = Signal(bool)  # pixel grid visibility
    tileGridToggled = Signal(bool)  # tile grid visibility
    palettePreviewToggled = Signal(bool)  # palette preview visibility

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("iconToolbar")

        # Tool names and their display info
        self._tool_names = ["pencil", "fill", "picker", "eraser"]
        self._tool_icons = {
            "pencil": "✏️",
            "fill": "🪣",
            "picker": "💧",
            "eraser": "🧹",
        }
        self._tool_tooltips = {
            "pencil": "Pencil (Draw pixels)",
            "fill": "Fill Bucket (Fill regions)",
            "picker": "Color Picker (Sample colors)",
            "eraser": "Eraser (Paint transparent)",
        }

        # Store button references
        self.tool_buttons: dict[str, QToolButton] = {}
        self.zoom_in_btn: QToolButton | None = None
        self.zoom_out_btn: QToolButton | None = None
        self.grid_btn: QToolButton | None = None
        self.tile_grid_btn: QToolButton | None = None
        self.palette_preview_btn: QToolButton | None = None

        # Track toggle states
        self._grid_visible = False
        self._tile_grid_visible = False
        self._palette_preview_enabled = True  # Start with palette colors visible (greyscale mode off)

        # Button group for tool mutual exclusion
        self.tool_group = QButtonGroup()
        self.tool_group.setExclusive(True)

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Initialize the toolbar UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(SPACING_SMALL)

        # Tool selection buttons (pencil, fill, picker, eraser)
        for i, tool_name in enumerate(self._tool_names):
            btn = QToolButton()
            btn.setCheckable(True)
            btn.setText(self._tool_icons[tool_name])
            btn.setToolTip(self._tool_tooltips[tool_name])
            btn.setIconSize(self._get_icon_size())

            self.tool_buttons[tool_name] = btn
            self.tool_group.addButton(btn, i)
            layout.addWidget(btn)

        # Set pencil as default
        if "pencil" in self.tool_buttons:
            self.tool_buttons["pencil"].setChecked(True)

        # Connect tool group signal
        self.tool_group.idClicked.connect(self._on_tool_clicked)

        # Separator
        layout.addSpacing(SPACING_SMALL * 2)

        # Zoom controls
        self.zoom_in_btn = QToolButton()
        self.zoom_in_btn.setText("➕")  # noqa: RUF001
        self.zoom_in_btn.setToolTip("Zoom In (Ctrl + Mouse Wheel Up)")
        self.zoom_in_btn.setIconSize(self._get_icon_size())
        self.zoom_in_btn.clicked.connect(self.zoomInClicked.emit)
        layout.addWidget(self.zoom_in_btn)

        self.zoom_out_btn = QToolButton()
        self.zoom_out_btn.setText("➖")  # noqa: RUF001
        self.zoom_out_btn.setToolTip("Zoom Out (Ctrl + Mouse Wheel Down)")
        self.zoom_out_btn.setIconSize(self._get_icon_size())
        self.zoom_out_btn.clicked.connect(self.zoomOutClicked.emit)
        layout.addWidget(self.zoom_out_btn)

        # Separator
        layout.addSpacing(SPACING_SMALL * 2)

        # Display toggle buttons
        self.grid_btn = QToolButton()
        self.grid_btn.setCheckable(True)
        self.grid_btn.setText("⊞")
        self.grid_btn.setToolTip("Toggle Pixel Grid (G)")
        self.grid_btn.setIconSize(self._get_icon_size())
        self.grid_btn.clicked.connect(self._on_grid_toggled)
        layout.addWidget(self.grid_btn)

        self.tile_grid_btn = QToolButton()
        self.tile_grid_btn.setCheckable(True)
        self.tile_grid_btn.setText("▦")
        self.tile_grid_btn.setToolTip("Toggle Tile Grid (T)")
        self.tile_grid_btn.setIconSize(self._get_icon_size())
        self.tile_grid_btn.clicked.connect(self._on_tile_grid_toggled)
        layout.addWidget(self.tile_grid_btn)

        self.palette_preview_btn = QToolButton()
        self.palette_preview_btn.setCheckable(True)
        self.palette_preview_btn.setChecked(True)  # Start with palette preview enabled
        self.palette_preview_btn.setText("🎨")
        self.palette_preview_btn.setToolTip("Toggle Palette Preview (P)")
        self.palette_preview_btn.setIconSize(self._get_icon_size())
        self.palette_preview_btn.clicked.connect(self._on_palette_preview_toggled)
        layout.addWidget(self.palette_preview_btn)

        # Add stretch to push everything to the left
        layout.addStretch()

    @staticmethod
    def _get_icon_size() -> QSize:
        """Get standard icon size (24x24)."""
        return QSize(24, 24)

    def _on_tool_clicked(self, button_id: int) -> None:
        """Handle tool button click."""
        if 0 <= button_id < len(self._tool_names):
            tool_name = self._tool_names[button_id]
            self.toolChanged.emit(tool_name)

    def _on_grid_toggled(self, checked: bool) -> None:
        """Handle pixel grid toggle."""
        self._grid_visible = checked
        self.gridToggled.emit(checked)

    def _on_tile_grid_toggled(self, checked: bool) -> None:
        """Handle tile grid toggle."""
        self._tile_grid_visible = checked
        self.tileGridToggled.emit(checked)

    def _on_palette_preview_toggled(self, checked: bool) -> None:
        """Handle palette preview toggle."""
        self._palette_preview_enabled = checked
        self.palettePreviewToggled.emit(checked)

    def get_current_tool(self) -> str:
        """Get the currently selected tool name.

        Returns:
            Tool name as string: "pencil", "fill", "picker", or "eraser".
        """
        checked_id = self.tool_group.checkedId()
        if 0 <= checked_id < len(self._tool_names):
            return self._tool_names[checked_id]
        return "pencil"

    def set_tool(self, tool_name: str) -> None:
        """Set the current tool by name (programmatic update).

        Uses QSignalBlocker to prevent re-emitting signals during programmatic updates.

        Args:
            tool_name: Tool name ("pencil", "fill", "picker", or "eraser").
        """
        if tool_name not in self.tool_buttons:
            return

        # Block signals during programmatic update
        blocker = QSignalBlocker(self.tool_group)  # noqa: F841  # pyright: ignore[reportUnusedVariable]
        self.tool_buttons[tool_name].setChecked(True)
        # Signal blocking ends automatically when blocker goes out of scope

    def set_grid_visible(self, visible: bool) -> None:
        """Set pixel grid visibility (programmatic update).

        Args:
            visible: Whether the pixel grid should be visible.
        """
        if self.grid_btn is None:
            return
        self._grid_visible = visible
        with QSignalBlocker(self.grid_btn):
            self.grid_btn.setChecked(visible)

    def set_tile_grid_visible(self, visible: bool) -> None:
        """Set tile grid visibility (programmatic update).

        Args:
            visible: Whether the tile grid should be visible.
        """
        if self.tile_grid_btn is None:
            return
        self._tile_grid_visible = visible
        with QSignalBlocker(self.tile_grid_btn):
            self.tile_grid_btn.setChecked(visible)

    def set_palette_preview(self, enabled: bool) -> None:
        """Set palette preview visibility (programmatic update).

        Args:
            enabled: Whether the palette preview should be enabled.
        """
        if self.palette_preview_btn is None:
            return
        self._palette_preview_enabled = enabled
        with QSignalBlocker(self.palette_preview_btn):
            self.palette_preview_btn.setChecked(enabled)

    def is_grid_visible(self) -> bool:
        """Check if pixel grid is visible.

        Returns:
            True if pixel grid is enabled, False otherwise.
        """
        return self._grid_visible

    def is_tile_grid_visible(self) -> bool:
        """Check if tile grid is visible.

        Returns:
            True if tile grid is enabled, False otherwise.
        """
        return self._tile_grid_visible

    def is_palette_preview_enabled(self) -> bool:
        """Check if palette preview is enabled.

        Returns:
            True if palette preview is enabled, False otherwise.
        """
        return self._palette_preview_enabled
