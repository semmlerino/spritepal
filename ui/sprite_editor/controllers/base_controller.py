#!/usr/bin/env python3
"""
Base controller class for MVC pattern.
Provides common functionality for all controllers.
"""

from typing import Any

from PySide6.QtCore import QObject


class BaseController(QObject):
    """Base class for controllers in MVC pattern."""

    def __init__(
        self,
        model: Any | None = None,  # type: ignore[reportExplicitAny]
        view: Any | None = None,  # type: ignore[reportExplicitAny]
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._model = model
        self._view = view

        if model and view:
            self.connect_signals()

    def set_model(self, model: Any) -> None:  # type: ignore[reportExplicitAny]
        """Set the model for this controller."""
        self._model = model
        if self._model and self._view:
            self.connect_signals()

    def set_view(self, view: Any) -> None:  # type: ignore[reportExplicitAny]
        """Set the view for this controller."""
        self._view = view
        if self._model and self._view:
            self.connect_signals()

    def connect_signals(self) -> None:
        """Connect signals between model and view (to be overridden)."""
        pass

    @property
    def model(self) -> Any:  # type: ignore[reportExplicitAny]
        """Get the associated model."""
        return self._model

    @property
    def view(self) -> Any:  # type: ignore[reportExplicitAny]
        """Get the associated view."""
        return self._view
