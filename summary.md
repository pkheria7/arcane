# ARCANE XAV Project Summary

## 1. Project Title

**ARCANE XAV: A Raspberry Pi Based Explainable Autonomous Vehicle With Rule-Based Safety, Evidence Recording, GPS Tracking, and Compliance Reporting**

ARCANE XAV is a small autonomous vehicle project built around a Raspberry Pi controlled four-motor car. The system combines real-time sensor-based navigation, camera-assisted scene understanding, GPS tracking, accident/evidence recording, and a planned Mac-side vision/LLM reporting workflow. The central idea is not only to make a small robotic vehicle move autonomously, but also to make its actions explainable, auditable, and usable for compliance-style accident reports.

The current implementation is split into two historical phases:

1. An earlier host-and-edge architecture where the Raspberry Pi acted as a thin hardware client and the Mac host handled dashboard control, data logging, camera scoring, and machine learning experiments.
2. A newer Pi-only rule-based autonomy implementation inside the `finally/` folder, where the Raspberry Pi performs all driving decisions locally and serves a live web UI to any phone or laptop on the same network.

The project has evolved away from depending on a trained driving model because the current model quality is not sufficient for reliable real-world driving. The current priority is robust, deterministic, rule-based autonomy that can avoid obstacles, record evidence when sensors detect risk, and provide transparent logs of every action.

## 2. Core Idea

The main idea of ARCANE XAV is to build a miniature autonomous vehicle that can:

- Sense obstacles using IR sensors and ultrasonic distance sensing.
- Use a camera mounted on a servo to inspect the direction of possible obstacles.
- Drive itself using rule-based decisions without requiring a laptop for control.
- Use all four motors for forward, reverse, and pivot turns.
- Avoid getting stuck permanently in an emergency stop state.
- Record video evidence when an obstacle or possible accident condition is detected.
- Log the vehicle's sensor state, motor commands, decisions, and reasoning.
- Show live telemetry, camera feed, GPS position, and evidence records through a browser UI.
- Allow a Mac to later run heavier vision/LLM/PDF generation on recorded evidence packages.

The innovation is the combination of autonomy and accountability. Many small robotics projects focus only on movement. ARCANE XAV treats autonomous movement as only one part of the system. The other part is explainability: if something happens, the vehicle should be able to show what it saw, what sensor triggered the event, what decision it made, how the motors were commanded, where it was, and what evidence was recorded.

## 3. Motivation and Problem Statement

Autonomous systems, even small experimental ones, need more than movement. They need:

- **Safety:** The vehicle should stop, reverse, pivot, or avoid obstacles before collision.
- **Reliability:** Decisions should happen locally and continuously, without depending on network requests.
- **Explainability:** The system should explain why it turned, stopped, reversed, or continued.
- **Evidence:** If a risk event occurs, camera footage and sensor logs should be saved.
- **Compliance:** Evidence should be converted into a structured report that a user can download.
- **Low-resource operation:** The Raspberry Pi 5 with 2 GB RAM should not run heavy ML inference continuously if it causes bottlenecks.

The original trained behavior-cloning model was not reliable enough. Therefore, the immediate goal shifted from ML-based driving to rule-based driving. This is a practical engineering decision: deterministic rules are easier to debug, safer under limited compute, and more predictable during hardware testing.

However, machine learning is still part of the broader project vision. Instead of using ML as the primary driving controller, ML is better used in two places:

1. Offline training and evaluation from collected driving logs.
2. Mac-side vision and language model analysis for accident/compliance reports.

This preserves safety on the Pi while still allowing advanced AI to improve reporting and scene interpretation.

## 4. System Overview

ARCANE XAV has three major layers:

1. **Physical vehicle layer**
   - Raspberry Pi 5, 2 GB RAM.
   - Four DC motors controlled through L298N motor drivers.
   - Camera mounted on a servo.
   - IR obstacle sensors.
   - HC-SR04 ultrasonic sensor.
   - MPU6050 IMU.
   - GPS module over serial UART.

2. **Autonomy and evidence layer**
   - Runs locally on the Pi.
   - Reads sensors continuously.
   - Captures camera frames at a low rate.
   - Uses rule-based state machine navigation.
   - Commands all four motors explicitly.
   - Records scene video and logs when IR sensors are active.
   - Stores evidence packages locally.

