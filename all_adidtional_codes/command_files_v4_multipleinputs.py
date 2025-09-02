#!/usr/bin/env -S mamba run -n env_py311 python
import os
import sys
import argparse

# Add src/ to Python path
sys.path.insert(0, os.path.abspath(os.path.join(__file__, "..", "..", "src")))

from lisflood_inputdata import create_stage_file, write_bci_qfix_multiple
from DEM_processing import create_par_file_75min_bci

def main():
    parser = argparse.ArgumentParser(description="Generate .stage, .par, and .bci files for LISFLOOD scenarios.")
    parser.add_argument("--base-name", required=True, help="Base name, e.g., Morges_2m_v2")
    parser.add_argument("--build-dir", required=True, help="Output directory with the .dem file")
    parser.add_argument("--location-id", type=int, required=True, help="Catchment ID for stage file")
    parser.add_argument("--start", type=int, default=10, help="Start precipitation in mm/hr")
    parser.add_argument("--end", type=int, default=80, help="End precipitation in mm/hr")
    parser.add_argument("--step", type=int, default=10, help="Step of precipitation in mm/hr")
    parser.add_argument("--area", type=float, required=True, help="Catchment area in km^2")
    parser.add_argument("--runoff-C", type=float, required=True, help="Runoff coefficient C")

    # New arguments for multiple inflows/outflows
    parser.add_argument("--inflow", action="append", default=[],
                        help="Add inflow as: side,start,end,width (can be repeated)")
    parser.add_argument("--outflow", action="append", default=[],
                        help="Add outflow as: side,start,end (can be repeated)")

    args = parser.parse_args()

    base_name = args.base_name
    output_dir = args.build_dir

    dem_file_path = os.path.join(output_dir, f"{base_name}.dem")
    stage_file_path = os.path.join(output_dir, f"{base_name}.stage")
    catchment_location_csv = "/rs_scratch/users/ge24z347/Data_forprocess/catchment_location.csv"

    # 1. Create .stage file
    print(f"  Generating stage file at: {stage_file_path}")
    create_stage_file(catchment_location_csv, args.location_id, stage_file_path)

    # Parse inflows
    inflows = []
    for inflow_str in args.inflow:
        side, start, end, width = inflow_str.split(",")
        inflows.append({
            "side": side.strip(),
            "start": float(start),
            "end": float(end),
            "width": float(width)
        })

    # Parse outflows
    outflows = []
    for outflow_str in args.outflow:
        side, start, end = outflow_str.split(",")
        outflows.append({
            "side": side.strip(),
            "start": float(start),
            "end": float(end)
        })

    # 2. Create .par and .bci files
    print(" Generating .par and .bci files...")
    for total_precip in range(args.start, args.end + 1, args.step):
        par_path = os.path.join(output_dir, f"{base_name}_{total_precip}.par")
        bci_path = os.path.join(output_dir, f"{base_name}_{total_precip}.bci")

        create_par_file_75min_bci(base_name, total_precip, par_path)

        write_bci_qfix_multiple(
            output_path=bci_path,
            rain_mm_per_hr=total_precip,
            runoff_coefficient=args.runoff_C,
            area_km2=args.area,
            inflows=inflows,
            outflows=outflows
        )

        print(f"  Created: {par_path} and {bci_path}")

    print("\n All .stage, .par, and .bci files generated.")


if __name__ == "__main__":
    main()