from __future__ import annotations

import json
import queue
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import dearpygui.dearpygui as dpg

sys.path.insert(0, str(Path(__file__).parent))

from config import (
    ALL_SENSOR_GROUPS,
    BUFFER_MAX_ROWS,
    DEFAULT_COLORS,
    DEFAULT_WINDOW_UNIT,
    DEFAULT_WINDOW_VALUE,
    GROUP_LABELS,
    LOGGING_STATE_FILE,
    POLL_INTERVAL_MS,
    SAMPLE_HZ,
    STREAM_SOURCE_FILE,
    WINDOW_UNIT_TO_MINUTES,
    max_lookback_minutes,
)
from data import (
    DataAdapter,
    append_new_stream_rows,
    empty_frame,
    export_data_bytes,
    infer_available_sensors,
    load_notes,
    load_settings,
    save_notes,
    save_settings,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hex_to_rgba(h: str, a: int = 255) -> Tuple[int, int, int, int]:
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a)


DPG_COLORS: Dict[str, Tuple[int, int, int, int]] = {
    k: _hex_to_rgba(v) for k, v in DEFAULT_COLORS.items()
}

_FALLBACK_COLORS = [
    (239, 83, 80, 255), (66, 165, 245, 255), (102, 187, 106, 255),
    (255, 167, 38, 255), (171, 71, 188, 255), (38, 166, 154, 255),
]


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

