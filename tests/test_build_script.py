"""Exercise build-script error handling in disposable project copies (no builds)."""

from pathlib import Path
import shutil
import subprocess
import sys

import pytest


POWERSHELL = shutil.which("pwsh") or shutil.which("powershell")
pytestmark = pytest.mark.skipif(
    sys.platform != "win32" or not POWERSHELL, reason="Windows PowerShell build script"
)
ROOT = Path(__file__).resolve().parents[1]
PYTHON = r"C:\Users\SCSM11\anaconda3\envs\music-cleaner\python.exe"


@pytest.mark.parametrize(
    "scenario, message",
    [
        ("missing_python", "Python executable not found"),
        ("missing_installer", "PyInstaller is not installed in the music-cleaner environment"),
        ("build_failure", "PyInstaller failed with exit code 7"),
        ("missing_output", "without the expected executable"),
    ],
)
def test_build_failures_stop_without_success(tmp_path, scenario, message):
    fake_python = tmp_path / "fake-python.cmd"
    if scenario != "missing_python":
        check_code = 1 if scenario == "missing_installer" else 0
        build_code = 7 if scenario == "build_failure" else 0
        fake_python.write_text(
            f'@echo off\nif "%~1"=="-c" exit /b {check_code}\nexit /b {build_code}\n'
        )
    (tmp_path / "packaging").mkdir()
    (tmp_path / "packaging/MusicMetadataCleaner.spec").write_text("# Test stub\n")
    script = tmp_path / "build.ps1"
    script.write_text((ROOT / "build.ps1").read_text().replace(PYTHON, str(fake_python)))
    unrelated = tmp_path / "keep.txt"
    unrelated.write_text("Do not delete")
    old_build = tmp_path / "build"
    old_build.mkdir()
    (old_build / "marker.txt").write_text("Old build")
    result = subprocess.run(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0
    assert message in result.stdout
    assert "Build completed successfully" not in result.stdout
    assert unrelated.read_text() == "Do not delete"
    if scenario in {"missing_python", "missing_installer"}:
        assert (old_build / "marker.txt").exists()
    if scenario == "missing_installer":
        assert f"& '{fake_python}' -m pip install pyinstaller" in result.stdout
