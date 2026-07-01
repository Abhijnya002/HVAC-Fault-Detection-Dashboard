"""Simulate Air Handling Unit (AHU) sensor data with injected faults.

Produces a time-series CSV that mimics BMS trend data for one AHU:
outdoor/mixed/supply/return air temps, supply fan speed, damper
position, cooling valve position, and duct static pressure. A few
common fault conditions are injected into known time windows so the
detector's output can be checked against ground truth.
"""

import numpy as np
import pandas as pd

RNG = np.random.default_rng(42)

DAYS = 14
FREQ_MIN = 5
COOLING_SETPOINT = 13.0  # supply air temp setpoint, deg C


def _diurnal_outdoor_temp(hours):
    return 22 + 8 * np.sin((hours - 9) / 24 * 2 * np.pi) + RNG.normal(0, 0.4, len(hours))


def generate(days=DAYS, freq_min=FREQ_MIN):
    periods = int(days * 24 * 60 / freq_min)
    timestamps = pd.date_range("2026-06-01", periods=periods, freq=f"{freq_min}min")
    hours = timestamps.hour + timestamps.minute / 60

    outdoor_air_temp = _diurnal_outdoor_temp(hours.values)
    occupied = ((hours >= 7) & (hours <= 19)).astype(float)

    # Baseline (healthy) equipment behavior
    return_air_temp = 22 + 1.5 * occupied + RNG.normal(0, 0.3, periods)
    mixed_air_damper_pos = np.clip(20 + 0.6 * (outdoor_air_temp - 15), 10, 90)
    mixed_air_temp = (
        mixed_air_damper_pos / 100 * outdoor_air_temp
        + (1 - mixed_air_damper_pos / 100) * return_air_temp
        + RNG.normal(0, 0.2, periods)
    )
    # Valve modulates to hit the SAT setpoint given the coil's max capacity
    # (a full-open coil can pull mixed air down to ~9 C).
    cooling_valve_pos = np.clip(
        (mixed_air_temp - COOLING_SETPOINT) / (mixed_air_temp - 9) * 100, 0, 100
    )
    supply_air_temp = mixed_air_temp - cooling_valve_pos / 100 * (mixed_air_temp - 9)
    supply_air_temp += RNG.normal(0, 0.2, periods)
    supply_fan_speed = np.clip(40 + 40 * occupied + RNG.normal(0, 2, periods), 0, 100)
    static_pressure = 0.4 + 0.008 * supply_fan_speed + RNG.normal(0, 0.03, periods)

    df = pd.DataFrame(
        {
            "timestamp": timestamps,
            "outdoor_air_temp": outdoor_air_temp,
            "return_air_temp": return_air_temp,
            "mixed_air_temp": mixed_air_temp,
            "supply_air_temp": supply_air_temp,
            "damper_position": mixed_air_damper_pos,
            "cooling_valve_position": cooling_valve_pos,
            "supply_fan_speed": supply_fan_speed,
            "static_pressure": static_pressure,
        }
    )

    df["fault_label"] = "none"

    # Fault 1: stuck damper (frozen at a fixed position for 1.5 days)
    stuck_mask = (df.timestamp >= "2026-06-03") & (df.timestamp < "2026-06-04 12:00")
    df.loc[stuck_mask, "damper_position"] = 25.0
    df.loc[stuck_mask, "fault_label"] = "stuck_damper"

    # Fault 2: supply air temperature sensor drift (biased high, ramps up)
    drift_mask = (df.timestamp >= "2026-06-06") & (df.timestamp < "2026-06-08")
    drift_progress = np.linspace(0, 4.5, drift_mask.sum())
    df.loc[drift_mask, "supply_air_temp"] += drift_progress
    df.loc[drift_mask, "fault_label"] = "sat_sensor_drift"

    # Fault 3: low delta-T / cooling coil fault (reduced cooling capacity).
    # Valve saturates near 100% trying to hit setpoint, but coil can only
    # produce a small temperature drop -> low delta-T despite max call for cooling.
    lowdt_mask = (df.timestamp >= "2026-06-10") & (df.timestamp < "2026-06-11 18:00")
    df.loc[lowdt_mask, "cooling_valve_position"] = 100.0
    df.loc[lowdt_mask, "supply_air_temp"] = (
        df.loc[lowdt_mask, "mixed_air_temp"] - 1.0 + RNG.normal(0, 0.2, lowdt_mask.sum())
    )
    df.loc[lowdt_mask, "fault_label"] = "low_delta_t_cooling_fault"

    # Fault 4: duct static pressure / fan performance fault (pressure too low for fan speed)
    fan_mask = (df.timestamp >= "2026-06-13") & (df.timestamp < "2026-06-14")
    df.loc[fan_mask, "static_pressure"] *= 0.45
    df.loc[fan_mask, "fault_label"] = "fan_performance_fault"

    return df


if __name__ == "__main__":
    data = generate()
    data.to_csv("output/ahu_sensor_data.csv", index=False)
    print(f"Generated {len(data)} rows -> output/ahu_sensor_data.csv")
    print(data["fault_label"].value_counts())
