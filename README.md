# Undertow

A tiny, game-like Python editor built with Pygame. It is a deliberately focused
prototype: type code, save it, run it with the current Python interpreter, and
read its output without leaving the window.

## Run

```powershell
py -m pip install -r requirements.txt
py main.py
```

## Verify

Run the tests and print the coverage percentage:

```powershell
.\tools\test-coverage.ps1
```

Pass `-TotalOnly` for just the percentage, or `-Html` to also write a browsable report to `htmlcov\index.html`.

## Controls

- Startup opens a pixel-styled project screen. Choose `OPEN PROJECT` and browse to an Undertow folder, or `CREATE PROJECT` to name a fresh child folder in the built-in file tree. A project must contain `[tool.undertow]` in `pyproject.toml`.
- The startup screen also lists the ten most recently opened projects. These machine-local preferences live in `%APPDATA%\Undertow\settings.toml`, separate from project files.
- `Ctrl+S` saves the document to `scratch.py`.
- `F5` or `Ctrl+Enter` runs the document.
- Drag with the left mouse button to select text; `Ctrl+C` copies and `Ctrl+V` pastes.
- Right-click opens controls for the pane under the pointer.
- An editor pane's context menu offers `VSPLIT PANE` and `HSPLIT PANE`; both views share the same document but keep separate carets, selections, and scroll positions.
- Pane arrangements are restored when Undertow starts and saved into `[tool.undertow].pane_layout` in `pyproject.toml` when it closes. Use `SAVE LAYOUT` in any pane's context menu to save immediately.
- `Tab` inserts four spaces; `Enter` keeps the current indentation.
- `Ctrl+Backspace` removes the preceding word.

The interface deliberately uses a pixel-style terminal palette inspired by the
reference: near-black panels, faded burgundy atmosphere, white active edges,
and cyan status lights.
