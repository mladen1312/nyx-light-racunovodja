#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
# 🌙 Nyx Light — Računovođa :: ONE-CLICK INSTALLER
# ═══════════════════════════════════════════════════════════════════════
#
# Ovaj skript instalira SVE potrebno na Mac Studio M3 Ultra (256 GB):
#   1. Homebrew (ako nedostaje)
#   2. Python 3.12+ i alate
#   3. Python dependencies (FastAPI, Qdrant, Neo4j, itd.)
#   4. LLM Inference Engine (vllm-mlx ili mlx-lm)
#   5. AI Model (Qwen3-235B-A22B kvantiziran za 256GB RAM)
#   6. Vision model (Qwen2.5-VL-7B)
#   7. Neo4j (Knowledge Graph)
#   8. Qdrant (Vector DB za RAG)
#   9. Kreiranje direktorija i konfiguracije
#  10. Pokretanje testova
#
# UPORABA:
#   chmod +x install.sh
#   ./install.sh
#
# Za samo dependencies (bez LLM modela):
#   ./install.sh --deps-only
#
# Za samo LLM model download:
#   ./install.sh --model-only
#
# ═══════════════════════════════════════════════════════════════════════

set -euo pipefail

# ── Boje ──
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

# ── Varijable ──
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${SCRIPT_DIR}"
DATA_DIR="${PROJECT_DIR}/data"
MODEL_DIR="${DATA_DIR}/models"
VENV_DIR="${PROJECT_DIR}/.venv"

# ── LLM Model konfiguracija ──
# Primarni model: Qwen3-235B MoE (samo ~22B aktivno, stane u 256GB M3 Ultra)
PRIMARY_MODEL="Qwen/Qwen3-235B-A22B-GGUF"
PRIMARY_MODEL_FILE="qwen3-235b-a22b-q4_k_m.gguf"
# Alternativa za manje RAM-a:
ALT_MODEL="Qwen/Qwen2.5-72B-Instruct-GGUF"
ALT_MODEL_FILE="qwen2.5-72b-instruct-q4_k_m.gguf"
# Vision model:
VISION_MODEL="Qwen/Qwen2.5-VL-7B-Instruct"
# MLX optimizirani:
MLX_MODEL="mlx-community/Qwen2.5-72B-Instruct-4bit"

# ══════════════════════════════════════════
# HELPER FUNKCIJE
# ══════════════════════════════════════════

banner() {
    echo ""
    echo -e "${PURPLE}═══════════════════════════════════════════════════${NC}"
    echo -e "${PURPLE}  🌙 Nyx Light — Računovođa :: Installer${NC}"
    echo -e "${PURPLE}═══════════════════════════════════════════════════${NC}"
    echo ""
}

step() {
    echo -e "\n${BLUE}[$(date +%H:%M:%S)]${NC} ${GREEN}▶${NC} $1"
}

warn() {
    echo -e "${YELLOW}  ⚠️  $1${NC}"
}

err() {
    echo -e "${RED}  ❌ $1${NC}"
}

ok() {
    echo -e "${GREEN}  ✅ $1${NC}"
}

check_macos() {
    if [[ "$(uname)" != "Darwin" ]]; then
        warn "Ova skripta je optimizirana za macOS (Apple Silicon)."
        warn "Na Linux-u preskačem Homebrew i mlx korake."
        IS_MACOS=false
    else
        IS_MACOS=true
        # Provjeri Apple Silicon
        if [[ "$(uname -m)" == "arm64" ]]; then
            ok "Apple Silicon detektiran ($(sysctl -n machdep.cpu.brand_string 2>/dev/null || echo 'M-series'))"
            # RAM check
            RAM_GB=$(( $(sysctl -n hw.memsize 2>/dev/null || echo 0) / 1073741824 ))
            if [[ $RAM_GB -ge 256 ]]; then
                ok "RAM: ${RAM_GB}GB — dovoljno za Qwen3-235B"
            elif [[ $RAM_GB -ge 64 ]]; then
                warn "RAM: ${RAM_GB}GB — koristit ćemo Qwen2.5-72B umjesto 235B"
                PRIMARY_MODEL="${ALT_MODEL}"
                PRIMARY_MODEL_FILE="${ALT_MODEL_FILE}"
            else
                warn "RAM: ${RAM_GB}GB — koristit ćemo manji model"
            fi
        fi
    fi
}

