import logging
from datetime import datetime
from pathlib import Path

from controller import SensorController

DATA_DIR = Path(__file__).parent.parent.parent / "data"
LOGS_DIR = Path(__file__).parent.parent.parent / "logs"
MANIFEST_PATH = DATA_DIR / "sensor_manifest.json"

LOGS_DIR.mkdir(parents=True, exist_ok=True)
log_filename = LOGS_DIR / f"run_{datetime.now():%Y-%m-%d_%H-%M-%S}.log"

logging.basicConfig(
    filename=log_filename,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    controller = SensorController(data_dir=DATA_DIR, manifest_path=MANIFEST_PATH)
    try:
        controller.run()
    except KeyboardInterrupt:
        controller.stop()


if __name__ == "__main__":
    main()
