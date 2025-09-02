#!/usr/bin/env python3
from pathlib import Path
import argparse
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

# column labels (must match your CSV headers)
COL_TENT = "0.10-0.30 m (tents: flooded)"
COL_VULN = "0.30-0.50 m (vehicles: vulnerable)"
COL_SEV  = ">0.50 m (vehicles: highly vulnerable)"
RENTALS_LABEL = ">1.0 m (fixed rentals affected)"  # if you changed the label, adjust here

# class groups for summing
VEHICLE_CLASSES = {
    "lake plot", "premium", "regular", "residence plots",
    "royal lake plot", "sleeping hut", "standard", "seasonal pitches", "vip",
}
RENTAL_GROUP = {"rentals", "rental chalet", "villa seeblick"}

# pretty, SHORT legend labels (fallback to raw label if not found)
LEGEND_LABELS = {
    "v2": r"v2 (only rainfall)",
    "v4": r"v4 (rainfall + $Q_{10}$)",
    "v5": r"v5 (rainfall + $Q_{30}$)",
    "v6": r"v6 (rainfall + $Q_{100}$)",
}

def parse_case_arg(s: str):
    """
    Accepts either:
      - a directory path, label inferred from its basename (e.g., Gordevio_2m_v4 -> v4)
      - 'label=/full/path' explicit form
    Returns (label, Path(dir)).
    """
    if "=" in s:
        label, path = s.split("=", 1)
        return label.strip(), Path(path.strip())
    p = Path(s)
    label = p.name.split("_")[-1] if "_" in p.name else p.name
    return label, p

def load_series(pivot_csv: Path):
    """Return scenarios, (tents, veh_030_050, veh_gt050, rentals) series."""
    df = pd.read_csv(pivot_csv)
    if df.empty:
        return [], pd.Series(dtype=float), pd.Series(dtype=float), pd.Series(dtype=float), pd.Series(dtype=float)

    df["class"] = df["class"].str.lower().str.strip()
    df = df.sort_values(["scenario", "class"])

    # ensure columns exist
    for col in (COL_TENT, COL_VULN, COL_SEV):
        if col not in df.columns:
            df[col] = 0

    # detect rentals column if present
    rentals_col = RENTALS_LABEL if RENTALS_LABEL in df.columns else None
    if rentals_col is None:
        for c in df.columns:
            if "fixed rentals affected" in c:
                rentals_col = c
                break

    # build series
    s_tents = (df[df["class"] == "tent"].groupby("scenario")[COL_TENT].sum())
    mask_vehicle = df["class"].isin(VEHICLE_CLASSES)
    s_vuln = df[mask_vehicle].groupby("scenario")[COL_VULN].sum()
    s_sev  = df[mask_vehicle].groupby("scenario")[COL_SEV].sum()

    if rentals_col:
        mask_rent = df["class"].isin(RENTAL_GROUP)
        s_rent = df[mask_rent].groupby("scenario")[rentals_col].sum()
    else:
        s_rent = pd.Series(dtype=float)

    # align indices
    scenarios = sorted(set(s_tents.index) | set(s_vuln.index) | set(s_sev.index) | set(s_rent.index))
    s_tents = s_tents.reindex(scenarios, fill_value=0)
    s_vuln  = s_vuln.reindex(scenarios,  fill_value=0)
    s_sev   = s_sev.reindex(scenarios,   fill_value=0)
    s_rent  = s_rent.reindex(scenarios,  fill_value=0) if not s_rent.empty else pd.Series([0]*len(scenarios), index=scenarios)

    return scenarios, s_tents, s_vuln, s_sev, s_rent

