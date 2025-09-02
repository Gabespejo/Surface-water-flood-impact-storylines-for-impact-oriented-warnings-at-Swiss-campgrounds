#!/usr/bin/env python3
import argparse
import re
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib import cm

# ----- Labels and stack order -----
LABELS = {
    ("tents", 1):   "tents sector (≥0.10 m)",
    ("camping", 1): "camping pitches 0.10–0.30 m",
    ("camping", 2): "camping pitches ≥0.30 m",
    ("rentals", 1): "rentals 0.10–<1.0 m",
    ("rentals", 2): "rentals ≥1.0 m",
}
STACK_ORDER = [
    ("tents", 1),
    ("camping", 1),
    ("camping", 2),
    ("rentals", 1),
    ("rentals", 2),
]

# Baseline (top-left) panel colors – pink family
BASELINE_COLORS = {
    ("tents", 1):   "#fde0dd",
    ("camping", 1): "#fa9fb5",
    ("camping", 2): "#c51b8a",
    ("rentals", 1): "#f768a1",
    ("rentals", 2): "#7a0177",
}

# Short names for titles
VERSION_TEXT = {
    "v2": "s2",
    "v4": "s4",
    "v5": "s5",
    "v6": "s6",
}

SEQUENTIAL_PALETTES = {
    "rdpu","reds","blues","greens","oranges","purples",
    "ylgn","ylgnbu","ylorbr","ylorrd","purd","pubu","bugn","bupu","gnbu"
}

# ---------- I/O helpers ----------
def infer_site_prefix(folder_name: str) -> str:
    m = re.match(r"^(.*)_v\d+$", folder_name)
    return m.group(1) if m else folder_name

def parse_version_specs(specs):
    out = []
    for s in specs:
        if "=" not in s:
            raise ValueError("Each --version must be like v2=/path/to/folder")
        label, d = s.split("=", 1)
        label = label.strip()
        dpath = Path(d.strip())
        if not dpath.is_dir():
            raise FileNotFoundError(f"Version folder not found: {dpath}")
        out.append((label, dpath))
    return out

def find_fractions_csv(vdir: Path) -> Path:
    p = vdir / "fractions_long.csv"
    if not p.exists():
        raise FileNotFoundError(f"Missing fractions_long.csv in {vdir}")
    return p

def read_totals_from(path: Path):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(str(path))
    if path.suffix.lower() == ".csv":
        t = pd.read_csv(path).iloc[0]
    else:
        t = pd.read_excel(path, sheet_name="site_totals").iloc[0]
    tents = int(t.get("tents_total", 0))
    camping = int(t.get("camping_pitches_total", 0))
    rentals = int(t.get("rentals_total", 0))
    return tents, camping, rentals

def auto_find_totals(version_dirs):
    for _, vdir in version_dirs:
        found = list(vdir.glob("*_exposure.xlsx"))
        if found:
            return read_totals_from(found[0])
    raise FileNotFoundError(
        "Could not auto-detect totals. Pass --totals pointing to the exposure XLSX "
        "(sheet 'site_totals') or a CSV with tents_total,camping_pitches_total,rentals_total."
    )

# ---------- Data transforms ----------
def pct_of_total(frac_long: pd.DataFrame, totals):
    tents, camp, rents = totals
    total_inv = max(tents + camp + rents, 1)
    rows = []
    for (ver, sc), g in frac_long.groupby(["version", "scenario"]):
        for (grp, lvl), sub in g.groupby(["group", "level"]):
            frac = float(sub["fraction"].iloc[0]) if not sub.empty else 0.0
            denom = tents if grp == "tents" else camp if grp == "camping" else rents
            pct_total = (frac * denom) / total_inv * 100.0
            rows.append({
                "version": ver,
                "scenario": int(sc),
                "group": grp,
                "level": int(lvl),
                "pct_total": pct_total
            })
    return pd.DataFrame(rows)

def matrix_for_version(df_pct, version, scenarios):
    M = []
    for key in STACK_ORDER:
        g, l = key
        y = (df_pct[(df_pct["version"] == version) &
                    (df_pct["group"] == g) &
                    (df_pct["level"] == l)]
             .set_index("scenario")
             .reindex(scenarios, fill_value=0.0)["pct_total"]
             .values.astype(float))
        M.append(y)
    return np.vstack(M)

