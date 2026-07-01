"""Generate charts summarizing AHU sensor trends and detected faults.

Saves static PNGs to output/ for quick review, and a tidy CSV
(output/powerbi_fault_summary.csv) meant to be dropped straight into
Power BI (or Excel) for an interactive dashboard.
"""

import matplotlib.pyplot as plt
import pandas as pd

FAULT_COLORS = {
    "stuck_damper": "#e07a5f",
    "sat_sensor_drift": "#3d405b",
    "low_delta_t_cooling_fault": "#81b29a",
    "fan_performance_fault": "#f2cc8f",
}


def plot_sensor_timeseries(df, out_path="output/sensor_timeseries.png"):
    fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True)

    axes[0].plot(df["timestamp"], df["supply_air_temp"], label="Supply Air Temp", color="#1f77b4")
    axes[0].plot(df["timestamp"], df["mixed_air_temp"], label="Mixed Air Temp", color="#7f7f7f", alpha=0.7)
    axes[0].set_ylabel("Temp (C)")
    axes[0].set_title("AHU Temperatures")
    axes[0].legend(loc="upper right")

    axes[1].plot(df["timestamp"], df["damper_position"], label="Damper Position (%)", color="#2ca02c")
    axes[1].plot(df["timestamp"], df["cooling_valve_position"], label="Cooling Valve (%)", color="#d62728")
    axes[1].set_ylabel("Position (%)")
    axes[1].set_title("Actuator Positions")
    axes[1].legend(loc="upper right")

    axes[2].plot(df["timestamp"], df["static_pressure"], label="Static Pressure (in. wc)", color="#9467bd")
    axes[2].set_ylabel("Pressure")
    axes[2].set_title("Duct Static Pressure")
    axes[2].legend(loc="upper right")

    for ax in axes:
        for label, color in FAULT_COLORS.items():
            mask = df["fault_label"] == label
            if mask.any():
                ax.fill_between(
                    df["timestamp"], *ax.get_ylim(), where=mask, color=color, alpha=0.15
                )

    fig.suptitle("HVAC (AHU) Sensor Trends with Injected Fault Windows Shaded")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_fault_counts(result, out_path="output/detected_fault_counts.png"):
    counts = (
        result.loc[result["detected_fault_type"] != "none", "detected_fault_type"]
        .value_counts()
        .reindex(FAULT_COLORS.keys(), fill_value=0)
    )
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(counts.index, counts.values, color=[FAULT_COLORS[k] for k in counts.index])
    ax.set_ylabel("Detected rows (5-min intervals)")
    ax.set_title("Detected Fault Counts by Type")
    ax.tick_params(axis="x", rotation=20)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def export_powerbi_summary(result, out_path="output/powerbi_fault_summary.csv"):
    daily = (
        result.assign(date=result["timestamp"].dt.date)
        .groupby(["date", "detected_fault_type"])
        .size()
        .reset_index(name="row_count")
    )
    daily.to_csv(out_path, index=False)


if __name__ == "__main__":
    result = pd.read_csv("output/ahu_fault_detection_results.csv", parse_dates=["timestamp"])
    plot_sensor_timeseries(result)
    plot_fault_counts(result)
    export_powerbi_summary(result)
    print("Saved charts and Power BI export to output/")
