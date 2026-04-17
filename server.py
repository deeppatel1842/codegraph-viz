"""Built-in HTTP server with file watching and live-reload.

Provides two modes:
- start_server(): One-shot HTTP server serving the graph viewer
- serve_with_watch(): Watches for .py file changes and auto-regenerates

The server binds to 127.0.0.1 only (localhost, not exposed to network).
Also handles embedding graph JSON into the HTML template so the output
is a single self-contained .html file that works offline.
"""

from __future__ import annotations

import json
import threading
import time
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path


class GraphHandler(SimpleHTTPRequestHandler):
    """Serves the graph viewer and provides JSON API for live-reload."""

    graph_data: dict | None = None
    output_dir: Path = Path(".")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(self.output_dir), **kwargs)

    def do_GET(self):
        if self.path == "/api/graph":
            self._send_json(self.graph_data or {})
        elif self.path == "/api/health":
            self._send_json({"status": "ok"})
        else:
            super().do_GET()

    def _send_json(self, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        # Suppress default request logging
        pass


def start_server(
    output_dir: Path,
    graph_data: dict,
    port: int = 7788,
    open_browser: bool = True,
) -> HTTPServer:
    """Start the graph viewer HTTP server.

    Args:
        output_dir: Directory containing graph.html and graph_data.json.
        graph_data: Current graph data dict (for /api/graph endpoint).
        port: Port to bind to.
        open_browser: Whether to open browser automatically.

    Returns:
        The running HTTPServer instance.
    """
    GraphHandler.graph_data = graph_data
    GraphHandler.output_dir = output_dir

    server = HTTPServer(("127.0.0.1", port), GraphHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    url = f"http://127.0.0.1:{port}/graph.html"
    print(f"Server running at {url}")

    if open_browser:
        webbrowser.open(url)

    return server


def serve_with_watch(
    project_root: Path,
    output_dir: Path,
    port: int = 7788,
    interval: float = 5.0,
):
    """Start server and watch for file changes, regenerating on change.

    Blocks until Ctrl+C.
    """
    from codegraph.scanner import scan_project

    print(f"Scanning {project_root}...")
    graph = scan_project(project_root)
    _write_outputs(output_dir, graph)

    server = start_server(output_dir, graph, port=port)
    last_hash = _quick_hash(project_root)

    print(f"Watching for changes (every {interval}s). Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(interval)
            current_hash = _quick_hash(project_root)
            if current_hash != last_hash:
                print("Changes detected, regenerating...")
                graph = scan_project(project_root)
                _write_outputs(output_dir, graph)
                GraphHandler.graph_data = graph
                last_hash = current_hash
                print(f"Updated: {len(graph['nodes'])} files, {len(graph['edges'])} edges")
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


def _write_outputs(output_dir: Path, graph: dict):
    """Write graph_data.json, file_index.json, and graph.html."""
    from codegraph.scanner import build_file_index

    output_dir.mkdir(parents=True, exist_ok=True)

    with open(output_dir / "graph_data.json", "w", encoding="utf-8") as f:
        json.dump(graph, f, indent=2)

    file_index = build_file_index(graph)
    with open(output_dir / "file_index.json", "w", encoding="utf-8") as f:
        json.dump(file_index, f, indent=2)

    # Embed into HTML template
    template_path = Path(__file__).parent / "templates" / "graph.html"
    if template_path.exists():
        template = template_path.read_text(encoding="utf-8")
        json_str = json.dumps(graph).replace("</script>", "<\\/script>")
        html = template.replace("__GRAPH_DATA_PLACEHOLDER__", json_str)
        with open(output_dir / "graph.html", "w", encoding="utf-8") as f:
            f.write(html)


def _quick_hash(project_root: Path) -> str:
    """Quick hash of all .py file mtimes for change detection."""
    import hashlib
    h = hashlib.md5()
    for py in sorted(project_root.rglob("*.py")):
        if any(p.startswith(".") for p in py.parts):
            continue
        try:
            h.update(f"{py}:{py.stat().st_mtime}".encode())
        except OSError:
            pass
    return h.hexdigest()
