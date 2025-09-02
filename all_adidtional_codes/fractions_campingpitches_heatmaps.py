#!/usr/bin/env python3
import argparse
import re
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm

# ----- Labels and component order -----
LABELS = {
    ("tents", 1):   "tents ≥0.10 m",
    ("camping", 1): "camping 0.10–0.30 m",
    ("camping", 2): "camping ≥0.30 m",
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

# Short names for titles
VERSION_TEXT = {"v2": "s2", "v4": "s4", "v5": "s5", "v6": "s6"}

# ---------- helpers ----------
def infer_site_prefix(name: str) -> str:
    m = re.match(r"^(.*)_v\d+$", name)
    return m.group(1) if m else name

def parse_version_specs(specs):
    out = []
    for s in specs:
        if "=" not in s:
            raise ValueError("Each --version must be like v2=/path/to/folder")
        label, d = s.split("=", 1)
        dpath = Path(d.strip())
        if not dpath.is_dir():
            raise FileNotFoundError(f"Version folder not found: {dpath}")
        out.append((label.strip(), dpath))
    return out

def find_fractions_csv(vdir: Path) -> Path:
    p = vdir / "fractions_long.csv"
    if not p.exists():
        raise FileNotFoundError(f"Missing fractions_long.csv in {vdir}")
    return p

def read_fractions_long(vdir: Path) -> pd.DataFrame:
    """
    Read fractions_long.csv and return columns:
      version, group, level, scenario, fraction
    NOTE: 'fraction' is per-group (count / group_total), 0..1.
    """
    p = find_fractions_csv(vdir)
    df = pd.read_csv(p)
    # basic hygiene
    needed = {"version", "group", "level", "scenario", "fraction"}
    if not needed.issubset(df.columns):
        raise ValueError(f"{p} must contain columns {sorted(needed)}")
    df = df.copy()
    df["scenario"] = pd.to_numeric(df["scenario"], errors="coerce")
    df = df.dropna(subset=["scenario"])
    df["scenario"] = df["scenario"].astype(int)
    df["level"] = pd.to_numeric(df["level"], errors="coerce").astype(int)
    df["group"] = df["group"].astype(str).str.lower()
    df["fraction"] = pd.to_numeric(df["fraction"], errors="coerce")
    df = df.dropna(subset=["fraction"]).reset_index(drop=True)
    return df[["version","group","level","scenario","fraction"]]

def read_site_totals(path: Path):
    """Return (tents_total, camping_total, rentals_total) from CSV or XLSX."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(str(path))
    if path.suffix.lower() == ".csv":
        t = pd.read_csv(path).iloc[0]
    else:
        t = pd.read_excel(path, sheet_name="site_totals").iloc[0]
    tents   = int(t.get("tents_total", 0))
    camping = int(t.get("camping_pitches_total", 0))
    rentals = int(t.get("rentals_total", 0))
    return tents, camping, rentals

def auto_find_totals(version_dirs):
    """Search any version dir for '*_exposure.xlsx' and read totals."""
    for _, vdir in version_dirs:
        found = list(vdir.glob("*_exposure.xlsx"))
        if found:
            return read_site_totals(found[0])
    raise FileNotFoundError(
        "Could not auto-detect totals. Pass --totals pointing to the exposure XLSX "
        "(sheet 'site_totals') or a CSV with tents_total,camping_pitches_total,rentals_total."
    )

def choose_components(df_long: pd.DataFrame):
    present = set(zip(df_long["group"], df_long["level"]))
    return [k for k in STACK_ORDER if k in present]

# ---------- percent builders ----------
def build_matrix_percent(df_long: pd.DataFrame, version: str, scenarios, keys,
                         mode: str, totals=None) -> np.ndarray:
    """
    mode = 'per-group'  -> % of that group (100 * fraction)
         = 'of-total'   -> % of total inventory:
                           (fraction * group_total) / (tents+camping+rentals) * 100
    """
    sub = df_long[df_long["version"] == version]
    M = []
    tents=camping=rentals=0
    total_inv = None
    if mode == "of-total":
        tents, camping, rentals = totals
        total_inv = max(tents + camping + rentals, 1)

    for g, l in keys:
        s = (sub[(sub["group"] == g) & (sub["level"] == l)]
               .set_index("scenario")["fraction"])
        frac = s.reindex(scenarios).astype(float).values  # per-group fraction (0..1)

        if mode == "per-group":
            y = 100.0 * frac
        else:
            denom = tents if g == "tents" else camping if g == "camping" else rentals
            counts = frac * float(denom)          # convert back to counts
            y = (counts / float(total_inv)) * 100 # % of total inventory
        M.append(y)

    return np.vstack(M) if M else np.zeros((0, len(scenarios)))

# ---------- drawing helpers ----------
def annotate_cells(ax, data, fmt="{:.0f}", fontsize=15, color="black", bold_zero=False):
    nrows, ncols = data.shape
    for i in range(nrows):
        for j in range(ncols):
            val = data[i, j]
            if not np.isfinite(val):
                continue
            txt = fmt.format(val)
            kw = dict(ha="center", va="center", fontsize=fontsize, color=color)
            if bold_zero and abs(val) < 0.5:
                kw["fontweight"] = "bold"
                kw["alpha"] = 0.7
            ax.text(j, i, txt, **kw)

def plot_baseline_heatmap(ax, M_base, scenarios, row_labels, vmax=None, cmap="Reds"):
    finite_vals = M_base[np.isfinite(M_base)]
    if vmax is None:
        vmax = np.percentile(finite_vals, 95) if finite_vals.size else 100.0
        vmax = min(max(vmax, 1.0), 100.0)
    im = ax.imshow(M_base, aspect="auto", cmap=cmap, vmin=0, vmax=vmax)
    ax.set_xticks(np.arange(len(scenarios)))
    ax.set_xticklabels([str(s) for s in scenarios], rotation=0, fontsize=18)
    ax.set_yticks(np.arange(len(row_labels)))
    ax.set_yticklabels(row_labels, fontsize=18)
    annotate_cells(ax, M_base, fmt="{:.0f}", color="black")
    return im

def plot_delta_heatmap(ax, M_delta, scenarios, row_labels, cmap="RdBu_r"):
    finite = M_delta[np.isfinite(M_delta)]
    amax = float(np.max(np.abs(finite))) if finite.size else 1.0
    amax = max(amax, 1.0)
    norm = TwoSlopeNorm(vmin=-amax, vcenter=0.0, vmax=amax)
    im = ax.imshow(M_delta, aspect="auto", cmap=cmap, norm=norm)
    ax.set_xticks(np.arange(len(scenarios)))
    ax.set_xticklabels([str(s) for s in scenarios], rotation=0, fontsize=18)
    ax.set_yticks(np.arange(len(row_labels)))
    ax.set_yticklabels(row_labels, fontsize=18)
    annotate_cells(ax, M_delta, fmt="{:+.0f}", color="black")
    ax.axhline(-0.5, color="k", lw=0.5)
    ax.axvline(-0.5, color="k", lw=0.5)
    return im, norm.vmin, norm.vmax

# ---------- main plot ----------
def make_fraction_heatmap_summary(version_dirs, outdir, base_version="v2",
                                  compare_versions=("v4","v5","v6"),
                                  title_prefix="", transparent=False,
                                  percent_mode="of-total", totals_path=None):

    # Read and combine fractions_long
    frames = []
    for vlabel, vdir in version_dirs:
        df = read_fractions_long(vdir)
        # enforce CLI label, in case the CSV has another label
        df["version"] = vlabel
        frames.append(df[["version","group","level","scenario","fraction"]])
    df_all = pd.concat(frames, ignore_index=True)

    # totals (needed for of-total)
    if percent_mode == "of-total":
        totals = read_site_totals(Path(totals_path)) if totals_path else auto_find_totals(version_dirs)
    else:
        totals = None

    # Which rows to show
    keys = choose_components(df_all)
    if not keys:
        raise SystemExit("No fraction rows present—nothing to plot.")

    row_labels = [LABELS[k] for k in keys]
    scenarios = sorted(df_all["scenario"].unique().tolist())

    # Matrices (% according to selected mode)
    M_base = build_matrix_percent(df_all, base_version, scenarios, keys,
                                  mode=percent_mode, totals=totals)

    M_deltas = []
    for v in compare_versions[:3]:
        if v in df_all["version"].unique():
            M_tgt = build_matrix_percent(df_all, v, scenarios, keys,
                                         mode=percent_mode, totals=totals)
            M_deltas.append((v, M_tgt - M_base))  # percentage points

    # Layout
    fig, axes = plt.subplots(2, 2, figsize=(14, 9), sharex=True, sharey=True)
    if transparent:
        fig.patch.set_alpha(0.0)
        for ax in axes.ravel():
            ax.set_facecolor("none")

    ax_base = axes[0, 0]
    other_axes = [axes[0, 1], axes[1, 0], axes[1, 1]]

    # Titles/labels
    site_title = (title_prefix + " — ") if title_prefix else ""
    base_text = VERSION_TEXT.get(base_version, base_version)
    suffix = "(% of total inventory)" if percent_mode == "of-total" else "(% of group affected)"
    ax_base.set_title(f"{site_title}Scenario: {base_text} {suffix}", fontsize=18)

    im_base = plot_baseline_heatmap(ax_base, M_base, scenarios, row_labels, vmax=None, cmap="Reds")
    ax_base.set_xlabel("Scenario (mm/h)", fontsize=18)

    im_delta = None
    for ax, pair in zip(other_axes, M_deltas):
        v, M_delta = pair
        v_text = VERSION_TEXT.get(v, v)
        ax.set_title(f"{v_text} − {base_text} (Δ percentage points)", fontsize=18)
        im_delta, vmin, vmax = plot_delta_heatmap(ax, M_delta, scenarios, row_labels, cmap="RdBu_r")
        ax.set_xlabel("Scenario (mm/h)", fontsize=18)

    # Colorbars
    cbar1 = fig.colorbar(im_base, ax=ax_base, fraction=0.046, pad=0.04, shrink=0.8)
    cbar1.set_label("% of total inventory" if percent_mode == "of-total" else "% affected (per group)", fontsize=18)
    cbar1.ax.tick_params(labelsize=18)

    used_axes = [ax for ax, pair in zip(other_axes, M_deltas)]
    if used_axes and im_delta is not None:
        cbar_ax = fig.add_axes([1.00, 0.15, 0.02, 0.70])
        cbar2 = fig.colorbar(im_delta, cax=cbar_ax)
        cbar2.set_label("Δ percentage points", fontsize=18)
        cbar2.ax.tick_params(labelsize=18)

    fig.tight_layout()
    plt.subplots_adjust(wspace=0.35)

    # Save
    first_dir = version_dirs[0][1]
    site_prefix = infer_site_prefix(first_dir.name)
    outdir = Path(outdir) if outdir else first_dir.parent / f"{site_prefix}_all_versions"
    outdir.mkdir(parents=True, exist_ok=True)
    out_png = outdir / f"{site_prefix}_fractions_heatmaps_{percent_mode}_baseline_{base_version}.png"
    fig.savefig(out_png, dpi=300, bbox_inches="tight", transparent=transparent)
    plt.close(fig)
    print(f"Saved: {out_png}")

# ---------- CLI ----------
def main():
    ap = argparse.ArgumentParser(
        description="Heatmaps from fractions_long.csv: baseline + Δ (s4−s2, s5−s2, s6−s2). "
                    "Percent can be per-group or of total inventory."
    )
    ap.add_argument("--version", action="append", required=True,
                    help='Repeat: vLABEL=/path/to/<Site>_2m_vLABEL (e.g., v2=/.../Morges_2m_v2)')
    ap.add_argument("--outdir", default=None,
                    help="Output folder for the PNG. Default: <site>_all_versions next to first version.")
    ap.add_argument("--base-version", default="v2", help="Baseline version label (default: v2).")
    ap.add_argument("--compare-versions", nargs="+", default=["v4","v5","v6"],
                    help="Versions to compare (up to 3 drawn).")
    ap.add_argument("--title-prefix", default="", help='Prefix for the baseline title (e.g., "Morges (2m)").')
    ap.add_argument("--transparent", action="store_true",
                    help="Save PNG with transparent background.")
    ap.add_argument("--percent-mode", choices=["of-total","per-group"], default="of-total",
                    help="How to compute percentages. Default: of-total (matches your stacked bars).")
    ap.add_argument("--totals", default=None,
                    help="Path to site_totals CSV/XLSX. If omitted with --percent-mode of-total, I will auto-detect *_exposure.xlsx in a version folder.")
    args = ap.parse_args()

    version_dirs = parse_version_specs(args.version)
    make_fraction_heatmap_summary(
        version_dirs=version_dirs,
        outdir=args.outdir,
        base_version=args.base_version,
        compare_versions=args.compare_versions,
        title_prefix=args.title_prefix,
        transparent=args.transparent,
        percent_mode=args.percent_mode,
        totals_path=args.totals
    )

if __name__ == "__main__":
    main()