"""Regression tests for xdist collection policy.

These tests verify that the PARALLEL BY DEFAULT policy is enforced correctly:
- Unmarked tests run in parallel (no serial grouping)
- Tests using session_managers (or dependent fixtures) are auto-serialized
- Tests marked @pytest.mark.parallel_unsafe are forced to serial
- Tests already marked with xdist_group are not modified

The actual implementation is in conftest.py::pytest_collection_modifyitems.
These tests use a minimal reimplementation to test the logic in isolation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

# Import canonical list from core_fixtures to prevent drift
from tests.fixtures.core_fixtures import SESSION_DEPENDENT_FIXTURES


def collection_policy_logic(
    has_xdist: bool,
    workers: str | None,
    items: list[Any],
) -> None:
    """Minimal reimplementation of the xdist grouping logic from conftest.py.

    This mirrors the logic in pytest_collection_modifyitems for isolated testing.
    If conftest.py changes, this should be updated to match.

    PARALLEL BY DEFAULT Policy:
    1. Skip if xdist not active or workers == 0
    2. Skip items with existing xdist_group
    3. Force serial for parallel_unsafe marked items
    4. Force serial for items using session_managers (direct or transitive)
    5. All other items run in parallel (no marker added)
    """
    if not has_xdist:
        return

    if not workers or workers == "0":
        return

    serial_group = pytest.mark.xdist_group("serial")

    for item in items:
        # Skip tests already marked with xdist_group
        if item.get_closest_marker("xdist_group"):
            continue

        # Force serial if marked parallel_unsafe
        if item.get_closest_marker("parallel_unsafe"):
            item.add_marker(serial_group)
            continue

        # Auto-detect session fixture usage
        fixture_names = set(getattr(item, 'fixturenames', []))
        if fixture_names & SESSION_DEPENDENT_FIXTURES:
            item.add_marker(serial_group)
            continue

        # DEFAULT: No marker = runs in parallel (the key policy)


class FakeItem:
    """Minimal fake pytest Item for testing collection hooks."""

    def __init__(
        self,
        nodeid: str = "test_example.py::test_func",
        markers: dict[str, object] | None = None,
        fixturenames: list[str] | None = None,
    ) -> None:
        self.nodeid = nodeid
        self._markers: dict[str, object] = markers or {}
        self.fixturenames = fixturenames or []
        self._added_markers: list[pytest.Mark] = []

    def get_closest_marker(self, name: str) -> object | None:
        """Return marker if present, else None."""
        return self._markers.get(name)

    def add_marker(self, marker: pytest.Mark) -> None:
        """Record added markers for verification."""
        self._added_markers.append(marker)

    def has_serial_group(self) -> bool:
        """Check if item was assigned to the serial xdist group."""
        return any(
            marker.name == "xdist_group" and marker.args == ("serial",)
            for marker in self._added_markers
        )


class TestXdistCollectionPolicy:
    """Test the PARALLEL BY DEFAULT xdist collection policy.

    These tests verify the POLICY, not the full hook implementation.
    The hook also validates skip_thread_cleanup which is tested separately.
    """

    def test_unmarked_test_runs_parallel(self) -> None:
        """Unmarked tests should run in parallel (no serial group)."""
        item = FakeItem()

        collection_policy_logic(has_xdist=True, workers="auto", items=[item])

        assert not item.has_serial_group(), (
            "Unmarked tests should NOT get serial group (parallel by default)"
        )

    def test_session_managers_test_gets_serial_group(self) -> None:
        """Tests using session_managers must be grouped to serial worker."""
        item = FakeItem(fixturenames=["session_managers"])

        collection_policy_logic(has_xdist=True, workers="auto", items=[item])

        assert item.has_serial_group(), (
            "Tests using session_managers must be serialized"
        )

    def test_managers_fixture_gets_serial_group(self) -> None:
        """Tests using managers fixture (depends on session_managers) must serialize."""
        item = FakeItem(fixturenames=["managers"])

        collection_policy_logic(has_xdist=True, workers="auto", items=[item])

        assert item.has_serial_group(), (
            "Tests using managers fixture must be serialized"
        )

    def test_parallel_unsafe_marker_forces_serial(self) -> None:
        """Tests marked parallel_unsafe must be serialized."""
        item = FakeItem(markers={"parallel_unsafe": pytest.mark.parallel_unsafe})

        collection_policy_logic(has_xdist=True, workers="auto", items=[item])

        assert item.has_serial_group(), (
            "Tests marked @pytest.mark.parallel_unsafe must be serialized"
        )

    def test_isolated_managers_runs_parallel(self) -> None:
        """Tests using isolated_managers should run parallel."""
        item = FakeItem(fixturenames=["isolated_managers", "tmp_path"])

        collection_policy_logic(has_xdist=True, workers="auto", items=[item])

        assert not item.has_serial_group(), (
            "Tests using isolated_managers should run parallel"
        )

    def test_existing_xdist_group_not_modified(self) -> None:
        """Tests with existing xdist_group should not be modified."""
        existing_marker = pytest.mark.xdist_group("custom")
        item = FakeItem(markers={"xdist_group": existing_marker})

        collection_policy_logic(has_xdist=True, workers="auto", items=[item])

        assert not item.has_serial_group(), (
            "Tests with existing xdist_group should not be modified"
        )
        assert len(item._added_markers) == 0, (
            "No markers should be added to tests with existing xdist_group"
        )

    def test_no_grouping_without_xdist_plugin(self) -> None:
        """No grouping should happen if xdist plugin is not active."""
        item = FakeItem(fixturenames=["session_managers"])

        collection_policy_logic(has_xdist=False, workers="auto", items=[item])

        assert len(item._added_markers) == 0, (
            "No markers should be added when xdist is not active"
        )

    def test_no_grouping_with_zero_workers(self) -> None:
        """No grouping should happen if -n 0 is used."""
        item = FakeItem(fixturenames=["session_managers"])

        collection_policy_logic(has_xdist=True, workers="0", items=[item])

        assert len(item._added_markers) == 0, (
            "No markers should be added when -n 0 is specified"
        )

    def test_no_grouping_without_n_option(self) -> None:
        """No grouping should happen if -n is not specified."""
        item = FakeItem(fixturenames=["session_managers"])

        collection_policy_logic(has_xdist=True, workers=None, items=[item])

        assert len(item._added_markers) == 0, (
            "No markers should be added when -n is not specified"
        )

    def test_multiple_items_processed_correctly(self) -> None:
        """Multiple items should be processed with correct policy."""
        unmarked = FakeItem(nodeid="test_a.py::test_unmarked")
        session_test = FakeItem(
            nodeid="test_b.py::test_session",
            fixturenames=["session_managers"],
        )
        parallel_unsafe = FakeItem(
            nodeid="test_c.py::test_unsafe",
            markers={"parallel_unsafe": pytest.mark.parallel_unsafe},
        )
        isolated_test = FakeItem(
            nodeid="test_d.py::test_isolated",
            fixturenames=["isolated_managers", "tmp_path"],
        )
        custom_group = FakeItem(
            nodeid="test_e.py::test_custom",
            markers={"xdist_group": pytest.mark.xdist_group("my_group")},
        )

        items = [unmarked, session_test, parallel_unsafe, isolated_test, custom_group]
        collection_policy_logic(has_xdist=True, workers="4", items=items)

        assert not unmarked.has_serial_group(), "Unmarked test should run parallel"
        assert session_test.has_serial_group(), "session_managers test should be serialized"
        assert parallel_unsafe.has_serial_group(), "parallel_unsafe test should be serialized"
        assert not isolated_test.has_serial_group(), "isolated_managers test should run parallel"
        assert not custom_group.has_serial_group(), "Custom xdist_group test should NOT be modified"


class TestParallelByDefaultPolicyDocumentation:
    """Verify the policy matches documentation claims."""

    def test_policy_is_parallel_by_default(self) -> None:
        """Verify the default is parallel, not serial."""
        # Create many unmarked items
        items = [
            FakeItem(nodeid=f"test_{i}.py::test_func")
            for i in range(10)
        ]

        collection_policy_logic(has_xdist=True, workers="auto", items=items)

        # All unmarked tests should run parallel (no serial group)
        for item in items:
            assert not item.has_serial_group(), (
                f"{item.nodeid}: Unmarked tests should NOT be serialized by default"
            )

    def test_only_session_dependent_tests_serialized(self) -> None:
        """Verify only session-dependent tests are serialized."""
        # Create items with different characteristics
        items = []
        for i in range(5):
            # Even: unmarked (should be parallel)
            # Odd: session_managers (should be serial)
            if i % 2 == 0:
                items.append(FakeItem(nodeid=f"test_{i}.py::test_unmarked"))
            else:
                items.append(FakeItem(
                    nodeid=f"test_{i}.py::test_session",
                    fixturenames=["session_managers"]
                ))

        collection_policy_logic(has_xdist=True, workers="auto", items=items)

        for i, item in enumerate(items):
            if i % 2 == 0:
                assert not item.has_serial_group(), (
                    f"{item.nodeid}: Unmarked test should run parallel"
                )
            else:
                assert item.has_serial_group(), (
                    f"{item.nodeid}: session_managers test should be serialized"
                )
