"""
budget.py — run this BEFORE trusting any scheduler result.

Prints the per-orbit energy budget for the default config and a few variations.
If the margin is negative, the battery trends to empty over many orbits no
matter what the scheduler does: no policy can fix a negative budget.

    python -m tools.budget
    python -m tools.budget --array 7 --compute 2.0 --beta 30 --panel zenith_fixed
"""

from __future__ import annotations

import argparse

from src.orbit_power import OrbitPowerConfig, orbit_energy_budget


def show(cfg: OrbitPowerConfig, compute_w: float, label: str) -> None:
    b = orbit_energy_budget(cfg, compute_w)
    print(f"\n{label}")
    print(f"  orbit period        {b['period_min']:6.1f} min   (altitude {cfg.altitude_km:g} km)")
    print(f"  eclipse             {b['eclipse_min']:6.1f} min   (beta {cfg.beta_deg:g} deg)")
    print(f"  energy in (array)   {b['energy_in_wh']:6.2f} Wh    ({cfg.panel_mode}, {cfg.array_peak_w:g} W peak)")
    print(f"  bus load            {b['bus_wh']:6.2f} Wh    ({cfg.bus_load_w:g} W always on)")
    print(f"  compute (average)   {b['compute_wh']:6.2f} Wh    ({compute_w:g} W average)")
    print(f"  battery losses      {b['battery_loss_wh']:6.2f} Wh    (round trip {cfg.charge_efficiency * cfg.discharge_efficiency:.0%})")
    verdict = "closes" if b["margin_wh"] >= 0 else "DOES NOT CLOSE: no scheduler can fix this"
    print(f"  margin              {b['margin_wh']:+6.2f} Wh    -> budget {verdict}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--array", type=float, default=9.0)
    ap.add_argument("--compute", type=float, default=0.0, help="average compute watts over the orbit")
    ap.add_argument("--beta", type=float, default=0.0)
    ap.add_argument("--altitude", type=float, default=400.0)
    ap.add_argument("--panel", default=None, choices=["sun_tracking", "zenith_fixed"])
    args = ap.parse_args()

    modes = [args.panel] if args.panel else ["sun_tracking", "zenith_fixed"]
    for mode in modes:
        cfg = OrbitPowerConfig(array_peak_w=args.array, beta_deg=args.beta, altitude_km=args.altitude, panel_mode=mode)
        show(cfg, args.compute, f"== {mode} ==")


if __name__ == "__main__":
    main()
