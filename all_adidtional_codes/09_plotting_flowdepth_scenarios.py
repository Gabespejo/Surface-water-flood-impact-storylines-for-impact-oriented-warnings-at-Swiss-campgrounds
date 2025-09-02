#!/usr/bin/env -S mamba run -n env_py311 python

import os
import argparse
import sys
sys.path.insert(0, "/storage/homefs/ge24z347/Campgrounds/src")
from flow_depth_plotting import g_plot_maxwd_swissTLM

def main():
    parser = argparse.ArgumentParser(description="Plot LISFLOOD max depth maps for multiple scenarios")
    parser.add_argument("--location-name", required=True, help="Location name (e.g., Gordevio)")
    parser.add_argument("--start", type=int, default=10, help="Start of rainfall intensity (e.g., 10)")
    parser.add_argument("--end", type=int, default=120, help="End of rainfall intensity (exclusive, e.g., 120)")
    parser.add_argument("--step", type=int, default=10, help="Step of rainfall intensity (e.g., 10)")
    parser.add_argument("--output-folder", required=True, help="Folder to save all plots")
    parser.add_argument("--geo-shape", default="/rs_scratch/users/ge24z347/Data_forprocess/geo_ezgg_2km_ge.shp", help="Path to shapefile for overlay")

    args = parser.parse_args()

    # ==== Paths ====
    location = args.location_name
    dem_file = f"/storage/homefs/ge24z347/LISFLOOD_FP_8_1/build/{location}_2m/{location}_2m.dem"
    simulation_base = f"/storage/homefs/ge24z347/LISFLOOD_FP_8_1/build/{location}_2m"
    os.makedirs(args.output_folder, exist_ok=True)

    # ==== Loop ====
    for rain in range(args.start, args.end, args.step):
        fv1_folder = f"{location}_2m_{rain}_fv1-gpu"
        max_file = os.path.join(simulation_base, fv1_folder, f"{location}_2m_{rain}_1h_{rain}.max")

        if not os.path.exists(max_file):
            print(f"  Missing: {max_file} — skipping.")
            continue

        print(f" Plotting {rain} mm/h...")
        g_plot_maxwd_swissTLM(
            dem_file=dem_file,
            max_file=max_file,
            plot_output_folder=args.output_folder,
            geo_ezgg_2km_ge=args.geo_shape,
            location_name=location,
            rain_intensity=f"{rain} mm/h",
            color1="navajowhite", color2="darkorange", color3="firebrick"
        )

    print(f"\n All plots saved in: {args.output_folder}")

if __name__ == "__main__":
    main()