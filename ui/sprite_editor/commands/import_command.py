"""Command for importing external images with undo/redo support."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, override

import numpy as np

from ui.sprite_editor.commands.pixel_commands import UndoCommand

if TYPE_CHECKING:
    from numpy.typing import NDArray

    from ui.sprite_editor.models.image_model import ImageModel


class ImportImageCommand(UndoCommand):
    """Command for importing an external image into the sprite editor.

    Stores both the previous and new image data/palette to support
    full undo/redo of import operations.
    """

    def __init__(
        self,
        previous_data: NDArray[np.uint8],
        previous_palette: list[tuple[int, int, int]],
        new_data: NDArray[np.uint8],
        new_palette: list[tuple[int, int, int]],
        source_path: str = "",
    ) -> None:
        """Initialize import command.

        Args:
            previous_data: Image data before import
            previous_palette: Palette before import
            new_data: New image data from import
            new_palette: New palette from import
            source_path: Source file path (for reference)
        """
        super().__init__()
        self._previous_data = previous_data.copy()
        self._previous_palette = list(previous_palette)
        self._new_data = new_data.copy()
        self._new_palette = list(new_palette)
        self._source_path = source_path

    @override
    def execute(self, model: ImageModel) -> None:
        """Apply imported image to model."""
        model.set_data(self._new_data, store_checksum=False)

    @override
    def unexecute(self, model: ImageModel) -> None:
        """Restore previous image data."""
        model.set_data(self._previous_data, store_checksum=False)

    @override
    def get_memory_size(self) -> int:
        """Return approximate memory usage in bytes."""
        return (
            self._previous_data.nbytes
            + self._new_data.nbytes
            + len(self._previous_palette) * 3 * 4  # 3 ints per color, ~4 bytes each
            + len(self._new_palette) * 3 * 4
            + len(self._source_path)
        )

    @property
    def new_palette(self) -> list[tuple[int, int, int]]:
        """Get the new palette from the import."""
        return self._new_palette

    @property
    def previous_palette(self) -> list[tuple[int, int, int]]:
        """Get the previous palette before import."""
        return self._previous_palette

    @override
    def _get_compress_data(self) -> dict[str, Any]:  # type: ignore[reportExplicitAny]
        """Get data to be compressed."""
        return {
            "previous_data": self._previous_data.tobytes(),
            "previous_shape": self._previous_data.shape,
            "previous_palette": self._previous_palette,
            "new_data": self._new_data.tobytes(),
            "new_shape": self._new_data.shape,
            "new_palette": self._new_palette,
            "source_path": self._source_path,
        }

    @override
    def _clear_uncompressed_data(self) -> None:
        """Clear uncompressed data after compression."""
        self._previous_data = np.array([], dtype=np.uint8)
        self._new_data = np.array([], dtype=np.uint8)

    @override
    def _restore_from_compressed(self, data: dict[str, Any]) -> None:  # type: ignore[reportExplicitAny]
        """Restore state from compressed data."""
        self._previous_data = np.frombuffer(data["previous_data"], dtype=np.uint8).reshape(data["previous_shape"])
        self._previous_palette = data["previous_palette"]
        self._new_data = np.frombuffer(data["new_data"], dtype=np.uint8).reshape(data["new_shape"])
        self._new_palette = data["new_palette"]
        self._source_path = data["source_path"]

    @classmethod
    @override
    def from_dict(cls, data: dict[str, Any]) -> ImportImageCommand:  # type: ignore[reportExplicitAny]
        """Deserialize command from dictionary."""
        cmd_data = data.get("data", {})
        if not cmd_data:
            msg = "Cannot deserialize ImportImageCommand without data"
            raise ValueError(msg)

        previous_data = np.frombuffer(cmd_data["previous_data"], dtype=np.uint8).reshape(cmd_data["previous_shape"])
        new_data = np.frombuffer(cmd_data["new_data"], dtype=np.uint8).reshape(cmd_data["new_shape"])

        return cls(
            previous_data=previous_data,
            previous_palette=cmd_data["previous_palette"],
            new_data=new_data,
            new_palette=cmd_data["new_palette"],
            source_path=cmd_data.get("source_path", ""),
        )
