#!/usr/bin/env bash
set -e

# Installer for Systemd GUI Dashboard on Ubuntu
# - Creates a local Python virtual environment in the project directory
# - Installs Python dependencies inside the venv
# - Creates a launcher script in ~/.local/bin
# - Installs a .desktop file in ~/.local/share/applications

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="systemd-gui-dashboard"
VENV_DIR="${SCRIPT_DIR}/.venv"
LAUNCHER_PATH="${HOME}/.local/bin/${APP_NAME}"
DESKTOP_DIR="${HOME}/.local/share/applications"
DESKTOP_FILE="${DESKTOP_DIR}/${APP_NAME}.desktop"

echo "Installing Systemd GUI Dashboard..."

# 1) Check python3
if ! command -v python3 >/dev/null 2>&1; then
    echo "Error: python3 not found. Please install Python 3."
    exit 1
fi

# 2) Ensure venv module exists (python3-venv)
if ! python3 -m venv --help >/dev/null 2>&1; then
    echo "Error: 'venv' module not available."
    echo "Install it with:  sudo apt install python3-venv"
    exit 1
fi

# 3) Create virtual environment if it does not exist
if [ ! -d "${VENV_DIR}" ]; then
    echo "Creating virtual environment in ${VENV_DIR}..."
    python3 -m venv "${VENV_DIR}"
fi

# 4) Install Python dependencies inside the venv
echo "Installing Python dependencies (PyQt6) into the virtual environment..."
"${VENV_DIR}/bin/pip" install --upgrade pip
"${VENV_DIR}/bin/pip" install -r "${SCRIPT_DIR}/requirements.txt"

# 5) Create ~/.local/bin if it does not exist
mkdir -p "${HOME}/.local/bin"

# 6) Create launcher script
cat > "${LAUNCHER_PATH}" <<EOF
#!/usr/bin/env bash
# Launcher for Systemd GUI Dashboard
VENV_DIR="${VENV_DIR}"
exec "\${VENV_DIR}/bin/python" "${SCRIPT_DIR}/systemd_gui_dashboard.py" "\$@"
EOF

chmod +x "${LAUNCHER_PATH}"

# 7) Install .desktop file
mkdir -p "${DESKTOP_DIR}"
cp "${SCRIPT_DIR}/${APP_NAME}.desktop" "${DESKTOP_FILE}"

# 8) Update desktop database (if available)
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "${DESKTOP_DIR}" || true
fi

echo "Installation completed."
echo
echo "You can run the application from your desktop menu as:"
echo "  Systemd GUI Dashboard"
echo
echo "Or from a terminal with:"
echo "  ${APP_NAME}"
