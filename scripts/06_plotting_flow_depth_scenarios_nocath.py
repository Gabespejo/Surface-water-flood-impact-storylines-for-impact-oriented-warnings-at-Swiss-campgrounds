#!/usr/bin/env -S mamba run -n env_py311 python

import os
import argparse
import sys
sys.path.insert(0, "/storage/homefs/ge24z347/Campgrounds/src")
from flow_depth_plotting import g_plot_maxwd_swissTLM_nocatchment

def main():
    parser = argparse.ArgumentParser(description="Plot LISFLOOD max depth maps for multiple scenarios")
    parser.add_argument("--location-name", required=True, help="Location name (e.g., Gordevio)")
    parser.add_argument("--version", default="", help="Version suffix (e.g., v1, _v2, v3_, _v4, or empty)")
    parser.add_argument("--duration", required=True, help="Rainfall duration (e.g., 60min or 75min)")
    parser.add_argument("--start", type=int, default=10, help="Start of rainfall intensity (e.g., 10)")
    parser.add_argument("--end", type=int, default=120, help="End of rainfall intensity (exclusive, e.g., 120)")
    parser.add_argument("--step", type=int, default=10, help="Step of rainfall intensity (e.g., 10)")
    parser.add_argument("--output-folder", required=True, help="Folder to save all plots")
    parser.add_argument("--use-catchments", action="store_true", help="Enable catchment overlay")
    parser.add_argument("--geo-shape", default=None, help="Path to shapefile for overlay (required if --use-catchments)")

    args = parser.parse_args()

    # ==== Clean version string to avoid double underscores ====
    version_clean = args.version.strip("_")
    if version_clean:
        base_name = f"{args.location_name}_2m_{version_clean}"
    else:
        base_name = f"{args.location_name}_2m"

    # ==== Paths ====
    dem_file = f"/storage/homefs/ge24z347/LISFLOOD_FP_8_1/build/{base_name}/{base_name}.dem"
    simulation_base = "/storage/homefs/ge24z347/LISFLOOD_FP_8_1/build"
    os.makedirs(args.output_folder, exist_ok=True)

    # ==== Loop ====
    for rain in range(args.start, args.end, args.step):
        fv1_folder = f"{base_name}_{rain}_fv1-gpu"
        max_file = os.path.join(
            simulation_base,
            base_name,
            fv1_folder,
            f"{base_name}_{args.duration}_{rain}.max"
        )

        if not os.path.exists(max_file):
            print(f"  Missing: {max_file} — skipping.")
            continue

        print(f" Plotting {rain} mm/h...")
        g_plot_maxwd_swissTLM_nocatchment(
            dem_file=dem_file,
            max_file=max_file,
            plot_output_folder=args.output_folder,
            location_name=args.location_name,
            rain_intensity=f"{rain} mm/h",
            use_catchments=args.use_catchments,
            geo_ezgg_2km_ge=args.geo_shape,
            color1="navajowhite", color2="darkorange", color3="firebrick"
        )

    print(f"\n All plots saved in: {args.output_folder}")

if __name__ == "__main__":
    main()