# Milestone 6 matched frame costs

1080p, view distance 96, balanced preset; ON/OFF/OFF/ON order, two repeats per condition.

| Effect | Scene | Enabled FPS | Control FPS | Enabled minus control ms |
| --- | --- | ---: | ---: | ---: |
| falloff | glowing_cave | 39.0 | 38.7 | -0.222 |
| foliage | forest | 47.6 | 50.1 | +1.037 |
| grain | surface_materials | 70.4 | 88.2 | +2.856 |
| camera | forest | 43.7 | 44.7 | +0.509 |
| camera | sunset_river | 37.9 | 41.9 | +2.496 |
| camera | glowing_cave | 35.3 | 38.4 | +2.263 |
| camera | underwater | 41.2 | 47.7 | +3.338 |

Camera compares the complete TAA/exposure/bloom/tone/vignette path with its disabled control.
It does not isolate the cost of individual stability fixes. Small or negative deltas can reflect run variation.
The final 60 FPS preset budget remains milestone 7. Raw frame logs, settings and GPU state accompany every run.
