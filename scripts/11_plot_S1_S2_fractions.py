#!/usr/bin/env python3
"""
Compare two scenario groups (e.g., S1 vs S2) as stacked horizontal bars for selected rainfall scenarios.

Example:
python plot_morges_s1_s2_bars.py \
  --fractions-v2 "/storage/homefs/ge24z347/exposure_results_campgrounds/Morges_2m_v2/fractions_long.csv" \
  --fractions-v4 "/storage/homefs/ge24z347/exposure_results_campgrounds/Morges_2m_v4/fractions_long.csv" \
  --totals "/storage/homefs/ge24z347/exposure_results_campgrounds/Morges_2m_v2/Morges_2m_v2_exposure.xlsx" \
  --versions v2 v4 \
  --version-labels S1 S2 \
  --scenarios 15 35 55 \
  --title "Morges: S1 (precipitation) vs S2 (precipitation + discharge)" \
  --outdir "/storage/homefs/ge24z347/exposure_results_campgrounds/Morges_plots" \
  --outfile "Morges_S1_S2_15_35_55.png" \
  --transparent
"""

from pathlib import Path
import argparse
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


STACK_ORDER = [
    ("mobile", 1),
    ("mobile", 2),
    ("non_mobile", 1),
    ("non_mobile", 2),
]

LABELS = {
    ("mobile", 1):     "mobile 0.10–0.30 m",
    ("mobile", 2):     "mobile ≥0.30 m",
    ("non_mobile", 1): "non-mobile 0.10–<1.0 m",
    ("non_mobile", 2): "non-mobile ≥1.0 m",
}

# Professional teal/indigo color scheme (edit if you want)
COLORS = {
    ("mobile", 1):     "#E0F2F1",
    ("mobile", 2):     "#00796B",
    ("non_mobile", 1): "#E8EAF6",
    ("non_mobile", 2): "#283593",
}


def read_totals(totals_path: str) -> tuple[int, int]:
    """Read totals from CSV or from an exposure XLSX (sheet 'site_totals')."""
    p = Path(totals_path)
    if p.suffix.lower() == ".csv":
        t = pd.read_csv(p).iloc[0]
    else:
        t = pd.read_excel(p, sheet_name="site_totals").iloc[0]

    def safe_int(x):
        try:
            if pd.isna(x):
                return 0
            return int(x)
        except Exception:
            return 0

    mobile_total = safe_int(t.get("mobile_total", 0))
    non_mobile_total = safe_int(t.get("non_mobile_total", 0))
    return mobile_total, non_mobile_total


def fractions_to_pct_total(frac_long: pd.DataFrame, totals: tuple[int, int]) -> pd.DataFrame:
    """Convert group-normalized fractions to % of total inventory."""
    mobile_total, non_mobile_total = totals
    total_inventory = max(mobile_total + non_mobile_total, 1)

    def denom_for_group(g: str) -> int:
        g = str(g).lower()
        if g == "mobile":
            return mobile_total
        if g == "non_mobile":
            return non_mobile_total
        return 0

    df = frac_long.copy()
    denom = df["group"].map(denom_for_group).astype(float)
    count = df["fraction"].astype(float) * denom
    df["pct_total"] = (count / total_inventory) * 100.0
    return df


def load_and_prepare(fractions_csv_paths: dict, versions: list[str], scenarios: list[int]) -> pd.DataFrame:
    """Load multiple fractions_long.csv files and return one combined dataframe."""
    dfs = []
    for v in versions:
        p = fractions_csv_paths[v]
        d = pd.read_csv(p)
        dfs.append(d)
    frac_long = pd.concat(dfs, ignore_index=True)

    # normalize types
    frac_long["version"] = frac_long["version"].astype(str).str.strip()
    frac_long["group"] = frac_long["group"].astype(str).str.lower().str.strip()
    frac_long["scenario"] = pd.to_numeric(frac_long["scenario"], errors="coerce")
    frac_long["level"] = pd.to_numeric(frac_long["level"], errors="coerce")
    frac_long["fraction"] = pd.to_numeric(frac_long["fraction"], errors="coerce")

    frac_long = frac_long.dropna(subset=["scenario", "level", "fraction"])
    frac_long["scenario"] = frac_long["scenario"].astype(int)
    frac_long["level"] = frac_long["level"].astype(int)

    # filter wanted versions + scenarios
    frac_long = frac_long[
        frac_long["version"].isin(versions) &
        frac_long["scenario"].isin(scenarios)
    ].copy()

    return frac_long


def build_full_grid(df_pct: pd.DataFrame, versions: list[str], scenarios: list[int]) -> pd.DataFrame:
    """Ensure missing combinations are filled with 0.0."""
    idx = pd.MultiIndex.from_product(
        [versions, scenarios, [k[0] for k in STACK_ORDER], [k[1] for k in STACK_ORDER]],
        names=["version", "scenario", "group", "level"]
    )
    df_full = (
        df_pct.set_index(["version", "scenario", "group", "level"])
              .reindex(idx, fill_value=0.0)
              .reset_index()
    )
    return df_full


