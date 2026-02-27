#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════
# Nyx Light — Računovođa — Apple Silicon Deployment Script
#
# Optimizirano za: Mac Studio M3 Ultra (192GB) / M5 Ultra (192-384GB)
#
# Korištenje:
#   ./start.sh              # Pokreni sve (API + LLM + watchers)
#   ./start.sh api          # Samo API server
#   ./start.sh llm          # Samo LLM server
#   ./start.sh stop         # Zaustavi sve
#   ./start.sh status       # Status servisa
#   ./start.sh setup        # Prvo pokretanje (instaliraj sve)
#   ./start.sh ingest-laws  # Učitaj zakone u RAG bazu
# ════════════════════════════════════════════════════════════════

set -e

# ── Boje za terminal ──
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; PURPLE='\033[0;35m'; NC='\033[0m'

echo -e "${PURPLE}🌙 Nyx Light — Računovođa${NC}"
echo -e "${BLUE}Apple Silicon AI Accounting System${NC}\n"

# ── Konfiguracija ──
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

API_HOST="${NYX_HOST:-0.0.0.0}"
API_PORT="${NYX_PORT:-7860}"
LLM_PORT="${NYX_LLM_PORT:-8080}"
VLM_PORT="${NYX_VLM_PORT:-8081}"
WORKERS="${NYX_WORKERS:-4}"

# Modeli
LLM_MODEL="${NYX_LLM_MODEL:-mlx-community/Qwen3-235B-A22B-4bit}"
VLM_MODEL="${NYX_VLM_MODEL:-mlx-community/Qwen3-VL-8B-4bit}"

# PID files
PID_DIR="$PROJECT_DIR/data/.pids"
mkdir -p "$PID_DIR"

# ── Helper funkcije ──
log_info()  { echo -e "${GREEN}✓${NC} $1"; }
log_warn()  { echo -e "${YELLOW}⚠${NC} $1"; }
log_error() { echo -e "${RED}✗${NC} $1"; }
log_step()  { echo -e "\n${BLUE}━━━ $1 ━━━${NC}"; }

check_apple_silicon() {
    if [[ "$(uname -m)" != "arm64" ]]; then
        log_error "Ovaj sustav zahtijeva Apple Silicon (M3/M5 Ultra)"
        exit 1
    fi
    # Check available memory
    local total_mem=$(sysctl -n hw.memsize 2>/dev/null || echo 0)
    local total_gb=$((total_mem / 1073741824))
    log_info "Apple Silicon detektiran: $(sysctl -n machdep.cpu.brand_string 2>/dev/null || echo 'Unknown')"
    log_info "Unified Memory: ${total_gb} GB"

    if [[ $total_gb -lt 64 ]]; then
        log_warn "Preporučeno minimalno 192 GB za puni sustav"
        log_warn "S ${total_gb} GB: samo manji modeli (Qwen3-30B-A3B)"
        export LLM_MODEL="mlx-community/Qwen3-30B-A3B-4bit"
    fi
}

ensure_dirs() {
    for d in data/{memory_db,rag_db,dpo_datasets,models/lora,laws,exports,backups,logs,uploads,uploads/email,uploads/folder,prompt_cache,.pids}; do
        mkdir -p "$d"
    done
}

# ── SETUP (prvo pokretanje) ──
do_setup() {
    log_step "Postavljanje okruženja"

    # Python venv
    if [[ ! -d "venv" ]]; then
        log_info "Kreiram Python virtualenv..."
        python3 -m venv venv
    fi
    source venv/bin/activate

    # Nadogradi pip
    pip install --upgrade pip -q

    # Core dependencies
    log_info "Instaliram Python pakete..."
    pip install -q \
        fastapi uvicorn httpx pyjwt passlib[bcrypt] aiofiles \
        openpyxl python-multipart pyyaml numpy \
        sentence-transformers

    # Apple Silicon ML pakete
    log_info "Instaliram Apple Silicon ML pakete..."
    pip install -q mlx mlx-lm 2>/dev/null || log_warn "mlx-lm nije dostupan (potreban macOS)"

    # Opcionalni paketi
    pip install -q qdrant-client neo4j 2>/dev/null || log_warn "Qdrant/Neo4j klijent nije instaliran"

    ensure_dirs

    # Download modela
    log_step "Provjera AI modela"
    if command -v mlx_lm.server &>/dev/null; then
        log_info "mlx-lm dostupan"
        # Model će se downloadati pri prvom pokretanju
    else
        log_warn "mlx-lm nije instaliran — LLM inference neće raditi"
    fi

    # Ingest zakona
    do_ingest_laws

    log_info "Setup završen! Pokrenite: ./start.sh"
}

