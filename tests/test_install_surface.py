import subprocess
import sys
import venv
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _venv_paths(tmp_path: Path):
    if sys.platform.startswith("win"):
        bindir = tmp_path / "Scripts"
        python = bindir / "python.exe"
        sol = bindir / "sol.exe"
    else:
        bindir = tmp_path / "bin"
        python = bindir / "python"
        sol = bindir / "sol"
    return python, sol


def test_sol_entrypoint_installs_and_reports_help(tmp_path):
    envdir = tmp_path / "venv"
    venv.create(envdir, with_pip=True)
    python, sol = _venv_paths(envdir)

    subprocess.run([str(python), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"], check=True)
    subprocess.run([str(python), "-m", "pip", "install", str(ROOT)], check=True)

    result = subprocess.run([str(sol), "--help"], check=True, capture_output=True, text=True)
    assert "usage: sol " in result.stdout
    assert "--setup" in result.stdout
