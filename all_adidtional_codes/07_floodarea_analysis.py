#!/usr/bin/env -S mamba run -n env_py311 python

import os
import sys
import argparse
import pandas as pd

# Fix: use absolute path to src
sys.path.insert(0, "/storage/homefs/ge24z347/Campgrounds/src")

from Waterdepth_analysis import calculate_flooded_area_by_scenarios_fv1, plot_flooded_area_fv1

def main():
    parser = argparse.ArgumentParser(description="Flooded area analysis and plotting for FV1 solver")
    parser.add_argument("--geojson-file", required=True, help="Path to GeoJSON file")
    parser.add_argument("--polygon-column-name", default="Campingplaetze_excel_finshed_Campingplatz", help="Column name for campground")
    parser.add_argument("--polygon-name", required=True, help="Name of the specific campground")
    parser.add_argument("--raster-folder", required=True, help="Folder where raster simulations are stored")
    parser.add_argument("--raster-prefix", required=True, help="Prefix used in raster file naming")
    parser.add_argument("--case-name", required=True, help="Case name for plotting (e.g., GORDEVIO)")
    parser.add_argument("--output-folder", required=True, help="Folder where to save plots and output CSV")
    parser.add_argument("--min-depth", type=float, default=0.05, help="Minimum water depth to count as flooded")
    parser.add_argument("--duration", required=True, choices=["60min", "75min", "1h"],
                    help="Duration tag in raster filename (e.g., 60min, 75min, 1h)")
    parser.add_argument("--start", type=int, default=10, help="Start precipitation")
    parser.add_argument("--end", type=int, default=120, help="End precipitation (exclusive)")
    parser.add_argument("--step", type=int, default=10, help="Step for precipitation")

    args = parser.parse_args()

    # Strip leading/trailing spaces from polygon name
    args.polygon_name = args.polygon_name.strip().lower()

    os.makedirs(args.output_folder, exist_ok=True)
    scenarios = list(range(args.start, args.end, args.step))

    print(f" Running flood analysis for: {args.case_name}")
    df_flooded = calculate_flooded_area_by_scenarios_fv1(
        args.geojson_file,
        args.polygon_column_name,
        args.polygon_name,
        args.raster_folder,
        args.raster_prefix,
        scenarios,
        args.min_depth
    )

    # Save DataFrame
    output_csv = os.path.join(args.output_folder, f"{args.case_name}_flooded_area_fv1.csv")
    df_flooded.to_csv(output_csv, index=False)
    print(f" Flooded area table saved to: {output_csv}")

    # Plot
    plot_flooded_area_fv1(df_flooded, args.case_name)

if __name__ == "__main__":
    main()