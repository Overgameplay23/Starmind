# Experiment results (20 seeds each, 0.08 jobs/min)

### baseline (9 W, tracking, beta 0)

_in 8.55 Wh/orbit, eclipse 36.1 min, floor 30%_


| policy | jobs done | missed | priority-1 missed | value done | min SoC | load-shed min | mean DoD | battery life (yr, notional) | wasted solar (Wh) |
|---|---|---|---|---|---|---|---|---|---|
| greedy | 796 | 15.7 ± 8.6 | 14.2 ± 7.2 | 97.1% | 21% | 591 | 26% | 4.8 | 72 |
| sunlight_only | 708 | 102.7 ± 6.1 | 100.3 ± 5.3 | 80.0% | 50% | 0 | 16% | 10.0 | 92 |
| threshold_55 | 808 | 3.6 ± 3.2 | 2.1 ± 1.7 | 99.5% | 24% | 32 | 25% | 5.2 | 72 |
| predictive_m0.5 | 809 | 1.8 ± 2.4 | 0.0 | 99.9% | 33% | 0 | 26% | 4.9 | 73 |

### shrink_array (7 W)

_in 6.65 Wh/orbit, eclipse 36.1 min, floor 30%_


| policy | jobs done | missed | priority-1 missed | value done | min SoC | load-shed min | mean DoD | battery life (yr, notional) | wasted solar (Wh) |
|---|---|---|---|---|---|---|---|---|---|
| greedy | 543 | 263.1 ± 20.9 | 169.9 ± 14.1 | 63.0% | 17% | 5383 | 16% | 10.3 | 0 |
| sunlight_only | 537 | 269.9 ± 19.4 | 179.8 ± 11.6 | 61.2% | 17% | 2815 | 15% | 11.4 | 0 |
| threshold_55 | 549 | 257.1 ± 20.6 | 165.2 ± 14.8 | 64.0% | 17% | 1142 | 15% | 10.8 | 0 |
| predictive_m0.5 | 736 | 72.0 ± 9.2 | 0.0 | 98.1% | 31% | 0 | 19% | 7.6 | 0 |

### heavy_workload (mix 0.30/0.30/0.40)

_in 8.55 Wh/orbit, eclipse 36.1 min, floor 30%_


| policy | jobs done | missed | priority-1 missed | value done | min SoC | load-shed min | mean DoD | battery life (yr, notional) | wasted solar (Wh) |
|---|---|---|---|---|---|---|---|---|---|
| greedy | 559 | 244.1 ± 19.5 | 61.5 ± 7.7 | 76.8% | 20% | 3950 | 21% | 6.9 | 11 |
| sunlight_only | 559 | 244.3 ± 19.1 | 71.5 ± 6.7 | 74.2% | 20% | 843 | 17% | 8.9 | 5 |
| threshold_55 | 599 | 203.7 ± 16.0 | 28.6 ± 5.4 | 86.5% | 20% | 463 | 18% | 8.4 | 6 |
| predictive_m0.5 | 643 | 160.2 ± 16.6 | 0.0 | 95.1% | 33% | 0 | 20% | 7.1 | 10 |

### protect_battery (floor 60 %)

_in 8.55 Wh/orbit, eclipse 36.1 min, floor 60%_


| policy | jobs done | missed | priority-1 missed | value done | min SoC | load-shed min | mean DoD | battery life (yr, notional) | wasted solar (Wh) |
|---|---|---|---|---|---|---|---|---|---|
| greedy | 777 | 33.6 ± 11.5 | 30.8 ± 9.9 | 93.8% | 51% | 1290 | 24% | 5.4 | 77 |
| sunlight_only | 706 | 104.0 ± 6.5 | 101.3 ± 5.5 | 79.8% | 55% | 32 | 16% | 10.0 | 93 |
| threshold_55 | 777 | 33.6 ± 11.5 | 30.8 ± 9.9 | 93.8% | 51% | 588 | 24% | 5.4 | 77 |
| predictive_m0.5 | 807 | 3.5 ± 3.3 | 0.0 | 99.9% | 62% | 0 | 23% | 5.9 | 78 |

### fixed_panel (9 W body-mounted)

_in 4.49 Wh/orbit, eclipse 36.1 min, floor 30%_


