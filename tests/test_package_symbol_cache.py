import tempfile
import time
import platform
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from undertow.symbols import PackageSymbolCache
from undertow.symbols import SymbolScannerManager


class PackageSymbolCacheTests(unittest.TestCase):
    def test_creates_database_and_caches_package_symbols_without_importing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "wavepkg"
            package.mkdir()
            (package / "__init__.py").write_text("from .tools import surf\n", encoding="utf-8")
            (package / "tools.py").write_text(
                'def surf(board: str, height: int = 2) -> bool:\n    """Ride a wave."""\n    return True\n',
                encoding="utf-8",
            )

            class Distribution:
                version = "1.0"
                files = [Path("wavepkg/__init__.py"), Path("wavepkg/tools.py")]
                metadata = {"Name": "wavepkg"}

                @staticmethod
                def locate_file(path: Path) -> Path:
                    return root / path

            cache = PackageSymbolCache(root / "symbols.sqlite3")
            with patch("undertow.symbols.package_cache.importlib.metadata.distribution", return_value=Distribution()):
                self.assertEqual(cache.cache_package("wavepkg"), 1)
            self.assertTrue((root / "symbols.sqlite3").exists())
            result = cache.lookup("wavepkg.tools", "surf")
            self.assertIsNotNone(result)
            self.assertEqual(result.prototype, "def surf(board: str, height: int = 2) -> bool")
            self.assertEqual(result.docstring, "Ride a wave.")

    def test_lookup_from_import_routes_hover_to_cached_symbol(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache = PackageSymbolCache(Path(directory) / "symbols.sqlite3")
            with closing(cache._connect()) as connection:
                package_id = connection.execute(
                    "INSERT INTO packages(distribution, version, python_tag, platform_tag) VALUES ('wavepkg', '1', '3.14', 'win')"
                ).lastrowid
                module_id = connection.execute(
                    "INSERT INTO modules(package_id, name, source_path, source_mtime_ns, source_size) VALUES (?, 'wavepkg.tools', 'tools.py', 0, 0)",
                    (package_id,),
                ).lastrowid
                connection.execute(
                    "INSERT INTO symbols(module_id, name, qualname, kind, prototype, docstring, line) VALUES (?, 'surf', 'surf', 'function', 'def surf() -> None', 'Ride.', 0)",
                    (module_id,),
                )
                connection.commit()
            result = cache.lookup_imported_function(["from wavepkg.tools import surf", "surf()"], "surf")
            self.assertEqual(result.prototype, "def surf() -> None")
            result = cache.lookup_imported_function(["import wavepkg.tools as waves", "waves.surf()"], "waves.surf")
            self.assertEqual(result.prototype, "def surf() -> None")

    def test_duplicate_property_declarations_do_not_abort_the_package_scan(self) -> None:
        """One getter/setter name collision must not hide later package APIs."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "wavepkg"
            package.mkdir()
            (package / "__init__.py").write_text("", encoding="utf-8")
            (package / "coast.py").write_text(
                "class Tide:\n"
                "    @property\n"
                "    def level(self) -> int:\n"
                "        return 0\n\n"
                "    @level.setter\n"
                "    def level(self, value: int) -> None:\n"
                "        pass\n\n"
                "def after_the_break() -> str:\n"
                "    return 'clear'\n",
                encoding="utf-8",
            )

            class Distribution:
                version = "1.0"
                files = [Path("wavepkg/__init__.py"), Path("wavepkg/coast.py")]
                metadata = {"Name": "wavepkg"}

                @staticmethod
                def locate_file(path: Path) -> Path:
                    return root / path

            cache = PackageSymbolCache(root / "symbols.sqlite3")
            with patch("undertow.symbols.package_cache.importlib.metadata.distribution", return_value=Distribution()):
                self.assertEqual(cache.cache_package("wavepkg"), 2)
            self.assertIsNotNone(cache.lookup("wavepkg.coast", "level"))
            self.assertIsNotNone(cache.lookup("wavepkg.coast", "after_the_break"))

    def test_standard_library_builtin_is_cached_for_hover(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache = PackageSymbolCache(Path(directory) / "symbols.sqlite3")
            result = cache.lookup_imported_function(["import time", "time.sleep(1)"], "time.sleep")
            self.assertIsNotNone(result)
            self.assertEqual(result.name, "sleep")
            self.assertIn("def sleep", result.prototype)
            self.assertTrue(result.docstring)
            self.assertIsNotNone(cache.lookup("time", "sleep"))

    def test_scanner_manager_queues_only_missing_and_unqueued_venv_packages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            site_packages = root / ".venv" / "Lib" / "site-packages"
            metadata = site_packages / "wavepkg-1.0.dist-info"
            metadata.mkdir(parents=True)
            (metadata / "METADATA").write_text("Name: wavepkg\nVersion: 1.0\n", encoding="utf-8")
            (root / ".venv" / "pyvenv.cfg").write_text("version = 3.12.4\n", encoding="utf-8")
            cache = PackageSymbolCache(root / "symbols.sqlite3")
            manager = SymbolScannerManager(cache, interval_ms=30_000, start_worker=False)

            self.assertEqual(manager.update(root, 0), 1)
            self.assertTrue(cache.has_pending_job("wavepkg", "1.0", "3.12", platform.platform()))
            self.assertTrue(manager.is_busy)
            self.assertEqual(manager.update(root, 30_000), 0)

    def test_scanner_busy_state_tracks_active_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = PackageSymbolCache(root / "symbols.sqlite3")
            self.assertFalse(cache.has_active_jobs())
            self.assertTrue(cache.enqueue_package("wavepkg", "1.0", root))
            self.assertTrue(cache.has_active_jobs())

    def test_worker_process_consumes_a_persisted_job(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            site_packages = root / ".venv" / "Lib" / "site-packages"
            package = site_packages / "wavepkg"
            metadata = site_packages / "wavepkg-1.0.dist-info"
            package.mkdir(parents=True)
            metadata.mkdir()
            (package / "__init__.py").write_text('def surf() -> bool:\n    """Ride."""\n    return True\n', encoding="utf-8")
            (metadata / "METADATA").write_text("Name: wavepkg\nVersion: 1.0\n", encoding="utf-8")
            (metadata / "RECORD").write_text("wavepkg/__init__.py,,\nwavepkg-1.0.dist-info/METADATA,,\nwavepkg-1.0.dist-info/RECORD,,\n", encoding="utf-8")
            cache = PackageSymbolCache(root / "symbols.sqlite3")
            manager = SymbolScannerManager(cache, start_worker=True)
            try:
                self.assertEqual(manager.update(root, 0), 1)
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline and cache.job_status("wavepkg", "1.0") not in {"complete", "failed"}:
                    time.sleep(0.1)
                self.assertEqual(cache.job_status("wavepkg", "1.0"), "complete")
                self.assertIsNotNone(cache.lookup("wavepkg", "surf"))
            finally:
                manager.stop()


if __name__ == "__main__":
    unittest.main()
