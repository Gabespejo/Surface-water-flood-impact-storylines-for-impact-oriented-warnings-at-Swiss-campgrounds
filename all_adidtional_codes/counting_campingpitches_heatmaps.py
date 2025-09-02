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

def read_counts_pivot(vdir: Path) -> pd.DataFrame:
    p = vdir / "counts_pivot.csv"
    if not p.exists():
        raise FileNotFoundError(f"Missing counts_pivot.csv in {vdir}")
    df = pd.read_csv(p)
    # expected cols: scenario, group, level, count, and optionally *_total
    # Clean types
    df["scenario"] = pd.to_numeric(df["scenario"], errors="coerce")
    df = df.dropna(subset=["scenario"]).copy()
    df["scenario"] = df["scenario"].astype(int)
    df["level"] = pd.to_numeric(df["level"], errors="coerce").astype("Int64")
    df["group"] = df["group"].astype(str).str.lower()
    return df

def choose_components(df: pd.DataFrame) -> list[tuple[str,int]]:
    """
    Show only components that have inventory (>0) if totals columns exist.
    If no totals columns, show components that ever appear in counts.
    """
    keys = []
    # Try totals
    tents_total = df.filter(regex=r"^tents_total$", axis=1)
    camp_total  = df.filter(regex=r"camping.*_total$", axis=1)
    rent_total  = df.filter(regex=r"rentals.*_total$", axis=1)

    def has_total(series_like):
        if series_like.shape[1] == 0:
            return None
        s = series_like.iloc[:,0]
        # totals are repeated per row; pick first non-null numeric
        v = pd.to_numeric(s, errors="coerce").dropna()
        return (v.iloc[0] if not v.empty else 0) > 0

    tents_ok = has_total(tents_total)
    camp_ok  = has_total(camp_total)
    rent_ok  = has_total(rent_total)

    if tents_ok is None and camp_ok is None and rent_ok is None:
        # fallback: presence in counts
        present = set(zip(df["group"], df["level"].astype(int)))
        for k in STACK_ORDER:
            if k in present:
                keys.append(k)
        return keys

    if tents_ok:
        keys.append(("tents", 1))
    if camp_ok:
        keys.extend([("camping", 1), ("camping", 2)])
    if rent_ok:
        keys.extend([("rentals", 1), ("rentals", 2)])
    return keys

def build_matrix_counts(df_all: pd.DataFrame, version: str, scenarios: list[int], keys: list[tuple[str,int]]) -> np.ndarray:
    M = []
    sub = df_all[df_all["version"] == version]
    for g,l in keys:
        y = (sub[(sub["group"]==g) & (sub["level"]==l)]
             .set_index("scenario")
             .reindex(scenarios, fill_value=0)["count"]
             .values.astype(float))
        M.append(y)
    return np.vstack(M) if M else np.zeros((0, len(scenarios)))

def annotate_cells(ax, data, fmt="{:d}",fontsize=15 ,color="black", bold_zero=False):
    """
    Put numbers into heatmap cells. data is 2D array.
    For float data, values are rounded for display.
    """
    nrows, ncols = data.shape
    for i in range(nrows):
        for j in range(ncols):
            val = data[i, j]
            if np.isnan(val):
                continue
            txt = fmt.format(int(round(val)))
            kw = dict(ha="center", va="center", fontsize=fontsize, color=color)
            if bold_zero and int(round(val)) == 0:
                kw["fontweight"] = "bold"
                kw["alpha"] = 0.6
            ax.text(j, i, txt, **kw)

def plot_baseline_heatmap(ax, M_base, scenarios, row_labels, vmax=None, cmap="Reds"):
    if vmax is None:
        vmax = np.nanpercentile(M_base, 95) if np.isfinite(M_base).any() else 1.0
        vmax = max(vmax, 1.0)
    im = ax.imshow(M_base, aspect="auto", cmap=cmap, vmin=0, vmax=vmax)
    ax.set_xticks(np.arange(len(scenarios)))
    ax.set_xticklabels([str(s) for s in scenarios], rotation=0)
    ax.set_yticks(np.arange(len(row_labels)))
    ax.set_yticklabels(row_labels)
    annotate_cells(ax, M_base, fmt="{:d}", color="black")
    return im

def plot_delta_heatmap(ax, M_delta, scenarios, row_labels, cmap="RdBu_r"):
    # symmetric limits around 0
    amax = float(np.nanmax(np.abs(M_delta))) if M_delta.size else 1.0
    amax = max(amax, 1.0)
    norm = TwoSlopeNorm(vmin=-amax, vcenter=0.0, vmax=amax)
    im = ax.imshow(M_delta, aspect="auto", cmap=cmap, norm=norm)
    ax.set_xticks(np.arange(len(scenarios)))
    ax.set_xticklabels([str(s) for s in scenarios], rotation=0)
    ax.set_yticks(np.arange(len(row_labels)))
    ax.set_yticklabels(row_labels)
    annotate_cells(ax, M_delta, fmt="{:+d}", color="black")
    ax.axhline(-0.5, color="k", lw=0.5)  # frame lines help reading
    ax.axvline(-0.5, color="k", lw=0.5)
    return im, norm.vmin, norm.vmax