| policy | jobs done | missed | priority-1 missed | value done | min SoC | load-shed min | mean DoD | battery life (yr, notional) | wasted solar (Wh) |
|---|---|---|---|---|---|---|---|---|---|
| greedy | 90 | 715.6 ± 29.3 | 324.6 ± 14.6 | 16.7% | 12% | 9350 | 19% | 7.9 | 6 |
| sunlight_only | 90 | 716.2 ± 29.4 | 325.6 ± 14.3 | 16.5% | 12% | 6536 | 19% | 8.0 | 6 |
| threshold_55 | 91 | 715.0 ± 29.5 | 324.0 ± 15.0 | 16.8% | 12% | 1880 | 19% | 7.9 | 6 |
| predictive_m0.5 | 307 | 499.9 ± 25.2 | 107.3 ± 12.5 | 59.8% | 30% | 0 | 20% | 7.4 | 5 |

### beta_sweep

| beta | eclipse (min) | tracking in (Wh) | fixed in (Wh) | greedy value, tracking / fixed | sunlight_only value, tracking / fixed | threshold_55 value, tracking / fixed | predictive_m0.5 value, tracking / fixed |
|---|---|---|---|---|---|---|---|
| 0 | 36.1 | 8.55 | 8.54 | 97.1% / 57.3% | 80.0% / 59.4% | 99.5% / 64.6% | 99.9% / 99.0% |
| 15 | 35.7 | 8.55 | 8.25 | 97.6% / 55.4% | 80.3% / 56.2% | 99.6% / 59.5% | 99.9% / 98.8% |
| 30 | 34.5 | 8.85 | 7.40 | 98.8% / 48.3% | 81.4% / 48.2% | 99.9% / 49.4% | 100.0% / 97.9% |
| 45 | 31.6 | 9.15 | 6.04 | 99.8% / 34.1% | 84.1% / 34.0% | 100.0% / 34.4% | 100.0% / 94.4% |
| 60 | 24.4 | 10.35 | 4.27 | 100.0% / 11.4% | 90.5% / 11.3% | 100.0% / 11.4% | 100.0% / 27.6% |
| 70 | 4.3 | 13.35 | 2.92 | 100.0% / 1.4% | 100.0% / 1.4% | 100.0% / 1.4% | 100.0% / 1.3% |
| 75 | 0.0 | 13.95 | 2.21 | 100.0% / 1.2% | 100.0% / 1.2% | 100.0% / 1.2% | 100.0% / 0.9% |

Plot: `results/beta_sweep.png`

### threshold_sweep (7.5 W array)

Threshold policy at different eclipse thresholds:


| policy | jobs done | missed | priority-1 missed | value done | min SoC | load-shed min | mean DoD | battery life (yr, notional) | wasted solar (Wh) |
|---|---|---|---|---|---|---|---|---|---|
| threshold_35 | 642 | 165.1 ± 24.4 | 117.9 ± 18.1 | 75.1% | 17% | 737 | 18% | 8.6 | 2 |
| threshold_45 | 648 | 159.8 ± 25.0 | 113.4 ± 19.1 | 76.0% | 17% | 663 | 17% | 8.9 | 2 |
| threshold_55 | 649 | 158.1 ± 25.4 | 111.4 ± 19.3 | 76.4% | 17% | 660 | 17% | 9.2 | 2 |
| threshold_65 | 649 | 157.8 ± 24.8 | 111.5 ± 18.9 | 76.4% | 17% | 655 | 17% | 9.4 | 2 |
| threshold_75 | 651 | 156.0 ± 25.1 | 110.0 ± 19.1 | 76.7% | 17% | 652 | 17% | 9.6 | 2 |
| threshold_85 | 651 | 156.1 ± 25.0 | 110.0 ± 19.2 | 76.7% | 17% | 648 | 16% | 9.8 | 2 |

Predictive policy at different safety margins (Wh):


| policy | jobs done | missed | priority-1 missed | value done | min SoC | load-shed min | mean DoD | battery life (yr, notional) | wasted solar (Wh) |
|---|---|---|---|---|---|---|---|---|---|
| predictive_m0 | 748 | 61.4 ± 10.9 | 19.6 ± 5.2 | 95.0% | 30% | 0 | 20% | 7.1 | 2 |
| predictive_m0.25 | 764 | 44.5 ± 9.0 | 1.5 ± 1.2 | 98.6% | 30% | 0 | 20% | 7.1 | 2 |
| predictive_m0.5 | 766 | 43.4 ± 8.9 | 0.0 | 98.9% | 31% | 0 | 20% | 7.0 | 2 |
| predictive_m1 | 766 | 43.5 ± 8.8 | 0.0 | 98.9% | 35% | 0 | 20% | 7.1 | 3 |
| predictive_m2 | 765 | 44.0 ± 8.6 | 0.0 | 98.9% | 43% | 0 | 20% | 7.2 | 3 |

Plot: `results/threshold_sweep.png`
