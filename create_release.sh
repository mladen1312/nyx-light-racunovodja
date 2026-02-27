#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# Nyx Light — Računovođa: KREIRANJE INSTALACIJSKOG PAKETA
# ═══════════════════════════════════════════════════════════════
#
# Ovu skriptu pokreće ADMIN (Mladen) da napravi .zip paket
# koji se može dati zaposlenicima bez GitHub pristupa.
#
# Korištenje:
#   ./create_release.sh
#
# Rezultat:
#   nyx-light-installer-v18-2026-02-27.zip (~5 MB)
#
# Korisnik (računovođa) samo:
#   1. Raspakira ZIP
#   2. Otvori Terminal
#   3. cd nyx-light-racunovodja
#   4. ./install.sh
#
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VERSION="v18"
DATE=$(date +%Y-%m-%d)
RELEASE_NAME="nyx-light-installer-${VERSION}-${DATE}"
BUILD_DIR="/tmp/${RELEASE_NAME}"
OUTPUT="${SCRIPT_DIR}/${RELEASE_NAME}.zip"

echo -e "${BLUE}═══════════════════════════════════════${NC}"
echo -e "${BLUE}  🌙 Nyx Light — Kreiranje paketa${NC}"
echo -e "${BLUE}═══════════════════════════════════════${NC}"
echo ""

# Očisti prethodne buildove
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

echo -e "  📦 Kopiram izvorni kod..."

# Kopiraj SVE osim nepotrebnog
if command -v rsync &>/dev/null; then
    rsync -a \
        --exclude='.git' \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='.pytest_cache' \
        --exclude='venv' \
        --exclude='.venv' \
        --exclude='*.egg-info' \
        --exclude='data/models/*' \
        --exclude='data/logs/*.log' \
        --exclude='data/*.db' \
        --exclude='data/prompt_cache/*' \
        --exclude='data/rag_db/*' \
        --exclude='data/memory_db/*' \
        --exclude='data/uploads/*' \
        --exclude='data/exports/*' \
        --exclude='data/backups/*' \
        --exclude='node_modules' \
        --exclude='.DS_Store' \
        --exclude='*.zip' \
        "$SCRIPT_DIR/" "$BUILD_DIR/" \
        2>/dev/null
