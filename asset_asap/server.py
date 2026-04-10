"""
Local HTTP server embedded in the addon.
Listens for POST /import-asset from the browser extension.
Runs in a daemon thread so it never blocks Blender.
"""

import bpy
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

_server_instance = None
_server_thread = None


class _Handler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):  # silence default console spam
        pass

    def _send(self, code, body: dict):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        # Allow requests from the browser extension (any origin)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS, GET")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        # Pre-flight for CORS
        self._send(200, {})

    def do_POST(self):
        print(f"[AssetASAP] Incoming POST request to {self.path}")
        if self.path != "/import-asset":
            self._send(404, {"error": "Not found"})
            return

        length = int(self.headers.get("Content-Length", 0))
        try:
            data = self.rfile.read(length).decode("utf-8")
            print(f"[AssetASAP] Received body: {data}")
            body = json.loads(data)
        except Exception as e:
            print(f"[AssetASAP] JSON decode error: {e}")
            self._send(400, {"error": "Invalid JSON"})
            return

        asset_name = body.get("asset_name", "").strip()
        if not asset_name:
            self._send(400, {"error": "asset_name is required"})
            return

        print(f"[AssetASAP] Triggering import for: {asset_name}")

        def _trigger():
            try:
                # Provide visual feedback in Blender's status bar
                if hasattr(bpy.context, "workspace"):
                    bpy.context.workspace.status_text_set(f"Asset ASAP: Importing {asset_name}...")
                print(f"[AssetASAP] Calling operator for {asset_name}")
                getattr(bpy.ops, "as").import_by_name(asset_name=asset_name)
            except Exception as e:
                print(f"[AssetASAP] Operator execution error: {e}")
            return None

        # Use a small delay to ensure the server response is sent first
        bpy.app.timers.register(_trigger, first_interval=0.1)
        self._send(200, {"status": "ok", "asset_name": asset_name})

    def do_GET(self):
        if self.path == "/ping":
            self._send(200, {"status": "alive"})
        else:
            self._send(404, {"error": "Not found"})


def start(port: int):
    global _server_instance, _server_thread

    if _server_instance is not None:
        return  # already running

    try:
        # Use 127.0.0.1 for better compatibility with browser fetch
        _server_instance = HTTPServer(("127.0.0.1", port), _Handler)
    except OSError as e:
        print(f"[AssetASAP] Could not start server on port {port}: {e}")
        return

    _server_thread = threading.Thread(target=_server_instance.serve_forever, daemon=True)
    _server_thread.start()
    print(f"[AssetASAP] Listening for browser extension on http://127.0.0.1:{port}")

    # Reflect in scene props if available
    def _mark_running():
        try:
            bpy.context.scene.as_props.server_running = True
        except Exception:
            pass
        return None

    bpy.app.timers.register(_mark_running, first_interval=0.5)


def stop():
    global _server_instance, _server_thread

    if _server_instance is None:
        return

    _server_instance.shutdown()
    _server_instance = None
    _server_thread = None

    def _mark_stopped():
        try:
            bpy.context.scene.as_props.server_running = False
            if hasattr(bpy.context, "workspace"):
                bpy.context.workspace.status_text_set(None)
        except Exception:
            pass
        return None

    bpy.app.timers.register(_mark_stopped, first_interval=0.0)
    print("[AssetASAP] Server stopped.")
