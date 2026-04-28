from pathlib import Path

APP_TITLE = "HYPER-DAQ"

PRESSURE_SENSORS = [f"PT{i}" for i in range(1, 8)]
TEMPERATURE_SENSORS = [f"TS{i}" for i in range(1, 7)] + ["T_sat PT2", "T_sat PT4"]
FLOW_SENSORS = ["Total Flow"]
TRANSFER_SENSORS = ["H, Transferred"]

ALL_SENSOR_GROUPS = {
    "Pressure": PRESSURE_SENSORS,
    "Temperature": TEMPERATURE_SENSORS,
    "Mass Flow Rate": FLOW_SENSORS,
    "H, Transferred": TRANSFER_SENSORS,
}

GROUP_LABELS = {
    "Pressure": "Pressure [bara]",
    "Temperature": "Temperature [K]",
    "Mass Flow Rate": "Mass Flow Rate [g/s]",
    "H, Transferred": "Total H₂ Transferred [kg]",
}

DEFAULT_COLORS = {
    "PT1": "#e53935",
    "PT2": "#f9a825",
    "PT3": "#8e44ad",
    "PT4": "#43a047",
    "PT5": "#1e88e5",
    "PT6": "#3949ab",
    "PT7": "#ab47bc",
    "TS1": "#ef5350",
    "TS2": "#fb8c00",
    "TS3": "#43a047",
    "TS4": "#1e88e5",
    "TS5": "#5e35b1",
    "TS6": "#616161",
    "T_sat PT2": "#f57c00",
    "T_sat PT4": "#2e7d32",
    "Total Flow": "#111827",
    "H, Transferred": "#1e88e5",
}

POLL_INTERVAL_MS = 120
DEFAULT_WINDOW_VALUE = 5.0
DEFAULT_WINDOW_UNIT = "min"
WINDOW_UNIT_TO_MINUTES = {"min": 1.0, "hr": 60.0}
AUTOSCALE_MAX_ROWS = 120_000
NOTES_FILE = Path("notes_log.json")
STREAM_SOURCE_FILE = Path("../backend/sensor_buffer.csv")

