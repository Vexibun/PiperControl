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

    def update_settings(self, data: dict):
        if "voice" in data:
            self.settings["voice"] = data["voice"]
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
<title>Piper Browser Control</title>
<style>
  * { box-sizing: border-box; }
  body { margin: 0; min-height: 100vh; display: flex; background: #121212; color: #eee; font-family: Inter, Arial, sans-serif; }
  
  .sidebar { width: 280px; background: #1a1a1a; border-right: 1px solid #333; overflow-y: auto; height: 100vh; position: fixed; left: 0; top: 0; }
  .main { flex: 1; margin-left: 280px; display: flex; justify-content: center; align-items: flex-start; padding: 24px; }
  
  .sidebar-section { border-bottom: 1px solid #333; padding: 16px; }
  .sidebar-title { font-weight: 600; font-size: 0.95rem; color: #4f8cff; margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center; cursor: pointer; user-select: none; }
  .sidebar-title:hover { color: #6fa3ff; }
  .toggle-btn { font-size: 0.8rem; color: #888; }
  .sidebar-content { display: none; max-height: 300px; overflow-y: auto; }
  .sidebar-content.open { display: block; }
  
  .history-item, .favorite-item { padding: 10px 12px; background: #222; border-radius: 8px; margin-bottom: 8px; font-size: 0.9rem; cursor: pointer; transition: background .15s; display: flex; justify-content: space-between; align-items: center; }
  .history-item:hover { background: #2d2d2d; }
  .favorite-item:hover { background: #2d2d2d; }
  .item-text { flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .item-actions { display: flex; gap: 6px; }
  .item-btn { background: none; border: none; color: #888; cursor: pointer; font-size: 0.8rem; padding: 0; }
  .item-btn:hover { color: #bbb; }
  
  .container { width: min(900px, 100%); }
  h1 { margin: 0 0 20px 0; font-size: 1.8rem; }
  .card { background: #1e1e1e; border: 1px solid #333; border-radius: 18px; padding: 24px; box-shadow: 0 16px 60px rgba(0,0,0,0.3); }
  
  textarea { width: 100%; min-height: 200px; border: 1px solid #333; background: #111; color: #fff; padding: 16px; border-radius: 12px; resize: vertical; font-size: 1rem; line-height: 1.6; }
  
  .row { display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); margin-top: 18px; }
  label { display: block; margin-bottom: 6px; color: #bbb; font-size: 0.9rem; }
  select, input[type="range"], input[type="number"], input[type="text"] { width: 100%; border-radius: 10px; background: #222; color: #fff; border: 1px solid #333; padding: 10px 12px; }
  
  .actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 20px; }
  button { border: none; border-radius: 10px; padding: 12px 18px; font-size: 0.95rem; cursor: pointer; transition: transform .15s ease, background .15s ease; }
  button:hover { transform: translateY(-1px); }
  .primary { background: #4f8cff; color: #fff; }
  .secondary { background: #2d2d2d; color: #ddd; }
  .danger { background: #e34d5a; color: #fff; }
  .small { padding: 8px 12px; font-size: 0.85rem; }
  
  .status { margin-top: 12px; font-size: 0.9rem; color: #8fa; }
  .field-inline { display: flex; gap: 12px; align-items: center; margin-top: 12px; }
  .field-inline span { font-size: 0.9rem; color: #999; }
  
  @media (max-width: 768px) {
    .sidebar { width: 0; }
    .main { margin-left: 0; }
  }
</style>
</head>
<body>
<div class="sidebar">
  <div class="sidebar-section">
    <div class="sidebar-title" onclick="toggleSection('history')">
      📋 History <span class="toggle-btn">▼</span>
    </div>
    <div id="history" class="sidebar-content open">
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
      <button class="secondary small" style="width:100%; margin-top:8px;" onclick="saveFavorite()">Save as Favorite</button>
    </div>
  </div>
</div>

<div class="main">
  <div class="container">
    <div class="card">
      <h1>Piper TTS</h1>
      <textarea id="text" placeholder="Type your text here... (Ctrl+Enter to speak, Escape to stop)"></textarea>
      
      <div class="row">
        <div>
          <label for="voice">Voice</label>
          <select id="voice"></select>
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
        <label><input type="checkbox" id="mute"> Mute Output</label>
        <label><input type="checkbox" id="autoClear"> Auto-clear</label>
        <span id="remote_info"></span>
      </div>
      
      <div class="actions">
        <button class="primary" onclick="onSpeak()">Speak</button>
        <button class="secondary" onclick="onStop()">Stop</button>
        <button class="secondary" onclick="onClear()">Clear</button>
        <button class="secondary" onclick="saveSettings()">Save Settings</button>
        <button class="danger" onclick="onShutdown()">Shutdown</button>
      </div>
      
      <div class="status" id="status">Loading...</div>
    </div>
  </div>
</div>

<script>
const q = id => document.getElementById(id);
const setStatus = msg => q('status').textContent = msg;

const toggleSection = (id) => {
  const section = q(id);
  section.classList.toggle('open');
};

const loadState = async () => {
  try {
    const res = await fetch('/api/status');
    const body = await res.json();
    const settings = body.settings;
    const voices = body.voices;
    const sinks = body.sinks;

    const voiceSelect = q('voice');
    voiceSelect.innerHTML = voices.map(v => `<option value="${v}">${v}</option>`).join('');
    if (settings.voice) voiceSelect.value = settings.voice;

    const deviceSelect = q('output_device');
    deviceSelect.innerHTML = sinks.map(s => `<option value="${s}">${s}</option>`).join('');
    if (settings.output_device) deviceSelect.value = settings.output_device;

    q('speed').value = settings.speed ?? 1.0;
    q('noise').value = settings.noise ?? 0.5;
    q('noise_w').value = settings.noise_w ?? 0.5;
    q('sentence_silence').value = settings.sentence_silence ?? 0.0;
    q('mute').checked = settings.mute ?? false;

    ['speed', 'noise', 'noise_w', 'sentence_silence'].forEach(id => updateLabel(id));
    q('remote_info').textContent = `${body.local_ip}:${body.port}`;

    await loadHistory();
    await loadFavorites();
    setStatus('Ready');
  } catch (e) {
    setStatus('Error loading state');
  }
};

const loadHistory = async () => {
  try {
    const res = await fetch('/api/history');
    const data = await res.json();
    const list = q('history-list');
    list.innerHTML = data.history.slice().reverse().map((item, i) => `
      <div class="history-item">
        <span class="item-text" title="${item.text}">${item.text}</span>
        <div class="item-actions">
          <button class="item-btn" onclick="insertText('${item.text.replace(/'/g, "\\'")}')" title="Use">↗</button>
        </div>
      </div>
    `).join('');
  } catch (e) {
    console.error('Failed to load history', e);
  }
};

const loadFavorites = async () => {
  try {
    const res = await fetch('/api/favorites');
    const data = await res.json();
    const list = q('favorites-list');
    list.innerHTML = Object.entries(data.favorites).map(([name, text]) => `
      <div class="favorite-item">
        <span class="item-text" title="${name}: ${text}">${name}</span>
        <div class="item-actions">
          <button class="item-btn" onclick="insertText('${text.replace(/'/g, "\\'")}')" title="Use">↗</button>
          <button class="item-btn" onclick="removeFavorite('${name.replace(/'/g, "\\'")}')" title="Delete">✕</button>
        </div>
      </div>
    `).join('');
  } catch (e) {
    console.error('Failed to load favorites', e);
  }
};

const updateLabel = id => q(`${id}_val`).textContent = q(id).value;
['speed','noise','noise_w','sentence_silence'].forEach(id => {
  q(id).addEventListener('input', () => updateLabel(id));
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
};

const onSpeak = async () => {
  const text = q('text').value.trim();
  if (!text) { setStatus('Enter text before speaking'); return; }
  const body = {...readSettings(), text};
  await fetch('/api/speak', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body),
  });
  setStatus('Speaking...');
  if (q('autoClear').checked) {
    setTimeout(() => q('text').value = '', 100);
  }
};

const onStop = async () => {
  await fetch('/api/stop', { method: 'POST' });
  setStatus('Stopped');
};

const onClear = () => {
  q('text').value = '';
  q('text').focus();
  setStatus('Text cleared');
};

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
  
  if (res.ok) {
    setStatus('Favorite saved');
    loadFavorites();
  } else {
    setStatus('Failed to save favorite');
  }
};

const removeFavorite = async (name) => {
  if (!confirm('Remove this favorite?')) return;
  
  const res = await fetch('/api/favorite/remove', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({name}),
  });
  
  if (res.ok) {
    setStatus('Favorite removed');
    loadFavorites();
  } else {
    setStatus('Failed to remove favorite');
  }
};

const clearHistory = async () => {
  if (!confirm('Clear all history?')) return;
  
  const res = await fetch('/api/history/clear', {method: 'POST'});
  if (res.ok) {
    setStatus('History cleared');
    loadHistory();
  }
};

const saveSettings = async () => {
  const res = await fetch('/api/settings', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(readSettings()),
  });
  setStatus(res.ok ? 'Settings saved' : 'Failed to save settings');
};

const onShutdown = async () => {
  if (!confirm('Shutdown server?')) return;
  await fetch('/api/shutdown', { method: 'POST' });
  setStatus('Server shutting down...');
};

window.addEventListener('DOMContentLoaded', () => {
  loadState();
  const textarea = q('text');
  textarea.addEventListener('keydown', event => {
    if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
      event.preventDefault();
      onSpeak();
    }
  });

  window.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      event.preventDefault();
      onStop();
    }
    if ((event.ctrlKey || event.metaKey) && event.key === 'l') {
      event.preventDefault();
      onClear();
    }
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
