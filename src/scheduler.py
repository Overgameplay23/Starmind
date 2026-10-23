"""
scheduler.py — the decisions.

The simulator steps time forward one minute at a time. Each step:

    1. New jobs arrive and join the queue.
    2. Jobs that can no longer finish before their deadline are dropped (missed).
    3. If the processor is idle, the POLICY picks a job to start (or nothing).
    4. The power system protects itself: if running compute would push the
       battery below its floor, the compute load is shed (job paused).
    5. The battery absorbs net power = solar - bus - compute.

Only step 3 differs between policies. Everything else is shared, so the
comparison is fair: same orbit, same physics, same job arrivals.

Policies
--------
greedy         start the most important job the moment the processor is free
sunlight_only  compute only while the array is producing
threshold      priority-1 jobs anytime; others in sunlight, or in eclipse if
               state of charge >= a fixed threshold (the classic heuristic)
predictive     look one orbit ahead: start a job only if the *projected*
               battery never dips below floor + margin. No magic threshold;
               the orbit is predictable, so we calculate instead of guess.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from .orbit_power import (
    Battery,
    OrbitPowerConfig,
    project_energy,
    solar_input_w,
    sunlight_mask,
)
from .workload_profile import DEFAULT_MIX, SYNTHETIC_PROFILES, JobProfile

MINUTES_PER_WEEK = 7 * 24 * 60


# ----------------------------------------------------------------------
# Jobs
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class Arrival:
    job_id: int
    arrival_min: float
    profile: JobProfile

    @property
    def deadline_min(self) -> float:
        return self.arrival_min + self.profile.deadline_min


@dataclass
class Job:
    arrival: Arrival
    remaining_min: float
    start_min: float | None = None
    finish_min: float | None = None

    @property
    def profile(self) -> JobProfile:
        return self.arrival.profile

    @property
    def deadline_min(self) -> float:
        return self.arrival.deadline_min

    def sort_key(self):
        # Most important first, then earliest deadline first (EDF).
        return (self.profile.priority, self.deadline_min, self.arrival.job_id)


def make_job_stream(
    duration_min: float = MINUTES_PER_WEEK,
    seed: int = 0,
    rate_per_min: float = 0.08,
    profiles: list[JobProfile] = SYNTHETIC_PROFILES,
    mix: list[float] = DEFAULT_MIX,
    dt_min: float = 1.0,
) -> list[Arrival]:
    """
    Poisson arrivals: each minute, the number of new jobs is Poisson(rate * dt).
    The same seed gives the same stream, so every policy faces identical work.
    """
    rng = np.random.default_rng(seed)
    n_steps = int(duration_min / dt_min)
    counts = rng.poisson(rate_per_min * dt_min, size=n_steps)
    total = int(counts.sum())
    types = rng.choice(len(profiles), size=total, p=np.asarray(mix) / sum(mix))
    arrivals, k = [], 0
    for step, c in enumerate(counts):
        for _ in range(c):
            arrivals.append(Arrival(k, step * dt_min, profiles[types[k]]))
            k += 1
    return arrivals


# ----------------------------------------------------------------------
# Policies
# ----------------------------------------------------------------------
@dataclass
class Context:
    """What a policy is allowed to see when it decides."""

    step: int
    t_min: float
    cfg: OrbitPowerConfig
    energy_wh: float
    in_sun: bool
    queue: list[Job]  # already sorted by Job.sort_key
    solar_w: np.ndarray  # full precomputed array output (the orbit is predictable)

    @property
    def soc(self) -> float:
        return self.energy_wh / self.cfg.battery_capacity_wh


Policy = Callable[[Context], "Job | None"]


def greedy() -> Policy:
    def choose(ctx: Context):
        return ctx.queue[0] if ctx.queue else None

    choose.__name__ = "greedy"
    return choose


def sunlight_only() -> Policy:
    def choose(ctx: Context):
        return ctx.queue[0] if (ctx.queue and ctx.in_sun) else None

    choose.__name__ = "sunlight_only"
    return choose


def threshold(eclipse_soc_threshold: float = 0.55) -> Policy:
    def choose(ctx: Context):
        if not ctx.queue or ctx.soc <= ctx.cfg.floor_soc:
            return None
        job = ctx.queue[0]
        if job.profile.priority == 1 or ctx.in_sun or ctx.soc >= eclipse_soc_threshold:
            return job
        return None

    choose.__name__ = f"threshold_{int(eclipse_soc_threshold * 100)}"
    return choose


def predictive(margin_wh: float = 0.5, priority1_margin_wh: float = 0.0) -> Policy:
    """
    Admission test, for each candidate job in priority order:

        project the battery one orbit ahead assuming
            load = bus + (this job for its runtime)
        admit if  min(projected energy) >= floor + margin

    Priority-1 jobs use a smaller margin (default 0), so important work only
    waits when it would genuinely break the floor. If the head of the queue
    doesn't fit, a smaller job behind it may (this is called backfilling).
    """

    def choose(ctx: Context):
        if not ctx.queue:
            return None
        cfg = ctx.cfg
        steps_per_orbit = int(math.ceil(cfg.period_min / cfg.dt_min))
        verdict: dict[tuple, bool] = {}  # jobs of the same type share one projection
        for job in ctx.queue:
            p = job.profile
            margin = priority1_margin_wh if p.priority == 1 else margin_wh
            key = (p.power_w, job.remaining_min, margin)
            if key not in verdict:
                run_steps = int(math.ceil(job.remaining_min / cfg.dt_min))
                horizon = steps_per_orbit + run_steps
                solar = ctx.solar_w[ctx.step : ctx.step + horizon]
                load = np.full(len(solar), cfg.bus_load_w)
                load[:run_steps] += p.power_w
                traj = project_energy(ctx.energy_wh, solar - load, cfg)
                verdict[key] = traj.min() >= cfg.floor_wh + margin
            if verdict[key]:
                return job
        return None

    choose.__name__ = f"predictive_m{margin_wh:g}"
    return choose


def default_policies() -> list[Policy]:
    return [greedy(), sunlight_only(), threshold(0.55), predictive(0.5)]


# ----------------------------------------------------------------------
# Simulator
# ----------------------------------------------------------------------
@dataclass
class SimResult:
    policy: str
    arrived: int
    completed: int
    missed: int
    missed_by_priority: dict[int, int]
    value_fraction: float  # value of finished work / value of all work that arrived
    preemptions: int
    min_soc: float
    load_shed_min: float  # minutes compute was paused by battery protection
    brownout_min: float  # minutes the BUS could not be served (battery empty)
    wasted_solar_wh: float  # sunlight dumped because the battery was full
    compute_energy_wh: float
    mean_dod: float  # average per-orbit depth of discharge
    max_dod: float
    battery_life_years: float
    t_min: np.ndarray = field(repr=False)
    soc: np.ndarray = field(repr=False)
    in_sun: np.ndarray = field(repr=False)
    compute_w: np.ndarray = field(repr=False)
    queue_len: np.ndarray = field(repr=False)


def simulate(
    cfg: OrbitPowerConfig,
    arrivals: list[Arrival],
    policy: Policy,
    duration_min: float = MINUTES_PER_WEEK,
    hardware_load_shedding: bool = True,
) -> SimResult:
    dt = cfg.dt_min
    dt_h = dt / 60.0
    n = int(duration_min / dt)
    steps_per_orbit = int(math.ceil(cfg.period_min / dt))

    # Precompute the environment, plus one extra orbit for look-ahead.
    t_all = np.arange(n + 2 * steps_per_orbit + 1000) * dt
    solar_all = solar_input_w(t_all, cfg)
    sun_all = sunlight_mask(t_all, cfg)

    batt = Battery(cfg)
    queue: list[Job] = []
    running: Job | None = None
    next_arrival = 0
    completed = missed = preemptions = 0
    missed_by_p: dict[int, int] = {}
    value_done = 0.0
    shed_min = brownout_min = wasted = compute_e = 0.0

    soc_tr = np.empty(n)
    comp_tr = np.zeros(n)
    q_tr = np.empty(n, dtype=int)

    def miss(job: Job):
        nonlocal missed
        missed += 1
        pr = job.profile.priority
        missed_by_p[pr] = missed_by_p.get(pr, 0) + 1

    for i in range(n):
        t = i * dt

        # 1. arrivals
        added = False
        while next_arrival < len(arrivals) and arrivals[next_arrival].arrival_min <= t:
            a = arrivals[next_arrival]
            queue.append(Job(a, remaining_min=a.profile.runtime_min))
            next_arrival += 1
            added = True
        if added:
            queue.sort(key=Job.sort_key)

        # 2. drop jobs that can no longer make their deadline
        kept = []
        for job in queue:
            if t + job.remaining_min > job.deadline_min:
                miss(job)
            else:
                kept.append(job)
        queue = kept
        if running is not None and t + running.remaining_min > running.deadline_min:
            miss(running)  # abort: finishing late is worthless and costs energy
            running = None

        # 3. preemption: a more important job waiting pushes the running one
        #    back into the queue (it keeps its progress). Then the policy decides.
        if running is not None and queue and queue[0].profile.priority < running.profile.priority:
            queue.append(running)
            queue.sort(key=Job.sort_key)
            running = None
            preemptions += 1

        #    policy decision
        if running is None and queue:
            ctx = Context(i, t, cfg, batt.energy_wh, bool(sun_all[i]), queue, solar_all)
            choice = policy(ctx)
            if choice is not None:
                queue.remove(choice)
                running = choice
                running.start_min = t

        # 4. power system protection (independent of the policy, like a real
        #    EPS): pause compute if the battery is below its floor, or if this
        #    step of compute would push it below. Below the floor, every watt of
        #    sunlight goes to recharging.
        solar = float(solar_all[i])
        compute = running.profile.power_w if running is not None else 0.0
        if compute > 0 and hardware_load_shedding:
            net = solar - cfg.bus_load_w - compute
            after = batt.energy_wh + min(net, 0.0) * dt_h / cfg.discharge_efficiency
            if batt.energy_wh < cfg.floor_wh or after < cfg.floor_wh:
                compute = 0.0
                shed_min += dt

        # 5. battery
        res = batt.step(solar - cfg.bus_load_w - compute, dt_h)
        wasted += res.wasted_wh
        if res.unserved_wh > 1e-12:
            brownout_min += dt
        compute_e += compute * dt_h

        # progress the running job
        if running is not None and compute > 0:
            running.remaining_min -= dt
            if running.remaining_min <= 1e-9:
                running.finish_min = t + dt
                completed += 1
                value_done += running.profile.value
                running = None

        soc_tr[i] = batt.soc
        comp_tr[i] = compute
        q_tr[i] = len(queue) + (running is not None)

    # Per-orbit depth of discharge -> notional battery life
    dods = []
    for k in range(n // steps_per_orbit):
        window = soc_tr[k * steps_per_orbit : (k + 1) * steps_per_orbit]
        dods.append(float(window.max() - window.min()))
    dods = np.array(dods) if dods else np.array([0.0])

    total_value = sum(a.profile.value for a in arrivals if a.arrival_min < n * dt)
    return SimResult(
        policy=policy.__name__,
        arrived=sum(1 for a in arrivals if a.arrival_min < n * dt),
        completed=completed,
        missed=missed,
        missed_by_priority=dict(sorted(missed_by_p.items())),
        value_fraction=value_done / total_value if total_value else 1.0,
        preemptions=preemptions,
        min_soc=float(soc_tr.min()),
        load_shed_min=shed_min,
        brownout_min=brownout_min,
        wasted_solar_wh=wasted,
        compute_energy_wh=compute_e,
        mean_dod=float(dods.mean()),
        max_dod=float(dods.max()),
        battery_life_years=battery_life_years(dods, cfg.period_min),
        t_min=np.arange(n) * dt,
        soc=soc_tr,
        in_sun=sun_all[:n],
        compute_w=comp_tr,
        queue_len=q_tr,
    )


# ----------------------------------------------------------------------
# Battery wear (notional)
# ----------------------------------------------------------------------
def cycles_to_failure(dod: float, n_ref: float = 30000.0, dod_ref: float = 0.25, k: float = 1.5) -> float:
    """
    Notional cycle-life curve: N(DoD) = n_ref * (dod_ref / DoD)^k.
    Shallower cycles -> many more of them. These constants are placeholders;
    replace them with the curve from your battery cell's datasheet.
    """
    return n_ref * (dod_ref / max(dod, 0.01)) ** k


def battery_life_years(dods: np.ndarray, period_min: float) -> float:
    """Miner's rule: each orbit uses up 1/N(DoD) of the battery's life."""
    damage_per_orbit = float(np.mean([1.0 / cycles_to_failure(d) for d in dods]))
    orbits_per_year = 365.25 * 24 * 60 / period_min
    return 1.0 / (damage_per_orbit * orbits_per_year)
