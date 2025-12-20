"""Validate SESSION_DEPENDENT_FIXTURES contains all transitive dependencies.

This test ensures that the static whitelist of session-dependent fixtures
is complete. If someone creates a new fixture that depends on session_managers
but forgets to add it to SESSION_DEPENDENT_FIXTURES, this test will fail
and tell them exactly what to add.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.fixtures.core_fixtures import SESSION_DEPENDENT_FIXTURES

if TYPE_CHECKING:
    from _pytest.fixtures import FixtureRequest


def test_session_dependent_fixtures_complete(request: FixtureRequest) -> None:
    """Fail if fixtures depending on session_managers aren't in the list.

    This test introspects pytest's fixture manager to find all fixtures
    that transitively depend on session_managers, and verifies they're
    all listed in SESSION_DEPENDENT_FIXTURES.

    The test prevents parallel execution issues where a fixture wrapping
    session_managers runs in parallel when it shouldn't.
    """
    # Get the fixture manager
    fm = request.config.pluginmanager.get_plugin("funcmanage")
    if fm is None:
        pytest.skip("Fixture manager not available")

    arg2fixturedefs = getattr(fm, '_arg2fixturedefs', None)
    if arg2fixturedefs is None:
        pytest.skip("Cannot introspect fixture definitions")

    # Build dependency graph: fixture_name -> set of fixture names it depends on
    deps: dict[str, set[str]] = {}
    for name, fixturedefs in arg2fixturedefs.items():
        if fixturedefs:
            # Use the last fixturedef (most specific scope)
            fixturedef = fixturedefs[-1]
            argnames = getattr(fixturedef, 'argnames', ())
            deps[name] = set(argnames)

    # BFS from session_managers to find all fixtures that depend on it
    session_dependents: set[str] = {'session_managers'}
    changed = True
    while changed:
        changed = False
        for name, fixture_deps in deps.items():
            if name not in session_dependents and fixture_deps & session_dependents:
                session_dependents.add(name)
                changed = True

    # Check for missing entries
    missing = session_dependents - SESSION_DEPENDENT_FIXTURES

    # Filter out private/autouse fixtures (they start with _ and run for all tests)
    # These are handled separately by the test infrastructure
    missing = {m for m in missing if not m.startswith('_')}

    if missing:
        pytest.fail(
            f"Fixtures depending on session_managers not in SESSION_DEPENDENT_FIXTURES: "
            f"{sorted(missing)}.\n\n"
            f"Add them to tests/fixtures/core_fixtures.py around line 78:\n"
            f"SESSION_DEPENDENT_FIXTURES: frozenset[str] = frozenset({{\n"
            + "".join(f"    '{m}',\n" for m in sorted(missing))
            + "    ...\n}})"
        )


def test_session_dependent_fixtures_no_stale_entries(request: FixtureRequest) -> None:
    """Warn if SESSION_DEPENDENT_FIXTURES contains fixtures that don't exist.

    This helps catch stale entries after fixtures are removed or renamed.
    We use a warning rather than failure because fixtures may be defined
    in conftest files that aren't always loaded.
    """
    fm = request.config.pluginmanager.get_plugin("funcmanage")
    if fm is None:
        pytest.skip("Fixture manager not available")

    arg2fixturedefs = getattr(fm, '_arg2fixturedefs', None)
    if arg2fixturedefs is None:
        pytest.skip("Cannot introspect fixture definitions")

    known_fixtures = set(arg2fixturedefs.keys())

    # Find entries in SESSION_DEPENDENT_FIXTURES that don't exist
    stale = SESSION_DEPENDENT_FIXTURES - known_fixtures

    if stale:
        # This is a warning, not a failure, because fixtures may be defined
        # in integration/conftest.py or other files that aren't always loaded
        import warnings

        warnings.warn(
            f"SESSION_DEPENDENT_FIXTURES contains entries not found in current "
            f"fixture definitions: {sorted(stale)}. These may be stale or "
            f"defined in conftest files not loaded for this test run.",
            UserWarning,
            stacklevel=1,
        )
