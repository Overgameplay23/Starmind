# Phase 2 hardware setup: measuring energy per inference

Goal: one number per model, **joules per inference above idle**, measured the same way
every time. That number replaces the made-up values in `src/workload_profile.py`.

## The idea

A power monitor (INA219 or INA260) sits in series with the Pi's 5 V supply, like an
ammeter. It measures the voltage across a tiny shunt resistor, which gives current, and
the bus voltage. Power is $P = V \cdot I$. The Pi reads the sensor over I2C and logs
its own power while it runs inference.

Energy is the area under the power curve:

$$
E_{\text{per inference}} = \frac{\int_{t_0}^{t_1} P(t)\,dt \;-\; P_{\text{idle}}\,(t_1 - t_0)}{N}
$$

Subtracting $P_{\text{idle}}$ removes the cost of the Pi just existing, so what's left is
the cost of the job.

```
  5 V supply (+) ──► VIN+ [ INA shunt ] VIN- ──► Pi 5 V in
  5 V supply (–) ─────────────────────────────► Pi GND ── INA GND
                         INA VCC ◄── Pi 3.3 V (pin 1)
                         INA SDA ◄─► Pi GPIO2 (pin 3)
                         INA SCL ◄─► Pi GPIO3 (pin 5)
                         INA GND ─── Pi GND  (pin 6)
```

## Parts

* Raspberry Pi 4 or 5 with Raspberry Pi OS Lite (no desktop: less background power noise)
* INA260 (15 A, built-in shunt) or INA219 (about 3.2 A with the usual 0.1 Ω shunt; fine for a Pi 4,
  can clip on a busy Pi 5)
* A way to put the sensor in series with the 5 V supply (see below)
* Jumper wires

## Getting the sensor in series

**Option A: USB-C pass-through breakout (best for a Pi 4).** Two USB-C breakouts, or one
inline "pass-through" board, with VBUS routed through the INA. Keep the CC and GND lines
connected straight through.

**Option B: 5 V into the GPIO header (works for Pi 4 and Pi 5).** A regulated 5.1 V supply goes
through the INA into pin 2 (5 V) and pin 6 (GND). Two cautions:
* This bypasses the Pi's input protection. Use a good regulated supply, set the voltage
  *before* connecting, and never plug in USB power at the same time.
* A Pi 5 powered this way can't negotiate 5 A, so it limits USB current and may warn about the
  power supply. For inference with nothing on the USB ports, that's fine.

Either way, double-check polarity before powering on. A reversed 5 V supply can kill a Pi.

## Pi software setup

```bash
sudo raspi-config                  # Interface Options -> I2C -> Enable, then reboot
sudo apt install -y i2c-tools python3-venv
i2cdetect -y 1                     # the INA should show up at 40
python3 -m venv ~/starmind-venv && source ~/starmind-venv/bin/activate
pip install adafruit-blinka adafruit-circuitpython-ina219 adafruit-circuitpython-ina260 numpy
git clone https://github.com/Overgameplay23/Starmind && cd Starmind
python3 measure/sensor_check.py --sensor ina219    # or ina260
```

`sensor_check.py` should show about 5.0–5.2 V and 2–4 W idle. Negative current means VIN+ and
VIN- are swapped.

## Measurement protocol

Do these in order. Run everything over SSH with no monitor or keyboard attached, and keep
Wi-Fi in the same state for every run.

1. **Test the pipeline** with the dependency-free workload:
   ```bash
   python3 measure/measure_energy.py --sensor ina219 --label matmul_full --inferences 300 \
       --cmd "python3 measure/bench_infer.py --model matmul --n 300"
   ```
2. **Real model at full speed** (`pip install ultralytics` first; it downloads `yolov8n.pt`):
   ```bash
   python3 measure/measure_energy.py --sensor ina219 --label yolo_full --inferences 100 \
       --cmd "python3 measure/bench_infer.py --model yolo --n 100"
   ```
3. **Throttled.** Cap the CPU clock, then repeat with a new label:
   ```bash
   echo 1200000 | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_max_freq   # 1.2 GHz
   # ... run step 2 again with --label yolo_1200MHz ...
   cat /sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_max_freq   # back to max
   ```
   Try a few clock speeds. You're looking for where energy per inference stops improving;
   past that point you're only getting slower.
4. **Repeat each condition at least 5 times.** Report the mean and spread, not your best run.

Results are appended to `measure/results.csv`. Commit that file.

## Things that quietly ruin measurements

* **Thermal throttling.** A hot Pi slows itself down, which changes both power and runtime.
  Check `vcgencmd measure_temp` and `vcgencmd get_throttled` (0x0 means no throttling) before
  and after each run, and let it cool between runs.
* **Too few samples.** The script refuses windows with fewer than 20 samples. Run more inferences.
* **Counting model loading.** `bench_infer.py` prints JOB_START/JOB_END markers so only the
  inference loop is counted. If you measure your own script, add the same markers.
* **A changing idle baseline.** Background updates or Wi-Fi scans can shift idle power. If the idle
  standard deviation printed by the script is large, re-run.

## Then

Turn the mean of each condition into a `JobProfile` in `MEASURED_PROFILES`: power above idle,
runtime, and energy per job. Then rerun the simulation with your measured numbers.
