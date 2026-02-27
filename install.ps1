# Sol — One-Line Installer for Windows
# Usage: irm https://raw.githubusercontent.com/Solasticeaistudio/solstice-agent/main/install.ps1 | iex

$ErrorActionPreference = "Stop"

function Write-Step($msg) { Write-Host "  [*] $msg" -ForegroundColor Cyan }
function Write-OK($msg)   { Write-Host "  [+] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "  [!] $msg" -ForegroundColor Yellow }
function Write-Fail($msg) { Write-Host "  [-] $msg" -ForegroundColor Red }

Write-Host ""
Write-Host "  Sol Installer" -ForegroundColor Cyan
Write-Host "  =============" -ForegroundColor Cyan
Write-Host ""

# --- Step 1: Find Python ---
Write-Step "Checking for Python..."

$python = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "Python (\d+)\.(\d+)") {
            $major = [int]$Matches[1]
            $minor = [int]$Matches[2]
            if ($major -ge 3 -and $minor -ge 10) {
                $python = $cmd
                Write-OK "Found $ver ($cmd)"
                break
            } else {
                Write-Warn "$ver is too old (need 3.10+)"
            }
        }
    } catch { }
}

if (-not $python) {
    Write-Fail "Python 3.10+ not found."
    Write-Host ""
    Write-Host "  Install Python from: https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host "  IMPORTANT: Check 'Add Python to PATH' during install." -ForegroundColor Yellow
    Write-Host ""
    exit 1
}

# --- Step 2: Install solstice-agent ---
Write-Step "Installing Sol..."

& $python -m pip install --upgrade solstice-agent 2>&1 | ForEach-Object {
    if ($_ -match "Successfully installed") { Write-OK $_ }
    elseif ($_ -match "WARNING.*not on PATH") { } # We handle this below
    elseif ($_ -match "Requirement already satisfied") { } # Quiet
    else { Write-Host "    $_" -ForegroundColor DarkGray }
}

# --- Step 3: Find and fix PATH ---
Write-Step "Checking PATH..."

# Get the Scripts directory for this Python
$scriptsDir = $null
try {
    $siteResult = & $python -c "import sysconfig; print(sysconfig.get_path('scripts', 'nt_user'))" 2>&1
    if ($siteResult -and (Test-Path $siteResult)) {
        $scriptsDir = $siteResult.Trim()
    }
} catch { }

# Fallback: find where pip installed the exe
if (-not $scriptsDir) {
    try {
        $pipShow = & $python -m pip show solstice-agent 2>&1
        $location = ($pipShow | Select-String "Location:").ToString().Split(": ")[1].Trim()
        $candidate = Join-Path (Split-Path $location) "Scripts"
        if (Test-Path $candidate) { $scriptsDir = $candidate }
    } catch { }
}

# Check if solstice-agent.exe exists there
$solExe = $null
if ($scriptsDir) {
    $candidate = Join-Path $scriptsDir "solstice-agent.exe"
    if (Test-Path $candidate) { $solExe = $candidate }
}

# Is Scripts dir already on PATH?
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
$needsPathFix = $false

if ($scriptsDir -and $solExe) {
    $pathDirs = $userPath -split ";"
    $alreadyOnPath = $pathDirs | Where-Object { $_.Trim().TrimEnd("\") -eq $scriptsDir.TrimEnd("\") }

    if (-not $alreadyOnPath) {
        $needsPathFix = $true
        Write-Warn "Scripts directory not on PATH: $scriptsDir"
        Write-Step "Adding to PATH..."

        # Add to user PATH permanently
        $newPath = "$userPath;$scriptsDir"
        [Environment]::SetEnvironmentVariable("Path", $newPath, "User")

        # Also add to current session so it works immediately
        $env:Path = "$env:Path;$scriptsDir"

        Write-OK "Added $scriptsDir to PATH"
    } else {
        Write-OK "Scripts directory already on PATH"
    }
} else {
    Write-Warn "Could not locate Scripts directory. You may need to add it to PATH manually."
}

# --- Step 4: Verify ---
Write-Step "Verifying installation..."

$solCmd = Get-Command "solstice-agent" -ErrorAction SilentlyContinue
if ($solCmd) {
    Write-OK "solstice-agent is ready!"
} else {
    # Try the python -m fallback
    try {
        & $python -m solstice_agent --help >$null 2>&1
        Write-OK "Installed! Use: python -m solstice_agent"
        Write-Warn "Note: 'solstice-agent' command requires opening a NEW terminal."
    } catch {
        Write-Fail "Installation may have failed. Try: $python -m solstice_agent"
    }
}

# --- Step 5: Show next steps ---
Write-Host ""
Write-Host "  ========================" -ForegroundColor Green
Write-Host "  Sol is installed!" -ForegroundColor Green
Write-Host "  ========================" -ForegroundColor Green
Write-Host ""

if ($needsPathFix) {
    Write-Host "  PATH was updated. Open a NEW terminal, then run:" -ForegroundColor Yellow
} else {
    Write-Host "  Next steps:" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "    solstice-agent --setup    # First-time setup (pick your AI provider)" -ForegroundColor White
Write-Host "    solstice-agent            # Start talking to Sol" -ForegroundColor White
Write-Host ""
