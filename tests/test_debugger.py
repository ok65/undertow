import sys
import tempfile
import time
import unittest
from pathlib import Path

from undertow.debug_session import DebugSession
from undertow.debugger import PythonDebugger
from undertow.execution import ExecutionConfig


class PythonDebuggerTests(unittest.TestCase):
    def test_breakpoints_are_toggled_using_resolved_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "example.py"
            source.write_text("pass\n", encoding="utf-8")
            debugger = PythonDebugger()

            self.assertTrue(debugger.toggle_breakpoint(root / "." / "example.py", 3))
            self.assertEqual(debugger.breakpoints, {(source.resolve(), 3)})
            self.assertFalse(debugger.toggle_breakpoint(source, 3))
            self.assertEqual(debugger.breakpoints, set())

    def test_watches_are_trimmed_unique_and_removable(self) -> None:
        debugger = PythonDebugger()

        self.assertFalse(debugger.add_watch("   "))
        self.assertTrue(debugger.add_watch("  request.user  "))
        self.assertFalse(debugger.add_watch("request.user"))
        self.assertEqual(debugger.watches, ["request.user"])
        self.assertFalse(debugger.remove_watch("missing"))
        self.assertTrue(debugger.remove_watch("request.user"))
        self.assertEqual(debugger.watches, [])

    def test_debug_session_launches_a_debugpy_adapter_and_relays_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "debug_target.py"
            source.write_text('print("debug-wave")\n', encoding="utf-8")
            session = DebugSession()
            config = ExecutionConfig(
                source=source.read_text(encoding="utf-8"),
                source_path=source,
                interpreter=Path(sys.executable),
                working_directory=root,
            )

            self.assertTrue(session.start(config, PythonDebugger()))
            events = []
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                events.extend(session.drain_events())
                if not session.is_active:
                    break
                time.sleep(0.02)
            events.extend(session.drain_events())

            self.assertIn(("output", "debug-wave", "stdout"), [(event.kind, event.text, event.stream) for event in events])
            self.assertTrue(any(event.kind == "finished" for event in events), events)

    def test_debug_session_pauses_at_a_breakpoint_then_continues(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "breakpoint_target.py"
            source.write_text('wave = {"height": 3}\nprint("after")\n', encoding="utf-8")
            debugger = PythonDebugger()
            debugger.toggle_breakpoint(source, 2)
            session = DebugSession()
            config = ExecutionConfig(source.read_text(encoding="utf-8"), source, Path(sys.executable), root)

            self.assertTrue(session.start(config, debugger))
            events = []
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                events.extend(session.drain_events())
                if any(event.kind == "paused" for event in events):
                    break
                time.sleep(0.02)

            self.assertTrue(any(event.kind == "paused" for event in events), events)
            self.assertEqual(session.paused_location, (source.resolve(), 2))
            local_scope = next(variable for variable in session.variables if variable.name == "Locals")
            wave = next(variable for variable in local_scope.children if variable.name == "wave")
            self.assertTrue(wave.can_expand)
            self.assertTrue(session.expand_variable(wave.variables_reference))
            while time.monotonic() < deadline:
                local_scope = next(variable for variable in session.variables if variable.name == "Locals")
                wave = next(variable for variable in local_scope.children if variable.name == "wave")
                if wave.children:
                    break
                time.sleep(0.02)

            local_scope = next(variable for variable in session.variables if variable.name == "Locals")
            wave = next(variable for variable in local_scope.children if variable.name == "wave")
            self.assertTrue(any("height" in child.name for child in wave.children))
            self.assertTrue(session.evaluate("wave['height']"))
            while time.monotonic() < deadline:
                events.extend(session.drain_events())
                if any(event.kind == "evaluation" for event in events):
                    break
                time.sleep(0.02)
            self.assertIn(("evaluation", "3"), [(event.kind, event.text) for event in events])
            evaluations = sum(event.kind == "evaluation" for event in events)
            self.assertTrue(session.evaluate("wave['height'] = 4"))
            while time.monotonic() < deadline:
                events.extend(session.drain_events())
                if sum(event.kind == "evaluation" for event in events) > evaluations:
                    break
                time.sleep(0.02)
            self.assertTrue(session.evaluate("wave['height']"))
            while time.monotonic() < deadline:
                events.extend(session.drain_events())
                if ("evaluation", "4") in [(event.kind, event.text) for event in events]:
                    break
                time.sleep(0.02)
            self.assertIn(("evaluation", "4"), [(event.kind, event.text) for event in events])
            self.assertTrue(session.continue_execution())
            while time.monotonic() < deadline:
                events.extend(session.drain_events())
                if not session.is_active:
                    break
                time.sleep(0.02)
            events.extend(session.drain_events())

            self.assertIn(("output", "after", "stdout"), [(event.kind, event.text, event.stream) for event in events])
            self.assertTrue(any(event.kind == "finished" for event in events), events)

    def test_simple_interpreter_assignment_updates_an_existing_global(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "global_target.py"
            source.write_text(
                'count = 2\n\ndef pause_here():\n    marker = 0\n    print(f"COUNT:{count}")\n\npause_here()\n',
                encoding="utf-8",
            )
            debugger = PythonDebugger()
            debugger.toggle_breakpoint(source, 4)
            session = DebugSession()
            config = ExecutionConfig(source.read_text(encoding="utf-8"), source, Path(sys.executable), root)

            self.assertTrue(session.start(config, debugger))
            events = []
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                events.extend(session.drain_events())
                if any(event.kind == "paused" for event in events):
                    break
                time.sleep(0.02)

            self.assertTrue(any(event.kind == "paused" for event in events), events)
            self.assertTrue(session.evaluate("count = 12"))
            while time.monotonic() < deadline:
                events.extend(session.drain_events())
                if any(event.kind == "evaluation" for event in events):
                    break
                time.sleep(0.02)
            self.assertIn(("evaluation", "count = 12"), [(event.kind, event.text) for event in events])
            self.assertTrue(session.continue_execution())
            while time.monotonic() < deadline:
                events.extend(session.drain_events())
                if not session.is_active:
                    break
                time.sleep(0.02)
            events.extend(session.drain_events())

            self.assertIn(("output", "COUNT:12", "stdout"), [(event.kind, event.text, event.stream) for event in events])


if __name__ == "__main__":
    unittest.main()
