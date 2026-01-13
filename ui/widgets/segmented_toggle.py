"""
Segmented toggle widget for switching between modes/views.
"""

from __future__ import annotations

from typing import cast

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QPushButton, QWidget

from ui.styles.components import get_segmented_button_style


class SegmentedToggle(QWidget):
    """
    A segmented control widget that acts like a radio button group.

    Displays a row of connected buttons where only one can be active at a time.
    """

    # Signal emitted when selection changes, carrying the data associated with the option
    selection_changed = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._group.buttonClicked.connect(self._on_button_clicked)

        self._buttons: list[QPushButton] = []
        self._data: dict[QPushButton, object] = {}

    def add_option(self, label: str, data: object, checked: bool = False) -> None:
        """Add an option to the segmented control."""
        btn = QPushButton(label)
        btn.setCheckable(True)
        btn.setCursor(self.cursor())

        self._layout.addWidget(btn)
        self._group.addButton(btn)
        self._buttons.append(btn)
        self._data[btn] = data

        if checked:
            btn.setChecked(True)

        self._update_styles()

    def _update_styles(self) -> None:
        """Update styles for all buttons based on position and state."""
        count = len(self._buttons)
        for i, btn in enumerate(self._buttons):
            position = "middle"
            if count == 1:
                position = "only"
            elif i == 0:
                position = "first"
            elif i == count - 1:
                position = "last"

            # Note: We rely on the stylesheet to handle checked/unchecked visual changes
            # but we need to re-apply if we change properties that affect style logic
            # However, for pure CSS pseudo-states (:checked), we might not need to re-set
            # the stylesheet on every click if the CSS covers it.
            # But our get_segmented_button_style helper takes 'checked' as arg to burn in colors
            # for stronger control. So we should update on state change.
            # Actually, standard CSS :checked selector is better for performance.
            # Let's check get_segmented_button_style implementation.
            # It uses :checked pseudo-class AND takes a 'checked' arg.
            # To avoid re-setting stylesheet constantly, let's just set it once with the position
            # and let :checked handle the rest.

            # Wait, get_segmented_button_style uses the 'checked' python arg to determine
            # base colors, which duplicates :checked logic.
            # Ideally, we generated one stylesheet that covers both states.
            # Let's use 'checked=False' to get the base style which includes :checked rules.
            btn.setStyleSheet(get_segmented_button_style(position, checked=False))

    def _on_button_clicked(self, btn: QPushButton) -> None:
        """Handle button click."""
        data = self._data.get(btn)
        self.selection_changed.emit(data)

    def current_data(self) -> object:
        """Get data of currently selected option."""
        btn = self._group.checkedButton()
        # checkedButton returns QAbstractButton, but we only added QPushButtons
        return self._data.get(cast(QPushButton, btn))

    def set_current_data(self, data: object) -> None:
        """Set the currently selected option by data."""
        current = self.current_data()
        if current == data:
            return

        for btn, btn_data in self._data.items():
            if btn_data == data:
                btn.setChecked(True)
                # QButtonGroup doesn't emit buttonClicked on programmatic change
                self.selection_changed.emit(data)
                return

    def set_tooltip(self, data: object, tooltip: str) -> None:
        """Set the tooltip for an option by its data."""
        for btn, btn_data in self._data.items():
            if btn_data == data:
                btn.setToolTip(tooltip)
                return
