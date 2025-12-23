"""
Session coordination for MainWindow save/restore functionality
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QObject

# SessionManager accessed via DI: inject(ApplicationStateManager)

if TYPE_CHECKING:
    from core.managers.application_state_manager import ApplicationStateManager
    from ui.extraction_panel import ExtractionPanel
    from ui.main_window import MainWindow
    from ui.managers.output_settings_manager import OutputSettingsManager

class SessionCoordinator(QObject):
    """Coordinates session save/restore operations"""

    def __init__(
        self,
        main_window: MainWindow,
        extraction_panel: ExtractionPanel,
        output_settings_manager: OutputSettingsManager,
        session_manager: ApplicationStateManager,
    ) -> None:
        """Initialize session coordinator

        Args:
            main_window: Main window for geometry save/restore
            extraction_panel: Extraction panel for file path save/restore
            output_settings_manager: Output settings for save/restore
            session_manager: Injected ApplicationStateManager instance
        """
        super().__init__()

        self.main_window = main_window
        self.extraction_panel = extraction_panel
        self.output_settings_manager = output_settings_manager
        self.session_manager = session_manager

    def restore_session(self) -> bool:
        """Restore the previous session"""
        # Validate file paths
        session_data: dict[str, Any] = dict(self.session_manager.get_session_data())  # pyright: ignore[reportExplicitAny] - session state
        validated_paths = {}

        for key in ["vram_path", "cgram_path", "oam_path"]:
            path = session_data.get(key, "")
            if path and Path(path).exists():
                validated_paths[key] = path
            else:
                validated_paths[key] = ""

        # Check if there's a valid session to restore
        has_valid_session = bool(validated_paths.get("vram_path") or validated_paths.get("cgram_path"))

        if has_valid_session:
            # Restore file paths
            self.extraction_panel.restore_session_files(validated_paths)

            # Restore output settings
            if session_data.get("output_name"):
                self.output_settings_manager.set_output_name(session_data["output_name"])

            self.output_settings_manager.set_grayscale_enabled(session_data.get("create_grayscale", True))
            self.output_settings_manager.set_metadata_enabled(session_data.get("create_metadata", True))

        # Always restore window size/position if enabled (regardless of session validity)
        self._restore_window_geometry()

        return has_valid_session

    def _restore_window_geometry(self) -> None:
        """Restore window geometry if enabled in settings"""

        session_manager = self.session_manager
        if session_manager.get("ui", "restore_position", False):
            window_geometry: dict[str, Any] = dict(self.session_manager.get_window_geometry())  # pyright: ignore[reportExplicitAny] - window state

            # Extract scalar values with type narrowing
            width_val = window_geometry.get("width")
            height_val = window_geometry.get("height")
            x_val = window_geometry.get("x")
            y_val = window_geometry.get("y")

            # Safely get values ensuring int type
            width = width_val if isinstance(width_val, int) else 0
            height = height_val if isinstance(height_val, int) else 0
            x = x_val if isinstance(x_val, int) else None
            y = y_val if isinstance(y_val, int) else None

            if width > 0 and height > 0:
                self.main_window.resize(width, height)

            if x is not None and y is not None and x >= 0:
                self.main_window.move(x, y)

            # Restore splitter sizes if available
            splitter_sizes = window_geometry.get("splitter_sizes", [])
            if isinstance(splitter_sizes, list) and len(splitter_sizes) >= 2:
                self.main_window.main_splitter.setSizes(splitter_sizes)

    def save_session(self) -> None:
        """Save the current session"""
        # Get session data from extraction panel
        session_data = self.extraction_panel.get_session_data()

        # Add output settings
        session_data.update({
            "output_name": self.output_settings_manager.get_output_name(),
            "create_grayscale": self.output_settings_manager.get_grayscale_enabled(),
            "create_metadata": self.output_settings_manager.get_metadata_enabled(),
        })

        # Save session data
        self.session_manager.update_session_data(session_data)

        # Save UI settings including splitter positions
        window_geometry: dict[str, int | float | list[int]] = {
            "width": self.main_window.width(),
            "height": self.main_window.height(),
            "x": self.main_window.x(),
            "y": self.main_window.y(),
            "splitter_sizes": self.main_window.main_splitter.sizes(),
        }
        self.session_manager.update_window_state(window_geometry)

        # Save the session to disk
        self.session_manager.save_session()

    def clear_session(self) -> None:
        """Clear session data"""
        self.session_manager.clear_session()

    def get_session_data(self) -> dict[str, Any]:  # pyright: ignore[reportExplicitAny] - Session state dict
        """Get current session data"""
        return dict(self.session_manager.get_session_data())
