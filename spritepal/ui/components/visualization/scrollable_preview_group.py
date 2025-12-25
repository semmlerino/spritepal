"""Scrollable preview group widget for displaying images in a scroll area."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QGroupBox, QLabel, QScrollArea, QVBoxLayout, QWidget

from ui.styles.theme import COLORS


class ScrollablePreviewGroup(QGroupBox):
    """Group box with a scrollable centered image label.

    Use for preview areas that need to display images larger than the
    available space, with automatic scrolling support.
    """

    def __init__(
        self,
        title: str = "Preview",
        min_height: int | None = None,
        with_styling: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the scrollable preview group.

        Args:
            title: Title for the group box
            min_height: Minimum height constraint, or None for no constraint
            with_styling: Whether to apply theme styling to the preview label
            parent: Parent widget
        """
        super().__init__(title, parent)

        if min_height is not None:
            self.setMinimumHeight(min_height)

        # Create layout
        layout = QVBoxLayout(self)

        # Create scroll area
        self._scroll_area = QScrollArea(self)
        self._scroll_area.setWidgetResizable(True)

        # Create preview label
        self._preview_label = QLabel(self)
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        if with_styling:
            self._preview_label.setStyleSheet(
                f"background-color: {COLORS['background']}; "
                f"border: 1px solid {COLORS['border']};"
            )

        self._scroll_area.setWidget(self._preview_label)
        layout.addWidget(self._scroll_area)

    @property
    def preview_label(self) -> QLabel:
        """Access the preview label for direct manipulation."""
        return self._preview_label

    def set_pixmap(self, pixmap: QPixmap) -> None:
        """Display a pixmap in the preview area.

        Args:
            pixmap: The pixmap to display
        """
        self._preview_label.setPixmap(pixmap)

    def clear_preview(self, fallback_text: str = "") -> None:
        """Clear the preview and optionally show fallback text.

        Args:
            fallback_text: Text to display when preview is cleared
        """
        self._preview_label.clear()
        if fallback_text:
            self._preview_label.setText(fallback_text)
