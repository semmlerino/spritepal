"""Facade classes for FrameMappingController domain decomposition.

These facades group related controller methods by domain, making the
controller a thin orchestrator while facades handle specific concerns.
"""

from ui.frame_mapping.facades.controller_context import ControllerContext

__all__ = ["ControllerContext"]
