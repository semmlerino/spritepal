UX Spec: Frame Mapping Pairing Mode (Order‑Agnostic, 1:1)
  This spec reframes the workflow around “pair any AI frame with any game frame,” removes sequential cues, and enforces one‑to‑one links with replace confirmation.

  Goals

  - Make it explicit that frame order does not matter; pairing is freeform.
  - Reduce steps to link a pair and adjust alignment in one continuous flow.
  - Enforce one‑to‑one mapping with clear replace behavior.

  Non‑Goals

  - No auto‑matching/similarity scoring in this iteration.
  - No changes to file formats or underlying mapping model.

  Primary Layout (current 3‑panel structure, re‑weighted)

  - Left panel: AI frames list with status badges and search/filter. (ui/frame_mapping/views/frame_browser_panel.py)
  - Center panel: Comparison view defaulting to Overlay once both frames are selected; alignment CTA visible. (ui/frame_mapping/views/comparison_panel.py)
  - Right panel: Game frames grid/list with thumbnails, search/filter, and “Link” interaction. (ui/frame_mapping/views/frame_browser_panel.py)
  - Secondary: Mapping table becomes collapsible “Mappings” drawer for audit/remove. (ui/frame_mapping/views/mapping_panel.py)

  Primary Flow

  - Load AI frames + import captures; empty state explains “order doesn’t matter.” (ui/workspaces/frame_mapping_workspace.py)
  - Select AI frame → game frames display with linked/unlinked badges.
  - Click a game frame card to link; selection stays on the AI frame.
  - After linking, auto‑switch to Overlay view and surface “Adjust alignment.”
  - Alignment edits keep both selections intact and update status without refresh jumps.

  Key Interactions

  - Linking: single click (or double‑click) on a game frame card.
  - Replace confirmation: if the game frame is already linked, show modal confirmation to replace. (ui/workspaces/frame_mapping_workspace.py)
  - Alignment: visible button in overlay view; double‑click still works as shortcut. (ui/frame_mapping/views/comparison_panel.py)
  - Auto‑advance: optional toggle, off by default (“Auto‑advance to next unmapped AI frame”).
  - Search/Filter: text search + “Unlinked only” on both lists.

  States & Feedback

  - Empty state: “Load AI frames and import captures. Order doesn’t matter.”
  - Link success: status bar message and badge updates in both lists.
  - Replace: clear confirmation text with both AI names, explicit Replace/Cancel.
  - Alignment hint: “Overlay active. Double‑click to adjust.” shown near comparison.

  Copy (example strings)

  - Header helper: “Pair any AI frame with any game frame. Order doesn’t matter.”
  - Game frame tooltip (linked): “Linked to AI: <name>. Click to replace.”
  - Replace dialog: “Replace link? ‘<game frame>’ is linked to ‘<AI A>’. Replace with ‘<AI B>’?”

  Acceptance Criteria

  - Linking does not auto‑advance by default and does not clear selection.
  - One game frame can only be linked to one AI frame at a time.
  - Replace confirmation appears when linking to an already‑linked game frame.
  - Overlay view becomes the default when both frames are selected.
  - Search/filter works on both AI and game frame lists.

  Edge Cases / Risks

  - Duplicate game frame IDs or missing preview PNGs still show actionable list items.
  - Large capture sets require a fast grid/list; avoid full refresh on every link.
  - Filtering must not hide the currently selected AI frame without warning.