#!/usr/bin/env bash
# Sol — One-Line Installer for macOS / Linux
# Usage: curl -fsSL https://raw.githubusercontent.com/Solasticeaistudio/solstice-agent/main/install.sh | bash

set -e

CYAN='\033[36m'
GREEN='\033[32m'
YELLOW='\033[33m'
RED='\033[31m'
DIM='\033[2m'
RESET='\033[0m'

step()  { echo -e "  ${CYAN}[*]${RESET} $1"; }
ok()    { echo -e "  ${GREEN}[+]${RESET} $1"; }
warn()  { echo -e "  ${YELLOW}[!]${RESET} $1"; }
fail()  { echo -e "  ${RED}[-]${RESET} $1"; }

echo ""
echo -e "  ${CYAN}Sol Installer${RESET}"
echo -e "  ${CYAN}=============${RESET}"
echo ""

# --- Step 1: Find Python ---
step "Checking for Python..."

PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        ver=$($cmd --version 2>&1)
        if echo "$ver" | grep -qE "Python 3\.(1[0-9]|[2-9][0-9])"; then
            PYTHON="$cmd"
            ok "Found $ver ($cmd)"
            break
        else
            warn "$ver is too old (need 3.10+)"
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    fail "Python 3.10+ not found."
    echo ""
    if [[ "$OSTYPE" == "darwin"* ]]; then
        warn "Install with: brew install python@3.12"
    else
        warn "Install with: sudo apt install python3 python3-pip  (or your distro's equivalent)"
    fi
    echo ""
    exit 1
fi

# --- Step 2: Install solstice-agent ---
step "Installing Sol..."

$PYTHON -m pip install --upgrade solstice-agent 2>&1 | while IFS= read -r line; do
    if echo "$line" | grep -q "Successfully installed"; then
        ok "$line"
    elif echo "$line" | grep -q "WARNING.*not on PATH"; then
        : # handled below
    elif echo "$line" | grep -q "Requirement already satisfied"; then
        : # quiet
    else
        echo -e "    ${DIM}$line${RESET}"
    fi
done

# --- Step 3: Check PATH ---
step "Checking PATH..."

# Get the user scripts directory
SCRIPTS_DIR=$($PYTHON -c "import sysconfig; print(sysconfig.get_path('scripts', vars={'base': sysconfig.get_config_var('base')}))" 2>/dev/null || true)

# Also check user scheme
USER_SCRIPTS=$($PYTHON -c "import site; import os; print(os.path.join(site.getusersitepackages().rsplit('/lib/', 1)[0], 'bin'))" 2>/dev/null || true)

PATH_FIXED=false
SHELL_RC=""

# Detect shell config file
if [ -n "$ZSH_VERSION" ] || [ "$SHELL" = "/bin/zsh" ]; then
    SHELL_RC="$HOME/.zshrc"
elif [ -n "$BASH_VERSION" ] || [ "$SHELL" = "/bin/bash" ]; then
    SHELL_RC="$HOME/.bashrc"
    [ -f "$HOME/.bash_profile" ] && SHELL_RC="$HOME/.bash_profile"
fi

# Check if solstice-agent is findable
if command -v solstice-agent &>/dev/null; then
    ok "solstice-agent is on PATH"
else
    # Find where the exe actually is
    SOL_PATH=""
    for d in "$SCRIPTS_DIR" "$USER_SCRIPTS" "$HOME/.local/bin"; do
        if [ -f "$d/solstice-agent" ]; then
            SOL_PATH="$d"
            break
        fi
    done

    if [ -n "$SOL_PATH" ]; then
        warn "solstice-agent found at $SOL_PATH (not on PATH)"

        if [ -n "$SHELL_RC" ]; then
            step "Adding $SOL_PATH to PATH in $SHELL_RC..."
            echo "" >> "$SHELL_RC"
            echo "# Added by Sol installer" >> "$SHELL_RC"
            echo "export PATH=\"\$PATH:$SOL_PATH\"" >> "$SHELL_RC"
            export PATH="$PATH:$SOL_PATH"
            PATH_FIXED=true
            ok "PATH updated in $SHELL_RC"
        else
            warn "Add this to your shell config: export PATH=\"\$PATH:$SOL_PATH\""
        fi
    else
        warn "Could not locate solstice-agent binary. Try: $PYTHON -m solstice_agent"
    fi
fi

# --- Step 4: Verify ---
step "Verifying installation..."

if command -v solstice-agent &>/dev/null; then
    ok "solstice-agent is ready!"
else
    $PYTHON -m solstice_agent --help &>/dev/null 2>&1 && ok "Installed! Use: $PYTHON -m solstice_agent" || fail "Verification failed."
fi

# --- Done ---
echo ""
echo -e "  ${GREEN}========================${RESET}"
echo -e "  ${GREEN}Sol is installed!${RESET}"
echo -e "  ${GREEN}========================${RESET}"
echo ""

if [ "$PATH_FIXED" = true ]; then
    echo -e "  ${YELLOW}PATH was updated. Open a NEW terminal, then run:${RESET}"
else
    echo -e "  ${CYAN}Next steps:${RESET}"
fi

echo ""
echo "    solstice-agent --setup    # First-time setup (pick your AI provider)"
echo "    solstice-agent            # Start talking to Sol"
echo ""
