#!/usr/bin/env python3
"""
Edit tab for the unified sprite editor.

This is a thin wrapper around EditWorkspace that provides backward
compatibility with existing code expecting the EditTab interface.
The actual editing UI lives in EditWorkspace.
"""

from typing import TYPE_CHECKING

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..workspaces import EditWorkspace

if TYPE_CHECKING:
    from ...controllers.editing_controller import EditingController
    from ..panels import PalettePanel, PreviewPanel
    from ..widgets import IconToolbar, PixelCanvas


class EditTab(QWidget):
    """Tab widget for pixel editing functionality.

    Thin wrapper around EditWorkspace that maintains backward compatibility.
    The workspace can be embedded in both VRAM mode (via this wrapper)
    and ROM mode (directly in ROMWorkflowPage).
    """

    # Signals (forwarded from workspace)
    detach_requested = Signal()
    image_modified = Signal()
    ready_for_inject = Signal()
    saveProjectRequested = Signal()
    loadProjectRequested = Signal()

    def __init__(
        self,
        controller: "EditingController | None" = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._setup_ui()
        # Ensure EditTab expands to fill parent (critical for ROM mode container)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def _setup_ui(self) -> None:
        """Create the edit tab UI with embedded workspace."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Create the workspace
        self._workspace = EditWorkspace()
        layout.addWidget(self._workspace, 1)

        # Forward workspace signals to tab signals
        self._workspace.detach_requested.connect(self.detach_requested.emit)
        self._workspace.image_modified.connect(self.image_modified.emit)
        self._workspace.ready_for_inject.connect(self.ready_for_inject.emit)
        self._workspace.saveProjectRequested.connect(self.saveProjectRequested.emit)
        self._workspace.loadProjectRequested.connect(self.loadProjectRequested.emit)

    @property
    def workspace(self) -> EditWorkspace:
        """Access the underlying EditWorkspace."""
        return self._workspace

    # Delegate panel access to workspace
    @property
    def icon_toolbar(self) -> "IconToolbar":
        """Access the icon toolbar (replaced tool panel)."""
        return self._workspace.icon_toolbar

    @property
    def palette_panel(self) -> "PalettePanel":
        """Access the palette panel."""
        return self._workspace.palette_panel

    @property
    def preview_panel(self) -> "PreviewPanel":
        """Access the preview panel."""
        return self._workspace.preview_panel

    @property
    def scroll_area(self) -> "QWidget":
        """Access the canvas scroll area."""
        return self._workspace.scroll_area

    @property
    def canvas_layout(self) -> "QVBoxLayout":
        """Access the canvas layout."""
        return self._workspace.canvas_layout

    @property
    def controller(self) -> "EditingController | None":
        """Get the current controller."""
        return self._workspace.controller

    @controller.setter
    def controller(self, value: "EditingController | None") -> None:
        """Set the controller (for backward compatibility)."""
        self._controller = value

    # Delegate canvas methods to workspace
    def get_canvas(self) -> "PixelCanvas | None":
        """Get the pixel canvas widget."""
        return self._workspace.get_canvas()

    def set_canvas(self, canvas: "PixelCanvas") -> None:
        """Set the pixel canvas widget."""
        self._workspace.set_canvas(canvas)

    def set_controller(self, controller: "EditingController") -> None:
        """Set the editing controller, create canvas, and connect signals."""
        self._controller = controller
        self._workspace.set_controller(controller)

    def update_from_controller(self) -> None:
        """Update UI state from controller."""
        self._workspace.update_from_controller()

    def set_palette(self, colors: list[tuple[int, int, int]], name: str = "") -> None:
        """Update the displayed palette."""
        self._workspace.set_palette(colors, name)

    def set_image_loaded(self, loaded: bool) -> None:
        """Enable/disable editing controls based on image state."""
        self._workspace.set_image_loaded(loaded)

    # Backward compatibility: expose buttons for tests that check them
    @property
    def detach_btn(self) -> "QWidget":
        """Access detach button (for tests)."""
        return self._workspace._detach_btn

    @property
    def inject_btn(self) -> "QWidget":
        """Access inject button (for tests)."""
        return self._workspace._inject_btn
