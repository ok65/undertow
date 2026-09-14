"""Document lifecycle services shared by every code pane in a workspace."""

from __future__ import annotations

from collections.abc import Callable

from undertow.editor import Editor


class DocumentManager:
    """Own persistence and disk reconciliation for canonical editor buffers.

    Several panes may view one ``lines`` list.  This service treats that list
    as one document, so a save, autosave, or external merge is performed once
    and its state is then reflected consistently in every view.
    """

    def __init__(
        self,
        editors: Callable[[], list[Editor]],
        active_editor: Callable[[], Editor | None],
        report_status: Callable[[str], None],
        autosave_interval_ms: int,
        external_check_interval_ms: int,
    ) -> None:
        self._editors = editors
        self._active_editor = active_editor
        self._report_status = report_status
        self.autosave_interval_ms = autosave_interval_ms
        self.external_check_interval_ms = external_check_interval_ms
        self.last_autosave_tick = 0
        self.last_external_check_tick = 0

    def _siblings(self, editor: Editor) -> list[Editor]:
        return [candidate for candidate in self._editors() if candidate.lines is editor.lines]

    def save(self, editor: Editor) -> str:
        """Save one buffer and clear its dirty marker in every pane view."""
        status = editor.save().upper()
        for sibling in self._siblings(editor):
            sibling.dirty = False
        return status

    def save_active(self) -> None:
        """Save the focused document and publish a concise UI status."""
        editor = self._active_editor()
        if editor is None:
            self._report_status("NO CODE DOCUMENT TO SAVE")
            return
        try:
            self._report_status(self.save(editor))
        except OSError:
            self._report_status("SAVE FAILED")

    def autosave(self, now_ms: int) -> int:
        """Persist dirty, conflict-free buffers at a fixed calm cadence."""
        if now_ms - self.last_autosave_tick < self.autosave_interval_ms:
            return 0
        self.last_autosave_tick = now_ms
        saved_buffers: set[int] = set()
        saved = 0
        for editor in self._editors():
            if editor is None or not editor.dirty or editor.external_change_pending or id(editor.lines) in saved_buffers:
                continue
            try:
                self.save(editor)
            except OSError:
                continue
            saved_buffers.add(id(editor.lines))
            saved += 1
        return saved

    def refresh_external(self, now_ms: int) -> tuple[int, int]:
        """Merge/reload changed files while protecting conflicting local edits."""
        if now_ms - self.last_external_check_tick < self.external_check_interval_ms:
            return 0, 0
        self.last_external_check_tick = now_ms
        inspected_buffers: set[int] = set()
        reloaded = conflicts = 0
        for editor in self._editors():
            if id(editor.lines) in inspected_buffers:
                continue
            inspected_buffers.add(id(editor.lines))
            if not editor.has_external_change():
                continue
            siblings = self._siblings(editor)
            if editor.dirty and editor.merge_external_disk_change():
                for sibling in siblings:
                    sibling.dirty = editor.dirty
                    sibling.lint_pending = True
                    sibling.record_disk_revision(editor.disk_lines)
                reloaded += 1
                continue
            if editor.dirty or any(sibling.external_change_pending for sibling in siblings):
                for sibling in siblings:
                    sibling.external_change_pending = True
                conflicts += 1
                continue
            if editor.reload_from_disk():
                for sibling in siblings:
                    sibling.dirty = False
                    sibling.lint_pending = True
                    sibling.record_disk_revision()
                reloaded += 1
            else:
                for sibling in siblings:
                    sibling.external_change_pending = True
                conflicts += 1
        if conflicts:
            self._report_status("EXTERNAL CHANGE PENDING — SAVE TO OVERWRITE")
        elif reloaded:
            self._report_status(f"RELOADED {reloaded} EXTERNAL FILE{'S' if reloaded != 1 else ''}")
        return reloaded, conflicts
