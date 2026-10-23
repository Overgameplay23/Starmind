"""
run_sim.py — the scoreboard.

Runs all four policies for one simulated week on 20 different random job
streams (seeds), and reports mean ± standard deviation. One seed is an
anecdote; twenty is evidence.

Outputs
  results/baseline.md         the table
  results/battery_one_day.png battery level for each policy over one day

Run from the repo root:  python -m sim.run_sim
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.orbit_power import OrbitPowerConfig, orbit_energy_budget
from src.scheduler import default_policies, make_job_stream, simulate
from src.workload_profile import DEFAULT_MIX, SYNTHETIC_PROFILES, mean_energy_per_job_wh

from .common import ECLIPSE, SURFACE, TEXT_2, color_for, markdown_table, run_policies, style_axes

RESULTS = Path(__file__).resolve().parent.parent / "results"


def plot_one_day(cfg: OrbitPowerConfig, rate: float, path: Path, seed: int = 0):
    arrivals = make_job_stream(seed=seed, rate_per_min=rate)
    fig, ax = plt.subplots(figsize=(11, 4.2), facecolor=SURFACE)
    day = int(24 * 60 / cfg.dt_min)
    start = 2 * day  # skip the first days so the start-up charge has washed out
    first = True
    for p in default_policies():
        r = simulate(cfg, arrivals, p)
        t_h = (r.t_min[start : start + day] - r.t_min[start]) / 60
        if first:
            sun = r.in_sun[start : start + day]
            ax.fill_between(t_h, 0, 100, where=~sun, color=ECLIPSE, alpha=0.6, linewidth=0, label="eclipse")
            first = False
        ax.plot(t_h, r.soc[start : start + day] * 100, color=color_for(r.policy), linewidth=2, label=r.policy)
    ax.axhline(cfg.floor_soc * 100, color=TEXT_2, linestyle="--", linewidth=1.2)
    ax.text(0.2, cfg.floor_soc * 100 + 1.5, f"floor {cfg.floor_soc:.0%}", color=TEXT_2, fontsize=9)
    ax.set_ylim(0, 100)
    ax.set_xlim(0, 24)
    style_axes(ax, "Battery state of charge over one day (same jobs, four policies)", "hours", "state of charge (%)")
    leg = ax.legend(loc="lower right", fontsize=9, frameon=True, ncol=5)
    leg.get_frame().set_edgecolor("none")
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--rate", type=float, default=0.08, help="job arrivals per minute")
    ap.add_argument("--array", type=float, default=9.0, help="array peak watts")
    args = ap.parse_args()

    cfg = OrbitPowerConfig(array_peak_w=args.array)
    RESULTS.mkdir(exist_ok=True)

    avg_compute_w = args.rate * mean_energy_per_job_wh(SYNTHETIC_PROFILES, DEFAULT_MIX) * 60
    b = orbit_energy_budget(cfg, avg_compute_w)
    budget = (
        f"Per-orbit budget: period {b['period_min']:.1f} min, eclipse {b['eclipse_min']:.1f} min | "
        f"in {b['energy_in_wh']:.2f} Wh, bus {b['bus_wh']:.2f} Wh, compute demand {b['compute_wh']:.2f} Wh, "
        f"battery losses {b['battery_loss_wh']:.2f} Wh -> margin {b['margin_wh']:+.2f} Wh"
    )
    print(budget)

    results = run_policies(cfg, default_policies(), seeds=args.seeds, rate=args.rate)
    table = markdown_table(results, f"One week, {args.seeds} seeds, {args.rate} jobs/min, {args.array:g} W array")
    print(table)
    (RESULTS / "baseline.md").write_text(budget + "\n\n" + table)
    plot_one_day(cfg, args.rate, RESULTS / "battery_one_day.png")
    print(f"wrote {RESULTS / 'baseline.md'} and battery_one_day.png")


if __name__ == "__main__":
    main()
