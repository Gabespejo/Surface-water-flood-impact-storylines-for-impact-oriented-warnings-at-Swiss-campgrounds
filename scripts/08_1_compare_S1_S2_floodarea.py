#!/usr/bin/env -S mamba run -n env_py311 python
# -*- coding: utf-8 -*-

import os
import sys
import argparse
import pandas as pd

sys.path.insert(0, "/storage/homefs/ge24z347/Campgrounds/src")


def main():
    parser = argparse.ArgumentParser(
        description="Compare flooded area between two versions and save plot (guaranteed)."
    )
    parser.add_argument("--csv-s1", required=True)
    parser.add_argument("--csv-s2", required=True)
    parser.add_argument("--case-name", required=True)
    parser.add_argument("--output-path", required=True)

    parser.add_argument("--label-s1", default="S1")
    parser.add_argument("--label-s2", default="S2")

    args = parser.parse_args()

    if not os.path.exists(args.csv_s1):
        raise FileNotFoundError(f"S1 CSV not found: {args.csv_s1}")
    if not os.path.exists(args.csv_s2):
        raise FileNotFoundError(f"S2 CSV not found: {args.csv_s2}")

    df_s1 = pd.read_csv(args.csv_s1)
    df_s2 = pd.read_csv(args.csv_s2)

    outdir = os.path.dirname(args.output_path)
    if outdir:
        os.makedirs(outdir, exist_ok=True)

    print(f"Plotting comparison for case: {args.case_name}")
    print(f"  S1 CSV: {args.csv_s1}")
    print(f"  S2 CSV: {args.csv_s2}")
    print(f"  Output: {args.output_path}")

    # --- use YOUR plotting function to create the figure ---
    import Waterdepth_analysis as wa

    # Prefer the function that supports output_path if you added it
    if hasattr(wa, "plot_flooded_area_two_versions_like_multiversion"):
        wa.plot_flooded_area_two_versions_like_multiversion(
            df_s1, df_s2, args.case_name,
            label_s1=args.label_s1,
            label_s2=args.label_s2,
            output_path=args.output_path,
            show=False,
        )
        print(f"Saved plot (via function): {args.output_path}")
        return

    # Otherwise call existing function (may only plot), then SAVE HERE
    if hasattr(wa, "plot_flooded_area_two_versions"):
        wa.plot_flooded_area_two_versions(df_s1, df_s2, args.case_name)
    else:
        raise AttributeError("No plotting function found in Waterdepth_analysis.py")

    # --- GUARANTEED SAVE: save the current matplotlib figure ---
    import matplotlib.pyplot as plt
    plt.savefig(args.output_path, dpi=300, transparent=True, bbox_inches="tight")
    plt.close()

    print(f"Saved plot (forced save): {args.output_path}")


if __name__ == "__main__":
    main()



