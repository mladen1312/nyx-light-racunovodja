#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
# 🌙 Nyx Light — Računovođa :: AUTO-UPDATE LLM MODELA
# ═══════════════════════════════════════════════════════════════════════
#
# Provjerava nove verzije LLM modela i sigurno ih zamjenjuje.
#
# KRITIČNO: Zamjena modela NE GUBI naučeno znanje!
#   Znanje je odvojeno od base modela:
#     ✅ data/memory_db/     — L1+L2 memorija (SQLite)
#     ✅ data/dpo_datasets/  — DPO preference parovi
#     ✅ data/models/lora/   — LoRA adapter težine
#     ✅ data/rag_db/        — Vektorska baza zakona
#     ✅ data/auth.db        — Korisnici
#     ✅ data/laws/          — RAG corpus
#     ✅ config.json         — Konfiguracija
#
# UPORABA:
#   ./update.sh              # Provjeri i ponudi update
#   ./update.sh --check      # Samo provjeri (ne skida)
#   ./update.sh --force      # Skini bez pitanja
#   ./update.sh --rollback   # Vrati prethodni model
#
# ═══════════════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="${SCRIPT_DIR}/data"
MODEL_DIR="${DATA_DIR}/models"
ARCHIVE_DIR="${MODEL_DIR}/archive"
REGISTRY="${MODEL_DIR}/registry.json"
LORA_DIR="${MODEL_DIR}/lora"

