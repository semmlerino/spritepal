"""Shared context for all domain facades.

The ControllerContext provides access to shared state (project, undo stack,
repositories) that facades need to operate. This avoids passing the full
controller reference to facades, enabling cleaner separation of concerns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.frame_mapping_project import FrameMappingProject


@dataclass
class ControllerContext:
    """Shared state for domain facades.

    Provides access to shared state:
    - project: The current project (may be None)

    Facades receive this context rather than the full controller,
    enabling them to operate on shared state without circular dependencies.

    Callers must check for None values before use; no require_*() helpers
    are provided as facades handle nullable properties.
    """

    # Uses a mutable list wrapper so that facades sharing this context object
    # see project changes immediately.  A plain attribute on a @dataclass would
    # require every facade to re-read the context; with the list indirection,
    # ``context.project = new_proj`` mutates the *same* list object that all
    # facades already reference.
    _project_holder: list[FrameMappingProject | None] = field(default_factory=lambda: [None])

    @property
    def project(self) -> FrameMappingProject | None:
        """Get the current project, may be None."""
        return self._project_holder[0]

    @project.setter
    def project(self, value: FrameMappingProject | None) -> None:
        """Set the current project."""
        self._project_holder[0] = value
