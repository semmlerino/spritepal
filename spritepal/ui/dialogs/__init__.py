"""
Dialog components for SpritePal UI
"""

from __future__ import annotations

# Import dialog components
# UnifiedManualOffsetDialog has smart selection built-in based on environment variable
from .manual_offset_dialog import UnifiedManualOffsetDialog
from .output_settings_dialog import OutputSettings, OutputSettingsDialog
from .resume_scan_dialog import ResumeScanDialog
from .settings_dialog import SettingsDialog
from .user_error_dialog import UserErrorDialog

# Primary interface
ManualOffsetDialog = UnifiedManualOffsetDialog

__all__ = [
    "ManualOffsetDialog",  # Primary interface (unified dialog)
    "OutputSettings",  # Output settings namedtuple
    "OutputSettingsDialog",  # Output settings dialog
    "ResumeScanDialog",
    "SettingsDialog",
    "UnifiedManualOffsetDialog",  # Explicit new dialog name
    "UserErrorDialog",
]
