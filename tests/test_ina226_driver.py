"""
Tests the INA226 driver against a fake I2C bus that behaves like the datasheet:
registers are 16-bit, sent high byte first, and SMBus word reads return the
low byte first. If these pass, the byte-order and scaling math is right; what's
left to check on hardware is wiring and the shunt value.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "measure"))
from sensors import INA226_CONFIG_VALUE, INA226Sensor, swap16  # noqa: E402


class FakeINA226Bus:
    def __init__(self, regs):
        self.regs = dict(regs)  # register -> 16-bit value as the chip holds it

    def read_word_data(self, addr, reg):
        return swap16(self.regs[reg])  # what SMBus hands back: low byte first

    def write_word_data(self, addr, reg, word):
        self.regs[reg] = swap16(word)


def chip(shunt_counts, bus_counts):
    return {0xFE: 0x5449, 0xFF: 0x2260, 0x00: 0x4127,
            0x01: shunt_counts & 0xFFFF, 0x02: bus_counts}


def test_config_register_value():
    assert INA226_CONFIG_VALUE == 0x4327


def test_reads_volts_and_amps():
    # 5.100 V bus -> 4080 counts of 1.25 mV. 0.75 A through 8 mohm -> 6.0 mV -> 2400 counts of 2.5 uV.
    bus = FakeINA226Bus(chip(2400, 4080))
    s = INA226Sensor(shunt_ohms=0.008, bus=bus)
    v, a = s.read()
    assert v == pytest.approx(5.100)
    assert a == pytest.approx(0.75)
    assert bus.regs[0x00] == 0x4327  # config written
    assert s.max_current_a == pytest.approx(10.24)


def test_negative_current_means_swapped_inputs():
    bus = FakeINA226Bus(chip(-2400, 4080))
    v, a = INA226Sensor(shunt_ohms=0.008, bus=bus).read()
    assert a == pytest.approx(-0.75)


def test_rejects_wrong_chip():
    regs = chip(0, 0)
    regs[0xFF] = 0x2270  # some other part
    with pytest.raises(RuntimeError):
        INA226Sensor(bus=FakeINA226Bus(regs))