3. **User interface and reporting layer**
   - Pi serves a lightweight browser UI.
   - Phone or laptop opens `http://<pi-ip>:8080`.
   - UI shows camera, sensor values, motor PWM, state, reason, GPS map, and evidence records.
   - Evidence records can be downloaded as `.zip`.
   - Mac later runs heavier vision model/LLM/PDF report generation.

## 5. Current Clean Implementation: `finally/`

The `finally/` folder contains the new clean Pi-only implementation. It is intentionally separate from the older host/model architecture so that the vehicle can be tested and improved without breaking previous experiments.

Important files:

- `finally/main.py`
  - Starts the autonomy loop.
  - Starts the web UI server.
  - Reads sensors, updates decisions, commands motors, captures camera frames, and records evidence.

- `finally/config.py`
  - Stores GPIO pins, camera settings, PWM values, loop rates, timing constants, and navigation thresholds.

- `finally/hardware.py`
  - Reads IR sensors, ultrasonic sensor, IMU, GPS, camera, and servo.
  - Contains both Pi hardware and simulated hardware implementations.

- `finally/motors.py`
  - Implements explicit four-wheel motor control.
  - Supports forward, reverse, differential turns, and pivot turns.
  - Includes wheel calibration such as trim, inversion, and minimum PWM.

- `finally/controller.py`
  - Implements the rule-based autonomy state machine.
  - Handles drive, obstacle avoidance, scan, reverse, pivot, recover, and hard stop behavior.

- `finally/vision.py`
  - Performs lightweight camera gap scoring.
  - Uses simple OpenCV image processing rather than heavy ML inference.

- `finally/recording.py`
  - Starts evidence recording when IR sensors are active.
  - Locks camera direction to the active IR sensor.
  - Writes `scene.mp4`, `actions.jsonl`, and `manifest.json`.

- `finally/ui_server.py`
  - Serves the browser UI.
  - Shows live camera, telemetry, GPS map, motor commands, and evidence download links.

- `finally/motor_test.py`
  - Hardware test script for all motors and movement modes.

- `finally/gps_test.py`
  - GPS diagnostic script that prints raw NMEA data and decodes GGA fix information.

## 6. Hardware Components

### 6.1 Raspberry Pi 5

The Raspberry Pi 5 with 2 GB RAM is the main onboard computer. It performs:

- GPIO input reading.
- PWM motor control.
- Servo control.
- Camera capture.
- Sensor fusion at a basic level.
- Rule-based decision-making.
- Evidence recording.
- Web UI hosting.

The design avoids heavy ML inference on the Pi because the Pi 5 2 GB has limited RAM and should prioritize real-time safety over complex compute. The camera processing is intentionally lightweight and low-rate.

### 6.2 Four DC Motors

The car uses four motors, likely connected through two L298N drivers. The system treats the vehicle as left and right sides:

- Front-left motor.
- Front-right motor.
- Rear-left motor.
- Rear-right motor.

The code supports:

- All wheels forward.
- All wheels reverse.
- Left-side reverse and right-side forward for left pivot.
- Right-side reverse and left-side forward for right pivot.
- Differential steering by reducing inner-side wheel power.

This is important because turning a loaded four-motor vehicle requires more torque than a simple two-motor car. The current PWM defaults have been increased to `0.90` for cruise, avoid, reverse, pivot, and recover actions.

### 6.3 IR Sensors

There are three IR sensors:

- Left IR.
- Center IR.
- Right IR.

They detect nearby obstacles. In the current design, IR sensors have camera priority. If an IR sensor activates, the camera turns toward that direction and stays there until the same IR sensor becomes inactive.

IR-to-camera mapping:

- Left IR active: servo turns to `180`.
- Center IR active: servo turns to `90`.
- Right IR active: servo turns to `0`.

This behavior supports evidence recording because the camera focuses on the risk direction for the full duration of the sensor event.

### 6.4 Ultrasonic Sensor

The HC-SR04 ultrasonic sensor measures front distance. It is used for:

- Detecting close front obstacles.
- Triggering blocked or emergency behavior.
- Helping avoid collision when IR detection is not enough.

The controller filters ultrasonic readings using consecutive sample counts. This prevents a single noisy distance reading from causing a false emergency.

### 6.5 Servo-Mounted Camera

The camera is mounted on a servo. It can look:

- Left: `180`.
- Front: `90`.
- Right: `0`.

The camera has two roles:

1. **Navigation assist**
   - During scan states, it checks left, front, and right directions.
   - The system calculates simple gap scores from camera frames.

2. **Evidence recording**
   - When an IR sensor is active, the camera locks to that direction and records the scene.

Camera processing is low-rate to avoid bottlenecks. The default camera resolution is small, such as `160x120`, and JPEG quality is reduced.

### 6.6 GPS Module

The GPS module is read over serial UART, usually `/dev/serial0` at `9600` baud. The UI displays:

- Latitude.
- Longitude.
- GPS fix quality.
- Last fix age.
- OpenStreetMap marker.
- Recent trail.

If there is no GPS fix, the UI shows `waiting for fix`. A diagnostic script, `finally/gps_test.py`, prints raw NMEA sentences and decodes GGA fix quality.

### 6.7 MPU6050 IMU

The MPU6050 provides acceleration and gyroscope data. In the broader project, this can help detect collisions or sudden impacts. The current evidence system records IMU values in the action log, so they can later be used in reports.

## 7. Methodology

The project methodology follows an iterative robotics engineering process:

1. Build the hardware interface.
2. Test sensors individually.
3. Test motors individually.
4. Build a simple control loop.
5. Add rule-based decision-making.
6. Add camera scanning and evidence recording.
7. Add live UI and telemetry.
8. Add GPS map display.
9. Collect logs and evidence.
10. Use Mac-side ML/LLM tools to generate reports.

This methodology is suitable because autonomous robots have many failure points: wiring, power, sensor noise, motor torque, camera latency, compute limitations, and network behavior. By testing each subsystem separately, the system becomes easier to debug.

## 8. Rule-Based Autonomy

The current autonomy is controlled by a state machine. A rule-based state machine is used instead of ML because:

- It is predictable.
- It is easier to debug.
- It is safer for early hardware trials.
- It requires very little compute.
- It can explain every action with a clear reason.

### 8.1 Main States

#### Drive

The vehicle moves forward when the path appears clear. It uses the configured cruise PWM.

#### Avoid Side

If the left IR sensor detects an obstacle, the vehicle steers right. If the right IR sensor detects an obstacle, the vehicle steers left. This prevents side collisions.

#### Blocked Stop

If the center IR or ultrasonic sensor indicates that the front is blocked, the vehicle stops briefly. This pause allows the system to avoid reacting too aggressively to transient noise.

#### Scan

The camera looks left, front, and right. The system calculates gap scores from images and chooses the safer direction.

#### Reverse

If the front remains blocked, the vehicle reverses for a short time. This is important because the previous behavior could get stuck in hard stop forever.

#### Pivot

The vehicle pivots toward the safer side. Four-motor pivot control gives stronger turning than weak differential steering.

#### Recover

After pivoting, the vehicle moves forward slowly and checks whether the path is clear.

#### Hard Stop

Hard stop is used for immediate danger or UI emergency stop. It is not intended to be a permanent trap. The system can proceed to scan/reverse/pivot behavior after a timed pause when appropriate.

### 8.2 Why the Stuck Hard-Stop Problem Happened

The older behavior stopped when an obstacle was detected and waited for the obstacle to clear. In physical reality, if the car is already close to an obstacle, simply waiting may never clear the sensor. The car must perform an active escape behavior.

The new behavior fixes this by using:

1. Stop.
2. Scan.
3. Reverse.
4. Pivot.
5. Recover.
6. Re-check.

This transforms hard stop from a dead-end state into a safety pause followed by escape.

## 9. Camera and Vision Methodology

The Pi does not run a heavy vision model during driving. Instead, it uses lightweight OpenCV methods:

- Convert frame to grayscale.
- Focus on the lower half of the image.
- Use edge density as an obstacle/corridor feature.
- Use brightness as a simple free-space cue.
- Split the image into left, center, and right regions.
- Produce gap scores from `0.0` to `1.0`.

This approach is not as intelligent as a trained segmentation model, but it is fast and useful for simple navigation support. It also avoids overloading the Pi.

The project deliberately separates real-time driving vision from offline report vision:

- Pi: simple, fast, safe, low-compute vision.
- Mac: heavier vision model and LLM report generation.

This division is practical and scalable.

## 10. Evidence Recording System

The evidence recording system is one of the most important parts of the project.

### 10.1 Trigger

Recording starts when an IR sensor becomes active:

- Left IR active starts a left-side event.
- Center IR active starts a front event.
- Right IR active starts a right-side event.

### 10.2 Camera Priority

When an IR sensor is active, camera priority belongs to that IR sensor. This means:

- The servo turns toward the active IR direction.
- The camera stays there while that IR remains active.
- Normal scanning does not override the IR camera direction.
- Recording stops only when the triggering IR sensor clears.

This ensures the evidence video actually captures the scene that caused the sensor event.

### 10.3 Evidence Package Contents

Each recording event becomes a folder under:

```text
finally_records/
```

Each folder contains:

- `scene.mp4`
  - Video of the event while the IR sensor was active.

- `actions.jsonl`
  - Line-by-line JSON log of every control loop.
  - Includes timestamp, sensor values, controller state, reason, decision, and motor command.

- `manifest.json`
  - Summary of the event.
  - Includes start/end time, duration, active IR sensor, frame count, and file paths.

The UI lists recent evidence records and provides a download link as a `.zip` file.

## 11. Compliance Report Vision

The final compliance reporting workflow is intended to happen on the Mac, not on the Pi.

### 11.1 Why Mac-Side Reporting

The Mac has more resources for:

- Vision-language models.
- Large language models.
- PDF generation.
- More detailed frame analysis.
- Long-form report writing.

The Pi should not run this heavy workload while driving.

### 11.2 Report Inputs

The Mac-side report generator should use:

- `scene.mp4`
- `actions.jsonl`
- `manifest.json`
- GPS coordinates from logs.
- IMU acceleration/gyro values.
- IR and ultrasonic readings.
- Motor command history.
- Controller states and reasons.

### 11.3 Expected Report Sections

A future downloadable PDF could include:

- Incident summary.
- Vehicle ID and timestamp.
- GPS map location.
- Sensor timeline.
- Camera evidence frames.
- Detected obstacle direction.
- Vehicle motion summary.
- Decision explanation.
- Whether the car stopped, reversed, pivoted, or continued.
- Possible cause of incident.
- Safety response assessment.
- Compliance notes.
- Appendix with raw logs.

### 11.4 Use of LLM

The LLM should not invent facts. It should summarize structured evidence. A good prompt should provide:

- Extracted facts from `actions.jsonl`.
- Key frames or vision model outputs from `scene.mp4`.
- GPS location.
- Sensor timeline.
- Motor command timeline.

The LLM's role should be:

- Generate readable explanation.
- Organize evidence.
- Produce compliance language.
- Explain why the system acted as it did.

The LLM should not be responsible for controlling the vehicle.

## 12. Earlier ML Work

The project includes older machine learning work in the original architecture.

### 12.1 Manual Driving Dataset

The Mac dashboard could collect manual driving data. Each row included:

- IR sensor values.
- Ultrasonic distance.
- Servo angle.
- GPS coordinates.
- IMU data.
- Gap scores.
- Manual steering.
- Manual speed.
- Direction.
- Stop state.
- Derived action label.

This dataset was intended for behavior cloning.

### 12.2 Behavior Cloning

Behavior cloning means training a model to imitate human driving. The model receives sensor features and predicts:

- Steering.
- Speed.
- Direction.

The project used scikit-learn models such as:

- Random Forest Regressor.
- Small Neural Network Regressor.
- Optional LightGBM Regressor.

The best manual model was saved as:

```text
models/manual/best_manual_model.joblib
```

However, the user observed that the model performed poorly in real driving. This is expected in early behavior cloning projects because:

- Dataset size may be small.
- Training data may not cover enough scenarios.
- Sensor noise affects predictions.
- Real-world motor behavior differs from recorded labels.
- A model can imitate bad or inconsistent manual driving.
- The model has no explicit safety guarantees.

Therefore, the project correctly shifted away from using the model for real-time control.

### 12.3 Synthetic Classifier Pipeline

There was also an older classifier pipeline that generated synthetic data and trained action classifiers:

- Left.
- Straight.
- Right.
- Stop.

This is useful for smoke testing ML infrastructure, but synthetic data cannot replace real-world vehicle data.

### 12.4 Recommended Future ML Direction

The best future role for ML is:

1. Improve offline scene understanding.
2. Generate better reports.
3. Analyze near-miss and accident evidence.
4. Suggest tuning changes.
5. Learn from recorded driving logs after the rule-based system is stable.

If ML is later reintroduced for driving, it should be used as advisory only. The rule-based safety layer should remain authoritative.

## 13. Tools and Technologies Used

### 13.1 Python

Python is the main programming language. It is used for:

- Hardware control.
- Sensor reading.
- State machine logic.
- Web server.
- Data logging.
- ML training.
- Report generation prototypes.

### 13.2 Raspberry Pi GPIO

The project uses Raspberry Pi GPIO for:

- Motor control.
- PWM outputs.
- IR sensors.
- Servo control.
- Ultrasonic sensor pins.

The code uses `gpiozero` and Pi GPIO backends such as `lgpio`.

### 13.3 OpenCV

OpenCV is used for:

- Camera frame encoding.
- JPEG processing.
- Gap scoring.
- Video writing for evidence records.

### 13.4 Picamera2

Picamera2 is used to capture camera frames from the Raspberry Pi camera.

### 13.5 Serial GPS

The GPS module uses UART serial communication and NMEA sentences. The code parses GGA sentences to obtain:

- Latitude.
- Longitude.
- Fix quality.

### 13.6 Leaflet and OpenStreetMap

The browser UI uses:

- Leaflet JavaScript map library.
- OpenStreetMap tile service.

The UI shows the vehicle's live GPS marker and recent path.

### 13.7 HTTP Server

The Pi serves the UI using Python's HTTP server tools:

- Browser dashboard.
- JSON telemetry endpoint.
- Camera image endpoint.
- Evidence record download endpoint.

### 13.8 Scikit-Learn

Scikit-learn was used in earlier ML experiments:

- Feature preprocessing.
- Random forest models.
- Neural network regressors/classifiers.
- Train/test split.
- Metrics.

### 13.9 Joblib

Joblib is used to save and load trained scikit-learn pipelines.

### 13.10 Pytest

Pytest is used for regression tests:

- Controller transitions.
- Motor mixing.
- IR polarity.
- Host processor behavior.
- Dataset/report generation.

## 14. Data Flow

### 14.1 Pi-Only Runtime Data Flow

1. Sensors are read.
2. Camera frame is captured at low rate.
3. Vision gap scores are calculated.
4. Controller state machine decides action.
5. Motor command is generated.
6. Servo direction is updated.
7. Evidence recorder checks IR triggers.
8. UI telemetry is updated.
9. Browser polls telemetry.
10. User sees camera, map, state, sensors, motors, and records.

### 14.2 Evidence Data Flow

1. IR sensor becomes active.
2. Recorder starts event folder.
3. Camera servo locks to IR direction.
4. Camera frames are written into video.
5. Every loop writes action/sensor/decision data to JSONL.
6. IR clears.
7. Recorder closes video and writes manifest.
8. UI lists downloadable record.
9. Mac downloads record zip.
10. Mac generates PDF report.

### 14.3 Future Mac-Side Report Data Flow

1. User downloads `.zip` from Pi UI.
2. Mac extracts `scene.mp4`, `actions.jsonl`, and `manifest.json`.
3. Vision model analyzes video frames.
4. Script extracts key events from logs.
5. LLM summarizes evidence.
6. PDF generator creates final report.
7. User downloads/shares report.

## 15. Safety Design

Safety is handled through:

- Local Pi decisions.
- No dependency on network for driving.
- Emergency stop button in UI.
- Ultrasonic filtering.
- Hard stop state.
- Reverse and pivot escape.
- Low-rate camera to avoid compute overload.
- Sensor failure fallback to motor stop.
- Motor tests before floor testing.

The system is designed so that UI failure does not stop autonomy and network failure does not affect driving decisions.

## 16. Performance Design for Raspberry Pi 5 2GB

The Pi has limited RAM and compute compared to a laptop. The project uses:

- Rule-based control instead of neural inference.
- Small camera frames.
- Low JPEG quality.
- Low-rate camera processing.
- No continuous disk image writes unless evidence is active.
- Small in-memory telemetry.
- Simple HTTP polling UI.
- Mac-side heavy reporting.

This keeps the vehicle responsive.

## 17. Why Rule-Based First Is the Correct Choice

The trained model currently performs poorly. In robotics, a poor driving model is dangerous because it can produce unpredictable motion. Rule-based logic is better for the current phase because:

- It is transparent.
- It can be manually inspected.
- It is easier to tune.
- It has explicit emergency handling.
- It does not require large datasets.
- It runs fast on the Pi.

Once the rule-based system consistently records high-quality logs, those logs can be used to train better ML models later.

## 18. Innovation

The project is innovative because it combines:

- Low-cost autonomous vehicle hardware.
- Local rule-based autonomy.
- Four-motor control.
- Servo-directed visual attention.
- Sensor-triggered evidence recording.
- GPS map telemetry.
- Downloadable evidence packages.
- Future vision/LLM compliance reporting.

The most important innovation is the evidence-first design. The vehicle is not just autonomous; it is designed to explain itself after an event.

## 19. Possible 32-Page Report Structure

This `summary.md` can be expanded into a 32-page report using the following structure:

1. Title Page.
2. Abstract.
3. Introduction.
4. Problem Statement.
5. Motivation.
6. Objectives.
7. System Overview.
8. Hardware Architecture.
9. Raspberry Pi Role.
10. Sensor Subsystem.
11. Motor Control Subsystem.
12. Camera and Servo System.
13. GPS and Map System.
14. Software Architecture.
15. Rule-Based Controller.
16. Obstacle Avoidance Methodology.
17. Evidence Recording System.
18. Compliance Report Vision.
19. Machine Learning Experiments.
20. Why ML Driving Was Rejected for Current Version.
21. Vision Processing.
22. UI Design.
23. Data Logging.
24. Safety Mechanisms.
25. Performance Optimization.
26. Testing Methodology.
27. Results and Observations.
28. Limitations.
29. Future Scope.
30. Ethical and Compliance Considerations.
31. Conclusion.
32. References and Appendix.

## 20. Limitations

Current limitations include:

- GPS may take time to get a satellite fix.
- Camera gap scoring is heuristic, not semantic.
- IR sensors may have polarity or range limitations.
- Ultrasonic readings may be noisy.
- Lighting conditions affect camera scoring.
- Servo jitter can occur without an ideal pin factory.
- Evidence report generation is not yet fully implemented.
- ML driving model is not reliable enough for real control.

## 21. Future Scope

Future improvements:

- Add Mac-side PDF report generator.
- Add vision model frame analysis.
- Add object detection for recorded videos.
- Add lane/corridor detection.
- Add better GPS trail export.
- Add offline map snapshot in PDF reports.
- Add calibration UI for motor trims.
- Add automatic sensor diagnostics.
- Add battery voltage monitoring.
- Add collision severity scoring.
- Add cloud or local database for evidence records.
- Improve ML using larger real-world datasets.
- Add hybrid controller where ML suggests but rules enforce safety.

## 22. Conclusion

ARCANE XAV is a practical, explainable autonomous vehicle platform. The current system prioritizes safety and reliability over premature ML control. The Raspberry Pi performs all real-time driving locally using deterministic rules, while the camera, IR sensors, ultrasonic sensor, IMU, and GPS provide environmental awareness. When risk is detected, the system records video and logs every action, creating evidence packages that can later be converted into compliance reports using Mac-side vision and LLM tools.

The project demonstrates a strong engineering philosophy: autonomous systems should not only act, but also record, explain, and justify their actions.

