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
from PySide6.QtWidgets import (
    QLabel,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ui.common.spacing_constants import SPACING_STANDARD

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

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Create the ROM workflow UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 1. Source Bar (Top)
        self._source_bar = SourceBar()
        self._source_bar.offset_changed.connect(self.offset_changed.emit)
        layout.addWidget(self._source_bar)

        # 2. Main Content (Splitter)
        self._main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._main_splitter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._main_splitter.setChildrenCollapsible(False)

        # Left Panel: Asset Browser
        self._left_panel = self._create_left_panel()
        self._main_splitter.addWidget(self._left_panel)

        # Right Panel: EditWorkspace (owned by this page)
        self._workspace = EditWorkspace()
        self._workspace.set_workflow_mode("rom")
        # Hide detach button in ROM mode (not applicable)
        self._workspace._detach_btn.hide()
        self._main_splitter.addWidget(self._workspace)

        # Set initial sizes
        self._main_splitter.setSizes([350, 650])
        self._main_splitter.setStretchFactor(0, 0)
        self._main_splitter.setStretchFactor(1, 1)

        layout.addWidget(self._main_splitter, 1)

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
            self._left_panel.setEnabled(False)  # Lock browser while editing
            self._workspace.setEnabled(True)
        elif state == "save":
            self._left_panel.setEnabled(False)
            self._workspace.setEnabled(False)
