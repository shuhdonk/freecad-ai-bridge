# FreeCAD AI Bridge

A lightweight local HTTP server that lets any AI assistant control **FreeCAD** via Python commands. No MCP protocol required — just plain HTTP + JSON.

## How It Works

```
┌──────────────┐    HTTP/JSON     ┌─────────────────────┐
│  AI Agent    │ ──────────────►  │  FreeCAD (desktop)  │
│  (any LLM)   │  localhost:8765  │  + Bridge Macro     │
└──────────────┘ ◄──────────────  └─────────────────────┘
                  JSON response
```

The bridge runs as a background thread inside FreeCAD. All FreeCAD API calls are dispatched to the main thread via Qt timers (thread-safe). The AI sends commands over HTTP and receives results.

## Requirements

- **FreeCAD 1.0+** (tested on 1.1.4)
- Any tool that can make HTTP requests (Python, Node.js, curl, etc.)

## Installation

1. Copy `freecad_ai_bridge.py` to your FreeCAD macro folder:
   - **Windows:** `%APPDATA%\FreeCAD\Macro\`
   - **Linux:** `~/.local/share/FreeCAD/Macro/`
   - **macOS:** `~/Library/Application Support/FreeCAD/Macro/`

2. Open FreeCAD → **Macro → Macros…** → select `freecad_ai_bridge` → **Run**

3. Check the **Report view** (bottom panel) for:
   ```
   FreeCAD AI Bridge started on port 8765
   ```

That's it. The bridge is now listening on `http://localhost:8765`.

## API Reference

All commands are sent as `POST http://localhost:8765/command` with a JSON body.

### Commands

| Command | Body | Description |
|---------|------|-------------|
| `status` | `{"cmd": "status"}` | FreeCAD version, open documents |
| `run_python` | `{"cmd": "run_python", "code": "..."}` | Execute arbitrary Python in FreeCAD's namespace |
| `list_documents` | `{"cmd": "list_documents"}` | All open docs with object names/types |
| `export` | `{"cmd": "export", "doc": "name", "fmt": "stl\|step\|obj", "path": "C:\\..."}` | Export a document to file |
| `screenshot` | `{"cmd": "screenshot", "width": 1200, "height": 900}` | PNG (base64) of the active 3D view |
| `close_doc` | `{"cmd": "close_doc", "doc": "name"}` | Close a document |

### Response Format

```json
{"ok": true, "result": "..."}
// or on error:
{"ok": false, "error": "message", "traceback": "..."}
```

### Example

**Check connection:**
```bash
curl -X POST http://localhost:8765/command \
  -H "Content-Type: application/json" \
  -d '{"cmd": "status"}'
```

## Using with AI Assistants

**Most any local or cloud AI model can connect.** Just tell your AI what you want 3D modeled and it will build it for you in FreeCAD. The bridge is model-agnostic — it's a plain HTTP API that works with anything that can execute code or make HTTP requests:

- **Local models:** Ollama (LLaMA, Mistral, etc.), LM Studio, llama.cpp
- **Cloud models:** ChatGPT (Code Interpreter), Claude (Tool Use), Gemini
- **IDE agents:** Cursor, Copilot, Windsurf
- **Custom agents:** Python scripts, Node.js, etc.

All you need to tell your AI is:

> "There is a local HTTP API at `http://localhost:8765/command`. Send POST requests with JSON bodies. The main command is `{"cmd": "run_python", "code": "..."}` which executes Python inside FreeCAD. Use `{"cmd": "screenshot"}` to see the 3D view. Use `{"cmd": "export"}` to save files."

Then just describe what you want: *"Make a mounting bracket, 80×40mm, 4 corner holes, 1mm fillets"* — and your AI will write the FreeCAD Python, push it through the bridge, verify with a screenshot, and export the STL for printing.

## Files

| File | Purpose |
|------|---------|
| `freecad_ai_bridge.py` | The FreeCAD macro (core server) |
| `freecad_client.js` | Node.js client example |
| `activate_freecad.ps1` | Windows helper to bring FreeCAD to foreground |

## Architecture Notes

- **Thread safety:** FreeCAD's Python API is NOT thread-safe. The bridge uses a `queue.Queue` + `QTimer` (50ms poll) to dispatch all commands to the main GUI thread.
- **Port:** Fixed at 8765. Change the `PORT` constant in the macro if needed.
- **Security:** Binds to `127.0.0.1` only — not accessible from the network.
- **Timeout:** Commands have a 120-second timeout.

## License

[MIT](LICENSE)
