# HYPER-DAQ

Live sensor data acquisition and visualization for HYPER's cryostats. Reads temperature, flow, and pressure sensors, streams them to
a real-time GUI, and writes per-run CSVs to disk.

## Contents

- [Setup](#setup)
- [System use](#system-use)
- [Sensor configuration](#sensor-configuration)
- [Changing GUI stuff](#changing-gui-stuff)
- [How the system works](#how-the-system-works)
  - [Branches](#branches)
  - [Where graph gaps come from](#where-graph-gaps-come-from)

---

## Setup

### 1. Install PyCharm

[PyCharm Community Edition](https://www.jetbrains.com/pycharm/download/) (free)
handles the Python install, the virtual environment, and a project terminal.
You do not need a system-wide Python install. I also advise Pycharm for changes 
to the code (it is easier than using Notepad).

### 2. Install the repo zip or clone it in PyCharm

Repository: <https://github.com/jace-d8/HYPER-DAQ>


**Option A - clone with git.** From a terminal:

```
git clone https://github.com/jace-d8/HYPER-DAQ.git
```

Or from inside PyCharm: **File → New → Project from Version Control…**,
paste the URL above, choose a folder, click **Clone**. PyCharm will open
the project automatically when the clone finishes.

**Option B - download as a zip (Easier if no git experience).** Open
<https://github.com/jace-d8/HYPER-DAQ> in a browser, click the green
**Code** button → **Download ZIP**, then extract the archive somewhere
permanent (e.g. `Desktop\HYPER-DAQ-main\`). In PyCharm: **File → Open**
and pick the extracted folder. Note that the zip doesn't include git
history, so to pull future updates you'll need to either re-download the
zip or switch to git later.

Either way, after this step PyCharm has the project open and you can
move on to creating the virtual environment.

### 3. Create the virtual environment

When PyCharm detects the project has no interpreter, it prompts to create
one. Click **Create**. It will make a `venv/` (or `.venv/`) folder in the
project root and use it as the Python interpreter.

### 4. Install dependencies

Pycharm should prompt you to download dependencies with the click 
of a button, if it does not:

Open PyCharm's bottom **Terminal** tab; it auto-activates the venv (you'll
see `(venv)` at the start of the prompt). Then:

```
pip install -r requirements.txt
```

**Note:** Most sensors require additional drivers to be installed (They are already installed on HYPER machines)

### 5. Create the desktop shortcut
Double-click `setup_shortcut.bat` in File Explorer. The **HYPER-DAQ** icon will then appear 
on either the local desktop or the onedrive desktop. HYPER machines are connected 
to onedrive so it will typically appear there, drag it from there to the local 
desktop and delete it from one drive.

### 6. Run it

Double-click **HYPER-DAQ** on the desktop. The launcher starts the backend, waits for the sensor manifest to appear, then opens the GUI.

Close the GUI window when done and the backend shuts down automatically.

---

## System use

### Starting and stopping logging

By default the system is in **test mode**; sensors are read, the chart
updates live, but **nothing is written to disk**. Click the **Logging OFF**
button at the top of the GUI to toggle logging state and start a logging run.

When logging starts:
- A new directory `data/run_<YYYY-MM-DD_HH-MM-SS>/` is created.
- Each sensor process opens its own CSV in that directory and writes every
  reading at the sensor's native rate.
- The controller writes `unified.csv` shards in the same directory at
  ~2.78 Hz (about 10,000 rows per hour-long shard).

**Note:** The unified csv will have per sensor data than the individual sensor files, 
it only grabs data from each sensor at it's selected frequency, not the fastest sensors
frequency. 

Click the button again to stop.

If a unified shard reaches the row cap mid-run, the writer rotates to
`unified_002.csv`, `unified_003.csv`, etc. 

### Where data lives

```
data/
  run_2026-05-10_14-30-22/
    LS336_1.csv         <- Lakeshore 336 native-rate readings
    Alicat.csv          <- Alicat flow native-rate readings
    NI_Pressure.csv     <- DAQ pressure native-rate readings
    unified_001.csv     <- wide-format snapshot @ ~2.78 Hz (sample-and-hold)
    unified_002.csv
    ...
  run_2026-05-10_15-12-08/
    ...
logs/
  run_<timestamp>.log   <- controller diagnostic log
```

The per-sensor CSVs contain **lossless data**, each reading is captured at
its native timestamp with no aliasing. `unified.csv` is convenient for quick
analysis but uses sample-and-hold semantics (the latest value as of each
tick).

### Changing sample/output rates

| Setting | Where | Default |
|---|---|---|
| Unified CSV rate | `src/backend/controller.py` → `UNIFIED_RATE_HZ` | ~2.78 Hz (10000 rows / hour) |
| Unified CSV row cap | `src/backend/controller.py` → `UNIFIED_MAX_ROWS` | 10,000 |
| Ring buffer capacity (display) | `SensorController(... capacity=4096)` | 4096 rows |
| Default GUI window size | `src/frontend/config.py` → `DEFAULT_WINDOW_VALUE` | 5.0 minutes |
| GUI poll period | `src/frontend/config.py` → `POLL_INTERVAL_MS` | 120 ms |

To change a sensor's polling rate, edit `poll_hz` on the driver class (e.g.
`Alicat.poll_hz = 40` in `src/drivers/Alicat.py`). These are currently
set to the hardware specs maximum frequency. NIDaq is special, see
the sensor configuration section below.

---

## Sensor configuration

Sensors are declared in `src/backend/controller.py` under `SENSOR_SPECS`.
Each entry is a python dictionary with:

- `name`: identifier used for the CSV filename and ring-buffer namespace.
- `module` / `class`: the driver to load in the subprocess (imported via
  `importlib`).
- `kwargs`: passed straight to the driver's `__init__`.
- `channels`: ordered list of channel names exposed to the GUI / unified CSV.
- `group`: which top-level GUI plot the channels go on (`Temperature`,
  `Pressure`, `Mass Flow Rate`, etc.).

### NI-DAQ

The NI-DAQ driver (`src/drivers/niDaq.py`) wraps `nidaqmx.Task`. All channels
on one device share a single hardware task with a single sample clock; one
`read()` returns a dict of mean values, one entry per channel.

#### Channel config (`NiDaqChannelConfig`)

```python
NiDaqChannelConfig(
    name="PT1",                          # channel display name
    physical_channel="cDAQ1Mod1/ai0",    # NI hardware address
    measurement_type="current",          # "voltage" | "current" | "thermocouple" | "rtd"
    min_val=0.0002,                      # expected lower bound (units depend on type)
    max_val=0.004,                       # expected upper bound
    terminal_config="DEFAULT",           # "DEFAULT" | "RSE" | "NRSE" | "DIFF"

    # --- thermocouple-only ---
    thermocouple_type="K",               # K | J | T | E | N | R | S | B

    # --- RTD-only ---
    rtd_type="PT_3851",
    resistance_config="3_WIRE",          # 2_WIRE | 3_WIRE | 4_WIRE
    current_excit_source="INTERNAL",
    current_excit_val=0.001,
    r_0=100.0,                           # nominal resistance at 0 °C

    # --- current-only (4-20 mA loops, etc.) ---
    shunt_resistor_loc="LET_DRIVER_CHOOSE",  # INTERNAL | EXTERNAL | LET_DRIVER_CHOOSE
    ext_shunt_resistor_val=249.0,        # ohms (only if EXTERNAL)
)
```

`min_val`/`max_val` are unit-specific:
- Voltage: volts
- Current: amps (so 4-20 mA = `min_val=0.004, max_val=0.020`)
- Thermocouple / RTD: degrees C

Tightening this range to your actual signal improves the DAQ's resolution
(it picks the best gain stage for the declared range). 

Not all the specifications shown above are required to configure the DAQ,
below is an example of two pressure sensors set up minimally:

```python
{
    "name": "NI_Pressure",
    "module": "src.drivers.niDaq",
    "class": "NiDaqTask",
    "kwargs": {
        "name": "NI_Pressure",
        "channels": [
            NiDaqChannelConfig(name="PT1", physical_channel="cDAQ2Mod1/ai0", measurement_type="current", min_val=0.002, max_val=0.004),
            NiDaqChannelConfig(name="PT2", physical_channel="cDAQ2Mod1/ai2", measurement_type="current", min_val=0.002, max_val=0.004),
        ],
        "sample_hz": 15,
    },
    "channels": ["PT1", "PT2"],
    "group": "Pressure",
},
```

#### Mean reduction (built into `read()`)

The NIDaq driver uses `READ_ALL_AVAILABLE` on every `read()`: it pulls
*every sample* the hardware has buffered since the last call and returns
the **mean per channel**. So:

- The hardware does the high-rate sampling (e.g., 1000 Hz).
- The Python subprocess reads less often (e.g., 15 Hz).
- Each read returns the mean of the ~67 samples per channel that
  accumulated in the DAQ buffer in that interval.

This gets us **high-frequency noise rejection for free**. We sample
fast in hardware, read slow in software, and store the noise-reduced means.

#### High-frequency setup

Two knobs in the spec's `kwargs`:

```python
"kwargs": {
    "name": "NI_Pressure",
    "channels": [...],
    "sample_hz": 1000,    # hardware sample clock: how fast the DAQ samples
},
```

And the Python poll rate is set on the sensor object (default in
`niDaq.py`):

```python
self.poll_hz = sample_hz   # default: poll Python-side as fast as we sample
```

For high-frequency mean reduction, **decouple these two**: leave `sample_hz`
high (e.g. 1000 or 10000) but lower `poll_hz` (e.g. 15-50 Hz). The driver 
supports this, just override `poll_hz` after construction or pass
it as a kwarg if you add the field.

| Goal | `sample_hz` | `poll_hz` | Stored value |
|---|---|---|---|
| Fast, raw | 1000 | 1000 | 1000 rows/sec, each is one sample |
| Fast, smoothed | 10000 | 50 | 50 rows/sec, each is mean of 200 samples |
| Slow, smoothed | 100 | 10 | 10 rows/sec, each is mean of 10 samples |

Internal buffer size is set in `_setup()`:
```python
self._task.timing.cfg_samp_clk_timing(
    rate=self.sample_hz,
    sample_mode=AcquisitionType.CONTINUOUS,
    samps_per_chan=int(self.sample_hz * 10),  # 10-second buffer
)
```
At 10000 Hz, this is a 100k-sample buffer per channel.
If you crank `sample_hz` further, bump the buffer multiplier too.

#### Channel/output list consistency

The number of `NiDaqChannelConfig` entries in `kwargs.channels` must match
the names declared in the top-level `channels` list. If you declare
`["PT1", "PT2"]` in `channels` but the kwargs only configure PT1, PT2's
column will read NaN (no hardware to read it from). Conversely, configuring
extra hardware channels not in `channels` works but those readings are
silently dropped before they reach the ring buffer or CSV.

### Other sensors

For Lakeshore 336/218 and Alicat, the relevant config lives in the driver
class (port, channels dict, etc.). The patterns are the same: edit
the `SENSOR_SPECS` entry's `kwargs` in `controller.py`. I left examples in the 
main branch code.

---

## Changing GUI stuff

### Sensor groups and labels (`src/frontend/config.py`)

```python
PRESSURE_SENSORS    = ["PT1", "PT2", "PT3", "PT4", "PT5", "PT6", "PT7"]
TEMPERATURE_SENSORS = ["TS1", "TS2", "TS3", "TS4", "TS5", "TS6", "T_sat PT2", "T_sat PT4"]
FLOW_SENSORS        = ["Total Flow"]
TRANSFER_SENSORS    = ["H, Transferred"]

ALL_SENSOR_GROUPS = {
    "Pressure":       PRESSURE_SENSORS,
    "Temperature":    TEMPERATURE_SENSORS,
    "Mass Flow Rate": FLOW_SENSORS,
    "H, Transferred": TRANSFER_SENSORS,
}

GROUP_LABELS = {
    "Pressure":       "Pressure [bara]",
    "Temperature":    "Temperature [K]",
    "Mass Flow Rate": "Mass Flow Rate [g/s]",
    "H, Transferred": "Total H₂ Transferred [kg]",
}
```

**Adding a sensor channel:** add the name to the right `*_SENSORS` list.
The "Add Graph" dropdown in the sidebar picks up new names automatically.

**Renaming a unit label:** edit `GROUP_LABELS`. Plot y-axis labels update
on next launch.

**Adding a whole new group:** add an entry to both `ALL_SENSOR_GROUPS` and
`GROUP_LABELS`, then make sure at least one sensor in `controller.py`
declares that group. The GUI auto-creates a plot panel for it.

### Line colors and themes

`DEFAULT_COLORS` in `config.py` is the cycle used for series within each
group. The GUI's `_make_themes` method (`src/frontend/gui.py`) defines
banner, button, and panel colors, look for `dpg.add_theme_color` to find
the values.

### Window default, units, and other layout

- Default window size and unit: `DEFAULT_WINDOW_VALUE` / `DEFAULT_WINDOW_UNIT`
  in `config.py`.
- Per-monitor scaling: handled automatically (`_layout_plots()` in
  `gui.py`). Plot heights split the body height across visible groups +
  custom graphs.
- Sidebar / metrics column widths: `_SIDEBAR_W` and `_METRICS_W` constants
  at the top of `HyperDaqApp` in `gui.py`.

I wrote the code with the intention of the window autoscaling to a given monitor,
but use this if there is an edge case that causing improper resizing. 

---

## How the system works

This is a multi-process architecture. The two top-level processes are:

```
[ launch.py ] -- spawns -- > [ main.py / SensorController ]   (the backend)
                          \-> [ gui.py / HyperDaqApp ]        (the frontend)
```

The backend further spawns one **subprocess per sensor**:

```
SensorController (parent)
├── sensor.LS336_1  -- subprocess
├── sensor.Alicat   -- subprocess
├── sensor.NI_Pressure -- subprocess
└── UnifierThread   (parent's own thread, writes unified.csv during logging)
```

Each sensor subprocess:
1. Imports its driver, calls `connect()` (claims the hardware handle to avoid conflict with other software).
2. Loops at the driver's `poll_hz`: `read() → push to buffer →
   write CSV row if logging is on`.
3. Writes its native-rate CSV directly to the active run directory.

The backend and GUI talk to each other through **shared regions of RAM**,
not files or network sockets. Python's `multiprocessing.shared_memory`
gives every process a window into the same chunk of memory, identified
by a string name, when the backend writes a sensor reading there, the
GUI sees the new value microseconds later with no copy in between. The
controller creates one such region (a ring buffer) per sensor, sized
`capacity × (1 + n_channels)` float64s, and writes their names plus
channel layouts to `data/sensor_manifest.json`. The GUI reads the
manifest, attaches to each ring buffer by name, and drains them at its
own pace.

Time correlation: the controller records a single `start_monotonic` at
launch and writes it to the manifest. Every sensor process and the GUI
use this as their time origin, so `time_min` values in every CSV are
in the same frame as the chart's x-axis.

### Branches

I included several architectural variants on separate branches
so you can pick whichever profile best fits the machine the lab is
running. Default branch is `main`.

| Branch | Frontend | Backend | Best on                                                                                                                                                                                                  |
|---|---|---|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `main` | DearPyGUI | multiprocessing | Lab machines with plenty of CPU cores, Works best with what we have. Default; what the README describes.                                                                                                 |
| `feature` | DearPyGUI | multiprocessing | Active dev branch; same architecture as `main` plus whatever's in flight.                                                                                                                                |
| `frontend-dearpygui` | DearPyGUI | asyncio (single process) | Reference single-process implementation. Lighter on RAM, no cross-process IPC, but constrained by the GIL, slower sensors are fine, fast ones (NIDaq at high rates) will see scheduling halts.           |
| `frontend-dash` | Plotly Dash (browser) | asyncio | Heaviest computationally because the GUI runs in a browser via a web server, but **accessible over the network** by URL. Use this if you need to view the chart remotely from your phone or home device. |
| `backend-multiprocess` | DearPyGUI | multiprocessing only | Same backend as `main` in isolation, for cherry-picking into other forks.                                                                                                                                |
| `backend-thread` | DearPyGUI | threading only | Sensors run as threads under one Python process. Best on **GPU-heavy machines that are CPU-light**, fewer processes means less context-switching overhead.                                               |

I advise using `main`. Only use other branches if there is 
a specific reason (browser-accessible display, very few
CPU cores, etc.).

### Why the main branch uses subprocesses instead of threads

Threads share a single Python interpreter and a single Global Interpreter
Lock. Sensor parsing (numpy reductions for NIDaq, dict building for
Lakeshore/Alicat) blocks the GIL for tens of milliseconds at a time. With
threads, the timing thread couldn't run smoothly because it was always
waiting for the GIL. With subprocesses, each sensor has its own GIL and
the OS schedules them across cores, the only thing that can pause the
data flow is the OS scheduler itself.

### Where graph gaps come from

There may be occasional gaps in the gui display. By default, the last read value
is repeated, but I allowed for gaps for data analysis accuracy. You may see 
gaps due to:

1. **Windows OS deschedules a Python thread for hundreds of ms.** Antivirus
   scans, system services, GPU workload from the GUI. The snapshot is
   purely software and can't prevent this, it's due to 'user-mode'
   Python on Windows. **For NI-DAQ this is effectively lossless**, the
   hardware keeps sampling into its own buffer (~10 seconds of headroom
   by default), and when the subprocess wakes back up it pulls every
   accumulated sample and means them. You lose temporal resolution
   (one wider-window mean instead of several narrower ones), not data.

2. **NIDaq hardware buffer overflows** if you set `sample_hz` very high
   and don't read often enough. The DAQ buffer is `sample_hz × 10` samples
   per channel. If a Python deschedule lasts longer than 10 seconds, older
   samples are dropped on the floor (the next `read()` will see fewer
   samples than expected). Mitigations:
   - Increase the buffer multiplier in `niDaq.py`'s `_setup` (e.g., from
     `* 10` to `* 60` for a 1-minute safety window).
   - Lower `sample_hz` if you don't need that resolution.
   - Make sure `poll_hz` is set so reads happen frequently enough that the
     buffer never gets close to full.

### Shutdown semantics

When you close the GUI window:
1. `launch.py` detects the GUI process exited.
2. It runs `taskkill /F /T /PID <backend_pid>` on Windows, which kills the
   backend *and every sensor subprocess descended from it*. No orphan
   `python.exe` processes are left running.
3. Each backend run uses a unique 8-character `run_id` in its shared
   memory names (`hyperdaq_LS336_1_a3f9c2e1`, etc.). Even if a previous
   run somehow left orphans behind, the next launch is in a fresh
   namespace, no `FileExistsError` on startup.

If you ever do see stale `python.exe` processes in Task Manager (e.g.,
after a power loss), end them all manually before relaunching.
