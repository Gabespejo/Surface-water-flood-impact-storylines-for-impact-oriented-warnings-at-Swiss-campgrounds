######################################################################
################# IMPACTS IN GENERAL ################################
#####################################################################
################# Flooded area combiprecip ###########################
import os
import numpy as np
import pandas as pd
import geopandas as gpd
import xarray as xr
import rioxarray  # enables rio.clip, rio.resolution, rio.crs


def flooded_area_timeseries_from_netcdf(
    nc_file: str,
    var: str,
    geojson_file: str,
    polygon_column_name: str,
    polygon_name: str,
    min_depth_threshold: float = 0.05,
    time_dim: str = "REFERENCE_TS",   # change if your file uses "time"
    assume_crs: str = "EPSG:2056",    # common for your workflow
    store_nc_basename: bool = True,   # NEW: store only filename by default
):
    # --- read polygon
    gdf = gpd.read_file(geojson_file)
    gdf["__cmp"] = gdf[polygon_column_name].astype(str).str.strip().str.lower()
    sel = gdf[gdf["__cmp"] == polygon_name.strip().lower()]
    if sel.empty:
        raise ValueError(
            f"Polygon '{polygon_name}' not found in column '{polygon_column_name}'."
        )

    geom = sel.geometry.values[0]

    # total area (use your existing column if present)
    if "area_polygon_campingsite" in sel.columns:
        total_area_m2 = float(sel["area_polygon_campingsite"].values[0])
    else:
        # compute (needs projected CRS)
        if sel.crs is None:
            sel = sel.set_crs(assume_crs)
        total_area_m2 = float(sel.to_crs(assume_crs).area.values[0])

    # --- open netcdf
    ds = xr.open_dataset(nc_file)
    if var not in ds:
        raise KeyError(f"Variable '{var}' not found in NetCDF. Available: {list(ds.data_vars)}")
    da = ds[var]

    # ensure CRS exists for clipping
    if not da.rio.crs:
        da = da.rio.write_crs(assume_crs)

    # geometry to same CRS as raster
    geom_gdf = gpd.GeoDataFrame(geometry=[geom], crs=gdf.crs)
    if geom_gdf.crs is None:
        geom_gdf = geom_gdf.set_crs(assume_crs)
    geom_gdf = geom_gdf.to_crs(da.rio.crs)

    # pixel area (e.g., 2m*2m=4m²)
    resx, resy = da.rio.resolution()
    pixel_area = abs(resx * resy)

    # --- loop over time steps
    rows = []
    if time_dim not in da.dims:
        raise KeyError(f"time_dim '{time_dim}' not in da.dims: {da.dims}")
    n = da.sizes[time_dim]

    for i in range(n):
        arr2d = da.isel({time_dim: i})

        # clip to polygon
        clipped = arr2d.rio.clip(geom_gdf.geometry, geom_gdf.crs, drop=True)

        # flooded mask
        flooded = (clipped >= min_depth_threshold)

        flooded_area_m2 = float(flooded.sum().values * pixel_area)
        rows.append(
            {
                "time": pd.to_datetime(arr2d[time_dim].values),
                "Flooded Area (m²)": flooded_area_m2,
                "Flooded Area (%)": 100.0 * flooded_area_m2 / total_area_m2,
            }
        )

    df = pd.DataFrame(rows).sort_values("time").reset_index(drop=True)

    # --- provenance columns (safe: overwrite if already present)
    df["nc_file"] = os.path.basename(nc_file) if store_nc_basename else nc_file
    df["polygon"] = polygon_name
    df["Total Area (m²)"] = total_area_m2

    # move provenance columns to front in a stable order
    front = ["nc_file", "polygon", "time", "Flooded Area (m²)", "Flooded Area (%)", "Total Area (m²)"]
    df = df[[c for c in front if c in df.columns] + [c for c in df.columns if c not in front]]

    return df