INLINE_CSS = """
body {
    margin: 0;
    font-family: Arial, sans-serif;
    background: #e5e7eb;
}
#app-root {
    min-height: 100vh;
    background: #e5e7eb;
    color: #111827;
    transition: background-color 220ms ease, color 220ms ease;
}
#app-root.dark-mode {
    background: #050816;
    color: #e5e7eb;
}
#app-root.dark-mode.flash-start {
    animation: logging-flash 1.2s ease;
}
@keyframes logging-flash {
    0% { box-shadow: inset 0 0 0 0 rgba(34, 197, 94, 0.0); }
    18% { box-shadow: inset 0 0 0 9999px rgba(34, 197, 94, 0.22); }
    100% { box-shadow: inset 0 0 0 0 rgba(34, 197, 94, 0.0); }
}
.app-banner {
    width: 100%;
    box-sizing: border-box;
    padding: 12px 18px;
    font-size: 14px;
    font-weight: 700;
    letter-spacing: 0.02em;
    transition: background-color 220ms ease, color 220ms ease;
}
.banner-off {
    background: #b91c1c;
    color: #ffffff;
}
.banner-on {
    background: #15803d;
    color: #ffffff;
}
.app-shell {
    display: grid;
    grid-template-columns: 300px 1fr 260px;
    gap: 12px;
    height: calc(100vh - 48px);
    padding: 6px;
    box-sizing: border-box;
}
.sidebar, .main-panel, .metrics-panel {
    background: #f3f4f6;
    border: 1px solid #d1d5db;
    border-radius: 4px;
    overflow: auto;
    transition: background-color 220ms ease, border-color 220ms ease, color 220ms ease;
}
#app-root.dark-mode .sidebar,
#app-root.dark-mode .main-panel,
#app-root.dark-mode .metrics-panel {
    background: #0f172a;
    border-color: #334155;
    color: #e5e7eb;
}
.sidebar {
    padding: 10px;
}
.main-panel {
    padding: 0 8px 8px 8px;
}
.metrics-panel {
    padding: 8px;
    background: #ffffff;
}
.main-toolbar {
    position: sticky;
    top: 0;
    z-index: 5;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 10px 4px 8px 4px;
    background: inherit;
}
.toolbar-status {
    display: flex;
    flex-direction: column;
    gap: 3px;
}
.toolbar-title {
    font-size: 16px;
    font-weight: 700;
}
.toolbar-subtitle {
    font-size: 12px;
    color: #6b7280;
}
#app-root.dark-mode .toolbar-subtitle,
#app-root.dark-mode label,
#app-root.dark-mode .sensor-group-title,
#app-root.dark-mode .save-status,
#app-root.dark-mode .metrics-help,
#app-root.dark-mode .metrics-title,
#app-root.dark-mode .note-timestamp {
    color: #cbd5e1;
}
.logging-toggle-btn {
    min-width: 160px;
    border: none;
    border-radius: 999px;
    padding: 12px 18px;
    font-size: 13px;
    font-weight: 700;
    cursor: pointer;
    color: #ffffff;
    transition: transform 160ms ease, background-color 220ms ease, box-shadow 220ms ease;
}
.logging-toggle-btn:hover {
    transform: translateY(-1px);
}
.toggle-off {
    background: #dc2626;
    box-shadow: 0 0 0 2px rgba(220, 38, 38, 0.15);
}
.toggle-on {
    background: #16a34a;
    box-shadow: 0 0 0 2px rgba(22, 163, 74, 0.18), 0 0 18px rgba(34, 197, 94, 0.25);
}
.panel-header {
    font-size: 12px;
    font-weight: 700;
    color: #3b82f6;
    margin: 8px 0 6px;
}
.divider {
    border-top: 1px solid #d1d5db;
    margin: 10px 0;
}
#app-root.dark-mode .divider,
#app-root.dark-mode .metrics-header,
#app-root.dark-mode .notes-section,
#app-root.dark-mode .note-entry,
#app-root.dark-mode .notes-log {
    border-color: #334155;
}
.btn {
    width: 100%;
    border: none;
    border-radius: 2px;
    padding: 10px 12px;
    color: white;
    font-weight: 700;
    cursor: pointer;
    margin-top: 8px;
}
.success-btn { background: #16a34a; }
.purple-btn { background: #7c3aed; }
.danger-btn { background: #dc2626; }
.text-input {
    width: 100%;
    margin-bottom: 6px;
    box-sizing: border-box;
    border: 1px solid #d1d5db;
    border-radius: 4px;
    padding: 8px 10px;
    background: #ffffff;
    color: #111827;
}
label {
    display: block;
    font-size: 12px;
    color: #374151;
    margin: 6px 0 4px;
}
.sensor-group-title {
    font-size: 12px;
    color: #6b7280;
    border-top: 1px solid #e5e7eb;
    padding-top: 8px;
    margin-top: 6px;
}
.metrics-header {
    display: grid;
    grid-template-columns: 1fr 88px 88px 24px;
    align-items: center;
    column-gap: 14px;
    border-bottom: 1px solid #e5e7eb;
    padding: 4px 0 8px 0;
    margin-bottom: 6px;
    position: sticky;
    top: 0;
    background: white;
    z-index: 2;
}
#app-root.dark-mode .metrics-header {
    background: #0f172a;
}
.metrics-title {
    font-size: 11px;
    font-weight: 700;
    color: #6b7280;
}
.metrics-title.left {
    text-align: left;
}
.metrics-title.live,
.metrics-title.pinned {
    text-align: right;
}
.metrics-title.live { color: #2563eb; }
.metrics-title.pinned { color: #dc2626; }
.clear-pin-btn {
    border: none;
    background: transparent;
    color: #ef4444;
    font-weight: 700;
    cursor: pointer;
}
.metrics-help {
    font-size: 11px;
    color: #6b7280;
    margin-top: 8px;
}
.save-status {
    font-size: 11px;
    color: #6b7280;
    margin-top: 6px;
    line-height: 1.4;
}
.notes-section {
    margin-top: 12px;
    border-top: 1px solid #e5e7eb;
    padding-top: 10px;
}
.notes-input {
    width: 100%;
    box-sizing: border-box;
    min-height: 72px;
    resize: vertical;
    padding: 8px;
    font-family: Arial, sans-serif;
    font-size: 12px;
    border: 1px solid #d1d5db;
    border-radius: 4px;
    background: #ffffff;
}
#app-root.dark-mode .notes-input,
#app-root.dark-mode .text-input {
    background: #111827;
    color: #e5e7eb;
    border-color: #334155;
}
#app-root.dark-mode .text-input::placeholder,
#app-root.dark-mode .notes-input::placeholder {
    color: #94a3b8;
}
#app-root.dark-mode .daq-dropdown,
#app-root.dark-mode .daq-dropdown .Select,
#app-root.dark-mode .daq-dropdown .Select-control,
#app-root.dark-mode .daq-dropdown .Select-menu-outer,
#app-root.dark-mode .daq-dropdown .Select-menu,
#app-root.dark-mode .daq-dropdown .Select-placeholder,
#app-root.dark-mode .daq-dropdown .Select-value,
#app-root.dark-mode .daq-dropdown .Select-value-label,
#app-root.dark-mode .daq-dropdown .Select div,
#app-root.dark-mode .daq-dropdown input,
#app-root.dark-mode .daq-dropdown .Select-input > input,
#app-root.dark-mode .daq-dropdown .VirtualizedSelectOption,
#app-root.dark-mode .daq-dropdown .VirtualizedSelectFocusedOption {
    background: #111827 !important;
    color: #e5e7eb !important;
}
#app-root.dark-mode .daq-dropdown .Select-control,
#app-root.dark-mode .daq-dropdown .Select-menu-outer {
    border-color: #334155 !important;
    background-image: none !important;
}
#app-root.dark-mode .daq-dropdown .Select-value,
#app-root.dark-mode .daq-dropdown .Select-placeholder {
    line-height: 34px !important;
}
#app-root.dark-mode .daq-dropdown .Select.is-open > .Select-control,
#app-root.dark-mode .daq-dropdown .Select.is-focused > .Select-control {
    border-color: #3b82f6 !important;
    box-shadow: 0 0 0 1px #3b82f6 !important;
}
#app-root.dark-mode .daq-dropdown .Select-arrow-zone,
#app-root.dark-mode .daq-dropdown .Select-clear-zone,
#app-root.dark-mode .daq-dropdown .Select-arrow {
    color: #cbd5e1 !important;
    border-top-color: #cbd5e1 !important;
}
#app-root.dark-mode .daq-dropdown .is-open > .Select-control .Select-arrow {
    border-bottom-color: #cbd5e1 !important;
    border-top-color: transparent !important;
}
#app-root.dark-mode .daq-dropdown .VirtualizedSelectFocusedOption {
    background: #1e293b !important;
}
#app-root.dark-mode .dash-table-container .dash-spreadsheet-container .dash-spreadsheet-inner td,
#app-root.dark-mode .dash-table-container .dash-spreadsheet-container .dash-spreadsheet-inner th,
#app-root.dark-mode .dash-table-container .dash-spreadsheet-container .dash-spreadsheet-inner table {
    background: #0f172a !important;
    color: #e5e7eb !important;
    border-color: #334155 !important;
}
.notes-log {
    margin-top: 8px;
    max-height: 220px;
    overflow-y: auto;
    border: 1px solid #e5e7eb;
    border-radius: 4px;
    background: #ffffff;
}
#app-root.dark-mode .notes-log {
    background: #111827;
}
.note-entry {
    padding: 8px;
    border-bottom: 1px solid #f3f4f6;
}
.note-entry:last-child {
    border-bottom: none;
}
.note-timestamp {
    font-size: 11px;
    color: #6b7280;
    margin-bottom: 4px;
}
.note-text {
    font-size: 12px;
    color: #111827;
    white-space: pre-wrap;
    line-height: 1.4;
}
#app-root.dark-mode .note-text {
    color: #e5e7eb;
}
.custom-graphs-container {
    display: flex;
    flex-direction: column;
    gap: 10px;
}
.custom-graph-card {
    position: relative;
    border: 1px solid #d1d5db;
    border-radius: 4px;
    background: #f3f4f6;
    padding-top: 4px;
}
#app-root.dark-mode .custom-graph-card {
    background: #0f172a;
    border-color: #334155;
}
.custom-remove-btn {
    position: absolute;
    bottom: 10px;
    right: 10px;
    z-index: 4;
    width: 24px;
    height: 24px;
    border: none;
    border-radius: 50%;
    background: rgba(17, 24, 39, 0.08);
    color: #ef4444;
    font-size: 18px;
    font-weight: 700;
    line-height: 22px;
    cursor: pointer;
}
.custom-remove-btn:hover {
    background: rgba(239, 68, 68, 0.14);
}
#app-root.dark-mode .custom-remove-btn {
    background: rgba(226, 232, 240, 0.10);
    color: #f87171;
}

"""