#!/usr/bin/env python3
"""
Project state model for the unified sprite editor.
Tracks file associations and workflow state.
"""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ProjectModel:
    """
    Model for managing project state and file associations.
    Tracks VRAM/CGRAM/OAM files as well as PNG and palette associations.
    """

    # Current files
    vram_file: str | None = None
    cgram_file: str | None = None
    oam_file: str | None = None
    image_file: str | None = None
    palette_file: str | None = None

    # Extraction parameters
    extraction_offset: int = 0xC000
    extraction_size: int = 0x4000
    tiles_per_row: int = 16
    current_palette_index: int = 8

    # File associations
    image_palette_associations: dict[str, str] = field(default_factory=dict)

    # Workflow state
    last_extracted_image: str | None = None
    last_injection_target: str | None = None

    def associate_image_palette(self, image_path: str, palette_path: str) -> None:
        """Associate an image file with a palette file."""
        self.image_palette_associations[image_path] = palette_path

    def get_associated_palette(self, image_path: str) -> str | None:
        """Get palette file associated with an image."""
        return self.image_palette_associations.get(image_path)

    def get_metadata_path(self, image_path: str) -> str:
        """Get the metadata file path for an image."""
        path = Path(image_path)
        return str(path.with_suffix(".metadata.json"))

    def get_paired_palette_path(self, image_path: str) -> str | None:
        """
        Get the paired .pal.json path for an image if it exists.
        Convention: image.png -> image.pal.json
        """
        path = Path(image_path)
        palette_path = path.with_suffix(".pal.json")
        if palette_path.exists():
            return str(palette_path)
        return None

    def clear(self) -> None:
        """Clear all project state."""
        self.vram_file = None
        self.cgram_file = None
        self.oam_file = None
        self.image_file = None
        self.palette_file = None
        self.last_extracted_image = None
        self.last_injection_target = None

    def has_vram_files(self) -> bool:
        """Check if VRAM files are loaded."""
        return bool(self.vram_file)

    def has_editing_image(self) -> bool:
        """Check if an image is loaded for editing."""
        return bool(self.image_file)

    def set_extraction_params(
        self, offset: int, size: int, tiles_per_row: int
    ) -> None:
        """Set extraction parameters."""
        self.extraction_offset = offset
        self.extraction_size = size
        self.tiles_per_row = tiles_per_row
