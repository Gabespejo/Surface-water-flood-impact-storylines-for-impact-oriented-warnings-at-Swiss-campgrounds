#!/usr/bin/env -S mamba run -n env_py311 python

import os
import argparse
import sys

# make sure we can import your plotting function
sys.path.insert(0, "/storage/homefs/ge24z347/Campgrounds/src")
from flow_depth_plotting import g_plot_maxwd_swissTLM_nocatchment_zoomed_nolake


def parse_extent(extent_str: str):
    """
    Parse --extent "xmin,xmax,ymin,ymax" into a 4-tuple of floats.
    """
    parts = [p.strip() for p in extent_str.split(",")]
    if len(parts) != 4:
        raise ValueError("--extent must have four comma-separated numbers: xmin,xmax,ymin,ymax")
    try:
        xmin, xmax, ymin, ymax = map(float, parts)
    except ValueError:
        raise ValueError("--extent values must be numeric.")
    if xmax <= xmin or ymax <= ymin:
        raise ValueError("--extent must satisfy xmax>xmin and ymax>ymin.")
    return (xmin, xmax, ymin, ymax)


def main():
    parser = argparse.ArgumentParser(description="Plot LISFLOOD max depth maps for multiple scenarios")
    parser.add_argument("--location-name", required=True, help="Location name (e.g., Gordevio)")
    parser.add_argument("--version", default="", help="Version suffix (e.g., v2, v4). Accepts forms like 'v2', '_v2', 'v2_'.")
    parser.add_argument("--duration", required=True, help="Rainfall duration (e.g., 60min or 75min)")
    parser.add_argument("--start", type=int, default=10, help="Start of rainfall intensity (e.g., 10)")
    parser.add_argument("--end", type=int, default=120, help="End of rainfall intensity (exclusive, e.g., 120)")
    parser.add_argument("--step", type=int, default=10, help="Step of rainfall intensity (e.g., 10)")
    parser.add_argument("--output-folder", required=True, help="Folder to save all plots")

    # Optional overlays
    parser.add_argument("--use-catchments", action="store_true", help="Enable catchment overlay")
    parser.add_argument("--geo-shape", default=None, help="Path to shapefile for catchment overlay (required if --use-catchments)")

    # Lake + campground
    parser.add_argument("--lake-shape", default=None,
                        help="Path to lake shapefile/polygon layer.")
    parser.add_argument("--lake-name", default=None,
                        help="Lake name in field 'gewaessername', e.g. 'Léman'")
    parser.add_argument("--campground-shape", default=None,
                        help="Path to campground shapefile/polygon layer to highlight.")
    parser.add_argument("--campground-edgecolor", default="magenta",
                        help="Boundary color for campground polygon (default: magenta)")
    parser.add_argument("--campground-linewidth", type=float, default=2.0,
                        help="Line width for campground polygon boundary (default: 2.0)")

    # Zoom controls
    parser.add_argument("--extent", default=None,
                        help='Zoom bbox "xmin,xmax,ymin,ymax" in meters (or km if --extent-units=km). '
                             "If provided, filenames include _zoom (handled by the plotter).")
    parser.add_argument("--extent-units", choices=["auto", "m", "km"], default="m",
                        help="Units for --extent (default: m). 'auto' will guess based on magnitude.")
    parser.add_argument("--also-full", action="store_true",
                        help="If set with --extent, also render a full-extent map for each scenario.")

    # Render quality
    parser.add_argument("--target-pixel-size", type=float, default=None,
                        help="Overlay render grid (m/px). If omitted, uses DEM native res.")
    parser.add_argument("--bg-layer", default="ch.swisstopo.swisstlm3d-karte-grau",
                        help="Swisstopo WMS layer (default: ch.swisstopo.swisstlm3d-karte-grau).")
    parser.add_argument("--bg-pixel-size", type=float, default=1.0,
                        help="Basemap pixel size (m/px). 0.5–2.0 is a good range.")
    parser.add_argument("--bg-dpi", type=int, default=96,
                        help="WMS DPI hint (96/192/256).")
    parser.add_argument("--bg-max-px", type=int, default=4096,
                        help="Per-tile max pixels for WMS requests.")

    args = parser.parse_args()

    # Validate catchments
    if args.use_catchments and not args.geo_shape:
        parser.error("--use-catchments set but --geo-shape not provided.")

    if args.lake_shape and not os.path.exists(args.lake_shape):
        parser.error(f"--lake-shape not found: {args.lake_shape}")

    if args.campground_shape and not os.path.exists(args.campground_shape):
        parser.error(f"--campground-shape not found: {args.campground_shape}")

    # Clean version string to avoid double underscores
    version_clean = args.version.strip("_")
    if version_clean:
        base_name = f"{args.location_name}_2m_{version_clean}"
    else:
        base_name = f"{args.location_name}_2m"

    # Paths
    dem_file = f"/storage/homefs/ge24z347/LISFLOOD_FP_8_1/build/{base_name}/{base_name}.dem"
    simulation_base = "/storage/homefs/ge24z347/LISFLOOD_FP_8_1/build"
    os.makedirs(args.output_folder, exist_ok=True)

    if not os.path.exists(dem_file):
        parser.error(f"DEM file not found: {dem_file}")

    # Parse extent if provided
    zoom_extent = parse_extent(args.extent) if args.extent else None

    # Loop scenarios
    for rain in range(args.start, args.end, args.step):
        fv1_folder = f"{base_name}_{rain}_fv1-gpu"
        max_file = os.path.join(
            simulation_base,
            base_name,
            fv1_folder,
            f"{base_name}_{args.duration}_{rain}.max"
        )

        if not os.path.exists(max_file):
            print(f"Missing: {max_file} — skipping.")
            continue

        print(f"Plotting {rain} mm/h...")

        # Zoomed map
        if zoom_extent is not None:
            g_plot_maxwd_swissTLM_nocatchment_zoomed_nolake(
                dem_file=dem_file,
                max_file=max_file,
                plot_output_folder=args.output_folder,
                location_name=args.location_name,
                rain_intensity=f"{rain} mm/h",
                use_catchments=args.use_catchments,
                geo_ezgg_2km_ge=args.geo_shape,
                extent=zoom_extent,
                extent_units=args.extent_units,
                target_pixel_size=args.target_pixel_size,
                bg_layer=args.bg_layer,
                bg_pixel_size=args.bg_pixel_size,
                bg_max_px=args.bg_max_px,
                bg_dpi=args.bg_dpi,
                lake_shapefile=args.lake_shape,
                lake_name=args.lake_name,
                campground_shapefile=args.campground_shape,
                campground_edgecolor=args.campground_edgecolor,
                campground_linewidth=args.campground_linewidth,
            )

            if args.also_full:
                g_plot_maxwd_swissTLM_nocatchment_zoomed_nolake(
                    dem_file=dem_file,
                    max_file=max_file,
                    plot_output_folder=args.output_folder,
                    location_name=args.location_name,
                    rain_intensity=f"{rain} mm/h",
                    use_catchments=args.use_catchments,
                    geo_ezgg_2km_ge=args.geo_shape,
                    extent=None,
                    target_pixel_size=args.target_pixel_size,
                    bg_layer=args.bg_layer,
                    bg_pixel_size=args.bg_pixel_size,
                    bg_max_px=args.bg_max_px,
                    bg_dpi=args.bg_dpi,
                    lake_shapefile=args.lake_shape,
                    lake_name=args.lake_name,
                    campground_shapefile=args.campground_shape,
                    campground_edgecolor=args.campground_edgecolor,
                    campground_linewidth=args.campground_linewidth,
                )

        else:
            g_plot_maxwd_swissTLM_nocatchment_zoomed_nolake(
                dem_file=dem_file,
                max_file=max_file,
                plot_output_folder=args.output_folder,
                location_name=args.location_name,
                rain_intensity=f"{rain} mm/h",
                use_catchments=args.use_catchments,
                geo_ezgg_2km_ge=args.geo_shape,
                extent=None,
                target_pixel_size=args.target_pixel_size,
                bg_layer=args.bg_layer,
                bg_pixel_size=args.bg_pixel_size,
                bg_max_px=args.bg_max_px,
                bg_dpi=args.bg_dpi,
                lake_shapefile=args.lake_shape,
                lake_name=args.lake_name,
                campground_shapefile=args.campground_shape,
                campground_edgecolor=args.campground_edgecolor,
                campground_linewidth=args.campground_linewidth,
            )

    print(f"\nAll plots saved in: {args.output_folder}")


if __name__ == "__main__":
    main()