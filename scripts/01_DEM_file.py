#!/usr/bin/env -S mamba run -n env_py311 python
import os
import sys
import argparse
import rasterio

# Add src/ to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(__file__, "..", "..", "src")))

from DEM_processing import convert_tif_to_asc, rename_file_extension

def main():
    parser = argparse.ArgumentParser(description="Convert DEM .tif to .dem and extract bounds")
    parser.add_argument("--input-tif", required=True, help="Input DEM in .tif format")
    parser.add_argument("--output-dem", required=True, help="Final output .dem path")
    args = parser.parse_args()

    input_tif = args.input_tif
    output_dem = args.output_dem
    asc_file = output_dem.replace(".dem", ".asc")

    # Step 1: Read and save bounds
    with rasterio.open(input_tif) as src:
        bounds = src.bounds  # (left, bottom, right, top)
        bounds_path = output_dem.replace(".dem", "_bounds.txt")
        with open(bounds_path, "w") as f:
            f.write(f"{bounds.left},{bounds.bottom},{bounds.right},{bounds.top}")
        print(f" Bounds saved to: {bounds_path}")

    # Step 2: Convert .tif to .asc
    print(f" Converting {input_tif} to {asc_file}")
    convert_tif_to_asc(input_tif, asc_file, desired_nodata_value=-9999)

    # Step 3: Rename .asc to .dem
    print(f" Renaming {asc_file} to {output_dem}")
    rename_file_extension(asc_file, ".dem")

    # Step 4: Delete the .asc file
    if os.path.exists(asc_file):
        os.remove(asc_file)
        print(f" Deleted temporary ASCII file: {asc_file}")
    else:
        print(f" No temporary .asc file found to delete.")

    print(" DEM conversion complete.")

if __name__ == "__main__":
    main()