from pathlib import Path

APP_TITLE = "Cryogenic Data Frontend"

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
STREAM_SOURCE_FILE = Path("../backend/test_stream.csv")

INLINE_CSS = """
body {
    margin: 0;
    font-family: Arial, sans-serif;
    background: #e5e7eb;
}
.app-shell {
    display: grid;
    grid-template-columns: 300px 1fr 260px;
    gap: 12px;
    height: 100vh;
    padding: 6px;
    box-sizing: border-box;
}
.sidebar, .main-panel, .metrics-panel {
    background: #f3f4f6;
    border: 1px solid #d1d5db;
    border-radius: 4px;
    overflow: auto;
}
.sidebar {
    padding: 10px;
}
.main-panel {
    padding: 0 8px;
}
.metrics-panel {
    padding: 8px;
    background: #ffffff;
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
.notes-log {
    margin-top: 8px;
    max-height: 220px;
    overflow-y: auto;
    border: 1px solid #e5e7eb;
    border-radius: 4px;
    background: #ffffff;
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
"""