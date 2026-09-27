# Local Voice Loop

A fully local voice loop: **parakeet** hears, **llama** thinks,
**supertonic** speaks. Hold-to-talk web UI, zero cloud, nothing leaves
the machine.

```
mic → parakeet STT (:5092) → Ollama llama3.2:3b (:11434)
    → tts-local (Supertonic F1) → speaker
```

## Pieces

| Dir | What |
|---|---|
| `stt/` | parakeet STT server runner (port 5092) |
| `llm/` | Ollama server runner (port 11434) |
| `talk/` | `talk.html` hold-to-talk UI + `talk-server.py` (stdlib proxy for the three stages, port 8090) |
| `systemd/` | boot-persistent units for all three (replace `/home/hatch` with your home before installing) |
| `voice-loop.sh` | one-command launcher: starts/verifies everything |

## Setup

Binaries and model weights are **not** bundled (hundreds of MB). Fetch them once:

```bash
# --- STT: parakeet server + ONNX Runtime + int8 models ---
cd stt
curl -sL -o parakeet https://github.com/achetronic/parakeet/releases/latest/download/parakeet-linux-amd64 && chmod +x parakeet
curl -sL -o onnxruntime.tgz https://github.com/microsoft/onnxruntime/releases/download/v1.25.1/onnxruntime-linux-x64-1.25.1.tgz
tar --no-same-owner -xzf onnxruntime.tgz          # root must pass --no-same-owner
mkdir -p models && cd models
for f in config.json vocab.txt nemo128.onnx decoder_joint-model.int8.onnx encoder-model.int8.onnx; do
  curl -sL -o "$f" "https://huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx/resolve/main/$f"
done
# Silero VAD (chunk boundaries for long audio) — raw tag path, the release-asset URL 404s:
curl -sL -o silero_vad.onnx https://github.com/snakers4/silero-vad/raw/v6.2.1/src/silero_vad/data/silero_vad.onnx
cd ..

# --- LLM: Ollama + llama3.2:3b (~2GB) ---
ollama pull llama3.2:3b

# --- TTS: a local tts-local CLI accepting --text/--out ---
# We use Supertonic F1 (MIT weights) behind a small CLI; any compatible
# engine works. Set TTS_LOCAL=/path/to/your-tts if it's not on PATH.

# --- launch ---
./voice-loop.sh
# talk page: http://127.0.0.1:8090/  (local only — see Findings)
```

Optional — boot persistence:

```bash
# replace /home/hatch with your home in each unit file first
sudo cp systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now voice-loop-parakeet voice-loop-ollama talk-server
```

`talk-server.py` is stdlib-only and proxies all three stages on one
origin (no CORS): `GET /` → UI, `GET /health` → backend dots,
`POST /api/stt|chat|tts` → the pipeline. `TTS_LOCAL` env var overrides
the TTS binary.

## Findings

- **Parakeet pilot verdict: VIABLE.** int8 `parakeet-tdt-0.6b-v3` +
  ONNX Runtime 1.25.1, no build step. Measured: 1.03 GB RSS with
  `-workers 1` (README claims ~2GB, likely assumes 4 workers), 6s of
  audio transcribed in ~2.9s (~2x realtime), model load ~13s. Test
  clip (synthetic speech): every word correct, diffs were punctuation
  and casing only, 3/3 identical.
- **Parakeet API quirks (measured):** `verbose_json` inflates duration
  ~2.7x (6s file reported as 16.4s) — don't trust duration/end fields;
  whisper-compat fields (`tokens`, `avg_logprob`, `temperature`) are
  placeholders; ffmpeg auto-detected for non-WAV uploads.
- **Silero VAD is a chunk-boundary oracle, not a pre-filter** (read from
  the server source): it only loads with `-long-audio`, and then
  over-limit audio gets chunked instead of rejected. Transcript was
  byte-identical before/after wiring it in.
- **Tunnel quest: four dead ends.** This network only allows proxied
  HTTP(S) egress. cloudflared ignores proxy env vars entirely;
  localtunnel hangs; pinggy's server never answers; ngrok's proxy
  support is a paid feature. Result: the talk page stays local-only
  (`127.0.0.1:8090`). The working remote path is a chat voice note run
  through the same loop — zero new infrastructure. proxly (MIT,
  self-hosted ngrok alternative) is the standing choice if a VPS +
  domain ever exists, but it's parked until then.
- **Split the concerns:** each stage is its own process with its own
  runner and unit; the talk server never embeds model paths — it talks
  HTTP to STT/LLM and shells out to TTS. Swapping any engine is a
  one-line change.
- **Keep the UI dumb:** the browser captures 16kHz mono WAV and posts
  it; all intelligence lives server-side. The whole page is one file,
  no build step.

## End result

- Full round-trip demoed: spoken question → transcription → llama
  answer → spoken reply as audio, all on the box.
- Two systemd units enabled at boot (`Restart=always`); hourly
  watchdog reinstalls them if the system dir gets wiped.
- Talk page built and verified rendering at `127.0.0.1:8090`.
- Tunnel quest closed after four failed tools — documented above so
  nobody re-spends tokens on it.

## Licenses

Glue code in this repo: **MIT** (see [LICENSE](LICENSE)).
Third-party pieces keep their own: parakeet server code MIT, NVIDIA
Parakeet TDT 0.6B weights CC-BY-4.0, Silero VAD MIT, Supertonic
weights MIT, Ollama under its own license.
