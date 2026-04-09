from __future__ import annotations

import io
import json
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from config import (
    FLOW_SENSORS,
    NOTES_FILE,
    PRESSURE_SENSORS,
    STREAM_SOURCE_FILE,
    TEMPERATURE_SENSORS,
    TRANSFER_SENSORS,
    ALL_SENSOR_GROUPS,
)


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


def append_new_stream_rows(
    cached_df: pd.DataFrame,
    source_df: pd.DataFrame,
    last_time: Optional[float],
    max_rows: Optional[int] = None,
) -> pd.DataFrame:
    if source_df.empty:
        return cached_df

    if last_time is None or cached_df.empty:
        fresh = source_df.copy()
    else:
        fresh = source_df[source_df["time_min"] > float(last_time)].copy()

    if fresh.empty:
        combined = cached_df
    else:
        combined = pd.concat([cached_df, fresh], ignore_index=True)
        combined = combined.drop_duplicates(subset=["time_min"], keep="last")
        combined = DataAdapter.normalize(combined)

    if max_rows is not None and len(combined) > max_rows:
        combined = combined.iloc[-max_rows:].reset_index(drop=True)

    return combined