else
    # Fallback za sustave bez rsync
    cp -r "$SCRIPT_DIR"/* "$BUILD_DIR/" 2>/dev/null || true
    rm -rf "$BUILD_DIR/.git" "$BUILD_DIR/venv" "$BUILD_DIR/.venv" 2>/dev/null
    find "$BUILD_DIR" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
    find "$BUILD_DIR" -name "*.pyc" -delete 2>/dev/null || true
    rm -f "$BUILD_DIR"/data/*.db 2>/dev/null
    rm -rf "$BUILD_DIR"/.pytest_cache 2>/dev/null
fi

# Osiguraj da su direktoriji prisutni (prazni, s .gitkeep)
for d in data/db data/logs data/exports data/uploads data/backups data/models \
         data/dpo_pairs data/lora_adapters data/memory data/embeddings \
         data/memory_db data/rag_db data/prompt_cache; do
    mkdir -p "$BUILD_DIR/$d"
    touch "$BUILD_DIR/$d/.gitkeep"
done

# Osiguraj da su skripte executable
chmod +x "$BUILD_DIR/install.sh"
chmod +x "$BUILD_DIR/start.sh"
chmod +x "$BUILD_DIR/update.sh" 2>/dev/null || true

echo -e "  📝 Kreiram ČITAJ-ME.txt..."

cat > "$BUILD_DIR/ČITAJ-ME.txt" << 'CITAJ'
═══════════════════════════════════════════════════
  🌙 Nyx Light — Računovođa
  Upute za instalaciju
═══════════════════════════════════════════════════

KORAK 1: Raspakirajte ovaj ZIP
   → Dvaput kliknite na ZIP datoteku
   → Pojavi se mapa "nyx-light-installer-..."

KORAK 2: Otvorite Terminal
   → Na tipkovnici: Cmd + Space (razmaknica)
   → Upišite: Terminal
   → Pritisnite Enter

KORAK 3: Uđite u mapu
   → Upišite (ili kopirajte) u Terminal:

   cd ~/Downloads/nyx-light-installer-*
   chmod +x install.sh
   ./install.sh

   → Pritisnite Enter i čekajte 30-60 minuta

KORAK 4: Gotovo!
   → Browser se automatski otvara
   → Login: admin / admin123
   → ODMAH promijenite lozinku!

═══════════════════════════════════════════════════
SVAKODNEVNO POKRETANJE:
   → Normalno se sustav pokreće automatski
   → Ako ne radi, otvorite Terminal i:
     cd /Users/Shared/nyx-light-racunovodja
     ./start.sh

PRISTUP IZ BROWSERA:
   → http://localhost:7860
   → Ili s drugog računala: http://[IP-Mac-Studia]:7860

PROBLEMI?
   → Kontaktirajte: Dr. Mladen Mešter
═══════════════════════════════════════════════════
CITAJ

echo -e "  🔧 Ažuriram install.sh za offline rad..."

# Patch install.sh da ne radi git clone nego koristi lokalni kod
cat > "$BUILD_DIR/install.sh.patch" << 'PATCH_EOF'
--- Ovaj install.sh je prilagođen za ZIP distribuciju ---
--- Ne zahtijeva GitHub pristup ---
PATCH_EOF

# Kreiraj wrapper install.sh koji kopira lokalni kod umjesto git clone
cat > "$BUILD_DIR/install.sh" << 'INSTALLER_EOF'
#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
# 🌙 Nyx Light — Računovođa :: OFFLINE INSTALLER (ZIP verzija)
# ═══════════════════════════════════════════════════════════════════════
#
# Ova verzija NE ZAHTIJEVA GitHub pristup.
# Kod se kopira iz ove mape u /Users/Shared/nyx-light-racunovodja
#
# Korištenje:
#   chmod +x install.sh && ./install.sh
#
# ═══════════════════════════════════════════════════════════════════════

set -euo pipefail

INSTALL_DIR="/Users/Shared/nyx-light-racunovodja"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PORT=7860

# ── Boje ──
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m'
BOLD='\033[1m'

step()  { echo -e "\n${BLUE}▶ $1${NC}"; }
ok()    { echo -e "${GREEN}  ✅ $1${NC}"; }
warn()  { echo -e "${YELLOW}  ⚠️  $1${NC}"; }
info()  { echo -e "  ℹ️  $1"; }

check_macos() {
    if [[ "$(uname)" != "Darwin" ]]; then
        echo -e "${RED}❌ Ova skripta radi samo na macOS (Mac Studio)${NC}"
        exit 1
    fi
    ok "macOS $(sw_vers -productVersion)"

    local ram_gb=$(( $(sysctl -n hw.memsize) / 1073741824 ))
    if [[ $ram_gb -ge 192 ]]; then
        ok "${ram_gb}GB RAM — puni AI model (Qwen3-235B)"
    elif [[ $ram_gb -ge 64 ]]; then
        ok "${ram_gb}GB RAM — manji AI model (Qwen3-30B)"
    else
        warn "${ram_gb}GB RAM — osnovni mod (bez AI modela)"
    fi
}

install_xcode_clt() {
    step "Korak 1/9: Xcode Command Line Tools"
    if xcode-select -p &>/dev/null; then
        ok "Već instaliran"
    else
        info "Pojavit će se prozor — kliknite 'Install'"
        xcode-select --install 2>/dev/null || true
        local waited=0
        while ! xcode-select -p &>/dev/null && [[ $waited -lt 600 ]]; do
            sleep 10; waited=$((waited+10)); echo -n "."
        done
        echo ""
        xcode-select -p &>/dev/null && ok "Instaliran" || warn "Možda treba ručno"
    fi
}

install_homebrew() {
    step "Korak 2/9: Homebrew"
    if command -v brew &>/dev/null; then
        ok "Već instaliran"
    else
        info "Instaliram Homebrew..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        [[ -f "/opt/homebrew/bin/brew" ]] && eval "$(/opt/homebrew/bin/brew shellenv)" && echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
        ok "Homebrew instaliran"
    fi
}

install_python() {
    step "Korak 3/9: Python 3.12"
    if command -v python3 &>/dev/null; then
        local ver=$(python3 --version 2>&1 | awk '{print $2}')
        local minor=$(echo "$ver" | cut -d. -f2)
        if [[ "$minor" -ge 11 ]]; then
            ok "Python $ver"
            return
        fi
    fi
    brew install python@3.12
    ok "Python $(python3 --version)"
}

copy_code() {
    step "Korak 4/9: Kopiranje koda"
    if [[ "$SCRIPT_DIR" == "$INSTALL_DIR" ]]; then
        ok "Već u instalacijskom direktoriju"
        return
    fi

    if [[ -d "$INSTALL_DIR" ]]; then
        info "Ažuriram postojeću instalaciju..."
        # Sačuvaj korisničke podatke
        for d in data/db data/memory_db data/rag_db data/dpo_pairs data/lora_adapters data/models; do
            if [[ -d "$INSTALL_DIR/$d" ]]; then
                cp -r "$INSTALL_DIR/$d" "/tmp/nyx_backup_$d" 2>/dev/null || true
            fi
        done
    fi

    mkdir -p "$INSTALL_DIR"
    rsync -a --delete \
        --exclude='venv' --exclude='.venv' --exclude='__pycache__' \
        --exclude='*.pyc' --exclude='data/models/*' --exclude='data/*.db' \
        "$SCRIPT_DIR/" "$INSTALL_DIR/"

    # Vrati backup podataka
    for d in data/db data/memory_db data/rag_db data/dpo_pairs data/lora_adapters data/models; do
        if [[ -d "/tmp/nyx_backup_$d" ]]; then
            cp -r "/tmp/nyx_backup_$d"/* "$INSTALL_DIR/$d/" 2>/dev/null || true
            rm -rf "/tmp/nyx_backup_$d"
        fi
    done

    ok "Kod kopiran u $INSTALL_DIR"
    cd "$INSTALL_DIR"
}

install_python_deps() {
    step "Korak 5/9: Python paketi"
    cd "$INSTALL_DIR"

    [[ ! -d "venv" ]] && python3 -m venv venv
    source venv/bin/activate
    pip install --upgrade pip -q

    info "Instaliram core pakete (2-3 minute)..."
    pip install -q \
        fastapi "uvicorn[standard]" httpx pydantic \
        aiofiles python-multipart websockets \
        openpyxl pandas python-dateutil \
        PyJWT "passlib[bcrypt]" \
        pyyaml numpy psutil \
        PyPDF2 Pillow \
        imapclient aiosmtplib

    ok "Core paketi"

    info "Instaliram Apple Silicon ML pakete..."
    pip install -q mlx mlx-lm 2>/dev/null && ok "mlx + mlx-lm" || warn "mlx-lm preskočen"

    info "Instaliram sentence-transformers..."
    pip install -q sentence-transformers 2>/dev/null && ok "sentence-transformers" || warn "Preskočen — RAG koristi fallback"

    pip install -q qdrant-client neo4j 2>/dev/null || true
}

setup_dirs_and_db() {
    step "Korak 6/9: Baze podataka"
    cd "$INSTALL_DIR"
    source venv/bin/activate

    mkdir -p data/{db,logs,exports,uploads,backups,models,embeddings,laws}
    mkdir -p data/{dpo_pairs,lora_adapters,memory,memory_db,rag_db,prompt_cache}

    PYTHONPATH=src python3 -c "
from nyx_light.auth import AuthManager
a = AuthManager(db_path='data/auth.db')
print('  ✅ Auth inicijaliziran (admin:admin123)')
" 2>/dev/null || warn "Auth init preskočen"

    ok "Direktoriji i baze kreirani"
}

ingest_laws() {
    step "Korak 7/9: Zakoni RH"
    cd "$INSTALL_DIR"
    source venv/bin/activate

    local count=$(ls data/laws/*.md 2>/dev/null | wc -l | tr -d ' ')
    if [[ "$count" -ge 20 ]]; then
        ok "$count zakona već učitano"
    else
        warn "Zakoni se učitavaju pri prvom pokretanju"
    fi
}

download_models() {
    step "Korak 8/9: AI modeli"
    cd "$INSTALL_DIR"
    source venv/bin/activate

    local ram_gb=$(( $(sysctl -n hw.memsize) / 1073741824 ))

    # Embedding model
    info "Preuzimam embedding model (~500MB)..."
    PYTHONPATH=src python3 -c "
try:
    from sentence_transformers import SentenceTransformer
    m = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2', cache_folder='data/models')
    print('  ✅ Embedding model preuzet')
except: print('  ⚠️  Embedding preskočen')
" 2>/dev/null

    # LLM model
    if pip show mlx-lm &>/dev/null 2>&1; then
        if [[ $ram_gb -ge 192 ]]; then
            local model="Qwen/Qwen3-235B-A22B-4bit"
            info "Preuzimam Qwen3-235B (~120GB) — trajanje: 30-60 min!"
        elif [[ $ram_gb -ge 64 ]]; then
            local model="Qwen/Qwen3-30B-A3B-4bit"
            info "Preuzimam Qwen3-30B (~16GB)..."
        else
            warn "Premalo RAM-a za AI model"
            return
        fi

        python3 -c "
from huggingface_hub import snapshot_download
snapshot_download('$model', local_dir='data/models/$(basename $model)', local_dir_use_symlinks=False)
print('  ✅ LLM model preuzet')
" 2>/dev/null || warn "LLM download neuspjeo"
    else
        warn "mlx-lm nije instaliran — chat koristi offline odgovore"
    fi
}

start_system() {
    step "Korak 9/9: Pokretanje"
    cd "$INSTALL_DIR"
    chmod +x start.sh
    ./start.sh start 2>/dev/null || ./start.sh 2>/dev/null || true

    info "Čekam server..."
    for i in $(seq 1 15); do
        curl -sf "http://localhost:$PORT/health" > /dev/null 2>&1 && break
        sleep 1; echo -n "."
    done
    echo ""

    if curl -sf "http://localhost:$PORT/health" > /dev/null 2>&1; then
        ok "Server radi na http://localhost:$PORT"
    else
        warn "Server se još pokreće — pričekajte 30 sekundi"
    fi

    open "http://localhost:$PORT" 2>/dev/null || true
}

print_done() {
    echo ""
    echo -e "${PURPLE}═══════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}${BOLD}  🌙 Nyx Light — Računovođa: INSTALACIJA ZAVRŠENA!${NC}"
    echo -e "${PURPLE}═══════════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "  ${BOLD}Pristup:${NC}   http://localhost:$PORT"
    echo -e "  ${BOLD}Korisnik:${NC}  admin"
    echo -e "  ${BOLD}Lozinka:${NC}   admin123 ${RED}(promijenite odmah!)${NC}"
    echo ""
    echo -e "  ${BOLD}Naredbe:${NC}"
    echo -e "    cd $INSTALL_DIR"
    echo -e "    ./start.sh          — Pokreni"
    echo -e "    ./start.sh stop     — Zaustavi"
    echo -e "    ./start.sh restart  — Restart"
    echo ""
    echo -e "  ${GREEN}✅ Svi podaci ostaju 100% lokalno na ovom Mac Studiu.${NC}"
    echo -e "${PURPLE}═══════════════════════════════════════════════════════${NC}"
}

# ── MAIN ──
echo -e "${PURPLE}═══════════════════════════════════════${NC}"
echo -e "${PURPLE}  🌙 Nyx Light — Offline Installer${NC}"
echo -e "${PURPLE}═══════════════════════════════════════${NC}"
echo ""
echo -e "  Trajanje: ${BOLD}30-60 minuta${NC}"
echo ""

check_macos
install_xcode_clt
install_homebrew
install_python
copy_code
install_python_deps
setup_dirs_and_db
ingest_laws
download_models
start_system
print_done
INSTALLER_EOF

chmod +x "$BUILD_DIR/install.sh"

# Kreiraj ZIP
echo -e "  📦 Kreiram ZIP paket..."
cd /tmp
zip -r "$OUTPUT" "$RELEASE_NAME" -x "*.pyc" "*__pycache__*" "*.git*" > /dev/null 2>&1

SIZE=$(du -sh "$OUTPUT" | awk '{print $1}')
echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  ✅ PAKET KREIRAN!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
echo ""
echo -e "  📦 ${BOLD}Datoteka:${NC}  $OUTPUT"
echo -e "  📏 ${BOLD}Veličina:${NC}  $SIZE"
echo ""
echo -e "  ${BOLD}Distribucija korisniku:${NC}"
echo -e "    1. USB stick   — kopirajte ZIP na USB"
echo -e "    2. AirDrop     — pošaljite direktno na Mac Studio"
echo -e "    3. Mrežna mapa — stavite na dijeljenu mapu"
echo -e "    4. Email       — ako je dovoljno malen"
echo ""
echo -e "  ${BOLD}Korisnik treba samo:${NC}"
echo -e "    1. Raspakiraj ZIP (dvaput kliknuti)"
echo -e "    2. Otvori Terminal (Cmd+Space → Terminal)"
echo -e "    3. ${BLUE}cd ~/Downloads/$RELEASE_NAME${NC}"
echo -e "    4. ${BLUE}./install.sh${NC}"
echo ""

# Cleanup
rm -rf "$BUILD_DIR"
