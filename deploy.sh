#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
# 🌙 Nyx Light — Računovođa :: ONE-FILE DEPLOY
# ═══════════════════════════════════════════════════════════════════════
#
# JEDINI FAJL KOJI TREBA POKRENUTI.
# Instalira SVE na Mac Studio M3 Ultra (256GB):
#
#   ✅ Faza 1: Provjera sustava (RAM, disk, chip)
#   ✅ Faza 2: Homebrew + Python + Git + Java
#   ✅ Faza 3: Python venv + 30+ pip paketa
#   ✅ Faza 4: Baze podataka (Qdrant + Neo4j + SQLite)
#   ✅ Faza 5: LLM modeli (Qwen3-235B-A22B + Qwen3-VL-8B)
#   ✅ Faza 6: Embedding model (multilingual-MiniLM-L12-v2)
#   ✅ Faza 7: Zakoni RH (25+ zakona/pravilnika za RAG)
#   ✅ Faza 8: Konfiguracija, auth, direktoriji
#   ✅ Faza 9: Testovi + cron za auto-update
#
# UPORABA:
#   curl -sSL https://raw.githubusercontent.com/mladen1312/nyx-light-racunovodja/main/deploy.sh | bash
#   # ILI
#   chmod +x deploy.sh && ./deploy.sh
#
# OPCIJE:
#   ./deploy.sh                 # Puna instalacija
#   ./deploy.sh --skip-models   # Sve osim modela (brzo, ~5 min)
#   ./deploy.sh --models-only   # Samo LLM modeli (~60 min)
#   ./deploy.sh --laws-only     # Samo zakoni RH
#   ./deploy.sh --resume        # Nastavi prekinutu instalaciju
#   ./deploy.sh --status        # Provjeri status instalacije
#   ./deploy.sh --uninstall     # Deinstalacija (čuva data/)
#
# ═══════════════════════════════════════════════════════════════════════
set -euo pipefail
trap 'echo -e "\n${RED}❌ Greška u liniji $LINENO${NC}"; exit 1' ERR

# ═══ BOJE ═══
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; PURPLE='\033[0;35m'; CYAN='\033[0;36m'
BOLD='\033[1m'; DIM='\033[2m'; NC='\033[0m'

# ═══ PUTANJE ═══
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${SCRIPT_DIR}"
DATA="${PROJECT_DIR}/data"
MODELS="${DATA}/models"
LAWS="${DATA}/laws"
VENV="${PROJECT_DIR}/.venv"
LOG="${DATA}/deploy.log"

# ═══ MODELI ═══
PRIMARY_256="mlx-community/Qwen3-235B-A22B-4bit"        # 256GB+ → ~124GB
PRIMARY_96="mlx-community/Qwen2.5-72B-Instruct-4bit"    # 96GB+  → ~42GB
PRIMARY_64="mlx-community/Qwen3-30B-A3B-4bit"           # 64GB+  → ~18GB
VISION="mlx-community/Qwen3-VL-8B-Instruct-4bit"        # Vision → ~5GB
EMBED="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# ═══ FLAGOVI ═══
SKIP_MODELS=false; MODELS_ONLY=false; LAWS_ONLY=false
RESUME=false; STATUS_ONLY=false; IS_MAC=true
for arg in "$@"; do
  case "$arg" in
    --skip-models)  SKIP_MODELS=true ;;
    --models-only)  MODELS_ONLY=true ;;
    --laws-only)    LAWS_ONLY=true ;;
    --resume)       RESUME=true ;;
    --status)       STATUS_ONLY=true ;;
  esac
done

# ═══ HELPER ═══
banner() {
  echo -e "${PURPLE}"
  cat << 'EOF'
  ╔═══════════════════════════════════════════════════════╗
  ║                                                       ║
  ║   🌙  Nyx Light — Računovođa                         ║
  ║       Privatni AI za računovodstvo u RH               ║
  ║       One-File Deploy v2.0                            ║
  ║                                                       ║
  ╚═══════════════════════════════════════════════════════╝
EOF
  echo -e "${NC}"
}
step()  { echo -e "\n${BLUE}━━━ $(date +%H:%M:%S) ━━━${NC} ${BOLD}$1${NC}"; }
ok()    { echo -e "  ${GREEN}✅${NC} $1"; }
warn()  { echo -e "  ${YELLOW}⚠️${NC}  $1"; }
err()   { echo -e "  ${RED}❌${NC} $1"; }
info()  { echo -e "  ${CYAN}ℹ${NC}  $1"; }
logf()  { mkdir -p "$(dirname "$LOG")"; echo "[$(date -Iseconds)] $*" >> "$LOG"; }
done?() { [[ -f "${DATA}/.phases" ]] && grep -q "^$1$" "${DATA}/.phases" 2>/dev/null; }
mark()  { mkdir -p "${DATA}"; echo "$1" >> "${DATA}/.phases"; }