def main():
    ap = argparse.ArgumentParser(description="Overlay impacts (tents/vehicles/rentals) across multiple versions.")
    ap.add_argument("--case", action="append", required=True,
                    help="Case folder or 'label=folder'. Example: --case /.../Gordevio_2m_v2 --case v4=/.../Gordevio_2m_v4")
    ap.add_argument("--outdir", required=True, help="Output directory for the plot.")
    ap.add_argument("--outfile", default="Impact_ALL_versions.png", help="Output filename (PNG).")
    ap.add_argument("--tag", default="", help="Prefix added to the plot title (e.g., 'Gordevio').")
    args = ap.parse_args()

    cases = [parse_case_arg(s) for s in args.case]
    outdir = Path(args.outdir); outdir.mkdir(parents=True, exist_ok=True)
    outfile = outdir / args.outfile
    title_prefix = f"{args.tag} — " if args.tag else ""

    series_by_case = []
    any_rentals = False

    for label, cdir in cases:
        csv = Path(cdir) / "counts_pivot.csv"
        if not csv.exists():
            print(f"[WARN] Missing: {csv}")
            continue
        scenarios, s_tents, s_vuln, s_sev, s_rent = load_series(csv)
        if len(scenarios) == 0:
            print(f"[INFO] No data in {csv} for {label}")
            continue
        if (not s_rent.empty) and (s_rent.sum() > 0):
            any_rentals = True
        series_by_case.append({
            "label": label, "scenarios": scenarios,
            "tents": s_tents, "vuln": s_vuln, "sev": s_sev, "rent": s_rent
        })

    if not series_by_case:
        raise SystemExit("No cases had data to plot.")

    # union x-axis
    all_scenarios = sorted(set().union(*[set(s["scenarios"]) for s in series_by_case]))

    # line styles (metrics)
    dash_vuln  = (0, (8, 4))   # 0.30–0.50
    dash_tents = (0, (2, 2))   # 0.10–0.30

    plt.figure(figsize=(12, 6))
    ax = plt.gca()
    colors = plt.rcParams["axes.prop_cycle"].by_key().get("color", ["C0","C1","C2","C3","C4","C5","C6"])

    # Plot lines; only the SOLID line per version carries the short legend label.
    for i, item in enumerate(series_by_case):
        color = colors[i % len(colors)]
        disp  = LEGEND_LABELS.get(item["label"], item["label"])

        t = item["tents"].reindex(all_scenarios, fill_value=0).values
        v = item["vuln"].reindex(all_scenarios,  fill_value=0).values
        s = item["sev"].reindex(all_scenarios,   fill_value=0).values
        r = item["rent"].reindex(all_scenarios,  fill_value=0).values

        # vehicles >0.50 (SOLID) — this one gets the version label
        ax.plot(all_scenarios, s, linestyle='-',  linewidth=2, color=color, label=disp)
        # vehicles 0.30–0.50 (long dashes) — no legend label (keeps legend short)
        ax.plot(all_scenarios, v, linestyle=dash_vuln, linewidth=2, color=color, label=None)
        # tents 0.10–0.30 (short dashes) — no legend label
        ax.plot(all_scenarios, t, linestyle=dash_tents, linewidth=2, color=color, label=None)
        # rentals >1.0 m (dash-dot) — no legend label
        if any_rentals and (r.max() > 0):
            ax.plot(all_scenarios, r, linestyle='-.', linewidth=2, color=color, label=None)

    ax.set_xlabel("Scenario (mm/h)")
    ax.set_ylabel("Number of camping pitches exposed")
    ax.set_title(f"{title_prefix}Impacts by scenario")

    # Legend 1: versions (colors)
    leg1 = ax.legend(title="Version", ncol=2, fontsize=9, loc="upper left")
    ax.add_artist(leg1)

    # Legend 2: line-style meaning (metrics)
    style_handles = [
        Line2D([0],[0], linestyle='-',      linewidth=2, color='black', label="Vehicles >0.50 m"),
        Line2D([0],[0], linestyle=dash_vuln,linewidth=2, color='black', label="Vehicles 0.30–0.50 m"),
        Line2D([0],[0], linestyle=dash_tents,linewidth=2,color='black', label="Tents 0.10–0.30 m"),
    ]
    if any_rentals:
        style_handles.append(Line2D([0],[0], linestyle='-.', linewidth=2, color='black', label="Rentals >1.0 m"))
    ax.legend(handles=style_handles, title="Metric", fontsize=9, loc="upper right")

    plt.tight_layout()
    plt.savefig(outfile, dpi=150)
    print("Saved:", outfile.resolve())

if __name__ == "__main__":
    main()