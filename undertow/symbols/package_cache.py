"""A reusable, source-only SQLite cache for installed package functions."""

from __future__ import annotations

import ast
import importlib
import importlib.metadata
import importlib.util
import inspect
import platform
import re
import sqlite3
import sys
import sysconfig
from dataclasses import dataclass
from pathlib import Path

from undertow.function_info import FunctionInfo, function_prototype


@dataclass(frozen=True)
class ScanJob:
    id: int
    package_name: str
    version: str
    site_packages: Path
    python_tag: str
    platform_tag: str


class PackageSymbolCache:
    """Index pip-package function signatures without importing package code."""

    def __init__(self, database_path: Path | None = None) -> None:
        self.database_path = database_path or Path(__file__).with_name("symbol_cache.sqlite3")
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._create_database()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _create_database(self) -> None:
        connection = self._connect()
        try:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS packages (
                    id INTEGER PRIMARY KEY,
                    distribution TEXT NOT NULL,
                    version TEXT NOT NULL,
                    python_tag TEXT NOT NULL,
                    platform_tag TEXT NOT NULL,
                    UNIQUE(distribution, version, python_tag, platform_tag)
                );
                CREATE TABLE IF NOT EXISTS modules (
                    id INTEGER PRIMARY KEY,
                    package_id INTEGER NOT NULL REFERENCES packages(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    source_mtime_ns INTEGER NOT NULL,
                    source_size INTEGER NOT NULL,
                    UNIQUE(package_id, name)
                );
                CREATE TABLE IF NOT EXISTS symbols (
                    id INTEGER PRIMARY KEY,
                    module_id INTEGER NOT NULL REFERENCES modules(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    qualname TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    prototype TEXT NOT NULL,
                    docstring TEXT NOT NULL,
                    line INTEGER NOT NULL,
                    UNIQUE(module_id, qualname)
                );
                CREATE INDEX IF NOT EXISTS symbol_name_lookup ON symbols(name);
                CREATE TABLE IF NOT EXISTS scan_jobs (
                    id INTEGER PRIMARY KEY,
                    package_name TEXT NOT NULL,
                    version TEXT NOT NULL,
                    site_packages TEXT NOT NULL,
                    python_tag TEXT NOT NULL,
                    platform_tag TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('queued', 'running', 'complete', 'failed')),
                    error TEXT NOT NULL DEFAULT '',
                    UNIQUE(package_name, version, python_tag, platform_tag)
                );
                CREATE INDEX IF NOT EXISTS scan_job_status ON scan_jobs(status, id);
            """)
            connection.commit()
        finally:
            connection.close()

    def cache_package(
        self, package_name: str, site_packages: Path | None = None,
        python_tag: str | None = None, platform_tag: str | None = None,
    ) -> int:
        """Rebuild and cache every parseable Python module in one distribution.

        This uses package metadata and reads source files directly; it never
        imports the package, so indexing cannot run its import-time code.
        """
        distribution = self._distribution(package_name, site_packages)
        runtime_python, runtime_platform = self._runtime_key()
        identity = (
            self._normalise_name(distribution.metadata["Name"]),
            distribution.version,
            python_tag or runtime_python,
            platform_tag or runtime_platform,
        )
        connection = self._connect()
        try:
            existing = connection.execute(
                "SELECT id FROM packages WHERE distribution = ? AND version = ? AND python_tag = ? AND platform_tag = ?",
                identity,
            ).fetchone()
            if existing is not None:
                connection.execute("DELETE FROM packages WHERE id = ?", (existing["id"],))
            cursor = connection.execute(
                "INSERT INTO packages(distribution, version, python_tag, platform_tag) VALUES (?, ?, ?, ?)",
                identity,
            )
            package_id = cursor.lastrowid
            count = 0
            for relative_path in distribution.files or ():
                if relative_path.suffix != ".py" or ".dist-info" in relative_path.parts:
                    continue
                source_path = Path(distribution.locate_file(relative_path))
                module_name = self._module_name(relative_path)
                if module_name is None:
                    continue
                try:
                    source = source_path.read_text(encoding="utf-8")
                    tree = ast.parse(source)
                    stat = source_path.stat()
                except (OSError, UnicodeDecodeError, SyntaxError):
                    continue
                module_id = connection.execute(
                    "INSERT INTO modules(package_id, name, source_path, source_mtime_ns, source_size) VALUES (?, ?, ?, ?, ?)",
                    (package_id, module_name, str(source_path), stat.st_mtime_ns, stat.st_size),
                ).lastrowid
                for node, qualname in self._functions(tree):
                    # Python permits multiple declarations for a member name
                    # (for example a @property getter and its setter).  The
                    # cache keeps the first source definition, but must never
                    # abandon the whole package because of that one collision.
                    inserted = connection.execute(
                        "INSERT OR IGNORE INTO symbols(module_id, name, qualname, kind, prototype, docstring, line) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (module_id, node.name, qualname, "function", function_prototype(node), ast.get_docstring(node, clean=True) or "No docstring.", node.lineno - 1),
                    )
                    count += inserted.rowcount
            connection.commit()
        finally:
            connection.close()
        return count

    @staticmethod
    def _distribution(package_name: str, site_packages: Path | None) -> importlib.metadata.Distribution:
        if site_packages is None:
            return importlib.metadata.distribution(package_name)
        target = PackageSymbolCache._normalise_name(package_name)
        for distribution in importlib.metadata.distributions(path=[str(site_packages)]):
            name = distribution.metadata.get("Name", "")
            if PackageSymbolCache._normalise_name(name) == target:
                return distribution
        raise importlib.metadata.PackageNotFoundError(package_name)

    @staticmethod
    def _normalise_name(name: str) -> str:
        return re.sub(r"[-_.]+", "-", name).lower()

    @staticmethod
    def _runtime_key() -> tuple[str, str]:
        return f"{sys.version_info.major}.{sys.version_info.minor}", platform.platform()

    def has_cached_package(self, package_name: str, version: str, python_tag: str | None = None, platform_tag: str | None = None) -> bool:
        """Whether this package build already has a completed shared cache."""
        runtime_python, runtime_platform = self._runtime_key()
        python_tag, platform_tag = python_tag or runtime_python, platform_tag or runtime_platform
        connection = self._connect()
        try:
            return connection.execute(
                "SELECT 1 FROM packages WHERE distribution = ? AND version = ? AND python_tag = ? AND platform_tag = ?",
                (self._normalise_name(package_name), version, python_tag, platform_tag),
            ).fetchone() is not None
        finally:
            connection.close()

    def has_pending_job(self, package_name: str, version: str, python_tag: str | None = None, platform_tag: str | None = None) -> bool:
        """Avoid sending duplicate work to the one scanner process."""
        runtime_python, runtime_platform = self._runtime_key()
        python_tag, platform_tag = python_tag or runtime_python, platform_tag or runtime_platform
        connection = self._connect()
        try:
            return connection.execute(
                "SELECT 1 FROM scan_jobs WHERE package_name = ? AND version = ? AND python_tag = ? AND platform_tag = ? AND status IN ('queued', 'running')",
                (self._normalise_name(package_name), version, python_tag, platform_tag),
            ).fetchone() is not None
        finally:
            connection.close()

    def job_status(self, package_name: str, version: str, python_tag: str | None = None, platform_tag: str | None = None) -> str | None:
        """Expose durable scanner progress to the GUI without worker IPC."""
        runtime_python, runtime_platform = self._runtime_key()
        python_tag, platform_tag = python_tag or runtime_python, platform_tag or runtime_platform
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT status FROM scan_jobs WHERE package_name = ? AND version = ? AND python_tag = ? AND platform_tag = ?",
                (self._normalise_name(package_name), version, python_tag, platform_tag),
            ).fetchone()
            return str(row["status"]) if row is not None else None
        finally:
            connection.close()

    def has_active_jobs(self) -> bool:
        """Whether the worker still has queued or in-flight scan work."""
        connection = self._connect()
        try:
            return connection.execute(
                "SELECT 1 FROM scan_jobs WHERE status IN ('queued', 'running') LIMIT 1"
            ).fetchone() is not None
        finally:
            connection.close()

    def enqueue_package(
        self, package_name: str, version: str, site_packages: Path,
        python_tag: str | None = None, platform_tag: str | None = None,
    ) -> bool:
        """Persist one scan request unless its result or job already exists."""
        runtime_python, runtime_platform = self._runtime_key()
        python_tag, platform_tag = python_tag or runtime_python, platform_tag or runtime_platform
        if self.has_cached_package(package_name, version, python_tag, platform_tag) or self.has_pending_job(package_name, version, python_tag, platform_tag):
            return False
        connection = self._connect()
        try:
            connection.execute(
                "DELETE FROM scan_jobs WHERE package_name = ? AND version = ? AND python_tag = ? AND platform_tag = ?",
                (self._normalise_name(package_name), version, python_tag, platform_tag),
            )
            connection.execute(
                "INSERT INTO scan_jobs(package_name, version, site_packages, python_tag, platform_tag, status) VALUES (?, ?, ?, ?, ?, 'queued')",
                (self._normalise_name(package_name), version, str(site_packages), python_tag, platform_tag),
            )
            connection.commit()
            return True
        finally:
            connection.close()

    def claim_next_job(self) -> ScanJob | None:
        """Claim one persistent job. Only the scanner process calls this."""
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT id, package_name, version, site_packages, python_tag, platform_tag FROM scan_jobs WHERE status = 'queued' ORDER BY id LIMIT 1"
            ).fetchone()
            if row is None:
                connection.commit()
                return None
            connection.execute("UPDATE scan_jobs SET status = 'running', error = '' WHERE id = ?", (row["id"],))
            connection.commit()
            return ScanJob(row["id"], row["package_name"], row["version"], Path(row["site_packages"]), row["python_tag"], row["platform_tag"])
        finally:
            connection.close()

    def finish_job(self, job_id: int, error: str = "") -> None:
        connection = self._connect()
        try:
            connection.execute(
                "UPDATE scan_jobs SET status = ?, error = ? WHERE id = ?",
                ("failed" if error else "complete", error[:400], job_id),
            )
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _module_name(relative_path: Path) -> str | None:
        parts = list(relative_path.parts)
        if not parts:
            return None
        filename = parts.pop()
        stem = Path(filename).stem
        if stem == "__init__":
            return ".".join(parts) or None
        return ".".join([*parts, stem])

    @classmethod
    def _functions(cls, node: ast.AST, prefix: str = ""):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                qualname = f"{prefix}.{child.name}" if prefix else child.name
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    yield child, qualname
                yield from cls._functions(child, qualname)

    def lookup_imported_function(self, lines: list[str], symbol_name: str, tree: ast.AST | None = None) -> FunctionInfo | None:
        """Resolve a cached function through direct or qualified source imports."""
        if tree is None:
            try:
                tree = ast.parse("\n".join(lines))
            except SyntaxError:
                return None
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                for imported in node.names:
                    alias = imported.asname or imported.name
                    if symbol_name == alias:
                        return self.lookup_or_stdlib(node.module, imported.name)
                    if symbol_name.startswith(alias + "."):
                        module, _, function = symbol_name.partition(".")
                        return self.lookup_or_stdlib(f"{node.module}.{imported.name}", function)
            elif isinstance(node, ast.Import):
                for imported in node.names:
                    alias = imported.asname or imported.name.split(".", 1)[0]
                    if not symbol_name.startswith(alias + "."):
                        continue
                    suffix = symbol_name[len(alias) + 1:].split(".")
                    return self.lookup_or_stdlib(".".join([imported.name, *suffix[:-1]]), suffix[-1])
        return None

    def lookup_or_stdlib(self, module_name: str, symbol_name: str) -> FunctionInfo | None:
        """Use cached package data first, then safely inspect standard-library APIs."""
        return self.lookup(module_name, symbol_name) or self._cache_standard_library_symbol(module_name, symbol_name)

    def _cache_standard_library_symbol(self, module_name: str, symbol_name: str) -> FunctionInfo | None:
        """Persist a built-in/stdlib callable, never importing project or pip code."""
        try:
            specification = importlib.util.find_spec(module_name)
        except (ImportError, ValueError):
            return None
        if specification is None or not self._is_standard_library_origin(specification.origin):
            return None
        try:
            module = importlib.import_module(module_name)
            value = getattr(module, symbol_name)
            signature = inspect.signature(value)
        except (AttributeError, ImportError, TypeError, ValueError):
            return None
        if not callable(value):
            return None
        info = FunctionInfo(
            symbol_name,
            0,
            f"def {symbol_name}{signature}",
            inspect.getdoc(value) or "No docstring.",
        )
        self._store_standard_library_symbol(module_name, info)
        return info

    @staticmethod
    def _is_standard_library_origin(origin: str | None) -> bool:
        if origin in {"built-in", "frozen"}:
            return True
        if origin is None:
            return False
        try:
            return Path(origin).resolve().is_relative_to(Path(sysconfig.get_path("stdlib")).resolve()) and "site-packages" not in Path(origin).parts
        except OSError:
            return False

    def _store_standard_library_symbol(self, module_name: str, info: FunctionInfo) -> None:
        python_tag, platform_tag = self._runtime_key()
        connection = self._connect()
        try:
            package = connection.execute(
                "SELECT id FROM packages WHERE distribution = '__stdlib__' AND version = ? AND python_tag = ? AND platform_tag = ?",
                (sys.version, python_tag, platform_tag),
            ).fetchone()
            if package is None:
                package_id = connection.execute(
                    "INSERT INTO packages(distribution, version, python_tag, platform_tag) VALUES ('__stdlib__', ?, ?, ?)",
                    (sys.version, python_tag, platform_tag),
                ).lastrowid
            else:
                package_id = package["id"]
            module = connection.execute(
                "SELECT id FROM modules WHERE package_id = ? AND name = ?", (package_id, module_name)
            ).fetchone()
            if module is None:
                module_id = connection.execute(
                    "INSERT INTO modules(package_id, name, source_path, source_mtime_ns, source_size) VALUES (?, ?, ?, 0, 0)",
                    (package_id, module_name, f"<stdlib:{module_name}>"),
                ).lastrowid
            else:
                module_id = module["id"]
            connection.execute(
                "INSERT OR REPLACE INTO symbols(module_id, name, qualname, kind, prototype, docstring, line) VALUES (?, ?, ?, 'function', ?, ?, 0)",
                (module_id, info.name, info.name, info.prototype, info.docstring),
            )
            connection.commit()
        finally:
            connection.close()

    def lookup(self, module_name: str, symbol_name: str) -> FunctionInfo | None:
        """Return a cached function description, without indexing on demand."""
        connection = self._connect()
        try:
            row = connection.execute("""
                SELECT symbols.name, symbols.line, symbols.prototype, symbols.docstring
                FROM symbols
                JOIN modules ON modules.id = symbols.module_id
                WHERE modules.name = ? AND symbols.name = ?
                ORDER BY symbols.id DESC LIMIT 1
            """, (module_name, symbol_name)).fetchone()
            if row is None:
                row = connection.execute("""
                    SELECT symbols.name, symbols.line, symbols.prototype, symbols.docstring
                    FROM symbols
                    JOIN modules ON modules.id = symbols.module_id
                    WHERE modules.name LIKE ? AND symbols.name = ?
                    ORDER BY symbols.id DESC LIMIT 1
                """, (module_name + ".%", symbol_name)).fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        return FunctionInfo(row["name"], row["line"], row["prototype"], row["docstring"])