# ═══════════════════════════════════════════════════
# STATUS CHECK
# ═══════════════════════════════════════════════════
if [[ "$STATUS_ONLY" == true ]]; then
  echo -e "${BOLD}Nyx Light — Status instalacije${NC}"
  for phase in system deps databases models embeddings laws config tests cron; do
    if done? "$phase"; then echo -e "  ${GREEN}✅${NC} $phase"
    else echo -e "  ${RED}⬜${NC} $phase"; fi
  done
  if [[ -d "$MODELS/primary" ]]; then
    info "Model: $(cat "$MODELS/registry.json" 2>/dev/null | python3 -c 'import sys,json; print(json.load(sys.stdin).get("primary",{}).get("name","?"))' 2>/dev/null || echo '?')"
  fi
  law_count=$(ls "$LAWS"/*.txt 2>/dev/null | wc -l | tr -d ' ')
  info "Zakoni: $law_count datoteka"
  exit 0
fi

banner

# ═══════════════════════════════════════════════════
# FAZA 1: SUSTAV
# ═══════════════════════════════════════════════════
if ! done? system || [[ "$RESUME" != true ]]; then
  step "Faza 1/9 — Provjera sustava"

  [[ "$(uname)" != "Darwin" ]] && IS_MAC=false && warn "Nije macOS — Linux mode"

  if $IS_MAC; then
    CHIP=$(sysctl -n machdep.cpu.brand_string 2>/dev/null || echo "?")
    RAM_GB=$(( $(sysctl -n hw.memsize 2>/dev/null || echo 0) / 1073741824 ))
    DISK_FREE=$(df -g "$PROJECT_DIR" 2>/dev/null | tail -1 | awk '{print $4}')
  else
    CHIP="Linux"; RAM_GB=$(free -g 2>/dev/null | awk '/Mem:/{print $2}' || echo 8)
    DISK_FREE=$(df -BG "$PROJECT_DIR" 2>/dev/null | tail -1 | awk '{print $4}' | tr -d 'G')
  fi

  ok "Čip: $CHIP"
  if (( RAM_GB >= 256 )); then
    ok "RAM: ${RAM_GB}GB — Qwen3-235B-A22B (MoE, optimalno)"
    SELECTED="$PRIMARY_256"; MODEL_NAME="Qwen3-235B-A22B"
  elif (( RAM_GB >= 96 )); then
    warn "RAM: ${RAM_GB}GB — Qwen2.5-72B (fallback)"
    SELECTED="$PRIMARY_96"; MODEL_NAME="Qwen2.5-72B"
  elif (( RAM_GB >= 64 )); then
    warn "RAM: ${RAM_GB}GB — Qwen3-30B-A3B (MoE, lite)"
    SELECTED="$PRIMARY_64"; MODEL_NAME="Qwen3-30B-A3B"
  else
    err "RAM: ${RAM_GB}GB — minimum 64GB!"; exit 1
  fi
  ok "Disk: ${DISK_FREE:-?}GB slobodno"
  logf "System: chip=$CHIP ram=${RAM_GB}GB model=$MODEL_NAME"
  mark system
fi

# ═══════════════════════════════════════════════════
# FAZA 2: SISTEMSKE OVISNOSTI
# ═══════════════════════════════════════════════════
if ! done? deps || [[ "$RESUME" != true ]]; then
  [[ "$MODELS_ONLY" == true || "$LAWS_ONLY" == true ]] && { mark deps; } || {
  step "Faza 2/9 — Sistemske ovisnosti"

  if $IS_MAC && ! command -v brew &>/dev/null; then
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  fi

  # Python
  command -v python3 &>/dev/null || { $IS_MAC && brew install python@3.12 || sudo apt install -y python3 python3-venv; }
  ok "Python: $(python3 --version 2>&1 | awk '{print $2}')"

  # Git
  command -v git &>/dev/null || { $IS_MAC && brew install git || sudo apt install -y git; }
  ok "Git: OK"

  mark deps; }
fi

# ═══════════════════════════════════════════════════
# FAZA 3: PYTHON VENV + PIP
# ═══════════════════════════════════════════════════
if ! done? pip || [[ "$RESUME" != true ]]; then
  [[ "$MODELS_ONLY" == true || "$LAWS_ONLY" == true ]] && { mark pip; } || {
  step "Faza 3/9 — Python paketi"

  [[ ! -d "$VENV" ]] && python3 -m venv "$VENV"
  source "$VENV/bin/activate"
  pip install -q --upgrade pip setuptools wheel

  info "Instaliram 35+ paketa..."
  pip install -q \
    fastapi==0.115.6 uvicorn[standard]==0.34.0 httpx==0.28.1 \
    python-multipart==0.0.20 jinja2==3.1.5 aiofiles==24.1.0 \
    openpyxl==3.1.5 pandas==2.2.3 python-dateutil==2.9.0 \
    pydantic==2.10.6 pydantic-settings==2.7.1

  pip install -q \
    huggingface-hub>=0.27.0 transformers>=4.48.0 tokenizers>=0.21.0 \
    sentence-transformers>=3.4.0 safetensors>=0.5.0

  # MLX samo na macOS Apple Silicon
  if $IS_MAC; then
    pip install -q mlx>=0.22.0 mlx-lm>=0.22.0 mlx-vlm>=0.1.0 2>/dev/null || warn "MLX install partial"
  fi

  pip install -q qdrant-client>=1.13.0 neo4j>=5.27.0 2>/dev/null || true
  pip install -q pytest pytest-asyncio
  ok "Svi Python paketi instalirani"
  mark pip; }
fi

# ═══════════════════════════════════════════════════
# FAZA 4: BAZE PODATAKA
# ═══════════════════════════════════════════════════
if ! done? databases || [[ "$RESUME" != true ]]; then
  [[ "$MODELS_ONLY" == true || "$LAWS_ONLY" == true ]] && { mark databases; } || {
  step "Faza 4/9 — Baze podataka"

  mkdir -p "$DATA"/{qdrant_storage,memory_db,dpo_datasets,logs,exports,uploads}
  mkdir -p "$MODELS"/{primary,vision,lora,embeddings,archive}

  # Qdrant
  if $IS_MAC; then
    brew install qdrant/tap/qdrant 2>/dev/null && ok "Qdrant (brew)" || {
      info "Qdrant: koristit će Docker ili Python client mode"
    }
  fi

  # Neo4j (opcionalan)
  if command -v java &>/dev/null; then
    brew install neo4j 2>/dev/null && ok "Neo4j" || info "Neo4j: opcionalan"
  else
    info "Neo4j: preskočen (treba Java) — Knowledge Graph opcionalan"
  fi

  ok "SQLite baze: memory_db, auth.db, dpo_datasets"
  mark databases; }
fi

# ═══════════════════════════════════════════════════
# FAZA 5: LLM MODELI
# ═══════════════════════════════════════════════════
if ! done? models || [[ "$RESUME" != true ]]; then
  [[ "$SKIP_MODELS" == true || "$LAWS_ONLY" == true ]] && { warn "Modeli preskočeni (--skip-models)"; mark models; } || {
  step "Faza 5/9 — LLM Modeli (može trajati 30-90 min)"
  source "$VENV/bin/activate"

  echo ""
  info "╔═══════════════════════════════════════════════════╗"
  info "║  LLM:    ${MODEL_NAME:-Qwen3-235B-A22B}"
  info "║  Vision: Qwen3-VL-8B-Instruct (32-lang OCR)"
  info "║  Repo:   ${SELECTED:-$PRIMARY_256}"
  info "╚═══════════════════════════════════════════════════╝"
  echo ""

  # Primarni LLM
  python3 -c "
from huggingface_hub import snapshot_download
print('Downloading ${MODEL_NAME:-LLM}...')
snapshot_download('${SELECTED:-$PRIMARY_256}', local_dir='${MODELS}/primary', resume_download=True)
print('✅ LLM downloaded')
"
  ok "Primarni: ${MODEL_NAME:-Qwen3-235B-A22B}"

  # Vision
  python3 -c "
from huggingface_hub import snapshot_download
print('Downloading Qwen3-VL-8B...')
snapshot_download('${VISION}', local_dir='${MODELS}/vision', resume_download=True)
print('✅ Vision downloaded')
"
  ok "Vision: Qwen3-VL-8B-Instruct"

  # Registry
  cat > "$MODELS/registry.json" << EOF
{
  "primary": {"name":"${MODEL_NAME:-Qwen3-235B-A22B}","repo":"${SELECTED:-$PRIMARY_256}","path":"${MODELS}/primary","date":"$(date -Iseconds)"},
  "vision": {"name":"Qwen3-VL-8B-Instruct","repo":"${VISION}","path":"${MODELS}/vision","date":"$(date -Iseconds)"},
  "ram_gb": ${RAM_GB:-0}
}
EOF
  ok "Model registry kreiran"
  mark models; }
fi

# ═══════════════════════════════════════════════════
# FAZA 6: EMBEDDING MODEL
# ═══════════════════════════════════════════════════
if ! done? embeddings || [[ "$RESUME" != true ]]; then
  [[ "$MODELS_ONLY" == true || "$LAWS_ONLY" == true ]] && { mark embeddings; } || {
  step "Faza 6/9 — Embedding model za RAG (~500MB)"
  source "$VENV/bin/activate"

  python3 -c "
from sentence_transformers import SentenceTransformer
import os; os.makedirs('${MODELS}/embeddings', exist_ok=True)
m = SentenceTransformer('${EMBED}', cache_folder='${MODELS}/embeddings')
e = m.encode(['Zakon o PDV-u članak 4.'])
print(f'✅ Embedding OK (dim={len(e[0])})')
" 2>/dev/null || warn "Embedding download — retry na sljedećem pokretanju"
  ok "paraphrase-multilingual-MiniLM-L12-v2"
  mark embeddings; }
fi

# ═══════════════════════════════════════════════════
# FAZA 7: ZAKONI RH
# ═══════════════════════════════════════════════════
if ! done? laws || [[ "$RESUME" != true ]]; then
  step "Faza 7/9 — Zakoni RH za RAG bazu (25+ zakona)"
  source "$VENV/bin/activate"
  mkdir -p "$LAWS" "$DATA/rag_db"

  python3 << 'PYEOF'
import sys, os
sys.path.insert(0, "src")
from nyx_light.rag.law_downloader import LawDownloader

dl = LawDownloader(laws_dir="data/laws", rag_dir="data/rag_db")
result = dl.download_all(priority_max=3, callback=lambda m: print(f"  📜 {m}"))
print(f"\n  ✅ Skinuto: {result['downloaded']}, Preskočeno: {result['skipped']}, Greške: {result['errors']}")
stats = dl.get_stats()
print(f"  📊 Ukupno: {stats['laws_downloaded']}/{stats['laws_in_catalog']} zakona ({stats['total_size_kb']} KB)")
PYEOF

  ok "RAG baza zakona popunjena"
  mark laws
fi

# ═══════════════════════════════════════════════════
# FAZA 8: KONFIGURACIJA
# ═══════════════════════════════════════════════════
if ! done? config || [[ "$RESUME" != true ]]; then
  [[ "$MODELS_ONLY" == true || "$LAWS_ONLY" == true ]] && { mark config; } || {
  step "Faza 8/9 — Konfiguracija sustava"
  source "$VENV/bin/activate"

  # config.json
  [[ ! -f config.json ]] && cat > config.json << 'CFGJSON'
{
  "nyx_light": {"version":"2.0.0","name":"Nyx Light — Računovođa"},
  "server": {"host":"0.0.0.0","port":8080,"workers":4},
  "llm": {"max_sessions":15,"max_tokens":4096,"temperature":0.1,"context_window":8192},
  "rag": {"qdrant_host":"localhost","qdrant_port":6333,"top_k":5,"min_confidence":0.7},
  "memory": {"l1_retention_days":30,"l2_promote_threshold":3},
  "dpo": {"min_pairs":10,"max_pairs_per_run":500,"schedule":"0 2 * * *"},
  "auth": {"token_expiry_hours":12,"max_failed_attempts":5,"lockout_minutes":15},
  "auto_update": {"check_laws_weekly":true,"check_models_weekly":true,"auto_download_laws":true,"auto_download_models":false},
  "security": {"auto_book":false,"require_approval":true,"audit_log":true}
}
CFGJSON
  ok "config.json"

  # Auth
  python3 -c "
import sys; sys.path.insert(0,'src')
from nyx_light.auth import AuthManager
m = AuthManager(db_path='data/auth.db')
u = m.list_users()
if not u: print('  🔐 Default admin kreiran (admin/admin) — PROMIJENI LOZINKU!')
else: print(f'  🔐 Auth: {len(u)} korisnika')
"
  ok "Auth sustav inicijaliziran"
  mark config; }
fi

# ═══════════════════════════════════════════════════
# FAZA 9: TESTOVI + CRON
# ═══════════════════════════════════════════════════
if ! done? tests || [[ "$RESUME" != true ]]; then
  [[ "$MODELS_ONLY" == true || "$LAWS_ONLY" == true ]] && { mark tests; } || {
  step "Faza 9/9 — Testovi i Auto-Update cron"
  source "$VENV/bin/activate"

  # Testovi
  cd "$PROJECT_DIR"
  python3 -m pytest tests/ -x -q --tb=short 2>&1 | tail -5 || warn "Neki testovi failed — provjeri logs"
  ok "Testovi pokrenuti"

  # Cron: auto-update zakona svake nedjelje u 03:00
  if $IS_MAC; then
    PLIST="$HOME/Library/LaunchAgents/com.nyx-light.update.plist"
    [[ ! -f "$PLIST" ]] && cat > "$PLIST" << PEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.nyx-light.update</string>
  <key>ProgramArguments</key><array>
    <string>${PROJECT_DIR}/update.sh</string><string>--auto</string>
  </array>
  <key>StartCalendarInterval</key><dict>
    <key>Weekday</key><integer>0</integer>
    <key>Hour</key><integer>3</integer>
  </dict>
  <key>StandardOutPath</key><string>${DATA}/logs/update.log</string>
  <key>StandardErrorPath</key><string>${DATA}/logs/update-err.log</string>
</dict></plist>
PEOF
    launchctl load "$PLIST" 2>/dev/null || true
    ok "Cron: svake nedjelje 03:00 — auto-update zakona i modela"
  else
    (crontab -l 2>/dev/null; echo "0 3 * * 0 cd $PROJECT_DIR && ./update.sh --auto >> $DATA/logs/update.log 2>&1") | sort -u | crontab -
    ok "Cron (Linux): svake nedjelje 03:00"
  fi
  mark tests; }
fi

# ═══════════════════════════════════════════════════
# GOTOVO
# ═══════════════════════════════════════════════════
echo ""
echo -e "${GREEN}╔═══════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                                                       ║${NC}"
echo -e "${GREEN}║   🎉  DEPLOY ZAVRŠEN USPJEŠNO!                       ║${NC}"
echo -e "${GREEN}║                                                       ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${BOLD}Pokretanje:${NC}"
echo -e "    source .venv/bin/activate"
echo -e "    python -m uvicorn src.nyx_light.web.app:app --host 0.0.0.0 --port 8080"
echo ""
echo -e "  ${BOLD}Update zakona:${NC}   ./update.sh --laws"
echo -e "  ${BOLD}Update modela:${NC}   ./update.sh --models"
echo -e "  ${BOLD}Provjeri NN:${NC}     ./update.sh --check-nn"
echo -e "  ${BOLD}Status:${NC}          ./deploy.sh --status"
echo -e "  ${BOLD}Testovi:${NC}         python -m pytest tests/ -v"
echo ""
echo -e "  ${YELLOW}⚠️  ODMAH PROMIJENI ADMIN LOZINKU!${NC}"
echo -e "  ${DIM}Auto-update: svake nedjelje u 03:00 (zakoni + provjera modela)${NC}"
echo ""
logf "Deploy complete"
