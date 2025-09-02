#!/usr/bin/env python3
from pathlib import Path
import argparse
import pandas as pd
import matplotlib.pyplot as plt

# --- CSV column labels (must match your overlay script) ---
COL_TENT = "0.10-0.30 m (tents: flooded)"
COL_VULN = "0.30-0.50 m (vehicles: vulnerable)"
COL_SEV  = ">0.50 m (vehicles: highly vulnerable)"
RENTALS_LABEL = ">1.0 m (fixed rentals affected)"  # auto-detect if named slightly differently

# --- class groups for summing ---
VEHICLE_CLASSES = {
    "lake plot","premium","regular","residence plots",
    "royal lake plot","sleeping hut","standard","seasonal pitches","VIP",  # <-- vip lowercase
}
RENTAL_GROUP = {"rentals","rental chalet","villa seeblick"}

# --- pretty legend labels with subscripts ---
LEGEND_LABELS = {
    "v2": r"v2 (only rainfall)",
    "v4": r"v4 (rainfall + $Q_{10}$)",
    "v5": r"v5 (rainfall + $Q_{30}$)",
    "v6": r"v6 (rainfall + $Q_{100}$)",
}

# --- line/marker styles (consistent with other plots) ---
LS_SEV   = "-"             # >0.50 m vehicles
LS_VULN  = (0, (8, 4))     # 0.30–0.50 m vehicles
LS_TENTS = (0, (2, 2))     # 0.10–0.30 m tents
LS_LOW_V = ":"             # 0.10–0.30 m camping pitches (non-tents)

MS = 5       # marker size
ME = 2       # mark every Nth point
LW_SEV, LW_VULN, LW_TENTS, LW_NONT = 2.6, 2.4, 3.0, 2.1

def parse_case(spec: str):
    """Accept 'label=/path' or '/path' (label inferred from dir name)."""
    if "=" in spec:
        lab, path = spec.split("=", 1)
        return lab.strip(), Path(path.strip())
    p = Path(spec)
    label = p.name.split("_")[-1] if "_" in p.name else p.name
    return label, p

def load_counts(pivot_csv: Path):
    df = pd.read_csv(pivot_csv)
    if df.empty:
        return None, None
    df["class"] = df["class"].str.lower().str.strip()
    df = df.sort_values(["scenario","class"])
    for col in (COL_TENT, COL_VULN, COL_SEV):
        if col not in df.columns:
            df[col] = 0
    rentals_col = RENTALS_LABEL if RENTALS_LABEL in df.columns else None
    if rentals_col is None:
        for c in df.columns:
            if "fixed rentals affected" in c:
                rentals_col = c
                break
    return df, rentals_col

def get_series(df, rentals_col):
    # 0.10–0.30 split into tents vs camping pitches (non-tents)
    s_low_tents = (df[df["class"] == "tent"]
                   .groupby("scenario")[COL_TENT].sum())
    s_low_nont  = (df[df["class"].isin(VEHICLE_CLASSES)]
                   .groupby("scenario")[COL_TENT].sum())
    # 0.30–0.50 and >0.50 (vehicles)
    s_vuln = (df[df["class"].isin(VEHICLE_CLASSES)]
              .groupby("scenario")[COL_VULN].sum())
    s_sev  = (df[df["class"].isin(VEHICLE_CLASSES)]
              .groupby("scenario")[COL_SEV].sum())
    # rentals > threshold
    if rentals_col:
        s_rent = (df[df["class"].isin(RENTAL_GROUP)]
                  .groupby("scenario")[rentals_col].sum())
    else:
        s_rent = None
    return s_low_tents, s_low_nont, s_vuln, s_sev, s_rent

def legend_outside(ax, title="Version", ncol=1):
    return ax.legend(
        title=title, fontsize=9, ncol=ncol,
        loc="upper left", bbox_to_anchor=(1.02, 1.0), borderaxespad=0
    )

