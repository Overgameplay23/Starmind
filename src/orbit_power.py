"""
orbit_power.py — the physics layer.

Everything the spacecraft's power system "is" lives here:
  1. Where we are in the orbit, and whether the Sun is visible.
  2. How much power the solar array makes at that moment.
  3. How the battery responds to a net surplus or deficit.

Read this file first. Every other module just asks it questions.

Conventions
-----------
* Time is in minutes. Power is in watts. Energy is in watt-hours (Wh).
* Orbit angle theta is measured from the "subsolar point" (local noon),
  so theta = 0 deg is the sunniest moment and theta = 180 deg is the
  middle of the eclipse.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

EARTH_RADIUS_KM = 6378.137
EARTH_MU_KM3_S2 = 398600.4418  # gravitational parameter, G * M_earth


@dataclass
class OrbitPowerConfig:
    """Every physical assumption in one place. Change numbers here, not in code."""

    # --- Orbit ---------------------------------------------------------
    altitude_km: float = 400.0  # roughly ISS altitude
    beta_deg: float = 0.0  # Sun angle off the orbit plane; 0 = longest eclipse

    # --- Solar array ---------------------------------------------------
    array_peak_w: float = 9.0
    # "sun_tracking": panel always faces the Sun -> flat output in sunlight.
    # "zenith_fixed": panel bolted to the top of a nadir-pointing satellite ->
    #                 output follows cos(angle to Sun), zero when Sun is behind it.
    panel_mode: str = "sun_tracking"

    # --- Loads ---------------------------------------------------------
    bus_load_w: float = 2.5  # radios, ADCS, heaters, flight computer: always on

    # --- Battery -------------------------------------------------------
    battery_capacity_wh: float = 12.0
    max_depth_of_discharge: float = 0.70  # 0.70 -> floor at 30 % state of charge
    initial_soc: float = 0.80
    charge_efficiency: float = 0.95  # fraction of charging energy actually stored
    discharge_efficiency: float = 0.95  # fraction of stored energy actually delivered
    max_charge_w: float = 6.0  # Li-ion charge-rate limit (0.5C for a 12 Wh pack)

    # --- Simulation ----------------------------------------------------
    dt_min: float = 1.0

    # Derived values are filled in by __post_init__ so they can't drift out of sync.
    period_min: float = field(init=False)
    eclipse_min: float = field(init=False)

    def __post_init__(self) -> None:
        if self.panel_mode not in ("sun_tracking", "zenith_fixed"):
            raise ValueError(f"unknown panel_mode {self.panel_mode!r}")
        self.period_min = orbit_period_min(self.altitude_km)
        self.eclipse_min = eclipse_duration_min(self.altitude_km, self.beta_deg)

    @property
    def floor_soc(self) -> float:
        return 1.0 - self.max_depth_of_discharge

    @property
    def floor_wh(self) -> float:
        return self.floor_soc * self.battery_capacity_wh

    @property
    def sunlight_min(self) -> float:
        return self.period_min - self.eclipse_min


# ----------------------------------------------------------------------
# Orbit geometry
# ----------------------------------------------------------------------
def orbit_period_min(altitude_km: float) -> float:
    """Kepler's third law for a circular orbit: T = 2*pi*sqrt(a^3 / mu)."""
    a = EARTH_RADIUS_KM + altitude_km
    return 2.0 * math.pi * math.sqrt(a**3 / EARTH_MU_KM3_S2) / 60.0


def eclipse_duration_min(altitude_km: float, beta_deg: float) -> float:
    """
    Time per orbit spent in Earth's shadow (cylindrical-shadow model).

        f_eclipse = (1/180 deg) * arccos( sqrt(h^2 + 2 R h) / ((R + h) cos beta) )

    Above the critical beta angle the orbit never enters the shadow.
    """
    h, r = altitude_km, EARTH_RADIUS_KM
    cos_beta = math.cos(math.radians(beta_deg))
    if cos_beta <= 0:
        return 0.0
    x = math.sqrt(h * h + 2.0 * r * h) / ((r + h) * cos_beta)
    if x >= 1.0:
        return 0.0  # beta above critical angle: permanent sunlight
    fraction = math.degrees(math.acos(x)) / 180.0
    return fraction * orbit_period_min(altitude_km)


def orbit_angle_deg(t_min, cfg: OrbitPowerConfig):
    """Orbit angle measured from local noon, in [0, 360)."""
    return (np.asarray(t_min, dtype=float) / cfg.period_min * 360.0) % 360.0


def sunlight_mask(t_min, cfg: OrbitPowerConfig):
    """True where the spacecraft can see the Sun. Eclipse is centered on 180 deg."""
    theta = orbit_angle_deg(t_min, cfg)
    half_eclipse_deg = cfg.eclipse_min / cfg.period_min * 180.0
    return np.abs(theta - 180.0) > half_eclipse_deg


