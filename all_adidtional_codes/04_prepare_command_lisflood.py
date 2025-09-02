#!/usr/bin/env -S mamba run -n env_py311 python
import os, sys, argparse

# point src/ at your modules
sys.path.insert(0, os.path.abspath(os.path.join(__file__, "..", "..", "src")))

from lisflood_inputdata import (
    copy_and_rename_n_file,
    copy_and_rename_dem_file,
    various_stage_files_quadratic,
    various_par_files_camp
)

def main():
    p = argparse.ArgumentParser(
        description="Auto-generate LISFLOOD scenario files (.n, .dem, .stage, .par)"
    )
    p.add_argument("--build-dir", required=True,
                   help="Directory where base .n and .dem files live and scenario files will be written")
    p.add_argument("--base-name", required=True,
                   help="Base name for files, e.g. 'Gordevio_2m', 'Salavaux_2m'")
    p.add_argument("--location-id", type=int, default=2,
                   help="Location ID for generating .stage files")
    p.add_argument("--start", type=int, default=1,
                   help="First scenario index")
    p.add_argument("--end", type=int, default=11,
                   help="Last scenario index (inclusive)")
    p.add_argument("--step", type=int, default=1,
                   help="Step between scenario indices")
    args = p.parse_args()

    bd = args.build_dir
    base = args.base_name

    # Correct CSV path for catchment location file
    catchment_location_csv = "/rs_scratch/users/ge24z347/Data_forprocess/catchment_location.csv"

    # 1) Copy & rename the .n and .dem files
    copy_and_rename_n_file(
        base_file=os.path.join(bd, f"{base}.n"),
        output_dir=bd,
        start=args.start,
        end=args.end,
        step=args.step
    )

    copy_and_rename_dem_file(
        base_file=os.path.join(bd, f"{base}.dem"),
        output_dir=bd,
        start=args.start,
        end=args.end,
        step=args.step
    )

    # 2) Generate .stage files
    various_stage_files_quadratic(
        dem_file_path=os.path.join(bd, f"{base}.dem"),
        selected_id=args.location_id,
        buffer_start=args.start,
        buffer_end=args.end,
        buffer_step=args.step,
        num_points=1,
        catchment_location_csv=catchment_location_csv  #  Passed explicitly
    )

    # 3) Generate .par files using your custom logic
    various_par_files_camp(
        dem_file_path=os.path.join(bd, f"{base}.dem"),
        buffer_start=args.start,
        buffer_end=args.end,
        buffer_step=args.step
    )

    print(" All scenarios generated.")

if __name__ == "__main__":
    main()