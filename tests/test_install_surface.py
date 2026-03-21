import subprocess
import sys
import tomllib
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
    distdir = tmp_path / "dist"
    distdir.mkdir()
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-cache-dir",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(distdir),
            str(ROOT),
        ],
        check=True,
    )
    wheel = next(distdir.glob("solstice_agent-*.whl"))

    envdir = tmp_path / "venv"
    venv.create(envdir, with_pip=True)
    python, sol = _venv_paths(envdir)

    subprocess.run(
        [str(python), "-m", "pip", "install", "--no-deps", str(wheel)],
        check=True,
    )

    result = subprocess.run([str(sol), "--help"], check=True, capture_output=True, text=True)
    assert "usage: sol " in result.stdout
    assert "--setup" in result.stdout


def test_pyproject_keeps_provider_sdks_out_of_base_dependencies():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    deps = pyproject["project"]["dependencies"]
    optional = pyproject["project"]["optional-dependencies"]

    assert all(pkg.split(">=")[0] not in {"openai", "anthropic", "google-genai"} for pkg in deps)
    assert any(pkg.startswith("openai") for pkg in optional["openai"])
    assert any(pkg.startswith("anthropic") for pkg in optional["anthropic"])
    assert any(pkg.startswith("google-genai") for pkg in optional["gemini"])


def test_install_docs_and_scripts_make_provider_choice_explicit():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    install_ps1 = (ROOT / "install.ps1").read_text(encoding="utf-8")
    install_sh = (ROOT / "install.sh").read_text(encoding="utf-8")
    security_doc = (ROOT / "docs" / "SECURITY.md").read_text(encoding="utf-8")
    connectors_doc = (ROOT / "docs" / "CONNECTORS.md").read_text(encoding="utf-8")

    assert "pipx install 'solstice-agent[openai]'" in readme
    assert "docs/SECURITY.md" in readme
    assert "docs/CONNECTORS.md" in readme
    assert 'solstice-agent[openai]' in install_ps1
    assert 'solstice-agent[openai]' in install_sh
    assert "Gateway file access fails closed unless `workspace_root` is configured" in security_doc
    assert "solstice_agent.connectors" in connectors_doc
    assert "ToolRegistry.list_connectors()" in connectors_doc
