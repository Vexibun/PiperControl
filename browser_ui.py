import http.server
import json
import socket
import socketserver
import threading
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

from engine import PiperEngine
from settings import load_settings, save_settings
from utils import list_voices, list_audio_sinks


def get_local_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


class BrowserRequestHandler(http.server.BaseHTTPRequestHandler):
    def __init__(self, *args, app=None, **kwargs):
        self.app = app
        super().__init__(*args, **kwargs)

    def _set_json_headers(self, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()

    def _set_html_headers(self, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._set_html_headers()
            self.wfile.write(self.app.html_page().encode("utf-8"))
            return

        if parsed.path == "/api/status":
            data = {
                "settings": self.app.settings,
                "voices": list_voices(),
                "sinks": list_audio_sinks(),
                "local_ip": get_local_ip(),
                "port": self.app.port,
            }
            self._set_json_headers()
            self.wfile.write(json.dumps(data).encode("utf-8"))
            return

        if parsed.path == "/api/history":
            self._set_json_headers()
            self.wfile.write(json.dumps({"history": self.app.history}).encode("utf-8"))
            return

        if parsed.path == "/api/favorites":
            self._set_json_headers()
            self.wfile.write(json.dumps({"favorites": self.app.favorites}).encode("utf-8"))
            return

        if parsed.path == "/api/presets":
            self._set_json_headers()
            self.wfile.write(json.dumps({"presets": self.app.presets}).encode("utf-8"))
            return

        if parsed.path == "/api/recents":
            self._set_json_headers()
            self.wfile.write(json.dumps(self.app.recents).encode("utf-8"))
            return

        self.send_error(404, "Not Found")

    def do_POST(self):
        parsed = urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_length).decode("utf-8")
        data = {}

        if self.headers.get("Content-Type", "").startswith("application/json"):
            try:
                data = json.loads(raw_body or "{}")
            except json.JSONDecodeError:
                data = {}
        else:
            for pair in raw_body.split("&"):
                if "=" in pair:
                    key, value = pair.split("=", 1)
                    data[key] = value

        if parsed.path == "/api/speak":
            text = data.get("text", "").strip()
            if text:
                self.app.update_settings(data)
                self.app.speak(text)
            self._set_json_headers()
            self.wfile.write(json.dumps({"ok": True}).encode("utf-8"))
            return

        if parsed.path == "/api/stop":
            self.app.stop()
            self._set_json_headers()
            self.wfile.write(json.dumps({"ok": True}).encode("utf-8"))
            return

        if parsed.path == "/api/settings":
            self.app.update_settings(data)
            self._set_json_headers()
            self.wfile.write(json.dumps({"ok": True, "settings": self.app.settings}).encode("utf-8"))
            return

        if parsed.path == "/api/favorite/add":
            name = data.get("name", "").strip()
            text = data.get("text", "").strip()
            if name and text:
                self.app.favorites[name] = text
                self.app.save_favorites()
                self._set_json_headers()
                self.wfile.write(json.dumps({"ok": True}).encode("utf-8"))
            else:
                self._set_json_headers(400)
                self.wfile.write(json.dumps({"ok": False, "error": "Name and text required"}).encode("utf-8"))
            return

        if parsed.path == "/api/favorite/remove":
            name = data.get("name", "").strip()
            if name and name in self.app.favorites:
                del self.app.favorites[name]
                self.app.save_favorites()
                self._set_json_headers()
                self.wfile.write(json.dumps({"ok": True}).encode("utf-8"))
            else:
                self._set_json_headers(404)
                self.wfile.write(json.dumps({"ok": False, "error": "Favorite not found"}).encode("utf-8"))
            return

        if parsed.path == "/api/history/clear":
            self.app.history = []
            self.app.save_history()
            self._set_json_headers()
            self.wfile.write(json.dumps({"ok": True}).encode("utf-8"))
            return

        if parsed.path == "/api/preset/save":
            name = data.get("name", "").strip()
            if name:
                self.app.presets[name] = {
                    "voice": data.get("voice"),
                    "speed": data.get("speed"),
                    "noise": data.get("noise"),
                    "noise_w": data.get("noise_w"),
                    "sentence_silence": data.get("sentence_silence"),
                }
                self.app.save_presets()
                self._set_json_headers()
                self.wfile.write(json.dumps({"ok": True}).encode("utf-8"))
            else:
                self._set_json_headers(400)
                self.wfile.write(json.dumps({"ok": False, "error": "Name required"}).encode("utf-8"))
            return

        if parsed.path == "/api/preset/load":
            name = data.get("name", "").strip()
            if name and name in self.app.presets:
                preset = self.app.presets[name]
                self.app.settings.update(preset)
                save_settings(self.app.settings)
                self._set_json_headers()
                self.wfile.write(json.dumps({"ok": True, "preset": preset}).encode("utf-8"))
            else:
                self._set_json_headers(404)
                self.wfile.write(json.dumps({"ok": False, "error": "Preset not found"}).encode("utf-8"))
            return

        if parsed.path == "/api/preset/delete":
            name = data.get("name", "").strip()
            if name and name in self.app.presets:
                del self.app.presets[name]
                self.app.save_presets()
                self._set_json_headers()
                self.wfile.write(json.dumps({"ok": True}).encode("utf-8"))
            else:
                self._set_json_headers(404)
                self.wfile.write(json.dumps({"ok": False, "error": "Preset not found"}).encode("utf-8"))
            return

        if parsed.path == "/api/shutdown":
            self._set_json_headers()
            self.wfile.write(json.dumps({"ok": True}).encode("utf-8"))
            threading.Thread(target=self.app.shutdown, daemon=True).start()
            return

        self.send_error(404, "Not Found")

    def log_message(self, format, *args):
        # suppress default HTTP logging
        return


class BrowserApp:

    def __init__(self, port: int = 8080):
        self.port = port
        self.settings = load_settings()
        self.engine = PiperEngine()
        self.tts_thread = None
        self.server = None
        self.thread = None
        self.history = self.load_history()
        self.favorites = self.load_favorites()
        self.presets = self.load_presets()
        self.recents = self.load_recents()

    def load_history(self):
        history_path = Path(__file__).parent / "history.json"
        if history_path.exists():
            try:
                with open(history_path, "r", encoding="utf-8") as f:
                    return json.load(f) or []
            except Exception:
                return []
        return []

    def save_history(self):
        history_path = Path(__file__).parent / "history.json"
        try:
            with open(history_path, "w", encoding="utf-8") as f:
                json.dump(self.history[-50:], f, indent=2)  # Keep last 50 items
        except Exception as e:
            print(f"Failed to save history: {e}")

    def load_favorites(self):
        favorites_path = Path(__file__).parent / "favorites.json"
        if favorites_path.exists():
            try:
                with open(favorites_path, "r", encoding="utf-8") as f:
                    return json.load(f) or {}
            except Exception:
                return {}
        return {}

    def save_favorites(self):
        favorites_path = Path(__file__).parent / "favorites.json"
        try:
            with open(favorites_path, "w", encoding="utf-8") as f:
                json.dump(self.favorites, f, indent=2)
        except Exception as e:
            print(f"Failed to save favorites: {e}")

    def add_to_history(self, text: str):
        from datetime import datetime
        self.history.append({
            "text": text,
            "timestamp": datetime.now().isoformat(),
        })
        self.save_history()

    def load_presets(self):
        presets_path = Path(__file__).parent / "presets.json"
        if presets_path.exists():
            try:
                with open(presets_path, "r", encoding="utf-8") as f:
                    return json.load(f) or {}
            except Exception:
                return {}
        return {}

    def save_presets(self):
        presets_path = Path(__file__).parent / "presets.json"
        try:
            with open(presets_path, "w", encoding="utf-8") as f:
                json.dump(self.presets, f, indent=2)
        except Exception as e:
            print(f"Failed to save presets: {e}")

    def load_recents(self):
        recents_path = Path(__file__).parent / "recents.json"
        if recents_path.exists():
            try:
                with open(recents_path, "r", encoding="utf-8") as f:
                    return json.load(f) or {"voices": [], "devices": []}
            except Exception:
                return {"voices": [], "devices": []}
        return {"voices": [], "devices": []}

    def save_recents(self):
        recents_path = Path(__file__).parent / "recents.json"
        try:
            with open(recents_path, "w", encoding="utf-8") as f:
                json.dump(self.recents, f, indent=2)
        except Exception as e:
            print(f"Failed to save recents: {e}")

    def add_recent_voice(self, voice: str):
        if voice in self.recents["voices"]:
            self.recents["voices"].remove(voice)
        self.recents["voices"].insert(0, voice)
        self.recents["voices"] = self.recents["voices"][:3]  # Keep last 3
        self.save_recents()

    def add_recent_device(self, device: str):
        if device in self.recents["devices"]:
            self.recents["devices"].remove(device)
        self.recents["devices"].insert(0, device)
        self.recents["devices"] = self.recents["devices"][:3]  # Keep last 3
        self.save_recents()

    def update_settings(self, data: dict):
        if "voice" in data:
            self.settings["voice"] = data["voice"]
            self.add_recent_voice(data["voice"])
        if "speed" in data:
            try:
                self.settings["speed"] = float(data["speed"])
            except (TypeError, ValueError):
                pass
        if "noise" in data:
            try:
                self.settings["noise"] = float(data["noise"])
            except (TypeError, ValueError):
                pass
        if "noise_w" in data:
            try:
                self.settings["noise_w"] = float(data["noise_w"])
            except (TypeError, ValueError):
                pass
        if "sentence_silence" in data:
            try:
                self.settings["sentence_silence"] = float(data["sentence_silence"])
            except (TypeError, ValueError):
                pass
        if "output_device" in data:
            self.settings["output_device"] = data["output_device"]
            self.add_recent_device(data["output_device"])
        if "mute" in data:
            self.settings["mute"] = bool(data["mute"])
            self.engine.set_mute(self.settings["mute"])

        save_settings(self.settings)

    def speak(self, text: str):
        if self.settings.get("mute") or not text:
            return

        if self.tts_thread and self.tts_thread.is_alive():
            return

        self.add_to_history(text)

        self.tts_thread = threading.Thread(
            target=self.engine._run,
            args=(text, self.settings),
            daemon=True,
        )
        self.tts_thread.start()

    def stop(self):
        self.engine.stop()

    def shutdown(self):
        self.stop()
        self.stop_server()

    def html_page(self) -> str:
        return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Piper TTS Control</title>
<style>
  * { box-sizing: border-box; }
  
  :root { --bg: #121212; --bg-light: #1e1e1e; --bg-sidebar: #1a1a1a; --border: #333; --text: #eee; --text-muted: #999; --primary: #4f8cff; --primary-hover: #6fa3ff; --secondary: #2d2d2d; --danger: #e34d5a; }
  
  body.light-mode { --bg: #f5f5f5; --bg-light: #ffffff; --bg-sidebar: #f0f0f0; --border: #ddd; --text: #222; --text-muted: #666; }
  
  body { margin: 0; min-height: 100vh; display: flex; background: var(--bg); color: var(--text); font-family: Inter, -apple-system, BlinkMacSystemFont, sans-serif; transition: background .2s, color .2s; overflow-x: hidden; }
  
  .sidebar { width: 300px; background: var(--bg-sidebar); border-right: 1px solid var(--border); overflow-y: auto; height: 100vh; position: fixed; left: 0; top: 0; }
  .sidebar-header { padding: 16px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; }
  .theme-toggle { background: none; border: none; font-size: 1.2rem; cursor: pointer; }
  .sidebar-overlay { display: none; }
  .main { flex: 1; margin-left: 300px; display: flex; justify-content: center; align-items: flex-start; padding: 24px; }
  .mobile-topbar { display: none; }
  .toolbar { display: flex; gap: 10px; margin-bottom: 12px; flex-wrap: wrap; }
  
  .sidebar-section { border-bottom: 1px solid var(--border); padding: 12px; }
  .sidebar-title { font-weight: 600; font-size: 0.9rem; color: var(--primary); margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center; cursor: pointer; user-select: none; }
  .sidebar-title:hover { color: var(--primary-hover); }
  .toggle-btn { font-size: 0.75rem; color: var(--text-muted); }
  .sidebar-content { display: none; max-height: 350px; overflow-y: auto; }
  .sidebar-content.open { display: block; }
  
  .item { padding: 8px 10px; background: var(--bg-light); border-radius: 8px; margin-bottom: 6px; font-size: 0.85rem; cursor: pointer; transition: background .15s; display: flex; justify-content: space-between; align-items: center; }
  .item:hover { background: var(--border); }
  .item-text { flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .item-actions { display: flex; gap: 4px; }
  .item-btn { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 0.75rem; padding: 0; }
  .item-btn:hover { color: var(--primary); }
  
  .search-box { width: 100%; padding: 8px; background: var(--bg-light); border: 1px solid var(--border); border-radius: 6px; color: var(--text); margin-bottom: 8px; font-size: 0.85rem; }
  .recent-buttons { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
  .recent-btn { padding: 6px 10px; background: var(--bg-light); border: 1px solid var(--border); border-radius: 6px; color: var(--text); cursor: pointer; font-size: 0.8rem; }
  .recent-btn:hover { background: var(--primary); color: white; }
  
  .container { width: min(900px, 100%); }
  h1 { margin: 0 0 20px 0; font-size: 1.7rem; }
  .card { background: var(--bg-light); border: 1px solid var(--border); border-radius: 14px; padding: 20px; box-shadow: 0 8px 32px rgba(0,0,0,0.1); }
  
  textarea { width: 100%; min-height: 180px; border: 1px solid var(--border); background: var(--bg); color: var(--text); padding: 14px; border-radius: 10px; resize: vertical; font-size: 1rem; line-height: 1.6; }
  textarea.batch-mode { min-height: 300px; }
  
  .counter { font-size: 0.8rem; color: var(--text-muted); margin-top: 4px; }
  .row { display: grid; gap: 14px; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); margin-top: 16px; }
  label { display: block; margin-bottom: 6px; color: var(--text); font-size: 0.9rem; font-weight: 500; }
  select, input[type="range"], input[type="number"], input[type="text"], input[type="search"] { width: 100%; border-radius: 8px; background: var(--bg); color: var(--text); border: 1px solid var(--border); padding: 10px; }
  input[type="range"] { padding: 6px; }
  
  .controls { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; }
  .mobile-actions-bar { display: none; }
  button { border: none; border-radius: 8px; padding: 10px 16px; font-size: 0.9rem; cursor: pointer; transition: transform .15s, background .15s; font-weight: 500; }
  button:hover { transform: translateY(-2px); }
  .primary { background: var(--primary); color: white; }
  .primary:hover { background: var(--primary-hover); }
  .secondary { background: var(--secondary); color: var(--text); }
  .secondary:hover { background: var(--border); }
  .danger { background: var(--danger); color: white; }
  .small { padding: 6px 10px; font-size: 0.8rem; }
  
  .status { margin-top: 10px; font-size: 0.9rem; color: #6f9; }
  .field-inline { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; margin-top: 12px; }
  .field-inline label { margin-bottom: 0; }
  
  .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); z-index: 1000; align-items: center; justify-content: center; }
  .modal.open { display: flex; }
  .modal-content { background: var(--bg-light); border-radius: 12px; padding: 24px; max-width: 500px; max-height: 80vh; overflow-y: auto; width: min(500px, calc(100vw - 32px)); }
  .modal-close { float: right; cursor: pointer; font-size: 1.5rem; color: var(--text-muted); }
  
  .shortcut-list { display: grid; gap: 10px; margin-top: 12px; }
  .shortcut { display: grid; grid-template-columns: 120px 1fr; gap: 12px; padding: 8px; background: var(--bg); border-radius: 6px; }
  .shortcut-key { font-weight: 600; color: var(--primary); font-family: monospace; }
  
  @media (max-width: 768px) {
    body.sidebar-open { overflow: hidden; }
    .sidebar { width: min(320px, 86vw); max-width: 100%; z-index: 1100; transform: translateX(-100%); transition: transform .2s ease; box-shadow: 0 10px 30px rgba(0,0,0,0.35); }
    .sidebar.open { transform: translateX(0); }
    .sidebar-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.45); z-index: 1050; }
    .sidebar-overlay.open { display: block; }
    .main { margin-left: 0; padding: 12px; width: 100%; }
    .mobile-topbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
    .mobile-brand { font-size: 1rem; font-weight: 600; }
    .mobile-actions { display: flex; align-items: center; gap: 8px; }
    .container { width: 100%; }
    .card { padding: 16px; border-radius: 12px; }
    h1 { font-size: 1.4rem; margin-bottom: 16px; }
    textarea { min-height: 160px; padding: 12px; }
    textarea.batch-mode { min-height: 240px; }
    .row { grid-template-columns: 1fr; gap: 12px; }
    .controls { display: grid; grid-template-columns: 1fr 1fr; }
    .controls button { width: 100%; }
    .field-inline { gap: 10px; align-items: flex-start; }
    .field-inline label { width: 100%; }
    .toolbar { gap: 8px; }
    .toolbar button { flex: 1 1 140px; }
    .shortcut { grid-template-columns: 1fr; gap: 6px; }
    .mobile-actions-bar {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
      position: fixed;
      left: 12px;
      right: 12px;
      bottom: 12px;
      z-index: 1000;
      padding: 10px;
      border: 1px solid var(--border);
      border-radius: 14px;
      background: color-mix(in srgb, var(--bg-light) 88%, transparent);
      backdrop-filter: blur(12px);
      box-shadow: 0 12px 32px rgba(0,0,0,0.28);
    }
    .mobile-actions-bar button {
      min-height: 48px;
      font-size: 1rem;
    }
    .card { padding-bottom: calc(88px + env(safe-area-inset-bottom, 0px)); }
  }

  @media (max-width: 480px) {
    .main { padding: 10px; }
    .card { padding: 14px; padding-bottom: calc(92px + env(safe-area-inset-bottom, 0px)); }
    button { padding: 10px 12px; }
    .controls { grid-template-columns: 1fr; }
    .counter { line-height: 1.5; }
    .mobile-topbar { margin-bottom: 10px; }
    .mobile-actions-bar { left: 10px; right: 10px; bottom: 10px; }
  }
</style>
</head>
<body>

<div id="sidebar-overlay" class="sidebar-overlay" onclick="closeSidebar()"></div>

<div id="sidebar" class="sidebar">
  <div class="sidebar-header">
    <div style="font-weight: 600;">Piper</div>
    <button class="theme-toggle" onclick="toggleTheme()" title="Toggle theme">🌙</button>
  </div>
  
  <div class="sidebar-section">
    <div class="sidebar-title" onclick="toggleSection('presets')">
      ⚙️ Presets <span class="toggle-btn">▼</span>
    </div>
    <div id="presets" class="sidebar-content open">
      <div id="presets-list"></div>
      <button class="secondary small" style="width:100%; margin-top:8px;" onclick="savePreset()">Save Current</button>
    </div>
  </div>
  
  <div class="sidebar-section">
    <div class="sidebar-title" onclick="toggleSection('recents')">
      📌 Recent <span class="toggle-btn">▼</span>
    </div>
    <div id="recents" class="sidebar-content open">
      <div style="margin-bottom:8px;">
        <small style="color:var(--text-muted);">Voices</small>
        <div id="recent-voices" class="recent-buttons"></div>
      </div>
      <div>
        <small style="color:var(--text-muted);">Devices</small>
        <div id="recent-devices" class="recent-buttons"></div>
      </div>
    </div>
  </div>
  
  <div class="sidebar-section">
    <div class="sidebar-title" onclick="toggleSection('history')">
      📋 History <span class="toggle-btn">▼</span>
    </div>
    <div id="history" class="sidebar-content open">
      <input type="search" id="history-search" class="search-box" placeholder="Search...">
      <div id="history-list"></div>
      <button class="secondary small" style="width:100%; margin-top:8px;" onclick="clearHistory()">Clear All</button>
    </div>
  </div>
  
  <div class="sidebar-section">
    <div class="sidebar-title" onclick="toggleSection('favorites')">
      ⭐ Favorites <span class="toggle-btn">▼</span>
    </div>
    <div id="favorites" class="sidebar-content open">
      <div id="favorites-list"></div>
      <button class="secondary small" style="width:100%; margin-top:8px;" onclick="saveFavorite()">Save Current</button>
    </div>
  </div>
</div>

<div class="main">
  <div class="container">
    <div class="card">
      <div class="mobile-topbar">
        <button class="secondary small" type="button" onclick="toggleSidebar()">☰ Menu</button>
        <div class="mobile-brand">Piper TTS</div>
        <div class="mobile-actions">
          <button class="secondary small" type="button" onclick="toggleTheme()" title="Toggle theme">◐</button>
        </div>
      </div>
      <h1>Piper TTS</h1>
      
      <div class="toolbar">
        <button class="secondary small" onclick="toggleBatchMode()" title="Switch to batch mode">📝 Batch</button>
        <button class="secondary small" onclick="showHelp()" title="Show keyboard shortcuts">⌨️ Help</button>
      </div>
      
      <textarea id="text" placeholder="Type your text here... (Ctrl+Enter to speak, Escape to stop)" ondrop="handleDrop(event)" ondragover="event.preventDefault()" ondragenter="event.preventDefault()"></textarea>
      <div class="counter">
        <span id="char-count">0</span> characters | <span id="word-count">0</span> words | <span id="read-time">~0 sec</span> read
      </div>
      
      <div class="mobile-actions-bar">
        <button class="primary" type="button" onclick="onSpeak()">▶️ Speak</button>
        <button class="secondary" type="button" onclick="onStop()">⏹️ Stop</button>
      </div>
      
      <div class="row">
        <div>
          <label for="voice">Voice</label>
          <select id="voice"></select>
          <div id="voice-preview" style="margin-top:6px;"></div>
        </div>
        <div>
          <label for="output_device">Output Device</label>
          <select id="output_device"></select>
        </div>
      </div>
      
      <div class="row">
        <div>
          <label for="speed">Speed <span id="speed_val">1.0</span></label>
          <input type="range" id="speed" min="0.6" max="1.6" step="0.05">
        </div>
        <div>
          <label for="noise">Noise <span id="noise_val">0.5</span></label>
          <input type="range" id="noise" min="0.0" max="1.0" step="0.05">
        </div>
        <div>
          <label for="volume">Volume <span id="volume_val">100</span>%</label>
          <input type="range" id="volume" min="0" max="100" step="5" value="100">
        </div>
      </div>
      
      <div class="row">
        <div>
          <label for="noise_w">Clarity <span id="noise_w_val">0.5</span></label>
          <input type="range" id="noise_w" min="0.0" max="1.0" step="0.05">
        </div>
        <div>
          <label for="sentence_silence">Silence <span id="sentence_silence_val">0.0</span></label>
          <input type="range" id="sentence_silence" min="0.0" max="2.0" step="0.1">
        </div>
      </div>
      
      <div class="field-inline">
        <label><input type="checkbox" id="mute"> Mute</label>
        <label><input type="checkbox" id="autoClear"> Auto-clear</label>
        <label><input type="checkbox" id="cleanup"> Clean text</label>
        <label><input type="checkbox" id="enterToSpeak"> Enter to speak</label>
        <span id="remote_info" style="color:var(--text-muted); font-size:0.85rem;"></span>
      </div>
      
      <div class="controls">
        <button class="primary" onclick="onSpeak()">▶️ Speak</button>
        <button class="secondary" onclick="onStop()">⏹️ Stop</button>
        <button class="secondary" onclick="onClear()">✕ Clear</button>
        <button class="secondary" onclick="saveSettings()">💾 Save</button>
        <button class="danger" onclick="onShutdown()">🔴 Shutdown</button>
      </div>
      
      <div class="status" id="status">Loading...</div>
    </div>
  </div>
</div>

<div id="help-modal" class="modal">
  <div class="modal-content">
    <span class="modal-close" onclick="closeHelp()">&times;</span>
    <h2>Keyboard Shortcuts</h2>
    <div class="shortcut-list">
      <div class="shortcut">
        <div class="shortcut-key">Ctrl+Enter</div>
        <div>Speak text</div>
      </div>
      <div class="shortcut">
        <div class="shortcut-key">Escape</div>
        <div>Stop speaking</div>
      </div>
      <div class="shortcut">
        <div class="shortcut-key">Ctrl+L</div>
        <div>Clear text</div>
      </div>
      <div class="shortcut">
        <div class="shortcut-key">Ctrl+B</div>
        <div>Toggle batch mode</div>
      </div>
    </div>
  </div>
</div>

<script>
const q = id => document.getElementById(id);
const setStatus = msg => q('status').textContent = msg;
let allHistory = [];

const toggleSection = (id) => q(id).classList.toggle('open');
const toggleSidebar = () => {
  q('sidebar').classList.toggle('open');
  q('sidebar-overlay').classList.toggle('open');
  document.body.classList.toggle('sidebar-open');
};
const closeSidebar = () => {
  q('sidebar').classList.remove('open');
  q('sidebar-overlay').classList.remove('open');
  document.body.classList.remove('sidebar-open');
};
const toggleTheme = () => {
  document.body.classList.toggle('light-mode');
  localStorage.setItem('theme', document.body.classList.contains('light-mode') ? 'light' : 'dark');
};
const toggleBatchMode = () => {
  q('text').classList.toggle('batch-mode');
  q('text').placeholder = q('text').classList.contains('batch-mode') ? 
    'Enter multiple lines to speak sequentially...' : 
    'Type your text here...';
};
const showHelp = () => q('help-modal').classList.add('open');
const closeHelp = () => q('help-modal').classList.remove('open');

const handleDrop = (e) => {
  e.preventDefault();
  const files = e.dataTransfer.files;
  if (files.length > 0) {
    const reader = new FileReader();
    reader.onload = (event) => q('text').value = event.target.result;
    reader.readAsText(files[0]);
    setStatus('File loaded');
  }
};

const updateCounter = () => {
  const text = q('text').value;
  const chars = text.length;
  const words = text.trim().split(/\\s+/).filter(w => w.length > 0).length;
  const readTime = Math.ceil(words / 150 * 60);
  q('char-count').textContent = chars;
  q('word-count').textContent = words;
  q('read-time').textContent = '~' + readTime;
};

const cleanupText = (text) => {
  return text
    .replace(/\\s+/g, ' ')
    .replace(/([.!?])\\s+([A-Z])/g, '$1 $2')
    .trim();
};

const loadState = async () => {
  const savedTheme = localStorage.getItem('theme');
  if (savedTheme === 'light') document.body.classList.add('light-mode');
  q('enterToSpeak').checked = localStorage.getItem('enterToSpeak') === 'true';
  
  try {
    const res = await fetch('/api/status');
    const body = await res.json();
    const settings = body.settings;
    const voices = body.voices;
    const sinks = body.sinks;

    q('voice').innerHTML = voices.map(v => `<option value="${v}">${v}</option>`).join('');
    if (settings.voice) q('voice').value = settings.voice;

    q('output_device').innerHTML = sinks.map(s => `<option value="${s}">${s}</option>`).join('');
    if (settings.output_device) q('output_device').value = settings.output_device;

    q('speed').value = settings.speed ?? 1.0;
    q('noise').value = settings.noise ?? 0.5;
    q('noise_w').value = settings.noise_w ?? 0.5;
    q('sentence_silence').value = settings.sentence_silence ?? 0.0;
    q('mute').checked = settings.mute ?? false;
    q('volume').value = localStorage.getItem('volume') || 100;

    ['speed', 'noise', 'noise_w', 'sentence_silence', 'volume'].forEach(id => updateLabel(id));
    q('remote_info').textContent = `${body.local_ip}:${body.port}`;

    await loadHistory();
    await loadFavorites();
    await loadPresets();
    await loadRecents();
    setStatus('Ready');
  } catch (e) {
    setStatus('Error loading state');
  }
};

const loadHistory = async () => {
  try {
    const res = await fetch('/api/history');
    const data = await res.json();
    allHistory = data.history;
    renderHistory(allHistory);
  } catch (e) {
    console.error('Failed to load history', e);
  }
};

const renderHistory = (items) => {
  const list = q('history-list');
  list.innerHTML = items.slice().reverse().map(item => `
    <div class="item">
      <span class="item-text" title="${item.text}">${item.text}</span>
      <div class="item-actions">
        <button class="item-btn" onclick="insertHistoryText('${item.text.replace(/'/g, "\\'")}')" title="Use">↗</button>
      </div>
    </div>
  `).join('');
};

q('history-search').addEventListener('input', (e) => {
  const query = e.target.value.toLowerCase();
  const filtered = allHistory.filter(item => item.text.toLowerCase().includes(query));
  renderHistory(filtered);
});

const loadFavorites = async () => {
  try {
    const res = await fetch('/api/favorites');
    const data = await res.json();
    const list = q('favorites-list');
    list.innerHTML = Object.entries(data.favorites).map(([name, text]) => `
      <div class="item">
        <span class="item-text" title="${name}: ${text}">${name}</span>
        <div class="item-actions">
          <button class="item-btn" onclick="insertHistoryText('${text.replace(/'/g, "\\'")}')" title="Use">↗</button>
          <button class="item-btn" onclick="removeFavorite('${name.replace(/'/g, "\\\\'")}')" title="Delete">✕</button>
        </div>
      </div>
    `).join('');
  } catch (e) {
    console.error('Failed to load favorites', e);
  }
};

const loadPresets = async () => {
  try {
    const res = await fetch('/api/presets');
    const data = await res.json();
    const list = q('presets-list');
    list.innerHTML = Object.entries(data.presets).map(([name, preset]) => `
      <div class="item">
        <span class="item-text" title="${name}">${name}</span>
        <div class="item-actions">
          <button class="item-btn" onclick="loadPreset('${name}')" title="Load">↗</button>
          <button class="item-btn" onclick="deletePreset('${name}')" title="Delete">✕</button>
        </div>
      </div>
    `).join('');
  } catch (e) {
    console.error('Failed to load presets', e);
  }
};

const loadRecents = async () => {
  try {
    const res = await fetch('/api/recents');
    const data = await res.json();
    
    q('recent-voices').innerHTML = data.voices.map(v => `
      <button class="recent-btn" onclick="setVoice('${v}')">${v}</button>
    `).join('');
    
    q('recent-devices').innerHTML = data.devices.map(d => `
      <button class="recent-btn" onclick="setDevice('${d}')">${d}</button>
    `).join('');
  } catch (e) {
    console.error('Failed to load recents', e);
  }
};

const updateLabel = id => {
  const el = q(`${id}_val`);
  if (el) el.textContent = id === 'volume' ? q(id).value : q(id).value;
};

['speed','noise','noise_w','sentence_silence','volume'].forEach(id => {
  q(id).addEventListener('input', () => {
    updateLabel(id);
    if (id === 'volume') localStorage.setItem('volume', q(id).value);
  });
});

q('text').addEventListener('input', updateCounter);
q('enterToSpeak').addEventListener('change', () => {
  localStorage.setItem('enterToSpeak', q('enterToSpeak').checked ? 'true' : 'false');
});

const readSettings = () => ({
  voice: q('voice').value,
  output_device: q('output_device').value,
  speed: q('speed').value,
  noise: q('noise').value,
  noise_w: q('noise_w').value,
  sentence_silence: q('sentence_silence').value,
  mute: q('mute').checked,
});

const insertText = (text) => {
  q('text').value = text;
  q('text').focus();
  updateCounter();
  if (window.innerWidth <= 768) closeSidebar();
};
const insertHistoryText = (text) => insertText(text);
const setVoice = (v) => {
  q('voice').value = v;
  updateSettings();
  if (window.innerWidth <= 768) closeSidebar();
};
const setDevice = (d) => {
  q('output_device').value = d;
  updateSettings();
  if (window.innerWidth <= 768) closeSidebar();
};

const onSpeak = async () => {
  let text = q('text').value.trim();
  if (!text) { setStatus('Enter text before speaking'); return; }
  if (q('cleanup').checked) text = cleanupText(text);
  
  const isBatch = q('text').classList.contains('batch-mode');
  if (isBatch) {
    const lines = text.split('\\n').filter(l => l.trim());
    for (const line of lines) {
      const body = {...readSettings(), text: line};
      await fetch('/api/speak', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body),
      });
      await new Promise(r => setTimeout(r, 500));
    }
    setStatus('Batch complete');
  } else {
    const body = {...readSettings(), text};
    await fetch('/api/speak', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body),
    });
    setStatus('Speaking...');
  }
  if (q('autoClear').checked) setTimeout(() => { q('text').value = ''; updateCounter(); }, 100);
};