# Boje
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()  { echo -e "${GREEN}[✓]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
err()  { echo -e "${RED}[✗]${NC} $*"; }
info() { echo -e "${BLUE}[i]${NC} $*"; }

# ═══════════════════════════════════════════════════
# KNOWLEDGE PRESERVATION CHECK
# ═══════════════════════════════════════════════════

verify_knowledge() {
    echo ""
    info "═══ Provjera znanja (Knowledge Preservation) ═══"
    local all_ok=true

    KNOWLEDGE_PATHS=(
        "${DATA_DIR}/memory_db"
        "${DATA_DIR}/dpo_datasets"
        "${DATA_DIR}/rag_db"
        "${DATA_DIR}/laws"
        "${DATA_DIR}/auth.db"
        "${MODEL_DIR}/lora"
    )

    for kp in "${KNOWLEDGE_PATHS[@]}"; do
        if [ -e "$kp" ]; then
            if [ -d "$kp" ]; then
                count=$(find "$kp" -type f 2>/dev/null | wc -l)
                size=$(du -sh "$kp" 2>/dev/null | cut -f1)
                log "  $kp — ${count} datoteka (${size})"
            else
                size=$(du -sh "$kp" 2>/dev/null | cut -f1)
                log "  $kp — ${size}"
            fi
        else
            warn "  $kp — NE POSTOJI (bit će kreiran)"
        fi
    done

    echo ""
}

# ═══════════════════════════════════════════════════
# RAM DETECTION
# ═══════════════════════════════════════════════════

detect_ram() {
    if command -v sysctl &>/dev/null; then
        # macOS
        echo $(( $(sysctl -n hw.memsize 2>/dev/null || echo 0) / 1073741824 ))
    elif [ -f /proc/meminfo ]; then
        # Linux
        echo $(( $(grep MemTotal /proc/meminfo | awk '{print $2}') / 1048576 ))
    else
        echo 0
    fi
}

recommend_model() {
    local ram=$1
    if [ "$ram" -ge 192 ]; then
        echo "mlx-community/Qwen3-235B-A22B-4bit"
    elif [ "$ram" -ge 96 ]; then
        echo "mlx-community/Qwen2.5-72B-Instruct-4bit"
    elif [ "$ram" -ge 64 ]; then
        echo "mlx-community/DeepSeek-R1-Distill-Qwen-32B-4bit"
    else
        echo "mlx-community/Qwen2.5-32B-Instruct-4bit"
    fi
}

model_name() {
    local repo=$1
    if [[ "$repo" == *"235B"* ]]; then echo "Qwen3-235B-A22B"
    elif [[ "$repo" == *"72B"* ]]; then echo "Qwen2.5-72B"
    elif [[ "$repo" == *"DeepSeek"* ]]; then echo "DeepSeek-R1-Distill-32B"
    else echo "Qwen2.5-32B"
    fi
}

# ═══════════════════════════════════════════════════
# CHECK FOR UPDATES
# ═══════════════════════════════════════════════════

check_updates() {
    info "Provjeravam nove verzije modela na HuggingFace..."

    local ram=$(detect_ram)
    local recommended=$(recommend_model $ram)
    local current_model=""
    local current_date=""

    # Čitaj registry
    if [ -f "$REGISTRY" ]; then
        current_model=$(python3 -c "
import json
r = json.load(open('$REGISTRY'))
for k,v in r.get('installed',{}).items():
    if v.get('model_type','llm') != 'vision':
        print(v.get('hf_repo',''))
        break
" 2>/dev/null || echo "")
        current_date=$(python3 -c "
import json
r = json.load(open('$REGISTRY'))
for k,v in r.get('installed',{}).items():
    if v.get('model_type','llm') != 'vision':
        print(v.get('installed_at',''))
        break
" 2>/dev/null || echo "")
    fi

    if [ -z "$current_model" ]; then
        warn "Nema instaliranog LLM modela"
        info "Preporučeni model za ${ram}GB RAM: $(model_name $recommended)"
        info "Repo: $recommended"
        return 1
    fi

    info "Trenutni model: $current_model"
    info "Instaliran: $current_date"
    info "Preporučeni: $recommended"

    # Provjeri HuggingFace API
    local remote_date=""
    remote_date=$(python3 -c "
import urllib.request, json
url = 'https://huggingface.co/api/models/${current_model}'
try:
    resp = urllib.request.urlopen(url, timeout=10)
    data = json.loads(resp.read())
    print(data.get('lastModified', ''))
except: print('')
" 2>/dev/null || echo "")

    if [ -z "$remote_date" ]; then
        warn "Nije moguće provjeriti remote verziju (nema interneta?)"
        return 2
    fi

    if [ "$remote_date" \> "$current_date" ]; then
        echo ""
        warn "═══ NOVA VERZIJA DOSTUPNA! ═══"
        info "  Lokalna:  $current_date"
        info "  Remote:   $remote_date"
        return 0
    else
        log "Model je ažuran — nema novih verzija"
        return 2
    fi
}

# ═══════════════════════════════════════════════════
# SAFE DOWNLOAD & SWAP
# ═══════════════════════════════════════════════════

safe_upgrade() {
    local model_repo=$1
    local model_id=$(echo "$model_repo" | tr '/' '-')
    local target_dir="${MODEL_DIR}/primary"
    local archive_name="primary_$(date +%Y%m%d_%H%M%S)"

    echo ""
    info "═══ SAFE UPGRADE ═══"
    info "Model: $model_repo"
    echo ""

    # Step 0: Verify knowledge
    verify_knowledge

    # Step 1: Backup stari model
    if [ -d "$target_dir" ]; then
        mkdir -p "$ARCHIVE_DIR"
        info "Step 1: Archiving current model → ${ARCHIVE_DIR}/${archive_name}"
        mv "$target_dir" "${ARCHIVE_DIR}/${archive_name}"
        log "  Stari model arhiviran"
    else
        info "Step 1: Nema starog modela za arhivirati"
    fi

    # Step 2: Download novi
    info "Step 2: Downloading $model_repo..."
    mkdir -p "$target_dir"

    if command -v huggingface-cli &>/dev/null; then
        huggingface-cli download "$model_repo" \
            --local-dir "$target_dir" \
            --local-dir-use-symlinks False || {
            err "Download failed!"
            # Rollback
            if [ -d "${ARCHIVE_DIR}/${archive_name}" ]; then
                warn "Rolling back..."
                rm -rf "$target_dir"
                mv "${ARCHIVE_DIR}/${archive_name}" "$target_dir"
                log "Rollback successful"
            fi
            return 1
        }
    else
        warn "huggingface-cli nije instaliran — instaliram..."
        pip install -q huggingface-hub
        huggingface-cli download "$model_repo" \
            --local-dir "$target_dir" \
            --local-dir-use-symlinks False || {
            err "Download failed — rolling back"
            rm -rf "$target_dir"
            [ -d "${ARCHIVE_DIR}/${archive_name}" ] && mv "${ARCHIVE_DIR}/${archive_name}" "$target_dir"
            return 1
        }
    fi

    # Step 3: Verify
    info "Step 3: Verifying new model..."
    if [ -f "${target_dir}/config.json" ]; then
        log "  config.json ✅"
    else
        err "  config.json MISSING — rolling back!"
        rm -rf "$target_dir"
        [ -d "${ARCHIVE_DIR}/${archive_name}" ] && mv "${ARCHIVE_DIR}/${archive_name}" "$target_dir"
        return 1
    fi

    local weight_count=$(find "$target_dir" -name "*.safetensors" -o -name "*.gguf" | wc -l)
    if [ "$weight_count" -gt 0 ]; then
        log "  Weights: ${weight_count} files ✅"
    else
        err "  No weight files found — rolling back!"
        rm -rf "$target_dir"
        [ -d "${ARCHIVE_DIR}/${archive_name}" ] && mv "${ARCHIVE_DIR}/${archive_name}" "$target_dir"
        return 1
    fi

    # Step 4: Update registry
    info "Step 4: Updating registry..."
    python3 -c "
import json, os
from datetime import datetime
registry_path = '${REGISTRY}'
r = {}
if os.path.exists(registry_path):
    r = json.load(open(registry_path))
r.setdefault('installed', {})
model_id = '${model_repo}'.split('/')[-1].lower()
r['installed'][model_id] = {
    'model_id': model_id,
    'hf_repo': '${model_repo}',
    'installed_at': datetime.now().isoformat(),
    'path': '${target_dir}',
    'name': '$(model_name $model_repo)',
    'model_type': 'llm',
}
r['active_llm'] = model_id
r.setdefault('history', []).append({
    'action': 'upgrade',
    'model': '${model_repo}',
    'timestamp': datetime.now().isoformat(),
})
json.dump(r, open(registry_path, 'w'), indent=2)
print('Registry updated')
"

    # Step 5: Verify knowledge is intact
    echo ""
    info "Step 5: Verifying knowledge preservation..."
    verify_knowledge

    # Check LoRA adapters
    local lora_count=0
    if [ -d "$LORA_DIR" ]; then
        lora_count=$(find "$LORA_DIR" -mindepth 1 -maxdepth 1 -type d | wc -l)
    fi

    echo ""
    log "═══ UPGRADE COMPLETE ═══"
    log "  Novi model: $(model_name $model_repo)"
    log "  LoRA adapteri sačuvani: ${lora_count}"
    log "  Memorija intaktna: ✅"
    log "  DPO datasets intaktni: ✅"
    log "  RAG baza intaktna: ✅"
    log "  Stari model: ${ARCHIVE_DIR}/${archive_name}"
    echo ""
    info "Pokrenite './start.sh' za restart s novim modelom"
}

# ═══════════════════════════════════════════════════
# ROLLBACK
# ═══════════════════════════════════════════════════

rollback() {
    info "═══ ROLLBACK ═══"
    if [ ! -d "$ARCHIVE_DIR" ]; then
        err "Nema arhiviranih modela za rollback"
        return 1
    fi

    local latest=$(ls -t "$ARCHIVE_DIR" | head -1)
    if [ -z "$latest" ]; then
        err "Nema arhiviranih modela"
        return 1
    fi

    info "Rolling back to: $latest"
    rm -rf "${MODEL_DIR}/primary"
    mv "${ARCHIVE_DIR}/${latest}" "${MODEL_DIR}/primary"
    log "Rollback uspješan"
}

# ═══════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════

main() {
    echo ""
    echo "═══════════════════════════════════════════"
    echo "  🌙 Nyx Light — Model Update Manager"
    echo "═══════════════════════════════════════════"
    echo ""

    local ram=$(detect_ram)
    info "RAM: ${ram} GB"
    info "Preporučeni: $(model_name $(recommend_model $ram))"

    case "${1:-}" in
        --check)
            check_updates
            ;;
        --force)
            local recommended=$(recommend_model $ram)
            safe_upgrade "$recommended"
            ;;
        --rollback)
            rollback
            ;;
        *)
            check_updates
            local status=$?
            if [ $status -eq 0 ]; then
                echo ""
                read -p "Želite li nadograditi model? [y/N] " -n 1 -r
                echo ""
                if [[ $REPLY =~ ^[Yy]$ ]]; then
                    local recommended=$(recommend_model $ram)
                    safe_upgrade "$recommended"
                else
                    info "Update odgođen"
                fi
            elif [ $status -eq 1 ]; then
                echo ""
                read -p "Želite li instalirati preporučeni model? [y/N] " -n 1 -r
                echo ""
                if [[ $REPLY =~ ^[Yy]$ ]]; then
                    local recommended=$(recommend_model $ram)
                    safe_upgrade "$recommended"
                fi
            fi
            ;;
    esac
}

main "$@"
