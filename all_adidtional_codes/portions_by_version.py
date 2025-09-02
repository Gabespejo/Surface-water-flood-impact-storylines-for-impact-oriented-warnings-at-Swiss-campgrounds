#!/usr/bin/env python3
from pathlib import Path
import argparse
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import to_rgba

# -------- Legend labels and stacking order (mobile / non_mobile) --------
LABELS = {
    ("mobile", 1):      "mobile 0.10–0.30 m",
    ("mobile", 2):      "mobile ≥0.30 m",
    ("non_mobile", 1):  "non-mobile 0.10–<1.0 m",
    ("non_mobile", 2):  "non-mobile ≥1.0 m",
}

STACK_ORDER = [
    ("mobile", 1),
    ("mobile", 2),
    ("non_mobile", 1),
    ("non_mobile", 2),
]

# Default colors (will be overridden by --palette or --colors)
COLORS = {
    ("mobile", 1):      "C0",
    ("mobile", 2):      "C1",
    ("non_mobile", 1):  "C2",
    ("non_mobile", 2):  "C3",
}

# Palettes that are sequential (light -> dark). For these we skip the lightest shade.
SEQUENTIAL_PALETTES = {
    "rdpu","reds","blues","greens","oranges","purples",
    "ylgn","ylgnbu","ylorbr","ylorrd","purd","pubu","bugn","bupu","gnbu",
}

# -------- Pretty title for version labels --------
def pretty_version_for_title(version: str) -> str:
    v = str(version).strip().lower()
    if v.startswith("v2"):
        return "Rainfall"
    if v.startswith("v4"):
        return r"Rainfall + $Q_{10}$"
    if v.startswith("v5"):
        return r"Rainfall + $Q_{30}$"
    if v.startswith("v6"):
        return r"Rainfall + $Q_{100}$"
    # fallback: keep the raw version (e.g., v3)
    return str(version)

# -------- Data helpers --------
def read_totals(totals_path: Path):
    """
    Read totals from a CSV or an exposure XLSX (sheet 'site_totals').

    Expected (new) columns:
      - mobile_total
      - non_mobile_total

    Backward-compatible fallback (old columns):
      - mobile_total := tents_total + camping_pitches_total
      - non_mobile_total := rentals_total
    """
    totals_path = Path(totals_path)
    if totals_path.suffix.lower() == ".csv":
        t = pd.read_csv(totals_path).iloc[0]
    else:
        try:
            t = pd.read_excel(totals_path, sheet_name="site_totals").iloc[0]
        except Exception as e:
            raise FileNotFoundError(f"Could not read totals from {totals_path}: {e}")

    def _safe_int(x):
        try:
            if pd.isna(x):
                return 0
            return int(x)
        except Exception:
            return 0

    # New fields first
    mobile = t.get("mobile_total")
    non_mobile = t.get("non_mobile_total")

    mobile_total = _safe_int(mobile)
    non_mobile_total = _safe_int(non_mobile)

    # Fallback to old fields if new missing/zero AND old present
    if mobile_total == 0:
        tents = _safe_int(t.get("tents_total", 0))
        camping = _safe_int(t.get("camping_pitches_total", 0))
        if (tents + camping) > 0:
            mobile_total = tents + camping

    if non_mobile_total == 0:
        rentals = _safe_int(t.get("rentals_total", 0))
        if rentals > 0:
            non_mobile_total = rentals

    return mobile_total, non_mobile_total

def build_percentage_of_total(frac_long: pd.DataFrame, totals):
    """
    Convert group-normalized fractions to % of total inventory per scenario.
    Groups expected in frac_long: 'mobile', 'non_mobile'.
    """
    mobile_total, non_mobile_total = totals
    total_inventory = max(mobile_total + non_mobile_total, 1)

    def denom_for_group(grp: str) -> int:
        grp = str(grp).lower()
        if grp == "mobile":
            return mobile_total
        if grp == "non_mobile":
            return non_mobile_total
        # Backward compatibility (if old groups slip in)
        if grp in ("tents", "camping"):
            return mobile_total
        if grp == "rentals":
            return non_mobile_total
        return 0

    out = []
    for (ver, sc), g in frac_long.groupby(["version", "scenario"]):
        for (grp, lvl), sub in g.groupby(["group", "level"]):
            frac = float(sub["fraction"].iloc[0]) if not sub.empty else 0.0
            denom = denom_for_group(grp)
            count = frac * denom
            pct_total = (count / total_inventory) * 100.0 if total_inventory > 0 else 0.0
            out.append({
                "version": ver,
                "scenario": int(sc),
                "group": str(grp),
                "level": int(lvl),
                "pct_total": pct_total
            })
    return pd.DataFrame(out)

# -------- Color configuration --------
def apply_palette(palette_name: str):
    """
    Update global COLORS from a matplotlib palette.
    - For sequential palettes (e.g., 'RdPu'), we auto-skip the lightest color.
    - For reversed palettes like 'RdPu_r', we do NOT skip.
    """
    global COLORS
    if not palette_name:
        return

    name_lower = palette_name.lower()
    cmap = plt.get_cmap(palette_name)

    n_needed = len(STACK_ORDER)

    # If it's a sequential palette (not reversed), skip the first (lightest) color
    if (name_lower in SEQUENTIAL_PALETTES) and not name_lower.endswith("_r"):
        samples = [cmap(i / n_needed) for i in range(1, n_needed + 1)]
    else:
        if n_needed == 1:
            samples = [cmap(0.6)]
        else:
            samples = [cmap(i / (n_needed - 1)) for i in range(n_needed)]

    for key, col in zip(STACK_ORDER, samples):
        COLORS[key] = col

