"""
sensor_check.py — Step 1 on the Pi: prove the sensor works before measuring anything.

Prints 10 readings of voltage, current and power. What "correct" looks like:
  * voltage about 5.0-5.2 V (it sags a little under load: that's normal)
  * current about 0.4-0.7 A for an idle Pi 4, more for a Pi 5
  * power = V x I, so about 2-4 W idle
If current is negative, VIN+ and VIN- are swapped. If voltage is ~0, the
sensor is on the wrong side of the supply or not powered.

    python3 measure/sensor_check.py --sensor ina219
"""

import argparse
import time


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sensor", choices=["ina260", "ina219"], default="ina260")
    ap.add_argument("--address", type=lambda s: int(s, 0), default=0x40)
    args = ap.parse_args()

    import board

    i2c = board.I2C()
    if args.sensor == "ina219":
        from adafruit_ina219 import INA219

        ina = INA219(i2c, addr=args.address)
        read = lambda: (ina.bus_voltage, ina.current / 1000.0)
    else:
        import adafruit_ina260

        ina = adafruit_ina260.INA260(i2c, address=args.address)
        read = lambda: (ina.voltage, ina.current / 1000.0)

    print(f"{'V':>8} {'A':>8} {'W':>8}")
    for _ in range(10):
        v, a = read()
        print(f"{v:8.3f} {a:8.3f} {v * a:8.3f}")
        time.sleep(0.5)


if __name__ == "__main__":
    main()
