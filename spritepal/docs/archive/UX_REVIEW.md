# SpritePal UX Review

## Executive Summary
The current SpritePal UI is functional and follows a logical "Input -> Settings -> Action" flow. However, as features have grown, the vertical density of the "Left Panel" has increased, leading to potential usability issues on standard displays (1080p or smaller). The primary concern is the visibility of critical action buttons and the efficient use of screen real estate.

## Detailed Findings

### 1. Layout & Navigation
*   **Issue: Action Button Visibility.** The primary action buttons ("Extract", "Open in Editor") and the "Output Settings" group are located at the bottom of the Left Panel, *below* the Tab Widget. Since the Tab Widget's content (especially the ROM Extraction panel) can be tall, these critical controls can be pushed off-screen, requiring the user to scroll or resize the window.
*   **Issue: Splitter Ratio.** The default split ratio (0.45 for left panel) is somewhat rigid.
*   **Proposal:** Restructure the Left Panel into two distinct zones:
    *   **Content Zone (Top, Scrollable):** Contains the `extraction_tabs`. This area should absorb all extra vertical space.
    *   **Action Zone (Bottom, Fixed):** Contains the "Output Settings" and Action Buttons. This area should be "pinned" to the bottom, ensuring buttons are *always* visible regardless of tab content height.

### 2. VRAM Extraction Panel (`ExtractionPanel`)
*   **Issue: Hidden Complexity.** The "Custom Range" preset reveals a large set of controls (Slider, Spinbox, Step Combo, Quick Jump) that drastically changes the panel height.
*   **Issue: Dense UI.** The panel inherits from `QGroupBox` ("Input Files") and packs everything inside.
*   **Proposal:**
    *   Wrap the "Custom Offset Controls" in a collapsible widget or ensure the parent container scrolls smoothly when this section expands.
    *   Consider moving "Extraction Mode" to the top, as it dictates which Drop Zones are required.

### 3. ROM Extraction Panel (`ROMExtractionPanel`)
*   **Issue: Vertical Stacking.** The panel vertically stacks File Selection, Navigation, Mode, Manual Offset Button, Status, CGRAM, and Output Name. This contributes significantly to the height issue.
*   **Issue: Disjointed Workflow.** The "Open Manual Offset Control" button launches a modal/dialog. While this keeps the main UI clean, it forces a context switch.
*   **Proposal:**
    *   Group related controls (e.g., ROM File and CGRAM File) closer together if possible, or use tabs/collapsible sections within the panel if complexity grows.
    *   The "Manual Offset Dialog" is a good pattern for advanced features, but ensure the main panel remains useful for the "Happy Path" (scanning/presets) without needing the dialog.

### 4. Visual Hierarchy & Feedback
*   **Issue: Silent Disable.** The "Extract" button is disabled until conditions are met (e.g., VRAM loaded). Users might not know *what* is missing.
*   **Proposal:**
    *   Implement a "Validation Status" indicator or tooltip on the disabled Extract button that explicitly lists missing requirements (e.g., "Requires VRAM file", "Select a sprite").
    *   Use distinct visual styling for the "Action Zone" (e.g., a subtle background color) to separate it from the configuration inputs.

## Actionable Recommendations (Priority Order)

1.  **[High] Fix Left Panel Layout:** Pin the "Output Settings" and "Action Buttons" to the bottom of the panel. Make the Tab Widget the only expanding/scrollable element.
2.  **[Medium] Add ScrollAreas:** Ensure the contents of `ExtractionPanel` and `ROMExtractionPanel` are wrapped in `QScrollArea` so they don't clip if the window is small.
3.  **[Medium] Validation Feedback:** Add tooltips to disabled action buttons explaining why they are disabled.

