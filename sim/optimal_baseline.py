"""
optimal_baseline.py — how good could ANY scheduler possibly be?

Heuristics are only meaningful next to a reference. This script solves the
scheduling problem exactly, as a mixed-integer linear program (MILP), on short
windows (a few orbits), and reports each heuristic as a percentage of that
optimum.

The optimum is an UPPER BOUND, deliberately generous:
  * it is clairvoyant (knows every future arrival),
  * it may pause and resume any job at any minute (full preemption),
so no real online policy can beat it. "Predictive reaches 97 % of the bound"
is a strong, honest claim; "predictive beats greedy" on its own is not.

Formulation (one-minute steps t, jobs j):
  y[j,t] in {0,1}   job j runs during minute t (only inside its window)
  done[j] in {0,1}  job j finished
  c[t], d[t], w[t]  >= 0  battery charge power, discharge power, wasted solar
  E[t]              stored energy

  maximize   sum_j value_j * done_j  -  penalty * sum_t slack_t
  subject to sum_j y[j,t] <= 1                      (one processor)
             sum_t y[j,t] = runtime_j * done_j      (finish all of it, or none)
             solar_t - bus - sum_j P_j y[j,t] = c_t - d_t + w_t   (power balance)
             c_t <= max_charge
             E[t+1] = E[t] + (eta_c c_t - d_t / eta_d) dt
             floor - slack_t <= E[t] <= capacity

Run:  python -m sim.optimal_baseline
"""

from __future__ import annotations

import argparse
import math
import time
from pathlib import Path

import numpy as np
import pulp

from src.orbit_power import OrbitPowerConfig, solar_input_w
from src.scheduler import Arrival, default_policies, make_job_stream, simulate


def solve_optimal(cfg: OrbitPowerConfig, arrivals: list[Arrival], horizon_min: int, time_limit_s: int = 120):
    dt = cfg.dt_min
    dt_h = dt / 60.0
    T = int(horizon_min / dt)
    solar = solar_input_w(np.arange(T) * dt, cfg)
    jobs = [a for a in arrivals if a.arrival_min < horizon_min]

    prob = pulp.LpProblem("orbit_schedule", pulp.LpMaximize)
    y, windows = {}, {}
    for a in jobs:
        start = int(a.arrival_min / dt)
        end = min(T, int(a.deadline_min / dt))  # last usable step is end-1
        windows[a.job_id] = range(start, end)
        for t in windows[a.job_id]:
            y[a.job_id, t] = pulp.LpVariable(f"y_{a.job_id}_{t}", cat="Binary")
    done = {a.job_id: pulp.LpVariable(f"done_{a.job_id}", cat="Binary") for a in jobs}
    c = [pulp.LpVariable(f"c_{t}", 0, cfg.max_charge_w) for t in range(T)]
    d = [pulp.LpVariable(f"d_{t}", 0) for t in range(T)]
    w = [pulp.LpVariable(f"w_{t}", 0) for t in range(T)]
    E = [pulp.LpVariable(f"E_{t}", 0, cfg.battery_capacity_wh) for t in range(T + 1)]
    slack = [pulp.LpVariable(f"s_{t}", 0) for t in range(T + 1)]

    prob += pulp.lpSum(a.profile.value * done[a.job_id] for a in jobs) - 1000 * pulp.lpSum(slack)

    running_at = {t: [] for t in range(T)}
    for a in jobs:
        steps = int(math.ceil(a.profile.runtime_min / dt))
        prob += pulp.lpSum(y[a.job_id, t] for t in windows[a.job_id]) == steps * done[a.job_id]
        for t in windows[a.job_id]:
            running_at[t].append(a)

    prob += E[0] == cfg.initial_soc * cfg.battery_capacity_wh
    for t in range(T):
        if running_at[t]:
            prob += pulp.lpSum(y[a.job_id, t] for a in running_at[t]) <= 1
        compute = pulp.lpSum(a.profile.power_w * y[a.job_id, t] for a in running_at[t])
        prob += float(solar[t]) - cfg.bus_load_w - compute == c[t] - d[t] + w[t]
        prob += E[t + 1] == E[t] + (cfg.charge_efficiency * c[t] - d[t] * (1 / cfg.discharge_efficiency)) * dt_h
        prob += E[t + 1] + slack[t + 1] >= cfg.floor_wh

    prob.solve(pulp.HiGHS(msg=False, timeLimit=time_limit_s))
    status = pulp.LpStatus[prob.status]
    total_value = sum(a.profile.value for a in jobs)
    got = sum(a.profile.value * (done[a.job_id].value() or 0) for a in jobs)
    return {"status": status, "value_fraction": got / total_value if total_value else 1.0, "jobs": len(jobs)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--orbits", type=int, default=4)
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--rate", type=float, default=0.10)
    ap.add_argument("--array", type=float, default=7.0)
    ap.add_argument("--soc0", type=float, default=0.45, help="starting state of charge")
    args = ap.parse_args()

    cfg = OrbitPowerConfig(array_peak_w=args.array, initial_soc=args.soc0)
    horizon = int(args.orbits * cfg.period_min)
    policies = default_policies()
    pct = {p.__name__: [] for p in policies}
    print(f"{args.seeds} instances x {args.orbits} orbits ({horizon} min), rate {args.rate}/min, array {args.array} W, start SoC {args.soc0:.0%}")
    for seed in range(args.seeds):
        arrivals = make_job_stream(duration_min=horizon, seed=1000 + seed, rate_per_min=args.rate)
        t0 = time.time()
        opt = solve_optimal(cfg, arrivals, horizon)
        line = f"seed {seed}: {opt['jobs']:3d} jobs, optimum {opt['value_fraction']:.3f} ({opt['status']}, {time.time() - t0:.1f}s)"
        for p in policies:
            r = simulate(cfg, arrivals, p, duration_min=horizon)
            ratio = r.value_fraction / opt["value_fraction"] if opt["value_fraction"] > 0 else 1.0
            pct[p.__name__].append(ratio)
            line += f" | {p.__name__} {ratio:.0%}"
        print(line)
    summary = [
        f"# Optimal baseline\n",
        f"{args.seeds} instances x {args.orbits} orbits ({horizon} min), {args.rate} jobs/min, "
        f"{args.array:g} W array, starting at {args.soc0:.0%} charge. The optimum is a clairvoyant, "
        f"fully preemptive upper bound (see the docstring).\n",
        "| policy | mean % of optimal value | worst instance |",
        "|---|---|---|",
    ]
    for name, vals in pct.items():
        summary.append(f"| {name} | {np.mean(vals):.1%} | {np.min(vals):.1%} |")
    text = "\n".join(summary) + "\n"
    print("\n" + text)
    out = Path(__file__).resolve().parent.parent / "results" / "optimal_baseline.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(text)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
