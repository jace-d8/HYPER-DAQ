import time
import csv
from datetime import datetime
import logging
import numpy as np
import matplotlib  # Not needed on windows

matplotlib.use("TkAgg")  # or "MacOSX"
import matplotlib.pyplot as plt
from lakeshore import Model336

log_filename = f"run_{datetime.now():%Y%m%d_%H%M%S}.log"

logging.basicConfig(
    filename=log_filename,
    level=logging.INFO,  # Level of info captured
    format="%(asctime)s - %(levelname)s - %(message)s",  # Log line format
)

logging.info("Program started.")

try:
    sensor = Model336()
    logging.info("Connected to Model336 successfully.")
except Exception as e:
    logging.exception("Failed to connect to Model336.")
    raise

current_hour = None
csv_file = None
writer = None
start = time.time()


def open_new_csv():
    global csv_file, writer, current_hour

    if csv_file:
        csv_file.close()
        logging.info("Closed previous CSV file.")

    timestamp = datetime.now()
    filename = f"temperature_{timestamp:%Y%m%d_%H00}.csv"

    csv_file = open(filename, "a", newline="")  # Open in write
    writer = csv.writer(csv_file)
    writer.writerow(["timestamp", "elapsed_s", "temperature_K"])
    current_hour = timestamp.hour
    logging.info(f"Started new CSV file: {filename}")

temps = []
times = []

# 0.5 Hz sampling
while True:

    now = datetime.now()
    if now.hour != current_hour:
        open_new_csv()
    try:
        temp = sensor.get_kelvin_reading("A")
        elapsed = time.time() - start
        writer.writerow([now, elapsed, temp])
        csv_file.flush()
        logging.info(f"Temperature: {temp:.4f} K")

    except Exception:
        logging.exception("Error reading temperature.")

    time.sleep(0.5)

# Convert to NumPy
temps = np.array(temps)
times = np.array(times)
# Plot
plt.plot(times, temps)
plt.xlabel("Time (s)")
plt.ylabel("Temperature (K)")
plt.title("Temperature Drift")
plt.show()
