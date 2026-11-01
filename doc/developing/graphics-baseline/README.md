# Milestone 1 measured baseline

CPU: AMD Ryzen 5 4600H with Radeon Graphics. GPU/driver/clock/temperature observations are in [environment.json](environment.json).
Resolution: 1920×1080; view distance: 96 nodes; FOV: 70°; VSync off; frame cap: 1000 FPS.
Fixed cameras, weather, time of day and lamp state; local server included. Startup and settling frames are excluded.
No screenshots or input-device automation. These static scenes do not establish exploration or all-game performance.

| Scene | Profile | Aggregate FPS | Median ms range | p95 ms range | p99 ms range | Frames |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| forest | basic | 485.5 | 1.95–1.97 | 2.53–2.63 | 3.16–3.16 | 19428 |
| sunset_river | basic | 477.7 | 1.85–2.14 | 2.30–2.93 | 2.71–3.54 | 19120 |
| glowing_cave | basic | 914.2 | 1.00–1.00 | 1.18–1.49 | 1.50–2.18 | 36577 |
| underwater | basic | 505.1 | 1.93–1.94 | 2.21–2.38 | 2.75–2.82 | 20204 |
| forest | quality | 17.8 | 54.51–55.58 | 59.79–61.47 | 60.46–64.62 | 712 |
| sunset_river | quality | 8.3 | 119.22–123.21 | 122.93–128.61 | 123.75–129.82 | 330 |
| glowing_cave | quality | 27.3 | 35.54–35.69 | 40.08–41.36 | 41.50–44.26 | 1090 |
| underwater | quality | 5.7 | 174.68–178.22 | 181.79–183.79 | 183.43–189.53 | 226 |
| forest | balanced | 40.7 | 24.03–24.37 | 27.89–28.30 | 28.70–29.21 | 1627 |
| sunset_river | balanced | 41.2 | 24.25–24.27 | 28.00–28.16 | 29.14–29.45 | 1646 |
| glowing_cave | balanced | 66.6 | 14.59–14.72 | 18.33–18.55 | 19.31–21.02 | 2662 |
| underwater | balanced | 46.7 | 20.77–21.12 | 24.71–25.10 | 26.11–26.72 | 1868 |

FPS combines frame counts and sampled durations across repeats. Percentile ranges show the individual repeats; they are not averaged percentiles.
The proposed balanced budget is 60 FPS (16.67 ms average) with p95 ≤22.2 ms.

- forest: misses the proposed budget.
- sunset_river: misses the proposed budget.
- glowing_cave: meets the proposed budget.
- underwater: misses the proposed budget.

Exact per-run settings, result records and compressed frame CSV/logs are in [raw](raw).
Prepared world: `/tmp/luanti-milestone1/prepared-world`; its source and map hashes are recorded in the environment file.
Use the same stopped prepared world for exact reruns; scene preparation can also be repeated from the recorded source world.
