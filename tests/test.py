import csv
import math
import random
import time
from pathlib import Path

STREAM_FILE = Path("../backend/test_stream.csv")

HEADERS = [
    "time_min",
    "fluid",
    "PT1", "PT2", "PT3", "PT4", "PT5", "PT6", "PT7",
    "TS1", "TS2", "TS3", "TS4", "TS5", "TS6",
    "T_sat PT2", "T_sat PT4",
    "Total Flow",
    "H, Transferred",
]

ROWS_PER_SECOND = 50
RESET_ON_START = True
LOOP_FOREVER = True
DURATION_MIN = 60.0


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_headers(path: Path) -> None:
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(HEADERS)


def ensure_headers(path: Path, reset: bool = False) -> None:
    ensure_parent(path)

    if reset or not path.exists() or path.stat().st_size == 0:
        write_headers(path)
        return

    with path.open("r", newline="") as f:
        first_row = next(csv.reader(f), [])

    if first_row != HEADERS:
        write_headers(path)


def build_row(t_min: float, transferred_kg: float) -> list:
    cycle = 20.0
    phase = (t_min % cycle) / cycle
    active = 0.10 < phase < 0.72

    fluid = "LH2" if active else "Idle"

    pressures = []
    for i in range(1, 8):
        base = 1.0 + 0.08 * i
        amp = 2.8 - 0.22 * i
        wave = math.sin(2 * math.pi * phase + i * 0.18)
        pulse = max(0.0, math.sin(math.pi * (phase - 0.10) / 0.62)) if active else 0.0
        value = base + amp * pulse + 0.10 * wave + random.gauss(0, 0.03)
        pressures.append(round(max(0.85, value), 4))

    temp_bases = [42, 55, 72, 89, 108, 142]
    temps = []
    for i, base in enumerate(temp_bases, start=1):
        pulse = max(0.0, math.sin(math.pi * (phase - 0.10) / 0.62)) if active else 0.0
        slow = math.sin(2 * math.pi * (t_min / 35.0) + i * 0.25)
        value = base - 10.0 * pulse + 2.5 * slow + random.gauss(0, 0.25 + 0.04 * i)
        temps.append(round(value, 4))

    t_sat_pt2 = round(22.8 + 0.08 * t_min + 0.4 * math.sin(t_min / 8.0) + random.gauss(0, 0.05), 4)
    t_sat_pt4 = round(22.1 + 0.075 * t_min + 0.35 * math.sin(t_min / 7.0 + 0.5) + random.gauss(0, 0.05), 4)

    if active:
        flow_shape = max(0.15, math.sin(math.pi * (phase - 0.10) / 0.62))
        total_flow = 4.2 * flow_shape + 0.25 * math.sin(t_min * 0.7) + random.gauss(0, 0.03)
    else:
        total_flow = max(0.0, 0.03 + random.gauss(0, 0.01))
    total_flow = round(max(0.0, total_flow), 4)

    return [
        round(t_min, 6),
        fluid,
        pressures[0], pressures[1], pressures[2], pressures[3], pressures[4], pressures[5], pressures[6],
        temps[0], temps[1], temps[2], temps[3], temps[4], temps[5],
        t_sat_pt2, t_sat_pt4,
        total_flow,
        round(transferred_kg, 6),
    ]


def run() -> None:
    ensure_headers(STREAM_FILE, reset=RESET_ON_START)

    dt_sec = 1.0 / ROWS_PER_SECOND
    dt_min = dt_sec / 60.0

    t_min = 0.0
    transferred_kg = 0.0

    while True:
        row = build_row(t_min, transferred_kg)

        with STREAM_FILE.open("a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(row)

        total_flow_gps = float(row[17])
        transferred_kg += total_flow_gps * dt_sec / 1000.0
        t_min += dt_min

        if not LOOP_FOREVER and t_min >= DURATION_MIN:
            break

        time.sleep(dt_sec)


if __name__ == "__main__":
    run()