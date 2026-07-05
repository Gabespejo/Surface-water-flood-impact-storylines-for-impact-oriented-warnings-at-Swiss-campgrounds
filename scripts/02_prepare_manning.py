#!/usr/bin/env -S mamba run -n env_py311 python
import os
import sys
import argparse
import geopandas as gpd
import rasterio

# Add src/ to Python path
sys.path.insert(0, os.path.abspath(os.path.join(__file__, "..", "..", "src")))

from DEM_processing import (
    geopackage_to_raster,
    clip_raster_to_bbox,
    resample_raster,
    convert_tif_to_asc,
    rename_file_extension,
)

# Manning-n lookup table
MANNING = {
    11: 0.033, 12: 0.200, 13: 0.200, 14: 0.100, 15: 0.100, 16: 0.100, 17: 0.100,
    21: 0.160, 31: 0.160, 32: 0.259, 33: 0.160, 34: 0.160, 35: 0.100,
    41: 0.200, 42: 0.200, 43: 0.200, 44: 0.200, 45: 0.200, 46: 0.200, 47: 0.100,
    51: 0.040, 52: 0.120, 53: 0.120, 61: 0.030, 62: 0.025, 63: 0.060, 64: 0.060,
}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--areal-gpkg", required=True)
    parser.add_argument("--code-field", default="LC_27")
    parser.add_argument("--work-folder", required=True)
    parser.add_argument("--output-n", required=True)
    parser.add_argument("--res-2m", type=float, default=2.0)
    args = parser.parse_args()

    os.makedirs(args.work_folder, exist_ok=True)

    # Derive DEM path from output filename
    base_name = os.path.splitext(os.path.basename(args.output_n))[0]  # e.g., Morges_2m
    build_folder = os.path.dirname(args.output_n)
    dem_path = os.path.join(build_folder, f"{base_name}.tif")

    if not os.path.exists(dem_path):
        raise FileNotFoundError(f"DEM file not found at: {dem_path}")

    # Load bounding box directly from DEM
    with rasterio.open(dem_path) as dem_src:
        bounds = dem_src.bounds
        xmin, ymin, xmax, ymax = bounds.left, bounds.bottom, bounds.right, bounds.top
        transform = dem_src.transform
        width = dem_src.width
        height = dem_src.height
        crs = dem_src.crs
        print(f" Loaded DEM bounds: {xmin}, {ymin}, {xmax}, {ymax}")
        print(f" DEM size: {width} x {height} | cellsize: {transform.a} | CRS: {crs}")

    # Load Arealstatistik and assign Manning values
    gdf = gpd.read_file(args.areal_gpkg)
    target_field = args.code_field + "_manning"
    gdf[target_field] = gdf[args.code_field].map(MANNING)

    # Output naming
    areal_prefix = os.path.join(build_folder, f"{base_name}_areal")
    tif100  = areal_prefix + "_100m.tif"
    clipped = areal_prefix + "_clip.tif"
    tif2m   = areal_prefix + ".tif"
    asc     = areal_prefix + ".asc"
    final_n = args.output_n

    # Step 1: Rasterize at 100 m
    print(" Rasterizing Arealstatistik...")
    geopackage_to_raster(gdf, target_field, tif100, resolution=100)

    # Step 2: Clip to DEM bounding box
    print(" Clipping to DEM bounds...")
    clip_raster_to_bbox(
        input_raster=tif100,
        output_raster=clipped,
        bbox=(xmin, ymin, xmax, ymax),
        bbox_crs="EPSG:2056"
    )

    # Step 3: Resample to match DEM grid exactly
    print(" Resampling to DEM grid...")
    resample_raster(
        input_raster=clipped,
        output_raster=tif2m,
        target_resolution=args.res_2m,
        resampling_method="nearest",
        target_transform=transform,
        target_width=width,
        target_height=height,
        target_crs=crs
    )

    # Step 4: Convert to .asc and rename to .n
    convert_tif_to_asc(tif2m, asc, desired_nodata_value=-9999)
    rename_file_extension(asc, ".n")
    manning_n = asc.replace(".asc", ".n")

    # Step 5: Move to final .n location
    if os.path.exists(manning_n):
        if os.path.exists(final_n):
            os.remove(final_n)
        os.rename(manning_n, final_n)
        print(f" Manning .n file saved to: {final_n}")
    else:
        raise FileNotFoundError(f"Converted .n file not found: {manning_n}")


if __name__ == "__main__":
    main()