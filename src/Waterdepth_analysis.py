
########## Functions Analysis water depth ######################
################################################################

import os
import glob
import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio.mask import mask
# from shapely.geometry import mapping  # optional; shapely geometry usually works directly

def _pick_max_file(raster_base_folder: str, raster_prefix: str, mm: int, duration: str) -> str | None:
    """
    Return the path to the .max raster for the given scenario (mm).
    Tries the provided duration tag first (e.g., 60min/75min/1h),
    then falls back to common tags, then a generic glob.
    """
    run_dir = os.path.join(raster_base_folder, f"{raster_prefix}_{mm}_fv1-gpu")

    # 1) try requested duration
    candidates = [os.path.join(run_dir, f"{raster_prefix}_{duration}_{mm}.max")]

    # 2) fallbacks (don’t duplicate requested)
    for alt in ("1h", "60min", "75min"):
        if alt != duration:
            candidates.append(os.path.join(run_dir, f"{raster_prefix}_{alt}_{mm}.max"))

    for c in candidates:
        if os.path.exists(c):
            return c

    # 3) last resort: any *_<mm>.max that starts with prefix
    matches = sorted(glob.glob(os.path.join(run_dir, f"{raster_prefix}_*_{mm}.max")))
    return matches[0] if matches else None


def calculate_flooded_area_by_scenarios_fv1(
    geojson_file,
    polygon_column_name,
    polygon_name,
    raster_base_folder,
    raster_prefix,
    scenarios,
    min_depth_threshold=0.05,
    duration="60min",   # <<< NEW: pass "60min", "75min", or "1h"
):
    """
    Calculate flooded area and percentage inside a selected polygon across multiple rainfall scenarios.
    """
    gdf = gpd.read_file(geojson_file)

    # Normalize and match polygon name
    gdf["__cmp"] = gdf[polygon_column_name].str.strip().str.lower()
    polygon_name_clean = polygon_name.strip().lower()
    selected_polygon = gdf[gdf["__cmp"] == polygon_name_clean]

    if selected_polygon.empty:
        available = gdf["__cmp"].unique()
        raise ValueError(
            f"❌ Polygon with name '{polygon_name}' not found in the GeoJSON.\n"
            f"🧩 Available (normalized) names: {available}"
        )

    geometry = selected_polygon.geometry.values[0]
    total_area_m2 = selected_polygon["area_polygon_campingsite"].values[0]
    gdf.drop(columns="__cmp", inplace=True)

    results = []
    any_found = False

    for mm in scenarios:
        raster_file = _pick_max_file(raster_base_folder, raster_prefix, mm, duration)

        if not raster_file or not os.path.exists(raster_file):
            print(f"Warning: Raster file not found for {mm} mm (looked in {raster_base_folder})")
            # keep x-axis continuity (optional): write NaN
            results.append({
                "Precipitation (mm/h)": mm,
                "Total Area (m²)": total_area_m2,
                "Flooded Area (m²)": np.nan,
                "Flooded Area (%)": np.nan
            })
            continue

        any_found = True
        with rasterio.open(raster_file) as src:
            out_image, out_transform = mask(src, [geometry], crop=True)
            flooded = out_image[0]

        flooded = np.where(flooded >= min_depth_threshold, 1, 0)
        pixel_area = abs(out_transform[0] * out_transform[4])
        flooded_area_m2 = float(np.sum(flooded) * pixel_area)
        flooded_area_percent = (flooded_area_m2 / total_area_m2) * 100.0

        results.append({
            "Precipitation (mm/h)": mm,
            "Total Area (m²)": total_area_m2,
            "Flooded Area (m²)": flooded_area_m2,
            "Flooded Area (%)": flooded_area_percent
        })

    df = pd.DataFrame(results)

    if not any_found:
        raise FileNotFoundError(
            f"No rasters found for any scenario with prefix '{raster_prefix}' and duration '{duration}'. "
            f"Checked under: {raster_base_folder}"
        )

    return df


##########################################################################################

