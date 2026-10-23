Per-orbit budget: period 92.6 min, eclipse 36.1 min | in 8.55 Wh, bus 3.86 Wh, compute demand 3.72 Wh, battery losses 0.32 Wh -> margin +0.65 Wh

**One week, 20 seeds, 0.08 jobs/min, 9 W array**

| policy | jobs done | missed | priority-1 missed | value done | min SoC | load-shed min | mean DoD | battery life (yr, notional) | wasted solar (Wh) |
|---|---|---|---|---|---|---|---|---|---|
| greedy | 796 | 15.7 ± 8.6 | 14.2 ± 7.2 | 97.1% | 21% | 591 | 26% | 4.8 | 72 |
| sunlight_only | 708 | 102.7 ± 6.1 | 100.3 ± 5.3 | 80.0% | 50% | 0 | 16% | 10.0 | 92 |
| threshold_55 | 808 | 3.6 ± 3.2 | 2.1 ± 1.7 | 99.5% | 24% | 32 | 25% | 5.2 | 72 |
| predictive_m0.5 | 809 | 1.8 ± 2.4 | 0.0 | 99.9% | 33% | 0 | 26% | 4.9 | 73 |
