"""
Consolidated UI coordinator for MainWindow preview, session, and tab operations.

This module merges PreviewCoordinator, SessionCoordinator, and TabCoordinator
into a single class to reduce file count and boilerplate.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QLabel,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ui.common.spacing_constants import (
    MIN_PANEL_WIDTH,
    PALETTE_GROUP_MAX_HEIGHT,
    PALETTE_GROUP_MIN_HEIGHT,
    PREVIEW_GROUP_MIN_HEIGHT,
)
from ui.styles import get_muted_text_style

if TYPE_CHECKING:
    from core.managers.application_state_manager import ApplicationStateManager
    from ui.extraction_panel import ExtractionPanel
    from ui.main_window import MainWindow
    from ui.managers.output_settings_manager import OutputSettingsManager
    from ui.managers.toolbar_manager import ToolbarManager
    from ui.palette_preview import PalettePreviewWidget
    from ui.rom_extraction_panel import ROMExtractionPanel
    from ui.zoomable_preview import PreviewPanel


class UICoordinator(QObject):
    """Coordinates UI preview, session, and tab operations for MainWindow.

    This class consolidates functionality from:
    - PreviewCoordinator: Sprite and palette preview widgets
    - SessionCoordinator: Session save/restore operations
    - TabCoordinator: Tab switching and state synchronization
    """

    # Signal from TabCoordinator
    tab_changed = Signal(int)  # tab index

    def __init__(
        self,
        # Preview dependencies
        sprite_preview: PreviewPanel,
        palette_preview: PalettePreviewWidget,
        # Session dependencies
        main_window: MainWindow,
        extraction_panel: ExtractionPanel,
        output_settings_manager: OutputSettingsManager,
        session_manager: ApplicationStateManager,
        # Tab dependencies
        extraction_tabs: QTabWidget,
        rom_extraction_panel: ROMExtractionPanel,
        toolbar_manager: ToolbarManager,
        actions_handler: MainWindow,
    ) -> None:
        """Initialize the consolidated UI coordinator.

        Args:
            sprite_preview: Sprite preview widget
            palette_preview: Palette preview widget
            main_window: Main window for geometry save/restore
            extraction_panel: VRAM extraction panel for file path save/restore
            output_settings_manager: Output settings for save/restore
            session_manager: Injected ApplicationStateManager instance
            extraction_tabs: Tab widget containing extraction tabs
            rom_extraction_panel: ROM extraction panel widget
            toolbar_manager: Toolbar manager
            actions_handler: Handler for tab coordination actions
        """
        super().__init__()

        # Preview state
        self.sprite_preview = sprite_preview
        self.palette_preview = palette_preview
        self.preview_info = QLabel("No sprites loaded")
        self.preview_info.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Session state
        self.main_window = main_window
        self.extraction_panel = extraction_panel
        self.output_settings_manager = output_settings_manager
        self.session_manager = session_manager

        # Tab state
        self.extraction_tabs = extraction_tabs
        self.rom_extraction_panel = rom_extraction_panel
        self.toolbar_manager = toolbar_manager
        self.actions_handler = actions_handler

        # Layout state
        self._saved_splitter_sizes: list[int] = []

        self._connect_signals()

    def _connect_signals(self) -> None:
        """Connect tab change signals"""
        self.extraction_tabs.currentChanged.connect(self._on_extraction_tab_changed)

    # =========================================================================
    # Preview Methods (from PreviewCoordinator)
    # =========================================================================

    def create_preview_panel(self, parent: QWidget) -> QWidget:
        """Create and configure the preview panel.

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

        preview_layout.addWidget(self.sprite_preview, 1)  # Give stretch factor to expand

        # Configure preview info label
        self.preview_info.setStyleSheet(get_muted_text_style())
        self.preview_info.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
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
        preview_group.setMinimumHeight(PREVIEW_GROUP_MIN_HEIGHT)
        palette_group.setMinimumHeight(PALETTE_GROUP_MIN_HEIGHT)
        palette_group.setMaximumHeight(PALETTE_GROUP_MAX_HEIGHT)

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
        """Update preview info message.

        Args:
            message: Message to display
        """
        if self.preview_info:
            self.preview_info.setText(message)

    # =========================================================================
    # Session Methods (from SessionCoordinator)
    # =========================================================================

    def restore_session(self) -> bool:
        """Restore the previous session."""
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

    def save_session(self) -> None:
        """Save the current session"""
        # Get session data from extraction panel
        session_data = self.extraction_panel.get_session_data()

        # Add output settings
        session_data.update(
            {
                "output_name": self.output_settings_manager.get_output_name(),
                "create_grayscale": self.output_settings_manager.get_grayscale_enabled(),
                "create_metadata": self.output_settings_manager.get_metadata_enabled(),
            }
        )

        # Save session data
        self.session_manager.update_session_data(session_data)

        # Save UI settings including splitter positions
        window_geometry: dict[str, int | float | list[int]] = {
            "width": self.main_window.width(),
            "height": self.main_window.height(),
            "x": self.main_window.x(),
            "y": self.main_window.y(),
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

    # =========================================================================
    # Tab Methods (from TabCoordinator)
    # =========================================================================

    def _on_extraction_tab_changed(self, index: int) -> None:
        """Handle tab change between extraction tabs.

        Args:
            index: New tab index (0=ROM, 1=VRAM, 2=Sprite Editor)
        """
        if index == 0:
            self._configure_rom_extraction_tab()
        elif index == 1:
            self._configure_vram_extraction_tab()
        elif index == 2:
            self._configure_sprite_editor_tab()

        # Emit signal for other components
        self.tab_changed.emit(index)

    def _configure_rom_extraction_tab(self) -> None:
        """Configure UI for ROM extraction tab"""
        self._restore_toolbar_state()

        # Check extraction readiness
        params = self.actions_handler.get_rom_extraction_params()
        if params is not None:
            self.toolbar_manager.set_extract_enabled(True)
        else:
            self.toolbar_manager.set_extract_enabled(False, "Load a ROM file")

        # Sync output name from ROM panel to main output field
        if params and params.get("output_base"):
            self.output_settings_manager.set_output_name(params["output_base"])

        # Configure output settings for ROM mode
        self.output_settings_manager.set_rom_extraction_mode()

    def _configure_vram_extraction_tab(self) -> None:
        """Configure UI for VRAM extraction tab"""
        self._restore_toolbar_state()

        # Check extraction readiness based on mode
        ready = self.actions_handler.is_vram_extraction_ready()
        if ready:
            self.toolbar_manager.set_extract_enabled(True)
        else:
            self.toolbar_manager.set_extract_enabled(False, "Load VRAM file")

        # Update output info label
        is_grayscale_mode = self.actions_handler.is_grayscale_mode()
        self.output_settings_manager.update_output_info_label(is_vram_tab=True, is_grayscale_mode=is_grayscale_mode)

        # Update checkbox states based on mode
        self.output_settings_manager.set_extraction_mode_options(is_grayscale_mode)

        # Configure output settings for VRAM mode
        self.output_settings_manager.set_vram_extraction_mode()

    def _configure_sprite_editor_tab(self) -> None:
        """Configure UI for Sprite Editor tab"""
        # Disable main Extract button - the editor has its own extract controls
        self.toolbar_manager.set_extract_enabled(False, "Use editor's Extract")

        # Clarify workflow: Rename Open Editor -> Open External, Disable Inject
        self.toolbar_manager.set_open_editor_button_label("Open External")
        self.toolbar_manager.set_inject_button_enabled(False)

    def _restore_toolbar_state(self) -> None:
        """Restore toolbar state when leaving editor tab"""
        self.toolbar_manager.set_open_editor_button_label("Open Editor")
        # Restore inject button state to match open editor button (both enabled after extraction)
        is_enabled = self.toolbar_manager.open_editor_button.isEnabled()
        self.toolbar_manager.set_inject_button_enabled(is_enabled)


    def get_current_tab_index(self) -> int:
        """Get current active tab index"""
        return self.extraction_tabs.currentIndex()

    def is_rom_tab_active(self) -> bool:
        """Check if ROM extraction tab is active"""
        return self.get_current_tab_index() == 0

    def is_vram_tab_active(self) -> bool:
        """Check if VRAM extraction tab is active"""
        return self.get_current_tab_index() == 1

    def is_sprite_editor_tab_active(self) -> bool:
        """Check if Sprite Editor tab is active"""
        return self.get_current_tab_index() == 2

    def switch_to_rom_tab(self) -> None:
        """Switch to ROM extraction tab"""
        if self.extraction_tabs:
            self.extraction_tabs.setCurrentIndex(0)

    def switch_to_vram_tab(self) -> None:
        """Switch to VRAM extraction tab"""
        if self.extraction_tabs:
            self.extraction_tabs.setCurrentIndex(1)

    def switch_to_sprite_editor_tab(self) -> None:
        """Switch to Sprite Editor tab"""
        if self.extraction_tabs:
            self.extraction_tabs.setCurrentIndex(2)
