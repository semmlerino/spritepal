#!/usr/bin/env python3
from __future__ import annotations

"""
Enhanced script to systematically apply pytest markers to test files.

This script analyzes test files and applies comprehensive pytest markers
including execution environment, test type, Qt components, and parallelization markers.
"""

import re
from pathlib import Path
from typing import Any


def analyze_test_file(content: str, filename: str) -> dict[str, Any]:
    """
    Analyze a test file and determine all appropriate pytest markers.

    Returns:
        Dictionary with marker categories and analysis results
    """
    analysis = {
        "execution_env": [],
        "test_type": [],
        "qt_components": [],
        "threading": [],
        "special": [],
        "reasons": [],
    }

    # Execution Environment Analysis
    has_qt_imports = any(
        qt_term in content
        for qt_term in [
            "PySide6",
            "PyQt5",
            "PySide6",
            "PySide2",
            "QWidget",
            "QDialog",
            "QApplication",
            "QMainWindow",
            "qtbot",
        ]
    )

    has_gui_usage = any(
        gui_term in content
        for gui_term in [
            "exec_()",
            "show()",
            "hide()",
            ".exec()",
            "qtbot",
            "QApplication([])",
            "QApplication.instance()",
        ]
    )

    uses_mocks = any(mock_term in content for mock_term in ["Mock", "MagicMock", "@patch", "mock_", "patch("])

    if has_gui_usage and not uses_mocks:
        analysis["execution_env"].append("gui")
        analysis["reasons"].append("Real GUI components requiring display")
    elif uses_mocks or not has_qt_imports:
        analysis["execution_env"].append("headless")

    if uses_mocks and not has_gui_usage:
        analysis["execution_env"].append("mock_only")

    # Test Type Analysis
    if "integration" in filename.lower() or any(
        term in content for term in ["workflow", "end_to_end", "e2e", "tempfile", "tmp_path"]
    ):
        analysis["test_type"].append("integration")
    elif not has_qt_imports and not any(term in content for term in ["tempfile", "tmp_path"]):
        analysis["test_type"].append("unit")

    # Qt Component Analysis
    if has_qt_imports:
        if uses_mocks:
            analysis["qt_components"].extend(["qt_mock"])
        else:
            analysis["qt_components"].extend(["qt_real", "qt_app"])
    else:
        analysis["qt_components"].append("no_qt")

    # Threading and Serial Requirements Analysis
    threading_patterns = [
        ("QApplication management", r"QApplication\(\[\]\)|QApplication\.instance\(\)"),
        ("Singleton management", r"reset_singleton|ManualOffsetDialogSingleton"),
        ("Manager registry manipulation", r"ManagerRegistry.*reset"),
        ("HAL process pool", r"HALProcessPool|ProcessPool.*HAL"),
        ("Thread safety concerns", r"thread_safety|threading|QThread"),
        ("Real Qt components", r"real_qt|RealComponentFactory"),
        ("Timer usage", r"QTimer|timer"),
    ]

    needs_serial = False
    for reason, pattern in threading_patterns:
        if re.search(pattern, content, re.IGNORECASE):
            analysis["reasons"].append(reason)
            needs_serial = True

            if "QApplication" in reason:
                analysis["threading"].append("qt_application")
            elif "Singleton" in reason or "Manager registry" in reason:
                analysis["threading"].append("singleton")
            elif "process pool" in reason.lower():
                analysis["threading"].append("process_pool")
            elif "Thread" in reason or "timer" in reason.lower():
                analysis["threading"].append("worker_threads")

    if needs_serial:
        analysis["threading"].append("serial")
    elif uses_mocks and not has_gui_usage:
        analysis["special"].append("parallel_safe")

    # Additional Special Markers
    if any(term in content for term in ["dialog", "Dialog", "exec_"]):
        analysis["special"].append("dialog")
        if uses_mocks:
            analysis["special"].append("mock_dialogs")

    if any(term in content for term in ["widget", "Widget", "QWidget"]):
        analysis["special"].append("widget")

    if any(term in content for term in ["tempfile", "tmp_path", "open(", "Path("]):
        analysis["special"].append("file_io")

    if any(term in content for term in ["rom", "ROM", ".smc", ".dmp", "vram", "VRAM"]):
        analysis["special"].append("rom_data")

    if any(term in content for term in ["performance", "benchmark", "profil"]):
        analysis["special"].extend(["performance", "benchmark"])

    if any(term in content for term in ["time.sleep", "QTimer", "wait_"]) or (has_gui_usage and not uses_mocks):
        analysis["special"].append("slow")

    return analysis


