"""Injection Coordinator for Frame Mapping Workspace.

Coordinates injection operations (single, selected, all) and handles
async injection lifecycle signals. Acts as a passive helper that receives
method calls from the workspace - does not connect signals itself.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, cast

from PySide6.QtWidgets import QMessageBox, QWidget

from utils.logging_config import get_logger

if TYPE_CHECKING:
    from ui.frame_mapping.controllers.frame_mapping_controller import FrameMappingController
    from ui.frame_mapping.views.mapping_panel import MappingPanel
    from ui.frame_mapping.views.workbench_canvas import WorkbenchCanvas
    from ui.frame_mapping.workspace_state_manager import WorkspaceStateManager
    from ui.managers.status_bar_manager import StatusBarManager

logger = get_logger(__name__)


class InjectionCoordinator:
    """Coordinates injection operations and async lifecycle.

    This is a passive helper that:
    - Validates ROM paths before injection
    - Handles confirmation dialogs
    - Tracks batch injection state
    - Updates UI on injection completion

    Signal connections remain in the workspace's _connect_signals().
    """

    def __init__(self) -> None:
        """Initialize with no dependencies (set via setters)."""
        self._controller: FrameMappingController | None = None
        self._state: WorkspaceStateManager | None = None
        self._mapping_panel: MappingPanel | None = None
        self._alignment_canvas: WorkbenchCanvas | None = None
        self._message_service: StatusBarManager | None = None
        self._parent_widget: QWidget | None = None
        # Callback for UI-specific updates (e.g., checkbox state, frame status)
        self._get_reuse_rom_enabled: Callable[[], bool] | None = None
        self._update_frame_status: Callable[[str], None] | None = None

    # -------------------------------------------------------------------------
    # Dependency Injection (Deferred)
    # -------------------------------------------------------------------------

    def set_controller(self, controller: FrameMappingController) -> None:
        """Set the controller for injection operations."""
        self._controller = controller

    def set_state(self, state: WorkspaceStateManager) -> None:
        """Set the state manager for tracking injection state."""
        self._state = state

    def set_mapping_panel(self, panel: MappingPanel) -> None:
        """Set the mapping panel for row updates."""
        self._mapping_panel = panel

    def set_alignment_canvas(self, canvas: WorkbenchCanvas) -> None:
        """Set the alignment canvas for preserve_sprite access."""
        self._alignment_canvas = canvas

    def set_message_service(self, service: StatusBarManager | None) -> None:
        """Set the message service for status updates."""
        self._message_service = service

    def set_parent_widget(self, widget: QWidget) -> None:
        """Set the parent widget for dialogs."""
        self._parent_widget = widget

    def set_ui_callbacks(
        self,
        get_reuse_rom_enabled: Callable[[], bool],
        update_frame_status: Callable[[str], None],
    ) -> None:
        """Set callbacks for UI-specific state access.

        Args:
            get_reuse_rom_enabled: Returns True if "reuse ROM" checkbox is checked
            update_frame_status: Updates status indicator for a single AI frame
        """
        self._get_reuse_rom_enabled = get_reuse_rom_enabled
        self._update_frame_status = update_frame_status

    # -------------------------------------------------------------------------
    # ROM Validation
    # -------------------------------------------------------------------------

    def validate_rom_path(self) -> bool:
        """Validate that the current ROM path is valid and exists.

        Shows appropriate error dialogs if validation fails.

        Returns:
            True if valid, False otherwise.
        """
        if self._state is None or self._parent_widget is None:
            return False

        if self._state.rom_path is None:
            QMessageBox.information(
                self._parent_widget,
                "Injection Requirement",
                "No ROM loaded.\n\nPlease select a ROM using the ROM selector in the header.",
            )
            return False

        if not self._state.is_rom_valid():
            QMessageBox.warning(
                self._parent_widget,
                "ROM Not Found",
                f"The ROM file from Sprite Editor no longer exists:\n{self._state.rom_path}\n\n"
                "Please reload the ROM in the Sprite Editor workspace.",
            )
            return False

        return True

    # -------------------------------------------------------------------------
    # Injection Operations
    # -------------------------------------------------------------------------

    def inject_single(self, ai_frame_id: str) -> None:
        """Handle inject single mapping request (async).

        Uses background thread to avoid UI freeze during ROM I/O.

        Args:
            ai_frame_id: AI frame ID (filename)
        """
        if self._controller is None or self._state is None or self._parent_widget is None:
            return

        project = self._controller.project
        if project is None:
            return

        if not project.get_mapping_for_ai_frame(ai_frame_id):
            QMessageBox.information(self._parent_widget, "Inject Frame", "Selected frame is not mapped.")
            return

        if not self.validate_rom_path():
            return

        # At this point self._state.rom_path is guaranteed not None and exists
        rom_path = cast(Path, self._state.rom_path)

        # Prepare injection target ROM
        target_rom = self._prepare_injection_target(f"AI Frame '{ai_frame_id}'", rom_path, "Inject Frame")
        if target_rom is None:
            return

        # Queue the injection
        self._queue_injection_batch([ai_frame_id], target_rom, rom_path)

    def inject_selected(self, selected_ids: list[str]) -> None:
        """Handle inject selected frames request (async).

        Uses background thread to avoid UI freeze during batch ROM I/O.

        Args:
            selected_ids: List of AI frame IDs to inject
        """
        if self._controller is None or self._state is None or self._parent_widget is None:
            return

        if not selected_ids:
            QMessageBox.information(self._parent_widget, "Inject Selected", "No frames selected for injection.")
            return

        if not self.validate_rom_path():
            return

        # At this point self._state.rom_path is guaranteed not None and exists
        rom_path = cast(Path, self._state.rom_path)

        frame_count = len(selected_ids)
        # Prepare injection target ROM
        target_rom = self._prepare_injection_target(f"{frame_count} selected frames", rom_path, "Inject Selected")
        if target_rom is None:
            return

        # Queue the injections
        self._queue_injection_batch(selected_ids, target_rom, rom_path, frame_count)

    def inject_all(self) -> None:
        """Handle inject all mapped frames request (async).

        Uses background thread to avoid UI freeze during batch ROM I/O.
        """
        if self._controller is None or self._state is None or self._parent_widget is None:
            return

        project = self._controller.project
        if project is None or project.mapped_count == 0:
            QMessageBox.information(self._parent_widget, "Inject All", "No mapped frames to inject.")
            return

        if not self.validate_rom_path():
            return

        # At this point self._state.rom_path is guaranteed not None and exists
        rom_path = cast(Path, self._state.rom_path)

        # Collect all mapped frame IDs
        mapped_ids = [
            ai_frame.id for ai_frame in project.ai_frames if project.get_mapping_for_ai_frame(ai_frame.id) is not None
        ]

        # Prepare injection target ROM
        target_rom = self._prepare_injection_target(f"{project.mapped_count} mapped frames", rom_path, "Inject All")
        if target_rom is None:
            return

        # Queue the injections
        self._queue_injection_batch(mapped_ids, target_rom, rom_path, len(mapped_ids))

    # -------------------------------------------------------------------------
    # Injection Helper Methods
    # -------------------------------------------------------------------------

    def _prepare_injection_target(self, description: str, rom_path: Path, action_name: str) -> Path | None:
        """Prepare injection target ROM by checking reuse eligibility and showing confirmation.

        Handles two scenarios:
        1. If reuse is enabled and last_injected_rom exists, offers to reuse it
        2. Otherwise, offers to create a new ROM copy

        Args:
            description: Human-readable description for the confirmation dialog
                        (e.g., "AI Frame 'frame_1'", "5 selected frames", "12 mapped frames")
            rom_path: Current ROM path (guaranteed to exist after validate_rom_path())
            action_name: Action name for error dialogs (e.g., "Inject Frame", "Inject Selected")

        Returns:
            Path to target ROM if confirmed, None if cancelled or creation failed.
        """
        if self._state is None or self._parent_widget is None or self._controller is None:
            return None

        # Check if we should reuse the last injected ROM
        reuse_enabled = self._get_reuse_rom_enabled() if self._get_reuse_rom_enabled else False
        can_reuse = (
            reuse_enabled and self._state.last_injected_rom is not None and self._state.last_injected_rom.exists()
        )

        if can_reuse:
            target_rom = cast(Path, self._state.last_injected_rom)
            reply = QMessageBox.question(
                self._parent_widget,
                "Confirm Injection",
                f"Inject {description}?\n\nReusing existing ROM: {target_rom.name}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
        else:
            reply = QMessageBox.question(
                self._parent_widget,
                "Confirm Injection",
                f"Inject {description}?\n\nA new copy of {rom_path.name} will be created for injection.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )

        if reply != QMessageBox.StandardButton.Yes:
            return None

        # Either reuse existing ROM or create a new copy
        if can_reuse:
            return cast(Path, self._state.last_injected_rom)

        # Create a new copy for injection
        target_rom = self._controller.create_injection_copy(rom_path)
        if target_rom is None:
            QMessageBox.critical(self._parent_widget, action_name, "Failed to create ROM copy for injection.")
            return None

        return target_rom

    def _queue_injection_batch(
        self, frame_ids: list[str], target_rom: Path, rom_path: Path, frame_count: int | None = None
    ) -> None:
        """Queue a batch of injections for async processing.

        Tracks batch state and queues all frames for injection with the specified target ROM.

        Args:
            frame_ids: List of AI frame IDs to inject
            target_rom: Target ROM path for injection output
            rom_path: Source ROM path (used when calling inject_mapping_async)
            frame_count: Optional frame count for status message. If not provided, defaults to len(frame_ids).
        """
        if self._state is None or self._controller is None:
            return

        # Default frame_count to list length if not provided
        if frame_count is None:
            frame_count = len(frame_ids)

        # Track batch injection for completion handling
        self._state.start_batch_injection(frame_ids, target_rom)

        # Show status message while batch processes (only for multi-frame batches)
        if frame_count > 1 and self._message_service:
            self._message_service.show_message(f"Injecting {frame_count} frames...")

        # Queue all injections asynchronously (processed sequentially by worker)
        preserve_sprite = self._alignment_canvas.get_preserve_sprite() if self._alignment_canvas else False
        for ai_frame_id in frame_ids:
            self._controller.inject_mapping_async(
                ai_frame_id,
                rom_path,
                output_path=target_rom,
                preserve_sprite=preserve_sprite,
            )

    # -------------------------------------------------------------------------
    # Async Injection Lifecycle Handlers
    # -------------------------------------------------------------------------

    def handle_mapping_injected(self, ai_frame_id: str, message: str) -> None:
        """Handle successful injection signal.

        Args:
            ai_frame_id: The AI frame ID that was injected
            message: Success message from controller
        """
        if self._message_service:
            self._message_service.show_message(f"Injection successful for frame {ai_frame_id}")

        # Use targeted updates instead of full refresh (avoids regenerating all thumbnails)
        if self._update_frame_status:
            self._update_frame_status(ai_frame_id)
        if self._mapping_panel:
            self._mapping_panel.update_row_status(ai_frame_id, "injected")

    def handle_stale_entries_warning(self, frame_id: str) -> None:
        """Handle stale entry ID warning from controller.

        Tracks the frame ID for potential retry with allow_fallback=True.
        Also updates the canvas warning label if the frame matches the current selection.

        Args:
            frame_id: Game frame ID with stale entries
        """
        if self._state is None:
            return

        logger.info("Stale entries detected for frame '%s'", frame_id)
        self._state.add_stale_game_frame_id(frame_id)

        # Update canvas warning label if this is the currently selected game frame
        if self._state.selected_game_id == frame_id and self._alignment_canvas:
            self._alignment_canvas.set_stale_entries_warning_visible(True)

    def handle_stale_entries_on_load(self, stale_frame_ids: list[str]) -> None:
        """Show warning when project loads with stale capture entries.

        Args:
            stale_frame_ids: Game frame IDs with mismatched entry IDs
        """
        count = len(stale_frame_ids)
        logger.warning("Project loaded with %d stale game frames: %s", count, stale_frame_ids)

        # Show status bar message
        if self._message_service:
            self._message_service.show_message(
                f"Warning: Stale entries detected in {count} frame(s) - preview/injection will use ROM offset fallback",
                timeout=8000,
            )

        # Log detailed information
        logger.info(
            "Stale entries in frames: %s. "
            "Capture files may have been re-recorded. "
            "Preview and injection will fall back to ROM offset filtering.",
            ", ".join(stale_frame_ids[:5]) + ("..." if count > 5 else ""),
        )

    def handle_async_injection_started(self, ai_frame_id: str) -> None:
        """Handle async injection started signal.

        Args:
            ai_frame_id: The AI frame ID being injected
        """
        if self._state is None:
            return

        logger.debug("Async injection started for frame '%s'", ai_frame_id)
        # Update status message to show progress
        pending = len(self._state.batch_injection_pending)
        if pending > 1 and self._message_service:
            self._message_service.show_message(f"Injecting frame {ai_frame_id}... ({pending} remaining)")

    def handle_async_injection_progress(self, ai_frame_id: str, message: str) -> None:
        """Handle async injection progress signal.

        Args:
            ai_frame_id: The AI frame ID being injected
            message: Progress message
        """
        logger.debug("Async injection progress for '%s': %s", ai_frame_id, message)

    def handle_async_injection_finished(self, ai_frame_id: str, success: bool, message: str) -> None:
        """Handle async injection completion signal.

        Updates batch tracking state and triggers completion handler when all done.

        Args:
            ai_frame_id: The AI frame ID that was injected
            success: Whether the injection succeeded
            message: Result message
        """
        if self._state is None or self._controller is None:
            return

        # Track stale entry failures for batch reporting
        # Note: stale_game_frame_ids stores GAME frame IDs, but ai_frame_id is an AI frame ID.
        # We need to look up the game frame ID for this AI frame to compare correctly.
        stale_entries = False
        if self._state.stale_game_frame_ids:
            project = self._controller.project
            if project is not None:
                mapping = project.get_mapping_for_ai_frame(ai_frame_id)
                if mapping is not None:
                    stale_entries = mapping.game_frame_id in self._state.stale_game_frame_ids

        self._state.record_batch_injection_result(ai_frame_id, success, stale_entries)

        # Check if batch is complete
        if not self._state.is_batch_injection_active():
            self._handle_batch_injection_complete()

    def _handle_batch_injection_complete(self) -> None:
        """Handle completion of batch injection.

        Shows summary message and updates ROM tracking state.
        """
        if self._state is None:
            return

        success_count = len(self._state.batch_injection_success)
        failed_stale_count = len(self._state.batch_injection_failed_stale)
        failed_other_count = len(self._state.batch_injection_failed_other)
        total_count = success_count + failed_stale_count + failed_other_count
        target_rom = self._state.batch_injection_target_rom

        # Update last injected ROM if any succeeded
        if success_count > 0 and target_rom is not None:
            self._state.last_injected_rom = target_rom

        # Build result message
        if target_rom is not None:
            if total_count == 1:
                # Single frame injection
                if success_count == 1:
                    msg = f"Injection successful: {target_rom.name}"
                elif failed_stale_count == 1:
                    msg = "Injection failed due to stale entry selection"
                elif failed_other_count == 1:
                    msg = "Injection failed"
                else:
                    msg = "Injection complete"
            else:
                # Batch injection
                msg = f"Injected {success_count}/{total_count} frames into {target_rom.name}"
                if failed_stale_count > 0:
                    msg += f"\n{failed_stale_count} frame(s) skipped due to outdated entry selection."
                if failed_other_count > 0:
                    msg += f"\n{failed_other_count} frame(s) failed."
        else:
            msg = f"Injection complete: {success_count}/{total_count} frames"

        if self._message_service:
            self._message_service.show_message(msg)

        logger.info("Batch injection complete: %d/%d succeeded", success_count, total_count)

        # Clear batch tracking state
        self._state.clear_batch_injection()
