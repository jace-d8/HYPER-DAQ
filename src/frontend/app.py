from __future__ import annotations

import json
from typing import List

import dash
import pandas as pd
from dash import ALL, Dash, Input, Output, Patch, State, callback_context, dcc, html

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
from ui import build_figure, build_single_group_figure, create_layout, custom_sensor_options_by_group, metric_table, render_notes_log, sensor_checklist_block
import requests

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


def _graph_signature(source_df: pd.DataFrame, filtered_selected: List[str], active_groups, window_minutes: float, pin_idx, dark_mode: bool, custom_graphs=None) -> str:
    available = infer_available_sensors(source_df)
    visible_groups = [group for group in ALL_SENSOR_GROUPS.keys() if group in set(active_groups or []) and group in available]
    payload = {
        "has_data": not source_df.empty,
        "groups": visible_groups,
        "sensors": filtered_selected,
        "window_minutes": round(window_minutes, 6),
        "pin_idx": int(pin_idx) if pin_idx is not None else None,
        "dark_mode": bool(dark_mode),
        "custom_graphs": custom_graphs or [],
    }
    return json.dumps(payload, sort_keys=True)


def _append_system_note(notes_data, text: str):
    notes = list(notes_data or [])
    timestamp = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    notes.append({"timestamp": timestamp, "text": text})
    save_notes(notes)
    return notes


def _available_group_options(source_df: pd.DataFrame) -> List[dict]:
    available = infer_available_sensors(source_df)
    return [{'label': group, 'value': group} for group in available.keys()]


def _valid_sensors_for_group(source_df: pd.DataFrame, group_name: str) -> List[str]:
    available = infer_available_sensors(source_df)
    return list(available.get(group_name, []))