# ── INGEST LAWS ──
do_ingest_laws() {
    log_step "Učitavanje zakona u RAG bazu"
    if [[ -f "venv/bin/activate" ]]; then source venv/bin/activate; fi
    PYTHONPATH=src python3 -c "
from nyx_light.rag.ingest_laws import ingest_all_laws
r = ingest_all_laws()
print(f'✓ Učitano {r[\"laws_processed\"]} zakona, {r[\"chunks_ingested\"]} chunks')
if r.get('errors'):
    for e in r['errors']: print(f'  ⚠ {e[\"file\"]}: {e[\"error\"]}')
" 2>/dev/null || log_warn "Greška pri učitavanju zakona"
}

# ── START LLM SERVER ──
start_llm() {
    log_step "Pokretanje LLM servera"

    if [[ -f "$PID_DIR/llm.pid" ]] && kill -0 "$(cat "$PID_DIR/llm.pid")" 2>/dev/null; then
        log_info "LLM server već pokrenut (PID $(cat "$PID_DIR/llm.pid"))"
        return
    fi

    if ! command -v mlx_lm.server &>/dev/null; then
        log_warn "mlx_lm.server nije dostupan — LLM preskočen"
        return
    fi

    log_info "Model: $LLM_MODEL"
    log_info "Port: $LLM_PORT"

    # Apple Silicon optimizacije
    export MALLOC_ARENA_MAX=2  # Manje fragmentacije memorije
    export MLX_METAL_JIT=1     # Metal JIT kompilacija

    nohup mlx_lm.server \
        --model "$LLM_MODEL" \
        --port "$LLM_PORT" \
        --host 127.0.0.1 \
        --max-tokens 4096 \
        --trust-remote-code \
        > data/logs/llm.log 2>&1 &
    echo $! > "$PID_DIR/llm.pid"
    log_info "LLM server pokrenut (PID $!)"
}

# ── START VLM SERVER (Vision) ──
start_vlm() {
    log_step "Pokretanje Vision servera"

    if [[ -f "$PID_DIR/vlm.pid" ]] && kill -0 "$(cat "$PID_DIR/vlm.pid")" 2>/dev/null; then
        log_info "VLM server već pokrenut"
        return
    fi

    if ! command -v mlx_lm.server &>/dev/null; then
        log_warn "VLM server preskočen (mlx_lm nedostupan)"
        return
    fi

    nohup mlx_lm.server \
        --model "$VLM_MODEL" \
        --port "$VLM_PORT" \
        --host 127.0.0.1 \
        --max-tokens 2048 \
        --trust-remote-code \
        > data/logs/vlm.log 2>&1 &
    echo $! > "$PID_DIR/vlm.pid"
    log_info "VLM server pokrenut (PID $!, port $VLM_PORT)"
}

