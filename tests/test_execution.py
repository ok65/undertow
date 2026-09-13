import sys
import tempfile
import time
import unittest
from pathlib import Path

from undertow.execution import ExecutionConfig, ExecutionManager


class ExecutionManagerTests(unittest.TestCase):
    def test_run_streams_stdout_stderr_and_stdin_from_a_worker_thread(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "script.py"
            manager = ExecutionManager()
            config = ExecutionConfig(
                source='import sys\nprint("READY")\nvalue = input()\nprint(f"OUT:{value}")\nprint("ERR:wave", file=sys.stderr)\n',
                source_path=source_path,
                interpreter=Path(sys.executable),
                working_directory=root,
                timeout_seconds=3,
            )

            self.assertTrue(manager.start_run(config))
            self.assertTrue(manager.is_running)
            events = []
            sent_input = False
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                new_events = manager.drain_events()
                events.extend(new_events)
                if not sent_input and any(event.text == "READY" for event in new_events):
                    self.assertTrue(manager.send_stdin("tide\n"))
                    sent_input = True
                if any(event.kind == "finished" for event in new_events):
                    break
                time.sleep(0.01)

            self.assertTrue(sent_input)
            self.assertFalse(manager.is_running)
            self.assertIn(("output", "READY", "stdout"), [(event.kind, event.text, event.stream) for event in events])
            self.assertIn(("output", "OUT:tide", "stdout"), [(event.kind, event.text, event.stream) for event in events])
            self.assertIn(("output", "ERR:wave", "stderr"), [(event.kind, event.text, event.stream) for event in events])
            self.assertIn(("finished", 0), [(event.kind, event.returncode) for event in events])

    def test_stop_terminates_a_running_process_and_returns_to_idle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manager = ExecutionManager()
            config = ExecutionConfig(
                source='import time\nprint("READY", flush=True)\ntime.sleep(30)\n',
                source_path=root / "long_running.py",
                interpreter=Path(sys.executable),
                working_directory=root,
                timeout_seconds=35,
            )

            self.assertTrue(manager.start_run(config))
            events = []
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                new_events = manager.drain_events()
                events.extend(new_events)
                if any(event.text == "READY" for event in new_events):
                    break
                time.sleep(0.01)

            self.assertTrue(any(event.text == "READY" for event in events))
            self.assertTrue(manager.stop())
            while time.monotonic() < deadline:
                events.extend(manager.drain_events())
                if any(event.kind == "stopped" for event in events):
                    break
                time.sleep(0.01)

            self.assertFalse(manager.is_running)
            self.assertTrue(any(event.kind == "stopped" for event in events))
            self.assertFalse(manager.stop())


if __name__ == "__main__":
    unittest.main()
