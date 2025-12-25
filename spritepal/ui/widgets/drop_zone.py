"""
Reusable file drop zone widget.

A drag-and-drop zone for file input with visual state feedback,
status badges (Required/Optional/Loaded), and browse button.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, override

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from PySide6.QtGui import (
        QColor,
        QDragEnterEvent,
        QDragLeaveEvent,
        QDropEvent,
        QPainter,
        QPaintEvent,
        QPen,
    )

    from core.managers.application_state_manager import ApplicationStateManager
else:
    from PySide6.QtGui import (
        QColor,
        QDragEnterEvent,
        QDragLeaveEvent,
        QDropEvent,
        QPainter,
        QPaintEvent,
        QPen,
    )

from ui.common.file_dialogs import browse_for_open_file
from ui.common.spacing_constants import (
    BORDER_THICK,
    BROWSE_BUTTON_MAX_WIDTH,
    CHECKMARK_OFFSET,
    CIRCLE_INDICATOR_MARGIN,
    CIRCLE_INDICATOR_SIZE,
    DROP_ZONE_MIN_HEIGHT,
    LINE_THICK,
    SPACING_SMALL,
    SPACING_TINY,
    TOGGLE_BUTTON_SIZE,
)
from ui.styles import (
    get_drop_zone_badge_style,
    get_drop_zone_style,
    get_link_text_style,
    get_muted_text_style,
    get_success_text_style,
)
from ui.styles.theme import COLORS


class DropZone(QWidget):
    """Drag and drop zone for file input with visual state feedback.

    Features:
    - Drag and drop file support
    - Browse button for file selection
    - Required/Optional status badge
    - Clear button when file is loaded
    - Path display with full path tooltip

    Signals:
        file_dropped: Emitted when a file is set or cleared (str path)
    """

    file_dropped = Signal(str)

    def __init__(
        self,
        file_type: str,
        parent: QWidget | None = None,
        *,
        settings_manager: ApplicationStateManager,
        required: bool = True,
        file_filter: str | None = None,
    ) -> None:
        """Initialize the drop zone.

        Args:
            file_type: Type of file (e.g., "VRAM", "CGRAM", "OAM")
            parent: Parent widget
            settings_manager: Application state manager for settings access
            required: Whether this file is required
            file_filter: Optional file filter for browse dialog
        """
        super().__init__(parent)
        self.file_type = file_type
        self.file_path = ""
        self._required = required
        self._file_filter = file_filter or f"{file_type} Files (*.dmp);;All Files (*)"
        self.setAcceptDrops(True)
        self.setMinimumHeight(DROP_ZONE_MIN_HEIGHT)

        # Apply initial styling based on required state
        self._update_style()

        # Store injected dependency
        self.settings_manager = settings_manager

        # Layout
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(SPACING_TINY)

        # Top row with badge
        top_row = QHBoxLayout()
        top_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top_row.setSpacing(SPACING_SMALL)

        # Status badge (Required/Optional/Loaded)
        self.status_badge = QLabel("Required" if required else "Optional")
        self._update_badge_style()
        top_row.addWidget(self.status_badge)

        layout.addLayout(top_row)

        # Icon and label
        self.label = QLabel(f"Drop {file_type} file here")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if self.label:
            self.label.setStyleSheet(get_muted_text_style(color_level="light"))
        layout.addWidget(self.label)

        # File path row with clear button
        path_row = QHBoxLayout()
        path_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        path_row.setSpacing(SPACING_TINY)

        self.path_label = QLabel("")
        self.path_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if self.path_label:
            self.path_label.setStyleSheet(get_link_text_style("extract"))
        self.path_label.setWordWrap(True)
        path_row.addWidget(self.path_label)

        # Clear button - small "×" to clear file selection  # noqa: RUF003
        self.clear_btn = QPushButton("×")  # noqa: RUF001
        self.clear_btn.setFixedSize(TOGGLE_BUTTON_SIZE, TOGGLE_BUTTON_SIZE)
        self.clear_btn.setToolTip("Clear selected file")
        self.clear_btn.setStyleSheet(
            f"""
            QPushButton {{
                border: none;
                border-radius: 10px;
                background-color: {COLORS["text_muted"]};
                color: white;
                font-weight: bold;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {COLORS["danger"]};
            }}
            """
        )
        _ = self.clear_btn.clicked.connect(self.clear)
        self.clear_btn.setVisible(False)
        path_row.addWidget(self.clear_btn)

        layout.addLayout(path_row)

        # Browse button
        self.browse_button = QPushButton("Browse")
        self.browse_button.setMaximumWidth(BROWSE_BUTTON_MAX_WIDTH)
        _ = self.browse_button.clicked.connect(self._browse_file)
        layout.addWidget(self.browse_button, alignment=Qt.AlignmentFlag.AlignCenter)

    def _update_style(self) -> None:
        """Update the drop zone styling based on current state."""
        if self.file_path:
            self.setStyleSheet(get_drop_zone_style("loaded"))
        else:
            self.setStyleSheet(get_drop_zone_style("empty", required=self._required))

    def _update_badge_style(self) -> None:
        """Update the badge styling based on current state."""
        if self.file_path:
            self.status_badge.setText("✓ Loaded")
            self.status_badge.setStyleSheet(get_drop_zone_badge_style("loaded"))
        elif self._required:
            self.status_badge.setText("Required")
            self.status_badge.setStyleSheet(get_drop_zone_badge_style("required"))
        else:
            self.status_badge.setText("Optional")
            self.status_badge.setStyleSheet(get_drop_zone_badge_style("optional"))

    def set_required(self, required: bool) -> None:
        """Update whether this drop zone is required.

        Args:
            required: Whether the file is required
        """
        self._required = required
        self._update_style()
        self._update_badge_style()

    @override
    def dragEnterEvent(self, event: QDragEnterEvent | None) -> None:
        """Handle drag enter events."""
        if event:
            mime_data = event.mimeData()
            if mime_data and mime_data.hasUrls():
                event.acceptProposedAction()
                self.setStyleSheet(get_drop_zone_style("hover"))

    @override
    def dragLeaveEvent(self, event: QDragLeaveEvent | None) -> None:
        """Handle drag leave events."""
        # Restore appropriate style based on current state
        self._update_style()

    @override
    def dropEvent(self, event: QDropEvent | None) -> None:
        """Handle drop events."""
        if event:
            mime_data = event.mimeData()
            if mime_data:
                files = [url.toLocalFile() for url in mime_data.urls()]
                if files:
                    self.set_file(files[0])
        self.dragLeaveEvent(None)  # Just reset the style

    @override
    def paintEvent(self, event: QPaintEvent | None) -> None:
        """Custom paint event to show loaded status indicator."""
        if event:
            super().paintEvent(event)

        if self.file_path:
            # Draw green checkmark indicator
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            # Draw circle
            painter.setPen(QPen(QColor(16, 124, 65), BORDER_THICK))
            painter.setBrush(QColor(16, 124, 65, 30))
            painter.drawEllipse(
                self.width() - CIRCLE_INDICATOR_MARGIN,
                CHECKMARK_OFFSET,
                CIRCLE_INDICATOR_SIZE,
                CIRCLE_INDICATOR_SIZE,
            )

            # Draw checkmark
            painter.setPen(QPen(QColor(16, 124, 65), LINE_THICK))
            painter.drawLine(self.width() - 28, 22, self.width() - 23, 27)
            painter.drawLine(self.width() - 23, 27, self.width() - 15, 19)

    def _browse_file(self) -> None:
        """Browse for file using file dialog."""
        filename = browse_for_open_file(
            self, f"Select {self.file_type} File", self._file_filter
        )

        if filename:
            self.set_file(filename)

    def set_file(self, file_path: str) -> None:
        """Set the file path.

        Args:
            file_path: Path to the file to load
        """
        if Path(file_path).exists():
            self.file_path = file_path
            if self.label:
                self.label.setText(f"✓ {self.file_type}")
            if self.label:
                self.label.setStyleSheet(get_success_text_style())

            # Show filename with full path in tooltip
            filename = Path(file_path).name
            if self.path_label:
                self.path_label.setText(filename)
                self.path_label.setToolTip(file_path)  # Full path on hover

            # Show clear button
            if self.clear_btn:
                self.clear_btn.setVisible(True)

            # Update visual state
            self._update_style()
            self._update_badge_style()

            self.file_dropped.emit(file_path)
            self.update()  # Trigger repaint

    def clear(self) -> None:
        """Clear the current file."""
        old_path = self.file_path
        self.file_path = ""
        if self.label:
            self.label.setText(f"Drop {self.file_type} file here")
        if self.label:
            self.label.setStyleSheet(get_muted_text_style(color_level="light"))
        if self.path_label:
            self.path_label.setText("")
            self.path_label.setToolTip("")  # Clear tooltip

        # Hide clear button
        if self.clear_btn:
            self.clear_btn.setVisible(False)

        # Update visual state
        self._update_style()
        self._update_badge_style()

        self.update()

        # Emit file_dropped signal with empty path to trigger UI updates
        if old_path:
            self.file_dropped.emit("")

    def has_file(self) -> bool:
        """Check if a file is loaded.

        Returns:
            True if a file is loaded
        """
        return bool(self.file_path)

    def get_file_path(self) -> str:
        """Get the current file path.

        Returns:
            The current file path, or empty string if none loaded
        """
        return self.file_path
