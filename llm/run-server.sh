#!/bin/bash
# Ollama server run script (local voice loop: parakeet :5092 -> Ollama :11434 -> tts-local)
# Model: llama3.2:3b (~2GB, `ollama pull llama3.2:3b`)
set -e
# Prefer the systemd unit when installed (native reboot trigger); fall back to
# a direct start otherwise.
UNIT=voice-loop-ollama
if [ -f /etc/systemd/system/$UNIT.service ] && command -v systemctl >/dev/null 2>&1; then
  systemctl enable --now $UNIT >/dev/null 2>&1 || true
  if systemctl is-active --quiet $UNIT; then echo "ollama running via systemd ($UNIT)"; exit 0; fi
  echo "WARNING: systemd unit $UNIT not active — falling back to direct start"
fi
export TMPDIR="${TMPDIR:-$HOME/.tmp}"
mkdir -p "$TMPDIR"
if curl -s --max-time 3 http://localhost:11434/api/tags > /dev/null 2>&1; then
  echo "ollama already running on :11434"
  exit 0
fi
nohup ollama serve > "$HOME/.ollama-serve.log" 2>&1 &
echo "ollama started (pid $!), log: $HOME/.ollama-serve.log"
for i in $(seq 1 30); do
  if curl -s --max-time 2 http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "healthy after ~$((i * 2))s"
    exit 0
  fi
  sleep 2
done
echo "WARNING: not healthy after 60s — check $HOME/.ollama-serve.log"
exit 1
