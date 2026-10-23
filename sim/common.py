"""Shared helpers for the experiment scripts: multi-seed runs and plot styling."""

from __future__ import annotations

import numpy as np

from src.orbit_power import OrbitPowerConfig
from src.scheduler import MINUTES_PER_WEEK, make_job_stream, simulate
from src.workload_profile import DEFAULT_MIX

# Fixed colour per policy (never re-assigned by rank), validated categorical order.
POLICY_COLORS = {
    "greedy": "#2a78d6",
    "sunlight_only": "#eb6834",
    "threshold": "#1baf7a",
    "predictive": "#eda100",
}
SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT_2 = "#52514e"
GRID = "#e4e3df"
ECLIPSE = "#d9d8d3"

METRICS = [
    ("completed", "jobs done", "{:.0f}"),
    ("missed", "missed", "{:.1f}"),
    ("p1_missed", "priority-1 missed", "{:.1f}"),
    ("value_fraction", "value done", "{:.1%}"),
    ("min_soc", "min SoC", "{:.0%}"),
    ("load_shed_min", "load-shed min", "{:.0f}"),
    ("mean_dod", "mean DoD", "{:.0%}"),
    ("battery_life_years", "battery life (yr, notional)", "{:.1f}"),
    ("wasted_solar_wh", "wasted solar (Wh)", "{:.0f}"),
]


def color_for(policy_name: str) -> str:
    for key, col in POLICY_COLORS.items():
        if policy_name.startswith(key):
            return col
    return TEXT_2


def run_policies(
    cfg: OrbitPowerConfig,
    policies,
    seeds: int = 20,
    rate: float = 0.08,
    mix=DEFAULT_MIX,
    duration_min: float = MINUTES_PER_WEEK,
) -> dict[str, dict[str, tuple[float, float]]]:
    """Run every policy on the SAME job streams; return {policy: {metric: (mean, std)}}."""
    streams = [make_job_stream(duration_min, seed=s, rate_per_min=rate, mix=mix) for s in range(seeds)]
    out = {}
    for p in policies:
        rows = []
        for arr in streams:
            r = simulate(cfg, arr, p, duration_min)
            row = {m: float(getattr(r, m)) for m, _, _ in METRICS if hasattr(r, m)}
            row["p1_missed"] = float(r.missed_by_priority.get(1, 0))
            rows.append(row)
        out[p.__name__] = {
            m: (float(np.mean([row[m] for row in rows])), float(np.std([row[m] for row in rows])))
            for m in rows[0]
        }
    return out


def markdown_table(results: dict, title: str = "") -> str:
    head = "| policy | " + " | ".join(label for _, label, _ in METRICS) + " |"
    sep = "|---|" + "---|" * len(METRICS)
    lines = [f"**{title}**\n" if title else "", head, sep]
    for name, metrics in results.items():
        cells = []
        for key, _, fmt in METRICS:
            mean, std = metrics[key]
            cell = fmt.format(mean)
            if key in ("missed", "p1_missed") and std > 0:
                cell += f" ± {std:.1f}"
            cells.append(cell)
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def style_axes(ax, title: str = "", xlabel: str = "", ylabel: str = ""):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=TEXT_2, labelsize=9)
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    if title:
        ax.set_title(title, color=TEXT, fontsize=11, loc="left", pad=10)
    ax.set_xlabel(xlabel, color=TEXT_2, fontsize=9)
    ax.set_ylabel(ylabel, color=TEXT_2, fontsize=9)


def cfg_with(cfg: OrbitPowerConfig, **changes) -> OrbitPowerConfig:
    """Copy a config with some fields changed (re-derives period and eclipse)."""
    base = {k: getattr(cfg, k) for k in cfg.__dataclass_fields__ if cfg.__dataclass_fields__[k].init}
    base.update(changes)
    return OrbitPowerConfig(**base)


__all__ = ["run_policies", "markdown_table", "style_axes", "color_for", "cfg_with"]
