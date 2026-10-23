"""
measure_energy.py — Phase 2: measure the real energy cost of one inference.

Runs on the Raspberry Pi, with a power monitor (INA226 by default) wired in
series with the Pi's 5 V supply (VIN+ from the supply, VIN- to the Pi) and its
SDA/SCL/GND on the Pi's GPIO header. The Pi measures its own power.

Protocol (same every time, so runs are comparable):
  1. Idle baseline: log power for --idle seconds with nothing running.
     The logger itself is running during the baseline, so its own cost
     gets subtracted along with the Pi's idle draw.
  2. Run your inference command, which must do exactly --inferences inferences.
  3. Energy per inference = (integral of P dt  -  P_idle * duration) / N
  4. Append one row to results.csv. Repeat with --label "...throttled" after
     capping the CPU clock, and run each condition 5+ times.

Example (INA226 with an R008 shunt):
  python3 measure/measure_energy.py --sensor ina226 --shunt 0.008 --label yolo_full \
      --inferences 100 --cmd "python3 measure/bench_infer.py --model yolo --n 100"

Dry run without hardware (fake sensor, to check the script works):
  python3 measure/measure_energy.py --sensor fake --label test --inferences 200 \
      --cmd "python3 measure/bench_infer.py --model matmul --n 200" --idle 3

Setup on the Pi: see docs/HARDWARE_SETUP.md. Not yet run on real hardware.
"""

from __future__ import annotations

import argparse
import csv
import shlex
import statistics
import subprocess
import threading
import time
from pathlib import Path

from sensors import FakeSensor, add_sensor_args, make_sensor


class Logger:
    """Samples power in a background thread at roughly `hz` samples per second."""

    def __init__(self, sensor, hz: float = 50.0):
        self.sensor, self.period = sensor, 1.0 / hz
        self.samples: list[tuple[float, float]] = []
        self._stop = threading.Event()

    def __enter__(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join()

    def _run(self):
        nxt = time.monotonic()
        while not self._stop.is_set():
            volts, amps = self.sensor.read()
            self.samples.append((time.monotonic(), volts * amps))
            nxt += self.period
            time.sleep(max(0.0, nxt - time.monotonic()))


def integrate_wh(samples: list[tuple[float, float]]) -> tuple[float, float]:
    """Trapezoid rule over real timestamps. Returns (energy_J, duration_s)."""
    energy_j = 0.0
    for (t0, p0), (t1, p1) in zip(samples, samples[1:]):
        energy_j += 0.5 * (p0 + p1) * (t1 - t0)
    return energy_j, samples[-1][0] - samples[0][0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cmd", required=True, help="command that runs exactly N inferences")
    ap.add_argument("--inferences", type=int, required=True)
    ap.add_argument("--label", required=True, help='e.g. "yolo_full" or "yolo_throttled_1200MHz"')
    ap.add_argument("--idle", type=float, default=60.0, help="idle baseline seconds")
    ap.add_argument("--hz", type=float, default=50.0)
    ap.add_argument("--out", default=str(Path(__file__).with_name("results.csv")))
    add_sensor_args(ap)
    args = ap.parse_args()
    sensor = make_sensor(args)

    print(f"1/2 idle baseline for {args.idle:.0f} s: don't touch anything...")
    with Logger(sensor, args.hz) as idle_log:
        time.sleep(args.idle)
    idle_powers = [p for _, p in idle_log.samples]
    p_idle = statistics.mean(idle_powers)
    print(f"    idle {p_idle:.3f} W  (std {statistics.pstdev(idle_powers):.3f} W, {len(idle_powers)} samples)")

    print(f"2/2 running: {args.cmd}")
    with Logger(sensor, args.hz) as run_log:
        FakeSensor.busy = True
        t0 = time.monotonic()
        proc = subprocess.run(shlex.split(args.cmd), check=True, capture_output=True, text=True)
        t1 = time.monotonic()
        FakeSensor.busy = False
    print(proc.stdout.strip())

    # If the job printed JOB_START/JOB_END markers, count only that window.
    marks = dict(line.split()[:2] for line in proc.stdout.splitlines() if line.startswith("JOB_"))
    if "JOB_START" in marks and "JOB_END" in marks:
        t0, t1 = float(marks["JOB_START"]), float(marks["JOB_END"])
        print(f"    using JOB_START/JOB_END window ({t1 - t0:.2f} s)")
    else:
        print("    WARNING: no JOB_START/JOB_END markers; start-up and model loading are included")
    window = [(t, p) for t, p in run_log.samples if t0 <= t <= t1]
    if len(window) < 20:
        raise SystemExit(f"only {len(window)} samples in the job window: run more inferences or raise --hz")
    runtime_s = t1 - t0

    energy_j, dur_s = integrate_wh(window)
    above_idle_j = energy_j - p_idle * dur_s
    per_inf_j = above_idle_j / args.inferences
    row = {
        "label": args.label,
        "inferences": args.inferences,
        "idle_w": round(p_idle, 4),
        "mean_power_w": round(energy_j / dur_s, 4),
        "power_above_idle_w": round(above_idle_j / dur_s, 4),
        "runtime_per_inference_s": round(runtime_s / args.inferences, 5),
        "energy_per_inference_j": round(per_inf_j, 5),
        "energy_per_inference_wh": float(f"{per_inf_j / 3600:.4g}"),
        "samples": len(window),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    for k, v in row.items():
        print(f"    {k:26s} {v}")

    out = Path(args.out)
    new = not out.exists()
    with out.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row))
        if new:
            w.writeheader()
        w.writerow(row)
    print(f"appended to {out}")


if __name__ == "__main__":
    main()
