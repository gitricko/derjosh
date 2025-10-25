#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import os
import sys
import re
from datetime import datetime
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker

# -----------------------
# Date/time extraction
# -----------------------

DATE_PATTERNS = [
    r"(20\d{2})[-_](\d{2})[-_](\d{2})",
    r"(\d{4})(\d{2})(\d{2})",
    r"(\d{2})[-_.](\d{2})[-_.](20\d{2})",
]

TIME_PATTERNS = [
    r"[_-](\d{2})[-_](\d{2})\.",
    r"[_-](\d{2})(\d{2})\.",
]

def extract_date_from_filename(fname: str) -> Optional[datetime]:
    base = os.path.basename(fname)
    for pat in DATE_PATTERNS:
        m = re.search(pat, base)
        if m:
            g = m.groups()
            try:
                if len(g) == 3:
                    if len(g[0]) == 4 and len(g[1]) == 2 and len(g[2]) == 2:
                        return datetime(int(g[0]), int(g[1]), int(g[2]))
                    if len(g[2]) == 4:
                        return datetime(int(g[2]), int(g[1]), int(g[0]))
                elif len(g) == 1 and len(g[0]) == 8:
                    return datetime.strptime(g[0], "%Y%m%d")
            except Exception:
                continue
    return None

def extract_time_from_filename(fname: str) -> Optional[Tuple[int, int]]:
    base = os.path.basename(fname)
    for pat in TIME_PATTERNS:
        m = re.search(pat, base)
        if m:
            try:
                h = int(m.group(1)); mi = int(m.group(2))
                if 0 <= h <= 23 and 0 <= mi <= 59:
                    return (h, mi)
            except Exception:
                continue
    return None

def is_weekend(dt: datetime) -> bool:
    return dt.weekday() >= 5

# ---------------------------
# Column normalization
# ---------------------------

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return df

CANDIDATES = {
    "symbol":  [r"^symbol$", r"^ticker$", r"^name$"],
    "price": [r"^price$", r"^last$", r"^close$", r"^mark$"],
    "borrow":  [r"^approx\s*borrow\s*size$"],
}

def find_column(df: pd.DataFrame, key: str, forced: Optional[str] = None) -> Optional[str]:
    if forced and forced in df.columns:
        return forced
    pats = CANDIDATES.get(key, [])
    lower_map = {c.lower(): c for c in df.columns}
    for pat in pats:
        regex = re.compile(pat, re.IGNORECASE)
        for lc, orig in lower_map.items():
            if regex.match(lc):
                return orig
    return None

# ---------------------------
# Robust CSV reader: header & separator detection
# ---------------------------

HEADER_CANDIDATE_PATTERNS = [
    r"^symbol$", r"^ticker$", r"^name$",
    r"^price$", r"^last$", r"^close$", r"^mark$",
    r"^approx\s*borrow\s*size$",
]

def _looks_like_header(tokens):
    for t in tokens:
        tnorm = str(t).strip().strip('"').strip("'").lower()
        for pat in HEADER_CANDIDATE_PATTERNS:
            if re.match(pat, tnorm, flags=re.IGNORECASE):
                return True
    return False

def detect_header_and_sep(path: str, max_lines: int = 80):
    seps = [",", ";", "\t", "|"]
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = []
            for _ in range(max_lines):
                ln = f.readline()
                if ln == "":
                    break
                lines.append(ln)
    except Exception:
        return 0, None

    best = None
    for idx, line in enumerate(lines):
        if not line or line.strip() == "":
            continue
        for sep in seps:
            tokens = [tok for tok in line.rstrip("\n\r").split(sep)]
            if len(tokens) < 2:
                continue
            score = 0
            if _looks_like_header(tokens):
                score += 10
            score += min(len(tokens), 20)
            if best is None or score > best[0]:
                best = (score, idx, sep, tokens)

    if best is not None and _looks_like_header(best[3]):
        return best[1], best[2]
    if best is not None and best[2] is not None:
        return best[1], best[2]
    return 0, None

