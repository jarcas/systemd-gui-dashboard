#!/usr/bin/env bash
set -e

APP_NAME="systemd-gui-dashboard"

echo "-----------------------------"
echo " ${APP_NAME} – Uninstaller"
echo "-----------------------------"
echo

# 1. Rutas utilizadas por install.sh
PROJECT_DIR="$HOME/${APP_NAME}"
LAUNCHER="$HOME/.local/bin/${APP_NAME}"
DESKTOP_FILE="$HOME/.local/share/applications/${APP_NAME}.desktop"
VENV_DIR="$PROJECT_DIR/.venv"

# 2. Eliminar lanzador
if [ -f "$LAUNCHER" ]; then
    echo "Removing launcher: $LAUNCHER"
    rm "$LAUNCHER"
else
    echo "Launcher not found: $LAUNCHER"
fi

# 3. Eliminar archivo .desktop del menú
if [ -f "$DESKTOP_FILE" ]; then
    echo "Removing desktop entry: $DESKTOP_FILE"
    rm "$DESKTOP_FILE"
else
    echo "Desktop entry not found: $DESKTOP_FILE"
fi

# 4. Eliminar proyecto + entorno virtual
if [ -d "$PROJECT_DIR" ]; then
    echo "Removing project directory: $PROJECT_DIR"
    rm -rf "$PROJECT_DIR"
else
    echo "Project directory not found: $PROJECT_DIR"
fi

echo
echo "Updating desktop database (optional)…"
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$HOME/.local/share/applications" || true
else
    echo "update-desktop-database not available; skipping."
fi

echo
echo "✔ Uninstallation completed."
echo "No system files were modified."
echo "All user-installed components of '${APP_NAME}' have been removed."
echo
