#!/usr/bin/env -S mamba run -n env_py311 python
import os
import sys
import argparse

# Make sure src/ is in your path
sys.path.insert(0, os.path.abspath(os.path.join(__file__, "..", "..", "src")))

from DEM_processing import create_stage_file, create_par_file_60min

def main():
    parser = argparse.ArgumentParser(
        description="Generate .stage file and multiple .par files for LISFLOOD scenarios."
    )
    parser.add_argument("--build-dir", required=True,
                        help="Directory where base .dem file is and .stage/.par files will be saved")
    parser.add_argument("--base-name", required=True,
                        help="Base file name, e.g. Morges_2m")
    parser.add_argument("--location-id", type=int, required=True,
                        help="Location ID from CSV for stage point")
    parser.add_argument("--start", type=int, default=5,
                        help="Start precipitation (e.g. 5 mm)")
    parser.add_argument("--end", type=int, default=75,
                        help="End precipitation (e.g. 75 mm)")
    parser.add_argument("--step", type=int, default=10,
                        help="Precipitation step (e.g. 10 mm)")
    parser.add_argument("--catchment-csv", required=True,
                        help="CSV with catchment locations (ID, East_X, North_Y)")
    args = parser.parse_args()

    bd = args.build_dir
    base = args.base_name

    # 1) Generate the .stage file
    stage_path = os.path.join(bd, f"{base}.stage")
    print(f" Creating stage file: {stage_path}")
    create_stage_file(
        catchment_location_csv=args.catchment_csv,
        selected_id=args.location_id,
        output_stage_file=stage_path
    )

    # 2) Generate .par files for each rainfall intensity
    print(" Generating .par files...")
    for total_precip in range(args.start, args.end + 1, args.step):
        par_path = os.path.join(bd, f"{base}_{total_precip}.par")
        create_par_file_60min(base, total_precip, par_path)

    print(" All .stage and .par files generated.")

if __name__ == "__main__":
    main()