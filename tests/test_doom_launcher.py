import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from undertow.doom_launcher import DoomLauncher


class DoomLauncherTests(unittest.TestCase):
    def test_launches_local_checkout_with_its_venv_python(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "Doom" / "Doom-PyGame"
            python = root / "venv" / "Scripts" / "python.exe"
            python.parent.mkdir(parents=True)
            python.write_text("", encoding="utf-8")
            (root / "main.py").write_text("pass\n", encoding="utf-8")
            launcher = DoomLauncher(Path(directory) / "IDE")

            with patch("undertow.doom_launcher.subprocess.Popen") as popen:
                self.assertEqual(launcher.launch(), "DOOM LAUNCHED — RIP AND TEAR")

            command = popen.call_args.args[0]
            self.assertEqual(command, [str(python), str(root / "main.py")])
            self.assertEqual(popen.call_args.kwargs["cwd"], str(root))

    def test_reports_when_the_optional_checkout_is_not_installed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(DoomLauncher(Path(directory) / "IDE").launch(), "DOOM NOT FOUND — SET UNDERTOW_DOOM_PATH")
