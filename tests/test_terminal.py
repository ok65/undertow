import tempfile
import time
import unittest
from pathlib import Path

from undertow.terminal import TerminalSession


class TerminalSessionTests(unittest.TestCase):
    def test_powershell_session_streams_project_python_output_without_blocking_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            terminal = TerminalSession(Path.cwd())
            self.assertTrue(terminal.start())

            events = []
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                events.extend(terminal.drain_events())
                if any(event.kind == "started" for event in events):
                    break
                time.sleep(0.01)
            self.assertTrue(any(event.kind == "started" for event in events), events)
            self.assertTrue(terminal.send("python -c \"print('TERMINAL_WAVE')\""))

            while time.monotonic() < deadline:
                events.extend(terminal.drain_events())
                if any("TERMINAL_WAVE" in event.text for event in events):
                    break
                time.sleep(0.01)
            terminal.stop()

            self.assertTrue(any("TERMINAL_WAVE" in event.text for event in events), events)


if __name__ == "__main__":
    unittest.main()