def plot_flooded_area_two_versions(
    df_v2,
    df_v4,
    case_name=None,  # kept for compatibility, not used
    label_v2="S1",
    label_v4="S2",
    output_path=None,
    show=True,
    dpi=300,
):
    """
    Two-version flooded area plot (clean, paper-ready):
      - Transparent background
      - No title
      - No grid
      - Colors matching your stacked-bar palette (light teal / dark teal)
    Expects columns:
      - 'Precipitation (mm/h)'
      - 'Flooded Area (%)'
    """

    import os
    import pandas as pd
    import matplotlib.pyplot as plt

    # --- Colors chosen to match your figure palette ---
    c_v2 = "#dff2f1"   # light teal
    c_v4 = "#00796b"   # dark teal

    # Align on precipitation so both curves share the same x-axis points
    a = df_v2[["Precipitation (mm/h)", "Flooded Area (%)"]].rename(
        columns={"Flooded Area (%)": "v2"}
    ).copy()

    b = df_v4[["Precipitation (mm/h)", "Flooded Area (%)"]].rename(
        columns={"Flooded Area (%)": "v4"}
    ).copy()

    m = pd.merge(a, b, on="Precipitation (mm/h)", how="inner").sort_values(
        "Precipitation (mm/h)"
    )

    if m.empty:
        raise ValueError("No matching precipitation values between v2 and v4 CSVs.")

    x = m["Precipitation (mm/h)"].values
    y2 = m["v2"].values
    y4 = m["v4"].values

    fig, ax = plt.subplots(figsize=(10, 6))

    # Transparent backgrounds
    fig.patch.set_alpha(0.0)
    ax.set_facecolor((1, 1, 1, 0))

    # Lines
    ax.plot(
        x, y2,
        marker="s",
        linewidth=2,
        markersize=6,
        color=c_v2,
        markerfacecolor=c_v2,
        markeredgecolor=c_v2,
        label=label_v2
    )

    ax.plot(
        x, y4,
        marker="s",
        linewidth=2,
        markersize=6,
        color=c_v4,
        markerfacecolor=c_v4,
        markeredgecolor=c_v4,
        label=label_v4
    )

    # Optional shaded gap
    ax.fill_between(x, y2, y4, alpha=0.12, color=c_v4, label="Δ")

    # Labels only (no title)
    ax.set_xlabel("precipitation (mm/h)")
    ax.set_ylabel("Flooded Area (%)")

    # No grid
    ax.grid(False)

    # --- CLEANER AXIS STYLE ---
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    # ⭐ BIGGER TICKS (your requested change)
    ax.tick_params(axis="both", labelsize=14, length=4, width=1)

    # Legend
    ax.legend(frameon=False, loc="best")

    plt.tight_layout()

    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        fig.savefig(output_path, dpi=dpi, transparent=True)
        if not show:
            plt.close(fig)

    if show:
        plt.show()

    return m

####################################################################################################

def plot_flooded_area_fv1(df_flooded, case_name, output_folder=None):
    """
    Plot flooded area percentage vs precipitation for FV1 solver and optionally save the plot.

    Parameters:
        df_flooded (pd.DataFrame): DataFrame with columns 'Precipitation (mm/h)' and 'Flooded Area (%)'.
        case_name (str): Name of the case (e.g., GORDEVIO or SALAVAUX) to be used in the title.
        output_folder (str, optional): Path to save the figure (e.g., /path/to/folder). If None, only shows.
    """
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(10, 6))

    # Plot FV1 line
    ax.plot(
        df_flooded["Precipitation (mm/h)"],
        df_flooded["Flooded Area (%)"],
        marker='s', color='dodgerblue', label="Flooded Area FV1"
    )

    # Labels and Title
    ax.set_xlabel('Precipitation (mm/h)', fontsize=12)
    ax.set_ylabel('Flooded Area (%)', fontsize=12)
    ax.set_title(f'Flooded Area (%) vs Precipitation (mm/h) - {case_name}', fontsize=14)
    ax.grid(True)
    ax.set_xlim(0, max(df_flooded["Precipitation (mm/h)"]) + 10)
    ax.set_ylim(0, max(df_flooded["Flooded Area (%)"]) * 1.1)
    ax.legend()

    plt.tight_layout()

    # Save or show
    if output_folder:
        os.makedirs(output_folder, exist_ok=True)
        fig_path = os.path.join(output_folder, f"{case_name}_flooded_area_fv1.png")
        plt.savefig(fig_path, dpi=300)
        print(f" Plot saved to: {fig_path}")
        plt.close()
    else:
        plt.show()
        
#################################################################################################