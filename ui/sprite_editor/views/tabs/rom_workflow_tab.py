#!/usr/bin/env python3
"""
ROM Workflow Tab for the Sprite Editor.
Combines ROM navigation, preview, and editing in a single unified interface.
"""

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

from ui.styles.theme import COLORS

from ..widgets.source_bar import SourceBar

if TYPE_CHECKING:
    from PIL import Image

    from .edit_tab import EditTab


class ROMWorkflowTab(QWidget):
    """
    Unified ROM workflow interface.
    """

    def __init__(self, edit_tab: "EditTab", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.edit_tab = edit_tab
        self.setStyleSheet(f"background-color: {COLORS['background']};")
        self.setMinimumSize(600, 400)  # Ensure tab has minimum size
        # Ensure widget expands to fill available space
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 1. Source Bar (Top)
        self.source_bar = SourceBar()
        layout.addWidget(self.source_bar)

        # 2. Main Content (Splitter)
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setStyleSheet(f"QSplitter::handle {{ background-color: {COLORS['border']}; width: 1px; }}")
        self.main_splitter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.main_splitter.setChildrenCollapsible(False)

        # Left Panel: Offset Browser + Preview
        self.left_panel = QWidget()
        self.left_panel.setStyleSheet(
            f"background-color: {COLORS['darker_gray']}; border-right: 1px solid {COLORS['border']};"
        )
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(12, 12, 12, 12)
        left_layout.setSpacing(15)

        # Offset Browser group
        browser_group = QFrame()
        browser_group.setStyleSheet(
            f"background-color: {COLORS['panel_background']}; border: 1px solid {COLORS['border']}; border-radius: 4px; padding: 10px;"
        )
        browser_layout = QVBoxLayout(browser_group)
        browser_layout.setContentsMargins(10, 10, 10, 10)

        title_label = QLabel("ROM NAVIGATION")
        title_label.setStyleSheet(
            f"color: {COLORS['highlight']}; font-weight: bold; font-size: 10px; letter-spacing: 1px;"
        )
        browser_layout.addWidget(title_label)

        self.offset_slider = QSlider(Qt.Orientation.Horizontal)
        self.offset_slider.setMinimum(0)
        self.offset_slider.setMaximum(100)  # Updated when ROM loads
        self.offset_slider.setStyleSheet(f"""
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
        browser_layout.addWidget(self.offset_slider)

        # Navigation row
        nav_layout = QHBoxLayout()
        self.prev_btn = QPushButton("◀ Prev")
        self.next_btn = QPushButton("Next ▶")

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
        self.prev_btn.setStyleSheet(button_style)
        self.next_btn.setStyleSheet(button_style)

        nav_layout.addWidget(self.prev_btn)
        nav_layout.addWidget(self.next_btn)
        browser_layout.addLayout(nav_layout)

        # Step controls
        step_layout = QHBoxLayout()
        step_layout.addWidget(QLabel("Step:"))
        self.step_spin = QSpinBox()
        self.step_spin.setRange(1, 0x10000)
        self.step_spin.setValue(0x100)
        self.step_spin.setDisplayIntegerBase(16)
        self.step_spin.setPrefix("0x")
        self.step_spin.setStyleSheet(
            f"background-color: {COLORS['input_background']}; border: 1px solid {COLORS['border']};"
        )
        step_layout.addWidget(self.step_spin)
        browser_layout.addLayout(step_layout)

        # Mini Preview
        preview_container = QFrame()
        preview_container.setFrameStyle(QFrame.Shape.StyledPanel)
        preview_container.setMinimumHeight(220)
        preview_container.setStyleSheet(
            f"background-color: {COLORS['preview_background']}; border: 1px solid {COLORS['border']}; border-radius: 4px;"
        )

        self.preview_layout = QVBoxLayout(preview_container)
        self.preview_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_layout.setContentsMargins(5, 5, 5, 5)

        self.preview_label = QLabel("No Preview")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setStyleSheet("border: none; background: transparent;")
        self.preview_layout.addWidget(self.preview_label)

        browser_layout.addWidget(preview_container)

        left_layout.addWidget(browser_group)

        # Recent Captures
        from ui.components.panels import RecentCapturesWidget

        self.recent_captures_widget = RecentCapturesWidget()
        left_layout.addWidget(self.recent_captures_widget, 1)

        self.main_splitter.addWidget(self.left_panel)

        # Right Panel: Editor (existing EditTab)
        self.edit_tab_container = QWidget()
        self.edit_tab_container.setMinimumWidth(400)  # Ensure container has minimum size
        self.edit_tab_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.edit_tab_layout = QVBoxLayout(self.edit_tab_container)
        self.edit_tab_layout.setContentsMargins(0, 0, 0, 0)
        self.edit_tab_layout.setSpacing(0)

        self.main_splitter.addWidget(self.edit_tab_container)

        # Set initial sizes
        self.main_splitter.setSizes([350, 650])
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)

        # Add splitter with stretch factor to fill available vertical space
        layout.addWidget(self.main_splitter, 1)

    def set_rom_size(self, size: int) -> None:
        """Update slider range."""
        self.offset_slider.setMaximum(size - 1)

    def update_preview(self, pil_image: "Image.Image") -> None:
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

        self.preview_label.setPixmap(pixmap)
        self.preview_label.setText("")

    def set_workflow_state(self, state: str) -> None:
        """Update UI based on workflow state."""
        if state == "preview":
            self.left_panel.setEnabled(True)
            self.edit_tab_container.setEnabled(False)
        elif state == "edit":
            self.left_panel.setEnabled(False)  # Lock offset while editing
            self.edit_tab_container.setEnabled(True)
        elif state == "save":
            self.left_panel.setEnabled(False)
            self.edit_tab_container.setEnabled(False)