def apply_custom_colors(color_list_str: str):
    """
    Override COLORS completely using a comma-separated list of colors.
    Mapped in order to: mobile1, mobile2, non_mobile1, non_mobile2.
    """
    global COLORS
    raw = [c.strip() for c in color_list_str.split(",") if c.strip()]
    if not raw:
        return
    rgba = [to_rgba(c) for c in raw]
    for i, key in enumerate(STACK_ORDER):
        COLORS[key] = rgba[i % len(rgba)]

# -------- Plotting --------
def stacked_bars_for_version(df_pct: pd.DataFrame, version: str, outdir: Path, title_prefix: str, transparent: bool):
    """Make one stacked bar figure for a single version."""
    sub = df_pct[df_pct["version"] == version].copy()
    if sub.empty:
        return
    scenarios = sorted(sub["scenario"].unique())
    x = np.arange(len(scenarios))

    # Build per-stack series
    stacks = {}
    for key in STACK_ORDER:
        g, l = key
        y = (sub[(sub["group"].str.lower() == g) & (sub["level"] == l)]
             .set_index("scenario")
             .reindex(scenarios, fill_value=0.0)["pct_total"]
             .values.astype(float))
        if y.sum() > 0:
            stacks[key] = y

    fig, ax = plt.subplots(figsize=(12, 6))
    bottom = np.zeros(len(scenarios), dtype=float)

    for key in STACK_ORDER:
        if key not in stacks:
            continue
        y = stacks[key]
        ax.bar(
            x, y, bottom=bottom,
            color=COLORS[key],
            label=LABELS[key],
            width=0.85,
            edgecolor="white", linewidth=0.5
        )
        bottom += y

    ax.set_xticks(x)
    ax.set_xticklabels([str(s) for s in scenarios])  # labels themselves
    # ↑ keep those, then bump tick label size:
    tick_fs = 18
    ax.tick_params(axis="x", which="both", labelsize=tick_fs)
    ax.tick_params(axis="y", which="both", labelsize=tick_fs)
    #ax.set_xlabel("Scenario (mm/h)", fontsize=18)
    #ax.set_ylabel("(%) of impact - camping pitches ", fontsize=18)
    #ax.set_title(f"{title_prefix} — {pretty_version_for_title(version)} (%) distribution of impact classes", fontsize=18)

    # 🔹 increase tick label sizes
    ax.tick_params(axis="both", which="major", labelsize=18)

    # 🔹 bigger legend text
    #ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1.0), fontsize=18)

    ax.margins(x=0.01)
    ax.set_ylim(0, 100)
    fig.tight_layout()
    outpath = outdir / f"{version}_stacked_bars.png"
    fig.savefig(outpath, dpi=150, bbox_inches="tight", transparent=transparent)
    plt.close(fig)
    print("Saved:", outpath)

# -------- CLI --------
def main():
    ap = argparse.ArgumentParser(description="Make stacked bar charts from fractions_long.csv (mobile / non_mobile).")
    ap.add_argument("--fractions-long", dest="fractions_long", help="Path to fractions_long.csv from the simplified overlay.")
    ap.add_argument("--fractions", dest="fractions_long", help="Alias of --fractions-long", required=False)
    ap.add_argument("--totals", required=True, help="Path to totals CSV or exposure XLSX (sheet 'site_totals').")
    ap.add_argument("--outdir", required=True, help="Where to write PNGs.")
    ap.add_argument("--title-prefix", default="portions_by_version", help="Prefix text for figure titles.")
    ap.add_argument("--palette", default=None,
                    help="Matplotlib palette (e.g. 'RdPu', 'RdPu_r', 'tab10', 'Set2', 'Dark2', 'Paired'). "
                         "Sequential palettes auto-skip the lightest shade.")
    ap.add_argument("--colors", default=None,
                    help="Comma-separated list of explicit colors to override the palette "
                         "(mapped in order to: mobile1, mobile2, non_mobile1, non_mobile2).")
    ap.add_argument("--transparent", action="store_true",
                    help="If set, saves PNGs with transparent background instead of white.")
    args = ap.parse_args()

    if not args.fractions_long:
        raise SystemExit("Please provide --fractions-long (or --fractions).")

    outdir = Path(args.outdir); outdir.mkdir(parents=True, exist_ok=True)

    # Apply color settings
    if args.palette:
        apply_palette(args.palette)
    if args.colors:
        apply_custom_colors(args.colors)

    # Load data
    frac_long = pd.read_csv(args.fractions_long)
    needed = {"version","group","level","scenario","fraction"}
    missing = needed - set(frac_long.columns)
    if missing:
        raise ValueError(f"fractions_long is missing columns: {missing}")

    frac_long["scenario"] = pd.to_numeric(frac_long["scenario"], errors="coerce")
    frac_long = frac_long.dropna(subset=["scenario"])
    frac_long["level"] = frac_long["level"].astype(int)
    # Ensure groups are lower case for matching
    frac_long["group"] = frac_long["group"].astype(str).str.lower()

    totals = read_totals(Path(args.totals))
    df_pct = build_percentage_of_total(frac_long, totals)

    for v in sorted(df_pct["version"].unique()):
        stacked_bars_for_version(df_pct, v, outdir, args.title_prefix, transparent=args.transparent)

if __name__ == "__main__":
    main()