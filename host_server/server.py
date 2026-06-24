from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .autonomous_dashboard import AUTONOMOUS_DASHBOARD_HTML
from .dashboard import DASHBOARD_HTML
from .processing import HostProcessor


class VehicleRequestHandler(BaseHTTPRequestHandler):
    processor: HostProcessor

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._write_html(DASHBOARD_HTML)
            return
        if parsed.path == "/auto":
            self._write_html(AUTONOMOUS_DASHBOARD_HTML)
            return
        if parsed.path == "/health":
            self._write_json({"status": "ok"})
            return
        if parsed.path == "/api/v1/state":
            self._write_json(self.processor.state())
            return
        if parsed.path == "/api/v1/latest-image":
            image = self.processor.latest_image_bytes()
            if image is None:
                self.send_error(404)
                return
            body, content_type = image
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == "/api/v1/accident-report":
            from urllib.parse import parse_qs

            query = parse_qs(parsed.query)
            report_path = query.get("path", [None])[0]
            if report_path and Path(report_path).exists():
                body = Path(report_path).read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/markdown; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_error(404)
            return
        self.send_error(404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/v1/manual-command":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
                command = self.processor.update_command(payload)
                self._write_json({"command": command.__dict__})
            except Exception as exc:
                self._write_error(exc)
            return
        if parsed.path == "/api/v1/mode":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
                result = self.processor.update_mode(payload)
                self._write_json(result)
            except Exception as exc:
                self._write_error(exc)
            return
        if parsed.path != "/api/v1/cycle":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            packet = json.loads(self.rfile.read(length).decode("utf-8"))
            command = self.processor.process_packet(packet)
            self._write_json(command.to_json_dict())
        except Exception as exc:
            self._write_error(exc)

    def log_message(self, format: str, *args) -> None:
        return

    def _write_json(self, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _write_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _write_error(self, exc: Exception) -> None:
        body = json.dumps({"error": str(exc)}).encode("utf-8")
        self.send_response(500)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run(host: str, port: int, model_path: str | None, dataset_path: str) -> None:
    VehicleRequestHandler.processor = HostProcessor(model_path=model_path, dataset_path=dataset_path)
    server = ThreadingHTTPServer((host, port), VehicleRequestHandler)
    print(f"ARCANE host processor listening on http://{host}:{port}")
    server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--model", default="models/manual/best_manual_model.joblib")
    parser.add_argument("--dataset", default="dataset/drives/manual_drive_log_6_clean.csv")
    args = parser.parse_args()
    run(args.host, args.port, args.model, args.dataset)


if __name__ == "__main__":
    main()