# ---------- Color config for Δ panels ----------
def palette_samples(palette_name, n):
    name_lower = palette_name.lower()
    cmap = plt.get_cmap(palette_name)
    if (name_lower in SEQUENTIAL_PALETTES) and not name_lower.endswith("_r"):
        # Skip lightest shade for sequential palettes
        return [cmap(i / n) for i in range(1, n + 1)]
    # Otherwise sample evenly across palette
    return [cmap(i / max(1, (n - 1))) for i in range(n)]

def parse_color_list(color_str, n):
    cols = [c.strip() for c in color_str.split(",") if c.strip()]
    if len(cols) < n:
        raise ValueError(f"--delta-colors needs {n} colors (got {len(cols)})")
    return cols[:n]

# ---------- Plot ----------
def make_all_in_one_summary(
    frac_long, totals, base_version, compare_versions, out_png,
    title_prefix="", delta_palette=None, delta_colors=None, show_legend=False,
    transparent=False
):
    df_pct = pct_of_total(frac_long, totals)
    scenarios = sorted(df_pct["scenario"].unique())
    x = np.arange(len(scenarios))
    M_base = matrix_for_version(df_pct, base_version, scenarios)

    # Δ colors per component
    if delta_colors:
        comp_colors = parse_color_list(delta_colors, len(STACK_ORDER))
    elif delta_palette:
        comp_colors = palette_samples(delta_palette, len(STACK_ORDER))
    else:
        diverge = cm.get_cmap("RdBu_r", 9)
        comp_colors = [diverge(i / 8) for i in range(2, 7)]

    fig, axes = plt.subplots(2, 2, figsize=(14, 9), sharex=True)
    ax_base, ax_d1, ax_d2, ax_d3 = axes[0, 0], axes[0, 1], axes[1, 0], axes[1, 1]
    delta_axes = [ax_d1, ax_d2, ax_d3]

    # ---- Baseline (top-left) ----
    bottom = np.zeros(len(scenarios))
    for key in STACK_ORDER:
        g, l = key
        y = (df_pct[(df_pct["version"] == base_version) &
                    (df_pct["group"] == g) &
                    (df_pct["level"] == l)]
             .set_index("scenario")
             .reindex(scenarios, fill_value=0.0)["pct_total"]
             .values.astype(float))
        ax_base.bar(
            x, y, bottom=bottom,
            color=BASELINE_COLORS.get(key, "C0"),
            edgecolor="white", linewidth=0.5, width=0.85,
            label=LABELS[key]
        )
        bottom += y

    base_text = VERSION_TEXT.get(base_version, base_version)
    title_left = f"{title_prefix} — Scenario: {base_text}" if title_prefix else f"Scenario: {base_text}"
    ax_base.set_title(title_left, fontsize=18)
    ax_base.set_ylabel("% of camping pitches affected", fontsize=18)
    ax_base.set_ylim(0, 100)
    ax_base.margins(y=0.02)

    # ---- Δ panels (top-right, bottom-left, bottom-right) ----
    for ax, v in zip(delta_axes, compare_versions[:3]):
        if v not in df_pct["version"].unique():
            ax.set_visible(False)
            continue
        M_tgt = matrix_for_version(df_pct, v, scenarios)
        D = M_tgt - M_base

        bottom_pos = np.zeros(len(scenarios))
        bottom_neg = np.zeros(len(scenarios))

        for i, key in enumerate(STACK_ORDER):
            vals = D[i]
            pos = np.clip(vals, 0, None)
            neg = np.clip(vals, None, 0)
            col = comp_colors[i]
            if np.any(pos):
                ax.bar(x, pos, bottom=bottom_pos, color=col, width=0.85,
                       edgecolor="white", lw=0.5)
                bottom_pos += pos
            if np.any(neg):
                ax.bar(x, neg, bottom=bottom_neg, color=col, width=0.85,
                       edgecolor="white", lw=0.5)
                bottom_neg += neg

        # Dynamic symmetric limits from stacked extremes + 10% padding
        max_stack = max(bottom_pos.max() if bottom_pos.size else 0.0,
                        abs(bottom_neg.min()) if bottom_neg.size else 0.0)
        pad = 0.10 * (max_stack if max_stack > 0 else 1.0)
        ylim = np.ceil((max_stack + pad) / 2.0) * 2.0
        ax.set_ylim(-ylim, ylim)
        ax.margins(y=0.03)
        ax.axhline(0, color="k", lw=0.8)

        v_text = VERSION_TEXT.get(v, v)
        ax.set_title(f"{v_text} − {base_text} (Δ percentage)", fontsize=18)

    # Axis labels & tick sizes
    for ax in axes[1, :]:
        ax.set_xlabel("Scenario (mm/h)", fontsize=18)
    for ax in axes.ravel():
        ax.set_xticks(x)
        ax.set_xticklabels([str(s) for s in scenarios], fontsize=18)
        ax.tick_params(axis="y", labelsize=18)

    # Legend (off by default; enable with --show-legend)
    if show_legend:
        base_handles = [plt.Rectangle((0, 0), 1, 1, color=BASELINE_COLORS[k]) for k in STACK_ORDER]
        fig.legend(base_handles, [LABELS[k] for k in STACK_ORDER],
                   title="vulnerability to flood hazard",
                   loc="upper right", bbox_to_anchor=(1.20, 1),
                   fontsize=18, title_fontsize=18)

    fig.tight_layout(rect=[0.02, 0.02, 0.98, 0.93])
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=150, bbox_inches="tight", transparent=transparent)
    plt.close(fig)
    print(f"Saved: {out_png}")

