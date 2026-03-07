"""Simple HTTP server for the grocery bot game visualizer."""

import http.server
import json
import os
import re

PORT = 8080
LOGS_DIR = "logs"


class VisualizerHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self.path = "/visualizer.html"
        elif self.path == "/api/logs":
            self._serve_log_list()
            return
        return super().do_GET()

    def _serve_log_list(self):
        """Return list of available game log basenames."""
        logs = set()
        if os.path.isdir(LOGS_DIR):
            for f in os.listdir(LOGS_DIR):
                m = re.match(r"((?:game|local)_[^.]+)\.(csv|json)$", f)
                if m:
                    logs.add(m.group(1))
        # Only include logs that have BOTH csv and json
        complete = sorted(
            name for name in logs
            if os.path.exists(f"{LOGS_DIR}/{name}.csv")
            and os.path.exists(f"{LOGS_DIR}/{name}.json")
        )
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(complete).encode())

    def log_message(self, format, *args):
        # Suppress per-request logging noise
        pass


if __name__ == "__main__":
    print(f"Visualizer running at http://localhost:{PORT}")
    print("Open in browser, then select a game log from the dropdown.")
    server = http.server.HTTPServer(("", PORT), VisualizerHandler)
    server.serve_forever()
