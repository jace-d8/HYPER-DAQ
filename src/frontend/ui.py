from __future__ import annotations

from typing import List, Optional, Set

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import dash_table, dcc, html
from plotly.subplots import make_subplots

from config import (
    ALL_SENSOR_GROUPS,
    DEFAULT_COLORS,
    DEFAULT_SLIDING_WINDOW_MIN,
    FLOW_SENSORS,
    GROUP_LABELS,
    POLL_INTERVAL_MS,
    PRESSURE_SENSORS,
    SLIDING_WINDOW_ROWS,
    STREAM_SOURCE_FILE,
    TEMPERATURE_SENSORS,
    TRANSFER_SENSORS,
)
from data import df_to_json, empty_frame, infer_available_sensors, load_notes


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

    if use_sliding_window:
        visible = df.tail(SLIDING_WINDOW_ROWS).copy()

        if len(visible) >= 2:
            window_start = float(visible.iloc[0]["time_min"])
            window_end = float(visible.iloc[-1]["time_min"])
        else:
            window_end = current_time
            window_start = max(x_min, window_end - sliding_window_min)

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
                persistence=True,
                persistence_type="local",
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


def create_layout() -> html.Div:
    return html.Div(
        [
            dcc.Store(id="data-store", data=df_to_json(empty_frame())),
            dcc.Store(id="pin-index-store", data=None, storage_type="local"),
            dcc.Store(id="last-seen-time-store", data=None),
            dcc.Store(id="notes-store", data=load_notes(), storage_type="local"),
            dcc.Interval(id="stream-interval", interval=POLL_INTERVAL_MS, n_intervals=0, disabled=False),
            dcc.Download(id="download-data"),
            html.Div(
                [
                    html.Div(
                        [
                            dcc.Dropdown(
                                id="save-format",
                                options=[
                                    {"label": "CSV", "value": "csv"},
                                    {"label": "JSON", "value": "json"},
                                    {"label": "XLSX", "value": "xlsx"},
                                ],
                                value="csv",
                                clearable=False,
                                persistence=True,
                                persistence_type="local",
                            ),
                            dcc.Checklist(
                                id="save-scope",
                                options=[{"label": "Save visible data only", "value": "visible"}],
                                value=["visible"],
                                inputStyle={"margin-right": "8px"},
                                labelStyle={"display": "block", "fontSize": "13px", "margin": "8px 0 4px 0"},
                                persistence=True,
                                persistence_type="local",
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
                                persistence=True,
                                persistence_type="local",
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
                                persistence=True,
                                persistence_type="local",
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