# ══════════════════════════════════════════
# 1. HOMEBREW
# ══════════════════════════════════════════

install_xcode_clt() {
    step "Provjera Xcode Command Line Tools..."
    if xcode-select -p &>/dev/null; then
        ok "Xcode CLT već instaliran"
    else
        step "Instaliram Xcode Command Line Tools..."
        info "Pojavit će se macOS prozor — kliknite 'Install' i čekajte."
        xcode-select --install 2>/dev/null || true
        # Čekaj da se instalira (max 10 minuta)
        local max_wait=600
        local waited=0
        while ! xcode-select -p &>/dev/null && [[ $waited -lt $max_wait ]]; do
            sleep 10
            waited=$((waited + 10))
            echo -n "."
        done
        echo ""
        if xcode-select -p &>/dev/null; then
            ok "Xcode CLT instaliran"
        else
            warn "Xcode CLT instalacija nije završena — možda treba ručno"
        fi
    fi
}

install_homebrew() {
    step "Provjera Homebrew..."
    if command -v brew &>/dev/null; then
        ok "Homebrew je već instaliran"
    elif [[ "$IS_MACOS" == true ]]; then
        step "Instaliram Homebrew..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        eval "$(/opt/homebrew/bin/brew shellenv)"
        ok "Homebrew instaliran"
    fi
}

# ══════════════════════════════════════════
# 2. SYSTEM DEPENDENCIES
# ══════════════════════════════════════════

install_system_deps() {
    step "Instaliram sistemske ovisnosti..."

    if [[ "$IS_MACOS" == true ]] && command -v brew &>/dev/null; then
        brew install python@3.12 git cmake wget curl jq 2>/dev/null || true
        ok "Sistemske ovisnosti instalirane (brew)"
    elif command -v apt-get &>/dev/null; then
        sudo apt-get update -qq
        sudo apt-get install -y -qq python3.12 python3.12-venv python3-pip \
            git cmake wget curl jq build-essential 2>/dev/null || true
        ok "Sistemske ovisnosti instalirane (apt)"
    fi
}

# ══════════════════════════════════════════
# 3. PYTHON VIRTUAL ENVIRONMENT
# ══════════════════════════════════════════

setup_python() {
    step "Postavljam Python virtual environment..."

    PYTHON_BIN="python3.12"
    if ! command -v $PYTHON_BIN &>/dev/null; then
        PYTHON_BIN="python3"
    fi

    if [[ ! -d "$VENV_DIR" ]]; then
        $PYTHON_BIN -m venv "$VENV_DIR"
        ok "Kreiran venv: $VENV_DIR"
    fi

    source "$VENV_DIR/bin/activate"
    pip install --upgrade pip setuptools wheel -q
    ok "Python $(python --version) aktiviran"
}

# ══════════════════════════════════════════
# 4. PYTHON DEPENDENCIES
# ══════════════════════════════════════════

