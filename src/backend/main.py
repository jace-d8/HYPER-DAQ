import logging
from datetime import datetime
from pathlib import Path

from controller import SensorController
from csv_buffer import CsvBuffer
from src.frontend.config import BUFFER_MAX_ROWS, SAMPLE_HZ

DATA_DIR = Path(__file__).parent.parent.parent / "data"
LOGS_DIR = Path(__file__).parent.parent.parent / "logs"

LOGS_DIR.mkdir(parents=True, exist_ok=True)
log_filename = LOGS_DIR / f"run_{datetime.now():%Y-%m-%d_%H-%M-%S}.log"

logging.basicConfig(
    filename=log_filename,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    csv_buffer = CsvBuffer(
        data_csv="sensor_data.csv",
        buffer_csv="sensor_buffer.csv",
        max_rows=BUFFER_MAX_ROWS,
        data_dir=DATA_DIR,
        logging_state_file=DATA_DIR / "logging_state.json",
    )

    controller = SensorController(
        csv_buffer=csv_buffer,
        sample_hz=SAMPLE_HZ,
    )

    try:
        controller.run()
    except KeyboardInterrupt:
        controller.stop()
    finally:
        csv_buffer.close()


if __name__ == "__main__":
    main()
