#!/usr/bin/env -S mamba run -n env_py311 python
# -*- coding: utf-8 -*-

import os
import sys
import argparse
from pathlib import Path
import pandas as pd


# Fix: use absolute path to src (same style as your other scripts)
sys.path.insert(0, "/storage/homefs/ge24z347/Campgrounds/src")
from Impact_campgrounds import exposure_counts_timeseries_from_netcdf


def main():
    p = argparse.ArgumentParser(
        description="Count impacted campground points per NetCDF timestep (mobile vs non_mobile, levels 1/2)."
    )
    p.add_argument("--nc-file", required=True, help="Path to NetCDF (e.g. ...Combiprecip.nc)")
    p.add_argument("--var", default="water_depth", help="Variable name in NetCDF (default water_depth)")
    p.add_argument("--time-dim", default="REFERENCE_TS", help="Time dimension name (default REFERENCE_TS)")

    p.add_argument("--points", required=True, help="Exposure points file (SHP/GPKG).")
    p.add_argument("--class-field", default="type", help="Field containing class labels (default type).")

    p.add_argument("--buffer", type=float, default=3.0, help="Buffer radius in meters (default 3)")
    p.add_argument("--rental-threshold", type=float, default=1.0, help="Non-mobile split threshold in m (default 1.0)")
    p.add_argument("--force-points-crs", default=None, help="Force CRS of points, e.g. EPSG:2056 (optional)")
    p.add_argument("--assume-crs", default="EPSG:2056", help="Assume CRS if NetCDF missing CRS (default EPSG:2056)")

    p.add_argument("--case-name", required=True, help="Prefix name for outputs (e.g. MORGES_CP)")
    p.add_argument("--outdir", required=True, help="Output folder")

    args = p.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    counts_long, counts_pivot, frac_long, frac_wide, totals = exposure_counts_timeseries_from_netcdf(
        nc_file=args.nc_file,
        var=args.var,
        points_path=args.points,
        class_field=args.class_field,
        buffer_m=args.buffer,
        rental_threshold=args.rental_threshold,
        time_dim=args.time_dim,
        force_points_crs=args.force_points_crs,
        assume_crs=args.assume_crs,
    )

    # add provenance columns (safe overwrite style)
    for df in (counts_long, counts_pivot, frac_long):
        df.insert(0, "case", args.case_name)
        df.insert(1, "nc_file", os.path.basename(args.nc_file))

    counts_long.to_csv(outdir / f"{args.case_name}_counts_long.csv", index=False)
    counts_pivot.to_csv(outdir / f"{args.case_name}_counts_pivot.csv", index=False)
    frac_long.to_csv(outdir / f"{args.case_name}_fractions_long.csv", index=False)
    frac_wide.to_csv(outdir / f"{args.case_name}_fractions_wide.csv")

    # Excel bundle
    xlsx = outdir / f"{args.case_name}_exposure_timeseries.xlsx"
    with pd.ExcelWriter(xlsx, engine="openpyxl") as xw:
        counts_long.to_excel(xw, sheet_name="counts_long", index=False)
        counts_pivot.to_excel(xw, sheet_name="counts_pivot", index=False)
        frac_long.to_excel(xw, sheet_name="fractions_long", index=False)
        frac_wide.to_excel(xw, sheet_name="fractions_wide")
        pd.DataFrame([totals]).to_excel(xw, sheet_name="site_totals", index=False)

    print("Saved:")
    print(" -", outdir / f"{args.case_name}_counts_long.csv")
    print(" -", outdir / f"{args.case_name}_counts_pivot.csv")
    print(" -", outdir / f"{args.case_name}_fractions_long.csv")
    print(" -", outdir / f"{args.case_name}_fractions_wide.csv")
    print(" -", xlsx)


if __name__ == "__main__":
    main()