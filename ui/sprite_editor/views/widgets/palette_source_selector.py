#!/usr/bin/env python3
"""
Palette Source Selector widget for the sprite editor.
Allows selection between default palette and Mesen2-captured palettes.
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.common.spacing_constants import (
    COMPACT_BUTTON_HEIGHT,
    MEDIUM_WIDTH,
    SPACING_SMALL,
)
from ui.sprite_editor.views.widgets.palette_preview_delegate import (
    PALETTE_COLORS_ROLE,
    PALETTE_IS_ACTIVE_ROLE,
    PalettePreviewDelegate,
)


class PaletteSourceSelector(QWidget):
    """
    Widget for selecting a palette source (default or Mesen2 capture).

    Provides a dropdown to choose between default palette and up to 8 Mesen2-
    captured palettes, with buttons for loading, saving, and editing palettes.

    Signals:
        sourceChanged: Emitted when palette source is changed.
            Args: source_type (str), palette_index (int)
        loadPaletteClicked: Emitted when "Load Palette..." button is clicked.
        savePaletteClicked: Emitted when "Save Palette..." button is clicked.
        editColorClicked: Emitted when "Edit Color" button is clicked.
        manualPaletteRequested: Emitted when "Manual Palette Offset..." is selected.
    """

    # Signals
    sourceChanged = Signal(str, int)  # source_type, palette_index
    loadPaletteClicked = Signal()
    savePaletteClicked = Signal()
    editColorClicked = Signal()
    manualPaletteRequested = Signal()  # Emitted when "Manual Palette Offset..." selected

    # Data keys for combo box items
    _SOURCE_TYPE_ROLE = 100
    _PALETTE_INDEX_ROLE = 101
    _MANUAL_PALETTE_MARKER = "manual"  # Special marker for manual palette entry

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the palette source selector.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self.setObjectName("paletteSourceSelector")
        self._separator_index = -1  # Index of the separator before manual entry
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Configure the widget layout and controls."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(SPACING_SMALL)

        # Combo box row
        combo_layout = QHBoxLayout()
        combo_layout.setContentsMargins(0, 0, 0, 0)
        combo_layout.setSpacing(SPACING_SMALL)

        label = QLabel("Active Palette Source:")
        combo_layout.addWidget(label)

        self._combo_box = QComboBox()
        self._combo_box.setMinimumWidth(MEDIUM_WIDTH)
        self._combo_box.setItemDelegate(PalettePreviewDelegate(self._combo_box))
        self._combo_box.currentIndexChanged.connect(self._on_combo_changed)
        combo_layout.addWidget(self._combo_box)
        combo_layout.addStretch()

        main_layout.addLayout(combo_layout)

        # Button row
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(SPACING_SMALL)

        self._load_palette_btn = QPushButton("Load Palette...")
        self._load_palette_btn.setMinimumHeight(COMPACT_BUTTON_HEIGHT)
        self._load_palette_btn.clicked.connect(self.loadPaletteClicked.emit)
        button_layout.addWidget(self._load_palette_btn)

        self._save_palette_btn = QPushButton("Save Palette...")
        self._save_palette_btn.setMinimumHeight(COMPACT_BUTTON_HEIGHT)
        self._save_palette_btn.clicked.connect(self.savePaletteClicked.emit)
        button_layout.addWidget(self._save_palette_btn)

        self._edit_color_btn = QPushButton("Edit Color")
        self._edit_color_btn.setMinimumHeight(COMPACT_BUTTON_HEIGHT)
        self._edit_color_btn.clicked.connect(self.editColorClicked.emit)
        button_layout.addWidget(self._edit_color_btn)

        button_layout.addStretch()

        main_layout.addLayout(button_layout)

        # Add default "Default" source to start
        self._add_initial_source("Default", "default", 0)

        # Add separator and manual palette option (tracked for insertion logic)
        self._separator_index = self._combo_box.count()
        self._combo_box.insertSeparator(self._separator_index)
        self._add_manual_palette_entry()

    def _add_initial_source(
        self,
        display_name: str,
        source_type: str,
        palette_index: int,
    ) -> None:
        """Add an initial palette source during setup (appends to end).

        This is used during initialization before the separator is added.
        """
        self._combo_box.addItem(display_name)
        index = self._combo_box.count() - 1
        self._combo_box.setItemData(index, source_type, self._SOURCE_TYPE_ROLE)
        self._combo_box.setItemData(index, palette_index, self._PALETTE_INDEX_ROLE)

    def _add_manual_palette_entry(self) -> None:
        """Add the 'Manual Palette Offset...' entry to the combo box."""
        self._combo_box.addItem("Manual Palette Offset...")
        index = self._combo_box.count() - 1
        self._combo_box.setItemData(index, self._MANUAL_PALETTE_MARKER, self._SOURCE_TYPE_ROLE)
        self._combo_box.setItemData(index, -1, self._PALETTE_INDEX_ROLE)

    def _on_combo_changed(self, index: int) -> None:
        """Handle combo box selection change.

        Args:
            index: Index of the selected item
        """
        if index < 0:
            return

        source_type = self._combo_box.itemData(index, self._SOURCE_TYPE_ROLE)
        palette_index = self._combo_box.itemData(index, self._PALETTE_INDEX_ROLE)

        # Check for manual palette selection
        if source_type == self._MANUAL_PALETTE_MARKER:
            # Emit signal for controller to show dialog
            self.manualPaletteRequested.emit()
            # Revert to previous selection (or default)
            # The controller will update the selection once a manual palette is loaded
            self._combo_box.blockSignals(True)
            self._combo_box.setCurrentIndex(0)  # Revert to Default
            self._combo_box.blockSignals(False)
            return

        if source_type is not None and palette_index is not None:
            self.sourceChanged.emit(source_type, palette_index)

    def get_selected_source(self) -> tuple[str, int]:
        """Get the currently selected palette source.

        Returns:
            Tuple of (source_type, palette_index) where source_type is "default"
            or "mesen" and palette_index is the palette number (0-7).
        """
        index = self._combo_box.currentIndex()
        if index < 0:
            return ("default", 0)

        source_type = self._combo_box.itemData(index, self._SOURCE_TYPE_ROLE)
        palette_index = self._combo_box.itemData(index, self._PALETTE_INDEX_ROLE)

        if source_type is None or palette_index is None:
            return ("default", 0)

        return (source_type, palette_index)

    def set_selected_source(self, source_type: str, palette_index: int) -> None:
        """Set the selected palette source.

        Args:
            source_type: Type of source ("default", "mesen", "rom", or "" for custom)
            palette_index: Palette index
        """
        if not source_type:
            # Handle custom/modified state
            index = self._ensure_custom_item()
            self._combo_box.setCurrentIndex(index)
            return

        for i in range(self._combo_box.count()):
            if (
                self._combo_box.itemData(i, self._SOURCE_TYPE_ROLE) == source_type
                and self._combo_box.itemData(i, self._PALETTE_INDEX_ROLE) == palette_index
            ):
                self._combo_box.setCurrentIndex(i)
                return

    def _ensure_custom_item(self) -> int:
        """Ensure a '[Modified]' entry exists in the combo box.

        Returns the index of the custom item.
        """
        # Check if already exists
        for i in range(self._combo_box.count()):
            if self._combo_box.itemData(i, self._SOURCE_TYPE_ROLE) == "":
                return i

        # Insert before the separator (keeping Manual at the end)
        if self._separator_index >= 0:
            self._combo_box.insertItem(self._separator_index, "[Modified]")
            index = self._separator_index
            # Update separator index since we inserted before it
            self._separator_index += 1
        else:
            self._combo_box.addItem("[Modified]")
            index = self._combo_box.count() - 1

        self._combo_box.setItemData(index, "", self._SOURCE_TYPE_ROLE)
        self._combo_box.setItemData(index, -1, self._PALETTE_INDEX_ROLE)
        return index

    def add_palette_source(
        self,
        display_name: str,
        source_type: str,
        palette_index: int,
        colors: list[tuple[int, int, int]] | None = None,
        is_active: bool = False,
    ) -> None:
        """Add a palette source to the dropdown.

        New sources are inserted before the separator (which precedes the
        "Manual Palette Offset..." entry), keeping the manual option at the end.

        Args:
            display_name: Display name for the source (e.g., "Default", "ROM Palette 8")
            source_type: Type of source ("default", "mesen", or "rom")
            palette_index: Palette index (0-15)
            colors: Optional list of RGB tuples for preview swatches (first 4 used)
            is_active: Whether this palette is actively used (detected via OAM)
        """
        # Insert before the separator (or append if no separator exists yet)
        if self._separator_index >= 0:
            self._combo_box.insertItem(self._separator_index, display_name)
            index = self._separator_index
            # Update separator index since we inserted before it
            self._separator_index += 1
        else:
            self._combo_box.addItem(display_name)
            index = self._combo_box.count() - 1

        self._combo_box.setItemData(index, source_type, self._SOURCE_TYPE_ROLE)
        self._combo_box.setItemData(index, palette_index, self._PALETTE_INDEX_ROLE)

        # Store color preview data (first 4 colors for delegate rendering)
        if colors:
            self._combo_box.setItemData(index, colors[:4], PALETTE_COLORS_ROLE)

        # Store OAM-active flag
        self._combo_box.setItemData(index, is_active, PALETTE_IS_ACTIVE_ROLE)

    def clear_mesen_sources(self) -> None:
        """Remove all Mesen2 sources, keeping only "Default".

        Preserves the default source and clears all mesen sources.
        If "Default" is removed, adds it back at index 0.
        """
        # Remove all mesen sources (iterate backwards to handle index changes)
        i = self._combo_box.count() - 1
        while i >= 0:
            source_type = self._combo_box.itemData(i, self._SOURCE_TYPE_ROLE)
            if source_type == "mesen":
                self._combo_box.removeItem(i)
                # Adjust separator index if we removed an item before it
                if i < self._separator_index:
                    self._separator_index -= 1
            i -= 1

        # Ensure "Default" exists
        if self._combo_box.count() == 0:
            self.add_palette_source("Default", "default", 0)

        # Reset to default if nothing selected
        if self._combo_box.currentIndex() < 0:
            self._combo_box.setCurrentIndex(0)

    def clear_rom_sources(self) -> None:
        """Remove all ROM palette sources, keeping Default and Mesen sources.

        Preserves the default source and any mesen sources.
        """
        # Remove all rom sources (iterate backwards to handle index changes)
        i = self._combo_box.count() - 1
        while i >= 0:
            source_type = self._combo_box.itemData(i, self._SOURCE_TYPE_ROLE)
            if source_type == "rom":
                self._combo_box.removeItem(i)
                # Adjust separator index if we removed an item before it
                if i < self._separator_index:
                    self._separator_index -= 1
            i -= 1

        # Ensure "Default" exists
        if self._combo_box.count() == 0:
            self.add_palette_source("Default", "default", 0)

        # Reset to default if nothing selected
        if self._combo_box.currentIndex() < 0:
            self._combo_box.setCurrentIndex(0)
