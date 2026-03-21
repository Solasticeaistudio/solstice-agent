# Release Checklist

## Goal

Ship Sol as an installable CLI with a verified `sol` command.

## Before tagging

1. Update version in:
- `pyproject.toml`
- `solstice_agent/__init__.py`
- `tests/test_agent.py`
- `CHANGELOG.md`

2. Run local checks:
```bash
pytest tests/test_install_surface.py -q
pytest tests/ -x -q
ruff check solstice_agent/
```

3. Verify the commands from a clean install:
```bash
python -m venv .release-smoke
.release-smoke/bin/python -m pip install .
.release-smoke/bin/sol --help
.release-smoke/bin/python -m pip install 'solstice-agent[openai]'
.release-smoke/bin/sol --help
```

Windows:
```powershell
python -m venv .release-smoke
.\.release-smoke\Scripts\python.exe -m pip install .
.\.release-smoke\Scripts\sol.exe --help
.\.release-smoke\Scripts\python.exe -m pip install "solstice-agent[openai]"
.\.release-smoke\Scripts\sol.exe --help
```

4. Confirm installer copy matches shipped command:
- `install.ps1`
- `install.sh`
- `README.md`
- `docs/SITE_COPY.md`

## Publish

1. Commit
2. Tag: `vX.Y.Z`
3. Push tag
4. Confirm GitHub Actions:
- CI green
- Publish workflow green

## After publish

1. Fresh-machine or fresh-venv install:
```bash
pipx install solstice-agent
sol --help
pipx install 'solstice-agent[openai]'
sol --help
```

2. Verify one-line installers:
- PowerShell installer
- shell installer

3. Update `solsticestudio.ai/sol` if needed
