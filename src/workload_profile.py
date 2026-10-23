"""
workload_profile.py — what the jobs cost.

A JobProfile is a *type* of job (e.g. "run the object detector on one image").
It carries the four numbers the scheduler cares about:

    power_w       how hard the processor pulls while the job runs
    runtime_min   how long it runs
    priority      1 = most important
    deadline_min  how long after arrival the result is still useful

and one derived number, the only one the battery actually feels:

    energy_wh = power_w * runtime_min / 60

The SYNTHETIC profiles below are placeholders. Phase 2 replaces them with
numbers you measure yourself on a Raspberry Pi with an INA260 power monitor
(see measure/). Keep both sets so you can compare.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class JobProfile:
    name: str
    power_w: float
    runtime_min: int
    priority: int
    deadline_min: int
    value: float  # how much finishing one is worth, for scoring

    @property
    def energy_wh(self) -> float:
        return self.power_w * self.runtime_min / 60.0


# Notional numbers. Not measurements. Power is the compute board's draw while
# running; the board is assumed power-gated (0 W) when idle.
SYNTHETIC_PROFILES: list[JobProfile] = [
    JobProfile("anomaly_check", power_w=3.0, runtime_min=2, priority=1, deadline_min=15, value=10.0),
    JobProfile("image_detect", power_w=4.0, runtime_min=6, priority=2, deadline_min=60, value=3.0),
    JobProfile("batch_compress", power_w=5.0, runtime_min=25, priority=3, deadline_min=300, value=1.0),
]

# Probability that an arriving job is each type (same order as the profiles).
DEFAULT_MIX: list[float] = [0.50, 0.35, 0.15]
HEAVY_MIX: list[float] = [0.30, 0.30, 0.40]


# Phase 2: fill these in from measure/results.csv, then pass
# profiles=MEASURED_PROFILES to make_job_stream().
MEASURED_PROFILES: list[JobProfile] = []


def mean_energy_per_job_wh(profiles: list[JobProfile], mix: list[float]) -> float:
    return sum(p.energy_wh * w for p, w in zip(profiles, mix))


def mean_runtime_min(profiles: list[JobProfile], mix: list[float]) -> float:
    return sum(p.runtime_min * w for p, w in zip(profiles, mix))
