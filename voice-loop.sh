#!/bin/bash
# Voice loop launcher: parakeet STT (:5092) + Ollama LLM (:11434) + tts-local.
# One command to bring the whole local voice loop up (or verify it's up).
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
"$HERE/stt/run-server.sh"
"$HERE/llm/run-server.sh"
echo "---"
curl -s --max-time 3 http://localhost:5092/health
echo
ollama list 2>/dev/null | head -4 || true
echo "voice loop up: stt :5092, llm :11434, tts via tts-local (on PATH)"
