#!/usr/bin/env -S mamba run -n env_py311 python
# -*- coding: utf-8 -*-

import os
import sys
import glob
import argparse
import pandas as pd

# Fix: use absolute path to src (same style as your other scripts)
sys.path.insert(0, "/storage/homefs/ge24z347/Campgrounds/src")

from Impact_campgrounds import flooded_area_timeseries_from_netcdf


def main():
    parser = argparse.ArgumentParser(
        description="Flooded area time series (per time step) from NetCDF"
    )

    parser.add_argument("--geojson-file", required=True, help="Path to GeoJSON file")
    parser.add_argument(
        "--polygon-column-name",
        default="Campingplaetze_excel_finshed_Campingplatz",
        help="Column name for campground name matching",
    )
    parser.add_argument("--polygon-name", required=True, help="Name of the specific campground")

    # NetCDF input: either one file OR a folder + glob
    parser.add_argument("--nc-file", default=None, help="Path to a single NetCDF file")
    parser.add_argument("--nc-folder", default=None, help="Folder with NetCDF files")
    parser.add_argument("--nc-glob", default="*.nc", help='Glob pattern inside nc-folder (default "*.nc")')

    parser.add_argument("--var", default="water_depth", help="Variable name in NetCDF (e.g., water_depth)")
    parser.add_argument("--time-dim", default="REFERENCE_TS", help="Time dimension name (e.g., REFERENCE_TS or time)")

    parser.add_argument("--min-depth", type=float, default=0.05, help="Minimum depth threshold (m)")
    parser.add_argument("--case-name", required=True, help="Case name for outputs (e.g., MORGES)")
    parser.add_argument("--output-folder", required=True, help="Folder to save output CSV")

    args = parser.parse_args()

    # validate input choice
    if (args.nc_file is None) == (args.nc_folder is None):
        raise SystemExit(" Provide exactly one: --nc-file OR --nc-folder")

    os.makedirs(args.output_folder, exist_ok=True)

    # Build list of NetCDF files
    if args.nc_file:
        nc_files = [args.nc_file]
    else:
        nc_files = sorted(glob.glob(os.path.join(args.nc_folder, args.nc_glob)))
        if not nc_files:
            raise SystemExit(f" No NetCDF files found in {args.nc_folder} with pattern {args.nc_glob}")

    print(f"Running flooded area time series for: {args.case_name}")
    print(f"Files: {len(nc_files)}")

    dfs = []
    for f in nc_files:
        print(f"  -> {f}")
        df = flooded_area_timeseries_from_netcdf(
            nc_file=f,
            var=args.var,
            geojson_file=args.geojson_file,
            polygon_column_name=args.polygon_column_name,
            polygon_name=args.polygon_name,
            min_depth_threshold=args.min_depth,
            time_dim=args.time_dim,
        )
        # keep provenance if multiple files
        dfs.append(df)

    df_all = pd.concat(dfs, ignore_index=True)

    out_csv = os.path.join(args.output_folder, f"{args.case_name}_flooded_area_timeseries.csv")
    df_all.to_csv(out_csv, index=False)
    print(f" Saved: {out_csv}")


if __name__ == "__main__":
    main()