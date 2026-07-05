#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import argparse
import sys
sys.path.append("/storage/homefs/ge24z347/Campgrounds/src")

from Exposure_buildings_campground import (
    export_building_level_exposure_csv,
    plot_first_change_threshold,
)


def safe_name(s):
    """Make safe filename from campground name."""
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in s).strip("_")


def main():

    parser = argparse.ArgumentParser(
        description="Compare exposure between two LISFLOOD versions (e.g. v2 vs v4)"
    )

    # INPUTS
    parser.add_argument("--hazard-v2", required=True,
                        help="Glob path for hazards WITHOUT discharge (version 2).")

    parser.add_argument("--hazard-v4", required=True,
                        help="Glob path for hazards WITH discharge (version 4).")

    parser.add_argument("--buildings", required=True,
                        help="Buildings shapefile/geopackage")

    parser.add_argument("--campgrounds", required=True,
                        help="Campgrounds polygons")

    parser.add_argument("--polygon-column", required=True,
                        help="Campground name column")

    parser.add_argument("--camp", action="append", required=True,
                        help="Campground name (repeat for multiple)")

    parser.add_argument("--outdir", required=True,
                        help="Output folder")

    parser.add_argument("--id-column", default="id_def")

    parser.add_argument("--buffer-m", type=float, default=2.0)

    args = parser.parse_args()

    os.makedirs(args.outdir, exist_ok=True)

    # --------------------------------------------------
    # 1️⃣ Compute building exposure tables
    # --------------------------------------------------

    print("Running exposure calculation for V2 (no discharge)...")

    csv_v2 = os.path.join(args.outdir, "buildings_exposed_v2.csv")

    df_v2 = export_building_level_exposure_csv(
        hazard_glob=args.hazard_v2,
        buildings_path=args.buildings,
        campgrounds_path=args.campgrounds,
        polygon_column=args.polygon_column,
        camp_names=args.camp,
        out_csv=csv_v2,
        id_column=args.id_column,
        buffer_m=args.buffer_m,
    )

    print("Running exposure calculation for V4 (with discharge)...")

    csv_v4 = os.path.join(args.outdir, "buildings_exposed_v4.csv")

    df_v4 = export_building_level_exposure_csv(
        hazard_glob=args.hazard_v4,
        buildings_path=args.buildings,
        campgrounds_path=args.campgrounds,
        polygon_column=args.polygon_column,
        camp_names=args.camp,
        out_csv=csv_v4,
        id_column=args.id_column,
        buffer_m=args.buffer_m,
    )

    print(f"Saved building tables:\n  {csv_v2}\n  {csv_v4}")

    # --------------------------------------------------
    # 2️⃣ Create comparison plot
    # --------------------------------------------------

    for camp_name in args.camp:

        fig_name = f"threshold_discharge_effect_{safe_name(camp_name)}_v4_minus_v2.png"
        out_png = os.path.join(args.outdir, fig_name)

        thr = plot_first_change_threshold(
            df_v2,
            df_v4,
            camp_name=camp_name,
            id_column=args.id_column,
            out_png=out_png,
            show=False,
        )

        thr_csv = os.path.join(
            args.outdir,
            f"threshold_table_{safe_name(camp_name)}_v4_minus_v2.csv"
        )

        thr.to_csv(thr_csv, index=False)

        print(f"Saved:\n  {out_png}\n  {thr_csv}")


if __name__ == "__main__":
    main()
