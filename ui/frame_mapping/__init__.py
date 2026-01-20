"""Frame Mapping workspace package."""

from ui.frame_mapping.controllers.frame_mapping_controller import FrameMappingController
from ui.frame_mapping.views.comparison_panel import ComparisonPanel
from ui.frame_mapping.views.frame_browser_panel import FrameBrowserPanel
from ui.frame_mapping.views.mapping_panel import MappingPanel

__all__ = [
    "ComparisonPanel",
    "FrameBrowserPanel",
    "FrameMappingController",
    "MappingPanel",
]
