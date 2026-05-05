import http.server
import socketserver
import threading
import socket
from urllib.parse import parse_qs


class TTSRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, tts_callback=None, stop_callback=None, **kwargs):
        self.tts_callback = tts_callback
        self.stop_callback = stop_callback
        super().__init__(*args, **kwargs)

    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            
            html = """
            <!DOCTYPE html>
            <html>
            <head><meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Piper Remote</title>
            <style>
                body { font-family: Arial; margin: 20px; background: #1e1e1e; color: #ddd; }
                textarea { width: 100%; height: 180px; padding: 12px; background: #333; color: #fff; border: none; border-radius: 8px; font-size: 16px; }
                button { padding: 14px 28px; font-size: 18px; margin: 8px 4px; border: none; border-radius: 8px; }
                .speak { background: #0066ff; color: white; }
                .stop { background: #ff4444; color: white; }
            </style>
            </head>
            <body>
                <h2>Piper TTS Remote</h2>
                <textarea id="text" placeholder="Write your text here..."></textarea><br>
                <button class="speak" onclick="speak()">Speak</button>
                <button class="stop" onclick="stopTTS()">Stop</button>

                <script>
                function speak() {
                    const text = document.getElementById('text').value.trim();
                    if (!text) return;
                    fetch('/speak', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                        body: 'text=' + encodeURIComponent(text)
                    });
                    document.getElementById('text').value = '';
                }

                function stopTTS() {
                    fetch('/stop', { method: 'POST' });
                }
                </script>
            </body>
            </html>
            """
            self.wfile.write(html.encode())

    def do_POST(self):
        if self.path == '/speak' and self.tts_callback:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length).decode()
            text = parse_qs(post_data).get('text', [''])[0]
            if text.strip():
                self.tts_callback(text.strip())

        elif self.path == '/stop' and self.stop_callback:
            self.stop_callback()

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"


class WebControl:
    def __init__(self, tts_callback, stop_callback):
        self.tts_callback = tts_callback
        self.stop_callback = stop_callback
        self.server = None
        self.thread = None
        self.port = 8080

    def get_local_ip(self):
        return get_local_ip()

    def start(self):
        if self.server:
            return False

        handler = lambda *args, **kwargs: TTSRequestHandler(*args, 
                                                            tts_callback=self.tts_callback, 
                                                            stop_callback=self.stop_callback, 
                                                            **kwargs)
        
        try:
            self.server = socketserver.TCPServer(("", self.port), handler)
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
            print(f"🌐 Phone Control started → http://{self.get_local_ip()}:{self.port}")
            return True
        except Exception as e:
            print(f"Failed to start: {e}")
            return False

    def stop(self):
        if self.server:
            try:
                self.server.shutdown()
                self.server.server_close()
            except:
                pass
            self.server = None
            print("Phone Control stopped")