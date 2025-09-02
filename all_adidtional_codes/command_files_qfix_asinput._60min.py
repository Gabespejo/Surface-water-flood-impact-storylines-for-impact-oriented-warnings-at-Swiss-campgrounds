#!/usr/bin/env -S mamba run -n env_py311 python
import os
import sys
import argparse

# Add src/ to Python path
sys.path.insert(0, os.path.abspath(os.path.join(__file__, "..", "..", "src")))

from lisflood_inputdata import create_stage_file, write_bci_qfix_asinput
from DEM_processing import create_par_file_60min_bci


def main():
    parser = argparse.ArgumentParser(description="Generate .stage, .par, and .bci files using optional inflow discharge (Q_m3s).")
    
    # Basic metadata
    parser.add_argument("--base-name", required=True, help="Base name, e.g., Morges_2m_v2")
    parser.add_argument("--build-dir", required=True, help="Output directory with the .dem file")
    parser.add_argument("--location-id", type=int, required=True, help="Catchment ID for stage file")
    
    # Rainfall loop
    parser.add_argument("--start", type=int, default=10, help="Start precipitation in mm/hr")
    parser.add_argument("--end", type=int, default=80, help="End precipitation in mm/hr")
    parser.add_argument("--step", type=int, default=10, help="Step of precipitation in mm/hr")
    
    # Optional inflow discharge parameters
    parser.add_argument("--q-m3s", type=float, help="Total inflow discharge in m³/s (Q_m3s)")
    parser.add_argument("--width", type=float, help="Width of inflow boundary in meters")
    parser.add_argument("--inflow-start", type=float, help="Inflow start coordinate")
    parser.add_argument("--inflow-end", type=float, help="Inflow end coordinate")
    parser.add_argument("--inflow-side", type=str, default="W", help="Inflow side: N, S, E, or W")

    # Outflow parameters (always required)
    parser.add_argument("--outflow-start", type=float, required=True, help="Outflow start coordinate")
    parser.add_argument("--outflow-end", type=float, required=True, help="Outflow end coordinate")
    parser.add_argument("--outflow-side", type=str, default="E", help="Outflow side: N, S, E, or W")

    args = parser.parse_args()

    base_name = args.base_name
    output_dir = args.build_dir

    dem_file_path = os.path.join(output_dir, f"{base_name}.dem")
    stage_file_path = os.path.join(output_dir, f"{base_name}.stage")
    catchment_location_csv = "/rs_scratch/users/ge24z347/Data_forprocess/catchment_location.csv"

    # 1. Create .stage file
    print(f"  Generating stage file at: {stage_file_path}")
    create_stage_file(catchment_location_csv, args.location_id, stage_file_path)

    # 2. Generate .par and .bci for each rainfall scenario
    print(" Generating .par and .bci files...")
    for total_precip in range(args.start, args.end + 1, args.step):
        par_path = os.path.join(output_dir, f"{base_name}_{total_precip}.par")
        bci_path = os.path.join(output_dir, f"{base_name}_{total_precip}.bci")

        create_par_file_60min_bci(base_name, total_precip, par_path)

        # If inflow parameters are all provided → include QFIX inflow
        if all(v is not None for v in [args.q_m3s, args.inflow_start, args.inflow_end, args.width]):
            write_bci_qfix_asinput(
                output_path=bci_path,
                Q_m3s=args.q_m3s,
                inflow_start=args.inflow_start,
                inflow_end=args.inflow_end,
                outflow_start=args.outflow_start,
                outflow_end=args.outflow_end,
                width_m=args.width,
                inflow_side=args.inflow_side,
                outflow_side=args.outflow_side
            )
        else:
            # Only outflow
            with open(bci_path, "w") as f:
                f.write(f"{args.outflow_side} {args.outflow_start:.3f} {args.outflow_end:.3f} FREE\n")
            print(f"  .bci file created at {bci_path} with only outflow.")

        print(f"  Created: {par_path} and {bci_path}")

    print("\n All .stage, .par, and .bci files generated.")


if __name__ == "__main__":
    main()