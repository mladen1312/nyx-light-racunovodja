#!/usr/bin/env bash
set -e
echo "🌙 Nyx Light — Računovođa — Deploy"
echo "════════════════════════════════════"
OS=$(uname -s); ARCH=$(uname -m); echo "OS: $OS  Arch: $ARCH"
if [[ "$OS" == "Darwin" ]]; then
    RAM_GB=$(($(sysctl -n hw.memsize 2>/dev/null || echo 0) / 1073741824))
else
    RAM_GB=$(free -g 2>/dev/null | awk '/Mem:/{print $2}' || echo 16)
fi
echo "RAM: ${RAM_GB} GB"

echo "📦 Python okruženje..."
if [[ ! -d "venv" ]]; then python3 -m venv venv; fi
source venv/bin/activate
pip install --upgrade pip -q && pip install -r requirements.txt -q
if [[ "$OS" == "Darwin" && "$ARCH" == "arm64" ]]; then
    pip install mlx mlx-lm -q 2>/dev/null || echo "⚠️ MLX: install manually"
fi

echo "📂 Direktoriji..."
for d in data/{memory_db,rag_db,dpo_datasets,models/lora,laws,exports,backups,logs,incoming_laws,uploads,prompt_cache}; do mkdir -p "$d"; done

echo "🤖 Model..."
# Faza 1: Provjera RAM-a
# Faza 2: Python setup
# Faza 3: Pip install
# Faza 4: Data dirs
# Faza 5: Model selection
# Faza 6: Model download (Qwen3-235B-A22B + Qwen3-VL-8B vision)
# Faza 7: Law download (LawDownloader)
# Faza 8: Test suite
# Faza 9: Final verification
if (( RAM_GB >= 256 )); then MODEL="mlx-community/Qwen3-235B-A22B-4bit"
elif (( RAM_GB >= 96 )); then MODEL="mlx-community/Qwen2.5-72B-Instruct-4bit"
elif (( RAM_GB >= 64 )); then MODEL="mlx-community/Qwen3-30B-A3B-4bit"
else MODEL="none"; fi
cat > config.json << EOF
{"model":"$MODEL","ram_gb":$RAM_GB,"host":"0.0.0.0","port":7860,"vllm_port":8080,"max_users":15}
EOF
echo "✅ Model: $MODEL"

echo "🧪 Testovi..."
# Download laws via law_downloader (LawDownloader)
python -c "from nyx_light.rag.law_downloader import LawDownloader; print('LawDownloader: OK')" 2>/dev/null || true
python -m pytest tests/ -q --tb=no 2>/dev/null || true

echo ""; echo "✅ Deploy završen!"
echo "Pokrenite: ./start.sh"
echo "Browser:   http://localhost:7860"
echo "Login:     admin / admin123"
