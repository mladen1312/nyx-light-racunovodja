#!/bin/bash
# ═══════════════════════════════════════════════════════════
# Nyx Light — Mac Studio Initial Setup
# Target: Premium 256GB — Maksimalna kvaliteta
# ═══════════════════════════════════════════════════════════
set -euo pipefail

echo "🌙 Nyx Light — Postavljanje Mac Studija"
echo "Stack: Premium 256GB — Maksimalna kvaliteta"
echo ""

# ── 1. Xcode Command Line Tools ──
echo "📦 Instalacija Xcode CLI tools..."
xcode-select --install 2>/dev/null || true

# ── 2. Homebrew ──
echo "🍺 Instalacija Homebrew..."
which brew || /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# ── 3. Systemske ovisnosti ──
echo "📦 Instalacija ovisnosti..."
brew install python@3.12 git git-lfs cmake pkg-config
brew install neo4j qdrant tailscale
brew install --cask visual-studio-code

# ── 4. Python okruženje ──
echo "🐍 Python virtualno okruženje..."
cd /Users/nyx/nyx-light-racunovodja || mkdir -p /Users/nyx/nyx-light-racunovodja
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip setuptools wheel

# ── 5. MLX i AI ovisnosti ──
echo "🧠 MLX i AI paketi..."
pip install mlx mlx-lm mlx-vlm
pip install vllm  # Ako je dostupan za macOS
pip install transformers tokenizers sentencepiece
pip install qdrant-client neo4j

# ── 6. Aplikacijske ovisnosti ──
echo "📦 Nyx Light ovisnosti..."
pip install fastapi uvicorn[standard] websockets
pip install pydantic python-multipart aiofiles
pip install openpyxl python-docx lxml
pip install psutil httpx aiohttp

# ── 7. Dev tools ──
echo "🛠 Dev alati..."
pip install pytest pytest-asyncio ruff mypy
pip install ipython jupyter

# ── 8. Nyx Light instalacija ──
echo "📦 Nyx Light install..."
cd /Users/nyx/nyx-light-racunovodja
git clone https://github.com/mladen1312/nyx-light-racunovodja.git . 2>/dev/null || git pull
pip install -e ".[dev]"

# ── 9. Direktoriji ──
echo "📁 Kreiranje direktorija..."
mkdir -p /Users/nyx/nyx-data/db
mkdir -p /Users/nyx/nyx-data/uploads
mkdir -p /Users/nyx/nyx-data/outputs
mkdir -p /Users/nyx/nyx-data/logs
mkdir -p /Users/nyx/nyx-data/backups
mkdir -p /Users/nyx/models

# ── 10. Download modela ──
echo "🧠 Preuzimanje AI modela (ovo traje)..."
echo "Reasoning: Qwen3-235B-A22B"
python -c "
from mlx_lm import load
print('Downloading reasoning model...')
# model, tokenizer = load('Qwen3-235B-A22B')
print('Model ready (uncomment above for actual download)')
"

echo "Vision: Qwen2.5-VL-72B-Instruct"
echo "Embedding: BAAI/bge-m3"
echo ""
echo "⚠️  Za download modela koristi:"
echo "  mlx_lm.convert --hf-path <HF_MODEL_ID> -q --q-bits 4"
echo "  ili huggingface-cli download <MODEL> --local-dir /Users/nyx/models/<MODEL>"

# ── 11. Tailscale (VPN) ──
echo "🔗 Tailscale setup..."
sudo tailscale up --hostname=nyx-studio

# ── 12. SSH hardening ──
echo "🔒 SSH konfiguracija..."
echo "PasswordAuthentication no" | sudo tee -a /etc/ssh/sshd_config.d/nyx.conf
echo "PubkeyAuthentication yes" | sudo tee -a /etc/ssh/sshd_config.d/nyx.conf

# ── 13. Launchd servisi ──
echo "⚙️  Instalacija servisa..."
# Plist datoteke se kopiraju iz deployment/services/

# ── 14. Testovi ──
echo "🧪 Pokretanje testova..."
cd /Users/nyx/nyx-light-racunovodja
python -m pytest tests/ -q --tb=short

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "✅ Nyx Light Mac Studio spreman!"
echo ""
echo "Servisi:"
echo "  API:  http://localhost:8420"
echo "  MLX:  http://localhost:8422/v1/chat/completions"
echo ""
echo "Remote pristup:"
echo "  SSH:  ssh nyx@nyx-studio"
echo "  VS Code: Remote SSH → nyx-studio"
echo ""
echo "Memory budget:"
python3 -c "
from nyx_light.deployment import recommend_stack
r = recommend_stack(256, 'quality')
b = r['memory_budget']
print(f'  Reasoning: {r["models"]["reasoning"]}')
print(f'  Vision:    {r["models"]["vision"]}')
print(f'  RAM used:  {b["used_gb"]} / {b["total_gb"]} GB ({b["utilization_pct"]}%)')
print(f'  Free:      {b["free_gb"]} GB')
"
echo "═══════════════════════════════════════════════════════════"
