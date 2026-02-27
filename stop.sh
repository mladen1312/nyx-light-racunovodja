#!/usr/bin/env bash
echo "🌙 Nyx Light — Stop"

# Stop web server
if [[ -f data/logs/web.pid ]]; then
    PID=$(cat data/logs/web.pid)
    kill "$PID" 2>/dev/null && echo "Web server (PID $PID) zaustavljen" || echo "Web server nije bio pokrenut"
    rm -f data/logs/web.pid
fi

# Stop vLLM-MLX
if [[ -f data/logs/vllm.pid ]]; then
    PID=$(cat data/logs/vllm.pid)
    kill "$PID" 2>/dev/null && echo "vLLM-MLX (PID $PID) zaustavljen" || echo "vLLM nije bio pokrenut"
    rm -f data/logs/vllm.pid
fi

# Kill any remaining uvicorn
pkill -f "uvicorn nyx_light" 2>/dev/null || true
echo "✅ Zaustavljeno"