const onStop = async () => {
  await fetch('/api/stop', { method: 'POST' });
  setStatus('Stopped');
};

const onClear = () => { q('text').value = ''; q('text').focus(); updateCounter(); setStatus('Text cleared'); };

const saveFavorite = async () => {
  const text = q('text').value.trim();
  if (!text) { setStatus('Enter text to save'); return; }
  const name = prompt('Favorite name:', '');
  if (!name) return;
  const res = await fetch('/api/favorite/add', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({name, text}),
  });
  if (res.ok) { setStatus('Favorite saved'); loadFavorites(); } 
  else setStatus('Failed to save favorite');
};

const removeFavorite = async (name) => {
  if (!confirm('Remove this favorite?')) return;
  const res = await fetch('/api/favorite/remove', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({name}),
  });
  if (res.ok) { setStatus('Favorite removed'); loadFavorites(); }
};

const savePreset = async () => {
  const name = prompt('Preset name:', '');
  if (!name) return;
  const res = await fetch('/api/preset/save', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({name, ...readSettings()}),
  });
  if (res.ok) { setStatus('Preset saved'); loadPresets(); }
};

const loadPreset = async (name) => {
  const res = await fetch('/api/preset/load', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({name}),
  });
  if (res.ok) {
    const data = await res.json();
    q('voice').value = data.preset.voice;
    q('speed').value = data.preset.speed;
    q('noise').value = data.preset.noise;
    q('noise_w').value = data.preset.noise_w;
    q('sentence_silence').value = data.preset.sentence_silence;
    ['speed', 'noise', 'noise_w', 'sentence_silence'].forEach(updateLabel);
    setStatus('Preset loaded');
  }
};

