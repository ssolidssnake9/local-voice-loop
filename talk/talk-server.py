#!/usr/bin/env python3
"""Talk page server for the local voice loop.

Serves talk.html and proxies the three loop stages on the same origin
(no CORS headaches):
  GET  /          -> talk.html
  GET  /health    -> {"parakeet": bool, "ollama": bool}
  POST /api/stt   -> wav bytes in, {"text": ...} out (parakeet :5092)
  POST /api/chat  -> {"text": ...} in, {"reply": ...} out (ollama :11434)
  POST /api/tts   -> {"text": ...} in, wav bytes out (tts-local)

Stdlib only. Run: python3 talk-server.py  (listens on 127.0.0.1:8090)
"""
import http.server
import json
import os
import subprocess
import tempfile
import urllib.request

HOST, PORT = "127.0.0.1", 8090
PARAKEET = "http://localhost:5092"
OLLAMA = "http://localhost:11434"
# Local TTS CLI: must accept `--text "..." --out out.wav`.
# Env override: TTS_LOCAL=/path/to/tts-local
TTS = os.environ.get("TTS_LOCAL", "tts-local")
HERE = os.path.dirname(os.path.abspath(__file__))
SYSTEM_PROMPT = (
    "You are Hellboy, a friendly voice assistant. Keep every reply to 1-3 "
    "short sentences in plain spoken language. No lists, no markdown, no emoji."
)


def http_post(url, body, ctype, timeout=180):
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": ctype}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def stt_transcribe(wav_bytes):
    boundary = "----voice-loop-boundary"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="speech.wav"\r\n'
        "Content-Type: audio/wav\r\n\r\n"
    ).encode() + wav_bytes + (
        f"\r\n--{boundary}\r\n"
        'Content-Disposition: form-data; name="language"\r\n\r\nen\r\n'
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="response_format"\r\n\r\njson\r\n'
        f"--{boundary}--\r\n"
    ).encode()
    raw = http_post(PARAKEET + "/v1/audio/transcriptions", body,
                    f"multipart/form-data; boundary={boundary}", timeout=120)
    return json.loads(raw).get("text", "")


def chat_reply(text):
    payload = json.dumps({
        "model": "llama3.2:3b",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        "stream": False,
        "options": {"num_predict": 150},
    }).encode()
    raw = http_post(OLLAMA + "/api/chat", payload, "application/json",
                    timeout=180)
    return json.loads(raw)["message"]["content"]


def tts_speak(text):
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    try:
        subprocess.run([TTS, "--text", text[:1200], "--out", tmp.name],
                       check=True, timeout=300,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with open(tmp.name, "rb") as f:
            return f.read()
    finally:
        os.unlink(tmp.name)


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # keep the log quiet; errors still surface via 500s

    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, "application/json", json.dumps(obj).encode())

    def _read_body(self):
        return self.rfile.read(int(self.headers.get("Content-Length", 0)))

    def do_GET(self):
        if self.path == "/":
            with open(os.path.join(HERE, "talk.html"), "rb") as f:
                self._send(200, "text/html; charset=utf-8", f.read())
        elif self.path == "/health":
            ok = {"parakeet": False, "ollama": False}
            try:
                urllib.request.urlopen(PARAKEET + "/health", timeout=3)
                ok["parakeet"] = True
            except Exception:
                pass
            try:
                urllib.request.urlopen(OLLAMA + "/api/tags", timeout=3)
                ok["ollama"] = True
            except Exception:
                pass
            self._json(ok)
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        try:
            if self.path == "/api/stt":
                text = stt_transcribe(self._read_body())
                self._json({"text": text})
            elif self.path == "/api/chat":
                text = json.loads(self._read_body()).get("text", "")
                self._json({"reply": chat_reply(text)})
            elif self.path == "/api/tts":
                text = json.loads(self._read_body()).get("text", "")
                self._send(200, "audio/wav", tts_speak(text))
            else:
                self._json({"error": "not found"}, 404)
        except Exception as e:  # noqa: BLE001 - surface backend errors as 500s
            self._json({"error": str(e)}, 500)


if __name__ == "__main__":
    srv = http.server.ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"talk page: http://{HOST}:{PORT}/", flush=True)
    srv.serve_forever()
