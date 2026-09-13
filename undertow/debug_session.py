"""One DAP-backed Python debug session, independent from its future panes."""

from __future__ import annotations

import ast
import os
import queue
import tempfile
import threading
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .dap import DapClient
from .debug_values import DebugVariable
from .execution import ExecutionConfig, ExecutionEvent

if TYPE_CHECKING:
    from .debugger import PythonDebugger


class DebugSessionState(StrEnum):
    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    FAILED = "failed"


@dataclass(frozen=True)
class InterpreterAssignment:
    """A simple name assignment routed into an actual paused DAP scope."""

    scope_reference: int
    name: str
    value: str


class DebugSession:
    """Launch one snapshot under debugpy and translate DAP events for Undertow."""

    def __init__(self) -> None:
        self._events: queue.SimpleQueue[ExecutionEvent] = queue.SimpleQueue()
        self._commands: queue.SimpleQueue[tuple[str, Any]] = queue.SimpleQueue()
        self._lock = threading.Lock()
        self._state = DebugSessionState.IDLE
        self._worker: threading.Thread | None = None
        self._variables: tuple[DebugVariable, ...] = ()
        self._paused_thread_id: int | None = None
        self._paused_frame_id: int | None = None
        self._paused_location: tuple[Path, int] | None = None
        self._source_path: Path | None = None
        self._snapshot_path: Path | None = None

    @property
    def state(self) -> DebugSessionState:
        with self._lock:
            return self._state

    @property
    def is_active(self) -> bool:
        return self.state not in {DebugSessionState.IDLE, DebugSessionState.FAILED}

    @property
    def variables(self) -> tuple[DebugVariable, ...]:
        with self._lock:
            return self._variables

    @property
    def paused_location(self) -> tuple[Path, int] | None:
        with self._lock:
            return self._paused_location

    def start(self, config: ExecutionConfig, debugger: PythonDebugger) -> bool:
        with self._lock:
            if self._state is not DebugSessionState.IDLE:
                return False
            self._state = DebugSessionState.STARTING
            self._worker = threading.Thread(target=self._run, args=(config, debugger), daemon=True)
            self._worker.start()
        return True

    def continue_execution(self) -> bool:
        return self._queue_command("continue")

    def step_over(self) -> bool:
        return self._queue_command("next")

    def step_in(self) -> bool:
        return self._queue_command("stepIn")

    def expand_variable(self, variables_reference: int) -> bool:
        """Request lazy children for an object currently shown in the tree."""
        with self._lock:
            if self._state is not DebugSessionState.PAUSED or variables_reference <= 0:
                return False
        self._commands.put(("variables", variables_reference))
        return True

    def evaluate(self, expression: str) -> bool:
        """Evaluate a REPL entry, routing simple assignments into live scopes."""
        expression = expression.strip()
        with self._lock:
            if self._state is not DebugSessionState.PAUSED or not expression or self._paused_frame_id is None:
                return False
            assignment = self._assignment_for(expression)
        self._commands.put(("set_variable", assignment) if assignment is not None else ("evaluate", expression))
        return True

    def stop(self) -> bool:
        with self._lock:
            if self._state in {DebugSessionState.IDLE, DebugSessionState.FAILED, DebugSessionState.STOPPING}:
                return False
            self._state = DebugSessionState.STOPPING
        self._commands.put(("disconnect", None))
        return True

    def drain_events(self) -> list[ExecutionEvent]:
        events: list[ExecutionEvent] = []
        while True:
            try:
                events.append(self._events.get_nowait())
            except queue.Empty:
                return events

    def _queue_command(self, command: str) -> bool:
        with self._lock:
            if self._state is not DebugSessionState.PAUSED:
                return False
        self._commands.put((command, None))
        return True

    def _run(self, config: ExecutionConfig, debugger: PythonDebugger) -> None:
        temporary_name = ""
        client: DapClient | None = None
        exited = False
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as handle:
                handle.write(config.source)
                temporary_name = handle.name
            snapshot = Path(temporary_name)
            with self._lock:
                self._source_path = config.source_path.resolve()
                self._snapshot_path = snapshot.resolve()
            client = DapClient(config.interpreter)
            client.start()
            client.request("initialize", {
                "clientID": "undertow",
                "clientName": "Undertow",
                "adapterID": "python",
                "pathFormat": "path",
                "linesStartAt1": True,
                "columnsStartAt1": True,
                "supportsVariableType": True,
            })
            launch_request = client.send_request("launch", {
                "name": "Undertow",
                "type": "debugpy",
                "request": "launch",
                "program": str(snapshot),
                "cwd": str(config.working_directory or config.source_path.parent),
                "console": "internalConsole",
                "python": str(config.interpreter),
                "justMyCode": True,
            })
            breakpoints = [{"line": line} for path, line in debugger.breakpoints if path == config.source_path.resolve()]
            client.request("setBreakpoints", {"source": {"path": str(snapshot)}, "breakpoints": breakpoints})
            client.request("configurationDone", {})
            client.wait_for_response(launch_request, "launch")
            with self._lock:
                self._state = DebugSessionState.RUNNING
            self._events.put(ExecutionEvent("started", f"> debugging {config.source_path.name} ..."))

            while not exited:
                self._handle_command(client)
                while True:
                    try:
                        message = client.events.get_nowait()
                    except queue.Empty:
                        break
                    exited = self._handle_event(client, message, exited)
                    if exited:
                        break
                while True:
                    try:
                        line = client.stderr.get_nowait()
                    except queue.Empty:
                        break
                    self._events.put(ExecutionEvent("output", line, "stderr"))
                if not exited:
                    threading.Event().wait(0.01)
        except (OSError, RuntimeError, TimeoutError) as error:
            self._events.put(ExecutionEvent("failed", f"debugger error: {error}"))
            with self._lock:
                self._state = DebugSessionState.FAILED
        finally:
            if client is not None:
                client.close()
                # debugpy reports termination just before its spawned target
                # releases the Windows working-directory handle.
                time.sleep(0.1)
            if temporary_name:
                try:
                    os.unlink(temporary_name)
                except OSError:
                    pass
            with self._lock:
                was_stopping = self._state is DebugSessionState.STOPPING
                if self._state is not DebugSessionState.FAILED:
                    self._state = DebugSessionState.IDLE
                self._worker = None
            if was_stopping:
                self._events.put(ExecutionEvent("stopped", "debugging stopped."))
            elif exited:
                self._events.put(ExecutionEvent("finished"))

    def _handle_command(self, client: DapClient) -> None:
        try:
            command, value = self._commands.get_nowait()
        except queue.Empty:
            return
        if command == "disconnect":
            client.request("disconnect", {"terminateDebuggee": True})
        elif command == "variables" and isinstance(value, int):
            self._load_variable_children(client, value)
        elif command == "set_variable" and isinstance(value, InterpreterAssignment):
            self._set_variable(client, value)
        elif command == "evaluate" and isinstance(value, str):
            self._evaluate(client, value)
        else:
            client.request(command, {"threadId": self._paused_thread_id or 1})
            with self._lock:
                self._state = DebugSessionState.RUNNING
                self._variables = ()
                self._paused_thread_id = None
                self._paused_frame_id = None
                self._paused_location = None

    def _handle_event(self, client: DapClient, message: dict[str, Any], exited: bool) -> bool:
        if message.get("event") == "output":
            body = message.get("body", {})
            category = body.get("category", "console")
            stream = "stderr" if category == "stderr" else "stdout"
            self._events.put(ExecutionEvent("output", body.get("output", "").rstrip("\r\n"), stream))
        elif message.get("event") == "stopped":
            body = message.get("body", {})
            reason = body.get("reason", "paused")
            with self._lock:
                self._state = DebugSessionState.PAUSED
                self._paused_thread_id = int(body.get("threadId", 1))
            self._capture_variables(client, self._paused_thread_id)
            self._events.put(ExecutionEvent("paused", f"debugger paused: {reason}"))
        elif message.get("event") in {"terminated", "exited"}:
            exited = True
        elif message.get("event") == "adapterError":
            self._events.put(ExecutionEvent("failed", message.get("body", {}).get("message", "DAP adapter failed.")))
            exited = True
        return exited

    def _capture_variables(self, client: DapClient, thread_id: int) -> None:
        """Read the selected frame's scopes while the debuggee is paused."""
        frames = client.request("stackTrace", {"threadId": thread_id}).get("stackFrames", [])
        if not frames:
            with self._lock:
                self._variables = ()
                self._paused_frame_id = None
                self._paused_location = None
            return
        frame_id = int(frames[0]["id"])
        with self._lock:
            self._paused_frame_id = frame_id
            source = frames[0].get("source", {}).get("path")
            line = frames[0].get("line")
            if source and isinstance(line, int):
                path = Path(source).resolve()
                self._paused_location = (self._source_path, line) if path == self._snapshot_path else (path, line)
        scopes = client.request("scopes", {"frameId": frame_id}).get("scopes", [])
        roots: list[DebugVariable] = []
        for scope in scopes:
            reference = int(scope.get("variablesReference", 0))
            children = tuple(self._read_variables(client, reference)) if reference else ()
            roots.append(DebugVariable(
                name=str(scope.get("name", "Scope")),
                value="",
                variables_reference=reference,
                children=children,
                expanded=True,
            ))
        with self._lock:
            self._variables = tuple(roots)
        self._events.put(ExecutionEvent("variables"))

    def _evaluate(self, client: DapClient, expression: str) -> None:
        try:
            body = client.request("evaluate", {
                "expression": expression,
                "frameId": self._paused_frame_id,
                "context": "repl",
            })
        except (RuntimeError, TimeoutError) as error:
            self._events.put(ExecutionEvent("evaluation_error", str(error)))
            return
        self._events.put(ExecutionEvent("evaluation", str(body.get("result", ""))))
        if self._paused_thread_id is not None:
            self._capture_variables(client, self._paused_thread_id)

    def _set_variable(self, client: DapClient, assignment: InterpreterAssignment) -> None:
        """Assign through DAP so resume observes the actual debugger state."""
        try:
            body = client.request("setVariable", {
                "variablesReference": assignment.scope_reference,
                "name": assignment.name,
                "value": assignment.value,
            })
        except (RuntimeError, TimeoutError) as error:
            self._events.put(ExecutionEvent("evaluation_error", str(error)))
            return
        self._events.put(ExecutionEvent("evaluation", f"{assignment.name} = {body.get('value', assignment.value)}"))
        if self._paused_thread_id is not None:
            self._capture_variables(client, self._paused_thread_id)

    def _assignment_for(self, expression: str) -> InterpreterAssignment | None:
        """Recognise only flat name assignments; all other Python stays DAP-evaluated."""
        try:
            statements = ast.parse(expression, mode="exec").body
        except SyntaxError:
            return None
        if len(statements) != 1:
            return None
        statement = statements[0]
        name: str
        value: str
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1 and isinstance(statement.targets[0], ast.Name):
            name = statement.targets[0].id
            value = ast.unparse(statement.value)
        elif isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name) and statement.value is not None:
            name = statement.target.id
            value = ast.unparse(statement.value)
        elif isinstance(statement, ast.AugAssign) and isinstance(statement.target, ast.Name):
            operator = {
                ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.FloorDiv: "//", ast.Mod: "%",
                ast.Pow: "**", ast.BitAnd: "&", ast.BitOr: "|", ast.BitXor: "^", ast.LShift: "<<", ast.RShift: ">>",
            }.get(type(statement.op))
            if operator is None:
                return None
            name = statement.target.id
            value = f"{name} {operator} ({ast.unparse(statement.value)})"
        else:
            return None
        scope = self._assignment_scope(name)
        return InterpreterAssignment(scope.variables_reference, name, value) if scope is not None else None

    def _assignment_scope(self, name: str) -> DebugVariable | None:
        """Prefer the real local binding; otherwise update an existing global."""
        local_scope = next((scope for scope in self._variables if scope.name.lower() == "locals"), None)
        global_scope = next((scope for scope in self._variables if scope.name.lower() == "globals"), None)
        if local_scope is not None and any(variable.name == name for variable in local_scope.children):
            return local_scope
        if global_scope is not None and any(variable.name == name for variable in global_scope.children):
            return global_scope
        return local_scope or global_scope

    def _load_variable_children(self, client: DapClient, variables_reference: int) -> None:
        children = tuple(self._read_variables(client, variables_reference))
        with self._lock:
            self._variables = tuple(self._replace_children(variable, variables_reference, children) for variable in self._variables)
        self._events.put(ExecutionEvent("variables"))

    @staticmethod
    def _read_variables(client: DapClient, variables_reference: int) -> list[DebugVariable]:
        values = client.request("variables", {"variablesReference": variables_reference}).get("variables", [])
        return [
            DebugVariable(
                name=str(value.get("name", "?")),
                value=str(value.get("value", "")),
                type_name=value.get("type"),
                variables_reference=int(value.get("variablesReference", 0)),
            )
            for value in values
        ]

    @classmethod
    def _replace_children(cls, variable: DebugVariable, reference: int, children: tuple[DebugVariable, ...]) -> DebugVariable:
        if variable.variables_reference == reference:
            return DebugVariable(variable.name, variable.value, variable.type_name, reference, children, expanded=True)
        return DebugVariable(
            variable.name,
            variable.value,
            variable.type_name,
            variable.variables_reference,
            tuple(cls._replace_children(child, reference, children) for child in variable.children),
            variable.expanded,
        )
