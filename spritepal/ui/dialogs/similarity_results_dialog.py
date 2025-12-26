"""
Dialog for displaying visual similarity search results.

Shows similar sprites with thumbnails, similarity scores, and allows navigation.
"""

from __future__ import annotations

from typing import Any, override

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.visual_similarity_search import SimilarityMatch
from ui.common.spacing_constants import SPACING_COMPACT_MEDIUM, SPACING_SMALL, SPACING_TINY, THUMBNAIL_SIZE
from ui.components import DialogBase
from ui.styles.theme import COLORS
from utils.logging_config import get_logger

logger = get_logger(__name__)


class SimilarityResultWidget(QFrame):
    """Widget displaying a single similarity search result."""

    sprite_selected = Signal(int)  # Emitted when sprite is selected

    def __init__(self, match: SimilarityMatch, thumbnail: QPixmap | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.match = match
        self.thumbnail = thumbnail

        self.setFrameStyle(QFrame.Shape.Box)
        # Use dark theme colors for consistency
        self.setStyleSheet(f"""
            SimilarityResultWidget {{
                border: 2px solid {COLORS["border"]};
                border-radius: 8px;
                background-color: {COLORS["panel_background"]};
                color: {COLORS["text_primary"]};
                margin: 4px;
                padding: 8px;
            }}
            SimilarityResultWidget:hover {{
                border-color: {COLORS["highlight"]};
                background-color: {COLORS["focus_background"]};
                color: {COLORS["text_primary"]};
            }}
        """)

        self._setup_ui()

    def _setup_ui(self):
        """Setup the UI for this result widget."""
        layout = QVBoxLayout()
        layout.setContentsMargins(SPACING_SMALL, SPACING_SMALL, SPACING_SMALL, SPACING_SMALL)
        layout.setSpacing(SPACING_TINY)

        # Thumbnail
        thumbnail_label = QLabel()
        if self.thumbnail and not self.thumbnail.isNull():
            # Scale thumbnail to reasonable size
            scaled_thumbnail = self.thumbnail.scaled(
                THUMBNAIL_SIZE,
                THUMBNAIL_SIZE,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            thumbnail_label.setPixmap(scaled_thumbnail)
        else:
            thumbnail_label.setText("No preview")
            thumbnail_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-style: italic;")

        thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumbnail_label.setMinimumSize(THUMBNAIL_SIZE, THUMBNAIL_SIZE)
        layout.addWidget(thumbnail_label)

        # Offset
        offset_label = QLabel(f"0x{self.match.offset:06X}")
        offset_label.setStyleSheet(f"font-family: monospace; font-weight: bold; color: {COLORS['border_focus']};")
        offset_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(offset_label)

        # Similarity score
        score_text = f"Score: {self.match.similarity_score:.2f}"
        score_label = QLabel(score_text)
        score_label.setStyleSheet(f"font-size: 11px; color: {COLORS['text_muted']};")
        score_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(score_label)

        # Hash distance
        distance_text = f"Distance: {self.match.hash_distance}"
        distance_label = QLabel(distance_text)
        distance_label.setStyleSheet(f"font-size: 10px; color: {COLORS['text_muted']};")
        distance_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(distance_label)

        # Select button
        select_btn = QPushButton("Go to Sprite")
        select_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS["highlight"]};
                color: {COLORS["text_primary"]};
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: {COLORS["highlight_hover"]};
            }}
            QPushButton:pressed {{
                background-color: {COLORS["browse_pressed"]};
            }}
        """)
        select_btn.clicked.connect(lambda: self.sprite_selected.emit(self.match.offset))
        layout.addWidget(select_btn)

        self.setLayout(layout)

    @override
    def mousePressEvent(self, event: Any):  # pyright: ignore[reportExplicitAny] - Qt mouse event
        """Handle mouse clicks to select sprite."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.sprite_selected.emit(self.match.offset)
        super().mousePressEvent(event)


class SimilarityResultsDialog(DialogBase):
    """Dialog showing visual similarity search results."""

    sprite_selected = Signal(int)  # Emitted when user selects a sprite

    def __init__(self, matches: list[SimilarityMatch], source_offset: int, parent: QWidget | None = None):
        # Declare instance variables before super().__init__()
        self.matches = matches
        self.source_offset = source_offset

        super().__init__(
            parent=parent,
            title="Similar Sprites Found",
            modal=True,
            min_size=(600, 400),
            size=(800, 600),
            with_button_box=False,  # We'll create our own close button
        )

    @override
    def _setup_ui(self):
        """Setup the dialog UI - called by BaseDialog."""
        layout = QVBoxLayout()

        # Header
        header_text = f"Found {len(self.matches)} sprites similar to 0x{self.source_offset:06X}"
        header_label = QLabel(header_text)
        header_label.setStyleSheet("font-size: 14px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(header_label)

        if not self.matches:
            # No results found
            no_results_label = QLabel(
                "No similar sprites found.\n\nTry adjusting the similarity threshold or ensuring more sprites are indexed."
            )
            no_results_label.setStyleSheet(
                f"color: {COLORS['text_muted']}; font-style: italic; text-align: center; margin: 40px;"
            )
            no_results_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(no_results_label)
        else:
            # Results grid in scroll area
            scroll_area = QScrollArea()
            scroll_area.setWidgetResizable(True)
            scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

            # Grid widget
            grid_widget = QWidget()
            grid_layout = QGridLayout(grid_widget)
            grid_layout.setSpacing(SPACING_COMPACT_MEDIUM)

            # Add results in grid (3 columns)
            cols = 3
            for i, match in enumerate(self.matches):
                row = i // cols
                col = i % cols

                # Create result widget
                result_widget = SimilarityResultWidget(match)
                result_widget.sprite_selected.connect(self._on_sprite_selected)

                grid_layout.addWidget(result_widget, row, col)

            # Add stretch to push everything to top
            grid_layout.setRowStretch(grid_layout.rowCount(), 1)

            scroll_area.setWidget(grid_widget)
            layout.addWidget(scroll_area)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

        # Set layout on content widget (BaseDialog pattern)
        self.content_widget.setLayout(layout)

    def _on_sprite_selected(self, offset: int):
        """Handle sprite selection."""
        self.sprite_selected.emit(offset)
        self.accept()  # Close dialog after selection


def show_similarity_results(
    matches: list[SimilarityMatch], source_offset: int, parent: QWidget | None = None
) -> SimilarityResultsDialog:
    """
    Convenience function to show similarity results dialog.

    Args:
        matches: List of similar sprites found
        source_offset: Offset of the source sprite
        parent: Parent widget

    Returns:
        The created dialog instance
    """
    return SimilarityResultsDialog(matches, source_offset, parent)
