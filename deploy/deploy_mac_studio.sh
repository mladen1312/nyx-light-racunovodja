#!/bin/bash
# ═══════════════════════════════════════════════════════════
# Nyx Light — Računovođa V1.3: Deploy za Mac Studio M3 Ultra
# MoE Architecture: Qwen3-235B-A22B
# ═══════════════════════════════════════════════════════════
#
# Korištenje:
#   chmod +x deploy/deploy_mac_studio.sh
#   sudo ./deploy/deploy_mac_studio.sh
#
# Hardver: Mac Studio M3 Ultra (256 GB Unified Memory)
# Model: Qwen3-235B-A22B (MoE: 235B ukupno, ~22B aktivno)
# ═══════════════════════════════════════════════════════════

set -e

echo "═══════════════════════════════════════════════════════════"
echo "  🌙 Nyx Light — Računovođa V1.3"
echo "  MoE Architecture: Qwen3-235B-A22B"
echo "  Target: Mac Studio M3 Ultra (256 GB)"
echo "═══════════════════════════════════════════════════════════"
echo ""

# Provjera root-a
if [ "$EUID" -ne 0 ]; then
    echo "❌ Pokrenite sa sudo: sudo ./deploy/deploy_mac_studio.sh"
    exit 1
fi

INSTALL_DIR="/opt/nyx-light"
LOG_DIR="/var/log/nyx-light"
VENV_DIR="$INSTALL_DIR/venv"

# ── 1. Provjera hardvera ──
echo "📌 Provjera hardvera..."
CHIP=$(sysctl -n machdep.cpu.brand_string 2>/dev/null || echo "Unknown")
MEM_BYTES=$(sysctl -n hw.memsize 2>/dev/null || echo "0")
MEM_GB=$((MEM_BYTES / 1073741824))
echo "  Čip: $CHIP"
echo "  Memorija: ${MEM_GB} GB"

if [ "$MEM_GB" -ge 256 ]; then
    echo "  ✅ 256 GB — optimalno za Qwen3-235B-A22B MoE"
    MODEL_SIZE="235B"
elif [ "$MEM_GB" -ge 192 ]; then
    echo "  ⚠️  192 GB — Qwen3-235B-A22B MoE može raditi uz agresivniji swap"
    MODEL_SIZE="235B"
elif [ "$MEM_GB" -ge 128 ]; then
    echo "  ⚠️  128 GB — koristim Qwen3-30B-A3B (manji MoE fallback)"
    MODEL_SIZE="30B"
elif [ "$MEM_GB" -ge 64 ]; then
    echo "  ⚠️  64 GB — koristim Qwen3-30B-A3B u reduciranom modu"
    MODEL_SIZE="30B"
else
    echo "  ❌ Nedovoljno memorije za produkcijski rad"
    MODEL_SIZE="30B"
fi

# ── 2. Kreiranje direktorija ──
echo ""
echo "📁 Kreiranje direktorija..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$LOG_DIR"
mkdir -p "$INSTALL_DIR/data"/{uploads,exports,models,prompt_cache,memory_db,rag_db,laws}
echo "  ✅ $INSTALL_DIR"
echo "  ✅ $LOG_DIR"

# ── 3. Kopiranje koda ──
echo ""
echo "📦 Kopiranje koda..."
cp -R . "$INSTALL_DIR/"
echo "  ✅ Kod kopiran"

# ── 4. Python venv ──
echo ""
echo "🐍 Kreiranje Python virtualnog okruženja..."
python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
pip install --upgrade pip
pip install -r "$INSTALL_DIR/requirements.txt"
echo "  ✅ Ovisnosti instalirane"

# ── 5. MLX instalacija ──
echo ""
echo "🔧 Instalacija MLX (Apple Silicon)..."
pip install mlx mlx-lm
echo "  ✅ MLX instaliran"

# ── 6. Wired Memory ──
echo ""
echo "🧠 Konfiguracija wired memory..."
WIRED_MB=$((MEM_GB * 1024 * 83 / 100))
echo "  Postavljam iogpu.wired_limit_mb=$WIRED_MB (83% od ${MEM_GB} GB)"
sysctl iogpu.wired_limit_mb=$WIRED_MB 2>/dev/null || echo "  ⚠️  iogpu.wired_limit_mb nije dostupan (potreban macOS 15+)"

# Persist across reboots
if ! grep -q "iogpu.wired_limit_mb" /etc/sysctl.conf 2>/dev/null; then
    echo "iogpu.wired_limit_mb=$WIRED_MB" >> /etc/sysctl.conf
    echo "  ✅ Wired memory persisted u /etc/sysctl.conf"
fi

# ── 7. Preuzimanje modela ──
echo ""
echo "🤖 Preuzimanje AI modela (ovo može potrajati)..."

if [ "$MODEL_SIZE" = "235B" ]; then
    echo "  Model 1: Qwen3-235B-A22B-4bit (MoE — ~70 GB na disku)"
    echo "           235B ukupno, samo ~22B aktivno u RAM-u"
    python3 -c "
