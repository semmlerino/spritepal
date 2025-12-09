"""
Preview coordination for MainWindow sprite and palette previews
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Qt
from PySide6.QtWidgets import (
    QGroupBox,
    QLabel,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ui.styles import get_muted_text_style

if TYPE_CHECKING:
    from ui.palette_preview import PalettePreviewWidget
    from ui.zoomable_preview import PreviewPanel

class PreviewCoordinator(QObject):
    """Coordinates sprite and palette preview widgets"""

    def __init__(
        self,
        sprite_preview: PreviewPanel,
        palette_preview: PalettePreviewWidget
    ) -> None:
        """Initialize preview coordinator

        Args:
            sprite_preview: Sprite preview widget
            palette_preview: Palette preview widget
        """
        super().__init__()
        self.sprite_preview = sprite_preview
        self.palette_preview = palette_preview

        # Initialize preview info label immediately for backward compatibility
        # This will be reconfigured in create_preview_panel() if that method is called
        self.preview_info = QLabel("No sprites loaded")
        self.preview_info.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def create_preview_panel(self, parent: QWidget) -> QWidget:
        """Create and configure the preview panel

        Args:
            parent: Parent widget

        Returns:
            Configured preview panel widget
        """
        # Create vertical splitter for right panel
        right_splitter = QSplitter(Qt.Orientation.Vertical)

        # Extraction preview group
        preview_group = QGroupBox("Extraction Preview")
        preview_layout = QVBoxLayout()

        preview_layout.addWidget(
            self.sprite_preview, 1
        )  # Give stretch factor to expand

        # Configure existing preview info label (created in __init__)
        self.preview_info.setStyleSheet(get_muted_text_style())
        self.preview_info.setStyleSheet(get_muted_text_style())
        self.preview_info.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum
        )
        preview_layout.addWidget(self.preview_info, 0)  # No stretch factor

        preview_group.setLayout(preview_layout)
        right_splitter.addWidget(preview_group)

        # Palette preview group
        palette_group = QGroupBox("Palette Preview")
        palette_layout = QVBoxLayout()
        palette_layout.addWidget(self.palette_preview)
        palette_group.setLayout(palette_layout)
        right_splitter.addWidget(palette_group)

        # Configure splitter with better proportions
        right_splitter.setSizes([500, 100])  # Much smaller palette area
        right_splitter.setStretchFactor(0, 4)  # Preview panel gets most space
        right_splitter.setStretchFactor(1, 0)  # Palette panel fixed size

        # Set minimum sizes - more compact
        preview_group.setMinimumHeight(200)
        palette_group.setMinimumHeight(80)
        palette_group.setMaximumHeight(120)  # Limit palette height

        return right_splitter

    def clear_previews(self) -> None:
        """Clear both sprite and palette previews"""
        if self.sprite_preview:
            self.sprite_preview.clear()
        if self.palette_preview:
            self.palette_preview.clear()
        if self.preview_info:
            self.preview_info.setText("No sprites loaded")

    def update_preview_info(self, message: str) -> None:
        """Update preview info message

        Args:
            message: Message to display
        """
        if self.preview_info:
            self.preview_info.setText(message)
