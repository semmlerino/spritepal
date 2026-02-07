# Frame Mapping System Redundancy Audit
Date: February 7, 2026

The Frame Mapping system has undergone significant architectural shifts, resulting in several layers of redundant wrappers and duplicate logic paths. The current architecture follows a deep **Workspace → Coordinator → Controller → Facade → Service → Project** chain, which can be simplified by consolidating domain logic and removing pass-through methods.

## 1. Duplicate Implementations

| Location | Category | Reason | Recommended Remain | Impact |
| :--- | :--- | :--- | :--- | :--- |
| `ui/frame_mapping/views/captures_library_pane.py` (`STATUS_COLORS`) | **Duplicate** | Defines local green/gray colors for "linked" status that match `MAPPING_STATUS_COLORS` in `status_colors.py`. | `ui/frame_mapping/views/status_colors.py` | Low |
| `ui/frame_mapping/services/ai_frame_service.py` (`find_frame_index`) | **Duplicate** | Manually loops through frames to find an index; this logic is already internal to `FrameMappingProject.reorder_ai_frame`. | `core/frame_mapping_project.py` | Low |
| `ui/frame_mapping/facades/ai_frames_facade.py` (`remove` vs `remove_batch`) | **Duplicate** | `remove` is a special case of `remove_batch`. Both handle mapping cleanup, signal emission, and undo clearing independently. | Consolidate into `remove_batch` | Medium |
| `ui/frame_mapping/workspace_logic_helper.py` (`refresh_mapping_status` vs `update_single_ai_frame_status`) | **Duplicate** | "Full refresh" methods often duplicate the logic found in "targeted update" methods by looping over the same collection. | Targeted updates should be primary logic. | Medium |

## 2. Redundant Wrappers

| Location | Category | Reason | Recommended Remain | Impact |
| :--- | :--- | :--- | :--- | :--- |
| `ui/frame_mapping/frame_operations_coordinator.py` | **Redundant Wrapper** | Acts as a middleman for `QMessageBox` and state clearing. Most methods just relay to the controller. | Logic should be in `Workspace` or `Controller`. | Medium |
| `ui/frame_mapping/services/mapping_service.py` (`get_link_for_game_frame`) | **Redundant Wrapper** | One-liner pass-through to `project.get_ai_frame_linked_to_game_frame`. | Call Project method directly. | Low |
| `ui/frame_mapping/services/ai_frame_service.py` (`get_frames`) | **Redundant Wrapper** | One-liner pass-through to `project.ai_frames`. | Access Project property directly. | Low |
| `ui/frame_mapping/services/organization_service.py` (`_rename_frame_no_history` etc) | **Redundant Wrapper** | Pass-through methods used by Undo commands to call Project methods. | Commands should call Project directly. | Low |
| `ui/frame_mapping/controllers/frame_mapping_controller.py` (`emit_*` methods) | **Redundant Wrapper** | Boilerplate bridge methods (30+ lines) created solely to satisfy the `Protocol` for facades. | Use a shared Signal relay or direct access. | Medium |

## 3. Dead or Unused Code

| Location | Category | Reason | Impact |
| :--- | :--- | :--- | :--- |
| `ui/frame_mapping/views/ai_frames_pane.py` (`select_frame` & `get_selected_index`) | **Dead Code** | Index-based selection is deprecated in favor of ID-based selection; these are now only used in legacy unit tests. | Low |
| `core/frame_mapping_project.py` (`get_frames_with_tag`) | **Dead Code** | Referenced only in unit tests; no production UI or logic uses tag-based filtering at the project level. | Low |
| `core/frame_mapping_project.py` (`filter_mappings_by_valid_ai_ids`) | **Dead Code** | Provides a subset of the functionality in `_prune_orphaned_mappings`, which is already called during project load. | Low |

## 4. Incomplete Migrations

| Location | Category | Reason | Impact |
| :--- | :--- | :--- | :--- |
| `core/frame_mapping_project.py` (`FrameMapping` class) | **Incomplete Migration** | Docstrings and comments still reference deprecated `ai_frame_index` for v1 migration, cluttering the stable v2+ data model. | Low |
| `ui/frame_mapping/views/ai_frames_pane.py` (MIME Data / UserRole) | **Incomplete Migration** | Still populating `UserRole + 1` with indices for backward compatibility despite 100% of internal logic moving to ID-based lookups. | Low |

## Summary of Impact
The most significant redundancy is the **triple-handling of selection state** (Pane → StateManager → LogicHelper). Cleaning this up would remove roughly 15% of the UI coordination code and eliminate the most common cause of state desync bugs in this module. Consolidating the **Coordinator** and **LogicHelper** into the **Workspace** or **Controller** would further flatten the deep hierarchy and simplify the maintenance of the frame mapping workflow.