install_python_deps() {
    step "Instaliram Python dependencies..."
    source "$VENV_DIR/bin/activate"

    pip install -q \
        "fastapi>=0.115.0" \
        "uvicorn[standard]>=0.30.0" \
        "websockets>=13.0" \
        "pydantic>=2.0" \
        "aiofiles>=24.0" \
        "python-multipart>=0.0.9" \
        "openpyxl>=3.1.0" \
        "pandas>=2.2.0" \
        "python-dateutil>=2.9.0" \
        "PyPDF2>=3.0.0" \
        "Pillow>=10.0.0" \
        "httpx>=0.27.0" \
        "python-jose[cryptography]>=3.3.0" \
        "passlib[bcrypt]>=1.7.4" \
        "pytest>=8.0.0" \
        "qdrant-client>=1.12.0" \
        "neo4j>=5.25.0"

    # MLX za Apple Silicon
    if [[ "$IS_MACOS" == true ]]; then
        pip install -q "mlx>=0.21.0" "mlx-lm>=0.20.0" "mlx-vlm>=0.1.0" 2>/dev/null || \
            warn "MLX instalacija — možda trebate Xcode Command Line Tools"
    fi

    # Install sam projekt
    pip install -e "$PROJECT_DIR" -q 2>/dev/null || true

    ok "Python dependencies instalirane"
}

# ══════════════════════════════════════════
# 5. LLM MODEL DOWNLOAD
# ══════════════════════════════════════════

download_model() {
    step "Preuzimam AI model..."
    mkdir -p "$MODEL_DIR"

    if [[ "$IS_MACOS" == true ]]; then
        # MLX format — optimiziran za Apple Silicon
        step "Preuzimam MLX model: $MLX_MODEL"
        source "$VENV_DIR/bin/activate"

        python -c "
from mlx_lm import load
print('Downloading ${MLX_MODEL}...')
model, tokenizer = load('${MLX_MODEL}')
print('Model spreman!')
" 2>/dev/null && ok "MLX model preuzet: $MLX_MODEL" || {
            warn "MLX download neuspješan — pokušavam huggingface-cli"
            pip install -q huggingface-hub
            huggingface-cli download "$MLX_MODEL" --local-dir "$MODEL_DIR/primary" 2>/dev/null || \
                warn "Model download neuspješan — preuzet ćete ručno"
        }

        # Vision model
        step "Preuzimam Vision model: $VISION_MODEL"
        python -c "
from huggingface_hub import snapshot_download
snapshot_download('${VISION_MODEL}', local_dir='${MODEL_DIR}/vision')
print('Vision model spreman!')
" 2>/dev/null && ok "Vision model preuzet" || warn "Vision model — preuzmite ručno"

    else
        # Linux/non-Mac: GGUF format za llama.cpp
        pip install -q huggingface-hub
        step "Preuzimam GGUF: $PRIMARY_MODEL"
        huggingface-cli download "$PRIMARY_MODEL" "$PRIMARY_MODEL_FILE" \
            --local-dir "$MODEL_DIR/primary" 2>/dev/null || \
            warn "GGUF download — preuzmite ručno s Hugging Face"
    fi
}

# ══════════════════════════════════════════
# 6. NEO4J (Knowledge Graph)
# ══════════════════════════════════════════

install_neo4j() {
    step "Postavljam Neo4j (Knowledge Graph)..."

    if command -v neo4j &>/dev/null; then
        ok "Neo4j je već instaliran"
        return
    fi

    if [[ "$IS_MACOS" == true ]] && command -v brew &>/dev/null; then
        brew install neo4j 2>/dev/null || warn "Neo4j instalacija — pokrenite ručno"
        ok "Neo4j instaliran (brew)"
    else
        # Docker fallback
        if command -v docker &>/dev/null; then
            docker pull neo4j:5 2>/dev/null || true
            ok "Neo4j Docker image spreman"
            echo "  Pokrenite: docker run -d -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/nyx_light_2026 neo4j:5"
        else
            warn "Neo4j: instalirajte ručno s https://neo4j.com/download/"
        fi
    fi
}

# ══════════════════════════════════════════
# 7. QDRANT (Vector DB za RAG)
# ══════════════════════════════════════════

