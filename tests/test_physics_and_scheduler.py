"""
Tests that pin the code to hand calculations. If one of these fails after you
change something, either the code is wrong or your hand calculation is.

    python -m pytest -q
"""

import math

import numpy as np
import pytest

from src.orbit_power import (
    Battery,
    OrbitPowerConfig,
    eclipse_duration_min,
    orbit_energy_budget,
    orbit_period_min,
    project_energy,
    solar_input_w,
)
from src.scheduler import default_policies, greedy, make_job_stream, predictive, simulate


# ---------- orbit geometry ------------------------------------------------
def test_period_matches_kepler_by_hand():
    # a = 6778.137 km; T = 2 pi sqrt(a^3/mu) = 5553.6 s = 92.56 min
    assert orbit_period_min(400) == pytest.approx(92.56, abs=0.02)


def test_eclipse_at_beta_zero_by_hand():
    # x = sqrt(400^2 + 2*6378.137*400)/6778.137 = 0.3352... arccos -> 70.2 deg
    # fraction 70.2/180 = 0.390 -> 0.390 * 92.56 = 36.1 min
    assert eclipse_duration_min(400, 0) == pytest.approx(36.1, abs=0.1)


def test_no_eclipse_above_critical_beta():
    beta_star = math.degrees(math.asin(6378.137 / (6378.137 + 400)))  # ~70.2 deg
    assert eclipse_duration_min(400, beta_star + 1) == 0.0
    assert eclipse_duration_min(400, beta_star - 5) > 0.0


def test_eclipse_shrinks_with_beta():
    lengths = [eclipse_duration_min(400, b) for b in (0, 30, 50, 60, 65)]
    assert all(a > b for a, b in zip(lengths, lengths[1:]))


# ---------- solar input ---------------------------------------------------
def test_sun_tracking_energy_is_peak_times_sunlit_time():
    cfg = OrbitPowerConfig(panel_mode="sun_tracking", dt_min=0.01)
    b = orbit_energy_budget(cfg)
    expected = 9.0 * (cfg.period_min - cfg.eclipse_min) / 60  # 8.47 Wh
    assert b["energy_in_wh"] == pytest.approx(expected, rel=0.01)


def test_fixed_panel_energy_is_cosine_integral():
    # Clipped cosine over a full orbit: integral = peak * T / pi (the eclipse
    # lies entirely in the half of the orbit where cos < 0 at beta = 0).
    cfg = OrbitPowerConfig(panel_mode="zenith_fixed", dt_min=0.01)
    b = orbit_energy_budget(cfg)
    assert b["energy_in_wh"] == pytest.approx(9.0 * cfg.period_min / math.pi / 60, rel=0.01)


def test_no_power_in_eclipse():
    cfg = OrbitPowerConfig()
    mid_eclipse = cfg.period_min / 2
    assert float(solar_input_w(mid_eclipse, cfg)) == 0.0
    assert float(solar_input_w(0.0, cfg)) == cfg.array_peak_w


# ---------- battery -------------------------------------------------------
def test_battery_discharge_pays_efficiency():
    cfg = OrbitPowerConfig(initial_soc=0.5)
    b = Battery(cfg)
    b.step(-6.0, 0.5)  # deliver 3 Wh to the load -> 3 / 0.95 = 3.158 Wh from storage
    assert b.energy_wh == pytest.approx(6.0 - 3.0 / 0.95)


def test_battery_charge_limit_and_full_clip():
    cfg = OrbitPowerConfig(initial_soc=0.99)
    b = Battery(cfg)
    r = b.step(10.0, 1.0)  # 10 W offered, 6 W accepted, room 0.12 Wh
    assert b.energy_wh == pytest.approx(cfg.battery_capacity_wh)
    # wasted = 4 W over the charge limit + whatever didn't fit
    assert r.wasted_wh == pytest.approx(4.0 + (6.0 * 0.95 - 0.12) / 0.95)


def test_projection_matches_battery_step():
    cfg = OrbitPowerConfig(initial_soc=0.6)
    rng = np.random.default_rng(1)
    net = rng.uniform(-8, 8, 200)
    b = Battery(cfg)
    stepped = []
    for p in net:
        b.step(p, cfg.dt_min / 60)
        stepped.append(b.energy_wh)
    projected = project_energy(0.6 * cfg.battery_capacity_wh, net, cfg)
    assert np.allclose(stepped, projected)


# ---------- scheduler -----------------------------------------------------
def test_same_seed_same_jobs():
    a = make_job_stream(duration_min=2000, seed=7)
    b = make_job_stream(duration_min=2000, seed=7)
    assert [(x.arrival_min, x.profile.name) for x in a] == [(x.arrival_min, x.profile.name) for x in b]


def test_job_accounting_adds_up():
    cfg = OrbitPowerConfig()
    arrivals = make_job_stream(duration_min=3000, seed=3)
    for p in default_policies():
        r = simulate(cfg, arrivals, p, duration_min=3000)
        assert r.completed + r.missed <= r.arrived
        assert r.arrived - (r.completed + r.missed) < 15  # only jobs still queued at the end


def test_predictive_never_breaks_floor_when_budget_closes():
    cfg = OrbitPowerConfig()
    r = simulate(cfg, make_job_stream(seed=0), predictive(0.5))
    assert r.min_soc >= cfg.floor_soc - 0.01
    assert r.load_shed_min == 0


def test_energy_conservation():
    # Every Wh is accounted for: stored change = (offered - wasted) * eta_c - delivered / eta_d
    cfg = OrbitPowerConfig(initial_soc=0.5)
    b = Battery(cfg)
    start = b.energy_wh
    dt_h = 1 / 60
    rng = np.random.default_rng(5)
    books = 0.0
    for p in rng.uniform(-7, 9, 2000):
        r = b.step(p, dt_h)
        if p >= 0:
            books += (p * dt_h - r.wasted_wh) * cfg.charge_efficiency
        else:
            books -= (-p * dt_h - r.unserved_wh) / cfg.discharge_efficiency
    assert b.energy_wh - start == pytest.approx(books, abs=1e-9)


def test_soc_stays_physical():
    cfg = OrbitPowerConfig(initial_soc=0.5, array_peak_w=6.0)
    r = simulate(cfg, make_job_stream(duration_min=3000, seed=2), greedy(), duration_min=3000)
    assert 0.0 <= r.soc.min() and r.soc.max() <= 1.0 + 1e-9
