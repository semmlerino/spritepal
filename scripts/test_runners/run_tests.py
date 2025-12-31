#!/usr/bin/env python3
from __future__ import annotations

"""Run tests directly with unittest to bypass pytest issues."""

import os
import sys
import unittest
from pathlib import Path

# Add spritepal to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Disable Qt if not available
os.environ["QT_QPA_PLATFORM"] = "offscreen"


def run_tests():
    """Run tests using unittest directly."""
    # Discover and run tests
    loader = unittest.TestLoader()
    suite = loader.discover("tests", pattern="test_minimal.py")

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())
