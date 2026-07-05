#!/usr/bin/env -S mamba run -n env_py311 python
import os, sys, argparse
sys.path.insert(0, os.path.abspath(os.path.join(__file__, "..", "..", "src")))

from lisflood_inputdata import create_stage_file, write_bci_qflex
from DEM_processing import create_par_file_75min_bci


def _norm_version(v: str) -> str:
    if not v:
        return ""
    return v if v.startswith("_") else f"_{v}"


def main():
    parser = argparse.ArgumentParser(
        description="Generate .stage, .par, and .bci files using optional inflow discharge (Q_m3s)."
    )
    # Basic metadata
    parser.add_argument("--base-name", required=True, help="Base name without version, e.g. Aaregg_2m")
    parser.add_argument("--version", default="", help="Version suffix like v4 or _v4 (optional)")
    parser.add_argument("--build-dir", required=True, help="Output directory")
    parser.add_argument("--location-id", type=int, required=True)

    # Rainfall loop
    parser.add_argument("--start", type=int, default=10)
    parser.add_argument("--end", type=int, default=80)
    parser.add_argument("--step", type=int, default=10)

    # ➕ NEW: CFL number for the par file
    parser.add_argument(
        "--cfl",
        type=float,
        required=True,
        help="CFL number to write into the .par file (e.g. 0.5, 0.7)"
    )

    # Optional inflows
    parser.add_argument("--q-m3s", type=float)
    parser.add_argument("--cell-size", type=float)
    parser.add_argument("--point-inflow", nargs=2, type=float, action="append",
                        help="Repeatable: --point-inflow X Y")
    parser.add_argument("--line-inflow", nargs=3, action="append",
                        help="Repeatable: --line-inflow SIDE START END")

    # Outflow (unchanged: still required)
    parser.add_argument("--outflow-side", type=str, default="E")
    parser.add_argument("--outflow-start", type=float, required=True)
    parser.add_argument("--outflow-end", type=float, required=True)
    parser.add_argument("--outflow-slope", type=float)

    args = parser.parse_args()

    version_suffix = _norm_version(args.version)            # "" or like "_v4"
    name_stem = f"{args.base_name}{version_suffix}"         # e.g. Aaregg_2m_v4

    outdir = args.build_dir
    os.makedirs(outdir, exist_ok=True)

    stage_file_path = os.path.join(outdir, f"{name_stem}.stage")
    catchment_location_csv = "/rs_scratch/users/ge24z347/Data_forprocess/catchment_location.csv"

    print(f"Generating stage file at: {stage_file_path}")
    create_stage_file(catchment_location_csv, args.location_id, stage_file_path)

    # Prepare inflows
    point_inflows = args.point_inflow if args.point_inflow else None
    line_inflows = None
    if args.line_inflow:
        line_inflows = [{"side": str(s), "start": float(a), "end": float(b)} for (s, a, b) in args.line_inflow]

    print("Generating .par and .bci files...")
    for rain in range(args.start, args.end + 1, args.step):
        par_path = os.path.join(outdir, f"{name_stem}_{rain}.par")
        bci_path = os.path.join(outdir, f"{name_stem}_{rain}.bci")

        # Use versioned stem inside the par, too + pass CFL
        create_par_file_75min_bci(
            base_name=name_stem,
            total_precipitation=rain,
            cfl=args.cfl,
            output_file_path=par_path
        )

        write_bci_qflex(
            output_path=bci_path,
            # robust access to q_m3s (same idea as before)
            Q_m3s=getattr(args, "q_m3s", None),
            cell_size=args.cell_size,
            point_inflows=point_inflows,
            line_inflows=line_inflows,
            outflow_side=args.outflow_side,
            outflow_start=args.outflow_start,
            outflow_end=args.outflow_end,
            outflow_slope=args.outflow_slope
        )

        print(f"Created: {par_path} and {bci_path}")

    print("\nAll .stage, .par, and .bci files generated.")


if __name__ == "__main__":
    main()

