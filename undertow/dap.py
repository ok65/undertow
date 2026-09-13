"""Minimal Debug Adapter Protocol transport over an adapter's stdio pipes."""

from __future__ import annotations

import json
import queue
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class DapProtocolError(RuntimeError):
    """The adapter sent a malformed DAP message."""


@dataclass(frozen=True)
class DapRequest:
    sequence: int
    responses: queue.Queue[dict[str, Any]]


class DapClient:
    """A small synchronous-request/asynchronous-event DAP client.

    One debug-session worker owns requests.  The reader thread only decodes
    messages and dispatches them, so UI code never touches adapter pipes.
    """

    def __init__(self, interpreter: Path) -> None:
        self.interpreter = interpreter
        self.events: queue.SimpleQueue[dict[str, Any]] = queue.SimpleQueue()
        self.stderr: queue.SimpleQueue[str] = queue.SimpleQueue()
        self._lock = threading.Lock()
        self._next_sequence = 1
        self._pending: dict[int, queue.Queue[dict[str, Any]]] = {}
        self._process: subprocess.Popen[bytes] | None = None
        self._reader: threading.Thread | None = None
        self._stderr_reader: threading.Thread | None = None

    def start(self) -> None:
        if self._process is not None:
            raise RuntimeError("DAP adapter is already running.")
        self._process = subprocess.Popen(
            [str(self.interpreter), "-m", "debugpy.adapter"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._reader = threading.Thread(target=self._read_messages, daemon=True)
        self._stderr_reader = threading.Thread(target=self._read_stderr, daemon=True)
        self._reader.start()
        self._stderr_reader.start()

    def request(self, command: str, arguments: dict[str, Any], timeout: float = 10) -> dict[str, Any]:
        """Send a DAP request and wait for its matching response."""
        request = self.send_request(command, arguments)
        return self.wait_for_response(request, command, timeout)

    def send_request(self, command: str, arguments: dict[str, Any]) -> DapRequest:
        """Send a DAP request without waiting for its response."""
        response_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
        with self._lock:
            process = self._process
            if process is None or process.stdin is None or process.poll() is not None:
                raise RuntimeError("DAP adapter is not running.")
            sequence = self._next_sequence
            self._next_sequence += 1
            self._pending[sequence] = response_queue
            self._write_message({
                "seq": sequence,
                "type": "request",
                "command": command,
                "arguments": arguments,
            })
        return DapRequest(sequence, response_queue)

    def wait_for_response(self, request: DapRequest, command: str, timeout: float = 10) -> dict[str, Any]:
        """Wait for a response previously returned by :meth:`send_request`."""
        try:
            response = request.responses.get(timeout=timeout)
        except queue.Empty as error:
            with self._lock:
                self._pending.pop(request.sequence, None)
            raise TimeoutError(f"DAP request {command!r} timed out.") from error
        if not response.get("success", False):
            raise RuntimeError(response.get("message", f"DAP request {command!r} failed."))
        return response.get("body", {})

    def close(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None and not stream.closed:
                stream.close()
        for reader in (self._reader, self._stderr_reader):
            if reader is not None:
                reader.join(timeout=1)
        for pending in tuple(self._pending.values()):
            pending.put({"success": False, "message": "DAP adapter closed."})
        self._pending.clear()

    def _write_message(self, message: dict[str, Any]) -> None:
        process = self._process
        assert process is not None and process.stdin is not None
        payload = json.dumps(message, separators=(",", ":")).encode("utf-8")
        process.stdin.write(f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii") + payload)
        process.stdin.flush()

    def _read_messages(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return
        try:
            while message := self._read_message(process.stdout):
                if message.get("type") == "response":
                    request_sequence = message.get("request_seq")
                    with self._lock:
                        pending = self._pending.pop(request_sequence, None)
                    if pending is not None:
                        pending.put(message)
                else:
                    self.events.put(message)
        except (OSError, ValueError, DapProtocolError) as error:
            self.events.put({"type": "event", "event": "adapterError", "body": {"message": str(error)}})

    @staticmethod
    def _read_message(stream: Any) -> dict[str, Any] | None:
        headers: dict[str, str] = {}
        while True:
            raw_line = stream.readline()
            if not raw_line:
                return None
            line = raw_line.decode("ascii").strip()
            if not line:
                break
            if ":" not in line:
                raise DapProtocolError("DAP header is missing ':'.")
            key, value = line.split(":", 1)
            headers[key.lower()] = value.strip()
        try:
            length = int(headers["content-length"])
        except (KeyError, ValueError) as error:
            raise DapProtocolError("DAP message is missing a valid Content-Length header.") from error
        payload = stream.read(length)
        if len(payload) != length:
            raise DapProtocolError("DAP message ended before its declared Content-Length.")
        return json.loads(payload.decode("utf-8"))

    def _read_stderr(self) -> None:
        process = self._process
        if process is None or process.stderr is None:
            return
        for line in iter(process.stderr.readline, b""):
            self.stderr.put(line.decode("utf-8", errors="replace").rstrip("\r\n"))