def main():
    ap = argparse.ArgumentParser(
        description="Compare versions per class; saves one PNG per class with class-coded line styles."
    )
    ap.add_argument("--case", action="append", required=True,
                    help="Case dir or 'label=dir' (expects counts_pivot.csv). Use multiple --case.")
    ap.add_argument("--outdir", required=True, help="Output folder for PNGs.")
    ap.add_argument("--tag", default="", help="Tag embedded in filenames and titles (e.g., 'Gordevio').")
    args = ap.parse_args()

    outdir = Path(args.outdir); outdir.mkdir(parents=True, exist_ok=True)
    tag = args.tag.strip()
    file_suffix = f"_{tag}_across_versions.png" if tag else "_across_versions.png"
    title_prefix = f"{tag} — " if tag else ""

    # Load all cases
    loaded = []
    for spec in args.case:
        label, cdir = parse_case(spec)
        csv = Path(cdir) / "counts_pivot.csv"
        if not csv.exists():
            print(f"[WARN] Missing: {csv}")
            continue
        df, rentals_col = load_counts(csv)
        if df is None:
            print(f"[INFO] Empty: {csv}")
            continue
        loaded.append((label, df, rentals_col))
    if not loaded:
        raise SystemExit("No data loaded.")

    # Common x-axis
    all_scenarios = sorted(set().union(*[set(df["scenario"].unique()) for _, df, _ in loaded]))

    # Build series, detect availability
    series = []
    any_low_tents = False
    any_low_nont  = False
    any_rentals   = False
    for label, df, rentals_col in loaded:
        s_low_tents, s_low_nont, s_vuln, s_sev, s_rent = get_series(df, rentals_col)
        if s_low_tents.sum() > 0: any_low_tents = True
        if s_low_nont.sum()  > 0: any_low_nont  = True
        if s_rent is not None and (s_rent.sum() > 0): any_rentals = True
        series.append((label, s_low_tents, s_low_nont, s_vuln, s_sev, s_rent))

    colors = plt.rcParams["axes.prop_cycle"].by_key().get("color", ["C0","C1","C2","C3","C4","C5","C6"])

    # --- Plot 0.30–0.50 (vehicles) ---
    fig, ax = plt.subplots(figsize=(10,5))
    for i, (label, s_low_tents, s_low_nont, s_vuln, s_sev, s_rent) in enumerate(series):
        y = s_vuln.reindex(all_scenarios, fill_value=0).values
        if y.sum() <= 0:  # skip empty series
            continue
        disp = LEGEND_LABELS.get(label, label)
        ax.plot(all_scenarios, y, linestyle=LS_VULN, linewidth=LW_VULN,
                marker="o", markersize=MS, markevery=ME,
                color=colors[i % len(colors)], label=disp)
    ax.set_xlabel("Scenario (mm/h)")
    ax.set_ylabel("Impacted pitches (count)")
    ax.set_title(f"{title_prefix} No access for Vehicles 0.30–0.50 m")
    legend_outside(ax)
    fig.tight_layout()
    out_030_050 = outdir / ("030_050" + file_suffix)
    fig.savefig(out_030_050, dpi=150, bbox_inches="tight"); print("Saved:", out_030_050.resolve())

    # --- Plot >0.50 (vehicles) ---
    fig, ax = plt.subplots(figsize=(10,5))
    for i, (label, s_low_tents, s_low_nont, s_vuln, s_sev, s_rent) in enumerate(series):
        y = s_sev.reindex(all_scenarios, fill_value=0).values
        if y.sum() <= 0:
            continue
        disp = LEGEND_LABELS.get(label, label)
        ax.plot(all_scenarios, y, linestyle=LS_SEV, linewidth=LW_SEV,
                marker="o", markersize=MS, markevery=ME,
                color=colors[i % len(colors)], label=disp)
    ax.set_xlabel("Scenario (mm/h)")
    ax.set_ylabel("Impacted pitches (count)")
    ax.set_title(f"{title_prefix} Pedestrians and/or vehicles highly vulnerable >0.50 m")
    legend_outside(ax)
    fig.tight_layout()
    out_gt050 = outdir / ("gt050" + file_suffix)
    fig.savefig(out_gt050, dpi=150, bbox_inches="tight"); print("Saved:", out_gt050.resolve())

    # --- Plot 0.10–0.30 (tents vs camping pitches) ---
    fig, ax = plt.subplots(figsize=(10,5))
    both_exist = any_low_tents and any_low_nont
    only_tents = any_low_tents and not any_low_nont
    only_nont  = any_low_nont  and not any_low_tents

    for i, (label, s_low_tents, s_low_nont, s_vuln, s_sev, s_rent) in enumerate(series):
        color = colors[i % len(colors)]
        disp  = LEGEND_LABELS.get(label, label)

        if both_exist or only_tents:
            y_t = s_low_tents.reindex(all_scenarios, fill_value=0).values
            if y_t.sum() > 0:
                ax.plot(all_scenarios, y_t, linestyle=LS_TENTS, linewidth=LW_TENTS,
                        marker="o", markersize=MS, markevery=ME,
                        color=color, label=(disp + " — tents") if both_exist else disp)

        if both_exist or only_nont:
            y_v = s_low_nont.reindex(all_scenarios, fill_value=0).values
            if y_v.sum() > 0:
                ax.plot(all_scenarios, y_v, linestyle=LS_LOW_V, linewidth=LW_NONT,
                        marker="s", markersize=MS, markevery=ME,
                        markerfacecolor="none", markeredgewidth=1.8,
                        color=color, label=(disp + " — camping pitches") if both_exist else disp)

    ax.set_xlabel("Scenario (mm/h)")
    ax.set_ylabel("Impacted pitches (count)")
    title_010_030 = f"{title_prefix}Tents 0.10–0.30 m" if only_tents else \
                    f"{title_prefix}Camping pitches 0.10–0.30 m" if only_nont else \
                    f"{title_prefix}0.10–0.30 m (tents & camping pitches)"
    ax.set_title(title_010_030)
    legend_outside(ax, ncol=1)
    fig.tight_layout()
    out_010_030 = outdir / ("010_030" + file_suffix)
    fig.savefig(out_010_030, dpi=150, bbox_inches="tight"); print("Saved:", out_010_030.resolve())

    # --- Rentals >1.0 m (only if present) ---
    if any_rentals:
        fig, ax = plt.subplots(figsize=(10,5))
        for i, (label, s_low_tents, s_low_nont, s_vuln, s_sev, s_rent) in enumerate(series):
            if s_rent is None:
                continue
            y = s_rent.reindex(all_scenarios, fill_value=0).values
            if y.sum() <= 0:
                continue
            disp = LEGEND_LABELS.get(label, label)
            ax.plot(all_scenarios, y, linestyle='-.', linewidth=2.2,
                    marker="x", markersize=MS, markevery=ME,
                    color=colors[i % len(colors)], label=disp)
        ax.set_xlabel("Scenario (mm/h)")
        ax.set_ylabel("Impacted pitches (count)")
        ax.set_title(f"{title_prefix}Rentals/rental chalets and bungalows >1.0 m")
        legend_outside(ax)
        fig.tight_layout()
        out_rent = outdir / ("rent_gt1" + file_suffix)
        fig.savefig(out_rent, dpi=150, bbox_inches="tight"); print("Saved:", out_rent.resolve())

if __name__ == "__main__":
    main()