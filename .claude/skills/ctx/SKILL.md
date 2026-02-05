---
name: ctx
description: "Preload architectural context for a subsystem. Use at session start before touching files."
argument-hint: "[compositor|palette|injection|frame-mapping|all]"
---

Load architectural context for the specified subsystem.

**Instructions:**

1. If `$ARGUMENTS` is "all", read all four rule files listed below. Otherwise, read the matching rule file.
2. After reading, summarize the key invariants and mental model in 3-5 bullet points.
3. Note any cross-cutting concerns between the requested subsystem and others.

**Rule files:**
- `compositor` → `.claude/rules/compositor.md`
- `palette` → `.claude/rules/palette.md`
- `injection` → `.claude/rules/injection.md`
- `frame-mapping` → `.claude/rules/frame-mapping.md`

These rules ARE the architectural reference. No additional files need to be read for context — only read source code when you need implementation details beyond what the rules provide.