def read_one_csv(path: str, sep: Optional[str]) -> pd.DataFrame:
    if sep is None:
        hdr_idx, auto_sep = detect_header_and_sep(path)
        try:
            if auto_sep is None:
                return pd.read_csv(path, engine="python", header=0, skiprows=hdr_idx)
            else:
                return pd.read_csv(path, engine="python", sep=auto_sep, header=0, skiprows=hdr_idx)
        except Exception:
            try:
                return pd.read_csv(path, engine="python", sep=";", header=0, skiprows=hdr_idx)
            except Exception:
                return pd.read_csv(path, engine="python", header=0)
    else:
        hdr_idx, _ = detect_header_and_sep(path)
        try:
            return pd.read_csv(path, engine="python", sep=sep, header=0, skiprows=hdr_idx)
        except Exception:
            return pd.read_csv(path, engine="python", sep=sep, header=0)

# ---------------------------
# Robust numeric parsing
# ---------------------------

def _parse_single_number(x):
    if pd.isna(x):
        return pd.NA
    s = str(x).strip()
    if s == "" or s in {"--", "—", "NA", "N/A", "na", "n/a", "None"}:
        return pd.NA
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1]
    s = s.replace(",", "").replace(" ", "")
    if s.endswith("%"):
        s = s[:-1]
    mult = 1.0
    if s.endswith(("K","k")):
        mult = 1_000.0; s = s[:-1]
    elif s.endswith(("M","m")):
        mult = 1_000_000.0; s = s[:-1]
    elif s.endswith(("B","b")):
        mult = 1_000_000_000.0; s = s[:-1]
    s = s.replace("\u2009", "").replace("\u00A0", "")
    try:
        val = float(s) * (-1.0 if neg else 1.0) * mult
        return val
    except Exception:
        return pd.NA

def parse_number_series(series: pd.Series) -> pd.Series:
    return series.map(_parse_single_number).astype("Float64")

# ---------------------------
# Reading and merging files
# ---------------------------

def pick_last_dates(files: List[str], n_days: int, mode: str = "data") -> List[datetime]:
    dates = []
    for f in files:
        dt = extract_date_from_filename(f)
        if dt is None:
            continue
        if mode == "weekday" and is_weekend(dt):
            continue
        dates.append(dt.date())
    uniq = sorted(set(dates))
    if not uniq:
        return []
    return uniq[-n_days:]

def load_and_merge(
    data_dir: str,
    n_days: int = 5,
    sep: Optional[str] = None,
    symbol_col: Optional[str] = None,
    price_col: Optional[str] = None,
    borrow_col: Optional[str] = None,
    date_mode: str = "data",
) -> pd.DataFrame:

    files = [os.path.join(data_dir, f) for f in os.listdir(data_dir) if f.lower().endswith(".csv")]
    if not files:
        raise FileNotFoundError(f"No CSV files found in {data_dir}")

    last_dates = pick_last_dates(files, n_days=n_days, mode=date_mode)
    if not last_dates:
        raise ValueError("No recent dates found based on filename dates.")

    items: List[Tuple[datetime, Optional[Tuple[int,int]], str]] = []
    for f in files:
        dt = extract_date_from_filename(f)
        if dt is None:
            continue
        if date_mode == "weekday" and is_weekend(dt):
            continue
        if dt.date() in last_dates:
            tm = extract_time_from_filename(f)
            items.append((dt, tm, f))

    def sort_key(x):
        dt, tm, _ = x
        return (dt, (tm[0], tm[1]) if tm is not None else (99, 99))
    items.sort(key=sort_key)

    frames = []
    for dt, tm, path in items:
        df = read_one_csv(path, sep=sep)
        df = normalize_columns(df)

        sym = find_column(df, "symbol", symbol_col)
        pri = find_column(df, "price", price_col)
        bor = find_column(df, "borrow", borrow_col)

        missing = [k for k, v in [("symbol", sym), ("price", pri), ("borrow", bor)] if v is None]
        if missing:
            raise ValueError(f"Missing columns {missing} in {os.path.basename(path)}. "
                             f"Detected columns: {list(df.columns)}")

        slim = df[[sym, pri, bor]].rename(columns={sym: "Symbol", pri: "Price", bor: "Borrow"})
        slim["Price"] = parse_number_series(slim["Price"])
        slim["Borrow"] = parse_number_series(slim["Borrow"])

        if tm is not None:
            h, mi = tm
            stamp = datetime(dt.year, dt.month, dt.day, h, mi)
        else:
            stamp = datetime(dt.year, dt.month, dt.day, 0, 0)

        slim["Date"] = dt.date()
        slim["Stamp"] = pd.to_datetime(stamp)

        frames.append(slim)

    all_df = pd.concat(frames, ignore_index=True)
    all_df = all_df.dropna(subset=["Symbol"])
    all_df = all_df.drop_duplicates(subset=["Stamp", "Symbol"], keep="last")
    all_df = all_df.sort_values(["Stamp", "Symbol"]).reset_index(drop=True)

    return all_df

