# HVAC Fault Detection Dashboard

A simplified, self-contained version of an HVAC fault detection pipeline for an
Air Handling Unit (AHU). It simulates realistic BMS sensor trend data,
runs rule-based fault detection to flag mechanical/control-system
malfunctions, and produces visualizations plus a Power BI-ready export.

## What it does

1. **`generate_data.py`** — simulates 2 weeks of 5-minute AHU sensor data
   (outdoor/mixed/supply/return air temp, damper position, cooling valve
   position, supply fan speed, duct static pressure) and injects four
   common fault conditions into known time windows:
   - Stuck damper
   - Supply air temperature (SAT) sensor drift
   - Low delta-T / reduced cooling capacity
   - Fan performance / duct static pressure fault

2. **`fault_detection.py`** — applies simple, explainable rules (in the
   spirit of ASHRAE Guideline 36 fault rules) to flag each condition, and
   scores detection precision/recall against the injected ground truth.

3. **`visualize.py`** — plots sensor trends with detected fault windows
   shaded, a bar chart of fault counts by type, and exports a tidy CSV
   (`output/powerbi_fault_summary.csv`) for a Power BI/Excel dashboard.

4. **`main.py`** — runs the full pipeline end to end.

## Usage

```bash
pip install -r requirements.txt
python main.py
```

Outputs land in `output/`:
- `ahu_sensor_data.csv` — raw simulated sensor data with ground-truth labels
- `ahu_fault_detection_results.csv` — data with detection flags
- `fault_detection_summary.csv` — precision/recall per fault type
- `sensor_timeseries.png`, `detected_fault_counts.png` — charts
- `powerbi_fault_summary.csv` — daily fault counts, ready to import into Power BI

## Notes

This is a scaled-down, synthetic-data version built to demonstrate the
approach (data simulation → rule-based fault detection → visualization)
rather than a production BMS integration.
