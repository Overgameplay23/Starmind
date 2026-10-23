# Optimal baseline

10 instances x 4 orbits (370 min), 0.1 jobs/min, 7 W array, starting at 45% charge. The optimum is a clairvoyant, fully preemptive upper bound (see the docstring).

| policy | mean % of optimal value | worst instance |
|---|---|---|
| greedy | 74.6% | 56.9% |
| sunlight_only | 67.6% | 47.8% |
| threshold_55 | 77.4% | 65.2% |
| predictive_m0.5 | 98.5% | 92.3% |