# ---------- CLI ----------
def main():
    ap = argparse.ArgumentParser(
        description="All-in-one baseline + delta stacked-bar summary across versions."
    )
    ap.add_argument(
        "--version", action="append", required=True,
        help="Repeat: vLABEL=/path/to/<Site>_2m_vLABEL  (e.g., v2=/.../Gordevio_2m_v2)"
    )
    ap.add_argument(
        "--outdir", default=None,
        help="Where to save the summary PNG. Default: <site_prefix>_all_versions next to the first version folder."
    )
    ap.add_argument(
        "--totals", default=None,
        help="Path to totals CSV or exposure XLSX (sheet 'site_totals'). If omitted, auto-detect '*_exposure.xlsx' in a version folder."
    )
    ap.add_argument("--base-version", default="v2", help="Baseline version (default: v2)")
    ap.add_argument("--compare-versions", nargs="+", default=["v4", "v5", "v6"],
                    help="Versions to compare against baseline (up to 3 rendered).")
    ap.add_argument("--title-prefix", default="", help="Text prefix for the baseline title (e.g., 'Gordevio (2m)')")
    ap.add_argument("--delta-palette", default=None,
                    help="Matplotlib palette for Δ bars (e.g., RdPu, Blues, tab10, Paired). "
                         "Sequential palettes auto-skip the lightest shade.")
    ap.add_argument("--delta-colors", default=None,
                    help="Explicit colors for Δ bars (comma-separated; 5 values).")
    ap.add_argument("--show-legend", action="store_true",
                    help="Show the baseline legend (off by default).")
    ap.add_argument("--transparent", action="store_true",
                    help="Save the figure with a transparent background.")
    args = ap.parse_args()

    version_dirs = parse_version_specs(args.version)
    site_prefix = infer_site_prefix(version_dirs[0][1].name)

    if args.outdir:
        outdir = Path(args.outdir)
    else:
        outdir = version_dirs[0][1].parent / f"{site_prefix}_all_versions"
    outdir.mkdir(parents=True, exist_ok=True)

    totals = read_totals_from(Path(args.totals)) if args.totals else auto_find_totals(version_dirs)

    frames = []
    for vlabel, vdir in version_dirs:
        frac_csv = find_fractions_csv(vdir)
        df = pd.read_csv(frac_csv)
        df["scenario"] = pd.to_numeric(df["scenario"], errors="coerce")
        df = df.dropna(subset=["scenario"]).copy()
        df["scenario"] = df["scenario"].astype(int)
        df["level"] = df["level"].astype(int)
        df["group"] = df["group"].astype(str).str.lower()
        df["version"] = vlabel  # enforce CLI label
        frames.append(df)
    frac_long = pd.concat(frames, ignore_index=True)

    out_png = outdir / f"{site_prefix}_summary_baseline_{args.base_version}.png"

    make_all_in_one_summary(
        frac_long=frac_long,
        totals=totals,
        base_version=args.base_version,
        compare_versions=args.compare_versions,
        out_png=out_png,
        title_prefix=args.title_prefix or site_prefix.replace("_", " "),
        delta_palette=args.delta_palette,
        delta_colors=args.delta_colors,
        show_legend=args.show_legend,
        transparent=args.transparent
    )

if __name__ == "__main__":
    main()