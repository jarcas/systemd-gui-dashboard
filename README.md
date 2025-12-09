# Systemd GUI Dashboard

PyQt6 desktop app to manage systemd services with a simple GUI: list, filter, view detailed status, and run start/stop/restart/reload/enable/disable/mask/unmask via `pkexec` for privileged actions.

## Features
- Table view with Unit, Description, Load, Active, Sub, Enabled and a colored State indicator.
- Live filtering across all columns and inline `systemctl status` details for the selected service.
- Common systemd actions executed with `pkexec /usr/bin/systemctl`.
- State color: green (active), red (inactive/failure), black (disabled/masked).
- Stable layout: Description column stretches; fixed 50px color column; default window 1150x720.

## Requirements
- Python 3.10+ (tested on Ubuntu)
- systemd available (`systemctl`)
- `pkexec` for privileged actions
- Python dependency: `PyQt6` (see `requirements.txt`)

## Installation (user)
Clone the repo and run the installer. It creates a local venv, installs deps, and places a launcher in `~/.local/bin`.

```bash
git clone <repo-url> systemd-gui-dashboard
cd systemd-gui-dashboard
./install.sh
```

After installing:
- Desktop menu: **Systemd GUI Dashboard**
- Terminal: `systemd-gui-dashboard`

## Usage
- Type in the filter box to narrow results; the clear icon wipes the filter.
- Select a service to view `systemctl status` in the lower pane.
- Use action buttons; `pkexec` will prompt for credentials when needed.
- Toolbar **Refresh** reloads the list.

## Uninstall
From the project directory:

```bash
./uninstall.sh
```

Removes the launcher, `.desktop` entry, and the venv at `~/systemd-gui-dashboard`.

## Development / run without installing
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python systemd_gui_dashboard.py
```

## Notes
- Read-only operations use plain `systemctl`; privileged ones run via `pkexec /usr/bin/systemctl`.
- Installs only under the user home; no system files are modified.