# ---------------------------
# Plotting helpers
# ---------------------------

def _format_time_axis(ax):
    locator = mdates.AutoDateLocator(minticks=4, maxticks=10)
    formatter = mdates.ConciseDateFormatter(locator)
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(formatter)
    ax.tick_params(axis='x', rotation=45)

def _format_index_axis(ax, labels):
    n = len(labels)
    positions = list(range(n))
    ax.set_xticks(positions)
    if n > 12:
        step = max(1, n // 12)
        ax.set_xticks(positions[::step])
        labels = labels[::step]
    ax.set_xticklabels(labels, rotation=45)

def _labels_from_stamps(stamps):
    return [pd.to_datetime(ts).strftime("%Y-%m-%d %H:%M") for ts in stamps]

def _adaptive_bar_width(stamps):
    s = pd.to_datetime(pd.Series(stamps)).sort_values().unique()
    if len(s) < 2:
        return 0.01
    diffs = pd.Series(s).diff().dropna().dt.total_seconds() / 86400.0
    w = float(diffs.min()) * 0.6
    return max(min(w, 0.2), 1/1440)

# --- dynamic y autoscale with padding ---
def _autoscale_y(ax, values, *, include_zero=False, pad=0.10, extra_floor=None):
    vals = np.asarray(values, dtype=float)
    vals = vals[~np.isnan(vals)]
    if vals.size == 0:
        return
    vmin, vmax = float(vals.min()), float(vals.max())
    if extra_floor is not None:
        vmin = min(vmin, float(extra_floor))
        vmax = max(vmax, float(extra_floor))
    if include_zero:
        vmin = min(vmin, 0.0)
        vmax = max(vmax, 0.0)
    span = vmax - vmin
    if span == 0.0:
        span = abs(vmax) if vmax != 0 else 1.0
    pad_abs = span * float(pad)
    ax.set_ylim(vmin - pad_abs, vmax + pad_abs)

def _pretty_big_y(ax, *, compact=False):
    """
    Removes the 1e6 offset display and formats Y-ticks.
    compact=False -> 2,500,000
    compact=True  -> 2.5M / 2.5k / 2.5B
    """
    # keine wissenschaftliche Notation/Offset
    ax.ticklabel_format(axis="y", style="plain", useOffset=False, useMathText=False)

    if not compact:
        ax.yaxis.set_major_formatter(
            mticker.FuncFormatter(lambda x, pos: f"{x:,.0f}")
        )
    else:
        def _abbr(x):
            axx = abs(x)
            if axx >= 1e9:  return f"{x/1e9:.1f}B"
            if axx >= 1e6:  return f"{x/1e6:.1f}M"
            if axx >= 1e3:  return f"{x/1e3:.1f}k"
            return f"{x:.0f}"
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, pos: _abbr(x)))

# ---------------------------
# Ranking helper
# ---------------------------

def rank_symbols(all_df: pd.DataFrame, mode: str, topN: Optional[int] = None) -> list:
    mode = (mode or "alpha").lower()
    if mode == "alpha":
        syms = sorted(all_df["Symbol"].dropna().unique().tolist())
        return syms if topN is None else syms[:topN]

    if mode == "borrow":
        rank = all_df.groupby("Symbol")["Borrow"].sum().sort_values(ascending=False)
        syms = list(rank.index)
        return syms if topN is None else syms[:topN]

    # dev_cum: current deviation |Price_last - BZAP_cum_last|
    rows = []
    for sym, g in all_df.groupby("Symbol"):
        g = g.sort_values("Stamp")
        cum_num = (g["Price"].astype(float) * g["Borrow"].astype(float)).cumsum()
        cum_den = g["Borrow"].astype(float).cumsum().replace(0, np.nan)
        bzap_cum = (cum_num / cum_den).astype(float)
        valid = (~bzap_cum.isna()) & (~g["Price"].isna())
        if not valid.any():
            dev = np.nan
            ts_last = g["Stamp"].max()
        else:
            idx_last = valid[valid].index[-1]
            dev = abs(float(g.loc[idx_last, "Price"]) - float(bzap_cum.loc[idx_last]))
            ts_last = g.loc[idx_last, "Stamp"]
        rows.append((sym, dev, ts_last))
    df = pd.DataFrame(rows, columns=["Symbol","DevCum","StampLast"])
    df["DevSort"] = df["DevCum"].fillna(-1)
    df = df.sort_values(["DevSort","StampLast"], ascending=[False, False])
    syms = df["Symbol"].tolist()
    return syms if topN is None else syms[:topN]

