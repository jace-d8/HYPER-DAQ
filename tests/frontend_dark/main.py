from __future__ import annotations

import base64
import io
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import dash
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, State, callback_context, dash_table, dcc, html
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
    "Total Flow": "#991b1b",
    "H, Transferred": "#1e88e5",
}

GROUP_TO_ROW = {
    "Pressure": 1,
    "Temperature": 2,
    "Mass Flow Rate": 3,
    "H, Transferred": 4,
}

SUBPLOT_TITLES = (
    "Pressure [bara]",
    "Temperature [K]",
    "Mass Flow Rate [g/s]",
    "Total H₂ Transferred [kg]",
)

INLINE_CSS = """
body {
    margin: 0;
    font-family: Inter, Arial, sans-serif;
    background: #0b1220;
    color: #e5e7eb;
}
.app-shell {
    display: grid;
    grid-template-columns: 300px 1fr 260px;
    gap: 14px;
    height: 100vh;
    padding: 10px;
    box-sizing: border-box;
    background: linear-gradient(180deg, #0b1220 0%, #111827 100%);
}
.sidebar, .main-panel, .metrics-panel {
    background: rgba(17, 24, 39, 0.96);
    border: 1px solid #263244;
    border-radius: 16px;
    overflow: auto;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.28);
}
.sidebar {
    padding: 14px;
}
.main-panel {
    padding: 6px 10px;
}
.metrics-panel {
    padding: 12px;
    background: rgba(15, 23, 42, 0.98);
}
.panel-header {
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 0.08em;
    color: #60a5fa;
    margin: 10px 0 8px;
}
.divider {
    border-top: 1px solid #243041;
    margin: 14px 0;
}

.btn {
    width: 100%;
    border: 1px solid transparent;
    border-radius: 10px;
    padding: 10px 12px;
    color: white;
    font-weight: 700;
    cursor: pointer;
    margin-top: 8px;
    transition: transform 0.15s ease, filter 0.15s ease, border-color 0.15s ease;
}
.btn:hover {
    filter: brightness(1.05);
}
.btn:active {
    transform: translateY(1px);
}
.primary-btn { background: linear-gradient(180deg, #2563eb 0%, #1d4ed8 100%); }
.success-btn { background: linear-gradient(180deg, #16a34a 0%, #15803d 100%); }
.purple-btn { background: linear-gradient(180deg, #8b5cf6 0%, #7c3aed 100%); }
.danger-btn { background: linear-gradient(180deg, #ef4444 0%, #dc2626 100%); }
.text-input {
    width: 100%;
    margin-bottom: 8px;
    box-sizing: border-box;
    border: 1px solid #314158;
    border-radius: 10px;
    background: #0f172a;
    color: #e5e7eb;
    padding: 10px 12px;
}
label {
    display: block;
    font-size: 12px;
    color: #cbd5e1;
    margin: 8px 0 6px;
    font-weight: 600;
}
.file-path-label {
    font-size: 11px;
    color: #94a3b8;
    margin-top: 8px;
    word-break: break-all;
}
.sensor-group-title {
    font-size: 12px;
    color: #93c5fd;
    border-top: 1px solid #243041;
    padding-top: 10px;
    margin-top: 8px;
    font-weight: 700;
}
.metrics-header {
    display: grid;
    grid-template-columns: 1fr 88px 88px 24px;
    align-items: center;
    column-gap: 14px;
    border-bottom: 1px solid #243041;
    padding: 4px 0 10px 0;
    margin-bottom: 8px;
    position: sticky;
    top: 0;
    background: rgba(15, 23, 42, 0.98);
    z-index: 2;
}
.metrics-title {
    font-size: 11px;
    font-weight: 800;
    color: #94a3b8;
    letter-spacing: 0.05em;
}
.metrics-title.left {
    text-align: left;
}
.metrics-title.live,
.metrics-title.pinned {
    text-align: right;
}
.metrics-title.live { color: #60a5fa; }
.metrics-title.pinned { color: #f59e0b; }
.clear-pin-btn {
    border: none;
    background: transparent;
    color: #f87171;
    font-weight: 800;
    cursor: pointer;
}
.metrics-help {
    font-size: 11px;
    color: #94a3b8;
    margin-top: 10px;
}
.dash-table-container .dash-spreadsheet-container .dash-spreadsheet-inner table {
    background: transparent !important;
}
.dash-table-container .dash-cell {
    background: transparent !important;
}
"""


@dataclass
class DataBundle:
    df: pd.DataFrame
    sheets: List[str]
    file_label: str


