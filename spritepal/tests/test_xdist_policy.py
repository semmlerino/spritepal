"""Regression tests for xdist collection policy.

These tests verify that the serial-by-default policy is enforced correctly:
- Unmarked tests must be grouped to the serial worker
- Tests marked @pytest.mark.parallel_safe must NOT get serial grouping
- Tests already marked with xdist_group should not be modified

The actual implementation is in conftest.py::pytest_collection_modifyitems.
These tests use a minimal reimplementation to test the logic in isolation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest

if TYPE_CHECKING:
    pass


def collection_policy_logic(
    has_xdist: bool,
    workers: str | None,
    items: list[Any],
) -> None:
    """Minimal reimplementation of the xdist grouping logic from conftest.py.

    This mirrors the logic in pytest_collection_modifyitems for isolated testing.
    If conftest.py changes, this should be updated to match.

    The canonical logic is:
    1. Skip if xdist not active or workers == 0
    2. Skip items with existing xdist_group
    3. Allow parallel_safe items to distribute (no marker added)
    4. Add serial group to everything else
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

        # Tests explicitly marked parallel_safe can distribute to any worker
        if item.get_closest_marker("parallel_safe"):
            continue

        # Everything else runs serial
        item.add_marker(serial_group)


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
        for marker in self._added_markers:
            if marker.name == "xdist_group" and marker.args == ("serial",):
                return True
        return False


@pytest.mark.parallel_safe
class TestXdistCollectionPolicy:
    """Test the serial-by-default xdist collection policy.

    These tests verify the POLICY, not the full hook implementation.
    The hook also validates skip_thread_cleanup which is tested separately.
    """

    def test_unmarked_test_gets_serial_group(self) -> None:
        """Unmarked tests must be grouped to serial worker."""
        item = FakeItem()

        collection_policy_logic(has_xdist=True, workers="auto", items=[item])

        assert item.has_serial_group(), (
            "Unmarked tests must be assigned to xdist_group('serial')"
        )

    def test_parallel_safe_test_not_serialized(self) -> None:
        """Tests marked parallel_safe must NOT get serial group."""
        item = FakeItem(markers={"parallel_safe": pytest.mark.parallel_safe})

        collection_policy_logic(has_xdist=True, workers="auto", items=[item])

        assert not item.has_serial_group(), (
            "Tests marked @pytest.mark.parallel_safe must NOT get serial grouping"
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
        item = FakeItem()

        collection_policy_logic(has_xdist=False, workers="auto", items=[item])

        assert len(item._added_markers) == 0, (
            "No markers should be added when xdist is not active"
        )

    def test_no_grouping_with_zero_workers(self) -> None:
        """No grouping should happen if -n 0 is used."""
        item = FakeItem()

        collection_policy_logic(has_xdist=True, workers="0", items=[item])

        assert len(item._added_markers) == 0, (
            "No markers should be added when -n 0 is specified"
        )

    def test_no_grouping_without_n_option(self) -> None:
        """No grouping should happen if -n is not specified."""
        item = FakeItem()

        collection_policy_logic(has_xdist=True, workers=None, items=[item])

        assert len(item._added_markers) == 0, (
            "No markers should be added when -n is not specified"
        )

    def test_multiple_items_processed_correctly(self) -> None:
        """Multiple items should be processed with correct policy."""
        unmarked = FakeItem(nodeid="test_a.py::test_unmarked")
        parallel_safe = FakeItem(
            nodeid="test_b.py::test_parallel",
            markers={"parallel_safe": pytest.mark.parallel_safe},
        )
        custom_group = FakeItem(
            nodeid="test_c.py::test_custom",
            markers={"xdist_group": pytest.mark.xdist_group("my_group")},
        )

        items = [unmarked, parallel_safe, custom_group]
        collection_policy_logic(has_xdist=True, workers="4", items=items)

        assert unmarked.has_serial_group(), "Unmarked test should be serialized"
        assert not parallel_safe.has_serial_group(), (
            "parallel_safe test should NOT be serialized"
        )
        assert not custom_group.has_serial_group(), (
            "Test with custom xdist_group should NOT be modified"
        )


@pytest.mark.parallel_safe
class TestSerialByDefaultPolicyDocumentation:
    """Verify the policy matches documentation claims."""

    def test_policy_is_conservative(self) -> None:
        """Verify the default is safe (serial), not dangerous (parallel)."""
        # Create many items with various characteristics
        items = [
            FakeItem(nodeid=f"test_{i}.py::test_func")
            for i in range(10)
        ]

        collection_policy_logic(has_xdist=True, workers="auto", items=items)

        # ALL items should be serialized (conservative default)
        for item in items:
            assert item.has_serial_group(), (
                f"Item {item.nodeid} should be serialized by default"
            )

    def test_only_explicit_parallel_safe_runs_parallel(self) -> None:
        """Only items with explicit parallel_safe marker should run parallel."""
        safe_item = FakeItem(
            nodeid="test_safe.py::test_parallel_safe",
            markers={"parallel_safe": pytest.mark.parallel_safe},
        )
        unsafe_item = FakeItem(nodeid="test_unsafe.py::test_no_marker")

        collection_policy_logic(
            has_xdist=True,
            workers="auto",
            items=[safe_item, unsafe_item],
        )

        assert not safe_item.has_serial_group(), (
            "parallel_safe should run parallel"
        )
        assert unsafe_item.has_serial_group(), (
            "Unmarked should be serialized"
        )
