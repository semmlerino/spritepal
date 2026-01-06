# UI Redesign Plan

## 1. Issue List (Prioritized)

| Rank | Location | Problem | Impact | Recommended Fix |
| :--- | :--- | :--- | :--- | :--- |
| **1** | `ROMExtractionPanel` (ROM Path) | **Path Truncation:** The `ROMFileWidget` likely displays the full absolute path in a `QLineEdit` or `QLabel`, pushing the "Browse" button off-screen or clipping the text at the end (the filename). | User cannot see which file is actually loaded if the path is deep. | Implement **path eliding** (middle truncation: `/home.../game.sfc`) for display, while keeping the full path in the tooltip. Use a `QHBoxLayout` with a stretch factor for the text. |
| **2** | `SpriteEditorWorkspace` (Header) | **Awkward Control Placement:** Undo/Redo buttons are floating in a custom "Header" `QWidget` above the stack, disconnected from the actual canvas in `VRAMEditorPage`/`ROMWorkflowPage`. | High cognitive load; user has to look away from the canvas to find basic tools. | Move Undo/Redo/Save to a **main QToolBar** attached to the `QMainWindow` or the top of the specific editor pane, using standard icons. |
| **3** | `MainWindow` -> `ROMWorkflowPage` | **Nested Splitters:** The Main Window has a Splitter (Nav vs Preview). The `ROMWorkflowPage` *also* has a Splitter (Nav vs Canvas). | "Boxed-in" feeling; double scrollbars; confusing resizing behavior where expanding one panel doesn't give space where expected. | **Flatten the hierarchy.** The "ROM Navigation" should be a Dock Widget or a side panel in the main layout, not nested deep inside a stacked widget page. |
| **4** | `ROMExtractionPanel` (Output Name) | **Inline Label/Input Layout:** The "Output Name:" label and input are in a simple `QHBoxLayout` without clear validation or width constraints. | The input field can get crushed if the panel is resized too small. | Stack the Label *above* the Input (Vertical layout) for the side panel to save horizontal space, or use a `QFormLayout` with defined field growth policies. |
| **5** | `VRAMEditorPage` (Tabs) | **Hidden Hierarchy:** The "Extract", "Edit", "Inject" workflow is hidden behind tabs that look like peer options rather than a sequence. | Users might edit without extracting or try to inject without editing. | Switch to a **Stepper UI** or a "Workflow Bar" at the top (Breadcrumbs) to show the linear process, or keep tabs but number them: "1. Extract", "2. Edit". |
| **6** | Global | **Inconsistent Sizing:** `ROMWorkflowPage` hardcodes `setMinimumWidth(700)`, while `MainWindow` enforces `(1000, 700)`. `VRAMEditorPage` enforces `500`. | Window resizing feels "stiff"; the window refuses to shrink below a large size even if content implies it should. | Remove hardcoded `setMinimumWidth` on high-level containers. Use `QScrollArea` with `setWidgetResizable(True)` for panels that might shrink. |
| **7** | `Offset Slider` (Styles) | **Visual Noise:** The custom stylesheet in `ROMWorkflowPage` (green/gray colors) likely conflicts with the native or system theme (Dark Mode issues). | Controls look "patched in" and unprofessional; contrast issues on different OS themes. | Remove ad-hoc `setStyleSheet` strings. Move to a centralized `theme.qss` file and use Qt's palette abstraction or a coherent color system variable set. |
| **8** | `SpriteSelectorWidget` | **List Readability:** The list of sprites likely shows raw hex offsets or internal names without visual grouping. | Hard to scan for specific assets. | Use a `QTreeWidget` with categories ("Hero", "Enemies", "UI") instead of a flat list. Add a small icon/thumbnail column if possible. |
| **9** | `ManualOffsetSection` | **Buried Functionality:** Manual offset controls are in a collapsible section or separate dialog. | Power users feel slowed down accessing direct memory addresses. | Integrate the "Go to Address" field directly into the top toolbar or the bottom status bar for quick access (like a VS Code "Go to Line"). |
| **10** | `PreviewPanel` | **Context Switching:** The preview panel is in the Main Window's right pane, but editing happens in the Center. | User edits in center, looks right to see result. | (Long term) Dock the preview *inside* the Editor workspace, or make it a floating/dockable window so users can place it next to the pixels they are changing. |

## 2. Proposed New Layout

**Concept:** Move away from the "Wizard/Page" stack and toward a modern **IDE Layout** (Visual Studio Code style).

*   **Left Sidebar (Activity Bar + Panel):** Handles "Selection" (ROM Browser, Sprite List, File Tree).
*   **Center (Editor Area):** The main Canvas. Tabs for different sprites if needed.
*   **Right Sidebar (Inspector):** Palette, Tool Options, Export Settings.
*   **Top (Toolbar):** Global actions (Undo, Redo, Zoom, Save).
*   **Bottom (Status):** Offset info, zoom level.

**ASCII Wireframe:**