# ---------------------------
# Grid Overview
# ---------------------------

def plot_grid_overview(all_df: pd.DataFrame, topN: int = 9, x_mode: str = "time",
                       overview_rank: str = "dev_cum", symbols: Optional[list] = None):
    if symbols is None:
        symbols = rank_symbols(all_df, overview_rank, topN)

    n = len(symbols)
    if n == 0:
        print("No symbols to plot.")
        return

    cols = min(3, n)
    rows = (n + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(5*cols, 3.8*rows), squeeze=False)
    rank_desc = {"borrow":"Top {n} by Borrow Size",
                 "alpha":"Top {n} (alphabetical)",
                 "dev_cum":"Top {n} by |Price - BZAP(cum.)| (latest)"}[overview_rank]
    fig.suptitle(f"Price & Borrow Size Overview — {rank_desc.format(n=n)} — last {all_df['Date'].nunique()} days",
                 fontsize=14)

    for ax, sym in zip(axes.flatten(), symbols):
        s = all_df[all_df["Symbol"] == sym].copy().sort_values(["Stamp"])

        # Price line
        if x_mode == "time":
            width = _adaptive_bar_width(s["Stamp"])
            ax.plot(s["Stamp"], s["Price"], marker="o", markersize=2.5, linewidth=1.1, label="Price")
            _format_time_axis(ax)
        else:  # index
            stamps = s["Stamp"].tolist()
            labels = _labels_from_stamps(stamps)
            xs = list(range(len(stamps)))
            width = 0.6
            ax.plot(xs, s["Price"].values, label="Price", linewidth=1.1, marker="o", markersize=2.5)
            _format_index_axis(ax, labels)


        # Borrow bars
        ax2 = ax.twinx()
        if x_mode == "time":
            ax2.bar(s["Stamp"], s["Borrow"], alpha=0.28, width=width, label="Borrow Size")
        else:  # index
            ax2.bar(xs, s["Borrow"].values, alpha=0.28, width=0.6, label="Borrow Size")
        ax2.set_yticks([])


        # BZAP (cum.) line
        cum_num = (s["Price"].astype(float) * s["Borrow"].astype(float)).cumsum()
        cum_den = s["Borrow"].astype(float).cumsum().replace(0, np.nan)
        bzap_cum = (cum_num / cum_den).astype(float)

        if x_mode == "time":
            ax.plot(s["Stamp"], bzap_cum, linestyle=":", linewidth=1.2, label="BZAP (cum.)")
            ax.fill_between(s["Stamp"], s["Price"], bzap_cum, alpha=0.07)
        else:
            ax.plot(xs, bzap_cum.values, linestyle=":", linewidth=1.2, label="BZAP (cum.)")
            ax.fill_between(xs, s["Price"].values, bzap_cum.values, alpha=0.07)


        ax.set_title(sym, fontsize=10)
        ax.legend(fontsize=8, loc="upper left",
                  frameon=True, facecolor="white", edgecolor="lightgray",
                  fancybox=True, framealpha=0.85)

    for ax in axes.flatten()[n:]:
        ax.axis("off")

    fig.tight_layout()
    plt.show()

# ---------------------------
# Detail Navigator
# ---------------------------

