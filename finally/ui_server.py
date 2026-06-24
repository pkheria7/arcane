from __future__ import annotations

import json
import zipfile
from io import BytesIO
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, Thread
from urllib.parse import urlparse

from .models import Telemetry
from .recording import list_records


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
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
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
      <div id="map"></div>
      <div class="grid" id="sensors"></div>
      <div class="grid" id="motors"></div>
      <h2>Evidence Records</h2>
      <div id="records"></div>
      <div class="actions">
        <button id="stop" class="danger">Emergency Stop</button>
        <button id="resume">Resume</button>
      </div>
      <pre id="raw"></pre>
    </section>
  </main>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
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
#map { height: 240px; border: 1px solid #333; border-radius: 8px; overflow: hidden; margin: 12px 0; background: #050505; }
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
a { color: #8bb6ff; }
h2 { font-size: 16px; margin: 16px 0 8px; }
.record { background: #0e0e0e; border: 1px solid #2b2b2b; border-radius: 8px; padding: 10px; margin: 8px 0; }
pre { white-space: pre-wrap; color: #aaa; font-size: 11px; max-height: 180px; overflow: auto; }
@media (max-width: 820px) { main { grid-template-columns: 1fr; } .camera { min-height: 220px; } }
"""


JS = """
let lastCameraAt = 0;
let map = null;
let marker = null;
let trail = null;
let trailPoints = [];
function tile(label, value, active=false) {
  return `<div class="tile ${active ? 'active' : ''}"><b>${label}</b>${value}</div>`;
}
function initMap(lat, lon) {
  if (map || !window.L) return;
  map = L.map('map').setView([lat, lon], 18);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 20,
    attribution: '&copy; OpenStreetMap contributors'
  }).addTo(map);
  marker = L.marker([lat, lon]).addTo(map);
  trail = L.polyline([], { color: '#6fa0ff', weight: 4 }).addTo(map);
}
function updateMap(s) {
  const lat = Number(s.gps_lat);
  const lon = Number(s.gps_lon);
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
  initMap(lat, lon);
  if (!map) return;
  const point = [lat, lon];
  marker.setLatLng(point);
  trailPoints.push(point);
  if (trailPoints.length > 300) trailPoints.shift();
  trail.setLatLngs(trailPoints);
  map.panTo(point, { animate: false });
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
      tile('Servo', (s.servo_angle || 0) + ' deg'),
      tile('GPS', s.gps_lat && s.gps_lon ? `${Number(s.gps_lat).toFixed(6)}, ${Number(s.gps_lon).toFixed(6)}` : 'waiting for fix', !s.gps_fix_quality),
      tile('GPS Fix', s.gps_fix_quality ? 'fix ' + s.gps_fix_quality : 'no fix', !s.gps_fix_quality)
    ].join('');
    updateMap(s);
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
    renderRecords(data);
    document.getElementById('raw').textContent = JSON.stringify(data, null, 2);
  } catch (err) {
    document.getElementById('reason').textContent = 'UI connection lost. Retrying...';
  }
}
async function renderRecords(data) {
  const box = document.getElementById('records');
  const active = data.active_recording;
  let html = active ? `<div class="record"><b>Recording ${active.active_ir}</b><br>${active.duration_s.toFixed(1)}s, ${active.frame_count} frames</div>` : '';
  try {
    const res = await fetch('/api/records');
    const records = await res.json();
    html += records.slice(0, 5).map(r => `<div class="record"><b>${r.id}</b><br>${(r.duration_s || 0).toFixed(1)}s, ${r.frame_count || 0} frames<br><a href="/api/records/${r.id}.zip">Download record</a></div>`).join('');
  } catch (err) {}
  box.innerHTML = html || '<div class="record">No evidence records yet.</div>';
}
document.getElementById('stop').onclick = () => post('/api/stop', { stop: true });
document.getElementById('resume').onclick = () => post('/api/stop', { stop: false });
setInterval(poll, 250);
poll();
"""


def make_handler(shared: SharedState, records_dir: str | Path):
    records_root = Path(records_dir)

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
            elif parsed.path == "/api/records":
                self._write(json.dumps(list_records(records_root)).encode("utf-8"), "application/json")
            elif parsed.path.startswith("/api/records/") and parsed.path.endswith(".zip"):
                record_id = Path(parsed.path.removeprefix("/api/records/").removesuffix(".zip")).name
                record_dir = records_root / record_id
                if not record_dir.exists() or not record_dir.is_dir():
                    self.send_error(404)
                    return
                self._write_zip(record_dir)
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

        def _write_zip(self, record_dir: Path) -> None:
            buffer = BytesIO()
            with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for path in record_dir.rglob("*"):
                    if path.is_file():
                        zf.write(path, path.relative_to(record_dir.parent))
            body = buffer.getvalue()
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition", f'attachment; filename="{record_dir.name}.zip"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def start_ui_server(shared: SharedState, host: str, port: int, records_dir: str | Path) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), make_handler(shared, records_dir))
    thread = Thread(target=server.serve_forever, name="arcane-ui", daemon=True)
    thread.start()
    return server
