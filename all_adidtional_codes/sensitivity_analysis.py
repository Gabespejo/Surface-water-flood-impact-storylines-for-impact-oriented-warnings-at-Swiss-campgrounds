#!/usr/bin/env -S mamba run -n env_py311 python
import os
import sys
import argparse

# Add src/ to import `compare_solver_signed_difference`
sys.path.insert(0, os.path.abspath(os.path.join(__file__, "..", "..", "src")))

from flow_depth_plotting import compare_solver_absolute_difference

def main():
    parser = argparse.ArgumentParser(description="Batch compare SIGNED difference maps from two LISFLOOD solver outputs.")
    parser.add_argument("--base-dir-a", required=True, help="Path to Solver A root folder")
    parser.add_argument("--base-dir-b", required=True, help="Path to Solver B root folder")
    parser.add_argument("--basename-core", required=True, help="Base name without version (e.g. Interlaken_2m)")
    parser.add_argument("--version-a", default="", help="Version suffix for Solver A (e.g. _v1, _v2, _v3, _v4 or empty for none)")
    parser.add_argument("--version-b", default="", help="Version suffix for Solver B (e.g. _v1, _v2, _v3, _v4 or empty for none)")
    parser.add_argument("--duration", required=True, help="Simulation duration string (e.g. 60min, 75min)")
    parser.add_argument("--dem-file", required=True, help="Path to DEM file")
    parser.add_argument("--out-dir", required=True, help="Folder to save comparison maps")
    parser.add_argument("--start", type=int, required=True, help="Start rainfall in mm")
    parser.add_argument("--end", type=int, required=True, help="End rainfall in mm")
    parser.add_argument("--step", type=int, default=10, help="Rainfall step (default: 10)")
    parser.add_argument("--location", default="Location", help="Label for plot title")
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    base_name_a = f"{args.basename_core}{args.version_a}"
    base_name_b = f"{args.basename_core}{args.version_b}"

    for rain in range(args.start, args.end + 1, args.step):
        folder_a = f"{base_name_a}_{rain}_fv1-gpu"
        folder_b = f"{base_name_b}_{rain}_fv1-gpu"

        fname_a = f"{base_name_a}_{args.duration}_{rain}.max"
        fname_b = f"{base_name_b}_{args.duration}_{rain}.max"

        fpath_a = os.path.join(args.base_dir_a, folder_a, fname_a)
        fpath_b = os.path.join(args.base_dir_b, folder_b, fname_b)

        outname = f"{base_name_a}_vs_{base_name_b}_absdiff_{rain}mm.png"
        output_path = os.path.join(args.out_dir, outname)

        if not os.path.exists(fpath_a):
            print(f" Missing: {fpath_a}")
            continue
        if not os.path.exists(fpath_b):
            print(f" Missing: {fpath_b}")
            continue

        compare_solver_absolute_difference(
            dem_file=args.dem_file,
            solver_a_file=fpath_a,
            solver_b_file=fpath_b,
            output_path=output_path,
            location=args.location,
            rain_label=f"{rain} mm/h"
        )

if __name__ == "__main__":
    main()