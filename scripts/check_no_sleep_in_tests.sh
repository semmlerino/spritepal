#!/usr/bin/env bash
# Check that tests don't use time.sleep() (blocks Qt event loop).
# Mark intentional uses with: # sleep-ok
set -eu

violations=$(grep -rn "time\.sleep" tests/ --include="*.py" | grep -v "# sleep-ok" || true)

if [ -n "$violations" ]; then
    echo "ERROR: time.sleep() found in tests without '# sleep-ok' marker:"
    echo "$violations"
    echo ""
    echo "Use qtbot.wait(ms), QApplication.processEvents(), or os.utime() instead."
    echo "If the sleep is intentional (e.g., concurrency test), add '# sleep-ok' comment."
    exit 1
fi

echo "OK: No unmarked time.sleep() in tests."
