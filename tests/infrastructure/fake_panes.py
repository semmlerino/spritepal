"""Fake pane implementations for WorkspaceLogicHelper tests.

These fakes store received values as public attributes, enabling
state-based assertions instead of brittle interaction assertions.
They implement the same interfaces as the real pane classes but
without any Qt widget overhead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeAIFramesPane:
    """Fake for AIFramesPane - stores state for assertions."""

    map_button_enabled: bool = False
    mapping_status: dict[str, str] = field(default_factory=dict)
    capture_palette_info: set[int] | None = None
    current_frame_palette_index: int | None = None
    selected_frame_id: str | None = None
    selected_emit_signal: bool = False
    last_updated_item_id: str | None = None
    last_updated_item_status: str | None = None
    _visible_items: set[str] = field(default_factory=set)

    def has_visible_item(self, ai_frame_id: str) -> bool:
        return ai_frame_id in self._visible_items

    def set_map_button_enabled(self, enabled: bool) -> None:
        self.map_button_enabled = enabled

    def set_mapping_status(self, status_map: dict[str, str]) -> None:
        self.mapping_status = status_map

    def select_frame_by_id(self, ai_frame_id: str, emit_signal: bool = False) -> None:
        self.selected_frame_id = ai_frame_id
        self.selected_emit_signal = emit_signal

    def set_capture_palette_info(self, palette_indices: set[int] | None) -> None:
        self.capture_palette_info = palette_indices

    def set_current_frame_palette_index(self, palette_index: int | None) -> None:
        self.current_frame_palette_index = palette_index

    def update_single_item_status(self, ai_frame_id: str, status: str) -> None:
        self.last_updated_item_id = ai_frame_id
        self.last_updated_item_status = status


@dataclass
class FakeCapturesPane:
    """Fake for CapturesLibraryPane - stores state for assertions."""

    link_status: dict[str, str | None] = field(default_factory=dict)
    game_frames: list[Any] = field(default_factory=list)
    game_frame_previews: dict[str, Any] = field(default_factory=dict)
    selected_frame_id: str | None = None
    cleared: bool = False
    selection_cleared: bool = False
    added_frames: list[tuple[Any, str | None]] = field(default_factory=list)
    last_single_link_update: tuple[str, str | None] | None = None

    def set_link_status(self, link_status: dict[str, str | None]) -> None:
        self.link_status = link_status

    def set_game_frames_with_link_status(self, game_frames: list[Any], link_status: dict[str, str | None]) -> None:
        self.game_frames = list(game_frames)
        self.link_status = link_status

    def clear(self) -> None:
        self.cleared = True
        self.game_frames = []
        self.link_status = {}

    def set_game_frame_previews(self, previews: dict[str, Any]) -> None:
        self.game_frame_previews = previews

    def update_single_item_link_status(self, game_frame_id: str, linked_ai_id: str | None) -> None:
        self.last_single_link_update = (game_frame_id, linked_ai_id)

    def add_game_frame(self, frame: Any, linked_ai_id: str | None = None) -> None:
        self.added_frames.append((frame, linked_ai_id))

    def clear_selection(self) -> None:
        self.selection_cleared = True
        self.selected_frame_id = None

    def select_frame(self, game_frame_id: str) -> None:
        self.selected_frame_id = game_frame_id
        self.selection_cleared = False


@dataclass
class FakeMappingPanel:
    """Fake for MappingPanel - stores state for assertions."""

    selected_ai_id: str | None = None
    selection_cleared: bool = False
    cleared_rows: list[str] = field(default_factory=list)
    row_alignments: dict[str, tuple[int, int, bool, bool]] = field(default_factory=dict)
    row_statuses: dict[str, str] = field(default_factory=dict)
    row_game_frame_texts: dict[str, str] = field(default_factory=dict)
    game_frame_previews: dict[str, Any] = field(default_factory=dict)

    def select_row_by_ai_id(self, ai_frame_id: str) -> None:
        self.selected_ai_id = ai_frame_id
        self.selection_cleared = False

    def clear_selection(self) -> None:
        self.selection_cleared = True
        self.selected_ai_id = None

    def clear_row_mapping(self, ai_frame_id: str) -> None:
        self.cleared_rows.append(ai_frame_id)

    def update_row_alignment(self, ai_frame_id: str, offset_x: int, offset_y: int, flip_h: bool, flip_v: bool) -> None:
        self.row_alignments[ai_frame_id] = (offset_x, offset_y, flip_h, flip_v)

    def update_row_status(self, ai_frame_id: str, status: str) -> None:
        self.row_statuses[ai_frame_id] = status

    def update_row_game_frame_text(self, ai_frame_id: str, game_frame_id: str) -> None:
        self.row_game_frame_texts[ai_frame_id] = game_frame_id

    def update_game_frame_preview(self, game_frame_id: str, pixmap: Any) -> None:
        self.game_frame_previews[game_frame_id] = pixmap


@dataclass
class FakeWorkbenchCanvas:
    """Fake for WorkbenchCanvas - stores state for assertions."""

    ai_frame: Any | None = None
    game_frame: Any | None = None
    game_frame_preview: Any | None = None
    game_frame_capture_result: Any | None = None
    game_frame_used_fallback: bool = False
    alignment_cleared: bool = False
    alignment: tuple[int, int, bool, bool, float, float, str] | None = None
    alignment_has_mapping: bool = False
    browsing_mode: bool | None = None
    ingame_edited_path: str | None = None
    auto_aligned: bool = False
    auto_align_with_scale: bool = False
    _drag_start_alignment: Any | None = None

    def set_ai_frame(self, ai_frame: Any | None) -> None:
        self.ai_frame = ai_frame

    def clear_alignment(self) -> None:
        self.alignment_cleared = True
        self.alignment = None

    def set_game_frame(
        self,
        game_frame: Any | None,
        preview: Any | None = None,
        capture_result: Any | None = None,
        used_fallback: bool = False,
    ) -> None:
        self.game_frame = game_frame
        self.game_frame_preview = preview
        self.game_frame_capture_result = capture_result
        self.game_frame_used_fallback = used_fallback

    def set_alignment(
        self,
        offset_x: int,
        offset_y: int,
        flip_h: bool,
        flip_v: bool,
        scale: float,
        sharpen: float,
        resampling: str,
        has_mapping: bool = False,
    ) -> None:
        self.alignment = (offset_x, offset_y, flip_h, flip_v, scale, sharpen, resampling)
        self.alignment_has_mapping = has_mapping
        self.alignment_cleared = False

    def set_browsing_mode(self, is_browsing: bool) -> None:
        self.browsing_mode = is_browsing

    def set_ingame_edited_path(self, path: str | None) -> None:
        self.ingame_edited_path = path

    def auto_align(self, with_scale: bool = False) -> None:
        self.auto_aligned = True
        self.auto_align_with_scale = with_scale

    def get_drag_start_alignment(self) -> Any | None:
        return self._drag_start_alignment

    def clear_drag_start_alignment(self) -> None:
        self._drag_start_alignment = None
