#!/bin/bash
# Post-agent lint check hook
# Runs ruff and basedpyright on changed Python files after agent completion

# Get changed .py files compared to HEAD
git_root=$(git rev-parse --show-toplevel 2>/dev/null)
cwd=$(pwd)
rel_prefix="${cwd#$git_root/}"

# Get changed files and filter to current directory's Python files
changed=$(git diff --name-only HEAD 2>/dev/null | grep "^${rel_prefix}/" | grep '\.py$' | sed "s|^${rel_prefix}/||" || true)

if [ -z "$changed" ]; then
    exit 0
fi

# Run lint checks
lint_output=$(echo "$changed" | xargs uv run ruff check --no-fix 2>&1 | head -40)
type_output=$(echo "$changed" | xargs uv run basedpyright 2>&1 | grep -E '(error|warning)' | head -20)

# Check if there are actual issues
has_lint_issues=false
has_type_issues=false

if [ -n "$lint_output" ] && ! echo "$lint_output" | grep -q "All checks passed"; then
    has_lint_issues=true
fi

if [ -n "$type_output" ] && ! echo "$type_output" | grep -q "0 errors, 0 warnings"; then
    has_type_issues=true
fi

# Exit 2 sends stderr to Claude as feedback
if [ "$has_lint_issues" = true ] || [ "$has_type_issues" = true ]; then
    echo "=== POST-AGENT LINT CHECK FOUND ISSUES ===" >&2
    if [ "$has_lint_issues" = true ]; then
        echo "" >&2
        echo "Ruff:" >&2
        echo "$lint_output" >&2
    fi
    if [ "$has_type_issues" = true ]; then
        echo "" >&2
        echo "Pyright:" >&2
        echo "$type_output" >&2
    fi
    echo "" >&2
    echo "Please fix these issues before continuing." >&2
    exit 2
fi

exit 0
