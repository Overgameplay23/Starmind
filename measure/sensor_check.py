"""
sensor_check.py — Step 1 on the Pi: prove the sensor works before measuring anything.

Prints 10 readings of voltage, current and power. What "correct" looks like on a Pi 400:
  * voltage about 4.9-5.2 V (it sags a little under load: that's normal)
  * current roughly 0.5-0.9 A at idle
  * power = V x I, so roughly 2.5-4.5 W at idle
If current is negative, VIN+ and VIN- are swapped. If voltage reads ~0, the
sensor's VBUS sense isn't connected to the supply.

    python3 measure/sensor_check.py --sensor ina226 --shunt 0.008
"""

import argparse
import time

from sensors import add_sensor_args, make_sensor


def main():
    ap = argparse.ArgumentParser()
    add_sensor_args(ap)
    args = ap.parse_args()
    sensor = make_sensor(args)
    if hasattr(sensor, "max_current_a"):
        print(f"INA226 found. Shunt {args.shunt} ohm -> max measurable current {sensor.max_current_a:.1f} A")

    print(f"{'V':>8} {'A':>8} {'W':>8}")
    for _ in range(10):
        v, a = sensor.read()
        print(f"{v:8.3f} {a:8.3f} {v * a:8.3f}")
        time.sleep(0.5)


if __name__ == "__main__":
    main()
