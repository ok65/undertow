import tempfile
import unittest
from pathlib import Path

from undertow.performance import PerformanceCapture


class PerformanceCaptureTests(unittest.TestCase):
    def test_capture_writes_a_bounded_readable_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            capture = PerformanceCapture()
            capture.start(Path(directory), frames=1)
            sum(range(100))

            paths = capture.end_frame()

            self.assertIsNotNone(paths)
            binary, report = paths
            self.assertTrue(binary.is_file())
            self.assertIn("Undertow GUI profile: 1 frames", report.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
