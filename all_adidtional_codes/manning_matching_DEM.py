#!/usr/bin/env -S mamba run -n env_py311 python
import os
import argparse
import sys
import numpy as np
import rasterio
from rasterio.warp import reproject, Resampling

# Add src/ to Python path to import from DEM_processing if needed
sys.path.insert(0, os.path.abspath(os.path.join(__file__, "..", "..", "src")))

def rename_file_extension(filepath, new_ext):
    base = os.path.splitext(filepath)[0]
    new_path = base + new_ext
    os.rename(filepath, new_path)
    return new_path

def main():
    parser = argparse.ArgumentParser(description="Reproject and export Manning raster to .n ASCII format.")
    parser.add_argument("--dem", required=True, help="Path to the DEM GeoTIFF (reference grid)")
    parser.add_argument("--manning", required=True, help="Path to the Manning GeoTIFF (to be reprojected)")
    parser.add_argument("--output-folder", required=True, help="Output folder where .n file will be saved")
    parser.add_argument("--output-base", default="manning", help="Base name for output files (default: manning)")
    args = parser.parse_args()

    os.makedirs(args.output_folder, exist_ok=True)
    dem_path = args.dem
    manning_path = args.manning
    output_asc = os.path.join(args.output_folder, f"{args.output_base}.asc")

    # Load DEM (reference)
    with rasterio.open(dem_path) as dem:
        dem_profile = dem.profile
        dem_transform = dem.transform
        dem_crs = dem.crs
        width, height = dem.width, dem.height

    # Load and reproject Manning
    with rasterio.open(manning_path) as src:
        if src.crs != dem_crs or src.transform != dem_transform:
            data = np.empty((1, height, width), dtype=np.float32)
            reproject(
                source=rasterio.band(src, 1),
                destination=data[0],
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=dem_transform,
                dst_crs=dem_crs,
                resampling=Resampling.nearest
            )
        else:
            data = src.read()

    # Define invalid threshold for placeholder values (e.g., 1000.0 or above)
    threshold = 100.0  # adjust if needed
    nodata_value = -9999

    manning_raw = data[0]

    # Set invalid or NaN values to NODATA
    manning_cleaned = np.where(
        np.isnan(manning_raw) | (manning_raw > threshold),
        nodata_value,
        manning_raw
    )

    # Export directly to ASCII
    transform = dem_transform
    ncols = width
    nrows = height
    xllcorner = transform.c
    yllcorner = transform.f + transform.e * nrows
    cellsize = transform.a

    with open(output_asc, 'w') as f:
        f.write(f"ncols         {ncols}\n")
        f.write(f"nrows         {nrows}\n")
        f.write(f"xllcorner     {xllcorner:.6f}\n")
        f.write(f"yllcorner     {yllcorner:.6f}\n")
        f.write(f"cellsize      {cellsize:.6f}\n")
        f.write(f"NODATA_value  {nodata_value}\n")
        np.savetxt(f, manning_cleaned, fmt="%.3f")

    # Rename to .n
    manning_n_path = rename_file_extension(output_asc, ".n")

    print(f" Manning raster exported to .n file:\n - ASCII: {manning_n_path}")

if __name__ == "__main__":
    main()