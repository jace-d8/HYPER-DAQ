from __future__ import annotations
import time
import pandas as pd
from main import DataAdapter, STREAM_SOURCE_FILE

WRITE_BATCH_SIZE = 1
WRITE_INTERVAL_SEC = 0.5
RESET_ON_COMPLETE = True


def ensure_target() -> None:
    if not STREAM_SOURCE_FILE.exists():
        pd.DataFrame(columns=DataAdapter.sample_data().df.columns).to_csv(STREAM_SOURCE_FILE, index=False)


def write_header(df: pd.DataFrame) -> None:
    STREAM_SOURCE_FILE.write_text(df.iloc[:0].to_csv(index=False), encoding="utf-8")


def append_rows(df: pd.DataFrame, start_idx: int, batch_size: int) -> int:
    end_idx = min(start_idx + batch_size, len(df))
    chunk = df.iloc[start_idx:end_idx]
    if chunk.empty:
        return start_idx
    chunk.to_csv(STREAM_SOURCE_FILE, mode="a", header=False, index=False)
    return end_idx


def main() -> None:
    ensure_target()
    template_df = DataAdapter.sample_data().df.copy()

    while True:
        write_header(template_df)
        next_idx = 0
        while next_idx < len(template_df):
            next_idx = append_rows(template_df, next_idx, WRITE_BATCH_SIZE)
            time.sleep(WRITE_INTERVAL_SEC)
        if not RESET_ON_COMPLETE:
            break
        time.sleep(1.0)


if __name__ == "__main__":
    main()
