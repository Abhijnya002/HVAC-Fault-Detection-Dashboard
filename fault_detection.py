"""Rule-based fault detection for AHU sensor trend data.

Each rule encodes a simple, explainable heuristic of the kind used in
building-automation fault detection (loosely inspired by ASHRAE
Guideline 36 style rules). Rules are evaluated independently per row,
then combined into a single detected-fault column.
"""

import numpy as np
import pandas as pd

ROLLING_WINDOW = 6  # 30 minutes at 5-minute sampling


def detect_stuck_damper(df, min_expected_swing=0.15, ratio_tolerance=0.3, window=ROLLING_WINDOW):
    """Flag when the damper barely moves while outdoor conditions (which the
    damper responds to) are actively swinging -- i.e. actual movement is far
    below what's expected given how much the outdoor air temp is changing.
    """
    expected_damper = np.clip(20 + 0.6 * (df["outdoor_air_temp"] - 15), 10, 90)
    expected_swing = expected_damper.rolling(window).std()
    actual_swing = df["damper_position"].rolling(window).std()
    return (expected_swing > min_expected_swing) & (actual_swing < ratio_tolerance * expected_swing)


def detect_sat_sensor_drift(df, threshold=2.0, valve_saturation=98):
    """Flag SAT readings that deviate from the value implied by the coil
    model. Skipped while the valve is saturated near 100%, since a maxed-out
    valve unable to hit setpoint is a coil/capacity fault, not a sensor issue,
    and would otherwise look identical to drift under this model.
    """
    expected_sat = df["mixed_air_temp"] - df["cooling_valve_position"] / 100 * (
        df["mixed_air_temp"] - 9
    )
    residual = df["supply_air_temp"] - expected_sat
    return (residual > threshold) & (df["cooling_valve_position"] < valve_saturation)


def detect_low_delta_t(df, min_delta_t=2.5, active_cooling=90):
    delta_t = df["mixed_air_temp"] - df["supply_air_temp"]
    cooling_active = df["cooling_valve_position"] > active_cooling
    return cooling_active & (delta_t < min_delta_t)


def detect_fan_performance_fault(df, expected_slope=0.008, expected_intercept=0.4, tolerance=0.15):
    expected_pressure = expected_intercept + expected_slope * df["supply_fan_speed"]
    return (expected_pressure - df["static_pressure"]) > tolerance


def run_all_rules(df):
    result = df.copy()
    result["flag_stuck_damper"] = detect_stuck_damper(result)
    result["flag_sat_sensor_drift"] = detect_sat_sensor_drift(result)
    result["flag_low_delta_t_cooling_fault"] = detect_low_delta_t(result)
    result["flag_fan_performance_fault"] = detect_fan_performance_fault(result)

    flag_cols = [
        "flag_stuck_damper",
        "flag_sat_sensor_drift",
        "flag_low_delta_t_cooling_fault",
        "flag_fan_performance_fault",
    ]
    result["any_fault_detected"] = result[flag_cols].any(axis=1)

    def _first_flag(row):
        for col in flag_cols:
            if row[col]:
                return col.replace("flag_", "")
        return "none"

    result["detected_fault_type"] = result.apply(_first_flag, axis=1)
    return result


def evaluate(result):
    """Compare detected faults against injected ground-truth labels."""
    label_to_flag = {
        "stuck_damper": "flag_stuck_damper",
        "sat_sensor_drift": "flag_sat_sensor_drift",
        "low_delta_t_cooling_fault": "flag_low_delta_t_cooling_fault",
        "fan_performance_fault": "flag_fan_performance_fault",
    }
    rows = []
    for label, flag_col in label_to_flag.items():
        truth = result["fault_label"] == label
        pred = result[flag_col]
        tp = (truth & pred).sum()
        fn = (truth & ~pred).sum()
        fp = (~truth & pred).sum()
        recall = tp / (tp + fn) if (tp + fn) else float("nan")
        precision = tp / (tp + fp) if (tp + fp) else float("nan")
        rows.append(
            {
                "fault_type": label,
                "true_positive_rows": tp,
                "false_negative_rows": fn,
                "false_positive_rows": fp,
                "recall": round(recall, 3),
                "precision": round(precision, 3),
            }
        )
    return pd.DataFrame(rows)


if __name__ == "__main__":
    df = pd.read_csv("output/ahu_sensor_data.csv", parse_dates=["timestamp"])
    result = run_all_rules(df)
    result.to_csv("output/ahu_fault_detection_results.csv", index=False)

    summary = evaluate(result)
    summary.to_csv("output/fault_detection_summary.csv", index=False)
    print(summary.to_string(index=False))