#################################################################################################################
###################COUNTING CMAPING PITCHES AFFECTED ########################################################
##################COMBIPRECIP #########################################################################
import numpy as np
import pandas as pd
import geopandas as gpd
import xarray as xr
import rioxarray  # noqa: F401  (needed for .rio accessor)
from rasterio.transform import rowcol


def exposure_counts_timeseries_from_netcdf(
    nc_file: str,
    var: str,
    points_path: str,
    class_field: str,
    buffer_m: float = 3.0,
    rental_threshold: float = 1.0,
    time_dim: str = "REFERENCE_TS",
    force_points_crs: str | None = None,
    assume_crs: str = "EPSG:2056",
):
    """
    Count impacted campground points per NetCDF timestep using MOBILE vs NON_MOBILE buckets.

    Classification (same as your raster workflow):
      - MOBILE (vehicle pitches + tents):
          Level 1: 0.10 <= depth < 0.30 m
          Level 2: depth >= 0.30 m
      - NON_MOBILE (fixed rentals):
          Level 1: 0.10 <= depth < rental_threshold
          Level 2: depth >= rental_threshold

    Returns:
      counts_long:  columns [time, group, level, count]
      counts_pivot: same as counts_long (already tidy; kept for compatibility)
      frac_long:    columns [time, group, level, count, fraction, row_label]
      frac_wide:    index = row_label ('mobile_1', ...), columns = time, values = fraction
      site_totals:  dict with inventory totals {'mobile_total':..., 'non_mobile_total':...}
    """

    # -----------------------------
    # Constants (kept inside function)
    # -----------------------------
    INTEREST = {
        "lake plot", "premium", "regular", "residence plots",
        "royal lake plot", "sleeping hut", "standard", "tent",
        "seasonal pitches", "vip",
        "rentals", "rental chalet", "villa seeblick"
    }

    VEHICLE_PITCH_CLASSES = {
        "lake plot", "premium", "regular", "residence plots",
        "royal lake plot", "sleeping hut", "standard", "seasonal pitches", "vip"
    }
    MOBILE_CLASSES = VEHICLE_PITCH_CLASSES | {"tent"}
    FIXED_RENTALS = {"rentals", "rental chalet", "villa seeblick"}

    # -----------------------------
    # Helper functions (nested)
    # -----------------------------
    def classify_depth_simple(depth_m, cls_name):
        if depth_m is None or np.isnan(depth_m) or cls_name is None:
            return None
        cls = str(cls_name).strip().lower()

        # non-mobile (fixed rentals)
        if cls in FIXED_RENTALS:
            if depth_m >= rental_threshold:
                return ("non_mobile", 2)
            if depth_m >= 0.10:
                return ("non_mobile", 1)
            return None

        # mobile (vehicle pitches + tents)
        if cls in MOBILE_CLASSES:
            if (depth_m >= 0.10) and (depth_m < 0.30):
                return ("mobile", 1)
            if depth_m >= 0.30:
                return ("mobile", 2)
            return None

        return None

    def prepare_points():
        pts = gpd.read_file(points_path)

        if force_points_crs:
            pts = pts.set_crs(force_points_crs, allow_override=True)

        if pts.crs is None:
            pts = pts.set_crs(assume_crs)

        classes = pts[class_field].astype(str).str.lower().str.strip()
        keep = classes.isin(INTEREST)
        pts = pts.loc[keep].copy()
        classes = classes.loc[keep].reset_index(drop=True)

        inv_mobile = int(classes.isin(MOBILE_CLASSES).sum())
        inv_non_mobile = int(classes.isin(FIXED_RENTALS).sum())
        return pts, classes, inv_mobile, inv_non_mobile

    def max_depth_within_buffer_array(arr2d, transform, x, y, r_m=3.0, nodata=None):
        px = abs(transform.a)  # assume square pixels
        rpx = int(np.ceil(r_m / px))

        r, c = rowcol(transform, x, y)
        h, w = arr2d.shape

        r0, r1 = max(0, r - rpx), min(h - 1, r + rpx)
        c0, c1 = max(0, c - rpx), min(w - 1, c + rpx)

        win = arr2d[r0:r1 + 1, c0:c1 + 1].astype("float64")

        rr = np.arange(r0, r1 + 1) - r
        cc = np.arange(c0, c1 + 1) - c
        dy = (rr[:, None]) * px
        dx = (cc[None, :]) * px
        mask = np.hypot(dx, dy) <= r_m

        if nodata is not None:
            win = np.where(win == nodata, np.nan, win)

        vals = win[mask]
        if vals.size == 0 or np.all(np.isnan(vals)):
            return np.nan
        return float(np.nanmax(vals))

    # -----------------------------
    # Main computation
    # -----------------------------
    pts, classes, inv_mobile, inv_non_mobile = prepare_points()

    ds = xr.open_dataset(nc_file)
    if var not in ds:
        raise KeyError(f"Variable '{var}' not in NetCDF. Available: {list(ds.data_vars)}")
    da = ds[var]

    # CRS for rioxarray
    if not da.rio.crs:
        da = da.rio.write_crs(assume_crs)

    # Reproject points to raster CRS
    pts = pts.to_crs(da.rio.crs)

    # time dim check
    if time_dim not in da.dims:
        raise KeyError(f"time_dim '{time_dim}' not found. da.dims={da.dims}")

    # transform / nodata once
    transform = da.rio.transform()
    nodata = da.rio.nodata

    times = pd.to_datetime(da[time_dim].values)

    rows_counts = []
    for i, t in enumerate(times):
        arr2d = da.isel({time_dim: i}).values

        depths = np.array(
            [max_depth_within_buffer_array(arr2d, transform, g.x, g.y, r_m=buffer_m, nodata=nodata)
             for g in pts.geometry],
            dtype=float
        )

        labels = [classify_depth_simple(d, c) for d, c in zip(depths, classes.values)]
        labels = [lab for lab in labels if lab is not None]

        # if nobody impacted -> keep explicit zeros for continuity
        if len(labels) == 0:
            for group in ["mobile", "non_mobile"]:
                for level in [1, 2]:
                    rows_counts.append({"time": t, "group": group, "level": level, "count": 0})
            continue

        groups, levels = zip(*labels)
        df_tmp = pd.DataFrame({"group": groups, "level": levels})

        counts = (df_tmp.groupby(["group", "level"])
                        .size()
                        .reset_index(name="count"))

        # ensure all 4 combos exist
        full = pd.MultiIndex.from_product(
            [["mobile", "non_mobile"], [1, 2]],
            names=["group", "level"]
        )
        counts = (counts.set_index(["group", "level"])
                        .reindex(full, fill_value=0)
                        .reset_index())
        counts["time"] = t

        rows_counts.extend(counts.to_dict("records"))

    counts_long = (pd.DataFrame(rows_counts)
                   .sort_values(["time", "group", "level"])
                   .reset_index(drop=True))

    counts_pivot = counts_long.copy()

    site_totals = {"mobile_total": inv_mobile, "non_mobile_total": inv_non_mobile}

    # Fractions
    def denom_for(group):
        return inv_mobile if group == "mobile" else inv_non_mobile

    frac_long = counts_long.copy()
    frac_long["denom"] = frac_long["group"].map(denom_for)
    frac_long["fraction"] = np.where(
        frac_long["denom"] > 0,
        frac_long["count"] / frac_long["denom"],
        np.nan
    )
    frac_long = frac_long.drop(columns=["denom"])
    frac_long["row_label"] = frac_long["group"] + "_" + frac_long["level"].astype(str)

    frac_wide = (frac_long
                 .pivot_table(index="row_label", columns="time", values="fraction", aggfunc="mean")
                 .sort_index())

    return counts_long, counts_pivot, frac_long, frac_wide, site_totals