def plot_detail_navigator(
    all_df: pd.DataFrame,
    initial_symbol: Optional[str] = None,
    x_mode: str = "time",
    borrow_zoom_frac: Optional[float] = None,
    borrow_view: str = "absolute",
    delta_baseline: str = "first",
    borrow_floor_mode: str = "none",
    symbol_order: Optional[list] = None,
):
    if symbol_order is not None and len(symbol_order) > 0:
        allowed = set(all_df["Symbol"].dropna().unique())
        symbols = [s for s in symbol_order if s in allowed]
        if not symbols:
            symbols = sorted(allowed)
    else:
        symbols = sorted(all_df["Symbol"].dropna().unique())

    start_idx = symbols.index(initial_symbol) if (initial_symbol in symbols) else 0
    state = {"i": start_idx, "borrow_view": borrow_view, "floor": borrow_floor_mode}

    fig = plt.figure(figsize=(10, 7))
    gs = fig.add_gridspec(3, 1, height_ratios=[2.0, 1.0, 0.05])
    ax_price = fig.add_subplot(gs[0, 0])
    ax_borrow = fig.add_subplot(gs[1, 0], sharex=ax_price)
    ax_info = fig.add_subplot(gs[2, 0])
    ax_info.axis("off")

    def compute_borrow_series(s: pd.DataFrame):
        b = s["Borrow"].astype(float).to_numpy()
        if state["borrow_view"] == "delta":
            if delta_baseline == "median":
                base = np.nanmedian(b)
            else:
                idx = np.where(~np.isnan(b))[0]
                base = b[idx[0]] if idx.size else 0.0
            vals = b - base
            return vals, "Borrow Size Δ", "Borrow Size Δ"
        else:
            return b, "Borrow Size", "Borrow Size"

    def draw(symbol):
        ax_price.clear()
        ax_borrow.clear()
        ax_info.clear()
        ax_info.axis("off")

        s = all_df[all_df["Symbol"] == symbol].sort_values(["Stamp"])

        if x_mode == "time":
            width = _adaptive_bar_width(s["Stamp"])
            ax_price.plot(s["Stamp"], s["Price"], linewidth=1.4, marker="o", markersize=3.2,
                        label=f"{symbol} Price")
            _format_time_axis(ax_price)
        else:  # index
            xs = list(range(len(s)))
            ax_price.plot(xs, s["Price"].values, linewidth=1.4, marker="o", markersize=3.2,
                        label=f"{symbol} Price")
            _format_index_axis(ax_price, _labels_from_stamps(s["Stamp"].tolist()))

        ax_price.set_ylabel("Price")

        # ---- BZAP overall + BZAP (cum.) ----
        v = (s["Price"] * s["Borrow"]).sum() / s["Borrow"].sum() if s["Borrow"].sum() else float("nan")
        if pd.notna(v):
            ax_price.axhline(v, linestyle="--", linewidth=1, label="BZAP (overall)")
        cum_num = (s["Price"] * s["Borrow"]).cumsum()
        cum_den = s["Borrow"].cumsum().replace(0, np.nan)
        bzap_series = (cum_num / cum_den).astype(float)
        if x_mode == "time":
            ax_price.plot(s["Stamp"], bzap_series, linestyle=":", linewidth=1.2, label="BZAP (cum.)")
        else:  # index
            ax_price.plot(xs, bzap_series.values, linestyle=":", linewidth=1.2, label="BZAP (cum.)")
        
        # --- Rolling BZAP ---
        N = 10
        p = s["Price"].astype(float)
        b = s["Borrow"].astype(float)
        num = (p * b).rolling(N, min_periods=1).sum()
        den = b.rolling(N, min_periods=1).sum()
        den = den.where(den != 0.0, np.nan)
        bzap_roll = (num / den).astype(float).replace([np.inf, -np.inf], np.nan)

        if bzap_roll.notna().any():
            if x_mode == "time":
                ax_price.plot(s["Stamp"], bzap_roll.values, linestyle="--", linewidth=1.2, label=f"BZAP ({N}-roll)")
            else:
                ax_price.plot(xs, bzap_roll.values, linestyle="--", linewidth=1.2, label=f"BZAP ({N}-roll)")
        
        # ---- BORROW ----
        bvals_plot, ylabel, blabel = compute_borrow_series(s)
        floor = None
        if state["borrow_view"] == "absolute":
            babs = s["Borrow"].astype(float).to_numpy()
            if state["floor"] == "p10":
                floor = float(np.nanpercentile(babs, 10))
            elif state["floor"] == "min":
                floor = float(np.nanmin(babs))

        if x_mode == "time":
            if floor is not None and state["borrow_view"] == "absolute":
                heights = (s["Borrow"].astype(float).to_numpy() - floor).clip(min=0)
                ax_borrow.bar(s["Stamp"], heights, width=width, alpha=0.35,
                              edgecolor="black", linewidth=0.4, label=blabel, bottom=floor)
                ax_borrow.axhline(floor, linestyle="--", linewidth=0.8, alpha=0.6)
                _autoscale_y(ax_borrow, s["Borrow"].astype(float).to_numpy(),
                             include_zero=False, pad=0.10, extra_floor=floor)
                _pretty_big_y(ax_borrow, compact=True)
            else:
                ax_borrow.bar(s["Stamp"], bvals_plot, width=width, alpha=0.35,
                              edgecolor="black", linewidth=0.4, label=blabel)
                _autoscale_y(ax_borrow, bvals_plot, include_zero=(state["borrow_view"]=="delta"), pad=0.10)
                _pretty_big_y(ax_borrow, compact=True)
            _format_time_axis(ax_borrow)
            
        else:
            xs = list(range(len(s)))
            if floor is not None and state["borrow_view"] == "absolute":
                heights = (s["Borrow"].astype(float).to_numpy() - floor).clip(min=0)
                ax_borrow.bar(xs, heights, width=0.6, alpha=0.35,
                              edgecolor="black", linewidth=0.4, label=blabel, bottom=floor)
                ax_borrow.axhline(floor, linestyle="--", linewidth=0.8, alpha=0.6)
                _autoscale_y(ax_borrow, s["Borrow"].astype(float).to_numpy(),
                             include_zero=False, pad=0.10, extra_floor=floor)
                _pretty_big_y(ax_borrow, compact=True)
            else:
                ax_borrow.bar(xs, bvals_plot, width=0.6, alpha=0.35,
                              edgecolor="black", linewidth=0.4, label=blabel)
                _autoscale_y(ax_borrow, bvals_plot, include_zero=(state["borrow_view"]=="delta"), pad=0.10)
                _pretty_big_y(ax_borrow, compact=True)
            _format_index_axis(ax_borrow, _labels_from_stamps(s["Stamp"].tolist()))

        # optional zoom after autoscale
        if borrow_zoom_frac is not None:
            y0, y1 = ax_borrow.get_ylim()
            span = y1 - y0
            y0_new = y0 + float(borrow_zoom_frac) * span
            if y0_new >= y1:
                y0_new = y1 - 0.01 * span
            ax_borrow.set_ylim(y0_new, y1)

        # cosmetics
        for spine in ["top","right"]:
            ax_price.spines[spine].set_visible(False)
            ax_borrow.spines[spine].set_visible(False)
        ax_price.grid(True, axis="y", alpha=0.2)
        ax_borrow.grid(True, axis="y", alpha=0.2)

        ax_price.legend(loc="upper left", fontsize=9, frameon=True, facecolor="white",
                        edgecolor="lightgray", fancybox=True, framealpha=0.8)
        ax_borrow.legend(loc="upper left", fontsize=9, frameon=True, facecolor="white",
                         edgecolor="lightgray", fancybox=True, framealpha=0.8)

        first = pd.to_datetime(s["Stamp"].min()).strftime("%Y-%m-%d %H:%M")
        last = pd.to_datetime(s["Stamp"].max()).strftime("%Y-%m-%d %H:%M")
        info_txt = (
            f"[{symbol}]  Window: {first} → {last}   "
            f"Snapshots: {s['Stamp'].nunique()}   "
            f"Borrow Size Σ: {s['Borrow'].sum():,.0f}   "
            f"BZAP: {v:,.2f}" if pd.notna(v) else f"[{symbol}]  (BZAP: N/A)"
        )
        ax_info.text(0.01, 0.5, info_txt, fontsize=10, va="center")

        fig.suptitle("Detail View — A/D or ←/→  |  Z: toggle Borrow Size  Delta Δ / Standard  |  +/−: zoom  |  X: floor (none/p10/min)  |  Q: quit",
                     fontsize=12)
        fig.tight_layout()
        fig.canvas.draw_idle()

    def on_key(event):
        nonlocal borrow_zoom_frac
        if event.key in ("right", "d"):
            state["i"] = (state["i"] + 1) % len(symbols)
            draw(symbols[state["i"]])
        elif event.key in ("left", "a"):
            state["i"] = (state["i"] - 1) % len(symbols)
            draw(symbols[state["i"]])
        elif event.key.lower() == "z":
            state["borrow_view"] = "delta" if state["borrow_view"] == "absolute" else "absolute"
            draw(symbols[state["i"]])
        elif event.key in ("+", "="):
            if borrow_zoom_frac is None:
                borrow_zoom_frac = 0.0
            borrow_zoom_frac = min(0.9, borrow_zoom_frac + 0.1)
            draw(symbols[state["i"]])
        elif event.key == "-":
            if borrow_zoom_frac is None:
                borrow_zoom_frac = 0.0
            borrow_zoom_frac = max(0.0, borrow_zoom_frac - 0.1)
            draw(symbols[state["i"]])
        elif event.key.lower() == "x":
            cycle = {"none":"p10", "p10":"min", "min":"none"}
            state["floor"] = cycle.get(state["floor"], "none")
            draw(symbols[state["i"]])
        elif event.key in ("q", "escape"):
            plt.close(fig)

    fig.canvas.mpl_connect("key_press_event", on_key)
    draw(symbols[start_idx])
    plt.show()

