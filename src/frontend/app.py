from __future__ import annotations

import json
from typing import List

import dash
import pandas as pd
from dash import ALL, Dash, Input, Output, Patch, State, callback_context, dcc

from config import ALL_SENSOR_GROUPS, APP_TITLE, AUTOSCALE_MAX_ROWS, INLINE_CSS, WINDOW_UNIT_TO_MINUTES
from data import (
    append_new_stream_rows,
    df_to_json,
    ensure_stream_source_exists,
    export_data_bytes,
    infer_available_sensors,
    load_stream_source,
    read_df,
    save_notes,
)
from ui import build_figure, create_layout, metric_table, render_notes_log, sensor_checklist_block


def _safe_window_minutes(window_value, window_unit) -> float:
    unit_scale = WINDOW_UNIT_TO_MINUTES.get(window_unit or "min", 1.0)
    safe_window_value = float(window_value) if window_value not in (None, "") else 5.0
    return max(0.01, safe_window_value * unit_scale)


def _selected_sensors(source_df: pd.DataFrame, checklist_values, checklist_ids, active_groups) -> List[str]:
    selected: List[str] = []
    for _, values in zip(checklist_ids or [], checklist_values or []):
        selected.extend(values or [])

    if not selected:
        for sensors in infer_available_sensors(source_df).values():
            selected.extend(sensors)

    filtered_selected: List[str] = []
    for group, sensors in ALL_SENSOR_GROUPS.items():
        if group in active_groups:
            filtered_selected.extend([s for s in sensors if s in selected and s in source_df.columns])
    return filtered_selected


