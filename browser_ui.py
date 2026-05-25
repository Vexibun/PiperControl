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
  body { margin: 0; min-height: 100vh; display: flex; justify-content: center; align-items: flex-start; background: #121212; color: #eee; font-family: Inter, Arial, sans-serif; }
  .container { width: min(980px, 100%); padding: 24px; }
  h1 { margin-bottom: 16px; font-size: 1.9rem; }
  .card { background: #1e1e1e; border: 1px solid #333; border-radius: 18px; padding: 20px; box-shadow: 0 16px 60px rgba(0,0,0,0.3); }
  textarea { width: 100%; min-height: 200px; border: 1px solid #333; background: #111; color: #fff; padding: 16px; border-radius: 14px; resize: vertical; font-size: 1rem; line-height: 1.6; }
  .row { display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); margin-top: 18px; }
  label { display: block; margin-bottom: 6px; color: #bbb; font-size: 0.95rem; }
  select, input[type="range"], input[type="number"] { width: 100%; border-radius: 12px; background: #222; color: #fff; border: 1px solid #333; padding: 10px 12px; }
  .actions { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 20px; }
  button { border: none; border-radius: 12px; padding: 14px 22px; font-size: 1rem; cursor: pointer; transition: transform .15s ease, background .15s ease; }
  button:hover { transform: translateY(-1px); }
  .primary { background: #4f8cff; color: #fff; }
  .secondary { background: #2d2d2d; color: #ddd; }
  .danger { background: #e34d5a; color: #fff; }
  .status { margin-top: 14px; font-size: 0.95rem; color: #8fa; }
  .field-inline { display: grid; gap: 12px; grid-template-columns: auto 1fr; align-items: center; }
  .field-inline span { font-size: 0.95rem; color: #ccc; }
</style>
</head>
<body>
<div class="container">
  <div class="card">
    <h1>Piper Browser Control</h1>
    <textarea id="text" placeholder="Type your text here..."></textarea>
    <div class="row">
      <div>
        <label for="voice">Voice</label>
        <select id="voice"></select>
      </div>
      <div>
        <label for="output_device">Output device</label>
        <select id="output_device"></select>
      </div>
    </div>
    <div class="row">
      <div>
        <label for="speed">Speed <span id="speed_val"></span></label>
        <input type="range" id="speed" min="0.6" max="1.6" step="0.05">
      </div>
      <div>
        <label for="noise">Noise <span id="noise_val"></span></label>
        <input type="range" id="noise" min="0.0" max="1.0" step="0.05">
      </div>
    </div>
    <div class="row">
      <div>
        <label for="noise_w">Clarity <span id="noise_w_val"></span></label>
        <input type="range" id="noise_w" min="0.0" max="1.0" step="0.05">
      </div>
      <div>
        <label for="sentence_silence">Silence <span id="sentence_silence_val"></span></label>
        <input type="range" id="sentence_silence" min="0.0" max="2.0" step="0.1">
      </div>
    </div>
    <div class="field-inline">
      <label for="mute"><input type="checkbox" id="mute"> Mute</label>
      <span id="remote_info"></span>
    </div>
    <div class="actions">
      <button class="primary" onclick="onSpeak()">Speak</button>
      <button class="secondary" onclick="onStop()">Stop</button>
      <button class="secondary" onclick="onClear()">Clear</button>
      <button class="danger" onclick="saveSettings()">Save settings</button>
      <button class="danger" onclick="onShutdown()">Shutdown server</button>
    </div>
    <div class="status" id="status"></div>
  </div>
</div>
<script>
const setStatus = msg => document.getElementById('status').textContent = msg;
const query = selector => document.getElementById(selector);

const loadState = async () => {
  const res = await fetch('/api/status');
  const body = await res.json();
  const settings = body.settings;
  const voices = body.voices;
  const sinks = body.sinks;

  const voiceSelect = query('voice');
  voiceSelect.innerHTML = voices.map(v => `<option value="${v}">${v}</option>`).join('');
  if (settings.voice) voiceSelect.value = settings.voice;

  const deviceSelect = query('output_device');
  deviceSelect.innerHTML = sinks.map(s => `<option value="${s}">${s}</option>`).join('');
  if (settings.output_device) deviceSelect.value = settings.output_device;

  query('speed').value = settings.speed ?? 1.0;
  query('noise').value = settings.noise ?? 0.5;
  query('noise_w').value = settings.noise_w ?? 0.5;
  query('sentence_silence').value = settings.sentence_silence ?? 0.0;
  query('mute').checked = settings.mute ?? false;

  ['speed', 'noise', 'noise_w', 'sentence_silence'].forEach(id => updateLabel(id));

  query('remote_info').textContent = `Server running at ${body.local_ip}:${body.port}`;
  setStatus('Ready');
};

const updateLabel = id => query(`${id}_val`).textContent = query(id).value;
['speed','noise','noise_w','sentence_silence'].forEach(id => {
  query(id).addEventListener('input', () => updateLabel(id));
});

const readSettings = () => ({
  voice: query('voice').value,
  output_device: query('output_device').value,
  speed: query('speed').value,
  noise: query('noise').value,
  noise_w: query('noise_w').value,
  sentence_silence: query('sentence_silence').value,
  mute: query('mute').checked,
});

const onSpeak = async () => {
  const text = query('text').value.trim();
  if (!text) { setStatus('Enter text before speaking.'); return; }
  const body = {...readSettings(), text};
  await fetch('/api/speak', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body),
  });
  setStatus('Speaking...');
};

const onStop = async () => {
  await fetch('/api/stop', { method: 'POST' });
  setStatus('Stopped');
};

const onClear = () => { query('text').value = ''; setStatus('Text cleared'); };

const saveSettings = async () => {
  await fetch('/api/settings', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(readSettings()),
  });
  setStatus('Settings saved');
};

const onShutdown = async () => {
  await fetch('/api/shutdown', { method: 'POST' });
  setStatus('Server is shutting down');
};

window.addEventListener('DOMContentLoaded', () => {
  loadState();
  const textarea = query('text');
  textarea.addEventListener('keydown', event => {
    if (event.key === 'Enter' && !event.shiftKey && !event.ctrlKey && !event.altKey && !event.metaKey) {
      event.preventDefault();
      onSpeak();
    }
  });

  window.addEventListener('keydown', event => {
    if (event.key === 'F1') {
      event.preventDefault();
      onSpeak();
    }
    if (event.key === 'Escape') {
      event.preventDefault();
      onStop();
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
