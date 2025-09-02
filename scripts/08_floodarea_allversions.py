#!/usr/bin/env -S mamba run -n env_py311 python
import os
import argparse
import pandas as pd
import matplotlib.pyplot as plt

def _pick_col(df, contains):
    # helper to find a column whose name contains a substring (case-insensitive)
    for c in df.columns:
        if contains.lower() in c.lower():
            return c
    return None

def main():
    p = argparse.ArgumentParser(description="Plot flooded area vs precipitation for multiple versions.")
    p.add_argument("--csv-files", nargs="+", required=True,
                   help="List of CSVs to plot (one per version).")
    p.add_argument("--labels", nargs="*", default=None,
                   help="Optional labels for legend (same count/order as csv-files). "
                        "If omitted, parent folder names are used.")
    p.add_argument("--case-name", required=True, help="Case name for the plot title.")
    p.add_argument("--output-folder", required=False,
                   help="Folder to save plot & combined CSV. Defaults to first CSV's folder.")
    p.add_argument("--outfile", default=None,
                   help="Output PNG filename (defaults to <case-name>_flooded_area_fv1_multi.png).")
    args = p.parse_args()

    if args.labels and (len(args.labels) != len(args.csv_files)):
        raise ValueError("Number of --labels must match number of --csv-files.")

    # Determine output folder / filename
    out_dir = args.output_folder or os.path.dirname(os.path.abspath(args.csv_files[0]))
    os.makedirs(out_dir, exist_ok=True)
    out_png = args.outfile or f"{args.case_name}_flooded_area_fv1_multi.png"
    out_png = os.path.join(out_dir, out_png)
    out_csv = os.path.join(out_dir, f"{args.case_name}_flooded_area_fv1_combined.csv")

    # Prepare combined dataframe keyed by precipitation
    combined = None
    plt.figure(figsize=(10, 5))

    for i, csv_path in enumerate(args.csv_files):
        if not os.path.exists(csv_path):
            print(f"Warning: CSV not found and skipped -> {csv_path}")
            continue

        df = pd.read_csv(csv_path)

        # Be tolerant to column names
        x_col = _pick_col(df, "Precipitation") or _pick_col(df, "precipitation")
        y_col = _pick_col(df, "Flooded Area (%)") or _pick_col(df, "Flooded") or _pick_col(df, "percent")

        if x_col is None or y_col is None:
            raise KeyError(f"Required columns not found in {csv_path}. "
                           f"Have: {list(df.columns)}")

        # sort by precipitation just in case
        df = df.sort_values(by=x_col)

        # choose label
        if args.labels:
            label = args.labels[i]
        else:
            # default to parent folder name (e.g., Gordevio_2m_v5)
            label = os.path.basename(os.path.dirname(os.path.abspath(csv_path))) or f"Series {i+1}"

        # plot
        plt.plot(df[x_col], df[y_col], marker="s", linewidth=2, label=label)

        # merge into combined table
        tmp = df[[x_col, y_col]].copy()
        tmp.columns = ["Precipitation (mm/h)", label]
        combined = tmp if combined is None else pd.merge(
            combined, tmp, on="Precipitation (mm/h)", how="outer"
        )

    if combined is None or combined.empty:
        raise RuntimeError("No valid data to plot.")

    # Save combined CSV
    combined.sort_values("Precipitation (mm/h)", inplace=True)
    combined.to_csv(out_csv, index=False)

    # Style and save figure
    plt.xlabel("Precipitation (mm/h)")
    plt.ylabel("Flooded Area (%)")
    plt.title(f"{args.case_name}: Flooded Area (%) for every scenario")
    plt.grid(True, linestyle="--", alpha=0.4)
    plt.legend(title="Version", loc="best")
    plt.tight_layout()
    plt.savefig(out_png, dpi=300)
    print(f"Saved plot: {out_png}")
    print(f"Saved combined table: {out_csv}")

if __name__ == "__main__":
    main()