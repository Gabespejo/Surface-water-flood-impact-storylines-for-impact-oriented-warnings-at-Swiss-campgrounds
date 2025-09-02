#!/usr/bin/env python3
from pathlib import Path
import argparse
import re
import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio.transform import rowcol
from rasterio.crs import CRS

# ---- classes of interest (ALL lowercase) ----
INTEREST = {
    "lake plot", "premium", "regular", "residence plots",
    "royal lake plot", "sleeping hut", "standard", "tent",
    "seasonal pitches", "VIP",
    "rentals", "rental chalet", "villa seeblick"
}

# camping-pitch classes (exclude tents and rentals)
VEHICLE_PITCH_CLASSES = {
    "lake plot", "premium", "regular", "residence plots",
    "royal lake plot", "sleeping hut", "standard", "seasonal pitches", "VIP"
}

# rentals group
FIXED_RENTALS = {"rentals", "rental chalet", "villa seeblick"}

# ------------------------------------------------------------------

def max_depth_within_buffer(src, x, y, r_m=3.0):
    """Max depth in a circular buffer of radius r_m (m) around (x, y)."""
    px = abs(src.transform.a)  # pixel size (assume square)
    rpx = int(np.ceil(r_m / px))
    r, c = rowcol(src.transform, x, y)
    r0, r1 = max(0, r - rpx), min(src.height - 1, r + rpx)
    c0, c1 = max(0, c - rpx), min(src.width  - 1, c + rpx)
    arr = src.read(1, window=((r0, r1 + 1), (c0, c1 + 1))).astype("float64")

    rr = np.arange(r0, r1 + 1) - r
    cc = np.arange(c0, c1 + 1) - c
    dy = (rr[:, None]) * px
    dx = (cc[None, :]) * px
    mask = np.hypot(dx, dy) <= r_m

    nodata = src.nodata
    if nodata is not None:
        arr = np.where(arr == nodata, np.nan, arr)

    vals = arr[mask]
    if vals.size == 0 or np.all(np.isnan(vals)):
        return np.nan
    return float(np.nanmax(vals))

# ---------- simplified classification with rentals L1/L2 ----------
# Returns tuples (group, level):
#   tents:   ("tents",   1)  if depth >= 0.10
#   camping: ("camping", 1)  if 0.10 <= depth < 0.30
#            ("camping", 2)  if depth >= 0.30
#   rentals: ("rentals", 1)  if 0.10 <= depth < rental_threshold
#            ("rentals", 2)  if depth >= rental_threshold
#   None                     otherwise (not affected)
def classify_depth_simple(depth_m, cls_name, rental_threshold):
    if np.isnan(depth_m) or cls_name is None:
        return None
    cls = str(cls_name).strip().lower()

    # Rentals
    if cls in FIXED_RENTALS:
        if depth_m >= rental_threshold:
            return ("rentals", 2)
        if depth_m >= 0.10:
            return ("rentals", 1)
        return None

    # Tents
    if cls == "tent":
        return ("tents", 1) if depth_m >= 0.10 else None

    # Vehicle pitches
    if cls in VEHICLE_PITCH_CLASSES:
        if (depth_m >= 0.10) and (depth_m < 0.30):
            return ("camping", 1)
        if depth_m >= 0.30:
            return ("camping", 2)
        return None

    return None

# ------------------------------------------------------------------

def overlay_one_scenario(points_path, class_field, raster_path, buffer_m, force_points_crs, rental_threshold):
    """Return (impacted_rows_df, counts_df) for one raster scenario using the simplified scheme."""
    pts = gpd.read_file(points_path)

    with rasterio.open(raster_path) as src:
        # set/align CRS
        if force_points_crs:
            pts = pts.set_crs(force_points_crs, allow_override=True)
        src_crs = src.crs or CRS.from_epsg(2056)
        if pts.crs is None:
            pts = pts.set_crs(src_crs)
        else:
            pts = pts.to_crs(src_crs)

        # filter to classes we care about
        classes = pts[class_field].astype(str).str.lower().str.strip()
        keep = classes.isin(INTEREST)
        pts = pts.loc[keep].copy()
        classes = classes.loc[keep].reset_index(drop=True)

        # measure depths
        depths = np.array([max_depth_within_buffer(src, g.x, g.y, r_m=buffer_m)
                           for g in pts.geometry], dtype=float)

    labels = [classify_depth_simple(d, c, rental_threshold) for d, c in zip(depths, classes.values)]
    # keep impacted only
    mask = [lab is not None for lab in labels]
    classes = classes[mask].reset_index(drop=True)
    depths  = depths [mask]
    gl = [lab for lab in labels if lab is not None]

    if len(gl) == 0:
        df = pd.DataFrame(columns=["class","depth_m","group","level"])
        counts = pd.DataFrame(columns=["group","level","count"])
        return df, counts

    groups, levels = zip(*gl)
    df = pd.DataFrame({
        "class": classes.values,
        "depth_m": depths,
        "group": groups,     # tents / camping / rentals
        "level": levels      # tents:1 ; camping:1/2 ; rentals:1/2
    })

    counts = (df.groupby(["group","level"])
                .size()
                .reset_index(name="count")
                .sort_values(["group","level"]))

    return df, counts

