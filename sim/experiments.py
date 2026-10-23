"""
experiments.py — the guide's experiments, plus the two that matter most.

  1. shrink_array     array 9 W -> 7 W. Total energy is king.
  2. heavy_workload   job mix [0.30, 0.30, 0.40]. The processor becomes the bottleneck.
  3. protect_battery  floor 30 % -> 60 %. Battery years vs. work done.
  4. fixed_panel      body-mounted panel instead of a sun-tracking one.
  5. beta_sweep       eclipse length changes with season (beta angle).
  6. threshold_sweep  is 55 % a good threshold? Compare against the predictive policy.

Outputs go to results/. Run all:  python -m sim.experiments
Run one:  python -m sim.experiments --only beta_sweep
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from src.orbit_power import OrbitPowerConfig, orbit_energy_budget
from src.scheduler import default_policies, greedy, predictive, sunlight_only, threshold
from src.workload_profile import HEAVY_MIX

from .common import SURFACE, TEXT_2, cfg_with, color_for, markdown_table, run_policies, style_axes

RESULTS = Path(__file__).resolve().parent.parent / "results"
BASE = OrbitPowerConfig()
RATE = 0.08


def table_experiment(name: str, cfg: OrbitPowerConfig, seeds: int, **kw) -> str:
    res = run_policies(cfg, default_policies(), seeds=seeds, rate=RATE, **kw)
    b = orbit_energy_budget(cfg)
    note = f"_in {b['energy_in_wh']:.2f} Wh/orbit, eclipse {b['eclipse_min']:.1f} min, floor {cfg.floor_soc:.0%}_\n\n"
    return f"### {name}\n\n" + note + markdown_table(res)


def beta_sweep(seeds: int) -> str:
    betas = [0, 15, 30, 45, 60, 70, 75]
    policies = [greedy(), sunlight_only(), threshold(0.55), predictive(0.5)]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), facecolor=SURFACE, sharey=True)
    lines = ["### beta_sweep\n", "| beta | eclipse (min) | tracking in (Wh) | fixed in (Wh) | " + " | ".join(
        f"{p.__name__} value, tracking / fixed" for p in policies) + " |", "|---|---|---|---|" + "---|" * len(policies)]
    curves = {(mode, p.__name__): [] for mode in ("sun_tracking", "zenith_fixed") for p in policies}
    for beta in betas:
        row = []
        energy = {}
        for mode in ("sun_tracking", "zenith_fixed"):
            # Fixed panels earn less, so give them a proportionally bigger array
            # (same mean income at beta = 0 is 4.49 vs 8.55 Wh); keep the workload.
            peak = 9.0 if mode == "sun_tracking" else 9.0 * 8.55 / 4.49
            cfg = cfg_with(BASE, beta_deg=beta, panel_mode=mode, array_peak_w=peak)
            energy[mode] = orbit_energy_budget(cfg)["energy_in_wh"]
            res = run_policies(cfg, policies, seeds=seeds, rate=RATE)
            for p in policies:
                curves[(mode, p.__name__)].append(res[p.__name__]["value_fraction"][0])
        ecl = cfg.eclipse_min
        for p in policies:
            row.append(f"{curves[('sun_tracking', p.__name__)][-1]:.1%} / {curves[('zenith_fixed', p.__name__)][-1]:.1%}")
        lines.append(f"| {beta} | {ecl:.1f} | {energy['sun_tracking']:.2f} | {energy['zenith_fixed']:.2f} | " + " | ".join(row) + " |")

    for ax, mode, title in zip(axes, ("sun_tracking", "zenith_fixed"),
                               ("Sun-tracking array (9 W)", "Body-fixed array (17.1 W, same income at beta 0)")):
        for p in policies:
            ax.plot(betas, np.array(curves[(mode, p.__name__)]) * 100, marker="o", markersize=5,
                    linewidth=2, color=color_for(p.__name__), label=p.__name__)
        style_axes(ax, title, "beta angle (deg)", "value of work completed (%)" if mode == "sun_tracking" else "")
    axes[0].legend(fontsize=8, frameon=False, loc="lower right")
    fig.suptitle("How the season (beta angle) changes what each policy gets done", x=0.01, ha="left",
                 color="#0b0b0b", fontsize=12)
    fig.tight_layout()
    fig.savefig(RESULTS / "beta_sweep.png", dpi=150, facecolor=SURFACE)
    plt.close(fig)
    return "\n".join(lines) + "\n\nPlot: `results/beta_sweep.png`\n"


def threshold_sweep(seeds: int) -> str:
    cfg = cfg_with(BASE, array_peak_w=7.5)  # tighter budget so the choice matters
    ths = [0.35, 0.45, 0.55, 0.65, 0.75, 0.85]
    margins = [0.0, 0.25, 0.5, 1.0, 2.0]
    th_res = run_policies(cfg, [threshold(t) for t in ths], seeds=seeds, rate=RATE)
    pr_res = run_policies(cfg, [predictive(m) for m in margins], seeds=seeds, rate=RATE)

    fig, ax = plt.subplots(figsize=(8, 4.6), facecolor=SURFACE)
    for res, key in ((th_res, "threshold"), (pr_res, "predictive")):
        xs = [v["mean_dod"][0] * 100 for v in res.values()]
        ys = [v["value_fraction"][0] * 100 for v in res.values()]
        ax.plot(xs, ys, marker="o", markersize=6, linewidth=2, color=color_for(key), label=key)
        for k, ((name, v), x, y) in enumerate(zip(res.items(), xs, ys)):
            label = name.split("_")[-1]
            if key == "threshold":
                label, offset = f"{label}%", (4, -13)
            else:
                if k not in (0, len(res) - 1):
                    continue  # the middle points overlap; label the ends of the sweep
                label = "margin " + label.replace("m", "") + " Wh"
                offset = (-80, -4) if k == 0 else (-78, 6)
            ax.annotate(label, (x, y), textcoords="offset points", xytext=offset, fontsize=8, color=TEXT_2)
    style_axes(ax, "Work done vs. battery stress, 7.5 W array (labels: threshold %, predictive margin)",
               "mean depth of discharge per orbit (%)", "value of work completed (%)")
    ax.legend(fontsize=9, frameon=False)
    fig.tight_layout()
    fig.savefig(RESULTS / "threshold_sweep.png", dpi=150, facecolor=SURFACE)
    plt.close(fig)
    return ("### threshold_sweep (7.5 W array)\n\nThreshold policy at different eclipse thresholds:\n\n"
            + markdown_table(th_res) + "\nPredictive policy at different safety margins (Wh):\n\n"
            + markdown_table(pr_res) + "\nPlot: `results/threshold_sweep.png`\n")


EXPERIMENTS = {
    "baseline": lambda s: table_experiment("baseline (9 W, tracking, beta 0)", BASE, s),
    "shrink_array": lambda s: table_experiment("shrink_array (7 W)", cfg_with(BASE, array_peak_w=7.0), s),
    "heavy_workload": lambda s: table_experiment("heavy_workload (mix 0.30/0.30/0.40)", BASE, s, mix=HEAVY_MIX),
    "protect_battery": lambda s: table_experiment("protect_battery (floor 60 %)", cfg_with(BASE, max_depth_of_discharge=0.4), s),
    "fixed_panel": lambda s: table_experiment("fixed_panel (9 W body-mounted)", cfg_with(BASE, panel_mode="zenith_fixed"), s),
    "beta_sweep": beta_sweep,
    "threshold_sweep": threshold_sweep,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--only", choices=list(EXPERIMENTS))
    args = ap.parse_args()
    RESULTS.mkdir(exist_ok=True)
    names = [args.only] if args.only else list(EXPERIMENTS)
    sections = []
    for name in names:
        print(f"running {name} ...", flush=True)
        sections.append(EXPERIMENTS[name](args.seeds))
        print(sections[-1])
    out = RESULTS / ("experiments.md" if not args.only else f"{args.only}.md")
    out.write_text(f"# Experiment results ({args.seeds} seeds each, {RATE} jobs/min)\n\n" + "\n".join(sections))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
