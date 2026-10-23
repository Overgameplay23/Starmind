"""
sensors.py — one interface for every power monitor: `sensor.read()` -> (volts, amps).

Supported:
  ina226  direct register driver (no vendor library needed): pip install smbus2
  ina260  Adafruit library:  pip install adafruit-blinka adafruit-circuitpython-ina260
  ina219  Adafruit library:  pip install adafruit-blinka adafruit-circuitpython-ina219
  fake    no hardware, for dry runs

How the INA226 works (the one you have)
---------------------------------------
The chip measures two voltages:
  * shunt voltage: the tiny drop across the shunt resistor, 2.5 uV per count
  * bus voltage:   the load-side supply voltage, 1.25 mV per count
Current comes from Ohm's law, I = V_shunt / R_shunt, so we need R_shunt. It is the
big resistor on the module; read its marking:
    R100 = 0.100 ohm (max ~0.8 A: too small for a Pi)
    R010 = 0.010 ohm (max ~8.2 A)
    R008 = 0.008 ohm (max ~10.2 A, common on "10 A" modules)
    R002 = 0.002 ohm (max ~41 A)
The shunt input saturates at 81.92 mV, so max current = 0.08192 V / R_shunt.
We compute current ourselves rather than using the chip's calibration register,
so the only thing to get right is R_shunt.
"""

from __future__ import annotations

import math
import time


class FakeSensor:
    """Pretends to be a Pi: ~3 W idle, ~6 W while 'busy'. For dry runs only."""

    busy = False

    def read(self) -> tuple[float, float]:
        watts = (6.0 if FakeSensor.busy else 3.0) + 0.05 * math.sin(time.time() * 50)
        return 5.1, watts / 5.1


# ----------------------------------------------------------------------
# INA226
# ----------------------------------------------------------------------
INA226_CONFIG = 0x00
INA226_SHUNT = 0x01
INA226_BUS = 0x02
INA226_MANUFACTURER_ID = 0xFE  # reads 0x5449 ("TI")
INA226_DIE_ID = 0xFF  # reads 0x2260 on an INA226

# Config register: [15] reset | [14:12] fixed 100 | [11:9] averaging |
#                  [8:6] bus conversion time | [5:3] shunt conversion time | [2:0] mode
# averaging 001 = 4 samples, conversion time 100 = 1.1 ms, mode 111 = continuous shunt + bus.
# One fresh reading every 4 x (1.1 + 1.1) ms = 8.8 ms -> about 113 per second.
INA226_CONFIG_VALUE = 0x4000 | (0b001 << 9) | (0b100 << 6) | (0b100 << 3) | 0b111  # 0x4327

SHUNT_LSB_V = 2.5e-6
BUS_LSB_V = 1.25e-3


def swap16(word: int) -> int:
    """SMBus returns the low byte first; the INA226 sends the high byte first."""
    return ((word & 0xFF) << 8) | (word >> 8)


def to_signed16(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


class INA226Sensor:
    def __init__(self, address: int = 0x40, shunt_ohms: float = 0.008, bus_number: int = 1, bus=None):
        if bus is None:
            from smbus2 import SMBus

            bus = SMBus(bus_number)
        self.bus, self.addr, self.r_shunt = bus, address, shunt_ohms
        maker, die = self._read(INA226_MANUFACTURER_ID), self._read(INA226_DIE_ID)
        if maker != 0x5449 or (die >> 4) != 0x226:
            raise RuntimeError(
                f"device at {address:#x} doesn't look like an INA226 "
                f"(manufacturer {maker:#06x}, die {die:#06x}); check wiring and address"
            )
        self._write(INA226_CONFIG, INA226_CONFIG_VALUE)
        self.max_current_a = 0.08192 / shunt_ohms

    def _read(self, reg: int) -> int:
        return swap16(self.bus.read_word_data(self.addr, reg))

    def _write(self, reg: int, value: int) -> None:
        self.bus.write_word_data(self.addr, reg, swap16(value))

    def read(self) -> tuple[float, float]:
        shunt_v = to_signed16(self._read(INA226_SHUNT)) * SHUNT_LSB_V
        bus_v = self._read(INA226_BUS) * BUS_LSB_V
        return bus_v, shunt_v / self.r_shunt


# ----------------------------------------------------------------------
# INA219 / INA260 (Adafruit libraries)
# ----------------------------------------------------------------------
class INA219Sensor:
    """Usually a 0.1 ohm shunt -> about 3.2 A max. Fine for a Pi 4 / Pi 400."""

    def __init__(self, address: int = 0x40):
        import board
        from adafruit_ina219 import ADCResolution, INA219

        self.ina = INA219(board.I2C(), addr=address)
        self.ina.bus_adc_resolution = ADCResolution.ADCRES_12BIT_4S
        self.ina.shunt_adc_resolution = ADCResolution.ADCRES_12BIT_4S

    def read(self) -> tuple[float, float]:
        return self.ina.bus_voltage, self.ina.current / 1000.0


class INA260Sensor:
    """Built-in 2 mohm shunt, good to 15 A."""

    def __init__(self, address: int = 0x40):
        import adafruit_ina260
        import board

        self.ina = adafruit_ina260.INA260(board.I2C(), address=address)
        self.ina.averaging_count = adafruit_ina260.AveragingCount.COUNT_4
        self.ina.current_conversion_time = adafruit_ina260.ConversionTime.TIME_1_1_ms
        self.ina.voltage_conversion_time = adafruit_ina260.ConversionTime.TIME_1_1_ms

    def read(self) -> tuple[float, float]:
        return self.ina.voltage, self.ina.current / 1000.0


# ----------------------------------------------------------------------
def add_sensor_args(ap) -> None:
    ap.add_argument("--sensor", choices=["ina226", "ina260", "ina219", "fake"], default="ina226")
    ap.add_argument("--address", type=lambda s: int(s, 0), default=0x40, help="I2C address, e.g. 0x40")
    ap.add_argument("--shunt", type=float, default=0.008,
                    help="INA226 shunt resistance in ohms: R008 -> 0.008, R010 -> 0.01, R100 -> 0.1")


def make_sensor(args):
    if args.sensor == "fake":
        return FakeSensor()
    if args.sensor == "ina226":
        return INA226Sensor(args.address, args.shunt)
    if args.sensor == "ina219":
        return INA219Sensor(args.address)
    return INA260Sensor(args.address)
