#!/usr/bin/env python3
"""
ROM workflow page combining asset browser and pixel editing.

This page provides the ROM-based sprite editing workflow:
- Left panel: SpriteAssetBrowser with searchable thumbnails
- Right panel: Pixel editing workspace

Unlike the old ROMWorkflowTab, this page owns its own EditWorkspace
instance, eliminating the need for widget reparenting when switching modes.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QLabel,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ui.common.spacing_constants import SPACING_STANDARD
from utils.constants import RomMappingType

from ..widgets.source_bar import SourceBar
from ..widgets.sprite_asset_browser import SpriteAssetBrowser
from .edit_workspace import EditWorkspace


class ROMWorkflowPage(QWidget):
    """ROM workflow page with asset browser and editing workspace.

    This page provides the ROM-based sprite editing workflow:
    - Left panel: SpriteAssetBrowser for navigating available sprites
    - Right panel: EditWorkspace for pixel editing

    The page owns its own EditWorkspace instance, which shares the
    EditingController with VRAMEditorPage's EditWorkspace. This allows
    mode switching without reparenting widgets.
    """

    # Forward signals from asset browser
    offset_changed = Signal(int)
    sprite_selected = Signal(int, str)  # offset, source_type
    sprite_activated = Signal(int, str)  # offset, source_type
    local_file_selected = Signal(str, str)  # path, name
    local_file_activated = Signal(str, str)  # path, name

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Create the ROM workflow UI with flat 3-pane splitter."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 1. Source Bar (Top)
        self._source_bar = SourceBar()
        self._source_bar.offset_changed.connect(self.offset_changed.emit)
        layout.addWidget(self._source_bar)

        # 2. Create EditWorkspace in embedded mode (widgets only, no layout)
        self._workspace = EditWorkspace(embed_mode="embedded")
        self._workspace.set_workflow_mode("rom")
        # Hide detach button in ROM mode (not applicable)
        self._workspace._detach_btn.hide()

        # 3. Icon toolbar from workspace
        layout.addWidget(self._workspace.icon_toolbar)

        # 4. Main Content: Flat 3-pane splitter
        # [Asset Browser | Canvas | Right Panels]
        self._main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._main_splitter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._main_splitter.setChildrenCollapsible(False)

        # Pane 0: Asset Browser
        self._left_panel = self._create_left_panel()
        self._main_splitter.addWidget(self._left_panel)

        # Pane 1: Canvas (from workspace)
        self._main_splitter.addWidget(self._workspace.scroll_area)

        # Pane 2: Right panels (from workspace)
        self._main_splitter.addWidget(self._workspace.right_panel_scroll)

        # Set initial sizes: [350 asset browser, 700 canvas, 250 panels]
        self._main_splitter.setSizes([350, 700, 250])
        self._main_splitter.setStretchFactor(0, 0)  # Asset browser: fixed
        self._main_splitter.setStretchFactor(1, 1)  # Canvas: stretches
        self._main_splitter.setStretchFactor(2, 0)  # Right panels: fixed

        layout.addWidget(self._main_splitter, 1)

        # 5. Status bar from workspace (bottom)
        layout.addWidget(self._workspace.status_bar)

    def _create_left_panel(self) -> QWidget:
        """Create the left panel with asset browser."""
        left_panel = QWidget()
        # Object name handles background and border via global theme
        left_panel.setObjectName("leftNavPanel")

        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(SPACING_STANDARD, SPACING_STANDARD, SPACING_STANDARD, SPACING_STANDARD)
        left_layout.setSpacing(SPACING_STANDARD)

        # Title banner
        title_label = QLabel("SPRITE & ASSET BROWSER")
        title_label.setObjectName("panelTitle")
        title_label.setStyleSheet("font-weight: bold; font-size: 12px; padding: 4px 0px;")
        left_layout.addWidget(title_label)

        # Asset Browser (fills entire left panel)
        self._asset_browser = SpriteAssetBrowser()

        # Forward signals from asset browser
        self._asset_browser.sprite_selected.connect(self.sprite_selected.emit)
        self._asset_browser.sprite_activated.connect(self.sprite_activated.emit)
        self._asset_browser.local_file_selected.connect(self.local_file_selected.emit)
        self._asset_browser.local_file_activated.connect(self.local_file_activated.emit)

        left_layout.addWidget(self._asset_browser, 1)

        return left_panel

    # Public accessors
    @property
    def workspace(self) -> EditWorkspace:
        """Access the editing workspace."""
        return self._workspace

    @property
    def source_bar(self) -> SourceBar:
        """Access the source bar."""
        return self._source_bar

    @property
    def asset_browser(self) -> SpriteAssetBrowser:
        """Access the sprite asset browser."""
        return self._asset_browser

    @property
    def main_splitter(self) -> QSplitter:
        """Access the main splitter."""
        return self._main_splitter

    @property
    def left_panel(self) -> QWidget:
        """Access the left panel."""
        return self._left_panel

    def set_workflow_state(self, state: str) -> None:
        """Update UI based on workflow state."""
        if state == "preview":
            self._left_panel.setEnabled(True)
            self._workspace.setEnabled(False)
        elif state == "edit":
            # Keep left panel enabled so user can browse other sprites while editing
            # Selecting a different sprite will prompt to save unsaved changes
            self._left_panel.setEnabled(True)
            self._workspace.setEnabled(True)
        elif state == "save":
            self._left_panel.setEnabled(False)
            self._workspace.setEnabled(False)

    # =========================================================================
    # Delegation methods for SourceBar
    # =========================================================================

    def set_rom_available(self, available: bool, rom_size: int = 0) -> None:
        """Update ROM availability state in source bar."""
        self._source_bar.set_rom_available(available, rom_size)

    def set_rom_path(self, path: str) -> None:
        """Set ROM file path in source bar."""
        self._source_bar.set_rom_path(path)

    def set_info(self, text: str) -> None:
        """Set info text in source bar."""
        self._source_bar.set_info(text)

    def set_checksum_valid(self, valid: bool) -> None:
        """Set checksum validity in source bar."""
        self._source_bar.set_checksum_valid(valid)

    def set_offset(self, offset: int, source_type: str | None = None) -> None:
        """Update displayed ROM offset in source bar and asset browser selection.

        Args:
            offset: ROM offset to display.
            source_type: Optional source type for precise selection ("rom", "mesen", "library").
                        If provided, selects matching offset AND source_type.
                        If None, falls back to offset-only matching.
        """
        self._source_bar.set_offset(offset)
        # Synchronize asset browser selection with composite identity
        if source_type:
            self._asset_browser.select_sprite(offset, source_type)
        else:
            # Fallback: offset-only matching (backwards compatibility)
            self._asset_browser.select_sprite_by_offset(offset)

    def set_mapping_type(self, mapping_type: RomMappingType) -> None:
        """Set ROM mapping type for SNES address conversion in source bar."""
        self._source_bar.set_mapping_type(mapping_type)

    def set_header_offset(self, offset: int) -> None:
        """Set SMC header offset (e.g. 512 bytes) for file-to-ROM offset conversion."""
        self._source_bar.set_header_offset(offset)

    def set_action_text(self, text: str) -> None:
        """Set action button text in source bar."""
        self._source_bar.set_action_text(text)

    def set_action_loading(self, loading: bool) -> None:
        """Set action button loading state in source bar."""
        self._source_bar.set_action_loading(loading)

    def set_modified_indicator(self, modified: bool) -> None:
        """Show or hide the unsaved changes indicator in the source bar.

        Args:
            modified: True if there are unsaved changes.
        """
        self._source_bar.set_modified(modified)

    # =========================================================================
    # Delegation methods for SpriteAssetBrowser
    # =========================================================================

    def set_thumbnail(self, offset: int, pixmap: QPixmap, source_type: str | None = None) -> None:
        """Set thumbnail for a sprite in asset browser.

        Args:
            offset: ROM offset of the sprite.
            pixmap: Thumbnail image.
            source_type: Optional filter - only update this source type
                        ("rom", "mesen", "library"). If None, updates all.
        """
        self._asset_browser.set_thumbnail(offset, pixmap, source_type)

    def add_rom_sprite(self, name: str, offset: int) -> None:
        """Add a ROM sprite to the asset browser."""
        self._asset_browser.add_rom_sprite(name, offset)

    def add_mesen_capture(self, name: str, offset: int, frame: int | None = None) -> None:
        """Add a Mesen capture to the asset browser."""
        self._asset_browser.add_mesen_capture(name, offset, frame=frame)

    def add_library_sprite(self, name: str, offset: int, thumbnail: QPixmap | None = None) -> None:
        """Add a library sprite to the asset browser."""
        self._asset_browser.add_library_sprite(name, offset, thumbnail=thumbnail)

    def clear_asset_browser(self) -> None:
        """Clear all items from asset browser."""
        self._asset_browser.clear_all()

    def clear_rom_palette_sources(self) -> None:
        """Clear ROM palette sources from the workspace palette panel."""
        if self._workspace and self._workspace.palette_panel:
            self._workspace.palette_panel.clear_rom_sources()

    def show_palette_warning(self, message: str) -> None:
        """Show a warning banner in the palette panel.

        Args:
            message: Warning message to display
        """
        if self._workspace and self._workspace.palette_panel:
            self._workspace.palette_panel.show_palette_warning(message)

    def hide_palette_warning(self) -> None:
        """Hide the palette warning banner."""
        if self._workspace and self._workspace.palette_panel:
            self._workspace.palette_panel.hide_palette_warning()
