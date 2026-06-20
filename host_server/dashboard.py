from __future__ import annotations


DASHBOARD_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ARCANE Remote Drive</title>
  <style>
    :root { color-scheme: dark; font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    body { margin: 0; background: #111; color: #f4f4f4; }
    main { display: grid; grid-template-columns: minmax(320px, 1.4fr) minmax(300px, 0.8fr); gap: 18px; padding: 18px; min-height: 100vh; box-sizing: border-box; }
    .video { background: #000; border: 1px solid #333; border-radius: 8px; min-height: 320px; display: grid; place-items: center; overflow: hidden; }
    .video img { width: 100%; height: 100%; object-fit: contain; }
    .panel { border: 1px solid #333; border-radius: 8px; padding: 16px; background: #181818; }
    .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
    .steering-grid { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px; }
    button { border: 1px solid #444; background: #242424; color: #fff; border-radius: 6px; padding: 12px; font-size: 15px; cursor: pointer; }
    button.active { background: #2f6fed; border-color: #6fa0ff; }
    button.stop { background: #9b1c1c; border-color: #e55353; font-weight: 700; }
    button.go { background: #1f6b3a; border-color: #36a760; }
    label { display: block; margin: 18px 0 8px; color: #ccc; }
    .status { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; line-height: 1.5; white-space: pre-wrap; color: #d8d8d8; }
    @media (max-width: 820px) { main { grid-template-columns: 1fr; } .steering-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
  </style>
</head>
<body>
  <main>
    <section class="video"><img id="preview" alt="Live vehicle camera"></section>
    <section class="panel">
      <div class="status">Camera servo: sensor controlled. Left/right IR points the camera to that side; ultrasonic below 50 cm triggers a gap scan.</div>

      <label>Steering <span id="steeringValue">straight</span></label>
      <div class="steering-grid" id="steeringButtons">
        <button data-steering="-1">Full Left</button>
        <button data-steering="-0.45">Slight Left</button>
        <button data-steering="0">Straight</button>
        <button data-steering="0.45">Slight Right</button>
        <button data-steering="1">Full Right</button>
      </div>

      <label>Speed mode</label>
      <div class="grid" id="speeds"></div>

      <label>Direction</label>
      <div class="grid">
        <button id="forward">Forward</button>
        <button id="reverse">Reverse</button>
      </div>

      <div class="grid" style="margin-top:14px;">
        <button id="go" class="go">Drive</button>
        <button id="stop" class="stop">STOP</button>
      </div>

      <label>Telemetry</label>
      <div class="status" id="status">Waiting for vehicle...</div>
    </section>
  </main>
  <script>
    const speeds = [2, 3, 4, 5];
    let state = { speed_cm_s: 5, steering: 0, direction: 'forward', servo_angle: 0, stop: true, sweep_requested: false };
    let latestImageAt = 0;
    const steeringLabels = new Map([
      [-1, 'full left'],
      [-0.45, 'slight left'],
      [0, 'straight'],
      [0.45, 'slight right'],
      [1, 'full right']
    ]);

    function postState(patch) {
      state = { ...state, ...patch };
      return fetch('/api/v1/manual-command', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(state)
      }).then(r => r.json()).then(data => { state = data.command; render(); });
    }

    function render() {
      document.querySelectorAll('[data-speed]').forEach(b => b.classList.toggle('active', Number(b.dataset.speed) === state.speed_cm_s));
      const currentSteering = Number(state.steering);
      document.querySelectorAll('[data-steering]').forEach(b => b.classList.toggle('active', Number(b.dataset.steering) === currentSteering));
      document.getElementById('steeringValue').textContent = steeringLabels.get(currentSteering) || currentSteering.toFixed(2);
      document.getElementById('go').classList.toggle('active', !state.stop);
      document.getElementById('stop').classList.toggle('active', state.stop);
      document.getElementById('forward').classList.toggle('active', state.direction === 'forward');
      document.getElementById('reverse').classList.toggle('active', state.direction === 'reverse');
    }

    const speedBox = document.getElementById('speeds');
    speeds.forEach(speed => {
      const button = document.createElement('button');
      button.textContent = speed + ' cm/s';
      button.dataset.speed = speed;
      button.onclick = () => postState({ speed_cm_s: speed });
      speedBox.appendChild(button);
    });
    document.querySelectorAll('[data-steering]').forEach(button => {
      button.onclick = () => postState({ steering: Number(button.dataset.steering), stop: false });
    });
    document.getElementById('go').onclick = () => postState({ stop: false });
    document.getElementById('stop').onclick = () => postState({ stop: true, steering: 0 });
    document.getElementById('forward').onclick = () => postState({ direction: 'forward' });
    document.getElementById('reverse').onclick = () => postState({ direction: 'reverse' });

    function poll() {
      fetch('/api/v1/state').then(r => r.json()).then(data => {
        state = data.command;
        document.getElementById('status').textContent = JSON.stringify(data, null, 2);
        const img = document.getElementById('preview');
        if (data.latest_image_url && data.latest_image_updated_at !== latestImageAt) {
          latestImageAt = data.latest_image_updated_at;
          img.src = data.latest_image_url + '&t=' + latestImageAt;
        }
        render();
      }).catch(() => {});
    }
    postState({});
    setInterval(poll, 180);
    poll();
  </script>
</body>
</html>
"""