```text
+-----------------------------------------------------------------------+
|  [Toolbar]  Open ROM  |  Save  |  Undo  Redo  |  Zoom: 100%         |
+----------------+-----------------------------------+------------------+
| LEFT PANEL     |  CENTER CANVAS                    | RIGHT PANEL      |
| (Nav/Source)   |                                   | (Tools/Props)    |
|                |                                   |                  |
| [ ROM Name ]   |  +-----------------------------+  | [ Palette ]      |
| /path/to...    |  |                             |  | +--------------+ |
|                |  |                             |  | |#|#|#|#|      | |
| [ Search... ]  |  |      ( Sprite Edit )        |  | +--------------+ |
|                |  |                             |  |                  |
| > Hero         |  |                             |  | [ Tool Opts ]    |
|   - Idle 01    |  |          (Grid)             |  |  Brush Size: 3   |
|   - Jump 02    |  |                             |  |  [ ] Mask        |
| > Enemies      |  |                             |  |                  |
| > Effects      |  +-----------------------------+  | [ Export ]       |
|                |                                   |  Name: sprite_01 |
|                |                                   |  [ Extract ]     |
|                |                                   |                  |
+----------------+-----------------------------------+------------------+
| [Status Bar]  ROM: Loaded  |  Offset: 0x123456  |  Ready              |
+-----------------------------------------------------------------------+
```

## 3. Component + Style System

**Typography Scale:**
*   **Label (Small):** 11px (Secondary info, paths).
*   **Body (Regular):** 13px (Standard UI inputs, list items).
*   **Header (Section):** 14px Bold (Panel titles like "ROM NAVIGATION").
*   **Title (Window):** 16px (Main tab titles).

**Sizing Tokens:**
*   **Button Height:** 32px (Standard), 24px (Small/Tool).
*   **Input Height:** 32px.
*   **Icon Size:** 16x16 (Small buttons), 24x24 (Toolbar).
*   **Scrollbars:** Standard OS width.

**Spacing Tokens:**
*   `SPACING_XS` (4px): Between related items (Label + Input).
*   `SPACING_SM` (8px): Between groups in a panel.
*   `SPACING_MD` (16px): Panel margins / Gutters between columns.
*   `SPACING_LG` (24px): Section dividers.

**Truncation Rules:**
*   **File Paths:** Always use `ElideMiddle` (`/home/.../folder/rom.sfc`).
*   **Sprite Names:** `ElideRight` (`Enemy - Walk...`).
*   **Tooltips:** MANDATORY for any truncated element.

## 4. Behavior Rules

1.  **Resizing:**
    *   **Center Canvas** has `StretchFactor = 1`. It absorbs all extra space.
    *   **Left/Right Panels** have fixed `MaximumWidth` (e.g., 300px) or `StretchFactor = 0`. They do not grow endlessly.
    *   **Minimum Window Width:** 800px (down from 1000px).
2.  **Collapsing:**
    *   Left and Right panels must be collapsible (via a toggle button or splitter handle double-click) to give full screen to the canvas.
3.  **Scrollbars:**
    *   **Never** show a scrollbar on the *entire* window.
    *   Only `QScrollArea` widgets inside the Left/Right panels should scroll.
    *   The Canvas handles its own panning (internal scroll).

## 5. Quick Wins vs. Deeper Refactor

**Phase 1: Quick Wins (Ship Today)**
*   [ ] **Fix Path Clipping:** Update `ROMFileWidget` to use `QFontMetrics.elidedText` for the path display.
*   [ ] **Move Undo/Redo:** Extract the Undo/Redo buttons from `SpriteEditorWorkspace` header and create a standard `QToolBar` in `MainWindow`.
*   [ ] **Fix Output Input:** Change `ROMExtractionPanel` "Output Name" layout to `QVBoxLayout` (Label atop Input) to prevent crushing.
*   [ ] **Standardize Margins:** Find all hardcoded `setContentsMargins(12, 12, 12, 12)` and replace with the `SPACING` constants.

**Phase 2: Layout Overhaul (Refactor)**
*   [ ] **Dock Widget System:** Replace `QSplitter` + `QStackedWidget` with `QMainWindow`'s native `QDockWidget` system. This gives user-resizable, floatable panels for free.
*   [ ] **Unified Navigation:** Merge `ExtractionWorkspace` and `ROMWorkflowPage` left panels into a single "Explorer" dock.
*   [ ] **CSS Theme:** Move all inline styles (`setStyleSheet`) to a `theme.qss` file.

## 6. Acceptance Checklist

*   [ ] **Window Resize:** Resizing the window to 800x600 does not cut off any buttons or inputs (scrollbars appear in panels only).
*   [ ] **Path Readability:** Loading a ROM with a 100-character path shows the filename clearly (e.g., `.../my_game.sfc`).
*   [ ] **Hierarchy:** "Undo" button is always visible in the toolbar, regardless of which tab is active.
*   [ ] **Canvas Priority:** When expanding the window, the Pixel Editor (Canvas) gets the space, not the buttons/lists.
*   [ ] **Inputs:** "Output Name" field is at least 150px wide.
*   [ ] **Contrast:** All text passes WCAG AA contrast against panel backgrounds (check the custom green slider colors).
