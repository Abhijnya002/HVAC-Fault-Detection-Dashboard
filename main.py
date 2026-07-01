"""End-to-end pipeline: simulate data -> detect faults -> visualize."""

import os

from generate_data import generate
from fault_detection import run_all_rules, evaluate
from visualize import plot_sensor_timeseries, plot_fault_counts, export_powerbi_summary

os.makedirs("output", exist_ok=True)


def main():
    print("1. Generating synthetic AHU sensor data...")
    df = generate()
    df.to_csv("output/ahu_sensor_data.csv", index=False)

    print("2. Running fault detection rules...")
    result = run_all_rules(df)
    result.to_csv("output/ahu_fault_detection_results.csv", index=False)

    summary = evaluate(result)
    summary.to_csv("output/fault_detection_summary.csv", index=False)
    print(summary.to_string(index=False))

    print("3. Building visualizations...")
    plot_sensor_timeseries(result)
    plot_fault_counts(result)
    export_powerbi_summary(result)

    print("\nDone. Outputs written to ./output/")


if __name__ == "__main__":
    main()
