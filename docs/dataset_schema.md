# Dataset Schema

Manual remote-control cycles are appended to `dataset/drives/manual_drive_log.csv`.

| Column | Description |
| --- | --- |
| `timestamp` | Unix timestamp in seconds |
| `ir_left`, `ir_center`, `ir_right` | Normalized binary obstacle signals where `1` means obstacle and `0` means clear |
| `ultrasonic_distance` | Distance in centimeters |
| `servo_angle` | Camera servo angle using physical calibration: `0` front, `90` left side, `180` right side |
| `gps_lat`, `gps_lon` | GPS coordinates when available |
| `heading` | IMU-derived heading |
| `acceleration`, `accel_x`, `accel_y`, `accel_z`, `gyro_z` | MPU6050 features |
| `image_path` | Captured frame path |
| `manual_steering` | Continuous steering label from `-1.0` full left to `+1.0` full right |
| `manual_speed_cm_s` | Selected dashboard speed mode |
| `manual_direction` | Manual drive direction: `forward` or `reverse` |
| `manual_stop` | Manual stop state |
| `derived_action` | Direction-aware label such as `straight`, `full_left`, `reverse_straight`, `reverse_full_right`, or `stop` |
| `left_gap_score`, `center_gap_score`, `right_gap_score` | Camera-derived free-space estimates |
| `best_gap_angle`, `best_gap_score` | Best passability estimate from the latest scan/current view |
| `gap_metrics_json` | Per-angle free-space, obstacle, narrow-pass, corridor-width, and passability metrics |

The older synthetic/expert classifier schema still exists for pipeline smoke tests, but real training should use the manual dataset.