install_qdrant() {
    step "Postavljam Qdrant (Vector DB za RAG zakona)..."

    if command -v docker &>/dev/null; then
        docker pull qdrant/qdrant:latest 2>/dev/null || true
        ok "Qdrant Docker image spreman"
        echo "  Pokrenite: docker run -d -p 6333:6333 qdrant/qdrant"
    elif [[ "$IS_MACOS" == true ]] && command -v brew &>/dev/null; then
        brew install qdrant 2>/dev/null || {
            warn "Qdrant: koristite Docker ili binarne"
            echo "  curl -L https://github.com/qdrant/qdrant/releases/latest/download/qdrant-aarch64-apple-darwin.tar.gz | tar xz"
        }
    else
        warn "Qdrant: instalirajte Docker, pa pokrenite qdrant/qdrant container"
    fi
}

# ══════════════════════════════════════════
# 8. DIREKTORIJI I KONFIGURACIJA
# ══════════════════════════════════════════

setup_dirs() {
    step "Kreiram direktorije..."

    mkdir -p \
        "$DATA_DIR/memory_db" \
        "$DATA_DIR/models/primary" \
        "$DATA_DIR/models/vision" \
        "$DATA_DIR/exports/cpp" \
        "$DATA_DIR/exports/synesis" \
        "$DATA_DIR/imports/cpp" \
        "$DATA_DIR/imports/synesis" \
        "$DATA_DIR/watch/inbox" \
        "$DATA_DIR/rag_corpus" \
        "$DATA_DIR/backups" \
        "$DATA_DIR/logs" \
        "$DATA_DIR/dpo_training"

    ok "Direktoriji kreirani"
}

create_config() {
    step "Kreiram konfiguraciju..."

    CONFIG_FILE="$PROJECT_DIR/config.json"
    if [[ -f "$CONFIG_FILE" ]]; then
        warn "config.json već postoji — preskačem"
        return
    fi

    cat > "$CONFIG_FILE" << 'CONFIGEOF'
{
  "nyx_light": {
    "version": "2.0.0",
    "name": "Nyx Light — Računovođa",
    "max_sessions": 15,
    "host": "0.0.0.0",
    "port": 8080
  },
  "llm": {
    "primary_model": "mlx-community/Qwen2.5-72B-Instruct-4bit",
    "vision_model": "Qwen/Qwen2.5-VL-7B-Instruct",
    "model_dir": "data/models",
    "max_tokens": 4096,
    "temperature": 0.1
  },
  "erp": {
    "cpp": {
      "method": "file",
      "export_dir": "data/exports/cpp",
      "import_dir": "data/imports/cpp",
      "auto_book": false,
      "auto_book_min_confidence": 0.95,
      "auto_book_max_amount": 50000
    },
    "synesis": {
      "method": "file",
      "export_dir": "data/exports/synesis",
      "import_dir": "data/imports/synesis",
      "auto_book": false,
      "auto_book_min_confidence": 0.95,
      "auto_book_max_amount": 50000
    }
  },
  "rag": {
    "qdrant_url": "http://localhost:6333",
    "collection": "zakoni_rh",
    "corpus_dir": "data/rag_corpus"
  },
  "neo4j": {
    "uri": "bolt://localhost:7687",
    "user": "neo4j",
    "password": "nyx_light_2026"
  },
  "database": {
    "path": "data/memory_db/nyx_light.db"
  },
  "safety": {
    "require_human_approval": true,
    "aml_limit_eur": 10000,
    "max_auto_book_amount": 50000,
    "cloud_api_blocked": true
  },
  "watch_folders": [
    "data/watch/inbox",
    "data/imports/cpp",
    "data/imports/synesis"
  ]
}
CONFIGEOF

    ok "config.json kreiran"
}

create_env_file() {
    ENV_FILE="$PROJECT_DIR/.env"
    if [[ -f "$ENV_FILE" ]]; then
        return
    fi

    cat > "$ENV_FILE" << 'ENVEOF'
# Nyx Light — Environment
NYX_HOST=0.0.0.0
NYX_PORT=8080
NYX_DB_PATH=data/memory_db/nyx_light.db
NYX_LOG_LEVEL=INFO
NYX_MAX_SESSIONS=15
# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASS=nyx_light_2026
# Qdrant
QDRANT_URL=http://localhost:6333
ENVEOF
    ok ".env kreiran"
}