def plot_stacked_bars(
    df_full: pd.DataFrame,
    versions: list[str],
    scenarios: list[int],
    version_labels: dict,
    outpath: Path,
    title: str,
    xlabel: str,
    transparent: bool,
):
    fig, ax = plt.subplots(figsize=(10, 6))

    bar_h = 0.35
    ypos = np.arange(len(scenarios))

    # fixed offsets for exactly two versions; if you pass more, it still works (spread evenly)
    if len(versions) == 1:
        offsets = {versions[0]: 0.0}
    else:
        offsets = {}
        step = bar_h  # keep about bar height separation
        center = (len(versions) - 1) / 2
        for i, v in enumerate(versions):
            offsets[v] = (center - i) * step  # top to bottom

    for v in versions:
        bottoms = np.zeros(len(scenarios), dtype=float)

        for (g, l) in STACK_ORDER:
            vals = []
            for s in scenarios:
                val = df_full.loc[
                    (df_full["version"] == v) &
                    (df_full["scenario"] == s) &
                    (df_full["group"] == g) &
                    (df_full["level"] == l),
                    "pct_total"
                ].values
                vals.append(float(val[0]) if len(val) else 0.0)

            vals = np.array(vals, dtype=float)

            ax.barh(
                ypos + offsets[v],
                vals,
                left=bottoms,
                height=bar_h * 0.95,
                color=COLORS[(g, l)],
                edgecolor="white",
                linewidth=0.6,
                label=LABELS[(g, l)] if v == versions[0] else None,  # legend once
            )
            bottoms += vals

    ax.set_yticks(ypos)
    ax.set_yticklabels([f"{s} mm/h" for s in scenarios], fontsize=12)

    # add S1/S2 labels near the start of each bar
    for i in range(len(scenarios)):
        for v in versions:
            ax.text(
                0.8,
                ypos[i] + offsets[v],
                version_labels.get(v, v),
                va="center",
                ha="left",
                fontsize=11,
            )

    ax.set_xlabel(xlabel, fontsize=12)
    ax.set_xlim(0, 100)

    ax.grid(axis="x", linestyle="--", alpha=0.35)
    ax.legend(loc="lower right", frameon=True, fontsize=10)

    ax.set_title(title, fontsize=13)
    ax.tick_params(axis="both", labelsize=14)
    fig.tight_layout()

    outpath.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(outpath, dpi=300, transparent=transparent, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {outpath}")


def parse_args():
    ap = argparse.ArgumentParser(description="Plot stacked bars (S1 vs S2) for selected scenarios with transparent background.")
    ap.add_argument("--fractions-v2", required=True, help="Path to fractions_long.csv for v2 (S1).")
    ap.add_argument("--fractions-v4", required=True, help="Path to fractions_long.csv for v4 (S2).")
    ap.add_argument("--totals", required=True, help="Totals file: exposure XLSX (sheet 'site_totals') or totals CSV.")

    ap.add_argument("--versions", nargs="+", default=["v2", "v4"], help='Versions to plot (default: v2 v4).')
    ap.add_argument("--version-labels", nargs="+", default=["S1", "S2"],
                    help='Labels shown in figure corresponding to --versions (default: S1 S2).')
    ap.add_argument("--scenarios", nargs="+", type=int, default=[15, 35, 55],
                    help="Scenarios to plot (default: 15 35 55).")

    ap.add_argument("--title", default="Morges: S1 vs S2", help="Figure title.")
    ap.add_argument("--xlabel", default="(%) camping pitches affected", help="X-axis label.")
    ap.add_argument("--outdir", required=True, help="Output folder to save the plot.")
    ap.add_argument("--outfile", default="S1_S2_selected_scenarios.png", help="Output filename (PNG).")
    ap.add_argument("--transparent", action="store_true", help="Save with transparent background.")
    return ap.parse_args()


def main():
    a = parse_args()

    if len(a.versions) != len(a.version_labels):
        raise SystemExit("ERROR: --versions and --version-labels must have the same length.")

    version_labels = {v: lab for v, lab in zip(a.versions, a.version_labels)}

    # map version -> csv path (supports exactly v2/v4 via args, but extendable if you add more later)
    fractions_paths = {}
    for v in a.versions:
        if v == "v2":
            fractions_paths[v] = a.fractions_v2
        elif v == "v4":
            fractions_paths[v] = a.fractions_v4
        else:
            raise SystemExit(f"ERROR: version '{v}' not supported by CLI. Add a path option for it if needed.")

    frac_long = load_and_prepare(fractions_paths, a.versions, a.scenarios)
    totals = read_totals(a.totals)
    df_pct = fractions_to_pct_total(frac_long, totals)
    df_full = build_full_grid(df_pct, a.versions, a.scenarios)

    outpath = Path(a.outdir) / a.outfile
    plot_stacked_bars(
        df_full=df_full,
        versions=a.versions,
        scenarios=a.scenarios,
        version_labels=version_labels,
        outpath=outpath,
        title=a.title,
        xlabel=a.xlabel,
        transparent=a.transparent,
    )


if __name__ == "__main__":
    main()