const deletePreset = async (name) => {
  if (!confirm('Delete this preset?')) return;
  const res = await fetch('/api/preset/delete', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({name}),
  });
  if (res.ok) { setStatus('Preset deleted'); loadPresets(); }
};

const clearHistory = async () => {
  if (!confirm('Clear all history?')) return;
  const res = await fetch('/api/history/clear', {method: 'POST'});
  if (res.ok) { setStatus('History cleared'); loadHistory(); }
};

const saveSettings = async () => {
  const res = await fetch('/api/settings', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(readSettings()),
  });
  setStatus(res.ok ? 'Settings saved' : 'Failed to save');
};

const updateSettings = async () => {
  await fetch('/api/settings', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(readSettings()),
  });
};

const onShutdown = async () => {
  if (!confirm('Shutdown server?')) return;
  await fetch('/api/shutdown', { method: 'POST' });
  setStatus('Server shutting down...');
};

window.addEventListener('DOMContentLoaded', () => {
  loadState();
  updateCounter();
  
  q('text').addEventListener('keydown', event => {
    if (
      event.key === 'Enter' &&
      q('enterToSpeak').checked &&
      !event.shiftKey &&
      !event.ctrlKey &&
      !event.metaKey &&
      !event.altKey
    ) {
      event.preventDefault();
      onSpeak();
      return;
    }

    if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
      event.preventDefault();
      onSpeak();
    }
  });

  window.addEventListener('keydown', event => {
    if (event.key === 'Escape') { event.preventDefault(); onStop(); }
    if ((event.ctrlKey || event.metaKey) && event.key === 'l') { event.preventDefault(); onClear(); }
    if ((event.ctrlKey || event.metaKey) && event.key === 'b') { event.preventDefault(); toggleBatchMode(); }
  });

  window.addEventListener('resize', () => {
    if (window.innerWidth > 768) closeSidebar();
  });
});
</script>
</body>
</html>"""

    def start(self):
        if self.server:
            return False

        handler = lambda *args, **kwargs: BrowserRequestHandler(*args, app=self, **kwargs)
        self.server = socketserver.ThreadingTCPServer(("", self.port), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return True

    def stop_server(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
            self.thread = None

    def run(self):
        if not self.start():
            print(f"Failed to start browser control on port {self.port}")
            return

        url = f"http://127.0.0.1:{self.port}"
        print(f"Browser control started → {url}")
        try:
            webbrowser.open(url)
        except Exception:
            pass
        try:
            self.thread.join()
        except KeyboardInterrupt:
            pass
        finally:
            self.stop_server()


def main(port: int = 8080):
    app = BrowserApp(port=port)
    app.run()


if __name__ == "__main__":
    main()