def find_raster(build_dir, basename, duration, q):
    """Try common layout variants inside build_dir for a given scenario q."""
    build_dir = Path(build_dir)
    candidates = [
        build_dir / f"{basename}_{q}_fv1-gpu" / f"{basename}_{duration}_{q}.max",
        build_dir / f"{basename}_{duration}_{q}.max",
        build_dir / f"{basename}_{q}.max",
        build_dir / f"{basename}_{q}_fv1-gpu" / f"{basename}_{q}.max",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None

# --- Inventory totals (denominators) from the points shapefile ---
def compute_inventory_totals(points_path, class_field, force_points_crs=None):
    gdf = gpd.read_file(points_path)
    if force_points_crs:
        gdf = gdf.set_crs(force_points_crs, allow_override=True)

    classes = gdf[class_field].astype(str).str.lower().str.strip()
    classes = classes[classes.isin(INTEREST)]

    tents_total   = int((classes == "tent").sum())
    pitches_total = int(classes.isin(VEHICLE_PITCH_CLASSES).sum())
    rentals_total = int(classes.isin(FIXED_RENTALS).sum())
    return tents_total, pitches_total, rentals_total

def add_side_totals(df: pd.DataFrame, totals: dict) -> pd.DataFrame:
    """Put totals in extra columns on the first row only (for easy human reading)."""
    if df.empty:
        return pd.DataFrame([totals])
    df_out = df.copy()
    for k in ("tents_total", "camping_pitches_total", "rentals_total"):
        df_out[k] = ""
    first = df_out.index[0]
    df_out.loc[first, "tents_total"] = totals["tents_total"]
    df_out.loc[first, "camping_pitches_total"] = totals["camping_pitches_total"]
    df_out.loc[first, "rentals_total"] = totals["rentals_total"]
    return df_out

def infer_version_label(basename: str, fallback: str = "v?") -> str:
    m = re.search(r"v\d+", basename)
    return m.group(0) if m else fallback

# --- Build fractions tables (long + wide) ---
def build_fractions_tables(counts_long: pd.DataFrame,
                           scenarios_all: list[int],
                           version_label: str,
                           inv_tents: int,
                           inv_camping: int,
                           inv_rentals: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Returns (fractions_long, fractions_wide)
      - long: [version, group, level, scenario, fraction]
      - wide: index rows like 'v6_camping_1', columns=scenario
    """

    def series_fraction(group, level, denom):
        vals = []
        for s in scenarios_all:
            count = counts_long.loc[
                (counts_long["scenario"] == s) &
                (counts_long["group"] == group) &
                (counts_long["level"] == level),
                "count"
            ].sum()
            vals.append((count / denom) if denom else np.nan)
        return np.array(vals, dtype=float)

    rows = []

    def add_long_if_any(group: str, level: int, denom: int):
        """Only add rows for groups that actually exist (denom>0). Avoids 0-division and ghost groups."""
        if denom <= 0:
            return
        arr = series_fraction(group, level, denom)
        for s, v in zip(scenarios_all, arr):
            rows.append({
                "version": version_label,
                "group": group,
                "level": int(level),
                "scenario": int(s),
                "fraction": float(v) if pd.notna(v) else np.nan
            })

    # Tents (level 1)
    add_long_if_any("tents",   1, inv_tents)
    # Camping (L1=0.10–0.30 ; L2>=0.30)
    add_long_if_any("camping", 1, inv_camping)
    add_long_if_any("camping", 2, inv_camping)
    # Rentals (L1=0.10–<thr ; L2>=thr)
    add_long_if_any("rentals", 1, inv_rentals)
    add_long_if_any("rentals", 2, inv_rentals)

    frac_long = pd.DataFrame(rows)

    if frac_long.empty:
        return frac_long, pd.DataFrame()

    frac_long["row_label"] = (
        frac_long["version"] + "_" + frac_long["group"] + "_" + frac_long["level"].astype(str)
    )
    frac_wide = (frac_long
                 .pivot_table(index="row_label", columns="scenario",
                              values="fraction", aggfunc="mean")
                 .sort_index())
    frac_wide = frac_wide.reindex(sorted(frac_wide.columns), axis=1)
    return frac_long, frac_wide

# ------------------------------------------------------------------

def run_many_scenarios(points_path, class_field, build_dir, basename, duration,
                       start, end, step, buffer_m, force_points_crs,
                       outdir, rental_threshold, version_label, debug_first=False):

    outdir = Path(outdir); outdir.mkdir(parents=True, exist_ok=True)
    all_counts = []; found_any = False

    # Inventory totals once (for denominators)
    inv_tents, inv_camping, inv_rentals = compute_inventory_totals(
        points_path, class_field, force_points_crs
    )
    print(f"[INFO] Inventory totals — tents:{inv_tents} camping:{inv_camping} rentals:{inv_rentals}")

    totals_dict = {
        "tents_total": inv_tents,
        "camping_pitches_total": inv_camping,
        "rentals_total": inv_rentals,
    }

    # NEW: remember which groups actually exist in the site
    valid_groups = set()
    if inv_tents > 0:
        valid_groups.add("tents")
    if inv_camping > 0:
        valid_groups.add("camping")
    if inv_rentals > 0:
        valid_groups.add("rentals")

    scenarios_seen = []

    for q in range(start, end + 1, step):
        raster = find_raster(build_dir, basename, duration, q)
        if raster is None:
            print(f"[WARN] Missing raster: {basename} {duration} {q} under {build_dir}")
            continue
        found_any = True
        scenarios_seen.append(q)
        print(f"[INFO] Scenario {q}: {raster}")

        df_imp, counts = overlay_one_scenario(points_path, class_field, str(raster),
                                              buffer_m=buffer_m,
                                              force_points_crs=force_points_crs,
                                              rental_threshold=rental_threshold)
        counts["scenario"] = q
        all_counts.append(counts)

        if debug_first:
            gpkg = outdir / f"debug_{basename}_{duration}_{q}.gpkg"
            try:
                gdf = gpd.read_file(points_path)
                if force_points_crs:
                    gdf = gdf.set_crs(force_points_crs, allow_override=True)
                with rasterio.open(raster) as src:
                    gdf = gdf.to_crs(src.crs or CRS.from_epsg(2056))
                gdf.to_file(gpkg, driver="GPKG")
                print(f"[DEBUG] wrote {gpkg}")
            except Exception as e:
                print(f"[DEBUG] failed to write debug gpkg: {e}")
            debug_first = False

    if not found_any:
        print("[ERR] No scenarios found. Check --build-dir, --duration and naming.")
        return

    scenarios_all = sorted(set(scenarios_seen))

    if not all_counts:
        print("[INFO] Scenarios found but no impacted points matched your rules.")
        counts_long = pd.DataFrame(columns=["group","level","count","scenario"])
        counts_pivot = pd.DataFrame()

        add_side_totals(counts_long, totals_dict).to_csv(outdir / "counts_long.csv", index=False)
        counts_pivot.to_csv(outdir / "counts_pivot.csv", index=False)

        xlsx = outdir / f"{basename}_exposure.xlsx"
        with pd.ExcelWriter(xlsx, engine="openpyxl") as xw:
            counts_long.to_excel(xw, sheet_name="counts_long", index=False)
            counts_pivot.to_excel(xw, sheet_name="counts_pivot", index=False)
            pd.DataFrame([totals_dict]).to_excel(xw, sheet_name="site_totals", index=False)
        print("Saved:", xlsx)

        frac_long, frac_wide = pd.DataFrame(), pd.DataFrame()
        fxlsx = outdir / f"{basename}_fractions.xlsx"
        with pd.ExcelWriter(fxlsx, engine="openpyxl") as xw:
            frac_long.to_excel(xw, sheet_name="fractions_long", index=False)
            frac_wide.to_excel(xw, sheet_name="fractions_wide")
        frac_long.to_csv(outdir / "fractions_long.csv", index=False)
        frac_wide.to_csv(outdir / "fractions_wide.csv")
        print("Saved:", fxlsx)
        return

    counts_long = pd.concat(all_counts, ignore_index=True)

    # NEW: drop accidental groups with zero inventory, if any
    if not valid_groups:
        print("[WARN] No valid groups in inventory — nothing to save.")
        return
    counts_long = counts_long[counts_long["group"].isin(valid_groups)].copy()

    # Pivot for impacted counts by group/level per scenario
    counts_pivot = (counts_long
        .pivot_table(index=["scenario","group","level"], values="count",
                     aggfunc="sum", fill_value=0)
        .reset_index()
        .sort_values(["scenario","group","level"]))

    # Save CSVs with totals side columns
    add_side_totals(counts_long, totals_dict).to_csv(outdir / "counts_long.csv", index=False)
    add_side_totals(counts_pivot, totals_dict).to_csv(outdir / "counts_pivot.csv", index=False)

    # Excel bundle
    xlsx = outdir / f"{basename}_exposure.xlsx"
    try:
        with pd.ExcelWriter(xlsx, engine="openpyxl") as xw:
            counts_long.to_excel(xw, sheet_name="counts_long", index=False)
            counts_pivot.to_excel(xw, sheet_name="counts_pivot", index=False)
            pd.DataFrame([totals_dict]).to_excel(xw, sheet_name="site_totals", index=False)
        print("Saved:", xlsx)
    except Exception as e:
        print(f"[INFO] Excel not written ({e}). CSVs saved in {outdir}")

    # Fractions (long & wide) — ONLY for groups with denom>0
    if not version_label:
        version_label = infer_version_label(str(basename))

    frac_long, frac_wide = build_fractions_tables(
        counts_long=counts_long.assign(scenario=counts_long["scenario"]),
        scenarios_all=scenarios_all,
        version_label=version_label,
        inv_tents=inv_tents,
        inv_camping=inv_camping,
        inv_rentals=inv_rentals
    )

    frac_long.to_csv(outdir / "fractions_long.csv", index=False)
    frac_wide.to_csv(outdir / "fractions_wide.csv")

    fxlsx = outdir / f"{basename}_fractions.xlsx"
    with pd.ExcelWriter(fxlsx, engine="openpyxl") as xw:
        frac_long.to_excel(xw, sheet_name="fractions_long", index=False)
        frac_wide.to_excel(xw, sheet_name="fractions_wide")
    print("Saved:", fxlsx)

# -------- CLI --------
def parse_args():
    p = argparse.ArgumentParser(
        description="Overlay campground points vs. LISFLOOD depth rasters across scenarios (simplified buckets with rentals L1/L2)."
    )
    p.add_argument("--points", required=True, help="Path to exposure points (SHP/GPKG).")
    p.add_argument("--class-field", default="type", help="Attribute with class labels (default: type).")
    p.add_argument("--build-dir", required=True, help="Path to the build directory (e.g. .../build/Sempach_2m_v4).")
    p.add_argument("--basename", help="Basename in filenames (default: inferred from build-dir name).")
    p.add_argument("--duration", required=True, help="Duration token in filenames (e.g. 75min or 60min).")
    p.add_argument("--start", type=int, default=10)
    p.add_argument("--end", type=int, default=110)
    p.add_argument("--step", type=int, default=10)
    p.add_argument("--buffer", type=float, default=3.0, help="Buffer radius in meters (default 3).")
    p.add_argument("--force-points-crs", default=None,
                   help="Force/set CRS of the points layer, e.g. 'EPSG:2056' (optional).")
    p.add_argument("--outdir", required=True, help="Output folder for CSV/XLSX.")
    p.add_argument("--rental-threshold", type=float, default=1.0,
                   help="Threshold (m) to split rentals levels (default 1.0).")
    p.add_argument("--version-label", default="",
                   help="Optional label for fractions rows (e.g., v2, v4, v5, v6). If omitted, inferred from basename.")
    p.add_argument("--debug-first", action="store_true",
                   help="Write a GPKG of impacted points for the first processed scenario.")
    return p.parse_args()

def main():
    a = parse_args()
    build_dir = Path(a.build_dir)
    basename = a.basename or build_dir.name  # e.g. 'Morges_2m_v6'

    run_many_scenarios(
        points_path=a.points,
        class_field=a.class_field,
        build_dir=build_dir,
        basename=basename,
        duration=a.duration,
        start=a.start, end=a.end, step=a.step,
        buffer_m=a.buffer,
        force_points_crs=a.force_points_crs,
        outdir=a.outdir,
        rental_threshold=a.rental_threshold,
        version_label=a.version_label,
        debug_first=a.debug_first,
    )

if __name__ == "__main__":
    main()