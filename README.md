# HVAC Fault Detection Dashboard

A simplified, self-contained version of an HVAC fault detection pipeline for
an Air Handling Unit (AHU). It simulates realistic BMS (Building Management
System) sensor trend data, runs rule-based fault detection to flag mechanical
and control-system malfunctions, and produces visualizations plus a
Power BI-ready export — the same three stages (data → detection →
dashboard) as the full production version, scaled down to a single AHU and
synthetic data so it can run anywhere with no building or database access.

## Table of contents

- [Why this exists](#why-this-exists)
- [Pipeline overview](#pipeline-overview)
- [The simulated AHU](#the-simulated-ahu)
- [Injected faults](#injected-faults)
- [Detection rules](#detection-rules)
- [Results](#results)
- [Visual output](#visual-output)
- [Interactive dashboard](#interactive-dashboard)
- [Usage](#usage)
- [Project structure](#project-structure)
- [Limitations & what a production version would add](#limitations--what-a-production-version-would-add)

## Why this exists

Building Management Systems generate huge volumes of trend data (temperatures,
damper/valve positions, fan speeds, pressures) but most sites have no
automated way to turn that into "this specific piece of equipment is
misbehaving." This project demonstrates a lightweight fault detection
approach that:

- doesn't require ML training data or labeled historical faults
- is fully explainable — every flag traces back to a physical rule an HVAC
  technician can sanity-check
- is cheap to run — a few explainable comparisons per row, no model serving

## Pipeline overview

```
generate_data.py  →  fault_detection.py  →  visualize.py  →  dashboard.py
   (simulate)          (detect + score)       (static charts)   (interactive HTML)
        \_______________________ main.py _______________________/
                        (runs all four end to end)
```

1. **`generate_data.py`** simulates 2 weeks of 5-minute AHU sensor data and
   injects four fault conditions into known time windows, keeping the
   ground-truth label for each row so detection accuracy can be measured.
2. **`fault_detection.py`** applies rule-based heuristics (in the spirit of
   ASHRAE Guideline 36 fault rules) to flag each condition, then scores
   precision/recall per fault type against the injected ground truth.
3. **`visualize.py`** plots sensor trends with detected fault windows shaded,
   a bar chart of fault counts by type, and exports a tidy CSV for a
   Power BI/Excel dashboard.
4. **`main.py`** runs steps 1–3 end to end and prints the scoring summary.

## The simulated AHU

`generate_data.py` models one AHU at 5-minute resolution over 14 days:

| Signal | Description |
|---|---|
| `outdoor_air_temp` | Diurnal sine wave + noise, stands in for a weather feed |
| `return_air_temp` | Rises during occupied hours (7am–7pm) |
| `mixed_air_temp` | Blend of outdoor + return air, weighted by damper position |
| `damper_position` | Modulates with outdoor air temp (economizer-style control) |
| `cooling_valve_position` | Modulates to drive supply air to the 13°C setpoint, capped by coil capacity |
| `supply_air_temp` | Result of mixed air temp minus the coil's cooling effect |
| `supply_fan_speed` | Higher during occupied hours |
| `static_pressure` | Tracks fan speed, plus noise |

Under normal operation the control loops are consistent with each other by
construction (e.g. supply air temp actually reflects damper + valve
positions), which is what lets the detection rules model "expected" behavior
and flag deviations from it.

## Injected faults

Four fault windows are injected into otherwise-healthy data:

| Fault | Window | What changes | Real-world cause |
|---|---|---|---|
| Stuck damper | Jun 3 – Jun 4 (1.5 days) | Damper freezes at a fixed 25% position regardless of outdoor conditions | Actuator or linkage failure |
| SAT sensor drift | Jun 6 – Jun 8 (2 days) | Supply air temp reading ramps up to +4.5°C above the true value | Miscalibrated or failing temperature sensor |
| Low delta-T cooling fault | Jun 10 – Jun 11 (1.5 days) | Cooling valve saturates at 100% but can only pull down ~1°C instead of the usual ~5–8°C | Refrigerant undercharge, fouled coil, or failed compressor |
| Fan performance fault | Jun 13 – Jun 14 (1 day) | Duct static pressure drops to ~45% of the expected value for the current fan speed | Belt slippage, damaged fan blade, or clogged filter |

## Detection rules

Each rule compares an observed signal against what the control logic implies
it *should* be, and fires when the deviation is sustained rather than a
single noisy sample:

- **Stuck damper** — compares the damper's actual rolling variability
  (30-min window) against the variability implied by outdoor air temp
  changes. If outdoor conditions are swinging but the damper barely moves,
  it's flagged.
- **SAT sensor drift** — computes an expected supply air temp from the
  mixed air temp and current valve position, and flags a sustained positive
  residual. Skipped while the valve is saturated near 100%, since a maxed-out
  valve that still can't hit setpoint is a capacity fault, not a sensor
  issue, and would otherwise look identical to drift under this model.
- **Low delta-T** — flags when the cooling valve is nearly fully open
  (>90%) but the mixed-to-supply temperature drop stays below 2.5°C, i.e.
  the coil is being asked for everything it has and still isn't delivering.
- **Fan performance** — flags when duct static pressure falls well below
  what the current fan speed should produce, based on the healthy
  speed-to-pressure relationship.

## Results

Precision/recall per fault type, scored against the injected ground truth
(`output/fault_detection_summary.csv`):

| Fault type | True positives | False negatives | False positives | Recall | Precision |
|---|---|---|---|---|---|
| Stuck damper | 399 | 33 | 0 | 0.92 | 1.00 |
| SAT sensor drift | 325 | 251 | 0 | 0.56 | 1.00 |
| Low delta-T cooling fault | 504 | 0 | 0 | 1.00 | 1.00 |
| Fan performance fault | 288 | 0 | 0 | 1.00 | 1.00 |

Precision is 1.00 across the board — every flag raised is a real fault, no
false alarms on healthy operation. Recall is lower for SAT sensor drift by
design: the fault is a *gradual* ramp from 0°C to 4.5°C of bias, so the rule
(correctly) doesn't flag it in the first day or so while the drift is still
within normal sensor noise — catching it only once it's large enough to be
distinguishable is the honest tradeoff of a threshold-based detector.

## Visual output

`visualize.py` produces:

- **`output/sensor_timeseries.png`** — supply/mixed air temps, damper and
  valve positions, and static pressure over the full 2-week window, with
  each injected fault window shaded so the signature of each fault is
  visible directly in the raw trends.
- **`output/detected_fault_counts.png`** — a bar chart of how many 5-minute
  intervals were flagged per fault type.
- **`output/powerbi_fault_summary.csv`** — daily counts of detected fault
  type, shaped for a one-click import into Power BI or Excel to build an
  interactive dashboard on top.

## Interactive dashboard

`dashboard.py` builds `output/dashboard.html` — a single self-contained file
(no external JS/CSS, no build step) that opens directly in a browser or
serves as a static GitHub Pages page. It includes:

- **KPI tiles** — sensor rows analyzed, flagged intervals, and average
  detection precision/recall across all four fault types.
- **Temperature trend chart** — supply/mixed air temp over the full 2-week
  window with fault windows shaded, a synced crosshair, and hover tooltips
  showing exact values (and which fault, if any, is active) at any point.
- **Fault count and precision/recall bar charts** — per fault type, with
  per-bar hover tooltips and direct value labels.
- **Light/dark mode toggle** and a **"View as table"** fallback on every
  chart, so every value is reachable without relying on hover or color.

Open it straight from disk:

```bash
python dashboard.py       # writes output/dashboard.html
open output/dashboard.html   # macOS; use `start` on Windows, `xdg-open` on Linux
```

## Usage

```bash
python -m venv .venv
source .venv/bin/activate         # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Outputs land in `output/`:

| File | Contents |
|---|---|
| `ahu_sensor_data.csv` | Raw simulated sensor data with ground-truth fault labels |
| `ahu_fault_detection_results.csv` | Same data with per-rule detection flags added |
| `fault_detection_summary.csv` | Precision/recall per fault type |
| `sensor_timeseries.png` | Sensor trend chart with fault windows shaded |
| `detected_fault_counts.png` | Bar chart of detected fault counts by type |
| `powerbi_fault_summary.csv` | Daily fault counts, ready for Power BI/Excel |
| `dashboard.html` | Self-contained interactive dashboard (see below) |

You can also run each stage independently — `python generate_data.py`,
`python fault_detection.py`, `python visualize.py`, `python dashboard.py` —
as long as the previous stage's CSV output already exists in `output/`.

## Project structure

```
.
├── generate_data.py       # Simulates AHU sensor data + injects faults
├── fault_detection.py     # Rule-based detection + precision/recall scoring
├── visualize.py           # Static charts + Power BI export
├── dashboard.py           # Interactive HTML dashboard
├── main.py                # Runs the full pipeline
├── requirements.txt
└── output/                # Generated CSVs, charts, and dashboard (sample outputs committed)
```

## Limitations & what a production version would add

This is intentionally scaled down to demonstrate the approach end to end:

- **Single AHU, synthetic data** — a real deployment would pull historical
  trend data for many air handlers/RTUs from the BMS (e.g. via BACnet or a
  SQL trend log export) rather than simulating it.
- **One fault at a time** — real equipment can develop overlapping faults;
  the rules here are tuned assuming faults don't co-occur, which is why the
  SAT drift rule explicitly excludes valve-saturated rows (see
  [Detection rules](#detection-rules)) rather than trying to disambiguate
  simultaneous faults.
- **Fixed thresholds** — thresholds here (e.g. 2.5°C delta-T, 30-min
  rolling windows) are tuned to this synthetic dataset. A production version
  would calibrate them per equipment type/site, or replace some with
  statistical process control limits derived from that site's own healthy
  baseline.
- **No alerting/persistence** — this pipeline is a batch script that writes
  CSVs; a production version would run on a schedule against live trend
  data and push new detections to a ticketing system or dashboard rather
  than a one-off report.
