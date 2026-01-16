"""Base widget class for ROM extraction widgets"""

from __future__ import annotations

from PySide6.QtCore import Qt, SignalInstance
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.common.collapsible_group_box import CollapsibleGroupBox
from ui.common.spacing_constants import (
    CONTROL_PANEL_LABEL_WIDTH,
    EXTRACTION_BUTTON_MIN_HEIGHT as BUTTON_MIN_HEIGHT,
    PATH_EDIT_MIN_WIDTH,
    SPACING_COMPACT_SMALL,
    SPACING_MEDIUM,
)
from ui.styles.theme import COLORS


class BaseExtractionWidget(QWidget):
    """Base class for extraction panel widgets with common functionality.

    Subclasses should call _setup_widget_with_group() in _setup_ui() for
    consistent layout pattern:

    def _setup_ui(self) -> None:
        inner_layout = QHBoxLayout()
        inner_layout.setSpacing(SPACING_MEDIUM)
        # ... add widgets to inner_layout ...
        self._setup_widget_with_group("Group Title", inner_layout)
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

    def _create_control_label(self, text: str) -> QLabel:
        """Create a control label with consistent styling.

        Args:
            text: The label text

        Returns:
            QLabel with standard width and right-aligned text
        """
        label = QLabel(text)
        label.setMinimumWidth(CONTROL_PANEL_LABEL_WIDTH)
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return label

    def _create_readonly_path_edit(self, placeholder: str) -> QLineEdit:
        """Create read-only path edit with consistent styling.

        Args:
            placeholder: Placeholder text to display when empty

        Returns:
            QLineEdit configured as read-only with standard width
        """
        edit = QLineEdit()
        edit.setPlaceholderText(placeholder)
        edit.setReadOnly(True)
        edit.setMinimumWidth(PATH_EDIT_MIN_WIDTH)
        return edit

    def _create_browse_button(self, signal: SignalInstance | None = None, tooltip: str = "") -> QPushButton:
        """Create browse button with consistent sizing.

        Args:
            signal: Optional signal to connect to clicked event
            tooltip: Optional tooltip text

        Returns:
            QPushButton with standard sizing for browse actions
        """
        btn = QPushButton("Browse...")
        btn.setMinimumHeight(BUTTON_MIN_HEIGHT)
        btn.setMinimumWidth(90)  # Fits "Browse..." text
        btn.setMaximumWidth(120)  # Prevents over-expansion
        if tooltip:
            btn.setToolTip(tooltip)
        if signal is not None:
            _ = btn.clicked.connect(signal.emit)
        return btn

    def _create_vbox_layout(self) -> QVBoxLayout:
        """Create VBoxLayout with standard spacing and margins.

        Returns:
            QVBoxLayout with SPACING_MEDIUM spacing and zero margins
        """
        layout = QVBoxLayout()
        layout.setSpacing(SPACING_MEDIUM)
        layout.setContentsMargins(0, 0, 0, 0)
        return layout

    def _create_hbox_layout(self) -> QHBoxLayout:
        """Create HBoxLayout with standard spacing and margins.

        Returns:
            QHBoxLayout with SPACING_MEDIUM spacing and zero margins
        """
        layout = QHBoxLayout()
        layout.setSpacing(SPACING_MEDIUM)
        layout.setContentsMargins(0, 0, 0, 0)
        return layout

    def _setup_widget_with_group(self, title: str, inner_layout: QLayout) -> None:
        """Set up the widget with a standard outer layout and group box.

        Args:
            title: The group box title
            inner_layout: The layout containing the widget's content
        """
        # Create outer layout
        outer_layout = QVBoxLayout()
        outer_layout.setContentsMargins(0, 0, 0, 0)

        # Create group box with inner layout
        group = self._create_group_box(title)
        group.setLayout(inner_layout)
        outer_layout.addWidget(group)

        self.setLayout(outer_layout)

    def _create_group_box(self, title: str) -> QGroupBox:
        """Create a group box with minimal styling (no borders for cleaner look).

        Internal layouts should use setContentsMargins(0,0,0,0) since
        the group box CSS provides all necessary padding.
        """
        group = QGroupBox(title)
        # Minimal styling - no borders to reduce visual noise
        # Only the title provides section separation
        # Note: margin-top creates space for title when subcontrol-origin: margin
        group.setStyleSheet(f"""
            QGroupBox {{
                font-weight: bold;
                color: {COLORS["text_secondary"]};
                margin-top: 12px;
                padding-top: 8px;
                padding-left: 0px;
                padding-right: 0px;
                padding-bottom: 4px;
                border: none;
                background-color: transparent;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 0px;
                top: 0px;
                padding: 0 {SPACING_COMPACT_SMALL}px 0 0px;
            }}
        """)
        group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        return group

    def _setup_widget_flat(self, inner_layout: QLayout, with_separator: bool = True) -> None:
        """Set up the widget with a flat layout (no group box wrapper).

        Use this for header-style sections that don't need visual boxing.

        Args:
            inner_layout: The layout containing the widget's content
            with_separator: If True, adds bottom margin for visual separation
        """
        # Create outer layout with appropriate spacing
        outer_layout = QVBoxLayout()
        outer_layout.setContentsMargins(0, 0, 0, SPACING_MEDIUM if with_separator else 0)
        outer_layout.setSpacing(0)

        # Add inner layout directly without container wrapper
        outer_layout.addLayout(inner_layout)

        self.setLayout(outer_layout)

    def _setup_widget_collapsible(
        self, title: str, inner_layout: QLayout, collapsed: bool = True, muted: bool = False
    ) -> CollapsibleGroupBox:
        """Set up the widget with a collapsible group box wrapper.

        Use this for optional sections that can be hidden by default.

        Args:
            title: The group box title
            inner_layout: The layout containing the widget's content
            collapsed: Whether to start collapsed (default True)
            muted: Whether to use subdued styling for optional sections (default False)

        Returns:
            The CollapsibleGroupBox instance for external control
        """
        outer_layout = QVBoxLayout()
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # Create collapsible group box
        collapsible = CollapsibleGroupBox(title=title, collapsed=collapsed, muted=muted, parent=self)
        collapsible.add_layout(inner_layout)
        outer_layout.addWidget(collapsible)

        self.setLayout(outer_layout)
        return collapsible
