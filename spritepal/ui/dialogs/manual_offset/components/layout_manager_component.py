"""
Layout Manager Component

Enhanced layout management with superior visual design for composed implementation.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from PySide6.QtWidgets import QSplitter, QWidget

from ui.dialogs.manual_offset_layout_manager import (
    LayoutManager as OriginalLayoutManager,
)
from utils.logging_config import get_logger

from .enhanced_layout_component import EnhancedLayoutComponent

if TYPE_CHECKING:
    from ui.dialogs.manual_offset.core.manual_offset_dialog_core import (
        ManualOffsetDialogCore,
    )

logger = get_logger(__name__)

class LayoutManagerComponent:
    """
    Layout manager that chooses enhanced or legacy layout based on implementation.

    For composed implementation: Uses modern enhanced layout with better spacing,
    proportions, and responsive behavior.

    For legacy implementation: Uses existing layout manager.
    """

    # Constants for compatibility with the existing dialog code
    MAX_MINI_MAP_HEIGHT = 50  # Mini ROM map height
    MIN_MINI_MAP_HEIGHT = 30  # Mini ROM map minimum height
    MIN_LEFT_PANEL_WIDTH = 380  # Minimum left panel width

    def __init__(self, dialog: ManualOffsetDialogCore):
        """Initialize the layout manager component."""
        self.dialog = dialog

        # Determine which layout manager to use
        use_enhanced = self._should_use_enhanced_layout()

        if use_enhanced:
            logger.debug("Using enhanced layout manager for superior visual design")
            self._enhanced_layout = EnhancedLayoutComponent(dialog)
            self._layout_manager = None
        else:
            logger.debug("Using legacy layout manager")
            self._layout_manager = OriginalLayoutManager(dialog)  # type: ignore[arg-type]  # ManualOffsetDialogCore implements required interface
            self._enhanced_layout = None

    def _should_use_enhanced_layout(self) -> bool:
        """Determine if we should use enhanced layout."""
        # Use enhanced layout when using composed dialogs
        flag_value = os.environ.get('SPRITEPAL_USE_COMPOSED_DIALOGS', '0').lower()
        return flag_value in ('1', 'true', 'yes', 'on')

    def configure_splitter(self, splitter: QSplitter, left_panel: QWidget, right_panel: QWidget) -> None:
        """Configure the main splitter."""
        if self._enhanced_layout:
            # Enhanced layout handles splitter configuration differently
            if splitter:
                self._enhanced_layout._configure_enhanced_splitter(splitter)
            # Also apply enhanced layout to panels (with null checks)
            if left_panel:
                self._enhanced_layout.enhance_panel_layout(left_panel, "left")
            if right_panel:
                self._enhanced_layout.enhance_panel_layout(right_panel, "right")
        elif self._layout_manager:
            self._layout_manager.configure_splitter(splitter, left_panel, right_panel)

    def fix_empty_space_issue(self) -> None:
        """Fix empty space issue in left panel."""
        if self._enhanced_layout:
            # Enhanced layout applies modern design
            self._enhanced_layout.create_enhanced_layout()
        elif self._layout_manager:
            self._layout_manager.fix_empty_space_issue()

    def on_dialog_show(self) -> None:
        """Handle dialog show event."""
        if self._enhanced_layout:
            # Apply enhanced sizing when dialog is shown
            self._enhanced_layout._apply_enhanced_sizing()
        elif self._layout_manager:
            self._layout_manager.on_dialog_show()

    def handle_resize(self, width: int) -> None:
        """Handle dialog resize."""
        if self._enhanced_layout:
            # Enhanced responsive resize handling
            self._enhanced_layout.handle_dialog_resize(width, self.dialog.height())
        elif self._layout_manager:
            self._layout_manager.handle_resize(width)

    def update_for_tab(self, tab_index: int, dialog_width: int = 0) -> None:
        """Update splitter sizes based on active tab."""
        if self._enhanced_layout:
            # Enhanced tab-specific proportions
            self._enhanced_layout.update_for_tab(tab_index)
        elif self._layout_manager:
            self._layout_manager.update_for_tab(tab_index, dialog_width or self.dialog.width())

    def create_section_header(self, title: str, subtitle: str = "") -> QWidget:
        """Create a section header (enhanced layout only)."""
        if self._enhanced_layout:
            return self._enhanced_layout.create_section_header(title, subtitle)
        # Fallback for legacy - simple label
        from PySide6.QtWidgets import QLabel
        label = QLabel(title)
        if subtitle:
            label.setText(f"{title}\n{subtitle}")
        return label

    def apply_standard_layout(self, layout: Any, spacing_type: str = 'normal') -> None:
        """Apply standard layout with enhanced spacing if using enhanced layout."""
        if self._enhanced_layout:
            # Enhanced layout applies improved spacing
            if spacing_type == 'compact':
                layout.setSpacing(self._enhanced_layout.constants.COMPACT_SPACING)
                layout.setContentsMargins(
                    self._enhanced_layout.constants.COMPACT_MARGINS,
                    self._enhanced_layout.constants.COMPACT_MARGINS,
                    self._enhanced_layout.constants.COMPACT_MARGINS,
                    self._enhanced_layout.constants.COMPACT_MARGINS
                )
            else:
                layout.setSpacing(self._enhanced_layout.constants.SECONDARY_SPACING)
                layout.setContentsMargins(
                    self._enhanced_layout.constants.PANEL_MARGINS,
                    self._enhanced_layout.constants.PANEL_MARGINS,
                    self._enhanced_layout.constants.PANEL_MARGINS,
                    self._enhanced_layout.constants.PANEL_MARGINS
                )
        elif self._layout_manager:
            # Delegate to legacy layout manager
            self._layout_manager.apply_standard_layout(layout, spacing_type)

    def remove_all_stretches(self, layout: Any) -> None:
        """Remove all stretch factors from layout (for compatibility)."""
        if self._enhanced_layout:
            # Enhanced layout handles stretches automatically
            pass
        elif self._layout_manager:
            # Delegate to legacy layout manager
            self._layout_manager.remove_all_stretches(layout)

    def create_section_title(self, title: str, subtitle: str = "") -> Any:
        """Create a section title (compatibility method)."""
        if self._enhanced_layout:
            # Use enhanced header creation
            return self._enhanced_layout.create_section_header(title, subtitle)
        # Delegate to legacy layout manager (only supports title, ignore subtitle)
        return self._layout_manager.create_section_title(title) if self._layout_manager else None

    def cleanup(self) -> None:
        """Clean up layout manager resources."""
        logger.debug("Cleaning up layout manager component")
        if self._enhanced_layout:
            self._enhanced_layout.cleanup()
        # No specific cleanup needed for legacy layout manager