def _graph_signature(source_df: pd.DataFrame, filtered_selected: List[str], active_groups, window_minutes: float, pin_idx) -> str:
    available = infer_available_sensors(source_df)
    visible_groups = [group for group in ALL_SENSOR_GROUPS.keys() if group in set(active_groups or []) and group in available]
    payload = {
        "has_data": not source_df.empty,
        "groups": visible_groups,
        "sensors": filtered_selected,
        "window_minutes": round(window_minutes, 6),
        "pin_idx": int(pin_idx) if pin_idx is not None else None,
    }
    return json.dumps(payload, sort_keys=True)


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

        updated_df = append_new_stream_rows(
            cached_df,
            source_df,
            last_seen_time,
            max_rows=AUTOSCALE_MAX_ROWS,
        )

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
        Output("zoom-state-store", "data"),
        Input("main-graph", "relayoutData"),
        Input("window-value", "value"),
        Input("window-unit", "value"),
        State("zoom-state-store", "data"),
        prevent_initial_call=True,
    )
    def track_zoom_state(relayout_data, window_value, window_unit, zoom_state):
        triggered = callback_context.triggered[0]["prop_id"] if callback_context.triggered else ""

        if triggered.startswith("window-value") or triggered.startswith("window-unit"):
            return {"locked": False, "xrange": None}

        if not relayout_data:
            return dash.no_update

        if relayout_data.get("xaxis.autorange"):
            return {"locked": False, "xrange": None}

        x0 = relayout_data.get("xaxis.range[0]")
        x1 = relayout_data.get("xaxis.range[1]")

        if x0 is not None and x1 is not None:
            return {"locked": True, "xrange": [float(x0), float(x1)]}

        return dash.no_update

    @app.callback(
        Output("main-graph", "figure"),
        Output("main-graph", "extendData"),
        Output("metrics-table", "data"),
        Output("graph-state-store", "data"),
        Input("data-store", "data"),
        Input("pin-index-store", "data"),
        Input({"type": "sensor-checklist", "group": ALL}, "value"),
        Input("window-value", "value"),
        Input("window-unit", "value"),
        Input("graph-toggle", "value"),
        Input("zoom-state-store", "data"),
        State({"type": "sensor-checklist", "group": ALL}, "id"),
        State("graph-state-store", "data"),
    )
    def update_graph_and_metrics(
        data_json,
        pin_idx,
        checklist_values,
        window_value,
        window_unit,
        graph_toggle_value,
        zoom_state,
        checklist_ids,
        graph_state,
    ):
        source_df = read_df(data_json)
        active_groups = set(graph_toggle_value or [])
        filtered_selected = _selected_sensors(source_df, checklist_values, checklist_ids, active_groups)
        table_data = metric_table(source_df, filtered_selected, pin_idx)
        window_minutes = _safe_window_minutes(window_value, window_unit)
        signature = _graph_signature(source_df, filtered_selected, active_groups, window_minutes, pin_idx)

        state = graph_state or {}
        state_signature = state.get("signature")
        state_last_time = state.get("last_time")
        initialized = bool(state.get("initialized"))

        triggered_props = {item["prop_id"] for item in callback_context.triggered} if callback_context.triggered else set()
        window_changed = any(
            prop.startswith("window-value") or prop.startswith("window-unit")
            for prop in triggered_props
        )

        zoom_locked = bool((zoom_state or {}).get("locked"))
        locked_range = (zoom_state or {}).get("xrange")

        if window_changed:
            zoom_locked = False
            locked_range = None

        active_x_range = locked_range if zoom_locked and locked_range else None

        if source_df.empty:
            fig = build_figure(
                source_df,
                filtered_selected,
                window_minutes=window_minutes,
                active_groups=active_groups,
                pin_time=None,
                x_range=active_x_range,
            )
            new_state = {"initialized": True, "signature": signature, "last_time": None}
            return fig, dash.no_update, table_data, new_state

        current_last_time = float(source_df.iloc[-1]["time_min"])
        pin_time = None
        if pin_idx is not None and 0 <= int(pin_idx) < len(source_df):
            pin_time = float(source_df.iloc[int(pin_idx)]["time_min"])

        data_only_trigger = triggered_props and all(prop.startswith("data-store") for prop in triggered_props)

        needs_full_redraw = (
            not initialized
            or state_signature != signature
            or state_last_time is None
            or not data_only_trigger
        )

        if needs_full_redraw:
            fig = build_figure(
                source_df,
                filtered_selected,
                window_minutes=window_minutes,
                active_groups=active_groups,
                pin_time=pin_time,
                x_range=active_x_range,
            )
            new_state = {"initialized": True, "signature": signature, "last_time": current_last_time}
            return fig, dash.no_update, table_data, new_state

        fresh = source_df[source_df["time_min"] > float(state_last_time)].copy()
        if fresh.empty:
            return dash.no_update, dash.no_update, table_data, dash.no_update

        trace_indices = list(range(len(filtered_selected)))
        if not trace_indices:
            new_state = {"initialized": True, "signature": signature, "last_time": current_last_time}
            return dash.no_update, dash.no_update, table_data, new_state

        x_updates = [fresh["time_min"].tolist() for _ in filtered_selected]
        y_updates = [fresh[sensor].tolist() if sensor in fresh.columns else [] for sensor in filtered_selected]

        window_start = max(float(source_df["time_min"].min()), current_last_time - window_minutes)

        if zoom_locked and locked_range:
            x_range = [float(locked_range[0]), float(locked_range[1])]
            left_edge = min(x_range)
            right_edge = max(x_range)
            visible_points = int(((source_df["time_min"] >= left_edge) & (source_df["time_min"] <= right_edge)).sum())
        else:
            x_range = [window_start, current_last_time]
            visible_points = int((source_df["time_min"] >= window_start).sum())

        max_points = max(visible_points, len(fresh), 1)

        extend_payload = ({"x": x_updates, "y": y_updates}, trace_indices, max_points)

        figure_patch = Patch()
        available = infer_available_sensors(source_df)
        visible_groups = [group for group in ALL_SENSOR_GROUPS.keys() if group in active_groups and group in available]
        for idx in range(len(visible_groups)):
            axis_name = "xaxis" if idx == 0 else f"xaxis{idx + 1}"
            figure_patch["layout"][axis_name]["range"] = x_range
            figure_patch["layout"][axis_name]["autorange"] = False

        new_state = {"initialized": True, "signature": signature, "last_time": current_last_time}
        return figure_patch, extend_payload, table_data, new_state

    @app.callback(
        Output("download-data", "data"),
        Output("save-status", "children"),
        Input("save-data-btn", "n_clicks"),
        State("save-format", "value"),
        State("save-scope", "value"),
        State("data-store", "data"),
        State("window-value", "value"),
        State("window-unit", "value"),
        prevent_initial_call=True,
    )
    def save_data(n_clicks, save_format, save_scope, data_json, window_value, window_unit):
        df = read_df(data_json)
        if df.empty:
            return dash.no_update, "No streamed data to save yet."

        use_visible_only = "visible" in (save_scope or [])
        export_df = df.copy()
        if use_visible_only and not export_df.empty:
            window_minutes = _safe_window_minutes(window_value, window_unit)
            window_end = float(export_df.iloc[-1]["time_min"])
            window_start = max(float(export_df["time_min"].min()), window_end - window_minutes)
            export_df = export_df[export_df["time_min"] >= window_start].copy()

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