def _custom_graph_title(group_name: str, sensors: List[str]) -> str:
    return f"{group_name}: {', '.join(sensors)}"


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

        notes = _append_system_note(notes_data, text)
        return notes, ""

    @app.callback(
        Output("notes-log", "children"),
        Input("notes-store", "data"),
    )
    def update_notes_log(notes_data):
        return render_notes_log(notes_data or [])
    @app.callback(
        Output("logging-state-store", "data"),
        Output("notes-store", "data", allow_duplicate=True),
        Input("logging-toggle-btn", "n_clicks"),
        State("logging-state-store", "data"),
        State("notes-store", "data"),
        prevent_initial_call=True,
    )
    def toggle_logging(n_clicks, logging_state, notes_data):
        current_enabled = bool((logging_state or {}).get("enabled"))
        next_enabled = not current_enabled

        next_state = {"enabled": next_enabled, "flash": next_enabled}

        try:
            requests.post(
                "http://127.0.0.1:8000/logging",
                json={"enabled": next_enabled},
                timeout=0.25,
            )
            note_text = "Logging started from dashboard toggle." if next_enabled else "Logging stopped from dashboard toggle."
        except requests.RequestException:
            note_text = (
                "Logging button changed locally, but backend is not running."
            )

        notes = _append_system_note(notes_data, note_text)
        return next_state, notes

    @app.callback(
        Output("app-root", "className"),
        Output("logging-banner", "children"),
        Output("logging-banner", "className"),
        Output("logging-toggle-btn", "children"),
        Output("logging-toggle-btn", "className"),
        Output("logging-mode-text", "children"),
        Input("logging-state-store", "data"),
    )
    def sync_logging_ui(logging_state):
        enabled = bool((logging_state or {}).get("enabled"))
        flash = bool((logging_state or {}).get("flash"))
        root_class = "dark-mode" if enabled else "light-mode"
        if enabled and flash:
            root_class += " flash-start"

        if enabled:
            return (
                root_class,
                "LOGGING ACTIVE, VISUALS SHIFTED TO RECORDING MODE",
                "app-banner banner-on",
                "Logging ON",
                "logging-toggle-btn toggle-on",
                "Logging is enabled. Dark mode marks active recording state.",
            )

        return (
            root_class,
            "TEST MODE, LOGGING OFF",
            "app-banner banner-off",
            "Logging OFF",
            "logging-toggle-btn toggle-off",
            "Logging is disabled. Flip the toggle before a real run.",
        )

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
        Output("custom-graph-group", "options"),
        Output("custom-graph-group", "value"),
        Input("data-store", "data"),
        State("custom-graph-group", "value"),
    )
    def refresh_custom_graph_groups(data_json, current_group):
        df = read_df(data_json)
        options = _available_group_options(df)
        valid_values = {option["value"] for option in options}
        if current_group in valid_values:
            return options, current_group
        next_value = options[0]["value"] if options else None
        return options, next_value

    @app.callback(
        Output("custom-graph-sensors", "options"),
        Output("custom-graph-sensors", "value"),
        Input("custom-graph-group", "value"),
        Input("data-store", "data"),
        State("custom-graph-sensors", "value"),
    )
    def refresh_custom_graph_sensor_options(group_name, data_json, current_sensors):
        df = read_df(data_json)
        sensors = _valid_sensors_for_group(df, group_name)
        options = [{'label': sensor, 'value': sensor} for sensor in sensors]
        selected = [sensor for sensor in (current_sensors or []) if sensor in sensors]
        return options, selected

    @app.callback(
        Output("custom-graphs-store", "data"),
        Input("add-custom-graph-btn", "n_clicks"),
        Input({"type": "remove-custom-graph", "index": ALL}, "n_clicks"),
        State("custom-graph-group", "value"),
        State("custom-graph-sensors", "value"),
        State("custom-graphs-store", "data"),
        State("data-store", "data"),
        prevent_initial_call=True,
    )
    def manage_custom_graphs(add_clicks, remove_clicks, group_name, selected_sensors, custom_graphs, data_json):
        triggered = callback_context.triggered[0]["prop_id"] if callback_context.triggered else ""
        graphs = list(custom_graphs or [])

        if triggered.startswith("add-custom-graph-btn"):
            df = read_df(data_json)
            valid_sensors = set(_valid_sensors_for_group(df, group_name))
            sensors = [sensor for sensor in (selected_sensors or []) if sensor in valid_sensors]
            if not group_name or not sensors:
                return dash.no_update
            next_id = max([int(graph.get("id", 0)) for graph in graphs] or [0]) + 1
            graphs.append({"id": next_id, "group": group_name, "sensors": sensors})
            return graphs

        if triggered.startswith("{"):
            triggered_id = json.loads(triggered.split(".")[0])
            if triggered_id.get("type") == "remove-custom-graph":
                remove_id = int(triggered_id.get("index"))
                # Dash fires this input once when a new remove button is inserted.
                # Only remove the graph after the user actually clicks the button.
                click_count = 0
                for graph, clicks in zip(graphs, remove_clicks or []):
                    if int(graph.get("id", -1)) == remove_id:
                        click_count = int(clicks or 0)
                        break
                if click_count <= 0:
                    return dash.no_update
                return [graph for graph in graphs if int(graph.get("id", -1)) != remove_id]

        return dash.no_update

    @app.callback(
        Output("custom-graphs-container", "children"),
        Input("custom-graphs-store", "data"),
        Input("data-store", "data"),
        Input("pin-index-store", "data"),
        Input("window-value", "value"),
        Input("window-unit", "value"),
        Input("zoom-state-store", "data"),
        Input("logging-state-store", "data"),
    )
    def render_custom_graphs(custom_graphs, data_json, pin_idx, window_value, window_unit, zoom_state, logging_state):
        df = read_df(data_json)
        window_minutes = _safe_window_minutes(window_value, window_unit)
        dark_mode = bool((logging_state or {}).get("enabled"))
        locked_range = (zoom_state or {}).get("xrange")
        x_range = locked_range if bool((zoom_state or {}).get("locked")) and locked_range else None

        pin_time = None
        if pin_idx is not None and not df.empty and 0 <= int(pin_idx) < len(df):
            pin_time = float(df.iloc[int(pin_idx)]["time_min"])

        cards = []
        for graph in custom_graphs or []:
            graph_id = int(graph.get("id", 0))
            group_name = graph.get("group")
            sensors = list(graph.get("sensors", []))
            title = _custom_graph_title(group_name, sensors)
            fig = build_single_group_figure(
                df,
                group_name,
                sensors,
                window_minutes=window_minutes,
                pin_time=pin_time,
                x_range=x_range,
                dark_mode=dark_mode,
                title=title,
            )
            cards.append(
                html.Div(
                    [
                        html.Button(
                            "×",
                            id={"type": "remove-custom-graph", "index": graph_id},
                            n_clicks=0,
                            title="Remove graph",
                            className="custom-remove-btn",
                        ),
                        dcc.Graph(
                            id={"type": "custom-graph", "index": graph_id},
                            figure=fig,
                            config={"displaylogo": False, "scrollZoom": True},
                        ),
                    ],
                    className="custom-graph-card",
                )
            )
        return cards

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
        Input("logging-state-store", "data"),
        Input("custom-graphs-store", "data"),
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
        logging_state,
        custom_graphs,
        checklist_ids,
        graph_state,
    ):
        source_df = read_df(data_json)
        active_groups = set(graph_toggle_value or [])
        filtered_selected = _selected_sensors(source_df, checklist_values, checklist_ids, active_groups)
        table_data = metric_table(source_df, filtered_selected, pin_idx)
        window_minutes = _safe_window_minutes(window_value, window_unit)
        dark_mode = bool((logging_state or {}).get("enabled"))
        # Custom graphs render below the main graph, so they should not add extra subplot rows here.
        signature = _graph_signature(source_df, filtered_selected, active_groups, window_minutes, pin_idx, dark_mode, [])

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
                dark_mode=dark_mode,
                custom_graphs=[],
            )
            new_state = {"initialized": True, "signature": signature, "last_time": None}
            return fig, dash.no_update, table_data, new_state

        current_last_time = float(source_df.iloc[-1]["time_min"])
        pin_time = None
        if pin_idx is not None and 0 <= int(pin_idx) < len(source_df):
            pin_time = float(source_df.iloc[int(pin_idx)]["time_min"])

        data_only_trigger = triggered_props and all(prop.startswith("data-store") for prop in triggered_props) and not custom_graphs

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
                dark_mode=dark_mode,
                custom_graphs=[],
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