from huggingface_hub import snapshot_download
try:
    snapshot_download('mlx-community/Qwen3-235B-A22B-4bit',
                      local_dir='$INSTALL_DIR/data/models/qwen3-235b-a22b-4bit',
                      local_dir_use_symlinks=False)
    print('  ✅ Qwen3-235B-A22B preuzet')
except Exception as e:
    print(f'  ⚠️  Qwen3-235B: {e}')
    print('  Ručno: huggingface-cli download mlx-community/Qwen3-235B-A22B-4bit')
" 2>/dev/null || echo "  ⚠️  Ručno preuzmite model"
else
    echo "  Model 1: Qwen3-30B-A3B-4bit (MoE fallback — ~18 GB)"
    python3 -c "
from huggingface_hub import snapshot_download
try:
    snapshot_download('mlx-community/Qwen3-30B-A3B-4bit',
                      local_dir='$INSTALL_DIR/data/models/qwen3-30b-a3b-4bit',
                      local_dir_use_symlinks=False)
    print('  ✅ Qwen3-30B-A3B preuzet')
except Exception as e:
    print(f'  ⚠️  Qwen3-30B: {e}')
" 2>/dev/null || echo "  ⚠️  Ručno preuzmite model"
fi

echo "  Model 2: Qwen3-VL-8B-Instruct-4bit (~5 GB, on-demand OCR)"
python3 -c "
from huggingface_hub import snapshot_download
try:
    snapshot_download('mlx-community/Qwen3-VL-8B-Instruct-4bit',
                      local_dir='$INSTALL_DIR/data/models/qwen3-vl-8b-4bit',
                      local_dir_use_symlinks=False)
    print('  ✅ Qwen3-VL-8B preuzet')
except Exception as e:
    print(f'  ⚠️  Qwen3-VL-8B: {e}')
" 2>/dev/null || echo "  ⚠️  Ručno preuzmite vision model"

# ── 8. Docker servisi (Qdrant + Neo4j) ──
echo ""
echo "🐳 Pokretanje Docker servisa..."
if command -v docker &>/dev/null; then
    cd "$INSTALL_DIR"
    docker compose up -d qdrant neo4j 2>/dev/null || echo "  ⚠️  Docker compose nije uspio"
    echo "  ✅ Qdrant (port 6333) i Neo4j (port 7474) pokrenuti"
else
    echo "  ⚠️  Docker nije instaliran. Instalirajte Docker Desktop za macOS."
    echo "  Qdrant i Neo4j mogu se pokrenuti naknadno: docker compose up -d"
fi

# ── 9. LaunchDaemon ──
echo ""
echo "🚀 Instalacija LaunchDaemon za auto-start..."
cp "$INSTALL_DIR/deploy/launchd/com.nexellum.nyx-light.plist" /Library/LaunchDaemons/
launchctl load /Library/LaunchDaemons/com.nexellum.nyx-light.plist 2>/dev/null || true
echo "  ✅ Nyx Light će se automatski pokretati pri boot-u"

# ── 10. vLLM-MLX Server ──
echo ""
echo "🔥 Pokretanje vLLM-MLX servera (MoE)..."

if [ "$MODEL_SIZE" = "235B" ]; then
    VLLM_MODEL="mlx-community/Qwen3-235B-A22B-4bit"
else
    VLLM_MODEL="mlx-community/Qwen3-30B-A3B-4bit"
fi

nohup "$VENV_DIR/bin/mlx_lm.server" \
    --model "$VLLM_MODEL" \
    --port 8080 \
    --host 127.0.0.1 \
    --max-concurrency 15 \
    > "$LOG_DIR/vllm.log" 2>&1 &
echo "  vLLM-MLX PID: $!"
echo "  Model: $VLLM_MODEL"
echo "  ✅ vLLM-MLX server pokrenut na portu 8080"

# ── 11. Pokretanje Nyx Light API ──
echo ""
echo "🌙 Pokretanje Nyx Light API servera..."
cd "$INSTALL_DIR"
nohup "$VENV_DIR/bin/python" -m nyx_light.main --host 0.0.0.0 --port 8000 \
    > "$LOG_DIR/nyx-light.log" 2>&1 &
echo "  Nyx Light PID: $!"
echo "  ✅ API server pokrenut na portu 8000"

# ── Završetak ──
echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  🌙 Nyx Light — Računovođa USPJEŠNO INSTALIRAN!"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "  🌐 Web sučelje:  http://$(hostname):8000"
echo "  📚 API docs:     http://$(hostname):8000/docs"
echo "  🔥 vLLM-MLX:     http://127.0.0.1:8080"
echo "  🗄️  Qdrant:       http://$(hostname):6333"
echo "  🕸️  Neo4j:        http://$(hostname):7474"
echo ""
echo "  📁 Instalacija:  $INSTALL_DIR"
echo "  📋 Logovi:       $LOG_DIR"
echo ""
echo "  15 zaposlenika se može spojiti na: http://$(hostname):8000"
echo ""
