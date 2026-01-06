"""
Workflow navigation bar for VRAM Editor.
Displays steps (Extract -> Edit -> Inject) as a breadcrumb/stepper.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from ui.styles.theme import COLORS, DIMENSIONS, FONTS


class WorkflowNavBar(QWidget):
    """
    Navigation bar showing workflow steps.
    Replaces tabs with a visual stepper.
    """

    step_selected = Signal(int)

    def __init__(self, steps: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._steps = steps
        self._current_index = 0
        self._buttons: list[QPushButton] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(DIMENSIONS["spacing_md"], DIMENSIONS["spacing_sm"], DIMENSIONS["spacing_md"], DIMENSIONS["spacing_sm"])
        layout.setSpacing(DIMENSIONS["spacing_md"])

        for i, step_name in enumerate(self._steps):
            # Create button for step
            btn = QPushButton(f"{i + 1}. {step_name}")
            btn.setCheckable(True)
            # Use lambda with default arg to capture loop variable
            btn.clicked.connect(lambda checked=False, idx=i: self.step_selected.emit(idx))
            
            layout.addWidget(btn)
            self._buttons.append(btn)
            
            # Add separator if not last
            if i < len(self._steps) - 1:
                sep = QLabel("→")
                sep.setStyleSheet(f"color: {COLORS['text_muted']}; font-weight: bold; font-size: {FONTS['large_size']};")
                layout.addWidget(sep)
        
        layout.addStretch()
        self.set_current_step(0)

    def set_current_step(self, index: int) -> None:
        """Set the active step index."""
        if 0 <= index < len(self._buttons):
            self._current_index = index
            for i, btn in enumerate(self._buttons):
                self._update_button_style(btn, i == index)

    def _update_button_style(self, btn: QPushButton, active: bool) -> None:
        """Update button style based on active state."""
        if active:
            # Active step style (highlighted)
            bg = COLORS["border_focus"]
            fg = COLORS["white"]
            border = COLORS["border_focus"]
        else:
            # Inactive step style (muted)
            bg = COLORS["panel_background"]
            fg = COLORS["text_secondary"]
            border = COLORS["border"]

        # Minimal inline style for custom stepper look
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                color: {fg};
                border: 1px solid {border};
                border-radius: {DIMENSIONS["border_radius"]}px;
                padding: 6px 12px;
                font-weight: bold;
                text-align: center;
                min-width: 80px;
            }}
            QPushButton:hover {{
                background-color: {COLORS["surface_hover"]};
                border-color: {COLORS["border_focus"]};
            }}
        """)
