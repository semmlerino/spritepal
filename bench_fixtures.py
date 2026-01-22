import shutil
import tempfile
import time
from pathlib import Path

from PySide6.QtWidgets import QApplication

from core.app_context import create_app_context, reset_app_context
from utils.logging_config import get_logger

logger = get_logger(__name__)


def bench_app_context():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    tmp_dir = Path(tempfile.mkdtemp())
    try:
        start_time = time.perf_counter()

        # Logic from fixture
        settings_path = tmp_dir / ".test_settings.json"
        _context = create_app_context(
            app_name="TestApp",
            settings_path=settings_path,
        )

        end_time = time.perf_counter()
        logger.info(f"AppContext creation time: {(end_time - start_time) * 1000:.2f}ms")

        reset_app_context()

    finally:
        shutil.rmtree(tmp_dir)


if __name__ == "__main__":
    # Warmup
    bench_app_context()
    # Measure
    bench_app_context()
    bench_app_context()
    bench_app_context()
