#!/usr/bin/env python3
"""
ROM workflow page combining offset navigation and pixel editing.

This page provides the ROM-based sprite editing workflow:
- Left panel: ROM offset navigation, preview, recent captures
- Right panel: Pixel editing workspace

Unlike the old ROMWorkflowTab, this page owns its own EditWorkspace
instance, eliminating the need for widget reparenting when switching modes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ui.components.panels import RecentCapturesWidget
from ui.styles.theme import COLORS

from ..widgets.source_bar import SourceBar
from .edit_workspace import EditWorkspace

if TYPE_CHECKING:
    from PIL import Image


class ROMWorkflowPage(QWidget):
    """ROM workflow page with navigation panel and editing workspace.

    This page provides the ROM-based sprite editing workflow:
    - Left panel: ROM offset navigation, mini preview, recent captures
    - Right panel: EditWorkspace for pixel editing

    The page owns its own EditWorkspace instance, which shares the
    EditingController with VRAMEditorPage's EditWorkspace. This allows
    mode switching without reparenting widgets.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {COLORS['background']};")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # Set minimum width at page root (nav 250 + workspace 450)
        self.setMinimumWidth(700)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Create the ROM workflow UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 1. Source Bar (Top)
        self._source_bar = SourceBar()
        layout.addWidget(self._source_bar)

        # 2. Main Content (Splitter)
        self._main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._main_splitter.setStyleSheet(
            f"QSplitter::handle {{ background-color: {COLORS['border']}; width: 1px; }}"
        )
        self._main_splitter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._main_splitter.setChildrenCollapsible(False)

        # Left Panel: Offset Browser + Preview
        self._left_panel = self._create_left_panel()
        self._main_splitter.addWidget(self._left_panel)

        # Right Panel: EditWorkspace (owned by this page)
        self._workspace = EditWorkspace()
        # Hide detach button in ROM mode (not applicable)
        self._workspace._detach_btn.hide()
        self._main_splitter.addWidget(self._workspace)

        # Set initial sizes
        self._main_splitter.setSizes([350, 650])
        self._main_splitter.setStretchFactor(0, 0)
        self._main_splitter.setStretchFactor(1, 1)

        layout.addWidget(self._main_splitter, 1)

    def _create_left_panel(self) -> QWidget:
        """Create the left navigation panel."""
        left_panel = QWidget()
        left_panel.setStyleSheet(
            f"background-color: {COLORS['darker_gray']}; border-right: 1px solid {COLORS['border']};"
        )
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(12, 12, 12, 12)
        left_layout.setSpacing(15)

        # Offset Browser group
        browser_group = QFrame()
        browser_group.setStyleSheet(
            f"background-color: {COLORS['panel_background']}; "
            f"border: 1px solid {COLORS['border']}; border-radius: 4px; padding: 10px;"
        )
        browser_layout = QVBoxLayout(browser_group)
        browser_layout.setContentsMargins(10, 10, 10, 10)

        title_label = QLabel("ROM NAVIGATION")
        title_label.setStyleSheet(
            f"color: {COLORS['highlight']}; font-weight: bold; font-size: 10px; letter-spacing: 1px;"
        )
        browser_layout.addWidget(title_label)

        # Offset slider
        self._offset_slider = QSlider(Qt.Orientation.Horizontal)
        self._offset_slider.setMinimum(0)
        self._offset_slider.setMaximum(100)  # Updated when ROM loads
        self._offset_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                border: 1px solid {COLORS["border"]};
                height: 6px;
                background: {COLORS["input_background"]};
                margin: 2px 0;
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: {COLORS["highlight"]};
                border: 1px solid {COLORS["highlight_border"]};
                width: 14px;
                height: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }}
        """)
        browser_layout.addWidget(self._offset_slider)

        # Navigation row
        nav_layout = QHBoxLayout()
        self._prev_btn = QPushButton("◀ Prev")
        self._next_btn = QPushButton("Next ▶")

        button_style = f"""
            QPushButton {{
                background-color: {COLORS["edit"]};
                color: white;
                border-radius: 2px;
                padding: 4px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {COLORS["edit_hover"]};
            }}
        """
        self._prev_btn.setStyleSheet(button_style)
        self._next_btn.setStyleSheet(button_style)

        nav_layout.addWidget(self._prev_btn)
        nav_layout.addWidget(self._next_btn)
        browser_layout.addLayout(nav_layout)

        # Step controls
        step_layout = QHBoxLayout()
        step_layout.addWidget(QLabel("Step:"))
        self._step_spin = QSpinBox()
        self._step_spin.setRange(1, 0x10000)
        self._step_spin.setValue(0x100)
        self._step_spin.setDisplayIntegerBase(16)
        self._step_spin.setPrefix("0x")
        self._step_spin.setStyleSheet(
            f"background-color: {COLORS['input_background']}; border: 1px solid {COLORS['border']};"
        )
        step_layout.addWidget(self._step_spin)
        browser_layout.addLayout(step_layout)

        # Mini Preview
        preview_container = QFrame()
        preview_container.setFrameStyle(QFrame.Shape.StyledPanel)
        preview_container.setMinimumHeight(220)
        preview_container.setStyleSheet(
            f"background-color: {COLORS['preview_background']}; "
            f"border: 1px solid {COLORS['border']}; border-radius: 4px;"
        )

        preview_layout = QVBoxLayout(preview_container)
        preview_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_layout.setContentsMargins(5, 5, 5, 5)

        self._preview_label = QLabel("No Preview")
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setStyleSheet("border: none; background: transparent;")
        preview_layout.addWidget(self._preview_label)

        browser_layout.addWidget(preview_container)

        left_layout.addWidget(browser_group)

        # Recent Captures
        self._recent_captures_widget = RecentCapturesWidget()
        left_layout.addWidget(self._recent_captures_widget, 1)

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
    def offset_slider(self) -> QSlider:
        """Access the offset slider."""
        return self._offset_slider

    @property
    def prev_btn(self) -> QPushButton:
        """Access the previous button."""
        return self._prev_btn

    @property
    def next_btn(self) -> QPushButton:
        """Access the next button."""
        return self._next_btn

    @property
    def step_spin(self) -> QSpinBox:
        """Access the step spinbox."""
        return self._step_spin

    @property
    def preview_label(self) -> QLabel:
        """Access the preview label."""
        return self._preview_label

    @property
    def recent_captures_widget(self) -> RecentCapturesWidget:
        """Access the recent captures widget."""
        return self._recent_captures_widget

    @property
    def main_splitter(self) -> QSplitter:
        """Access the main splitter."""
        return self._main_splitter

    @property
    def left_panel(self) -> QWidget:
        """Access the left panel."""
        return self._left_panel

    def set_rom_size(self, size: int) -> None:
        """Update slider range based on ROM size."""
        self._offset_slider.setMaximum(size - 1)

    def update_preview(self, pil_image: Image.Image) -> None:
        """Update the mini-preview label."""
        # Convert PIL to QPixmap
        if pil_image.mode != "RGBA":
            pil_image = pil_image.convert("RGBA")

        data = pil_image.tobytes("raw", "RGBA")
        qimg = QImage(data, pil_image.width, pil_image.height, QImage.Format.Format_RGBA8888)
        pixmap = QPixmap.fromImage(qimg)

        # Scale for preview if too small
        if pixmap.width() < 128:
            pixmap = pixmap.scaled(
                pixmap.width() * 2,
                pixmap.height() * 2,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )

        self._preview_label.setPixmap(pixmap)
        self._preview_label.setText("")

    def set_workflow_state(self, state: str) -> None:
        """Update UI based on workflow state."""
        if state == "preview":
            self._left_panel.setEnabled(True)
            self._workspace.setEnabled(False)
        elif state == "edit":
            self._left_panel.setEnabled(False)  # Lock offset while editing
            self._workspace.setEnabled(True)
        elif state == "save":
            self._left_panel.setEnabled(False)
            self._workspace.setEnabled(False)
