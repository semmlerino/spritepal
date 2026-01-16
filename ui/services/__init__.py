"""UI services package.

Contains service classes that coordinate UI workflows without being tied to specific widgets.
"""

from ui.services.dialog_coordinator import DialogCoordinator
from ui.services.extraction_workflow_coordinator import ExtractionWorkflowCoordinator

__all__ = ["DialogCoordinator", "ExtractionWorkflowCoordinator"]
