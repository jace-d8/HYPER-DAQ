from __future__ import annotations

from typing import List

import dash
import pandas as pd
from dash import ALL, Dash, Input, Output, State, callback_context, dcc

from config import ALL_SENSOR_GROUPS, APP_TITLE, AUTOSCALE_MAX_ROWS, INLINE_CSS
from data import (
    append_new_stream_rows,
    df_to_json,
    ensure_stream_source_exists,
    export_data_bytes,
    infer_available_sensors,
    load_notes,
    load_stream_source,
    read_df,
    save_notes,
)
from ui import build_figure, create_layout, metric_table, render_notes_log, sensor_checklist_block


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