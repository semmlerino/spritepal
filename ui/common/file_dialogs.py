from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QWidget

from core.app_context import get_app_context

logger = logging.getLogger(__name__)


class FileDialogHelper:
    """
    Helper class for standardized file dialog operations

    Provides consistent directory selection and file dialog patterns
    used throughout SpritePal's UI components.
    """

    @staticmethod
    def browse_directory(
        parent: QWidget | None = None,
        title: str = "Select Directory",
        initial_dir: str = "",
        settings_key: str | None = None,
        settings_namespace: str = "file_dialogs",
    ) -> str:
        """
        Browse for directory with standardized behavior

        Args:
            parent: Parent widget for the dialog
            title: Dialog title
            initial_dir: Initial directory to show
            settings_key: Settings key to save/restore last directory
            settings_namespace: Settings namespace for the key

        Returns:
            Selected directory path, or empty string if cancelled
        """
        try:
            settings = get_app_context().application_state_manager
        except RuntimeError:
            logger.warning("AppContext not available for browse_directory, using fallback")
            settings = None

        # Determine initial directory
        if initial_dir and Path(initial_dir).exists():
            start_dir = initial_dir
        elif settings_key and settings is not None:
            # Try to restore from settings
            saved_dir = str(settings.get(settings_namespace, settings_key, ""))
            start_dir = saved_dir if saved_dir and Path(saved_dir).exists() else settings.get_default_directory()
        elif settings is not None:
            start_dir = settings.get_default_directory()
        else:
            start_dir = str(Path.home())

        # Show directory dialog
        directory = QFileDialog.getExistingDirectory(
            parent, title, str(start_dir), QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks
        )

        if directory and settings is not None:
            # Save to settings for future use
            if settings_key:
                settings.set(settings_namespace, settings_key, directory)
            settings.set_last_used_directory(directory)

        return directory

    @staticmethod
    def browse_open_file(
        parent: QWidget | None = None,
        title: str = "Open File",
        file_filter: str = "All Files (*.*)",
        initial_path: str = "",
        settings_key: str | None = None,
        settings_namespace: str = "file_dialogs",
    ) -> str:
        """
        Returns:
            Selected file path, or empty string if cancelled
        """
        try:
            settings = get_app_context().application_state_manager
        except RuntimeError:
            logger.warning("AppContext not available for browse_open_file, using fallback")
            settings = None

        # Determine initial directory
        if initial_path and Path(initial_path).exists():
            start_path = initial_path if Path(initial_path).is_file() else initial_path
        elif settings_key and settings is not None:
            # Try to restore from settings
            saved_path = str(settings.get(settings_namespace, settings_key, ""))
            if saved_path and Path(saved_path).exists():
                start_path = saved_path
            else:
                start_path = settings.get_default_directory()
        elif settings is not None:
            start_path = settings.get_default_directory()
        else:
            start_path = str(Path.home())

        # Show open file dialog
        filename, _ = QFileDialog.getOpenFileName(parent, title, str(start_path), file_filter)

        if filename and settings is not None:
            # Save to settings for future use
            if settings_key:
                settings.set(settings_namespace, settings_key, filename)
            settings.set_last_used_directory(str(Path(filename).parent))

        return filename

    @staticmethod
    def browse_save_file(
        parent: QWidget | None = None,
        title: str = "Save File",
        file_filter: str = "All Files (*.*)",
        initial_path: str = "",
        settings_key: str | None = None,
        settings_namespace: str = "file_dialogs",
    ) -> str:
        """
        Browse for file to save with standardized behavior

        Args:
            parent: Parent widget for the dialog
            title: Dialog title
            file_filter: File filter string
            initial_path: Initial file/directory path with suggested filename
            settings_key: Settings key to save/restore last location
            settings_namespace: Settings namespace for the key

        Returns:
            Selected file path, or empty string if cancelled
        """
        try:
            settings = get_app_context().application_state_manager
        except RuntimeError:
            logger.warning("AppContext not available for browse_save_file, using fallback")
            settings = None

        # Determine initial path
        if initial_path:
            start_path = initial_path
        elif settings_key and settings is not None:
            # Try to restore from settings
            saved_path = str(settings.get(settings_namespace, settings_key, ""))
            if saved_path and Path(saved_path).parent.exists():
                start_path = saved_path
            else:
                start_path = settings.get_default_directory()
        elif settings is not None:
            start_path = settings.get_default_directory()
        else:
            start_path = str(Path.home())

        # Show save file dialog
        filename, _ = QFileDialog.getSaveFileName(parent, title, str(start_path), file_filter)

        if filename and settings is not None:
            # Save to settings for future use
            if settings_key:
                settings.set(settings_namespace, settings_key, filename)
            settings.set_last_used_directory(str(Path(filename).parent))

        return filename

    @staticmethod
    def get_smart_initial_directory(
        current_path: str = "", fallback_setting: str | None = None, fallback_namespace: str = "file_dialogs"
    ) -> str:
        """
        Get smart initial directory for file dialogs

        Args:
            current_path: Current path to check
            fallback_setting: Settings key for fallback directory
            fallback_namespace: Settings namespace for fallback

        Returns:
            Best initial directory to use
        """
        try:
            settings = get_app_context().application_state_manager
        except RuntimeError:
            logger.warning("AppContext not available for get_smart_initial_directory, using fallback")
            settings = None

        # Check current path first
        if current_path:
            current = Path(current_path)
            if current.is_file():
                dir_path = current.parent
                if dir_path.exists():
                    return str(dir_path)
            elif current.is_dir():
                return current_path

        # Check fallback setting
        if fallback_setting and settings is not None:
            saved_dir = str(settings.get(fallback_namespace, fallback_setting, ""))
            if saved_dir and Path(saved_dir).exists():
                return saved_dir

        # Use default directory
        if settings is not None:
            return settings.get_default_directory()
        return str(Path.home())


# Convenience functions for common dialog patterns
def browse_for_directory(parent: QWidget | None = None, title: str = "Select Directory", initial_dir: str = "") -> str:
    """Convenience function for simple directory browsing"""
    return FileDialogHelper.browse_directory(parent, title, initial_dir)


def browse_for_open_file(
    parent: QWidget | None = None,
    title: str = "Open File",
    file_filter: str = "All Files (*.*)",
    initial_path: str = "",
) -> str:
    """Convenience function for simple file opening"""
    return FileDialogHelper.browse_open_file(parent, title, file_filter, initial_path)


def browse_for_save_file(
    parent: QWidget | None = None,
    title: str = "Save File",
    file_filter: str = "All Files (*.*)",
    initial_path: str = "",
) -> str:
    """Convenience function for simple file saving"""
    return FileDialogHelper.browse_save_file(parent, title, file_filter, initial_path)