def get_marker_list(analysis: dict[str, Any]) -> list[str]:
    """Get comprehensive pytest markers from analysis results."""
    markers = []

    # Add all markers from analysis categories
    all_marker_categories = [
        analysis["execution_env"],
        analysis["test_type"],
        analysis["qt_components"],
        analysis["threading"],
        analysis["special"],
    ]

    for category in all_marker_categories:
        for marker in category:
            markers.append(f"pytest.mark.{marker}")

    # Remove duplicates and sort
    return sorted(set(markers))


def add_pytest_markers(file_path: Path, analysis: dict[str, Any]) -> bool:
    """
    Add comprehensive pytest markers to a test file.

    Returns:
        True if file was modified, False if markers already exist
    """
    content = file_path.read_text()

    # Check if pytestmark already exists
    if "pytestmark" in content:
        print(f"  Skipped {file_path.name} - markers already exist")
        return False

    # Skip files with less than 10 lines (likely empty or template files)
    if len(content.split("\n")) < 10:
        print(f"  Skipped {file_path.name} - too short")
        return False

    markers = get_marker_list(analysis)

    if not markers:
        print(f"  Skipped {file_path.name} - no markers determined")
        return False

    # Create marker block
    reasons = analysis.get("reasons", [])
    if reasons:
        marker_comment = f"# Test characteristics: {', '.join(reasons)}"
    else:
        marker_comment = "# Systematic pytest markers applied based on test content analysis"

    marker_lines = [marker_comment, "pytestmark = ["]

    for marker in markers:
        marker_lines.append(f"    {marker},")

    marker_lines.append("]")
    marker_block = "\n".join(marker_lines) + "\n\n"

    # Find insertion point - after imports but before first class/function
    lines = content.split("\n")
    insert_idx = 0

    # Skip docstring if present
    in_docstring = False
    for i, line in enumerate(lines):
        if line.strip().startswith('"""') or line.strip().startswith("'''"):
            if not in_docstring:
                in_docstring = True
            elif in_docstring:
                in_docstring = False
                insert_idx = i + 1
                continue

        if not in_docstring:
            # Skip imports, constants, and blank lines
            if line.startswith("import ") or line.startswith("from ") or line.strip() == "" or line.startswith("#"):
                insert_idx = i + 1
                continue

            # Found first non-import line
            break

    # Insert marker block
    lines.insert(insert_idx, marker_block)
    new_content = "\n".join(lines)

    try:
        file_path.write_text(new_content)
        marker_summary = [m.split(".")[-1] for m in markers]
        print(f"  ✓ Added {len(markers)} markers to {file_path.name}: {', '.join(marker_summary)}")
        return True
    except Exception as e:
        print(f"  ✗ Error writing {file_path.name}: {e}")
        return False


def main():
    """Main function to process test files."""
    test_dir = Path("tests")
    if not test_dir.exists():
        print("Error: tests directory not found")
        return

    modified_count = 0
    skipped_count = 0
    error_count = 0

    stats = {
        "gui": 0,
        "headless": 0,
        "mock_only": 0,
        "serial": 0,
        "parallel_safe": 0,
        "integration": 0,
        "unit": 0,
    }

    print("🔍 Analyzing test files for systematic pytest marker application...\n")

    for test_file in sorted(test_dir.rglob("test_*.py")):
        try:
            content = test_file.read_text()
            analysis = analyze_test_file(content, test_file.name)

            # Update statistics
            for category in ["execution_env", "test_type", "threading", "special"]:
                for marker in analysis.get(category, []):
                    if marker in stats:
                        stats[marker] += 1

            if add_pytest_markers(test_file, analysis):
                modified_count += 1
            else:
                skipped_count += 1

        except Exception as e:
            print(f"  ✗ Error processing {test_file}: {e}")
            error_count += 1

    print("\n📊 Processing Summary:")
    print(f"  Modified: {modified_count} files")
    print(f"  Skipped: {skipped_count} files (already marked or too short)")
    print(f"  Errors: {error_count} files")

    print("\n📈 Marker Statistics:")
    for marker, count in sorted(stats.items()):
        if count > 0:
            print(f"  {marker}: {count} files")

    print("\n🚀 Usage Examples:")
    print("  # Run only fast, headless tests:")
    print("  pytest -m 'headless and not slow'")
    print("  ")
    print("  # Run only GUI tests (with display):")
    print("  pytest -m 'gui'")
    print("  ")
    print("  # Run unit tests only:")
    print("  pytest -m 'unit'")
    print("  ")
    print("  # Run parallel-safe tests:")
    print("  pytest -m 'parallel_safe' -n auto")
    print("  ")
    print("  # Run serial tests only:")
    print("  pytest -m 'serial'")
    print("  ")
    print("  # Skip slow tests for quick feedback:")
    print("  pytest -m 'not slow'")


if __name__ == "__main__":
    main()