def solar_input_w(t_min, cfg: OrbitPowerConfig):
    """Array output in watts at each time."""
    sun = sunlight_mask(t_min, cfg)
    if cfg.panel_mode == "sun_tracking":
        return np.where(sun, cfg.array_peak_w, 0.0)
    # zenith_fixed: incidence angle depends on orbit angle AND beta.
    theta = np.radians(orbit_angle_deg(t_min, cfg))
    cos_incidence = np.cos(theta) * math.cos(math.radians(cfg.beta_deg))
    return np.where(sun, cfg.array_peak_w * np.clip(cos_incidence, 0.0, None), 0.0)


# ----------------------------------------------------------------------
# Battery
# ----------------------------------------------------------------------
@dataclass
class StepResult:
    stored_change_wh: float  # change in stored energy this step
    wasted_wh: float  # sunlight the array could have produced but nothing could use
    unserved_wh: float  # load energy the battery could not supply (brownout)


class Battery:
    """
    Energy bookkeeping with losses.

    Positive net power (surplus) charges the battery, limited by max_charge_w,
    with charge_efficiency loss. Anything that won't fit is "wasted": in a real
    spacecraft a shunt regulator dumps it as heat.

    Negative net power (deficit) discharges the battery. Delivering E Wh to the
    load costs E / discharge_efficiency Wh of stored energy.
    """

    def __init__(self, cfg: OrbitPowerConfig):
        self.cfg = cfg
        self.energy_wh = cfg.initial_soc * cfg.battery_capacity_wh

    @property
    def soc(self) -> float:
        return self.energy_wh / self.cfg.battery_capacity_wh

    def step(self, net_power_w: float, dt_h: float) -> StepResult:
        cfg = self.cfg
        before = self.energy_wh
        wasted = unserved = 0.0
        if net_power_w >= 0:
            accepted_w = min(net_power_w, cfg.max_charge_w)
            wasted += (net_power_w - accepted_w) * dt_h
            stored = accepted_w * cfg.charge_efficiency * dt_h
            room = cfg.battery_capacity_wh - self.energy_wh
            if stored > room:
                # Surplus beyond a full battery is dumped. Convert back to array-side Wh.
                wasted += (stored - room) / cfg.charge_efficiency
                stored = room
            self.energy_wh += stored
        else:
            needed = (-net_power_w) * dt_h / cfg.discharge_efficiency
            if needed > self.energy_wh:
                unserved = (needed - self.energy_wh) * cfg.discharge_efficiency
                needed = self.energy_wh
            self.energy_wh -= needed
        return StepResult(self.energy_wh - before, wasted, unserved)


def project_energy(
    energy_wh: float, net_power_w: np.ndarray, cfg: OrbitPowerConfig
) -> np.ndarray:
    """
    Fast look-ahead: given a starting energy and a planned net-power profile,
    return the stored energy after each step. Same physics as Battery.step.
    Used by the predictive scheduler to ask "what if I start this job now?"
    """
    dt_h = cfg.dt_min / 60.0
    out = np.empty(len(net_power_w))
    e = energy_wh
    cap, eta_c, eta_d, pmax = (
        cfg.battery_capacity_wh,
        cfg.charge_efficiency,
        cfg.discharge_efficiency,
        cfg.max_charge_w,
    )
    for i, p in enumerate(net_power_w):
        if p >= 0:
            e = min(cap, e + min(p, pmax) * eta_c * dt_h)
        else:
            e = max(0.0, e + p * dt_h / eta_d)
        out[i] = e
    return out


# ----------------------------------------------------------------------
# First-principles check: the per-orbit energy budget
# ----------------------------------------------------------------------
def orbit_energy_budget(cfg: OrbitPowerConfig, avg_compute_w: float = 0.0) -> dict:
    """
    Energy in vs. energy out over ONE orbit, before any scheduling.

    If 'margin_wh' is negative, no scheduler can save you: the battery trends
    to empty. Scheduling only moves loads in time; it cannot create energy.
    """
    n = int(round(cfg.period_min / cfg.dt_min))
    t = np.arange(n) * cfg.dt_min
    dt_h = cfg.dt_min / 60.0
    solar = solar_input_w(t, cfg)
    load = cfg.bus_load_w + avg_compute_w
    energy_in = float(solar.sum() * dt_h)
    energy_out = load * cfg.period_min / 60.0

    # Energy that has to pass through the battery pays round-trip losses.
    deficit_steps = np.clip(load - solar, 0.0, None)
    through_battery_wh = float(deficit_steps.sum() * dt_h)
    eta_rt = cfg.charge_efficiency * cfg.discharge_efficiency
    loss_wh = through_battery_wh * (1.0 / eta_rt - 1.0)

    return {
        "period_min": cfg.period_min,
        "eclipse_min": cfg.eclipse_min,
        "energy_in_wh": energy_in,
        "bus_wh": cfg.bus_load_w * cfg.period_min / 60.0,
        "compute_wh": avg_compute_w * cfg.period_min / 60.0,
        "battery_loss_wh": loss_wh,
        "margin_wh": energy_in - energy_out - loss_wh,
    }