# ── START API SERVER ──
start_api() {
    log_step "Pokretanje API servera"

    if [[ -f "$PID_DIR/api.pid" ]] && kill -0 "$(cat "$PID_DIR/api.pid")" 2>/dev/null; then
        log_info "API server već pokrenut (PID $(cat "$PID_DIR/api.pid"))"
        return
    fi

    if [[ -f "venv/bin/activate" ]]; then source venv/bin/activate; fi

    log_info "API: http://${API_HOST}:${API_PORT}"
    log_info "Workers: $WORKERS"

    nohup uvicorn nyx_light.api.app:app \
        --host "$API_HOST" \
        --port "$API_PORT" \
        --workers "$WORKERS" \
        --app-dir src \
        --timeout-keep-alive 120 \
        --limit-concurrency 20 \
        > data/logs/api.log 2>&1 &
    echo $! > "$PID_DIR/api.pid"
    log_info "API server pokrenut (PID $!)"

    # Čekaj da se digne
    for i in {1..10}; do
        if curl -s "http://127.0.0.1:${API_PORT}/health" >/dev/null 2>&1; then
            log_info "API server spreman ✓"
            return
        fi
        sleep 1
    done
    log_warn "API server se još podiže..."
}

# ── STOP ──
do_stop() {
    log_step "Zaustavljanje servisa"
    for svc in api llm vlm; do
        if [[ -f "$PID_DIR/${svc}.pid" ]]; then
            pid=$(cat "$PID_DIR/${svc}.pid")
            if kill -0 "$pid" 2>/dev/null; then
                kill "$pid" 2>/dev/null
                log_info "${svc} zaustavljen (PID $pid)"
            fi
            rm -f "$PID_DIR/${svc}.pid"
        fi
    done
}

# ── STATUS ──
do_status() {
    log_step "Status servisa"
    for svc in api llm vlm; do
        if [[ -f "$PID_DIR/${svc}.pid" ]] && kill -0 "$(cat "$PID_DIR/${svc}.pid")" 2>/dev/null; then
            log_info "${svc}: POKRENUT (PID $(cat "$PID_DIR/${svc}.pid"))"
        else
            log_warn "${svc}: ZASTAVLJEN"
        fi
    done

    # API health
    if curl -s "http://127.0.0.1:${API_PORT}/health" >/dev/null 2>&1; then
        local health=$(curl -s "http://127.0.0.1:${API_PORT}/health")
        log_info "API health: $health"
    fi

    # Memory usage
    local mem_used=$(vm_stat 2>/dev/null | awk '/Pages active/ {print $3}' | tr -d '.')
    if [[ -n "$mem_used" ]]; then
        local mem_gb=$(echo "scale=1; $mem_used * 16384 / 1073741824" | bc 2>/dev/null || echo "?")
        log_info "Aktivna memorija: ${mem_gb} GB"
    fi

    # Thermal
    local therm=$(pmset -g therm 2>/dev/null | grep "CPU_Speed_Limit" | awk -F= '{print $2}' | tr -d ' ')
    if [[ -n "$therm" ]]; then
        log_info "CPU Speed Limit: ${therm}%"
    fi
}

# ── START ALL ──
do_start() {
    check_apple_silicon
    ensure_dirs
    start_llm
    start_vlm
    start_api

    echo ""
    log_info "═══════════════════════════════════════════"
    log_info "Nyx Light — Računovođa pokrenut!"
    log_info ""
    log_info "  Web UI:    http://${API_HOST}:${API_PORT}"
    log_info "  LLM API:   http://127.0.0.1:${LLM_PORT}"
    log_info "  VLM API:   http://127.0.0.1:${VLM_PORT}"
    log_info ""
    log_info "  Login:     admin / admin123 (promijeni!)"
    log_info "  Logovi:    data/logs/"
    log_info "  Stop:      ./start.sh stop"
    log_info "═══════════════════════════════════════════"
}

# ── MAIN ──
case "${1:-start}" in
    setup)        do_setup ;;
    start)        do_start ;;
    api)          ensure_dirs; start_api ;;
    llm)          start_llm ;;
    vlm)          start_vlm ;;
    stop)         do_stop ;;
    status)       do_status ;;
    restart)      do_stop; sleep 2; do_start ;;
    ingest-laws)  do_ingest_laws ;;
    *)
        echo "Korištenje: $0 {setup|start|stop|restart|status|api|llm|vlm|ingest-laws}"
        exit 1
    ;;
esac
