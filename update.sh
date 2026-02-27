#!/usr/bin/env bash
# 🌙 Nyx Light — AUTO-UPDATE (Zakoni + Modeli + NN Monitor)
# ./update.sh             — Interaktivno
# ./update.sh --auto      — Cron (tiho)
# ./update.sh --laws      — Samo zakoni
# ./update.sh --check-nn  — Provjeri NN
# ./update.sh --models    — Provjeri modele
# ./update.sh --force     — Forsiraj sve
# ./update.sh --rollback  — Vrati model
# ./update.sh --status    — Status
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA="$DIR/data"; MODELS="$DATA/models"; LAWS="$DATA/laws"; VENV="$DIR/.venv"
LOG="$DATA/logs/update.log"
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
log(){ echo -e "  ${GREEN}✅${NC} $*"; }
warn(){ echo -e "  ${YELLOW}⚠️${NC} $*"; }
err(){ echo -e "  ${RED}❌${NC} $*"; }
info(){ echo -e "  ${CYAN}ℹ${NC} $*"; }
logf(){ mkdir -p "$(dirname "$LOG")"; echo "[$(date -Iseconds)] $*" >> "$LOG"; }
MODE="interactive"
for a in "$@"; do case "$a" in
  --auto) MODE=auto;; --laws) MODE=laws;; --models) MODE=models;;
  --check-nn) MODE=check_nn;; --force) MODE=force;;
  --rollback) MODE=rollback;; --status) MODE=status;; esac; done
[[ -d "$VENV" ]] && source "$VENV/bin/activate"

verify_knowledge() {
  info "Knowledge Preservation Check"
  for p in "$DATA/memory_db" "$DATA/dpo_datasets" "$DATA/rag_db" "$DATA/laws" "$MODELS/lora"; do
    [[ -d "$p" ]] && { c=$(find "$p" -type f 2>/dev/null|wc -l|tr -d ' '); s=$(du -sh "$p" 2>/dev/null|cut -f1); log "$(basename $p): ${c} fajlova ($s)"; }
  done
  [[ -f "$DATA/auth.db" ]] && log "auth.db: $(du -sh "$DATA/auth.db"|cut -f1)"
}

if [[ "$MODE" == "status" ]]; then
  echo -e "\n${BOLD}🌙 Nyx Light — Status${NC}\n"
  [[ -f "$MODELS/registry.json" ]] && python3 -c "
import json; r=json.load(open('$MODELS/registry.json'))
print(f'  LLM:    {r.get(\"primary\",{}).get(\"name\",\"?\")}')
print(f'  Vision: {r.get(\"vision\",{}).get(\"name\",\"?\")}')
" 2>/dev/null
  log "Zakoni: $(ls "$LAWS"/*.txt 2>/dev/null|wc -l|tr -d ' ') datoteka"
  python3 -c "
import sys;sys.path.insert(0,'src')
from nyx_light.rag.nn_monitor import NNMonitor
s=NNMonitor(laws_dir='data/laws').get_status()
print(f'  Zadnja NN provjera: {s[\"last_check\"] or \"nikada\"}')
" 2>/dev/null || true
  verify_knowledge; exit 0
fi

echo -e "\n${BOLD}🌙 Nyx Light — Update [$(date +%Y-%m-%d\ %H:%M)]${NC}\n"

update_laws() {
  info "Update zakona RH"
  logf "Laws update"
  python3 -c "
import sys;sys.path.insert(0,'src')
from nyx_light.rag.law_downloader import LawDownloader
dl=LawDownloader(laws_dir='data/laws',rag_dir='data/rag_db')
c=dl.check_for_updates()
if c['updates_available']>0 or c['not_downloaded']>0:
  r=dl.download_all(callback=lambda m:print(f'    📜 {m}'))
  print(f'  ✅ Skinuto:{r[\"downloaded\"]} Ažurno:{r[\"skipped\"]} Greške:{r[\"errors\"]}')
else: print('  ✅ Svi zakoni ažurni')
s=dl.get_stats(); print(f'  📊 {s[\"laws_downloaded\"]}/{s[\"laws_in_catalog\"]} ({s[\"total_size_kb\"]}KB)')
"
}

check_nn() {
  info "Provjera Narodnih Novina"
  logf "NN check"
  python3 -c "
import sys;sys.path.insert(0,'src')
from nyx_light.rag.nn_monitor import NNMonitor
m=NNMonitor(laws_dir='data/laws',rag_dir='data/rag_db')
r=m.check_for_updates(days_back=14)
print(f'  Provjereno: {r.nn_issues_checked} NN brojeva')
for a in r.new_amendments: print(f'    📋 {a.title} (NN {a.nn_number})')
if r.relevant_found==0: print('  ✅ Nema izmjena (14 dana)')
"
}

auto_update_rag() {
  logf "NN auto-update"
  python3 -c "
import sys;sys.path.insert(0,'src')
from nyx_light.rag.nn_monitor import NNMonitor
m=NNMonitor(laws_dir='data/laws',rag_dir='data/rag_db')
r=m.auto_update_rag(callback=lambda x:print(f'    {x}'))
if r.get('rag_updated'): print('  ✅ RAG ažuriran')
else: print('  ✅ RAG ažuran')
"
}

check_models() {
  info "Provjera LLM modela"
  logf "Model check"
  python3 -c "
import sys;sys.path.insert(0,'src')
from nyx_light.model_manager import ModelManager
mgr=ModelManager(models_dir='data/models'); s=mgr.status()
print(f'  LLM: {s.get(\"primary\",\"?\")}  Vision: {s.get(\"vision\",\"?\")}')
u=mgr.check_for_updates()
if u.get('primary_update') or u.get('vision_update'):
  print('  🆕 Nove verzije! Pokrenite: ./update.sh --force')
else: print('  ✅ Modeli ažurni')
"
}

force_all() {
  update_laws
  verify_knowledge
  python3 -c "
import sys;sys.path.insert(0,'src')
from nyx_light.model_manager import ModelManager
mgr=ModelManager(models_dir='data/models')
rec=mgr.recommend_model(); print(f'  Preporučeni: {rec.name}')
r=mgr.safe_upgrade(rec.name,callback=lambda m:print(f'    {m}'))
print(f'  {\"✅\" if r.get(\"ok\") else \"❌\"} {r.get(\"message\",\"?\")}')
"
  verify_knowledge
}

rollback() {
  verify_knowledge
  if ls "$MODELS/archive"/primary_* &>/dev/null 2>&1; then
    L=$(ls -td "$MODELS/archive"/primary_*|head -1)
    mv "$MODELS/primary" "$MODELS/primary_failed_$(date +%s)" 2>/dev/null||true
    cp -r "$L" "$MODELS/primary"; log "Rollback: $L"
  else err "Nema arhive"; fi
  verify_knowledge
}

case "$MODE" in
  interactive) check_nn;echo "";update_laws;echo "";check_models;echo "";verify_knowledge;;
  auto) auto_update_rag;update_laws;check_models;;
  laws) update_laws;; models) check_models;; check_nn) check_nn;;
  force) force_all;; rollback) rollback;;
esac
echo -e "\n${GREEN}Gotovo.${NC} Log: $LOG"
logf "Done (mode=$MODE)"