# ---------------------------
# Main
# ---------------------------

def main():
    ap = argparse.ArgumentParser(description="Analyze Price vs Borrow Size over last N days (BZAP autoscaled).")
    ap.add_argument("--data-dir", default="./data")
    ap.add_argument("--days", type=int, default=5)
    ap.add_argument("--topN", type=int, default=9)
    ap.add_argument("--sep", default=None)
    ap.add_argument("--symbol-col", default=None)
    ap.add_argument("--price-col", default=None)
    ap.add_argument("--borrow-col", default=None)
    ap.add_argument("--detail", action="store_true")
    ap.add_argument("--no-overview", action="store_true",
                help="Do not show the overview grid (detail-only mode).")
    ap.add_argument("--initial-symbol", default=None)
    ap.add_argument("--x-mode", choices=["time","index",], default="time",
                help="'time' = real Timeaxle (with gaps), "
                     "'index' = same spacing without time lables")
    ap.add_argument("--date-mode", choices=["data","weekday"], default="data")

    # Live/visual options
    ap.add_argument("--borrow-zoom-frac", type=float, default=None,
                    help="Optional: shift lower y bound by fraction of autoscaled range (0..1).")
    ap.add_argument("--borrow-view", choices=["absolute","delta"], default="absolute",
                    help="Absolute Borrow Size or Δ vs baseline.")
    ap.add_argument("--delta-baseline", choices=["first","median"], default="first",
                    help="Baseline for Δ mode.")
    ap.add_argument("--borrow-floor-mode", choices=["none","p10","min"], default="none",
                    help="Optional floor for absolute view (visual offset).")

    # Ranking & ordering
    ap.add_argument("--overview-rank", choices=["borrow","dev_cum","alpha"], default="dev_cum",
                    help="Ranking in overview: borrow (ΣBorrow), dev_cum (latest |Price-BZAP(cum.)|), alpha.")
    ap.add_argument("--detail-order", choices=["overview","alpha","borrow","dev_cum"], default="overview",
                    help="'Order' in detail view; 'overview' to follow overview ranking.")
    ap.add_argument("--debug", action="store_true",
                    help="Print full Python tracebacks on errors.")

    args = ap.parse_args()

    try:
        all_df = load_and_merge(
            data_dir=args.data_dir,
            n_days=args.days,
            sep=args.sep,
            symbol_col=args.symbol_col,
            price_col=args.price_col,
            borrow_col=args.borrow_col,
            date_mode=args.date_mode,
        )
    except (ValueError, FileNotFoundError) as e:
        print(f"[INPUT ERROR]\n{e}\n" + "-"*60)
        if args.debug:
            import traceback; traceback.print_exc()
        sys.exit(2)

    except Exception as e:
        print(f"[UNEXPECTED ERROR]\n{e}\n" + "-"*60)
        if args.debug:
            import traceback; traceback.print_exc()
        sys.exit(2)


    overview_symbols = rank_symbols(all_df, args.overview_rank, topN=args.topN)

    if not args.no_overview:
        plot_grid_overview(all_df, topN=args.topN, x_mode=args.x_mode,
                           overview_rank=args.overview_rank, symbols=overview_symbols)
        
    if args.detail:
        if args.detail_order == "overview":
            detail_symbols = overview_symbols
        else:
            detail_symbols = rank_symbols(all_df, args.detail_order, topN=None)

        plot_detail_navigator(
            all_df,
            initial_symbol=args.initial_symbol,
            x_mode=args.x_mode,
            borrow_zoom_frac=args.borrow_zoom_frac,
            borrow_view=args.borrow_view,
            delta_baseline=args.delta_baseline,
            borrow_floor_mode=args.borrow_floor_mode,
            symbol_order=detail_symbols,
        )

if __name__ == "__main__":
    main()
