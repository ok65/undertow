from dataclasses import dataclass, field


@dataclass
class OutputBuffer:
    """Shared output sink for runners, linters, and future debug adapters."""
    lines: list[str] = field(default_factory=list)
    status: str = "SYSTEM READY"

    def publish(self, status: str, lines: list[str]) -> None:
        self.status = status
        self.lines = lines


class EditorService:
    """Base contract for document-attached features such as lint/completion/debug."""
    name = "service"

    def run(self, document: object) -> None:
        raise NotImplementedError
