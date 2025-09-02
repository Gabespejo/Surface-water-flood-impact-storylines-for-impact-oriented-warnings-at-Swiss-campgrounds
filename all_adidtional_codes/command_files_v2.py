#!/usr/bin/env -S mamba run -n env_py311 python
import os
import sys
import argparse

# Add src/ to Python path
sys.path.insert(0, os.path.abspath(os.path.join(__file__, "..", "..", "src")))

from lisflood_inputdata import create_stage_file
from DEM_processing import create_par_file_75min

def main():
    parser = argparse.ArgumentParser(description="Generate .stage and .par files for LISFLOOD scenarios.")
    parser.add_argument("--base-name", required=True, help="Base name, e.g., Morges_2m_v2")
    parser.add_argument("--build-dir", required=True, help="Output directory with the .dem file")
    parser.add_argument("--location-id", type=int, required=True, help="Catchment ID for stage file")
    parser.add_argument("--start", type=int, default=5, help="Start precipitation in mm")
    parser.add_argument("--end", type=int, default=75, help="End precipitation in mm")
    parser.add_argument("--step", type=int, default=10, help="Step of precipitation in mm")
    args = parser.parse_args()

    base_name = args.base_name
    output_dir = args.build_dir

    # Path to input files
    dem_file_path = os.path.join(output_dir, f"{base_name}.dem")
    stage_file_path = os.path.join(output_dir, f"{base_name}.stage")
    catchment_location_csv = "/rs_scratch/users/ge24z347/Data_forprocess/catchment_location.csv"

    # 1. Create .stage file
    print(f"  Generating stage file at: {stage_file_path}")
    create_stage_file(catchment_location_csv, args.location_id, stage_file_path)

    # 2. Create .par files for each rainfall intensity
    print(" Generating .par files...")
    for total_precip in range(args.start, args.end + 1, args.step):
        output_par = os.path.join(output_dir, f"{base_name}_{total_precip}.par")
        create_par_file_75min(base_name, total_precip, output_par)
        print(f"  Created: {output_par}")

    print(" All .stage and .par files generated.")

if __name__ == "__main__":
    main()