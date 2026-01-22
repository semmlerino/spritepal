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


def confirm_replace_ai_frame_link(
    parent: QWidget | None,
    ai_frame_name: str,
    old_game_frame_name: str,
    new_game_frame_name: str,
) -> bool:
    """Show a confirmation dialog for replacing an AI frame's existing link.

    Args:
        parent: Parent widget for the dialog
        ai_frame_name: Name of the AI frame being remapped
        old_game_frame_name: Name of the currently linked game frame
        new_game_frame_name: Name of the new game frame to link to

    Returns:
        True if user confirms replacement, False if cancelled
    """
    result = QMessageBox.question(
        parent,
        "Replace Link?",
        f"AI frame '{ai_frame_name}' is already mapped to '{old_game_frame_name}'.\n\n"
        f"Replace with '{new_game_frame_name}'?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        QMessageBox.StandardButton.Cancel,
    )
    return result == QMessageBox.StandardButton.Yes
