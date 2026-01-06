"""
Library Tab for displaying saved sprites.

Provides a grid view of sprites saved to the library with search,
filtering, and management capabilities.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.common.spacing_constants import SPACING_SMALL
from ui.common.widget_helpers import create_styled_label
from ui.styles import get_panel_style
from ui.styles.theme import COLORS

if TYPE_CHECKING:
    from core.sprite_library import LibrarySprite, SpriteLibrary

logger = logging.getLogger(__name__)


class LibraryTab(QWidget):
    """
    Tab displaying saved sprites from the library.

    Shows a searchable grid of sprite thumbnails with:
    - Search/filter by name, tags, notes
    - Click to select and view details
    - Double-click to open in editor
    - Right-click context menu for management

    Signals:
        sprite_selected: Emitted when a sprite is selected. Args: (LibrarySprite)
        sprite_activated: Emitted when a sprite is double-clicked. Args: (LibrarySprite)
        edit_requested: Emitted when edit is requested. Args: (rom_offset: int)
    """

    sprite_selected = Signal(object)  # LibrarySprite
    sprite_activated = Signal(object)  # LibrarySprite
    edit_requested = Signal(int)  # rom_offset

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(get_panel_style())

        self._library: SpriteLibrary | None = None
        self._current_sprites: list[LibrarySprite] = []

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Initialize the tab UI."""
        layout = QVBoxLayout()
        layout.setContentsMargins(SPACING_SMALL, SPACING_SMALL, SPACING_SMALL, SPACING_SMALL)
        layout.setSpacing(SPACING_SMALL)

        # Header with title and count
        header_layout = QHBoxLayout()
        header_layout.setSpacing(SPACING_SMALL)

        title_label = create_styled_label("Sprite Library", style="title", parent=self)
        header_layout.addWidget(title_label)

        self._count_label = QLabel("0 sprites", parent=self)
        self._count_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 12px;")
        header_layout.addWidget(self._count_label)

        header_layout.addStretch()

        self._refresh_btn = QPushButton("Refresh", parent=self)
        self._refresh_btn.setToolTip("Reload library from disk")
        header_layout.addWidget(self._refresh_btn)

        layout.addLayout(header_layout)

        # Search bar
        search_layout = QHBoxLayout()
        search_layout.setSpacing(SPACING_SMALL)

        search_label = QLabel("Search:", parent=self)
        search_layout.addWidget(search_label)

        self._search_input = QLineEdit(parent=self)
        self._search_input.setPlaceholderText("Filter by name, tags, notes...")
        self._search_input.setClearButtonEnabled(True)
        search_layout.addWidget(self._search_input)

        layout.addLayout(search_layout)

        # Sprite grid (using QListWidget in icon mode)
        self._grid_widget = QListWidget(parent=self)
        self._grid_widget.setViewMode(QListWidget.ViewMode.IconMode)
        self._grid_widget.setIconSize(self._grid_widget.iconSize().scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio))
        self._grid_widget.setGridSize(
            self._grid_widget.gridSize().scaled(80, 100, Qt.AspectRatioMode.IgnoreAspectRatio)
        )
        self._grid_widget.setSpacing(8)
        self._grid_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._grid_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._grid_widget.setWordWrap(True)
        self._grid_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
        self._grid_widget.setUniformItemSizes(True)

        # Style the grid
        self._grid_widget.setStyleSheet(f"""
            QListWidget {{
                background-color: {COLORS["background"]};
                border: 1px solid {COLORS["border"]};
                border-radius: 4px;
            }}
            QListWidget::item {{
                padding: 4px;
                border-radius: 4px;
            }}
            QListWidget::item:selected {{
                background-color: {COLORS["accent"]};
                color: {COLORS["background"]};
            }}
            QListWidget::item:hover:!selected {{
                background-color: {COLORS["panel_background"]};
            }}
        """)

        layout.addWidget(self._grid_widget, 1)  # Stretch to fill

        # Empty state
        self._empty_label = QLabel(
            "No sprites in library.\n\n"
            "Use 'Save to Library' after extracting a sprite\n"
            "or from the Mesen2 Captures panel.",
            parent=self,
        )
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 12px;")
        self._empty_label.setWordWrap(True)
        layout.addWidget(self._empty_label)

        self._update_empty_state()

        self.setLayout(layout)

    def _connect_signals(self) -> None:
        """Connect internal signals."""
        self._search_input.textChanged.connect(self._on_search_changed)
        self._refresh_btn.clicked.connect(self._refresh)
        self._grid_widget.itemClicked.connect(self._on_item_clicked)
        self._grid_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._grid_widget.customContextMenuRequested.connect(self._show_context_menu)

    def set_library(self, library: SpriteLibrary) -> None:
        """
        Set the sprite library to display.

        Args:
            library: The sprite library to use
        """
        self._library = library

        # Connect library signals
        library.sprite_added.connect(self._on_sprite_added)
        library.sprite_removed.connect(self._on_sprite_removed)
        library.sprite_updated.connect(self._on_sprite_updated)
        library.library_loaded.connect(self._on_library_loaded)

        # Load initial data
        self._refresh()

    def _refresh(self) -> None:
        """Refresh the display from the library."""
        if self._library is None:
            return

        self._current_sprites = self._library.sprites
        self._populate_grid(self._current_sprites)
        self._update_count()

    def _populate_grid(self, sprites: list[LibrarySprite]) -> None:
        """Populate the grid with sprites."""
        self._grid_widget.clear()

        for sprite in sprites:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, sprite.unique_id)
            item.setText(sprite.name)
            item.setToolTip(
                f"Offset: {sprite.offset_hex}\n"
                f"Tags: {', '.join(sprite.tags) if sprite.tags else 'None'}\n"
                f"Notes: {sprite.notes or 'None'}"
            )

            # Load thumbnail if available
            if self._library is not None:
                thumb_path = self._library.get_thumbnail_path(sprite)
                if thumb_path is not None:
                    pixmap = QPixmap(str(thumb_path))
                    if not pixmap.isNull():
                        item.setIcon(QIcon(pixmap))

            self._grid_widget.addItem(item)

        self._update_empty_state()

    def _update_count(self) -> None:
        """Update the sprite count label."""
        count = len(self._current_sprites)
        self._count_label.setText(f"{count} sprite{'s' if count != 1 else ''}")

    def _update_empty_state(self) -> None:
        """Show/hide empty state based on grid contents."""
        has_items = self._grid_widget.count() > 0
        self._grid_widget.setVisible(has_items)
        self._empty_label.setVisible(not has_items)

    def _on_search_changed(self, text: str) -> None:
        """Handle search text changes."""
        if self._library is None:
            return

        if text:
            self._current_sprites = self._library.search(text)
        else:
            self._current_sprites = self._library.sprites

        self._populate_grid(self._current_sprites)
        self._update_count()

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        """Handle single-click on grid item."""
        unique_id = item.data(Qt.ItemDataRole.UserRole)
        if self._library is not None:
            sprite = self._library.get_sprite(unique_id)
            if sprite is not None:
                self.sprite_selected.emit(sprite)

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        """Handle double-click on grid item."""
        unique_id = item.data(Qt.ItemDataRole.UserRole)
        if self._library is not None:
            sprite = self._library.get_sprite(unique_id)
            if sprite is not None:
                self.sprite_activated.emit(sprite)
                self.edit_requested.emit(sprite.rom_offset)

    def _show_context_menu(self, position: QPoint) -> None:
        """Show context menu for grid item."""
        item = self._grid_widget.itemAt(position)
        if item is None:  # type: ignore[reportUnnecessaryComparison]
            return

        unique_id = item.data(Qt.ItemDataRole.UserRole)
        if self._library is None:
            return

        sprite = self._library.get_sprite(unique_id)
        if sprite is None:
            return

        menu = QMenu(self)

        edit_action = menu.addAction("Edit Sprite")
        edit_action.triggered.connect(lambda: self.edit_requested.emit(sprite.rom_offset))

        menu.addSeparator()

        rename_action = menu.addAction("Rename...")
        rename_action.triggered.connect(lambda: self._rename_sprite(sprite))

        menu.addSeparator()

        delete_action = menu.addAction("Delete from Library")
        delete_action.triggered.connect(lambda: self._delete_sprite(sprite))

        menu.exec(self._grid_widget.mapToGlobal(position))

    def _rename_sprite(self, sprite: LibrarySprite) -> None:
        """Show dialog to rename sprite."""
        from PySide6.QtWidgets import QInputDialog

        new_name, ok = QInputDialog.getText(
            self,
            "Rename Sprite",
            "New name:",
            text=sprite.name,
        )
        if ok and new_name and self._library is not None:
            self._library.update_sprite(sprite.unique_id, name=new_name)

    def _delete_sprite(self, sprite: LibrarySprite) -> None:
        """Delete sprite from library with confirmation."""
        from PySide6.QtWidgets import QMessageBox

        result = QMessageBox.question(
            self,
            "Delete Sprite",
            f"Delete '{sprite.name}' from library?\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if result == QMessageBox.StandardButton.Yes and self._library is not None:
            self._library.remove_sprite(sprite.unique_id)

    def _on_sprite_added(self, sprite: object) -> None:
        """Handle sprite added to library."""
        self._refresh()

    def _on_sprite_removed(self, unique_id: str) -> None:
        """Handle sprite removed from library."""
        self._refresh()

    def _on_sprite_updated(self, sprite: object) -> None:
        """Handle sprite updated in library."""
        self._refresh()

    def _on_library_loaded(self, count: int) -> None:
        """Handle library loaded from disk."""
        self._refresh()

    def cleanup(self) -> None:
        """Cleanup resources."""
        self._grid_widget.clear()
