# Audit Report: Sprite Rearrangement System

**Date:** Tuesday, January 13, 2026
**Status:** Fact-finding pass complete.

## Executive Summary & Context

In SNES ROM hacking (specifically for games like *Kirby Super Star*), sprites are often stored as a collection of scattered 8x8 "tiles" rather than a single contiguous image. To make editing intuitive, SpritePal allows users to "rearrange" these scattered tiles into a logical, contiguous layout (the **Logical View**). 

The system must handle three distinct representations:
1.  **Physical Layout:** How tiles are literally stored in the ROM (often scattered or in a "strip").
2.  **Canvas Layout:** A user-defined 2D grid where they can visually group and align tiles.
3.  **Logical Layout:** The final contiguous image presented in the editor.

This audit reveals that the current implementation is heavily overloaded, blending UI concerns with complex coordinate transformations and state persistence, leading to a system that is difficult to maintain and prone to "silent" desynchronization.

---

## 1. Responsibilities & Ownership

### Jan 14, 2026 Update: Legacy Consolidation
As of Jan 14, the legacy `RowArrangementDialog` and its dedicated row-based image processing/preview paths have been removed. The system now exclusively uses the more flexible `GridArrangementDialog`. The `GridImageProcessor` and `GridPreviewGenerator` have been refactored to be standalone (removing inheritance from the now-deleted row counterparts).

- **GridArrangementDialog (Consolidated Orchestrator):** Handles UI construction, mouse/keyboard events, palette cycling, and tile management. that serves as the "God Object." It handles UI construction, mouse/keyboard events, palette cycling, and even raw image slicing via the `GridImageProcessor`.
- **GridArrangementManager (State Machine):** Tracks the logical mapping of tiles. However, it is "passive"—it relies on the Dialog to decide when to record history or how to calculate target slots.
- **GridGraphicsView (The Interactive Canvas):** This component is responsible for both *rendering* (drawing grid lines, dimming unselected tiles) and *complex logic* (panning, zooming, and the "marquee" drag-selection algorithm).
- **ROMWorkflowController (Persistence & Integration):** Triggers the dialog and manages the "Sidecar" files (JSON files saved next to the ROM that store the arrangement).

### Critical Ownership Issues
- **Service Logic in UI:** The logic for "slicing" an image into tiles exists inside the Dialog's initialization flow. If the image fails to load, the Dialog enters a broken state that is hard to recover from.
- **Transformation Leakage:** The `ArrangementBridge` (which converts Physical $\leftrightarrow$ Logical coordinates) is created by the Dialog but used by the Controller. This creates a tight coupling where the Controller must understand the internal result format of the Dialog.

---

## 2. Data & Control Flow

### State Mutation Chain
1.  **Action:** A user drags a tile on the Canvas.
2.  **Serialization:** The `GridGraphicsView` encodes the tile list into a string (e.g., `"1,2|0,1;0,2"`) to pass via standard Qt Drag-and-Drop.
3.  **Command Pattern:** The Dialog catches the drop, decodes the string, and creates a `CanvasPlaceItemsCommand`.
4.  **Bypassing Logic:** The command calls "No History" backdoors in the Manager (e.g., `_set_item_at_no_history`) to prevent infinite undo loops. This means any validation logic in the Manager's public `add_tile` method is completely bypassed.
5.  **Brute-Force Refresh:** On any change, the Dialog calls `_update_displays()`, which clears and re-renders the *entire* preview image from scratch using PIL, then converts it back to a Qt QPixmap.

---

## 3. Complexity & Structural Issues

### The "Emergent Behavior" Problem
- **Hidden ROM Reordering:** The order of tiles in the final ROM is implicitly derived from their top-to-bottom, left-to-right position on the arrangement canvas. If a user moves a tile one pixel to the left, it might accidentally "jump" ahead of another tile in the ROM sequence, potentially breaking the game's sprite rendering if it expects a specific index order.
- **Implicit Grid Rules:** When a user double-clicks a tile to "add" it, the system uses a hardcoded `width_hint = 16` to find the next empty slot. This often ignores the user's actual grid settings, causing tiles to appear in unexpected locations.

### Structural Weaknesses
- **State Redundancy:** The `GridArrangementManager` maintains **five separate collections** to track the same data (tiles, sets, groups, mapping, and order). If these ever drift apart, the system enters an undefined state.
- **String-Based Communication:** Using strings to pass tile data during Drag-and-Drop is error-prone. A single typo in the coordinate parser can cause a crash or silent data corruption.

---

## 4. Failure Modes & Risks

### Reliability Gaps
- **The Identity Gap:** Arrangements are saved based on the ROM file name and the hex offset. If the user shifts the offset by 1 byte, the arrangement is lost. If they rename the ROM, the arrangement is lost. There is no content-based hashing to verify if an arrangement still matches the sprite data.
- **Persistence Restoration:** While the system *detects* a saved arrangement, it doesn't auto-apply it. The user sees a message: "Saved arrangement found. Click 'Arrange Tiles' to re-apply." This adds friction to the workflow.
- **Performance:** For large sprites (e.g., a boss with 100+ tiles), the "Clear and Rebuild" strategy for UI updates causes noticeable lag, as the system performs dozens of PIL image operations and memory allocations on every mouse move.
- **Silent Failures:** If the `GridImageProcessor` fails to find a tile, it simply returns `None`, and the preview skips that tile. The user is not warned that their arrangement is now incomplete.