from __future__ import annotations


AUTONOMOUS_DASHBOARD_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ARCANE Autonomous Drive</title>
  <style>
    :root { color-scheme: dark; font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    body { margin: 0; background: #0b0b0b; color: #f4f4f4; }
    main { display: grid; grid-template-columns: minmax(320px, 1.6fr) minmax(300px, 0.7fr); gap: 18px; padding: 18px; min-height: 100vh; box-sizing: border-box; }
    .camera { background: #000; border: 1px solid #333; border-radius: 10px; min-height: 360px; display: grid; place-items: center; overflow: hidden; }
    .camera img { width: 100%; height: 100%; object-fit: contain; }
    .panel { border: 1px solid #333; border-radius: 10px; padding: 18px; background: #151515; display: flex; flex-direction: column; gap: 14px; }
    h1 { margin: 0 0 6px; font-size: 20px; }
    .mode { font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; padding: 6px 10px; border-radius: 6px; display: inline-block; }
    .mode.manual { background: #2f6fed; color: #fff; }
    .mode.auto { background: #1f6b3a; color: #fff; }
    .decision { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 14px; background: #0f0f0f; border: 1px solid #2a2a2a; border-radius: 8px; padding: 14px; }
    .decision .row { display: flex; justify-content: space-between; padding: 5px 0; border-bottom: 1px solid #222; }
    .decision .row:last-child { border-bottom: none; }
    .decision .label { color: #aaa; }
    .decision .value { color: #fff; font-weight: 600; }
    .reason { font-size: 13px; color: #ccc; line-height: 1.5; }
    .sensors { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
    .sensor { background: #0f0f0f; border: 1px solid #2a2a2a; border-radius: 8px; padding: 10px; text-align: center; }
    .sensor .label { font-size: 11px; color: #888; text-transform: uppercase; }
    .sensor .value { font-size: 16px; font-weight: 700; margin-top: 4px; }
    .sensor.active { border-color: #e55353; background: #2a1515; }
    button { border: 1px solid #444; background: #242424; color: #fff; border-radius: 8px; padding: 16px; font-size: 16px; cursor: pointer; font-weight: 600; }
    button:hover { background: #2f2f2f; }
    button.stop { background: #9b1c1c; border-color: #e55353; }
    button.stop:hover { background: #b51d1d; }
    button.auto { background: #1f6b3a; border-color: #36a760; }
    button.auto:hover { background: #257a43; }
    button:disabled { opacity: 0.5; cursor: not-allowed; }
    .actions { display: flex; flex-direction: column; gap: 10px; margin-top: auto; }
    .status { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; color: #888; }
    .report-link { color: #6fa0ff; text-decoration: none; }
    .report-link:hover { text-decoration: underline; }
    @media (max-width: 820px) { main { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <main>
    <section class="camera"><img id="preview" alt="Live vehicle camera"></section>
    <section class="panel">
      <div>
        <h1>ARCANE Autonomous</h1>
        <span id="modeBadge" class="mode manual">Manual</span>
        <span id="modelBadge" class="mode" style="margin-left: 8px; background: #444;">Model: checking...</span>
      </div>

      <div id="errorBox" class="reason" style="color: #ff9999; display: none;"></div>

      <div class="decision">
        <div class="row"><span class="label">Action</span><span id="actionValue" class="value">-</span></div>
        <div class="row"><span class="label">Speed</span><span id="speedValue" class="value">-</span></div>
        <div class="row"><span class="label">Steering</span><span id="steeringValue" class="value">-</span></div>
        <div class="row"><span class="label">Direction</span><span id="directionValue" class="value">-</span></div>
        <div class="row"><span class="label">Reason</span><span id="reasonValue" class="value">-</span></div>
      </div>

      <div id="explanation" class="reason">Waiting for telemetry...</div>

      <div class="sensors">
        <div class="sensor" id="irLeft"><div class="label">IR Left</div><div class="value">-</div></div>
        <div class="sensor" id="irCenter"><div class="label">IR Center</div><div class="value">-</div></div>
        <div class="sensor" id="irRight"><div class="label">IR Right</div><div class="value">-</div></div>
        <div class="sensor" id="ultrasonic"><div class="label">Ultrasonic</div><div class="value">-</div></div>
      </div>

      <div class="actions">
        <button id="toggleAuto" class="auto">Start Autonomous</button>
        <button id="emergencyStop" class="stop">Emergency Stop / Manual Takeover</button>
      </div>

      <div id="reportArea" class="status"></div>
    </section>
  </main>
  <script>
    let mode = 'manual';
    let modelLoaded = false;
    let latestImageAt = 0;

    async function postMode(nextMode) {
      const res = await fetch('/api/v1/mode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: nextMode })
      });
      const result = await res.json();
      if (result.error) {
        showError(result.error);
        mode = 'manual';
      } else {
        mode = result.mode;
        showError(null);
      }
      renderMode();
    }

    function renderMode() {
      const badge = document.getElementById('modeBadge');
      const btn = document.getElementById('toggleAuto');
      badge.className = 'mode ' + mode;
      badge.textContent = mode === 'auto' ? 'Autonomous' : 'Manual';
      btn.textContent = mode === 'auto' ? 'Stop Autonomous' : 'Start Autonomous';
      btn.disabled = !modelLoaded && mode !== 'auto';
    }

    function renderModelStatus(loaded, error) {
      modelLoaded = loaded;
      const badge = document.getElementById('modelBadge');
      if (loaded) {
        badge.textContent = 'Model loaded';
        badge.style.background = '#1f6b3a';
      } else {
        badge.textContent = error ? 'Model error' : 'No model';
        badge.style.background = '#9b1c1c';
      }
      const btn = document.getElementById('toggleAuto');
      btn.disabled = !loaded && mode !== 'auto';
    }

    function showError(text) {
      const box = document.getElementById('errorBox');
      if (text) {
        box.textContent = text;
        box.style.display = 'block';
      } else {
        box.style.display = 'none';
      }
    }

    function renderSensors(frame) {
      const setSensor = (id, active, text) => {
        const el = document.getElementById(id);
        el.classList.toggle('active', Boolean(active));
        el.querySelector('.value').textContent = text;
      };
      setSensor('irLeft', frame.ir_left, frame.ir_left ? 'OBSTACLE' : 'clear');
      setSensor('irCenter', frame.ir_center, frame.ir_center ? 'OBSTACLE' : 'clear');
      setSensor('irRight', frame.ir_right, frame.ir_right ? 'OBSTACLE' : 'clear');
      setSensor('ultrasonic', false, (frame.ultrasonic_distance ?? 0).toFixed(1) + ' cm');
    }

    function renderDecision(decision, command) {
      if (!decision) return;
      document.getElementById('actionValue').textContent = decision.action;
      document.getElementById('speedValue').textContent = (command?.speed_cm_s ?? 0).toFixed(1) + ' cm/s';
      document.getElementById('steeringValue').textContent = (command?.steering ?? 0).toFixed(2);
      document.getElementById('directionValue').textContent = command?.direction ?? '-';
      document.getElementById('reasonValue').textContent = decision.reason_code;
      document.getElementById('explanation').textContent = decision.explanation || 'No explanation available.';
    }

    function renderReport(path) {
      const area = document.getElementById('reportArea');
      if (!path) {
        area.textContent = '';
        return;
      }
      area.innerHTML = 'Accident report: <a class="report-link" href="/api/v1/accident-report?path=' + encodeURIComponent(path) + '" target="_blank">' + path + '</a>';
    }

    async function poll() {
      try {
        const res = await fetch('/api/v1/state');
        const data = await res.json();
        mode = data.mode || 'manual';
        renderModelStatus(data.model_loaded, data.model_load_error);
        renderMode();
        renderSensors(data.latest_frame || {});
        renderDecision(data.latest_command_decision, data.command);
        renderReport(data.latest_accident_report_path);

        const img = document.getElementById('preview');
        if (data.latest_image_url && data.latest_image_updated_at !== latestImageAt) {
          latestImageAt = data.latest_image_updated_at;
          img.src = data.latest_image_url + '&t=' + latestImageAt;
        }
      } catch (err) {
        document.getElementById('explanation').textContent = 'Host unreachable. Retrying...';
      }
    }

    document.getElementById('toggleAuto').onclick = () => postMode(mode === 'auto' ? 'manual' : 'auto');
    document.getElementById('emergencyStop').onclick = () => postMode('manual');

    renderMode();
    setInterval(poll, 180);
    poll();
  </script>
</body>
</html>
"""
