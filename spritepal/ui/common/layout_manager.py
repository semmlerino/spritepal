"""
Layout management utilities for consistent UI patterns in SpritePal.

This module provides standardized layout patterns and utilities to prevent
common layout issues like unwanted empty spaces, incorrect stretch behaviors,
and inconsistent spacing across the application.

Best Practices Enforced:
1. Remove all stretch factors from splitters to prevent empty space
2. Use consistent spacing from spacing_constants module
3. Apply appropriate size policies to prevent unwanted expansion
4. Configure layouts with proper margins and spacing
5. Handle tab-specific layout requirements
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLayout,
    QSizePolicy,
    QSpacerItem,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .spacing_constants import (
    GROUP_PADDING,
    PANEL_PADDING,
    SPACING_LARGE,
    SPACING_MEDIUM,
    SPACING_SMALL,
    SPACING_TINY,
    TAB_CONTENT_PADDING,
    TAB_SECTION_SPACING,
)


class LayoutManager:
    """
    Centralized layout management for consistent UI patterns.

    This class provides static methods for applying standardized layout
    configurations, spacing, and size policies across the application.
    Helps prevent common layout issues and ensures visual consistency.
    """

    @staticmethod
    def apply_compact_layout(widget: QWidget) -> None:
        """
        Apply compact layout settings to a widget.

        Removes stretches, sets tight spacing, and configures size policies
        for compact display. Ideal for toolbars, control panels, and dense layouts.

        Args:
            widget: Widget whose layout should be made compact
        """
        layout = widget.layout()
        if layout is None:
            return

        # Remove all stretches first
        LayoutManager.remove_all_stretches(layout)

        # Set compact spacing and margins
        layout.setContentsMargins(SPACING_SMALL, SPACING_SMALL,
                                  SPACING_SMALL, SPACING_SMALL)
        layout.setSpacing(SPACING_TINY)

        # Set compact size policy
        LayoutManager.set_size_policies(widget, QSizePolicy.Policy.Preferred,
                                       QSizePolicy.Policy.Minimum)

    @staticmethod
    def apply_standard_layout(widget: QWidget) -> None:
        """
        Apply standard layout settings to a widget.

        Uses standard spacing from spacing_constants and appropriate size policies
        for general-purpose layouts. This is the default recommended configuration.

        Args:
            widget: Widget whose layout should use standard settings
        """
        layout = widget.layout()
        if layout is None:
            return

        # Set standard spacing and margins
        layout.setContentsMargins(PANEL_PADDING, PANEL_PADDING,
                                  PANEL_PADDING, PANEL_PADDING)
        layout.setSpacing(SPACING_MEDIUM)

        # Set balanced size policy
        LayoutManager.set_size_policies(widget, QSizePolicy.Policy.Preferred,
                                       QSizePolicy.Policy.Preferred)

    @staticmethod
    def apply_tab_layout(widget: QWidget) -> None:
        """
        Apply tab-specific layout settings to a widget.

        Uses larger padding and spacing appropriate for tab content areas.
        Prevents tabs from looking cramped while maintaining good proportions.

        Args:
            widget: Tab content widget to configure
        """
        layout = widget.layout()
        if layout is None:
            return

        # Set tab-appropriate spacing and margins
        layout.setContentsMargins(TAB_CONTENT_PADDING, TAB_CONTENT_PADDING,
                                  TAB_CONTENT_PADDING, TAB_CONTENT_PADDING)
        layout.setSpacing(TAB_SECTION_SPACING)

        # Set size policy for tab content
        LayoutManager.set_size_policies(widget, QSizePolicy.Policy.Preferred,
                                       QSizePolicy.Policy.Expanding)

    @staticmethod
    def apply_group_layout(widget: QWidget) -> None:
        """
        Apply group box layout settings to a widget.

        Uses compact internal padding suitable for grouped controls
        while maintaining readability and proper spacing.

        Args:
            widget: Group box widget to configure
        """
        layout = widget.layout()
        if layout is None:
            return

        # Set group-appropriate spacing and margins
        layout.setContentsMargins(GROUP_PADDING, GROUP_PADDING,
                                  GROUP_PADDING, GROUP_PADDING)
        layout.setSpacing(SPACING_SMALL)

        # Set compact size policy for groups
        LayoutManager.set_size_policies(widget, QSizePolicy.Policy.Preferred,
                                       QSizePolicy.Policy.Minimum)

    @staticmethod
    def configure_splitter(splitter: QSplitter, sizes: list[int]) -> None:
        """
        Configure a splitter with proper sizes and no stretch factors.

        This is critical for preventing empty space issues. Qt splitters
        with stretch factors can create unwanted empty areas when content
        doesn't fill the available space.

        Args:
            splitter: QSplitter to configure
            sizes: List of sizes for each splitter section
        """
        # CRITICAL: Set all stretch factors to 0 to prevent empty space
        for i in range(splitter.count()):
            splitter.setStretchFactor(i, 0)

        # Set the actual sizes
        splitter.setSizes(sizes)

        # Ensure splitter respects content size hints
        splitter.setChildrenCollapsible(False)

    @staticmethod
    def remove_all_stretches(layout: QLayout | None) -> None:
        """
        Remove all QSpacerItem stretches from a layout.

        Stretch spacers can cause empty space issues when content doesn't
        fill the available area. This method removes all spacer items
        that have expanding size policies.

        Args:
            layout: Layout to clean of stretch spacers
        """
        if not layout:
            return

        # Collect spacer items to remove (can't modify while iterating)
        items_to_remove = []

        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item and isinstance(item, QSpacerItem):
                # Remove expanding spacers that can cause empty space
                h_policy = item.sizePolicy().horizontalPolicy()
                v_policy = item.sizePolicy().verticalPolicy()
                if (QSizePolicy.Policy.Expanding in (h_policy, v_policy)):
                    items_to_remove.append(item)

        # Remove the problematic spacers
        for item in items_to_remove:
            layout.removeItem(item)

    @staticmethod
    def set_size_policies(widget: QWidget,
                         h_policy: QSizePolicy.Policy,
                         v_policy: QSizePolicy.Policy) -> None:
        """
        Set size policies on a widget with standardized configurations.

        Size policies control how widgets grow and shrink. Proper size policy
        configuration is essential for preventing unwanted empty spaces and
        ensuring responsive layouts.

        Args:
            widget: Widget to configure
            h_policy: Horizontal size policy
            v_policy: Vertical size policy
        """
        size_policy = QSizePolicy(h_policy, v_policy)
        widget.setSizePolicy(size_policy)

    @staticmethod
    def create_form_row_layout() -> QHBoxLayout:
        """
        Create a standardized horizontal layout for form rows.

        Returns a configured QHBoxLayout with appropriate spacing
        for label-control pairs in forms.

        Returns:
            Configured QHBoxLayout for form rows
        """
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING_MEDIUM)
        return layout

    @staticmethod
    def create_button_row_layout() -> QHBoxLayout:
        """
        Create a standardized horizontal layout for button rows.

        Returns a configured QHBoxLayout with appropriate spacing
        for button groups and action bars.

        Returns:
            Configured QHBoxLayout for button rows
        """
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING_SMALL)
        return layout

    @staticmethod
    def create_section_layout() -> QVBoxLayout:
        """
        Create a standardized vertical layout for content sections.

        Returns a configured QVBoxLayout with appropriate spacing
        for grouping related content within tabs or panels.

        Returns:
            Configured QVBoxLayout for content sections
        """
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING_LARGE)
        return layout

    @staticmethod
    def configure_horizontal_splitter(splitter: QSplitter,
                                     left_size: int,
                                     right_size: int) -> None:
        """
        Configure a horizontal splitter with specific left/right sizes.

        Convenience method for the common case of two-panel horizontal splits.
        Ensures no stretch factors that could cause empty space.

        Args:
            splitter: Horizontal QSplitter to configure
            left_size: Size of the left panel
            right_size: Size of the right panel
        """
        LayoutManager.configure_splitter(splitter, [left_size, right_size])

    @staticmethod
    def configure_vertical_splitter(splitter: QSplitter,
                                   top_size: int,
                                   bottom_size: int) -> None:
        """
        Configure a vertical splitter with specific top/bottom sizes.

        Convenience method for the common case of two-panel vertical splits.
        Ensures no stretch factors that could cause empty space.

        Args:
            splitter: Vertical QSplitter to configure
            top_size: Size of the top panel
            bottom_size: Size of the bottom panel
        """
        LayoutManager.configure_splitter(splitter, [top_size, bottom_size])

    @staticmethod
    def prevent_widget_expansion(widget: QWidget) -> None:
        """
        Configure a widget to prevent unwanted expansion.

        Sets size policies to prevent the widget from growing beyond
        its size hint, which helps prevent empty space issues.

        Args:
            widget: Widget to prevent from expanding
        """
        LayoutManager.set_size_policies(widget, QSizePolicy.Policy.Fixed,
                                       QSizePolicy.Policy.Fixed)

    @staticmethod
    def allow_horizontal_expansion(widget: QWidget) -> None:
        """
        Configure a widget to expand horizontally but not vertically.

        Useful for widgets that should fill available width but maintain
        a fixed height (like input fields, toolbars).

        Args:
            widget: Widget to allow horizontal expansion
        """
        LayoutManager.set_size_policies(widget, QSizePolicy.Policy.Expanding,
                                       QSizePolicy.Policy.Fixed)

    @staticmethod
    def allow_vertical_expansion(widget: QWidget) -> None:
        """
        Configure a widget to expand vertically but not horizontally.

        Useful for widgets that should fill available height but maintain
        a fixed width (like side panels, lists).

        Args:
            widget: Widget to allow vertical expansion
        """
        LayoutManager.set_size_policies(widget, QSizePolicy.Policy.Fixed,
                                       QSizePolicy.Policy.Expanding)
