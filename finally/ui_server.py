from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock, Thread
from urllib.parse import urlparse

from .models import Telemetry


class SharedState:
    def __init__(self) -> None:
        self.lock = Lock()
        self.telemetry = Telemetry()

    def update(self, telemetry: Telemetry) -> None:
        with self.lock:
            self.telemetry = telemetry

    def snapshot(self) -> Telemetry:
        with self.lock:
            return self.telemetry

    def set_emergency_stop(self, value: bool) -> None:
        with self.lock:
            self.telemetry.emergency_stop = value


HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ARCANE Pi Autonomy</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <main>
    <section class="camera"><img id="camera" alt="Latest Pi camera frame"></section>
    <section class="panel">
      <h1>ARCANE Pi Autonomy</h1>
      <div class="badges">
        <span id="state" class="badge">starting</span>
        <span id="hz" class="badge muted">0.0 Hz</span>
      </div>
      <p id="reason">Waiting for telemetry...</p>
      <div class="grid" id="sensors"></div>
      <div class="grid" id="motors"></div>
      <div class="actions">
        <button id="stop" class="danger">Emergency Stop</button>
        <button id="resume">Resume</button>
      </div>
      <pre id="raw"></pre>
    </section>
  </main>
  <script src="/static/app.js"></script>
</body>
</html>
"""


CSS = """
:root { color-scheme: dark; font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
body { margin: 0; background: #101010; color: #f2f2f2; }
main { min-height: 100vh; display: grid; grid-template-columns: minmax(300px, 1.3fr) minmax(300px, .8fr); gap: 16px; padding: 16px; box-sizing: border-box; }
.camera { background: #000; border: 1px solid #333; border-radius: 8px; display: grid; place-items: center; overflow: hidden; min-height: 320px; }
.camera img { width: 100%; height: 100%; object-fit: contain; }
.panel { border: 1px solid #333; border-radius: 8px; background: #181818; padding: 16px; }
h1 { margin: 0 0 10px; font-size: 22px; }
.badges { display: flex; gap: 8px; flex-wrap: wrap; }
.badge { background: #1f6b3a; border-radius: 6px; padding: 6px 10px; font-weight: 700; }
.badge.muted { background: #333; }
p { color: #ddd; line-height: 1.45; }
.grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin: 12px 0; }
.tile { background: #0e0e0e; border: 1px solid #2b2b2b; border-radius: 8px; padding: 10px; min-height: 48px; }
.tile b { display: block; color: #9c9c9c; font-size: 11px; text-transform: uppercase; margin-bottom: 4px; }
.tile.active { border-color: #e55353; background: #2a1515; }
.actions { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 14px; }
button { border: 1px solid #444; border-radius: 8px; background: #252525; color: white; padding: 14px; font-size: 16px; font-weight: 700; }
button.danger { background: #9b1c1c; border-color: #e55353; }
pre { white-space: pre-wrap; color: #aaa; font-size: 11px; max-height: 180px; overflow: auto; }
@media (max-width: 820px) { main { grid-template-columns: 1fr; } .camera { min-height: 220px; } }
"""


JS = """
let lastCameraAt = 0;
function tile(label, value, active=false) {
  return `<div class="tile ${active ? 'active' : ''}"><b>${label}</b>${value}</div>`;
}
async function post(path, body) {
  await fetch(path, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body || {}) });
}
async function poll() {
  try {
    const res = await fetch('/api/state');
    const data = await res.json();
    const s = data.sensors || {};
    const c = data.command || {};
    document.getElementById('state').textContent = data.emergency_stop ? 'emergency_stop' : data.state;
    document.getElementById('hz').textContent = (data.loop_hz || 0).toFixed(1) + ' Hz';
    document.getElementById('reason').textContent = data.error || data.reason || '-';
    document.getElementById('sensors').innerHTML = [
      tile('IR Left', s.ir_left ? 'OBSTACLE' : 'clear', s.ir_left),
      tile('IR Center', s.ir_center ? 'OBSTACLE' : 'clear', s.ir_center),
      tile('IR Right', s.ir_right ? 'OBSTACLE' : 'clear', s.ir_right),
      tile('Ultrasonic', (s.ultrasonic_cm || 0).toFixed(1) + ' cm', (s.ultrasonic_cm || 999) < 35),
      tile('Gaps L/C/R', `${(s.left_gap || 0).toFixed(2)} / ${(s.center_gap || 0).toFixed(2)} / ${(s.right_gap || 0).toFixed(2)}`),
      tile('Servo', (s.servo_angle || 0) + ' deg')
    ].join('');
    document.getElementById('motors').innerHTML = [
      tile('Front Left', (c.front_left || 0).toFixed(2)),
      tile('Front Right', (c.front_right || 0).toFixed(2)),
      tile('Rear Left', (c.rear_left || 0).toFixed(2)),
      tile('Rear Right', (c.rear_right || 0).toFixed(2))
    ].join('');
    if (data.camera_updated_at && data.camera_updated_at !== lastCameraAt) {
      lastCameraAt = data.camera_updated_at;
      document.getElementById('camera').src = '/api/camera?t=' + lastCameraAt;
    }
    document.getElementById('raw').textContent = JSON.stringify(data, null, 2);
  } catch (err) {
    document.getElementById('reason').textContent = 'UI connection lost. Retrying...';
  }
}
document.getElementById('stop').onclick = () => post('/api/stop', { stop: true });
document.getElementById('resume').onclick = () => post('/api/stop', { stop: false });
setInterval(poll, 250);
poll();
"""


def make_handler(shared: SharedState):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._write(HTML.encode("utf-8"), "text/html; charset=utf-8")
            elif parsed.path == "/static/style.css":
                self._write(CSS.encode("utf-8"), "text/css; charset=utf-8")
            elif parsed.path == "/static/app.js":
                self._write(JS.encode("utf-8"), "application/javascript; charset=utf-8")
            elif parsed.path == "/api/state":
                self._write(json.dumps(shared.snapshot().to_dict()).encode("utf-8"), "application/json")
            elif parsed.path == "/api/camera":
                data = shared.snapshot().last_camera_jpeg
                if not data:
                    self.send_error(404)
                    return
                self._write(data, "image/jpeg")
            else:
                self.send_error(404)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/api/stop":
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
                shared.set_emergency_stop(bool(payload.get("stop", True)))
                self._write(json.dumps({"ok": True}).encode("utf-8"), "application/json")
                return
            self.send_error(404)

        def log_message(self, format: str, *args) -> None:
            return

        def _write(self, body: bytes, content_type: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def start_ui_server(shared: SharedState, host: str, port: int) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), make_handler(shared))
    thread = Thread(target=server.serve_forever, name="arcane-ui", daemon=True)
    thread.start()
    return server

