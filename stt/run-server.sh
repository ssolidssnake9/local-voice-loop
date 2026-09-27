#!/bin/bash
# Parakeet STT server run script (local voice loop: parakeet :5092 -> Ollama -> tts-local)
# Models: istupakov/parakeet-tdt-0.6b-v3-onnx (int8) + Silero VAD v6.2.1 (chunk boundaries)
set -e
# Prefer the systemd unit when installed (native reboot trigger); fall back to
# a direct start otherwise.
UNIT=voice-loop-parakeet
if [ -f /etc/systemd/system/$UNIT.service ] && command -v systemctl >/dev/null 2>&1; then
  systemctl enable --now $UNIT >/dev/null 2>&1 || true
  if systemctl is-active --quiet $UNIT; then echo "parakeet running via systemd ($UNIT)"; exit 0; fi
  echo "WARNING: systemd unit $UNIT not active — falling back to direct start"
fi
DIR="$(cd "$(dirname "$0")" && pwd)"
export ONNXRUNTIME_LIB="$DIR/onnxruntime-linux-x64-1.25.1/lib/libonnxruntime.so"
export TMPDIR="${TMPDIR:-$HOME/.tmp}"
mkdir -p "$TMPDIR"
if curl -s --max-time 3 http://localhost:5092/health | grep -q '"ok"'; then
  echo "parakeet already running on :5092"
  exit 0
fi
cd "$DIR"
nohup ./parakeet -port 5092 -models ./models -workers 1 -long-audio > server.log 2>&1 &
echo "parakeet started (pid $!), log: $DIR/server.log"
for i in $(seq 1 30); do
  if curl -s --max-time 2 http://localhost:5092/health | grep -q '"ok"'; then
    echo "healthy after ~$((i * 2))s"
    exit 0
  fi
  sleep 2
done
echo "WARNING: not healthy after 60s — check server.log"
exit 1
