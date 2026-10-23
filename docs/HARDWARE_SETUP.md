# Phase 2 hardware setup: measuring energy per inference

Hardware: **Raspberry Pi 400 + INA226 module**. The INA219 and INA260 also work: pass
`--sensor ina219` or `--sensor ina260` in the commands below.

Goal: one number per model, **joules per inference above idle**, measured the same way
every time. That number replaces the made-up values in `src/workload_profile.py`.

## The idea

The INA226 sits in series with the Pi's 5 V supply, like an ammeter. All of the Pi's
current flows through a tiny shunt resistor on the module. The chip measures the voltage
across that resistor and gets current from Ohm's law:

$$
I = \frac{V_{\text{shunt}}}{R_{\text{shunt}}}
$$

It also measures the supply voltage, so $P = V \cdot I$. The Pi reads the chip over I2C and
logs its own power while it runs inference. Energy is the area under the power curve, minus
what the Pi uses when idle:

$$
E_{\text{per inference}} = \frac{\int_{t_0}^{t_1} P(t)\,dt \;-\; P_{\text{idle}}\,(t_1 - t_0)}{N}
$$

## Step 1: know your shunt

The shunt is the large resistor on the INA226 module. Read the marking printed on it:

| Marking | Resistance | `--shunt` | Max current | OK for a Pi 400? |
|---|---|---|---|---|
| R100 | 0.1 Ω | `0.1` | 0.82 A | **No**, the Pi exceeds it under load |
| R010 | 0.01 Ω | `0.01` | 8.2 A | Yes |
| R008 | 0.008 Ω | `0.008` | 10.2 A | Yes (typical "10 A" module) |
| R002 | 0.002 Ω | `0.002` | 41 A | Works, but coarse (1.25 mA steps) |

Max current is $81.92\ \text{mV} / R_{\text{shunt}}$, because the chip's shunt input saturates at
81.92 mV. **Getting `--shunt` wrong scales every current reading by the same wrong factor**,
so check it carefully.

## Step 2: put the sensor in series with the Pi's power

The Pi 400 takes 5.1 V over USB-C and doesn't use USB Power Delivery, so it only needs
5 V and ground passed through correctly.

**Option A (recommended): USB-C inline breakout.** A male-to-female USB-C pass-through
board with exposed VBUS pads. Plug the official Pi 400 supply into one end and the Pi into
the other, then route VBUS through the INA226:

```
 supply VBUS ──► IN+ [shunt] IN- ──► Pi VBUS
 supply GND  ───────────────────────► Pi GND  (straight through; leave CC lines connected)
```

**Option B: cut a USB-A to USB-C cable.** Use a 5 V / 3 A USB-A supply. Route the red (VBUS)
wire through IN+ → IN- and pass the black (GND) straight through. The data wires aren't needed.

Don't back-power the Pi 400 through its GPIO 5 V pins. That bypasses its input protection.

**Bus-voltage pin:** some INA226 modules have a separate VBUS/VBS pin. If `sensor_check.py`
shows a sensible current but about 0 V, connect that pin to IN- (the Pi side).

## Step 3: wire I2C to the Pi 400's rear GPIO header

| INA226 pin | Pi header pin |
|---|---|
| VCC | pin 1 (3.3 V) |
| GND | pin 6 (GND) |
| SDA | pin 3 (GPIO2) |
| SCL | pin 5 (GPIO3) |

The Pi 400's header faces backwards, so it's easy to flip it mentally. Check pin 1 against a
Pi 400 pinout diagram before connecting anything. The INA226's GND must be shared with the Pi's
GND; it is, once both go to pin 6.

## Step 4: software

```bash
sudo raspi-config        # Interface Options -> I2C -> Enable
                         # System Options -> Boot -> Console (no desktop: steadier idle power)
sudo reboot
sudo apt install -y i2c-tools python3-venv git
i2cdetect -y 1           # the INA226 should appear at 40 (or 41-4f if A0/A1 are strapped)
python3 -m venv ~/starmind-venv && source ~/starmind-venv/bin/activate
pip install smbus2 numpy
git clone https://github.com/Overgameplay23/Starmind && cd Starmind
python3 measure/sensor_check.py --sensor ina226 --shunt 0.008    # use YOUR shunt value
```

Expected at idle: about 4.9–5.2 V, 0.5–0.9 A, 2.5–4.5 W. If the current is negative, IN+ and
IN- are swapped. If the device doesn't respond, check SDA/SCL and that I2C is enabled.

**Sanity check with a known load (optional, recommended):** if you have a multimeter, put it in
series too and compare currents. Agreement within a few percent means your shunt value is right.

## Step 5: measurement protocol

Run everything over SSH if you can, with nothing extra plugged in. Keep Wi-Fi in the same state
for every run.

1. **Pipeline test**, using the dependency-free workload:
   ```bash
   python3 measure/measure_energy.py --sensor ina226 --shunt 0.008 --label matmul_full \
       --inferences 300 --cmd "python3 measure/bench_infer.py --model matmul --n 300"
   ```
2. **Real model at full speed.** Run `pip install ultralytics` first. This needs the 64-bit
   Raspberry Pi OS (`uname -m` should print `aarch64`); the first run downloads `yolov8n.pt`. On a Pi 400, expect on the order of a second per image at 640 px, so try
   `--imgsz 320` too:
   ```bash
   python3 measure/measure_energy.py --sensor ina226 --shunt 0.008 --label yolo_full_320 \
       --inferences 50 --cmd "python3 measure/bench_infer.py --model yolo --n 50 --imgsz 320"
   ```
3. **Throttled.** Cap the CPU clock (the Pi 400 tops out at 1.8 GHz), then repeat with a new label:
   ```bash
   echo 1200000 | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_max_freq      # 1.2 GHz
   # ... repeat step 2 with --label yolo_1200MHz_320 ...
   cat /sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq \
       | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_max_freq                # back to max
   ```
   Try 600 MHz, 1.0, 1.2, 1.5 and 1.8 GHz. You're looking for the point where energy per
   inference stops improving; below it, you're only getting slower.
4. **Repeat every condition at least 5 times.** Report the mean and spread, not your best run.

Results are appended to `measure/results.csv`. Commit that file.

## Things that quietly ruin measurements

* **Thermal throttling.** The Pi 400's large internal heatsink makes this less likely than on a
  bare Pi 4, but check: `vcgencmd get_throttled` should print `throttled=0x0` before and after a run.
* **Too few samples.** The script refuses windows with fewer than 20 samples; run more inferences.
* **Counting model loading.** `bench_infer.py` prints JOB_START/JOB_END markers so only the
  inference loop is counted. If you measure your own script, add the same markers.
* **A changing idle baseline.** Background updates or Wi-Fi scans shift idle power. If the idle
  standard deviation printed by the script is large, re-run.

## Then

Send the `results.csv` rows back (or commit them). The means become `JobProfile`s in
`MEASURED_PROFILES`, and the simulation reruns on your measured numbers.