# ---------- main plot ----------
def make_counts_heatmap_summary(version_dirs, outdir, base_version="v2", compare_versions=("v4","v5","v6"), title_prefix=""):
    # Read & combine
    frames = []
    for vlabel, vdir in version_dirs:
        df = read_counts_pivot(vdir)
        df["version"] = vlabel
        frames.append(df[["version","scenario","group","level","count"] + [c for c in df.columns if c.endswith("_total")]])
    df_all = pd.concat(frames, ignore_index=True)

    # Components to show (drop groups with zero inventory)
    keys = choose_components(df_all)
    if not keys:
        raise SystemExit("No components with inventory > 0 or with counts—nothing to plot.")

    row_labels = [LABELS[k] for k in keys]

    # Scenarios (union to align axes)
    scenarios = sorted(df_all["scenario"].unique().tolist())

    # Matrices
    M_base = build_matrix_counts(df_all, base_version, scenarios, keys)
    M_deltas = []
    for v in compare_versions[:3]:
        if v in df_all["version"].unique():
            M_tgt = build_matrix_counts(df_all, v, scenarios, keys)
            M_deltas.append((v, M_tgt - M_base))

    # Layout
    fig, axes = plt.subplots(2, 2, figsize=(14, 9), sharex=True, sharey=True)
    ax_base = axes[0,0]
    other_axes = [axes[0,1], axes[1,0], axes[1,1]]

    # Baseline
    site_title = (title_prefix + " — ") if title_prefix else ""
    base_text = VERSION_TEXT.get(base_version, base_version)
    ax_base.set_title(f"{site_title}Scenario: {base_text} (counts)", fontsize=18)
    im_base = plot_baseline_heatmap(ax_base, M_base, scenarios, row_labels, vmax=None, cmap="Reds")
    ax_base.set_xlabel("Scenario (mm/h)", fontsize=18)
    ax_base.set_ylabel("", fontsize=18)
    ax_base.tick_params(axis='both', which='major', labelsize=18)

# Deltas
    for ax, pair in zip(other_axes, M_deltas):
        v, M_delta = pair
        v_text = VERSION_TEXT.get(v, v)
        ax.set_title(f"{v_text} − {base_text} (Δ counts)", fontsize=18)
        im_delta, vmin, vmax = plot_delta_heatmap(ax, M_delta, scenarios, row_labels, cmap="RdBu_r")
        ax.set_xlabel("Scenario (mm/h)", fontsize=18)
        ax.set_ylabel("", fontsize=18)
        ax.tick_params(axis='both', which='major', labelsize=18)

     # Base counts colorbar
    cbar1 = fig.colorbar(im_base, ax=ax_base, fraction=0.046, pad=0.04, shrink=0.8)
    cbar1.set_label("camping pitches affected", fontsize=18)
    cbar1.ax.tick_params(labelsize=18)

    # Delta counts colorbar (shared for all deltas)
    used_axes = [ax for ax, pair in zip(other_axes, M_deltas)]
    if used_axes:
        # manual placement to avoid overlap
        cbar_ax = fig.add_axes([1.2, 0.15, 0.02, 0.7])  # [left, bottom, width, height]
        cbar2 = fig.colorbar(im_delta, cax=cbar_ax)
        cbar2.set_label("Δ count ((S6/S5/S4) − S2)", fontsize=18)
        cbar2.ax.tick_params(labelsize=18)

    fig.tight_layout()
    # Adjust subplot spacing to push 2nd column further right
    plt.subplots_adjust(wspace=0.35)  # increase horizontal space between columns

    # Save
    first_dir = version_dirs[0][1]
    site_prefix = infer_site_prefix(first_dir.name)
    outdir = Path(outdir) if outdir else first_dir.parent / f"{site_prefix}_all_versions"
    outdir.mkdir(parents=True, exist_ok=True)
    out_png = outdir / f"{site_prefix}_counts_heatmaps_baseline_{base_version}.png"
    fig.savefig(out_png, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out_png}")
# ---------- CLI ----------
def main():
    ap = argparse.ArgumentParser(description="Counts heatmaps: baseline + Δ (s4−s2, s5−s2, s6−s2) with numbers in cells.")
    ap.add_argument("--version", action="append", required=True,
                    help='Repeat: vLABEL=/path/to/<Site>_2m_vLABEL (e.g., v2=/.../Morges_2m_v2)')
    ap.add_argument("--outdir", default=None,
                    help="Output folder for the PNG. Default: <site>_all_versions next to first version.")
    ap.add_argument("--base-version", default="v2", help="Baseline version label (default: v2).")
    ap.add_argument("--compare-versions", nargs="+", default=["v4","v5","v6"],
                    help="Versions to compare (up to 3 drawn).")
    ap.add_argument("--title-prefix", default="", help='Prefix for the baseline title (e.g., "Morges (2m)").')
    args = ap.parse_args()

    version_dirs = parse_version_specs(args.version)
    make_counts_heatmap_summary(
        version_dirs=version_dirs,
        outdir=args.outdir,
        base_version=args.base_version,
        compare_versions=args.compare_versions,
        title_prefix=args.title_prefix
    )

if __name__ == "__main__":
    main()