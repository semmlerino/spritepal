"""Result types for injection operations.

These dataclasses provide structured return values for the injection
orchestrator, replacing signal emissions in the controller.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from core.frame_mapping_project import MappingStatus


@dataclass(frozen=True)
class InjectionRequest:
    """Immutable snapshot of injection parameters.

    All parameters needed for an injection operation, collected from
    UI context and passed to the orchestrator.

    Attributes:
        ai_frame_id: ID of the AI frame to inject (filename).
        rom_path: Path to the source ROM file.
        output_path: Explicit output path, or None to auto-generate.
        create_backup: Whether to create backup before injection.
        force_raw: Force RAW (uncompressed) injection for all tiles.
        allow_fallback: Allow fallback when stored entry IDs are stale.
        preserve_sprite: Keep original sprite visible where AI doesn't cover.
        emit_project_changed: Whether to emit project_changed signal after success.
    """

    ai_frame_id: str
    rom_path: Path
    output_path: Path | None = None
    create_backup: bool = True
    force_raw: bool = False
    allow_fallback: bool = False
    preserve_sprite: bool = False
    emit_project_changed: bool = True
    palette_rom_offset: int | None = None  # ROM offset for palette injection


@dataclass(frozen=True)
class TileInjectionResult:
    """Result of injecting a single tile group.

    Attributes:
        rom_offset: ROM offset where tiles were injected.
        tile_count: Number of tiles injected.
        compression_used: Compression type used ("HAL" or "RAW").
        success: Whether injection succeeded.
        message: Human-readable result message.
    """

    rom_offset: int
    tile_count: int
    compression_used: Literal["HAL", "RAW"]
    success: bool
    message: str


@dataclass(frozen=True)
class InjectionResult:
    """Result of complete frame injection.

    Returned by InjectionOrchestrator.execute() with all information
    the controller needs to update UI and project state.

    Attributes:
        success: Whether overall injection succeeded.
        tile_results: Results for each tile group injection.
        output_rom_path: Path to output ROM (if created).
        messages: Human-readable status messages.
        error: Error message if injection failed, else None.
        new_mapping_status: Status to set on mapping if success ("injected").
        needs_fallback_confirmation: True if injection aborted due to stale
            entries and allow_fallback was False.
        stale_frame_id: Frame ID with stale entries (for UI warning).
    """

    success: bool
    tile_results: tuple[TileInjectionResult, ...] = field(default_factory=tuple)
    output_rom_path: Path | None = None
    messages: tuple[str, ...] = field(default_factory=tuple)
    error: str | None = None
    new_mapping_status: MappingStatus | None = None
    needs_fallback_confirmation: bool = False
    stale_frame_id: str | None = None
    queue_time_game_frame_id: str | None = None

    @staticmethod
    def failure(error: str) -> InjectionResult:
        """Create a failure result with error message."""
        return InjectionResult(success=False, error=error)

    @staticmethod
    def stale_entries(frame_id: str, error: str) -> InjectionResult:
        """Create a result indicating stale entries need confirmation."""
        return InjectionResult(
            success=False,
            error=error,
            needs_fallback_confirmation=True,
            stale_frame_id=frame_id,
        )
