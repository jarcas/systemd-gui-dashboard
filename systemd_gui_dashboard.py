#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Systemd GUI Dashboard for Ubuntu.

This application provides a graphical interface to:
- List systemd services
- Start / Stop / Restart / Reload services
- Enable / Disable / Mask / Unmask services at boot
- Show detailed status for a selected service

Read-only operations use plain `systemctl` (no root needed).
Privileged operations are run via `pkexec /usr/bin/systemctl ...`,
so the desktop PolicyKit dialog will request admin credentials.
"""

import sys
import subprocess
from typing import Dict, List, Tuple

from PyQt6.QtCore import Qt, QSortFilterProxyModel, QModelIndex
from PyQt6.QtGui import QAction, QPixmap, QColor
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
    QTextEdit,
    QMessageBox,
    QSplitter,
    QStatusBar,
    QToolBar,
    QAbstractItemView,
    QStyle,
    QStyleFactory,
    QHeaderView,
)
from PyQt6.QtGui import QStandardItemModel, QStandardItem


# -------------------------
# Helper functions
# -------------------------

def run_command(command: List[str], require_root: bool = False) -> Tuple[int, str, str]:
    """
    Run a system command and capture exit code, stdout and stderr.

    If require_root is True, the command is prefixed with `pkexec`.
    This will trigger a graphical PolicyKit dialog if necessary.
    """
    full_cmd = command
    if require_root:
        # Use full path to systemctl for pkexec.
        full_cmd = ["pkexec", "/usr/bin/systemctl"] + command[1:]
    try:
        proc = subprocess.run(
            full_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except FileNotFoundError as ex:
        # Typical case: pkexec or systemctl not found
        return 1, "", f"Command not found: {ex}"
    except Exception as ex:  # noqa: BLE001
        return 1, "", f"Unexpected error: {ex}"


def get_services_list() -> List[Dict[str, str]]:
    """
    Get a list of services from systemd.

    Uses:
      - systemctl list-units --type=service --all
      - systemctl list-unit-files --type=service

    Returns:
      List of dicts with keys:
        unit, load, active, sub, description, enabled
    """
    services: List[Dict[str, str]] = []

    # 1) Get enabled/disabled/masked states from list-unit-files
    enabled_map: Dict[str, str] = {}
    code, out, err = run_command(
        ["systemctl", "list-unit-files", "--type=service", "--no-legend", "--no-pager"],
        require_root=False,
    )
    if code == 0:
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            # Typical format: UNIT FILE      STATE   VENDOR_PRESET
            # e.g.: ssh.service              enabled enabled
            parts = line.split()
            if len(parts) < 2:
                continue
            unit_file = parts[0]
            state = parts[1]
            enabled_map[unit_file] = state
    else:
        # If this fails, we still continue without enabled info
        enabled_map = {}

    # 2) Get actual units with their runtime state
    code, out, err = run_command(
        ["systemctl", "list-units", "--type=service", "--all", "--no-legend", "--no-pager"],
        require_root=False,
    )
    if code != 0:
        # If we cannot list services, raise an exception to be handled by caller
        raise RuntimeError(f"Failed to list services:{err}")

    runtime_services: Dict[str, Dict[str, str]] = {}

    for line in out.splitlines():
        line = line.rstrip()
        if not line:
            continue

        # Typical format:
        # UNIT                LOAD   ACTIVE SUB     DESCRIPTION
        # ssh.service         loaded active running OpenBSD Secure Shell server
        parts = line.split()

        # systemctl prefixes failed units with a bullet "●". Drop it so columns align.
        if parts and parts[0] == "●":
            parts = parts[1:]

        if len(parts) < 5:
            # Not expected, but protect against malformed lines
            continue

        unit = parts[0]
        load = parts[1]
        active = parts[2]
        sub = parts[3]
        description = " ".join(parts[4:])

        enabled_state = enabled_map.get(unit, "?")

        runtime_services[unit] = {
            "unit": unit,
            "load": load,
            "active": active,
            "sub": sub,
            "description": description,
            "enabled": enabled_state,
        }

    # Combine runtime units with those that are installed but not loaded
    # so disabled services still appear in the table and can be enabled.
    services.extend(runtime_services.values())

    for unit, state in enabled_map.items():
        if unit in runtime_services:
            continue
        services.append(
            {
                "unit": unit,
                "load": "n/a",
                "active": "inactive",
                "sub": "dead",
                "description": "Not loaded (available to enable/start)",
                "enabled": state,
            }
        )

    return services


def get_service_status(unit: str) -> str:
    """
    Return `systemctl status <unit>` output as a string.
    """
    code, out, err = run_command(
        ["systemctl", "status", unit, "--no-pager"],
        require_root=False,
    )
    if code == 0:
        return out
    # Even if systemctl returned non-zero, showing stderr is useful.
    return out + "\n" + err


def service_state_color(active_state: str, enabled_state: str) -> QColor:
    """Return the QColor representing the service state.

    Priority: disabled/masked -> black; active/running -> green; otherwise red.
    """
    if enabled_state in {"disabled", "masked"}:
        return QColor("black")
    if active_state == "active":
        return QColor("green")
    return QColor("red")


def build_color_icon(color: QColor, size: int = 14) -> QPixmap:
    """Create a small filled square pixmap to show in the table."""
    pixmap = QPixmap(size, size)
    pixmap.fill(color)
    return pixmap


# -------------------------
# Main window
# -------------------------

class ServiceManagerWindow(QMainWindow):
    """
    Main window for Systemd GUI Dashboard.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.setWindowTitle("Systemd GUI Dashboard")
        self.resize(1150, 720)

        # Use a modern, clean style if available
        if "Fusion" in QStyleFactory.keys():
            QApplication.setStyle(QStyleFactory.create("Fusion"))

        # Data model: raw services and proxy for filtering
        # Extra column at the end holds a colored indicator for service state
        self.model = QStandardItemModel(0, 7, self)
        self.model.setHorizontalHeaderLabels(
            ["Unit", "Description", "Load", "Active", "Sub", "Enabled", "State"]
        )

        self.proxy_model = QSortFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.model)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy_model.setFilterKeyColumn(-1)  # Filter over all columns

        # Build UI
        self._create_actions()
        self._create_toolbar()
        self._create_central_widget()
        self._create_status_bar()

        # Load initial data
        self.refresh_services()

    # ---------------------
    # UI creation
    # ---------------------

    def _create_actions(self) -> None:
        """Create actions for toolbar/menu."""
        self.refresh_action = QAction("Refresh", self)
        self.refresh_action.setStatusTip("Reload the list of services")
        self.refresh_action.triggered.connect(self.refresh_services)

        style = self.style()
        self.refresh_action.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_BrowserReload))

    def _create_toolbar(self) -> None:
        """Create top toolbar."""
        toolbar = QToolBar("Main toolbar", self)
        toolbar.setMovable(False)
        toolbar.addAction(self.refresh_action)
        self.addToolBar(toolbar)

    def _create_central_widget(self) -> None:
        """Create main central area: filter, table, details, and control buttons."""
        central = QWidget(self)
        main_layout = QVBoxLayout(central)

        # Filter row
        filter_layout = QHBoxLayout()
        filter_label = QLabel("Filter:", self)
        self.filter_edit = QLineEdit(self)
        self.filter_edit.setPlaceholderText("Type to filter by unit or description...")
        self.filter_edit.textChanged.connect(self.on_filter_changed)

        clear_filter_button = QPushButton(self)
        clear_filter_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_LineEditClearButton))
        clear_filter_button.setToolTip("Clear the filter text")
        clear_filter_button.clicked.connect(self.filter_edit.clear)

        filter_layout.addWidget(filter_label)
        filter_layout.addWidget(self.filter_edit, stretch=1)
        filter_layout.addWidget(clear_filter_button)

        # Table view of services
        self.table_view = QTableView(self)
        self.table_view.setModel(self.proxy_model)
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.verticalHeader().setVisible(False)
        self.table_view.doubleClicked.connect(self.on_row_double_clicked)
        self.table_view.selectionModel().selectionChanged.connect(self.on_selection_changed)

        header = self.table_view.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # Unit
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # Description fills space
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # Load
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Active
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # Sub
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)  # Enabled
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)  # Color indicator
        self.table_view.setColumnWidth(6, 50)

        # Details text area
        self.details_edit = QTextEdit(self)
        self.details_edit.setReadOnly(True)
        self.details_edit.setPlaceholderText("Service details (systemctl status) will appear here.")

        splitter = QSplitter(Qt.Orientation.Vertical, self)
        splitter.addWidget(self.table_view)
        splitter.addWidget(self.details_edit)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        # Buttons for control
        buttons_layout = QHBoxLayout()

        self.start_button = QPushButton("Start", self)
        self.stop_button = QPushButton("Stop", self)
        self.restart_button = QPushButton("Restart", self)
        self.reload_button = QPushButton("Reload", self)
        self.enable_button = QPushButton("Enable", self)
        self.disable_button = QPushButton("Disable", self)
        self.mask_button = QPushButton("Mask", self)
        self.unmask_button = QPushButton("Unmask", self)
        self.status_button = QPushButton("Show Status", self)

        self.start_button.clicked.connect(lambda: self.run_action("start"))
        self.stop_button.clicked.connect(lambda: self.run_action("stop"))
        self.restart_button.clicked.connect(lambda: self.run_action("restart"))
        self.reload_button.clicked.connect(lambda: self.run_action("reload"))
        self.enable_button.clicked.connect(lambda: self.run_action("enable"))
        self.disable_button.clicked.connect(lambda: self.run_action("disable"))
        self.mask_button.clicked.connect(lambda: self.run_action("mask"))
        self.unmask_button.clicked.connect(lambda: self.run_action("unmask"))
        self.status_button.clicked.connect(self.show_status_for_selected)

        for btn in [
            self.start_button,
            self.stop_button,
            self.restart_button,
            self.reload_button,
            self.enable_button,
            self.disable_button,
            self.mask_button,
            self.unmask_button,
            self.status_button,
        ]:
            buttons_layout.addWidget(btn)

        buttons_layout.addStretch(1)

        # Assemble layouts
        main_layout.addLayout(filter_layout)
        main_layout.addWidget(splitter)
        main_layout.addLayout(buttons_layout)

        self.setCentralWidget(central)

        # Initially disable buttons until a row is selected
        self.update_buttons_enabled_state()

    def _create_status_bar(self) -> None:
        """Create status bar."""
        status = QStatusBar(self)
        self.setStatusBar(status)
        self.statusBar().showMessage("Ready")

    # ---------------------
    # Data loading and UI updates
    # ---------------------

    def refresh_services(self) -> None:
        """Reload the list of services from systemctl."""
        self.statusBar().showMessage("Loading services...")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            services = get_services_list()
            self.populate_model(services)
            self.statusBar().showMessage(f"Loaded {len(services)} services.")
        except Exception as ex:  # noqa: BLE001
            QApplication.restoreOverrideCursor()
            self.statusBar().showMessage("Error loading services.")
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to load services:\n{ex}",
            )
            return
        finally:
            QApplication.restoreOverrideCursor()

        self.update_buttons_enabled_state()
        self.details_edit.clear()

    def populate_model(self, services: List[Dict[str, str]]) -> None:
        """Fill the model with a new list of services."""
        self.model.removeRows(0, self.model.rowCount())
        for svc in services:
            active_state = svc["active"]
            enabled_state = svc["enabled"]
            color = service_state_color(active_state, enabled_state)

            status_item = QStandardItem("")
            status_item.setEditable(False)
            status_item.setData(build_color_icon(color), Qt.ItemDataRole.DecorationRole)
            status_item.setToolTip(
                f"Active: {active_state} | Enabled: {enabled_state}"
            )

            row_items = [
                QStandardItem(svc["unit"]),
                QStandardItem(svc["description"]),
                QStandardItem(svc["load"]),
                QStandardItem(active_state),
                QStandardItem(svc["sub"]),
                QStandardItem(enabled_state),
                status_item,
            ]
            for it in row_items:
                # Align text slightly to the left and vertically centered
                it.setEditable(False)
                it.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            self.model.appendRow(row_items)

    def on_filter_changed(self, text: str) -> None:
        """Update proxy filter when filter text changes."""
        self.proxy_model.setFilterFixedString(text)

    def on_selection_changed(self, selected, deselected) -> None:  # noqa: ANN001
        """Called when the selection changes in the table."""
        self.update_buttons_enabled_state()
        self.show_status_for_selected(auto=True)

    def on_row_double_clicked(self, index: QModelIndex) -> None:
        """Double-click on row: show status for that service."""
        self.show_status_for_selected(auto=False)

    def get_selected_unit(self) -> str:
        """
        Return the unit name of the currently selected service or empty string.
        """
        selection_model = self.table_view.selectionModel()
        if not selection_model:
            return ""

        indexes = selection_model.selectedRows()
        if not indexes:
            return ""

        proxy_index = indexes[0]
        source_index = self.proxy_model.mapToSource(proxy_index)

        unit_index = self.model.index(source_index.row(), 0)
        unit = self.model.data(unit_index)
        if not unit:
            return ""
        return str(unit)

    def get_selected_row_states(self) -> Dict[str, str]:
        """
        Return a dict with the main state fields (active, enabled) for the selected row.
        """
        info = {"active": "", "enabled": ""}

        selection_model = self.table_view.selectionModel()
        if not selection_model:
            return info

        indexes = selection_model.selectedRows()
        if not indexes:
            return info

        proxy_index = indexes[0]
        source_index = self.proxy_model.mapToSource(proxy_index)

        active_index = self.model.index(source_index.row(), 3)
        enabled_index = self.model.index(source_index.row(), 5)

        active = self.model.data(active_index) or ""
        enabled = self.model.data(enabled_index) or ""

        info["active"] = str(active)
        info["enabled"] = str(enabled)

        return info

    def update_buttons_enabled_state(self) -> None:
        """Enable or disable buttons depending on selection and service state."""
        unit = self.get_selected_unit()
        has_selection = bool(unit)

        state = self.get_selected_row_states()
        active_state = state["active"]
        enabled_state = state["enabled"]

        # Base enable/disable: disabled if no selection
        for btn in [
            self.start_button,
            self.stop_button,
            self.restart_button,
            self.reload_button,
            self.enable_button,
            self.disable_button,
            self.mask_button,
            self.unmask_button,
            self.status_button,
        ]:
            btn.setEnabled(has_selection)

        if not has_selection:
            return

        # Refine based on states:
        # If service is active, you can stop/restart/reload; if not, you can start.
        if active_state == "active":
            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(True)
            self.restart_button.setEnabled(True)
            self.reload_button.setEnabled(True)
        else:
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            self.restart_button.setEnabled(False)
            # Reload may still make sense if unit is loaded but not active, but keep it simple:
            self.reload_button.setEnabled(True)

        # Enabled / disabled / masked states
        # systemctl list-unit-files states: enabled, disabled, static, masked, etc.
        if enabled_state == "enabled":
            self.enable_button.setEnabled(False)
            self.disable_button.setEnabled(True)
            self.mask_button.setEnabled(True)
            self.unmask_button.setEnabled(False)
        elif enabled_state == "disabled":
            self.enable_button.setEnabled(True)
            self.disable_button.setEnabled(False)
            self.mask_button.setEnabled(True)
            self.unmask_button.setEnabled(False)
        elif enabled_state == "masked":
            self.enable_button.setEnabled(False)
            self.disable_button.setEnabled(False)
            self.mask_button.setEnabled(False)
            self.unmask_button.setEnabled(True)
        else:
            # Unknown or static; keep operations available but limited
            self.enable_button.setEnabled(True)
            self.disable_button.setEnabled(True)
            self.mask_button.setEnabled(True)
            self.unmask_button.setEnabled(True)

    # ---------------------
    # Actions
    # ---------------------

    def run_action(self, action: str) -> None:
        """
        Run a systemctl action requiring root privileges for the selected service.

        Supported actions:
          start, stop, restart, reload, enable, disable, mask, unmask
        """
        unit = self.get_selected_unit()
        if not unit:
            QMessageBox.warning(self, "No selection", "Please select a service first.")
            return

        valid_actions = {
            "start",
            "stop",
            "restart",
            "reload",
            "enable",
            "disable",
            "mask",
            "unmask",
        }
        if action not in valid_actions:
            QMessageBox.critical(self, "Error", f"Invalid action: {action}")
            return

        self.statusBar().showMessage(f"Running '{action}' on {unit}...")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

        # Here we build the command as ["systemctl", action, unit],
        # and run_command will prepend pkexec /usr/bin/systemctl.
        code, out, err = run_command(["systemctl", action, unit], require_root=True)

        QApplication.restoreOverrideCursor()

        if code == 0:
            self.statusBar().showMessage(f"Action '{action}' completed successfully for {unit}.")
            # Refresh list to reflect new state
            self.refresh_services()
            QMessageBox.information(
                self,
                "Success",
                f"Action '{action}' completed successfully for:\n{unit}",
            )
        else:
            self.statusBar().showMessage(f"Action '{action}' failed for {unit}.")
            QMessageBox.critical(
                self,
                "Error",
                (
                    f"Action '{action}' failed for {unit} (exit code {code}).\n\n"
                    f"Output:\n{out}\n\nErrors:\n{err}"
                ),
            )

    def show_status_for_selected(self, auto: bool = False) -> None:
        """
        Show systemctl status for the selected service in the details pane.

        If auto is True, it is triggered by selection change and will not show modal errors.
        """
        unit = self.get_selected_unit()
        if not unit:
            if not auto:
                QMessageBox.warning(self, "No selection", "Please select a service first.")
            self.details_edit.clear()
            return

        self.statusBar().showMessage(f"Loading status for {unit}...")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        status_text = get_service_status(unit)
        QApplication.restoreOverrideCursor()
        self.details_edit.setPlainText(status_text)
        self.statusBar().showMessage(f"Status loaded for {unit}.")


# -------------------------
# Main entry point
# -------------------------

def main() -> None:
    """Application entry point."""
    app = QApplication(sys.argv)
    app.setApplicationName("Systemd GUI Dashboard")
    window = ServiceManagerWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
