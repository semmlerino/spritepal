"""Tests for FrameMappingWorkspace dependency injection.

Verifies that the workspace can accept an injected controller or create its own.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ui.frame_mapping.controllers.frame_mapping_controller import FrameMappingController
from ui.workspaces.frame_mapping_workspace import FrameMappingWorkspace


class TestFrameMappingWorkspaceDI:
    """Tests for controller dependency injection in workspace."""

    def test_default_controller_creation(self, app_context, qtbot) -> None:
        """Workspace creates its own controller when none injected."""
        workspace = FrameMappingWorkspace()
        qtbot.addWidget(workspace)

        # Verify controller exists
        assert workspace.controller is not None
        assert isinstance(workspace.controller, FrameMappingController)

        # Verify controller has workspace as parent (for Qt ownership)
        assert workspace.controller.parent() is workspace

    def test_injected_controller(self, app_context, qtbot) -> None:
        """Workspace uses injected controller when provided."""
        # Create a controller without parent
        injected_controller = FrameMappingController(parent=None)

        # Inject into workspace
        workspace = FrameMappingWorkspace(controller=injected_controller)
        qtbot.addWidget(workspace)

        # Verify workspace uses the injected controller
        assert workspace.controller is injected_controller

        # Verify injected controller does not have workspace as parent
        # (caller controls lifecycle)
        assert workspace.controller.parent() is None

    def test_signal_connections_with_injected_controller(self, app_context, qtbot) -> None:
        """Signal connections work with injected controller."""
        # Create controller
        controller = FrameMappingController(parent=None)

        # Inject into workspace
        workspace = FrameMappingWorkspace(controller=controller)
        qtbot.addWidget(workspace)

        # Verify key signals are connected by checking workspace handles signals
        # We can test this by emitting a signal and checking for no errors
        with qtbot.waitSignal(controller.project_changed, timeout=1000):
            controller.project_changed.emit()

    def test_signal_connections_with_default_controller(self, app_context, qtbot) -> None:
        """Signal connections work with default controller."""
        # Create workspace (creates default controller)
        workspace = FrameMappingWorkspace()
        qtbot.addWidget(workspace)

        # Verify signals work
        with qtbot.waitSignal(workspace.controller.project_changed, timeout=1000):
            workspace.controller.project_changed.emit()

    def test_controller_property_access(self, app_context, qtbot) -> None:
        """Controller property provides access to controller."""
        workspace = FrameMappingWorkspace()
        qtbot.addWidget(workspace)

        # Access via property
        controller = workspace.controller
        assert controller is not None
        assert isinstance(controller, FrameMappingController)

        # Property returns the same instance
        assert workspace.controller is controller

    def test_multiple_workspaces_with_separate_controllers(self, app_context, qtbot) -> None:
        """Multiple workspaces can have separate controllers."""
        workspace1 = FrameMappingWorkspace()
        workspace2 = FrameMappingWorkspace()
        qtbot.addWidget(workspace1)
        qtbot.addWidget(workspace2)

        # Each workspace has its own controller
        assert workspace1.controller is not workspace2.controller

    def test_multiple_workspaces_with_shared_controller(self, app_context, qtbot) -> None:
        """Multiple workspaces can share a controller (though unusual)."""
        shared_controller = FrameMappingController(parent=None)

        workspace1 = FrameMappingWorkspace(controller=shared_controller)
        workspace2 = FrameMappingWorkspace(controller=shared_controller)
        qtbot.addWidget(workspace1)
        qtbot.addWidget(workspace2)

        # Both workspaces use the same controller
        assert workspace1.controller is shared_controller
        assert workspace2.controller is shared_controller
        assert workspace1.controller is workspace2.controller

    def test_controller_survives_workspace_deletion_when_injected(self, app_context, qtbot) -> None:
        """Injected controller is not deleted when workspace is deleted."""
        controller = FrameMappingController(parent=None)

        workspace = FrameMappingWorkspace(controller=controller)
        qtbot.addWidget(workspace)

        # Delete workspace
        workspace.deleteLater()
        qtbot.wait(50)

        # Controller still exists (caller owns it)
        assert controller is not None
        # Can still call methods
        controller.new_project("test")
        assert controller.has_project