# ══════════════════════════════════════════
# 9. TESTOVI
# ══════════════════════════════════════════

run_tests() {
    step "Pokrećem testove..."
    source "$VENV_DIR/bin/activate"
    cd "$PROJECT_DIR"

    PYTHONPATH=src python -m pytest tests/ -q --tb=short 2>&1 | tail -5

    ok "Testovi završeni"
}

# ══════════════════════════════════════════
# 10. STARTUP SKRIPTE
# ══════════════════════════════════════════

create_startup_scripts() {
    step "Kreiram startup skripte..."

    # start.sh — pokreće cijeli sustav
    cat > "$PROJECT_DIR/start.sh" << 'STARTEOF'
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/.venv/bin/activate"

echo "🌙 Nyx Light — Računovođa"
echo "   Pokrećem sustav..."

# Neo4j (ako je brew)
if command -v neo4j &>/dev/null; then
    neo4j start 2>/dev/null || true
fi

# Qdrant (ako je Docker)
if command -v docker &>/dev/null; then
    docker start qdrant 2>/dev/null || \
        docker run -d --name qdrant -p 6333:6333 qdrant/qdrant 2>/dev/null || true
fi

# Web server
echo ""
echo "   🌐 http://localhost:8080"
echo "   📡 WebSocket: ws://localhost:8080/ws"
echo "   📚 API docs: http://localhost:8080/docs"
echo ""

cd "$SCRIPT_DIR"
PYTHONPATH=src python -m nyx_light.ui.web
STARTEOF
    chmod +x "$PROJECT_DIR/start.sh"

    # stop.sh
    cat > "$PROJECT_DIR/stop.sh" << 'STOPEOF'
#!/usr/bin/env bash
echo "Zaustavljam Nyx Light..."
pkill -f "nyx_light.ui.web" 2>/dev/null || true
echo "Zaustavljeno."
STOPEOF
    chmod +x "$PROJECT_DIR/stop.sh"

    ok "start.sh i stop.sh kreirani"
}

# ══════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════

main() {
    banner
    check_macos

    DEPS_ONLY=false
    MODEL_ONLY=false

    for arg in "$@"; do
        case $arg in
            --deps-only) DEPS_ONLY=true ;;
            --model-only) MODEL_ONLY=true ;;
            --help|-h)
                echo "Uporaba: ./install.sh [--deps-only|--model-only]"
                exit 0
                ;;
        esac
    done

    if [[ "$MODEL_ONLY" == true ]]; then
        download_model
        exit 0
    fi

    # Full install
    install_xcode_clt
    install_homebrew
    install_system_deps
    setup_python
    install_python_deps
    setup_dirs
    create_config
    create_env_file
    create_startup_scripts

    if [[ "$DEPS_ONLY" == false ]]; then
        install_neo4j
        install_qdrant
        download_model
    fi

    run_tests

    echo ""
    echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  ✅ INSTALACIJA ZAVRŠENA!${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "  Pokrenite sustav:  ${BLUE}./start.sh${NC}"
    echo -e "  Web sučelje:       ${BLUE}http://localhost:8080${NC}"
    echo -e "  Testovi:           ${BLUE}source .venv/bin/activate && pytest tests/${NC}"
    echo -e "  Update modela:     ${BLUE}./update.sh${NC}"
    echo -e "  Provjeri update:   ${BLUE}./update.sh --check${NC}"
    echo ""
    echo -e "  ${YELLOW}VAŽNO: Sustav radi 100% offline — nijedan podatak ne napušta Mac Studio!${NC}"
    echo -e "  ${YELLOW}Pri zamjeni modela (./update.sh) znanje se NE GUBI — LoRA adapteri,${NC}"
    echo -e "  ${YELLOW}memorija, DPO dataset i RAG baza ostaju netaknuti.${NC}"
    echo ""
}

main "$@"
