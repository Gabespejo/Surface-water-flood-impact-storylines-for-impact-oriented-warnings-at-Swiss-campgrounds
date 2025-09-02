#!/usr/bin/env -S mamba run -n env_py311 python
import os
import sys
import argparse

# make sure your src/ folder is on PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(__file__, "..", "..", "src")))

import DEM_processing
from DEM_processing import convert_tif_to_asc, rename_file_extension

def main():
    parser = argparse.ArgumentParser(
        description="1) extract & merge DEM tiles, 2) convert to ASCII, 3) rename to .dem, 4) clean up"
    )
    parser.add_argument("--location-csv", required=True,
                        help="CSV with ID, East_X, North_Y")
    parser.add_argument("--dem-folder", required=True,
                        help="Folder containing the 2 m DEM tiles")
    parser.add_argument("--work-folder", required=True,
                        help="Temporary folder to copy & merge tiles into")
    parser.add_argument("--output-dem", required=True,
                        help="Final .dem path (after .asc → .dem rename)")
    parser.add_argument("--location-id", type=int, default=2,
                        help="ID in the CSV for which to extract the DEM")
    parser.add_argument("--width", type=int, default=2000,
                        help="Number of DEM columns (at DEM resolution)")
    parser.add_argument("--height", type=int, default=2000,
                        help="Number of DEM rows (at DEM resolution)")
    parser.add_argument("--resolution", type=float, default=2.0,
                        help="DEM resolution in meters")
    args = parser.parse_args()

    # 1) cut & merge
    bounds = DEM_processing.extract_auto_matched_rasters(
        location_csv   = args.location_csv,
        dem_folder     = args.dem_folder,
        output_folder  = args.work_folder,
        location_id    = args.location_id,
        target_width   = args.width,
        target_height  = args.height,
        resolution     = args.resolution
    )
    merged_tif = args.output_dem.replace(".dem", ".tif")
    DEM_processing.merge_dem_rasters(
        input_folder = args.work_folder,
        output_file  = merged_tif,
        bounds       = bounds
    )

    # 2) convert to Esri ASCII (.asc)
    asc_file = merged_tif.replace(".tif", ".asc")
    convert_tif_to_asc(
        dem_tif              = merged_tif,
        output_asc           = asc_file,
        desired_nodata_value = -9999
    )

    # 3) rename .asc → .dem
    rename_file_extension(
        input_file_path = asc_file,
        new_extension   = ".dem"
    )

    # 4) delete only the temporary .asc
    if os.path.exists(asc_file):
        os.remove(asc_file)
        print(f"Deleted temporary ASCII file: {asc_file}")
    else:
        print(f"No temporary .asc found to delete at: {asc_file}")

    # 5) write DEM bounds out for the next script
    bounds_path = args.output_dem.replace(".dem", "_4km_bounds.txt")
    with open(bounds_path, "w") as f:
        # bounds is a tuple: (minx, miny, maxx, maxy)
        f.write(",".join(str(b) for b in bounds))
    print(f"Saved DEM bounds to {bounds_path}")

if __name__ == "__main__":
    main()