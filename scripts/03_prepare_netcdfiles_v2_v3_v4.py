#!/usr/bin/env -S mamba run -n env_py311 python
import os
import argparse
import sys

# Add src/ to Python path
sys.path.insert(0, os.path.abspath(os.path.join(__file__, "..", "..", "src")))

from lisflood_inputdata import create_precip_automatic_camp_v2

def main():
    parser = argparse.ArgumentParser(description="Generate NetCDF rainfall scenarios for a case study.")
    parser.add_argument("--base-name", required=True, help="Base name for output files (e.g., 'Morges_2m_v2')")
    parser.add_argument("--dem-file", required=True, help="Path to the DEM file (e.g., *_perc999.tif)")
    parser.add_argument("--start", type=int, required=True, help="Start rainfall intensity in mm")
    parser.add_argument("--end", type=int, required=True, help="End rainfall intensity in mm")
    parser.add_argument("--step", type=int, default=5, help="Step size in mm (default: 5)")
    parser.add_argument("--output-dir", required=True, help="Output directory for NetCDF files")
    args = parser.parse_args()

    create_precip_automatic_camp_v2(
        base_name=args.base_name,
        dem_file_path=args.dem_file,
        buffer_start=args.start,
        buffer_end=args.end,
        buffer_step=args.step,
        output_dir=args.output_dir
    )

if __name__ == "__main__":
    main()