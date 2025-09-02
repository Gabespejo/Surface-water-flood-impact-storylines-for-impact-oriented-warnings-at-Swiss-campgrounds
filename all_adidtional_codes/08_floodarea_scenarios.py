#!/usr/bin/env -S mamba run -n env_py311 python

import os
import sys
import argparse
import pandas as pd

sys.path.insert(0, "/storage/homefs/ge24z347/Campgrounds/src")
from Waterdepth_analysis import plot_flooded_area_fv1

def main():
    parser = argparse.ArgumentParser(description="Plot flooded area vs precipitation for a given case.")
    parser.add_argument("--csv-file", required=True, help="Path to CSV file with flood analysis results.")
    parser.add_argument("--case-name", required=True, help="Case name for the plot title.")
    parser.add_argument("--output-folder", required=False, help="Folder where to save the plot. Defaults to CSV's folder.")
    args = parser.parse_args()

    if not os.path.exists(args.csv_file):
        raise FileNotFoundError(f" CSV not found: {args.csv_file}")

    df = pd.read_csv(args.csv_file)

    # Use the same folder as CSV if output not provided
    output_folder = args.output_folder or os.path.dirname(args.csv_file)

    print(f" Plotting for case: {args.case_name}")
    plot_flooded_area_fv1(df, args.case_name, output_folder=output_folder)

if __name__ == "__main__":
    main()