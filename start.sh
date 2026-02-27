#!/usr/bin/env bash
set -e
echo "🌙 Nyx Light — Računovođa — Start"

# Activate venv if exists
if [[ -f "venv/bin/activate" ]]; then source venv/bin/activate; fi

# Create data dirs
for d in data/{memory_db,rag_db,dpo_datasets,models/lora,laws,exports,backups,logs,incoming_laws,uploads,prompt_cache}; do mkdir -p "$d"; done

# Read config
PORT=${NYX_PORT:-7860}
HOST=${NYX_HOST:-0.0.0.0}

# Start vLLM-MLX server in background (if MLX available)
if command -v mlx_lm.server &>/dev/null && [[ -f config.json ]]; then
    MODEL=$(python3 -c "import json;print(json.load(open('config.json')).get('model','none'))" 2>/dev/null || echo "none")
    if [[ "$MODEL" != "none" ]]; then
        VLLM_PORT=$(python3 -c "import json;print(json.load(open('config.json')).get('vllm_port',8080))" 2>/dev/null || echo 8080)
        echo "🤖 Starting vLLM-MLX: $MODEL on port $VLLM_PORT"
        nohup mlx_lm.server --model "$MODEL" --port "$VLLM_PORT" --max-concurrency 15 > data/logs/vllm.log 2>&1 &
        echo $! > data/logs/vllm.pid
        echo "   PID: $(cat data/logs/vllm.pid)"
    fi
fi

# Apple Silicon optimizations
export MLX_METAL_FAST_SYNCH=1
export MLX_METAL_PREALLOCATE=true
export TOKENIZERS_PARALLELISM=false
export MALLOC_NANO_ZONE=0

# Start FastAPI server
echo "🌐 Starting web server on $HOST:$PORT"
echo "   http://localhost:$PORT"
python -m uvicorn nyx_light.api.app:app --host "$HOST" --port "$PORT" --workers 1 --log-level info &
echo $! > data/logs/web.pid
echo "   PID: $(cat data/logs/web.pid)"

echo ""
echo "✅ Nyx Light pokrenut!"
echo "   Web:  http://localhost:$PORT"
echo "   Login: admin / admin123"
echo ""
echo "Za zaustavljanje: ./stop.sh"

# Wait for both processes
wait
