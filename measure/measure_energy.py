"""
measure_energy.py — Phase 2: measure the real energy cost of one inference.

Runs on the Raspberry Pi, with an INA260 wired in series with the Pi's 5 V
supply (VIN+ from the supply, VIN- to the Pi) and its SDA/SCL/GND on the Pi's
GPIO header. The Pi measures its own power.

Protocol (same every time, so runs are comparable):
  1. Idle baseline: log power for --idle seconds with nothing running.
     The logger itself is running during the baseline, so its own cost
     gets subtracted along with the Pi's idle draw.
  2. Run your inference command, which must do exactly --inferences inferences.
  3. Energy per inference = (integral of P dt  -  P_idle * duration) / N
  4. Append one row to results.csv. Repeat with --label "...throttled" after
     capping the CPU clock, and run each condition 5+ times.

Example:
  python3 measure/measure_energy.py --sensor ina219 --label "yolo_full" --inferences 100 \
      --cmd "python3 measure/bench_infer.py --model yolo --n 100"

Dry run without hardware (fake sensor, to check the script works):
  python3 measure/measure_energy.py --fake --label test --inferences 200 \
      --cmd "python3 measure/bench_infer.py --model matmul --n 200" --idle 3

Setup on the Pi:
  sudo raspi-config  -> Interface Options -> I2C -> enable
  pip install adafruit-circuitpython-ina260   (or -ina219 for an INA219)
  i2cdetect -y 1     -> the INA260 should answer at 0x40

NOTE: written against the Adafruit CircuitPython INA260 library; not yet run
on hardware. If an attribute name errors, check the library docs and fix it here.
"""

from __future__ import annotations

import argparse
import csv
import math
import shlex
import statistics
import subprocess
import threading
import time
from pathlib import Path


class FakeSensor:
    """Pretends to be a Pi: ~3 W idle, ~6 W while 'busy'. For dry runs only."""

    busy = False

    @property
    def power_w(self) -> float:
        base = 6.0 if FakeSensor.busy else 3.0
        return base + 0.05 * math.sin(time.time() * 50)


class INA219Sensor:
    """
    INA219 breakouts usually have a 0.1 ohm shunt -> about 3.2 A maximum.
    Fine for a Pi 4 doing inference; a Pi 5 under heavy load can exceed it.
    pip install adafruit-circuitpython-ina219
    """

    def __init__(self, address: int = 0x40):
        import board
        from adafruit_ina219 import ADCResolution, INA219

        self.ina = INA219(board.I2C(), addr=address)
        # 12-bit, 4-sample averaging on both channels: less noise, ~2 ms per reading.
        self.ina.bus_adc_resolution = ADCResolution.ADCRES_12BIT_4S
        self.ina.shunt_adc_resolution = ADCResolution.ADCRES_12BIT_4S

    @property
    def power_w(self) -> float:
        # bus_voltage is measured on the load side (VIN-), current in mA.
        return self.ina.bus_voltage * self.ina.current / 1000.0


class INA260Sensor:
    """INA260 has a built-in 2 mohm shunt, good to 15 A. pip install adafruit-circuitpython-ina260"""

    def __init__(self, address: int = 0x40):
        import adafruit_ina260
        import board

        self.ina = adafruit_ina260.INA260(board.I2C(), address=address)
        # Average 4 conversions of ~1.1 ms each: smooths noise, still ~200 Hz capable.
        self.ina.averaging_count = adafruit_ina260.AveragingCount.COUNT_4
        self.ina.current_conversion_time = adafruit_ina260.ConversionTime.TIME_1_1_ms
        self.ina.voltage_conversion_time = adafruit_ina260.ConversionTime.TIME_1_1_ms

    @property
    def power_w(self) -> float:
        # Compute P = V * I ourselves from the two raw readings.
        return self.ina.voltage * self.ina.current / 1000.0  # current is in mA


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
            self.samples.append((time.monotonic(), self.sensor.power_w))
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
    ap.add_argument("--sensor", choices=["ina260", "ina219"], default="ina260")
    ap.add_argument("--address", type=lambda s: int(s, 0), default=0x40, help="I2C address, e.g. 0x40")
    ap.add_argument("--fake", action="store_true", help="no hardware: fake sensor for a dry run")
    args = ap.parse_args()

    if args.fake:
        sensor = FakeSensor()
    elif args.sensor == "ina219":
        sensor = INA219Sensor(args.address)
    else:
        sensor = INA260Sensor(args.address)

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
