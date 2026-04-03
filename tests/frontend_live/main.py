from __future__ import annotations

import io
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set

import dash
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import ALL, Dash, Input, Output, State, callback_context, dash_table, dcc, html
from plotly.subplots import make_subplots

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
DEFAULT_SLIDING_WINDOW_MIN = 12.0
NOTES_FILE = Path("notes_log.json")
STREAM_SOURCE_FILE = Path("fake_live_stream.csv")

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


@dataclass
class DataBundle:
    df: pd.DataFrame


class DataAdapter:
    @staticmethod
    def normalize(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df.columns = [str(c).strip() for c in df.columns]

        if df.empty:
            cols = ["time_min", "fluid", *PRESSURE_SENSORS, *TEMPERATURE_SENSORS, *FLOW_SENSORS, *TRANSFER_SENSORS]
            return pd.DataFrame(columns=cols)

        if "time_min" not in df.columns:
            df = df.rename(columns={df.columns[0]: "time_min"})

        if not pd.api.types.is_numeric_dtype(df["time_min"]):
            try:
                parsed = pd.to_datetime(df["time_min"])
                df["time_min"] = (parsed - parsed.min()).dt.total_seconds() / 60.0
            except Exception as exc:
                raise ValueError("Could not convert the first column into time_min.") from exc

        for col in df.columns:
            if col not in {"time_min", "fluid"}:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        return df.sort_values("time_min").reset_index(drop=True)

    @staticmethod
    def _build_profile(
        t: np.ndarray,
        knots: List[Tuple[float, float]],
        noise: float,
        rng: np.random.Generator,
    ) -> np.ndarray:
        x = [k[0] for k in knots]
        y = [k[1] for k in knots]
        return np.interp(t, x, y) + rng.normal(0, noise, len(t))

    @staticmethod
    def sample_data() -> DataBundle:
        rng = np.random.default_rng(7)
        t = np.linspace(0, 60, 2400)
        pressure_windows: List[Tuple[float, float]] = [(0.7, 11.5), (27.0, 30.0), (50.0, 57.5)]

        df = pd.DataFrame({"time_min": t, "fluid": "Parahydrogen"})

        for i, name in enumerate(PRESSURE_SENSORS, start=1):
            amp = 4.5 - i * 0.15
            phase = i * 0.1
            y = np.full_like(t, 0.9 + i * 0.02)
            for start, end in pressure_windows:
                mask = (t >= start) & (t <= end)
                y[mask] = 0.9 + amp + 0.15 * np.sin((t[mask] + phase) * 4)
                decay_mask = (t > end) & (t < end + 2.0)
                y[decay_mask] = 0.9 + amp * np.exp(-(t[decay_mask] - end) * 1.8)
            y += rng.normal(0, 0.04 + i * 0.002, len(t))
            df[name] = y

        temp_profiles = {
            "TS1": [(0, 42), (4, 50), (9, 58), (14, 52), (21, 47), (27, 43), (31, 50), (40, 39), (48, 34), (52, 44), (58, 60), (60, 56)],
            "TS2": [(0, 55), (4, 61), (9, 68), (14, 60), (21, 56), (27, 51), (31, 60), (40, 48), (48, 42), (52, 58), (58, 79), (60, 72)],
            "TS3": [(0, 72), (4, 79), (9, 85), (14, 77), (21, 71), (27, 66), (31, 74), (40, 60), (48, 53), (52, 70), (58, 97), (60, 88)],
            "TS4": [(0, 89), (4, 96), (9, 104), (14, 92), (21, 84), (27, 77), (31, 90), (40, 73), (48, 64), (52, 84), (58, 114), (60, 104)],
            "TS5": [(0, 108), (4, 117), (9, 125), (14, 111), (21, 101), (27, 92), (31, 108), (40, 86), (48, 77), (52, 102), (58, 136), (60, 126)],
            "TS6": [(0, 142), (4, 150), (9, 158), (14, 141), (21, 129), (27, 117), (31, 143), (40, 101), (48, 92), (52, 132), (58, 175), (60, 168)],
        }
        temp_noise = {"TS1": 0.35, "TS2": 0.40, "TS3": 0.45, "TS4": 0.50, "TS5": 0.55, "TS6": 0.60}
        for name, knots in temp_profiles.items():
            df[name] = DataAdapter._build_profile(t, knots, temp_noise[name], rng)

        df["T_sat PT2"] = np.interp(t, [0, 60], [23.0, 27.0]) + rng.normal(0, 0.05, len(t))
        df["T_sat PT4"] = np.interp(t, [0, 60], [22.0, 26.0]) + rng.normal(0, 0.05, len(t))

        flow = np.zeros_like(t)
        for start, end in pressure_windows:
            mask = (t >= start) & (t <= end)
            flow[mask] = 4.2 * np.clip(np.sin((t[mask] - start) / (end - start) * math.pi), 0.15, 1.0)
            tail = (t > end) & (t <= end + 2.5)
            flow[tail] = 4.0 * np.exp(-(t[tail] - end) * 1.2)
        flow += 0.4 * (((t > 12) & (t < 27)) | ((t > 35.5) & (t < 41.5)) | ((t > 46.5) & (t < 49.0))).astype(float)
        flow += rng.normal(0, 0.04, len(t))
        df["Total Flow"] = np.clip(flow, 0, None)
        df["H, Transferred"] = np.cumsum(df["Total Flow"].clip(lower=0).to_numpy()) * (t[1] - t[0]) * 60 / 1000

        return DataBundle(df=df)


def read_df(data_json: Optional[str]) -> pd.DataFrame:
    if not data_json:
        return DataAdapter.normalize(pd.DataFrame())
    return pd.read_json(io.StringIO(data_json), orient="split")


def df_to_json(df: pd.DataFrame) -> str:
    return df.to_json(date_format="iso", orient="split")


def infer_available_sensors(df: pd.DataFrame) -> Dict[str, List[str]]:
    cols = set(df.columns)
    return {
        group: [sensor for sensor in sensors if sensor in cols]
        for group, sensors in ALL_SENSOR_GROUPS.items()
        if any(sensor in cols for sensor in sensors)
    }


def export_data_bytes(df: pd.DataFrame, export_format: str) -> tuple[bytes, str]:
    fmt = (export_format or "csv").lower()
    if fmt == "csv":
        return df.to_csv(index=False).encode("utf-8"), "text/csv"
    if fmt == "json":
        return df.to_json(orient="records", indent=2).encode("utf-8"), "application/json"
    if fmt == "xlsx":
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Data")
        return buffer.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    raise ValueError(f"Unsupported export format: {export_format}")


def build_figure(
    df: pd.DataFrame,
    sensor_selection: List[str],
    use_sliding_window: bool = False,
    sliding_window_min: float = DEFAULT_SLIDING_WINDOW_MIN,
    active_groups: Optional[Set[str]] = None,
) -> go.Figure:
    if df.empty:
        fig = go.Figure()
        fig.update_layout(
            height=700,
            margin={"l": 60, "r": 20, "t": 40, "b": 50},
            plot_bgcolor="#f4f4f5",
            paper_bgcolor="#f3f4f6",
            font={"family": "Arial, sans-serif", "size": 12},
            annotations=[
                {
                    "text": "Waiting for live data...",
                    "xref": "paper",
                    "yref": "paper",
                    "x": 0.5,
                    "y": 0.5,
                    "showarrow": False,
                    "font": {"size": 18, "color": "#6b7280"},
                }
            ],
            xaxis={"visible": False},
            yaxis={"visible": False},
            uirevision="live-graph",
        )
        return fig

    selection_set = set(sensor_selection)
    available = infer_available_sensors(df)
    active_groups = set(ALL_SENSOR_GROUPS.keys()) if active_groups is None else set(active_groups)
    visible_groups = [group for group in ALL_SENSOR_GROUPS.keys() if group in active_groups and group in available]

    if not visible_groups:
        fig = go.Figure()
        fig.update_layout(
            height=700,
            margin={"l": 60, "r": 20, "t": 40, "b": 50},
            plot_bgcolor="#f4f4f5",
            paper_bgcolor="#f3f4f6",
            font={"family": "Arial, sans-serif", "size": 12},
            annotations=[
                {
                    "text": "No graphs selected",
                    "xref": "paper",
                    "yref": "paper",
                    "x": 0.5,
                    "y": 0.5,
                    "showarrow": False,
                    "font": {"size": 18, "color": "#6b7280"},
                }
            ],
            xaxis={"visible": False},
            yaxis={"visible": False},
            uirevision="live-graph",
        )
        return fig

    subplot_titles = tuple(GROUP_LABELS[group] for group in visible_groups)
    fig = make_subplots(
        rows=len(visible_groups),
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=subplot_titles,
    )

    group_to_row = {group: idx + 1 for idx, group in enumerate(visible_groups)}
    current_time = float(df.iloc[-1]["time_min"])
    x_min = float(df["time_min"].min())
    x_max = float(df["time_min"].max())

    if use_sliding_window:
        window_span = min(sliding_window_min, max(x_max - x_min, 0.5))
        window_end = max(current_time, x_min + window_span)
        window_start = max(x_min, window_end - window_span)
        visible = df[df["time_min"] >= window_start].copy()
        x_range = [window_start, window_end]
    else:
        visible = df.copy()
        x_range = None

    time = visible["time_min"]

    for group in visible_groups:
        row = group_to_row[group]
        for sensor in available[group]:
            if sensor not in selection_set:
                continue
            fig.add_trace(
                go.Scatter(
                    x=time,
                    y=visible[sensor],
                    mode="lines",
                    name=sensor,
                    uid=sensor,
                    line={"color": DEFAULT_COLORS.get(sensor)},
                    showlegend=True,
                    hovertemplate=f"{sensor}<br>Time: %{{x:.2f}} min<br>Value: %{{y:.3f}}<extra></extra>",
                    connectgaps=True,
                ),
                row=row,
                col=1,
            )

    for group in visible_groups:
        row = group_to_row[group]
        fig.add_vline(x=current_time, line_width=1.5, line_dash="solid", line_color="#111827", row=row, col=1)

    figure_height = max(380 * len(visible_groups), 420)
    fig.update_layout(
        height=figure_height,
        margin={"l": 60, "r": 20, "t": 70, "b": 50},
        plot_bgcolor="#f4f4f5",
        paper_bgcolor="#f3f4f6",
        legend={"orientation": "v", "x": 1.01, "y": 1.0, "xanchor": "left", "yanchor": "top"},
        hovermode="x unified",
        font={"family": "Arial, sans-serif", "size": 12},
        uirevision="live-graph",
    )
    fig.update_xaxes(
        title_text="Time [min]",
        showgrid=True,
        gridcolor="rgba(0,0,0,0.10)",
        fixedrange=False,
        autorange=not use_sliding_window,
    )
    if x_range is not None:
        fig.update_xaxes(range=x_range)
    fig.update_yaxes(showgrid=True, gridcolor="rgba(0,0,0,0.10)", autorange=True, fixedrange=False)

    for group in visible_groups:
        row = group_to_row[group]
        fig.update_yaxes(title_text=GROUP_LABELS[group], row=row, col=1)

    return fig


def metric_table(df: pd.DataFrame, sensors: List[str], pinned_idx: Optional[int]) -> List[dict]:
    if df.empty:
        return []

    live_idx = len(df) - 1
    pin_idx = pinned_idx if pinned_idx is not None and 0 <= pinned_idx < len(df) else None
    rows = []
    for sensor in sensors:
        live_val = df.iloc[live_idx][sensor] if sensor in df.columns else np.nan
        pin_val = df.iloc[pin_idx][sensor] if pin_idx is not None and sensor in df.columns else np.nan
        rows.append(
            {
                "sensor": sensor,
                "live": f"{live_val:.3f}" if pd.notna(live_val) else "-",
                "pinned": f"{pin_val:.3f}" if pd.notna(pin_val) else "-",
            }
        )
    return rows


def sensor_checklist_block(group_name: str, sensors: List[str]) -> html.Div:
    return html.Div(
        [
            html.Div(group_name, className="sensor-group-title"),
            dcc.Checklist(
                id={"type": "sensor-checklist", "group": group_name},
                options=[{"label": s, "value": s} for s in sensors],
                value=sensors,
                inputStyle={"margin-right": "8px", "accentColor": "#2563eb"},
                labelStyle={"display": "block", "margin": "3px 0", "fontSize": "13px"},
            ),
        ],
        className="sensor-group-block",
    )


def build_metrics_header() -> html.Div:
    return html.Div(
        [
            html.Div("SENSOR", className="metrics-title left"),
            html.Div("LIVE", className="metrics-title live"),
            html.Div("PINNED", className="metrics-title pinned"),
            html.Button("X", id="clear-pin-btn", n_clicks=0, className="clear-pin-btn"),
        ],
        className="metrics-header",
    )


def render_notes_log(notes: List[dict]) -> List[html.Div]:
    if not notes:
        return [html.Div("No notes yet.", className="save-status")]

    return [
        html.Div(
            [
                html.Div(note.get("timestamp", ""), className="note-timestamp"),
                html.Div(note.get("text", ""), className="note-text"),
            ],
            className="note-entry",
        )
        for note in reversed(notes)
    ]


def load_notes() -> List[dict]:
    if not NOTES_FILE.exists():
        return []
    try:
        with NOTES_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except Exception:
        return []
    return []


def save_notes(notes: List[dict]) -> None:
    with NOTES_FILE.open("w", encoding="utf-8") as f:
        json.dump(notes, f, indent=2)


def empty_frame() -> pd.DataFrame:
    cols = ["time_min", "fluid", *PRESSURE_SENSORS, *TEMPERATURE_SENSORS, *FLOW_SENSORS, *TRANSFER_SENSORS]
    return pd.DataFrame(columns=cols)


def ensure_stream_source_exists() -> None:
    if STREAM_SOURCE_FILE.exists():
        return
    empty_frame().to_csv(STREAM_SOURCE_FILE, index=False)


def load_stream_source() -> pd.DataFrame:
    ensure_stream_source_exists()
    try:
        df = pd.read_csv(STREAM_SOURCE_FILE)
    except pd.errors.EmptyDataError:
        df = empty_frame()
    return DataAdapter.normalize(df)


def append_new_stream_rows(cached_df: pd.DataFrame, source_df: pd.DataFrame, last_time: Optional[float]) -> pd.DataFrame:
    if source_df.empty:
        return cached_df

    if last_time is None or cached_df.empty:
        fresh = source_df.copy()
    else:
        fresh = source_df[source_df["time_min"] > float(last_time)].copy()

    if fresh.empty:
        return cached_df

    combined = pd.concat([cached_df, fresh], ignore_index=True)
    combined = combined.drop_duplicates(subset=["time_min"], keep="last")
    return DataAdapter.normalize(combined)


def create_layout() -> html.Div:
    return html.Div(
        [
            dcc.Store(id="data-store", data=df_to_json(empty_frame())),
            dcc.Store(id="pin-index-store", data=None),
            dcc.Store(id="last-seen-time-store", data=None),
            dcc.Store(id="notes-store", data=load_notes()),
            dcc.Interval(id="stream-interval", interval=POLL_INTERVAL_MS, n_intervals=0, disabled=False),
            dcc.Download(id="download-data"),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("SAVE AS", className="panel-header"),
                            html.Label("File type"),
                            dcc.Dropdown(
                                id="save-format",
                                options=[
                                    {"label": "CSV", "value": "csv"},
                                    {"label": "JSON", "value": "json"},
                                    {"label": "XLSX", "value": "xlsx"},
                                ],
                                value="csv",
                                clearable=False,
                            ),
                            dcc.Checklist(
                                id="save-scope",
                                options=[{"label": "Save visible data only", "value": "visible"}],
                                value=["visible"],
                                inputStyle={"margin-right": "8px"},
                                labelStyle={"display": "block", "fontSize": "13px", "margin": "8px 0 4px 0"},
                            ),
                            html.Button("Save As", id="save-data-btn", className="btn purple-btn"),
                            html.Div(
                                "The app now saves whatever has actually been streamed into the GUI.",
                                id="save-status",
                                className="save-status",
                            ),
                            html.Div(className="divider"),
                            html.Div("STREAM", className="panel-header"),
                            html.Div(f"Polling file: {STREAM_SOURCE_FILE.name}", className="save-status"),
                            dcc.Checklist(
                                id="view-mode-toggle",
                                options=[{"label": "Use sliding window", "value": "sliding"}],
                                value=[],
                                inputStyle={"margin-right": "8px"},
                                labelStyle={"display": "block", "fontSize": "13px", "margin": "4px 0 6px 0"},
                            ),
                            html.Div(className="divider"),
                            html.Div("TOGGLE GRAPHS", className="panel-header"),
                            dcc.Checklist(
                                id="graph-toggle",
                                options=[
                                    {"label": "Pressure", "value": "Pressure"},
                                    {"label": "Temperature", "value": "Temperature"},
                                    {"label": "Mass Flow Rate", "value": "Mass Flow Rate"},
                                    {"label": "H, Transferred", "value": "H, Transferred"},
                                ],
                                value=["Pressure", "Temperature", "Mass Flow Rate", "H, Transferred"],
                                inputStyle={"margin-right": "8px"},
                                labelStyle={"display": "block", "fontSize": "13px", "margin": "3px 0"},
                            ),
                            html.Div(className="divider"),
                            html.Div("TOGGLE SENSORS", className="panel-header"),
                            html.Div(id="sensor-panel"),
                        ],
                        className="sidebar",
                    ),
                    html.Div(
                        [
                            dcc.Graph(
                                id="main-graph",
                                config={"displaylogo": False, "scrollZoom": True},
                                style={"height": "100%"},
                            )
                        ],
                        className="main-panel",
                    ),
                    html.Div(
                        [
                            build_metrics_header(),
                            dash_table.DataTable(
                                id="metrics-table",
                                columns=[
                                    {"name": "Sensor", "id": "sensor"},
                                    {"name": "Live", "id": "live"},
                                    {"name": "Pinned", "id": "pinned"},
                                ],
                                data=[],
                                style_as_list_view=True,
                                style_header={"display": "none"},
                                style_table={"width": "100%"},
                                style_cell={
                                    "padding": "7px 8px",
                                    "fontFamily": "Arial",
                                    "fontSize": "12px",
                                    "border": "none",
                                    "backgroundColor": "#ffffff",
                                    "fontVariantNumeric": "tabular-nums",
                                },
                                style_cell_conditional=[
                                    {"if": {"column_id": "sensor"}, "textAlign": "left", "width": "120px", "minWidth": "120px", "maxWidth": "120px"},
                                    {"if": {"column_id": "live"}, "textAlign": "right", "width": "88px", "minWidth": "88px", "maxWidth": "88px"},
                                    {"if": {"column_id": "pinned"}, "textAlign": "right", "width": "88px", "minWidth": "88px", "maxWidth": "88px"},
                                ],
                                style_data_conditional=[
                                    {"if": {"column_id": "live"}, "color": "#2563eb", "fontWeight": "700"},
                                    {"if": {"column_id": "pinned"}, "color": "#d97706", "fontWeight": "700"},
                                ],
                            ),
                            html.Div("Click chart to pin. Click again to move pin.", className="metrics-help"),
                            html.Div(
                                [
                                    html.Div("NOTES / LOG", className="panel-header"),
                                    dcc.Textarea(
                                        id="notes-input",
                                        className="notes-input",
                                        placeholder="Add a note. Timestamp is added automatically.",
                                    ),
                                    html.Button("Add Note", id="add-note-btn", className="btn purple-btn"),
                                    html.Div(id="notes-log", className="notes-log"),
                                ],
                                className="notes-section",
                            ),
                        ],
                        className="metrics-panel",
                    ),
                ],
                className="app-shell",
            ),
        ]
    )