class HyperDaqApp:
    _SIDEBAR_W = 280
    _METRICS_W = 260
    _BANNER_H = 30
    _POLL_S = POLL_INTERVAL_MS / 1000.0

    def __init__(self):
        self._lock = threading.Lock()
        self._df = empty_frame()
        self._last_seen: Optional[float] = None
        self._update_q: queue.Queue = queue.Queue()

        self._logging_enabled = False
        self._pinned_time: Optional[float] = None
        self._notes = load_notes()

        _s = load_settings()
        self._save_format = _s.get("save_format", "csv").lower()
        _win_val = float(_s.get("window_value", DEFAULT_WINDOW_VALUE))
        _win_unit = _s.get("window_unit", "Minutes")
        _win_key = "hr" if _win_unit == "Hours" else "min"
        self._window_minutes = _win_val * WINDOW_UNIT_TO_MINUTES[_win_key]
        self._group_visible: Dict[str, bool] = {
            g: _s.get("group_visible", {}).get(g, True) for g in ALL_SENSOR_GROUPS
        }
        self._startup_settings = _s

        self._custom_graphs: List[dict] = []
        self._custom_counter = 0
        self._custom_xaxis: Dict[int, str] = {}
        self._custom_yaxis: Dict[int, str] = {}
        self._custom_series: Dict[int, Dict[str, str]] = {}

        self._series_tags: Dict[str, Dict[str, str]] = {g: {} for g in ALL_SENSOR_GROUPS}
        self._xaxis_tags: Dict[str, str] = {}
        self._yaxis_tags: Dict[str, str] = {}
        self._series_shown: set = set()
        self._metrics_created: set = set()

        self._theme_cache: Dict[str, int] = {}

    # ------------------------------------------------------------------
    # Themes
    # ------------------------------------------------------------------

    def _make_themes(self):
        with dpg.theme(tag="t_global"):
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_color(dpg.mvThemeCol_WindowBg,       (15,  23,  42,  255))
                dpg.add_theme_color(dpg.mvThemeCol_ChildBg,         (15,  23,  42,  255))
                dpg.add_theme_color(dpg.mvThemeCol_PopupBg,         (20,  30,  55,  255))
                dpg.add_theme_color(dpg.mvThemeCol_Text,            (229, 231, 235, 255))
                dpg.add_theme_color(dpg.mvThemeCol_FrameBg,         (30,  41,  59,  255))
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered,  (51,  65,  85,  255))
                dpg.add_theme_color(dpg.mvThemeCol_Button,          (59,  130, 246, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered,   (37,  99,  235, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,    (29,  78,  216, 255))
                dpg.add_theme_color(dpg.mvThemeCol_Separator,       (51,  65,  85,  255))
                dpg.add_theme_color(dpg.mvThemeCol_ScrollbarBg,     (15,  23,  42,  255))
                dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrab,   (51,  65,  85,  255))
                dpg.add_theme_color(dpg.mvThemeCol_Header,          (51,  65,  85,  255))
                dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered,   (71,  85,  105, 255))
                dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing,     6, 4)
                dpg.add_theme_style(dpg.mvStyleVar_FramePadding,    6, 4)
                dpg.add_theme_style(dpg.mvStyleVar_WindowPadding,   8, 8)
                dpg.add_theme_style(dpg.mvStyleVar_ChildRounding,   4)
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding,   4)
        dpg.bind_theme("t_global")

        with dpg.theme(tag="t_btn_off"):
            with dpg.theme_component(dpg.mvButton):
                dpg.add_theme_color(dpg.mvThemeCol_Button,         (220, 38,  38,  255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered,   (185, 28,  28,  255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,    (153, 27,  27,  255))

        with dpg.theme(tag="t_btn_on"):
            with dpg.theme_component(dpg.mvButton):
                dpg.add_theme_color(dpg.mvThemeCol_Button,         (22,  163, 74,  255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered,   (21,  128, 61,  255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,    (20,  83,  45,  255))

        with dpg.theme(tag="t_banner_off"):
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_color(dpg.mvThemeCol_ChildBg,        (185, 28,  28,  255))

        with dpg.theme(tag="t_banner_on"):
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_color(dpg.mvThemeCol_ChildBg,        (21,  128, 61,  255))

    def _sensor_theme(self, sensor: str, fallback_idx: int = 0) -> int:
        if sensor in self._theme_cache:
            return self._theme_cache[sensor]
        color = list(DPG_COLORS.get(sensor, _FALLBACK_COLORS[fallback_idx % len(_FALLBACK_COLORS)]))
        with dpg.theme() as t:
            with dpg.theme_component(dpg.mvLineSeries):
                dpg.add_theme_color(dpg.mvPlotCol_Line, color, category=dpg.mvThemeCat_Plots)
        self._theme_cache[sensor] = t
        return t

    def _pin_theme(self) -> int:
        if "__pin__" in self._theme_cache:
            return self._theme_cache["__pin__"]
        with dpg.theme() as t:
            with dpg.theme_component(dpg.mvInfLineSeries):
                dpg.add_theme_color(dpg.mvPlotCol_Line, (245, 158, 11, 255),
                                    category=dpg.mvThemeCat_Plots)
        self._theme_cache["__pin__"] = t
        return t

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build(self):
        vw = dpg.get_viewport_width()
        vh = dpg.get_viewport_height()
        main_w = vw - self._SIDEBAR_W - self._METRICS_W - 30
        body_h = vh - self._BANNER_H - 8

        with dpg.window(tag="primary", no_title_bar=True, no_resize=True,
                        no_move=True, no_scrollbar=True, width=vw, height=vh):

            with dpg.child_window(tag="banner", width=-1, height=self._BANNER_H,
                                  no_scrollbar=True, border=False):
                dpg.bind_item_theme("banner", "t_banner_off")
                dpg.add_text("TEST MODE, LOGGING OFF", tag="banner_text", indent=10)

            with dpg.group(horizontal=True):
                self._build_sidebar(body_h)
                self._build_main(main_w, body_h)
                self._build_metrics(body_h)

        with dpg.handler_registry():
            dpg.add_mouse_click_handler(button=0, callback=self._on_left_click)

    def _build_sidebar(self, h: int):
        with dpg.child_window(tag="sidebar", width=self._SIDEBAR_W, height=h, border=True):

            # Save
            dpg.add_text("SAVE", color=(59, 130, 246, 255))
            dpg.add_separator()
            with dpg.group(horizontal=True):
                dpg.add_text("Format:", color=(107, 114, 128, 255))
                dpg.add_radio_button(
                    ("CSV", "JSON", "XLSX"), tag="save_format", horizontal=True,
                    callback=lambda s, a: (setattr(self, "_save_format", a.lower()), self._save_settings()),
                )
            dpg.add_checkbox(label="Visible window only", tag="save_scope", default_value=True,
                             callback=lambda s, a: self._save_settings())
            dpg.add_button(label="Save As", width=-1, callback=self._on_save)
            dpg.add_text("", tag="save_status", color=(107, 114, 128, 255),
                         wrap=self._SIDEBAR_W - 20)
            dpg.add_separator()

            # Stream
            dpg.add_text("STREAM", color=(59, 130, 246, 255))
            dpg.add_separator()
            dpg.add_text(f"Source: {STREAM_SOURCE_FILE.name}", color=(107, 114, 128, 255),
                         wrap=self._SIDEBAR_W - 20)
            dpg.add_text("Window size", color=(107, 114, 128, 255))
            with dpg.group(horizontal=True):
                dpg.add_input_float(
                    tag="win_val", default_value=DEFAULT_WINDOW_VALUE,
                    min_value=0.5, step=0.5, width=130,
                    callback=self._on_window_changed,
                )
                dpg.add_combo(
                    ("Minutes", "Hours"), tag="win_unit", default_value="Minutes",
                    width=110, callback=self._on_window_changed,
                )
            max_lb = max_lookback_minutes(SAMPLE_HZ)
            dpg.add_text(
                f"Max: {max_lb:.1f} min ({max_lb / 60:.2f} hr) at {SAMPLE_HZ} Hz",
                color=(107, 114, 128, 255), wrap=self._SIDEBAR_W - 20,
            )
            dpg.add_button(label="Reset Zoom", width=-1, callback=self._reset_zoom)
            dpg.add_separator()

            # Graph toggles
            dpg.add_text("TOGGLE GRAPHS", color=(59, 130, 246, 255))
            dpg.add_separator()
            for group in ALL_SENSOR_GROUPS:
                dpg.add_checkbox(
                    label=group, tag=f"gtoggle_{group}", default_value=True,
                    callback=lambda s, a, u: self._on_group_toggle(u, a),
                    user_data=group,
                )
            dpg.add_separator()

            # Add custom graph
            dpg.add_text("ADD GRAPH", color=(59, 130, 246, 255))
            dpg.add_separator()
            dpg.add_text("Unit group", color=(107, 114, 128, 255))
            dpg.add_combo(
                list(ALL_SENSOR_GROUPS.keys()), tag="cg_group",
                default_value=list(ALL_SENSOR_GROUPS.keys())[0],
                width=-1, callback=self._refresh_cg_sensor_list,
            )
            dpg.add_text("Sensors", color=(107, 114, 128, 255))
            with dpg.group(tag="cg_sensors"):
                pass
            dpg.add_button(label="Add Graph", width=-1, callback=self._add_custom_graph)

    def _build_main(self, w: int, h: int):
        n = len(ALL_SENSOR_GROUPS)
        plot_h = max(160, (h - 70) // n)

        with dpg.child_window(tag="main_panel", width=w, height=h, border=True):
            with dpg.group(horizontal=True, tag="toolbar"):
                with dpg.group():
                    dpg.add_text("Run Control")
                    dpg.add_text("Toggle logging before a real run.",
                                 color=(107, 114, 128, 255))
                dpg.add_spacer(width=12)
                dpg.add_button(
                    label="Logging OFF", tag="log_btn", width=160, height=36,
                    callback=self._on_log_toggle,
                )
                dpg.bind_item_theme("log_btn", "t_btn_off")
            dpg.add_separator()

            for group in ALL_SENSOR_GROUPS:
                xt, yt = f"xax_{group}", f"yax_{group}"
                self._xaxis_tags[group] = xt
                self._yaxis_tags[group] = yt

                with dpg.plot(tag=f"plot_{group}", height=plot_h, width=-1,
                              label=GROUP_LABELS.get(group, group), anti_aliased=True):
                    dpg.add_plot_legend(outside=False)
                    dpg.add_plot_axis(dpg.mvXAxis, tag=xt, label="Time [min]")
                    dpg.add_plot_axis(dpg.mvYAxis, tag=yt,
                                      label=GROUP_LABELS.get(group, group))

                    for i, sensor in enumerate(ALL_SENSOR_GROUPS.get(group, [])):
                        st = f"ser_{group}_{sensor}"
                        dpg.add_line_series([], [], label=sensor, tag=st, parent=yt)
                        dpg.bind_item_theme(st, self._sensor_theme(sensor, i))
                        dpg.configure_item(st, show=False)
                        self._series_tags[group][sensor] = st

            dpg.add_group(tag="custom_container")

    def _build_metrics(self, h: int):
        with dpg.child_window(tag="metrics_panel", width=self._METRICS_W, height=h, border=True):
            with dpg.group(horizontal=True):
                dpg.add_text("SENSOR",  color=(107, 114, 128, 255))
                dpg.add_spacer(width=16)
                dpg.add_text("LIVE",    color=(37,  99,  235, 255))
                dpg.add_spacer(width=10)
                dpg.add_text("PINNED",  color=(217, 119,   6, 255))
                dpg.add_button(label="X", small=True, callback=self._clear_pin)
            dpg.add_separator()
            with dpg.group(tag="metrics_rows"):
                pass
            dpg.add_text("Click chart to pin a time.",
                         color=(107, 114, 128, 255), wrap=self._METRICS_W - 16)
            dpg.add_separator()
            dpg.add_text("NOTES / LOG", color=(59, 130, 246, 255))
            dpg.add_separator()
            dpg.add_input_text(tag="note_input", multiline=True, width=-1, height=80,
                               hint="Add a note...")
            dpg.add_button(label="Add Note", width=-1, callback=self._add_note)
            dpg.add_separator()
            with dpg.child_window(tag="notes_panel", width=-1, height=-1, border=False):
                pass
            self._render_notes()

    # ------------------------------------------------------------------
    # Callbacks  (all fire on main thread via DPG)
    # ------------------------------------------------------------------

    def _on_log_toggle(self):
        self._logging_enabled = not self._logging_enabled
        if self._logging_enabled:
            dpg.set_value("banner_text", "LOGGING ACTIVE — RECORDING MODE")
            dpg.configure_item("log_btn", label="Logging ON")
            dpg.bind_item_theme("log_btn", "t_btn_on")
            dpg.bind_item_theme("banner", "t_banner_on")
        else:
            dpg.set_value("banner_text", "TEST MODE, LOGGING OFF")
            dpg.configure_item("log_btn", label="Logging OFF")
            dpg.bind_item_theme("log_btn", "t_btn_off")
            dpg.bind_item_theme("banner", "t_banner_off")
        try:
            LOGGING_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(LOGGING_STATE_FILE, "w") as f:
                json.dump({"enabled": self._logging_enabled}, f)
        except Exception:
            pass

    def _on_window_changed(self):
        val = max(0.5, float(dpg.get_value("win_val") or 0))
        dpg.set_value("win_val", val)
        unit = dpg.get_value("win_unit") or "Minutes"
        key = "hr" if unit == "Hours" else "min"
        self._window_minutes = val * WINDOW_UNIT_TO_MINUTES[key]
        self._save_settings()

    def _reset_zoom(self):
        for xt in self._xaxis_tags.values():
            if dpg.does_item_exist(xt):
                dpg.set_axis_limits_auto(xt)
        for xt in self._custom_xaxis.values():
            if dpg.does_item_exist(xt):
                dpg.set_axis_limits_auto(xt)

    def _on_group_toggle(self, group: str, enabled: bool):
        self._group_visible[group] = enabled
        tag = f"plot_{group}"
        if dpg.does_item_exist(tag):
            dpg.configure_item(tag, show=enabled)
        self._save_settings()

    def _on_left_click(self):
        for group in ALL_SENSOR_GROUPS:
            pt = f"plot_{group}"
            if dpg.does_item_exist(pt) and dpg.is_item_hovered(pt):
                x, _ = dpg.get_plot_mouse_pos()
                with self._lock:
                    df = self._df
                if not df.empty:
                    idx = int((df["time_min"] - float(x)).abs().idxmin())
                    self._pinned_time = float(df.iloc[idx]["time_min"])
                    self._refresh_pin_lines()
                break

    def _clear_pin(self):
        self._pinned_time = None
        self._refresh_pin_lines()

    def _refresh_pin_lines(self):
        for group, yt in self._yaxis_tags.items():
            tag = f"pin_{group}"
            if dpg.does_item_exist(tag):
                dpg.delete_item(tag)
            if self._pinned_time is not None and dpg.does_item_exist(yt):
                dpg.add_inf_line_series([self._pinned_time], tag=tag,
                                        parent=yt, label="Pin")
                dpg.bind_item_theme(tag, self._pin_theme())
        for gid, yt in self._custom_yaxis.items():
            tag = f"cpin_{gid}"
            if dpg.does_item_exist(tag):
                dpg.delete_item(tag)
            if self._pinned_time is not None and dpg.does_item_exist(yt):
                dpg.add_inf_line_series([self._pinned_time], tag=tag,
                                        parent=yt, label="Pin")
                dpg.bind_item_theme(tag, self._pin_theme())

    def _refresh_cg_sensor_list(self):
        group = dpg.get_value("cg_group")
        dpg.delete_item("cg_sensors", children_only=True)
        for sensor in ALL_SENSOR_GROUPS.get(group, []):
            dpg.add_checkbox(label=sensor, tag=f"cg_cb_{sensor}",
                             default_value=True, parent="cg_sensors")

    def _add_custom_graph(self):
        group = dpg.get_value("cg_group")
        sensors = [
            s for s in ALL_SENSOR_GROUPS.get(group, [])
            if dpg.does_item_exist(f"cg_cb_{s}") and dpg.get_value(f"cg_cb_{s}")
        ]
        if not sensors:
            return
        self._add_custom_graph_from_config(group, sensors)
        self._save_settings()

    def _remove_custom_graph(self, gid: int):
        self._custom_graphs = [g for g in self._custom_graphs if g["id"] != gid]
        if dpg.does_item_exist(f"cg_card_{gid}"):
            dpg.delete_item(f"cg_card_{gid}")
        self._custom_xaxis.pop(gid, None)
        self._custom_yaxis.pop(gid, None)
        self._custom_series.pop(gid, None)
        self._save_settings()

    def _add_note(self):
        text = (dpg.get_value("note_input") or "").strip()
        if not text:
            return
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._notes.append({"timestamp": ts, "text": text})
        save_notes(self._notes)
        dpg.set_value("note_input", "")
        self._render_notes()

    def _render_notes(self):
        if not dpg.does_item_exist("notes_panel"):
            return
        dpg.delete_item("notes_panel", children_only=True)
        for note in reversed(self._notes):
            with dpg.group(parent="notes_panel"):
                dpg.add_text(note.get("timestamp", ""),
                             color=(107, 114, 128, 255), wrap=self._METRICS_W - 24)
                dpg.add_text(note.get("text", ""), wrap=self._METRICS_W - 24)
                dpg.add_separator()

    def _on_save(self):
        dpg.add_file_dialog(
            label="Save Data",
            callback=self._do_save,
            default_filename=f"cryo_data.{self._save_format}",
            width=640, height=420,
        )

    def _do_save(self, sender, app_data):
        path = (app_data or {}).get("file_path_name", "")
        if not path:
            return
        with self._lock:
            df = self._df.copy()
        if dpg.get_value("save_scope") and not df.empty:
            ct = float(df.iloc[-1]["time_min"])
            df = df[df["time_min"] >= ct - self._window_minutes].copy()
        try:
            content, _ = export_data_bytes(df, self._save_format)
            with open(path, "wb") as f:
                f.write(content)
            dpg.set_value("save_status", f"Saved {len(df)} rows → {Path(path).name}")
        except Exception as e:
            dpg.set_value("save_status", f"Error: {e}")

    # ------------------------------------------------------------------
    # Live updates  (called from main loop — always on main thread)
    # ------------------------------------------------------------------

    def _update_plots(self, df: pd.DataFrame):
        if df.empty:
            return
        ct = float(df.iloc[-1]["time_min"])
        ws = ct - self._window_minutes

        now_mono = time.monotonic()
        prev_mono = getattr(self, "_dbg_prev_mono", None)
        prev_ct = getattr(self, "_dbg_prev_ct", None)
        if prev_mono is not None:
            d_mono = now_mono - prev_mono
            d_ct_s = (ct - prev_ct) * 60.0
            if d_mono > 0.30 or d_ct_s > 0.30 or d_ct_s < 0.0:
                qsize = self._update_q.qsize()
                print(f"[plot] dmono={d_mono*1000:6.0f}ms  dct={d_ct_s*1000:+6.0f}ms  "
                      f"ct={ct:.4f}min  rows={len(df)}  qsize={qsize}", flush=True)
        self._dbg_prev_mono = now_mono
        self._dbg_prev_ct = ct
        visible = df[df["time_min"] >= ws]
        if visible.empty:
            visible = df.tail(1)
        times = visible["time_min"].tolist()
        available = infer_available_sensors(df)

        for group, sensors in available.items():
            xt = self._xaxis_tags.get(group)
            yt = self._yaxis_tags.get(group)
            if not xt or not yt:
                continue
            for sensor in sensors:
                if sensor not in df.columns:
                    continue
                st = self._series_tags.get(group, {}).get(sensor)
                if not st or not dpg.does_item_exist(st):
                    continue
                vals = [float(v) if pd.notna(v) else float("nan")
                        for v in visible[sensor]]
                dpg.set_value(st, [times, vals])
                if sensor not in self._series_shown:
                    self._series_shown.add(sensor)
                    dpg.configure_item(st, show=True)
            dpg.set_axis_limits(xt, ws, ct)
            dpg.set_axis_limits_auto(yt)

        for graph in self._custom_graphs:
            gid = graph["id"]
            xt = self._custom_xaxis.get(gid)
            yt = self._custom_yaxis.get(gid)
            if not xt or not yt:
                continue
            for sensor in graph["sensors"]:
                if sensor not in df.columns:
                    continue
                st = self._custom_series.get(gid, {}).get(sensor)
                if not st or not dpg.does_item_exist(st):
                    continue
                vals = [float(v) if pd.notna(v) else float("nan")
                        for v in visible[sensor]]
                dpg.set_value(st, [times, vals])
            dpg.set_axis_limits(xt, ws, ct)
            dpg.set_axis_limits_auto(yt)

    def _update_metrics(self, df: pd.DataFrame):
        if df.empty:
            return
        available = infer_available_sensors(df)
        live_idx = len(df) - 1
        pin_idx = (
            int((df["time_min"] - self._pinned_time).abs().idxmin())
            if self._pinned_time is not None else None
        )

        for sensors in available.values():
            for sensor in sensors:
                if sensor not in self._metrics_created:
                    with dpg.group(horizontal=True, parent="metrics_rows",
                                   tag=f"mrow_{sensor}"):
                        dpg.add_text(sensor[:16], tag=f"mlabel_{sensor}")
                        dpg.add_spacer(width=4)
                        dpg.add_text("---", tag=f"mlive_{sensor}",
                                     color=(37, 99, 235, 255))
                        dpg.add_spacer(width=4)
                        dpg.add_text("---", tag=f"mpin_{sensor}",
                                     color=(217, 119, 6, 255))
                    self._metrics_created.add(sensor)

                if sensor not in df.columns:
                    continue
                v = df.iloc[live_idx][sensor]
                dpg.set_value(f"mlive_{sensor}",
                              f"{float(v):.3f}" if pd.notna(v) else "---")
                pv = df.iloc[pin_idx][sensor] if pin_idx is not None else None
                dpg.set_value(f"mpin_{sensor}",
                              f"{float(pv):.3f}" if pv is not None and pd.notna(pv) else "---")

    # ------------------------------------------------------------------
    # Settings persistence
    # ------------------------------------------------------------------

    def _save_settings(self):
        save_settings({
            "window_value": dpg.get_value("win_val"),
            "window_unit":  dpg.get_value("win_unit"),
            "save_format":  dpg.get_value("save_format"),
            "save_scope":   dpg.get_value("save_scope"),
            "group_visible": {g: dpg.get_value(f"gtoggle_{g}") for g in ALL_SENSOR_GROUPS},
            "custom_graphs": [
                {"group": g["group"], "sensors": g["sensors"]}
                for g in self._custom_graphs
            ],
        })

    def _apply_settings(self):
        s = self._startup_settings
        if not s:
            return
        win_val = float(s.get("window_value", DEFAULT_WINDOW_VALUE))
        win_unit = s.get("window_unit", "Minutes")
        dpg.set_value("win_val", win_val)
        dpg.set_value("win_unit", win_unit)
        fmt = s.get("save_format", "csv").upper()
        dpg.set_value("save_format", fmt if fmt in ("CSV", "JSON", "XLSX") else "CSV")
        dpg.set_value("save_scope", bool(s.get("save_scope", True)))
        for g, visible in self._group_visible.items():
            dpg.set_value(f"gtoggle_{g}", visible)
            tag = f"plot_{g}"
            if dpg.does_item_exist(tag):
                dpg.configure_item(tag, show=visible)
        for cg in s.get("custom_graphs", []):
            self._add_custom_graph_from_config(cg["group"], cg["sensors"])

    def _add_custom_graph_from_config(self, group: str, sensors: List[str]):
        sensors = [s for s in sensors if s in ALL_SENSOR_GROUPS.get(group, [])]
        if not sensors:
            return
        gid = self._custom_counter
        self._custom_counter += 1
        self._custom_graphs.append({"id": gid, "group": group, "sensors": sensors})
        self._custom_series[gid] = {}
        title = f"{group}: {', '.join(sensors)}"
        xt, yt = f"cxax_{gid}", f"cyax_{gid}"
        self._custom_xaxis[gid] = xt
        self._custom_yaxis[gid] = yt
        with dpg.group(tag=f"cg_card_{gid}", parent="custom_container"):
            with dpg.group(horizontal=True):
                dpg.add_text(title, color=(107, 114, 128, 255))
                dpg.add_button(label="Remove", small=True,
                               callback=lambda s, a, u: self._remove_custom_graph(u),
                               user_data=gid)
            with dpg.plot(tag=f"cg_plot_{gid}", height=200, width=-1,
                          label=title, anti_aliased=True):
                dpg.add_plot_legend()
                dpg.add_plot_axis(dpg.mvXAxis, tag=xt, label="Time [min]")
                dpg.add_plot_axis(dpg.mvYAxis, tag=yt,
                                  label=GROUP_LABELS.get(group, group))
                for i, sensor in enumerate(sensors):
                    st = f"cg_ser_{gid}_{sensor}"
                    dpg.add_line_series([], [], label=sensor, tag=st, parent=yt)
                    dpg.bind_item_theme(st, self._sensor_theme(sensor, i))
                    self._custom_series[gid][sensor] = st

    # ------------------------------------------------------------------
    # Poll thread
    # ------------------------------------------------------------------

    def _poll(self):
        _file_pos: int = 0
        _columns: list = []

        while dpg.is_dearpygui_running():
            try:
                path = STREAM_SOURCE_FILE
                if not path.exists():
                    time.sleep(self._POLL_S)
                    continue

                size = path.stat().st_size
                if size == _file_pos:
                    time.sleep(self._POLL_S)
                    continue

                if size < _file_pos:
                    # file was rewritten (buffer rotation) — reset
                    _file_pos = 0
                    _columns = []

                with open(path, "r", newline="", encoding="utf-8") as f:
                    if not _columns or _file_pos == 0:
                        header = f.readline()
                        _columns = [c.strip() for c in header.strip().split(",")]
                        _file_pos = f.tell()
                    f.seek(_file_pos)
                    new_text = f.read()
                    _file_pos = f.tell()

                if not new_text.strip():
                    time.sleep(self._POLL_S)
                    continue

                import io as _io
                new_rows = pd.read_csv(_io.StringIO(new_text), header=None, names=_columns)
                new_rows = DataAdapter.normalize(new_rows)

                if not new_rows.empty:
                    with self._lock:
                        cached = self._df
                        last = self._last_seen
                    updated = append_new_stream_rows(cached, new_rows, last,
                                                     max_rows=BUFFER_MAX_ROWS)
                    if not updated.empty:
                        new_last = float(updated.iloc[-1]["time_min"])
                        with self._lock:
                            self._df = updated
                            self._last_seen = new_last
                        self._update_q.put(updated)
            except Exception:
                pass
            time.sleep(self._POLL_S)

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def run(self):
        dpg.create_context()
        dpg.create_viewport(title="HYPER-DAQ", width=1400, height=900,
                            min_width=900, min_height=600)
        dpg.setup_dearpygui()

        self._make_themes()
        self._build()
        self._refresh_cg_sensor_list()
        self._apply_settings()
        dpg.set_primary_window("primary", True)
        dpg.show_viewport()

        threading.Thread(target=self._poll, daemon=True).start()

        while dpg.is_dearpygui_running():
            # Drain queue — process only the latest update per frame
            df = None
            try:
                while True:
                    df = self._update_q.get_nowait()
            except queue.Empty:
                pass

            if df is not None:
                self._update_plots(df)
                self._update_metrics(df)

            dpg.render_dearpygui_frame()

        dpg.destroy_context()


if __name__ == "__main__":
    HyperDaqApp().run()