class DataAdapter:
    @staticmethod
    def load_from_upload(contents: str, filename: str, sheet_name: Optional[str] = None) -> DataBundle:
        _, content_string = contents.split(",", 1)
        decoded = base64.b64decode(content_string)
        suffix = Path(filename).suffix.lower()

        if suffix in {".xlsx", ".xlsm", ".xls"}:
            excel = pd.ExcelFile(io.BytesIO(decoded))
            sheets = excel.sheet_names
            chosen_sheet = sheet_name or sheets[0]
            df = pd.read_excel(io.BytesIO(decoded), sheet_name=chosen_sheet)
            return DataBundle(df=DataAdapter.normalize(df), sheets=sheets, file_label=filename)

        if suffix == ".csv":
            df = pd.read_csv(io.BytesIO(decoded))
            return DataBundle(df=DataAdapter.normalize(df), sheets=["CSV"], file_label=filename)

        if suffix == ".parquet":
            df = pd.read_parquet(io.BytesIO(decoded))
            return DataBundle(df=DataAdapter.normalize(df), sheets=["Parquet"], file_label=filename)

        raise ValueError("Unsupported file type. Use Excel, CSV, or Parquet.")

    @staticmethod
    def normalize(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df.columns = [str(c).strip() for c in df.columns]

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
    def _build_profile(t: np.ndarray, knots: list[tuple[float, float]], noise: float,
                       rng: np.random.Generator) -> np.ndarray:
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
            "TS1": [(0, 42), (4, 50), (9, 58), (14, 52), (21, 47), (27, 43), (31, 50), (40, 39), (48, 34), (52, 44),
                    (58, 60), (60, 56)],
            "TS2": [(0, 55), (4, 61), (9, 68), (14, 60), (21, 56), (27, 51), (31, 60), (40, 48), (48, 42), (52, 58),
                    (58, 79), (60, 72)],
            "TS3": [(0, 72), (4, 79), (9, 85), (14, 77), (21, 71), (27, 66), (31, 74), (40, 60), (48, 53), (52, 70),
                    (58, 97), (60, 88)],
            "TS4": [(0, 89), (4, 96), (9, 104), (14, 92), (21, 84), (27, 77), (31, 90), (40, 73), (48, 64), (52, 84),
                    (58, 114), (60, 104)],
            "TS5": [(0, 108), (4, 117), (9, 125), (14, 111), (21, 101), (27, 92), (31, 108), (40, 86), (48, 77),
                    (52, 102), (58, 136), (60, 126)],
            "TS6": [(0, 142), (4, 150), (9, 158), (14, 141), (21, 129), (27, 117), (31, 143), (40, 101), (48, 92),
                    (52, 132), (58, 175), (60, 168)],
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

        return DataBundle(df=df, sheets=["Processed"], file_label="sample_data.xlsx")


def read_df(data_json: str) -> pd.DataFrame:
    return pd.read_json(io.StringIO(data_json), orient="split")


def infer_available_sensors(df: pd.DataFrame) -> Dict[str, List[str]]:
    cols = set(df.columns)
    return {
        group: [sensor for sensor in sensors if sensor in cols]
        for group, sensors in ALL_SENSOR_GROUPS.items()
        if any(sensor in cols for sensor in sensors)
    }


def filter_df(df: pd.DataFrame, start_min: Optional[float], end_min: Optional[float],
              fluid: Optional[str]) -> pd.DataFrame:
    out = df.copy()
    if fluid and "fluid" in out.columns:
        out = out[out["fluid"].astype(str) == str(fluid)]
    if start_min is not None:
        out = out[out["time_min"] >= float(start_min)]
    if end_min is not None:
        out = out[out["time_min"] <= float(end_min)]
    return out.reset_index(drop=True)


def build_figure(df: pd.DataFrame, sensor_selection: List[str]) -> go.Figure:
    row_count = len(SUBPLOT_TITLES)
    fig = make_subplots(
        rows=row_count,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.09,
        subplot_titles=SUBPLOT_TITLES,
    )
    time = df["time_min"]
    selection_set = set(sensor_selection)

    for group, sensors in infer_available_sensors(df).items():
        row = GROUP_TO_ROW[group]
        for sensor in sensors:
            if sensor not in selection_set:
                continue
            fig.add_trace(
                go.Scatter(
                    x=time,
                    y=df[sensor],
                    mode="lines",
                    name=sensor,
                    line={"color": DEFAULT_COLORS.get(sensor)},
                    showlegend=True,
                    hovertemplate=f"{sensor}<br>Time: %{{x:.2f}} min<br>Value: %{{y:.3f}}<extra></extra>",
                ),
                row=row,
                col=1,
            )

    span = max(0.0, float(df["time_min"].max() - df["time_min"].min()))
    red_x = float(df["time_min"].min() + span * 0.17)
    blue_x = float(df["time_min"].min() + span * 0.30)
    for row in range(1, row_count + 1):
        fig.add_vline(x=red_x, line_width=1, line_dash="dash", line_color="#ef4444", row=row, col=1)
        fig.add_vline(x=blue_x, line_width=1, line_dash="dot", line_color="#60a5fa", row=row, col=1)

    fig.update_layout(
        height=980,
        margin={"l": 60, "r": 20, "t": 70, "b": 50},
        plot_bgcolor="#111827",
        paper_bgcolor="#111827",
        legend={
            "orientation": "v",
            "x": 1.01,
            "y": 1.0,
            "xanchor": "left",
            "yanchor": "top",
            "bgcolor": "rgba(15, 23, 42, 0.85)",
            "bordercolor": "#334155",
            "borderwidth": 1,
            "font": {"color": "#e5e7eb"},
        },
        hovermode="x unified",
        font={"family": "Inter, Arial, sans-serif", "size": 12, "color": "#e5e7eb"},
        hoverlabel={"bgcolor": "#0f172a", "font_color": "#e5e7eb"},
    )
    fig.update_xaxes(
        title_text="Time [min]",
        showgrid=True,
        gridcolor="rgba(148,163,184,0.16)",
        zeroline=False,
        color="#cbd5e1",
    )
    fig.update_yaxes(
        showgrid=True,
        gridcolor="rgba(148,163,184,0.16)",
        zeroline=False,
        color="#cbd5e1",
    )
    fig.update_yaxes(title_text="Pressure [bara]", row=1, col=1)
    fig.update_yaxes(title_text="Temperature [K]", row=2, col=1)
    fig.update_yaxes(title_text="Mass Flow Rate [g/s]", row=3, col=1)
    fig.update_yaxes(title_text="Transferred H₂ [kg]", row=4, col=1)
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


def moving_std(y: pd.Series, window_points: int) -> pd.Series:
    return y.rolling(window=max(3, window_points), min_periods=max(3, window_points // 3)).std()


def run_oscillation_analysis(df: pd.DataFrame, selected: List[str], window_min: float) -> str:
    numeric_candidates = [s for s in selected if s in df.columns and s != "H, Transferred"]
    if df.empty or not numeric_candidates:
        return "No data available for analysis."

    t_step = max(df["time_min"].diff().median(), 1e-4)
    window_points = max(int(float(window_min or 0.25) / t_step), 3)

    stats = []
    for sensor in numeric_candidates:
        s = moving_std(df[sensor], window_points)
        peak_std = float(np.nanmax(s.to_numpy())) if len(s) else float("nan")
        stats.append((sensor, peak_std))

    stats = [x for x in stats if not np.isnan(x[1])]
    if not stats:
        return "No oscillation signal detected in selected sensors."

    stats.sort(key=lambda x: x[1], reverse=True)
    top = stats[:5]
    lines = [f"Top oscillation indicators, {window_min:.2f} min window:"]
    lines.extend([f"{name}: peak rolling std {value:.3f}" for name, value in top])
    return "\n".join(lines)


def sensor_checklist_block(group_name: str, sensors: List[str]) -> html.Div:
    return html.Div(
        [
            html.Div(group_name, className="sensor-group-title"),
            dcc.Checklist(
                id={"type": "sensor-checklist", "group": group_name},
                options=[{"label": s, "value": s} for s in sensors],
                value=sensors,
                inputStyle={"margin-right": "8px"},
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


def create_layout(sample_bundle: DataBundle) -> html.Div:
    return html.Div(
        [
            dcc.Store(id="data-store", data=sample_bundle.df.to_json(date_format="iso", orient="split")),
            dcc.Store(id="sheet-store", data=sample_bundle.sheets),
            dcc.Store(id="file-label-store", data=sample_bundle.file_label),
            dcc.Store(id="pin-index-store", data=None),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("FILE", className="panel-header"),
                            dcc.Upload(
                                id="upload-data",
                                children=html.Button("Browse Excel, CSV, or Parquet...", className="btn primary-btn"),
                                multiple=False,
                            ),
                            html.Div(id="file-path-label", className="file-path-label"),
                            html.Label("Sheet"),
                            dcc.Dropdown(
                                id="sheet-dropdown",
                                options=[{"label": s, "value": s} for s in sample_bundle.sheets],
                                value=sample_bundle.sheets[0],
                                clearable=False,
                            ),
                            html.Div(className="divider"),
                            html.Div("TIME RANGE", className="panel-header"),
                            html.Label("Start (min)"),
                            dcc.Input(id="start-min", type="number", value=0, debounce=True, className="text-input"),
                            html.Label("End (min)"),
                            dcc.Input(id="end-min", type="number", value=60, debounce=True, className="text-input"),
                            html.Label("Fluid"),
                            dcc.Dropdown(id="fluid-dropdown", options=[{"label": "All", "value": "ALL"}], value="ALL",
                                         clearable=False),
                            html.Button("Plot / Refresh", id="refresh-btn", className="btn success-btn"),
                            html.Div(className="divider"),
                            html.Div("EXPORT", className="panel-header"),
                            html.Label("Format"),
                            dcc.Dropdown(
                                id="export-format",
                                options=[{"label": "PNG", "value": "png"}, {"label": "SVG", "value": "svg"},
                                         {"label": "HTML", "value": "html"}],
                                value="png",
                                clearable=False,
                            ),
                            html.Label("DPI"),
                            dcc.Input(id="dpi-input", type="number", value=300, debounce=True, className="text-input"),
                            html.Button("Save Plot as Image", id="save-btn", className="btn purple-btn"),
                            dcc.Download(id="download-plot"),
                            html.Div(className="divider"),

                            html.Div("TOGGLE SENSORS", className="panel-header"),
                            html.Div(id="sensor-panel"),
                        ],
                        className="sidebar",
                    ),
                    html.Div(
                        [dcc.Graph(id="main-graph", config={"displaylogo": False, "scrollZoom": True},
                                   style={"height": "96vh"})],
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
                                    "padding": "8px 8px",
                                    "fontFamily": "Inter, Arial, sans-serif",
                                    "fontSize": "12px",
                                    "border": "none",
                                    "backgroundColor": "rgba(0,0,0,0)",
                                    "color": "#e5e7eb",
                                    "fontVariantNumeric": "tabular-nums",
                                },
                                style_cell_conditional=[
                                    {"if": {"column_id": "sensor"}, "textAlign": "left", "width": "120px",
                                     "minWidth": "120px", "maxWidth": "120px"},
                                    {"if": {"column_id": "live"}, "textAlign": "right", "width": "88px",
                                     "minWidth": "88px", "maxWidth": "88px"},
                                    {"if": {"column_id": "pinned"}, "textAlign": "right", "width": "88px",
                                     "minWidth": "88px", "maxWidth": "88px"},
                                ],
                                style_data_conditional=[
                                    {"if": {"column_id": "live"}, "color": "#60a5fa", "fontWeight": "700"},
                                    {"if": {"column_id": "pinned"}, "color": "#f59e0b", "fontWeight": "700"},
                                ],
                            ),
                            html.Div("Click chart to pin. Click again to move pin.", className="metrics-help"),
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
        Output("data-store", "data"),
        Output("sheet-store", "data"),
        Output("file-label-store", "data"),
        Output("sheet-dropdown", "options"),
        Output("sheet-dropdown", "value"),
        Input("upload-data", "contents"),
        State("upload-data", "filename"),
        State("sheet-dropdown", "value"),
        prevent_initial_call=True,
    )
    def load_uploaded_data(contents, filename, selected_sheet):
        if not contents or not filename:
            raise ValueError("No file uploaded.")
        bundle = DataAdapter.load_from_upload(contents, filename, selected_sheet)
        options = [{"label": s, "value": s} for s in bundle.sheets]
        return bundle.df.to_json(date_format="iso", orient="split"), bundle.sheets, bundle.file_label, options, \
        bundle.sheets[0]

    @app.callback(Output("file-path-label", "children"), Input("file-label-store", "data"))
    def update_file_label(file_label):
        return file_label or "sample_data.xlsx"

    @app.callback(
        Output("fluid-dropdown", "options"),
        Output("fluid-dropdown", "value"),
        Output("sensor-panel", "children"),
        Output("start-min", "value"),
        Output("end-min", "value"),
        Input("data-store", "data"),
    )
    def refresh_controls(data_json):
        df = read_df(data_json)
        fluids = ["ALL"]
        if "fluid" in df.columns:
            fluids += sorted([str(x) for x in df["fluid"].dropna().unique()])
        available = infer_available_sensors(df)
        sensor_blocks = [sensor_checklist_block(group_name, sensors) for group_name, sensors in available.items()]
        return (
            [{"label": x, "value": x} for x in fluids],
            "ALL",
            sensor_blocks,
            round(float(df["time_min"].min()), 3),
            round(float(df["time_min"].max()), 3),
        )

    @app.callback(
        Output("main-graph", "figure"),
        Output("metrics-table", "data"),
        Input("refresh-btn", "n_clicks"),
        Input({"type": "sensor-checklist", "group": dash.dependencies.ALL}, "value"),
        Input("main-graph", "clickData"),
        Input("clear-pin-btn", "n_clicks"),
        State("data-store", "data"),
        State("start-min", "value"),
        State("end-min", "value"),
        State("fluid-dropdown", "value"),
        State({"type": "sensor-checklist", "group": dash.dependencies.ALL}, "id"),
        State("pin-index-store", "data"),
    )
    def update_figure(_, checklist_values, click_data, clear_pin_clicks, data_json, start_min, end_min, fluid_value,
                      checklist_ids, pin_idx):
        df = read_df(data_json)
        fluid = None if fluid_value in (None, "ALL") else fluid_value
        filtered = filter_df(df, start_min, end_min, fluid)
        source_df = filtered if not filtered.empty else df

        selected: List[str] = []
        for cid, values in zip(checklist_ids, checklist_values):
            selected.extend(values or [])
        if not selected:
            for sensors in infer_available_sensors(source_df).values():
                selected.extend(sensors)

        fig = build_figure(source_df, selected)

        triggered = callback_context.triggered[0]["prop_id"] if callback_context.triggered else ""
        pin_index = pin_idx
        if triggered.startswith("main-graph.clickData") and click_data and click_data.get("points"):
            clicked_x = click_data["points"][0]["x"]
            pin_index = int((source_df["time_min"] - float(clicked_x)).abs().idxmin())
            fig.add_vline(x=float(source_df.loc[pin_index, "time_min"]), line_width=1.5, line_dash="solid",
                          line_color="#f59e0b")
        elif triggered.startswith("clear-pin-btn"):
            pin_index = None
        elif pin_index is not None and 0 <= pin_index < len(source_df):
            fig.add_vline(x=float(source_df.loc[pin_index, "time_min"]), line_width=1.5, line_dash="solid",
                          line_color="#f59e0b")

        table_data = metric_table(source_df, [s for s in selected if s in source_df.columns], pin_index)
        return fig, table_data

    @app.callback(
        Output("pin-index-store", "data"),
        Input("main-graph", "clickData"),
        Input("clear-pin-btn", "n_clicks"),
        State("data-store", "data"),
        State("start-min", "value"),
        State("end-min", "value"),
        State("fluid-dropdown", "value"),
        prevent_initial_call=True,
    )
    def manage_pin(click_data, clear_pin_clicks, data_json, start_min, end_min, fluid_value):
        triggered = callback_context.triggered[0]["prop_id"] if callback_context.triggered else ""
        if triggered.startswith("clear-pin-btn"):
            return None
        if triggered.startswith("main-graph.clickData") and click_data and click_data.get("points"):
            df = read_df(data_json)
            fluid = None if fluid_value in (None, "ALL") else fluid_value
            source_df = filter_df(df, start_min, end_min, fluid)
            source_df = source_df if not source_df.empty else df
            clicked_x = click_data["points"][0]["x"]
            return int((source_df["time_min"] - float(clicked_x)).abs().idxmin())
        return dash.no_update

    @app.callback(
        Output("download-plot", "data"),
        Input("save-btn", "n_clicks"),
        State("main-graph", "figure"),
        State("export-format", "value"),
        State("dpi-input", "value"),
        prevent_initial_call=True,
    )
    def export_plot(_, fig_dict, export_format, dpi):
        fig = go.Figure(fig_dict)
        export_format = export_format or "png"
        scale = max(int(dpi or 300) / 100, 1)

        if export_format == "html":
            return {"content": fig.to_html(include_plotlyjs="cdn"), "filename": "cryo_plot.html"}
        if export_format in {"png", "svg"}:
            return dcc.send_bytes(fig.to_image(format=export_format, scale=scale), f"cryo_plot.{export_format}")
        return dash.no_update


def create_app() -> Dash:
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
            <style>{INLINE_CSS}
.Select-control, .Select-menu-outer {{
    background: #0f172a !important;
    border-color: #314158 !important;
    color: #e5e7eb !important;
}}
.Select--single > .Select-control .Select-value, .Select-placeholder {{
    color: #e5e7eb !important;
}}
.VirtualizedSelectOption {{
    background: #0f172a !important;
    color: #e5e7eb !important;
}}
.VirtualizedSelectFocusedOption {{
    background: #1e293b !important;
    color: #ffffff !important;
}}
input[type="checkbox"] {{
    accent-color: #60a5fa;
}}
</style>
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
    sample_bundle = DataAdapter.sample_data()
    app.layout = create_layout(sample_bundle)
    register_callbacks(app)
    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
