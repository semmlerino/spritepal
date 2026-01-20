"""Replace link confirmation dialog."""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox, QWidget


def confirm_replace_link(
    parent: QWidget | None,
    game_frame_name: str,
    old_ai_frame_name: str,
    new_ai_frame_name: str,
) -> bool:
    """Show a confirmation dialog for replacing an existing frame link.

    Args:
        parent: Parent widget for the dialog
        game_frame_name: Name/ID of the game frame being linked
        old_ai_frame_name: Name of the currently linked AI frame
        new_ai_frame_name: Name of the new AI frame to link

    Returns:
        True if user confirms replacement, False if cancelled
    """
    result = QMessageBox.question(
        parent,
        "Replace Link?",
        f"'{game_frame_name}' is linked to '{old_ai_frame_name}'.\n\nReplace with '{new_ai_frame_name}'?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        QMessageBox.StandardButton.Cancel,
    )
    return result == QMessageBox.StandardButton.Yes
