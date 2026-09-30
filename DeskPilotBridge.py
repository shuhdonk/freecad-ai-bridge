"""
DeskPilot Bridge for FreeCAD (v2 - Thread-Safe)
================================================
A lightweight local HTTP server that lets DeskPilot control FreeCAD.
All FreeCAD API calls are dispatched to the MAIN thread via QTimer
to avoid deadlocks (FreeCAD's Python API is NOT thread-safe).

Usage:
  1. In FreeCAD: Macro -> Macros... -> select DeskPilotBridge -> Run
  2. Check the Report view (bottom panel) for "DeskPilot Bridge started"
  3. DeskPilot sends JSON commands over HTTP to localhost:8765.

Commands (POST /command, JSON body):
  {"cmd": "status"}
  {"cmd": "run_python", "code": "..."}
  {"cmd": "list_documents"}
  {"cmd": "export", "doc": "name", "fmt": "stl|step|obj", "path": "C:\\..."}
  {"cmd": "screenshot", "width": 1200, "height": 900}
  {"cmd": "close_doc", "doc": "name"}

Responses: JSON {"ok": true/false, "result": ..., "error": ...}
"""

import json
import base64
import os
import sys
import traceback
import queue
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

try:
    import FreeCAD
    import FreeCADGui as Gui
    from PySide2.QtCore import QTimer  # FreeCAD 1.x uses PySide2 (or PySide6)
except ImportError:
    try:
        from PySide6.QtCore import QTimer
    except ImportError:
        print("ERROR: This script must be run INSIDE FreeCAD.")
        sys.exit(1)

PORT = 8765


# ─── Command Queue (main-thread safe) ────────────────────────────────────────
_cmd_queue = queue.Queue()
_response_queue = queue.Queue()


def _execute_on_main(cmd, req):
    """Execute a command on the MAIN thread. Called by QTimer."""
    try:
        result = _dispatch(cmd, req)
        _response_queue.put({"ok": True, "result": result})
    except Exception as e:
        err = traceback.format_exc()
        print(f"[DeskPilotBridge] Error in {cmd}:\n{err}")
        _response_queue.put({"ok": False, "error": str(e), "traceback": err})


def _dispatch(cmd, req):
    if cmd == "status":
        return {
            "freecad_version": list(FreeCAD.Version()),
            "open_documents": list(FreeCAD.listDocuments().keys()),
            "python_version": sys.version.split('\n')[0],
        }

    elif cmd == "run_python":
        code = req.get("code", "")
        ns = {"FreeCAD": FreeCAD, "Gui": Gui, "__name__": "__bridge__"}
        exec(compile(code, "<deskpilot>", "exec"), ns)
        return ns.get("result", "OK")

    elif cmd == "list_documents":
        docs = {}
        for name, doc in FreeCAD.listDocuments().items():
            obj_list = []
            for obj in doc.Objects:
                obj_list.append({
                    "name": obj.Name,
                    "type": obj.TypeId,
                    "label": obj.Label,
                })
            docs[name] = {"objects": obj_list}
        return docs

    elif cmd == "export":
        doc_name = req.get("doc")
        fmt = req.get("fmt", "stl").lower()
        path = req.get("path", "")
        if not doc_name or doc_name not in FreeCAD.listDocuments():
            raise ValueError(f"Document '{doc_name}' not found")
        doc = FreeCAD.getDocument(doc_name)
        import Import
        import Mesh
        import MeshPart
        if fmt == "step":
            Import.export(doc.Objects, path)
        elif fmt == "stl":
            mesh = Mesh.Mesh()
            for obj in doc.Objects:
                if hasattr(obj, "Shape") and obj.Shape.Solids:
                    m = MeshPart.meshFromShape(
                        Shape=obj.Shape, LinearDeflection=0.1, AngularDeflection=0.5236
                    )
                    mesh.addMesh(m)
            mesh.write(path)
        elif fmt == "obj":
            Import.export(doc.Objects, path)
        else:
            raise ValueError(f"Unsupported format: {fmt}")
        return f"Exported to {path}"

    elif cmd == "screenshot":
        width = req.get("width", 1200)
        height = req.get("height", 900)
        view = Gui.activeDocument().ActiveView
        view.fitAll()
        tmp_path = os.path.join(os.environ.get("TEMP", "/tmp"), "_deskpilot_shot.png")
        view.saveImage(tmp_path, width, height, "White")
        with open(tmp_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("ascii")
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        return {"image_base64": img_b64}

    elif cmd == "close_doc":
        doc_name = req.get("doc")
        if doc_name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(doc_name)
            return f"Closed {doc_name}"
        raise ValueError(f"Document '{doc_name}' not found")

    else:
        raise ValueError(f"Unknown command: {cmd}")


# ─── Main-thread QTimer: polls the queue every 50ms ──────────────────────────
def _timer_tick():
    """Called on the main thread. Processes one queued command per tick."""
    try:
        cmd, req = _cmd_queue.get_nowait()
        _execute_on_main(cmd, req)
    except queue.Empty:
        pass


# ─── HTTP Handler (background thread - only enqueues) ────────────────────────
class BridgeHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send_json(self, data, code=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/command":
            self._send_json({"ok": False, "error": "Unknown path"}, 404)
            return

        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        try:
            req = json.loads(raw)
        except json.JSONDecodeError as e:
            self._send_json({"ok": False, "error": f"Bad JSON: {e}"})
            return

        cmd = req.get("cmd", "")

        # Enqueue for main-thread execution
        _cmd_queue.put((cmd, req))

        # Wait for the response (with timeout)
        try:
            response = _response_queue.get(timeout=120)
            self._send_json(response)
        except queue.Empty:
            self._send_json({"ok": False, "error": "Timeout waiting for FreeCAD to process command"})


# ─── Startup ──────────────────────────────────────────────────────────────────
def start_bridge():
    # Start HTTP server in a daemon thread (it only enqueues, never touches FreeCAD)
    server = HTTPServer(("127.0.0.1", PORT), BridgeHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    # Start QTimer on the main thread to process commands
    timer = QTimer()
    timer.timeout.connect(_timer_tick)
    timer.start(50)  # poll every 50ms

    # Keep a reference so the timer isn't garbage collected
    start_bridge._timer = timer
    start_bridge._server = server

    print("[DeskPilotBridge] v2 started on port 8765 (thread-safe)")
    Gui.addLogMessage("DeskPilot Bridge v2 started on port 8765")


start_bridge()
