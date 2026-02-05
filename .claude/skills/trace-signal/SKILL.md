---
name: trace-signal
description: "Trace a Qt signal from definition through all connections to handlers"
argument-hint: "[signal_name]"
context: fork
agent: Explore
---

Trace the Qt signal `$ARGUMENTS` through the codebase. Present a complete connection map.

**Steps:**

1. **Find definition**: Search for `$ARGUMENTS = Signal(` to locate where the signal is defined. Note the class and file.

2. **Find emissions**: Search for `$ARGUMENTS.emit(` or `self.$ARGUMENTS.emit(` to find all emission points. Note file:line for each.

3. **Find connections**: Search for `$ARGUMENTS.connect(` to find all connection sites. For each connection, note:
   - The file:line where `.connect()` is called
   - The handler method/function being connected

4. **Find handlers**: For each connected handler, locate its definition. Note file:line.

5. **Present the trace** in this format:

```
Signal: [signal_name]
Defined: [class] in [file:line]
Arguments: [signal signature]

Emission points:
  1. [file:line] — [context/when emitted]

Connections → Handlers:
  1. [connection file:line] → [handler_name] at [handler file:line]
  2. ...
```

If the signal fans out to 3+ handlers, flag it as a multiplexing hotspot.