def register_callbacks(app: Dash) -> None:
    @app.callback(
        Output("notes-store", "data"),
        Output("notes-input", "value"),
        Input("add-note-btn", "n_clicks"),
        State("notes-input", "value"),
        State("notes-store", "data"),
        prevent_initial_call=True,
    )
    def add_note(n_clicks, note_text, notes_data):
        text = (note_text or "").strip()
        if not text:
            return dash.no_update, dash.no_update

        notes = list(notes_data or [])
        timestamp = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
        notes.append({"timestamp": timestamp, "text": text})
        save_notes(notes)
        return notes, ""

    @app.callback(
        Output("notes-log", "children"),
        Input("notes-store", "data"),
    )
    def update_notes_log(notes_data):
        return render_notes_log(notes_data or [])

    @app.callback(
        Output("data-store", "data"),
        Output("last-seen-time-store", "data"),
        Input("stream-interval", "n_intervals"),
        State("data-store", "data"),
        State("last-seen-time-store", "data"),
    )
    def ingest_stream_file(n_intervals, data_json, last_seen_time):
        cached_df = read_df(data_json)
        source_df = load_stream_source()
        updated_df = append_new_stream_rows(cached_df, source_df, last_seen_time)

        if updated_df.empty:
            return df_to_json(updated_df), None

        new_last_seen = float(updated_df.iloc[-1]["time_min"])
        return df_to_json(updated_df), new_last_seen

    @app.callback(
        Output("sensor-panel", "children"),
        Input("data-store", "data"),
    )
    def refresh_controls(data_json):
        df = read_df(data_json)
        available = infer_available_sensors(df)
        sensor_blocks = [sensor_checklist_block(group_name, sensors) for group_name, sensors in available.items()]
        return sensor_blocks

    @app.callback(
        Output("pin-index-store", "data"),
        Input("main-graph", "clickData"),
        Input("clear-pin-btn", "n_clicks"),
        State("data-store", "data"),
        prevent_initial_call=True,
    )
    def manage_pin(click_data, clear_pin_clicks, data_json):
        triggered = callback_context.triggered[0]["prop_id"] if callback_context.triggered else ""
        if triggered.startswith("clear-pin-btn"):
            return None
        if triggered.startswith("main-graph.clickData") and click_data and click_data.get("points"):
            source_df = read_df(data_json)
            if source_df.empty:
                return None
            clicked_x = click_data["points"][0]["x"]
            return int((source_df["time_min"] - float(clicked_x)).abs().idxmin())
        return dash.no_update

    @app.callback(
        Output("main-graph", "figure"),
        Output("metrics-table", "data"),
        Input("data-store", "data"),
        Input("pin-index-store", "data"),
        Input({"type": "sensor-checklist", "group": ALL}, "value"),
        Input("view-mode-toggle", "value"),
        Input("graph-toggle", "value"),
        State({"type": "sensor-checklist", "group": ALL}, "id"),
    )
    def update_figure_and_metrics(data_json, pin_idx, checklist_values, view_mode_value, graph_toggle_value, checklist_ids):
        source_df = read_df(data_json)

        selected: List[str] = []
        for _, values in zip(checklist_ids or [], checklist_values or []):
            selected.extend(values or [])
        if not selected:
            for sensors in infer_available_sensors(source_df).values():
                selected.extend(sensors)

        active_groups = set(graph_toggle_value or [])
        filtered_selected: List[str] = []
        for group, sensors in ALL_SENSOR_GROUPS.items():
            if group in active_groups:
                filtered_selected.extend([s for s in sensors if s in selected])

        use_sliding_window = "sliding" in (view_mode_value or [])
        fig = build_figure(
            source_df,
            filtered_selected,
            use_sliding_window=use_sliding_window,
            active_groups=active_groups,
        )

        if not source_df.empty and pin_idx is not None and 0 <= int(pin_idx) < len(source_df):
            pin_time = float(source_df.iloc[int(pin_idx)]["time_min"])
            available = infer_available_sensors(source_df)
            visible_groups = [group for group in ALL_SENSOR_GROUPS.keys() if group in active_groups and group in available]
            group_to_row = {group: idx + 1 for idx, group in enumerate(visible_groups)}
            for group in visible_groups:
                row = group_to_row[group]
                fig.add_vline(x=pin_time, line_width=1.5, line_dash="solid", line_color="#f59e0b", row=row, col=1)

        table_data = metric_table(source_df, [s for s in filtered_selected if s in source_df.columns], pin_idx)
        return fig, table_data

    @app.callback(
        Output("download-data", "data"),
        Output("save-status", "children"),
        Input("save-data-btn", "n_clicks"),
        State("save-format", "value"),
        State("save-scope", "value"),
        State("data-store", "data"),
        prevent_initial_call=True,
    )
    def save_data(n_clicks, save_format, save_scope, data_json):
        df = read_df(data_json)
        if df.empty:
            return dash.no_update, "No streamed data to save yet."

        use_visible_only = "visible" in (save_scope or [])
        export_df = df.copy()
        scope_label = "visible" if use_visible_only else "full"

        export_format = (save_format or "csv").lower()
        content_bytes, _ = export_data_bytes(export_df, export_format)
        filename = f"cryo_{scope_label}_data.{export_format}"
        status = f"Saving {len(export_df)} streamed rows as {export_format.upper()}."
        return dcc.send_bytes(content_bytes, filename), status


def create_app() -> Dash:
    ensure_stream_source_exists()
    app = Dash(__name__)
    app.title = APP_TITLE
    app.index_string = f"""
    <!DOCTYPE html>
    <html>
        <head>
            {{%metas%}}
            <title>{{%title%}}</title>
            {{%favicon%}}
            {{%css%}}
            <style>{INLINE_CSS}</style>
        </head>
        <body>
            {{%app_entry%}}
            <footer>
                {{%config%}}
                {{%scripts%}}
                {{%renderer%}}
            </footer>
        </body>
    </html>
    """
    app.layout = create_layout()
    register_callbacks(app)
    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
