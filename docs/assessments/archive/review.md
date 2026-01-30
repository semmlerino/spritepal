The best structure for 50+ signals + deep chains

Keep Qt signals as UI intents + UI notifications. Make the workflow chain explicit in code.

Rule of thumb

Views emit intents (user did X).

Coordinator/Workspace calls controller methods (explicit workflow).

Controller updates model + emits “deltas” (what changed).

Workspace applies deltas to views (targeted refresh), using QSignalBlocker / guards to avoid feedback loops.

Your “Alignment Changed (7 layers)” chain is basically this already, but it can be made less fragile by collapsing “signal relay layers” into direct calls where the only reason for a signal is “Qt needs it.” 

 

What I’d change in your architecture (high leverage)

Replace “many tiny update signals” with 1–3 delta signals

Keep alignment_updated(ai_id) if it’s working, but consider evolving toward:

mapping_changed(ai_id, change: MappingChange) and palette_changed(change: PaletteChange)

This reduces fan-out + “which signal do I emit?” bugs. 

 

Bundle parameter-heavy signals into dataclasses

Instead of alignment_changed(x, y, flip_h, flip_v, scale, sharpen, resampling), emit alignment_changed(AlignmentState(...)).

You get versionable payloads, fewer broken connections, and easier tracing. 

 

Make chains “command → result” rather than “signal → signal → signal”

Keep the undo/command stack (good call). But once you’re in the controller, prefer direct method calls and return values.

Signals are best for notification, not for driving multi-step logic. 

 

Centralize selection state

You have ai_frame_selected + game_frame_selected + canvas sync behavior. Unify into one SelectionModel (ai_id, game_id, mapping_id).

This alone kills a lot of “wrong capture selected” / “edits applied to stale selection” edge cases. 
 

Add a first-class trace ID for cascades

For any top-level action (drag, drop, inject), generate action_id.

Include it in logs (and optionally delta signals) so debugging “7 layers later” becomes trivial.

Signal taxonomy that keeps systems sane

If you enforce just this naming + intent split, complexity drops fast:

*_requested / *_changed from Views → Workspace (intents)

*_changed / *_updated from Controller → Workspace (model deltas)

Avoid View → View connections entirely (everything routes through Workspace)

You’re already mostly doing this; the remaining step is to stop using signals to perform work once you’re past the UI boundary. 

 