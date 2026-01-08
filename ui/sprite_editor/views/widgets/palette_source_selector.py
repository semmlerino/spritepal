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
    """

    # Signals
    sourceChanged = Signal(str, int)  # source_type, palette_index
    loadPaletteClicked = Signal()
    savePaletteClicked = Signal()
    editColorClicked = Signal()

    # Data keys for combo box items
    _SOURCE_TYPE_ROLE = 100
    _PALETTE_INDEX_ROLE = 101

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the palette source selector.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self.setObjectName("paletteSourceSelector")
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
        self.add_palette_source("Default", "default", 0)

    def _on_combo_changed(self, index: int) -> None:
        """Handle combo box selection change.

        Args:
            index: Index of the selected item
        """
        if index < 0:
            return

        source_type = self._combo_box.itemData(index, self._SOURCE_TYPE_ROLE)
        palette_index = self._combo_box.itemData(index, self._PALETTE_INDEX_ROLE)

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
            source_type: Type of source ("default" or "mesen")
            palette_index: Palette index (0-7)
        """
        for i in range(self._combo_box.count()):
            if (
                self._combo_box.itemData(i, self._SOURCE_TYPE_ROLE) == source_type
                and self._combo_box.itemData(i, self._PALETTE_INDEX_ROLE) == palette_index
            ):
                self._combo_box.setCurrentIndex(i)
                return

    def add_palette_source(self, display_name: str, source_type: str, palette_index: int) -> None:
        """Add a palette source to the dropdown.

        Args:
            display_name: Display name for the source (e.g., "Default")
            source_type: Type of source ("default" or "mesen")
            palette_index: Palette index (0-7)
        """
        self._combo_box.addItem(display_name)
        index = self._combo_box.count() - 1
        self._combo_box.setItemData(index, source_type, self._SOURCE_TYPE_ROLE)
        self._combo_box.setItemData(index, palette_index, self._PALETTE_INDEX_ROLE)

    def clear_mesen_sources(self) -> None:
        """Remove all Mesen2 sources, keeping only "Default".

        Preserves the default source and clears all mesen sources.
        If "Default" is removed, adds it back at index 0.
        """
        # Remove all mesen sources
        i = self._combo_box.count() - 1
        while i >= 0:
            source_type = self._combo_box.itemData(i, self._SOURCE_TYPE_ROLE)
            if source_type == "mesen":
                self._combo_box.removeItem(i)
            i -= 1

        # Ensure "Default" exists
        if self._combo_box.count() == 0:
            self.add_palette_source("Default", "default", 0)

        # Reset to default if nothing selected
        if self._combo_box.currentIndex() < 0:
            self._combo_box.setCurrentIndex(0)
