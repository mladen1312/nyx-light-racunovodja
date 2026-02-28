#!/bin/bash
# Nyx Light — Live Edit Session
# Pokreni ovo kad želiš editirati kod u živo

PROJECT="/Users/nyx/nyx-light-racunovodja"
cd "$PROJECT"
source .venv/bin/activate

echo "🌙 Nyx Light — Live Edit Mode"
echo ""
echo "Servisi:"
echo "  API:     http://localhost:8420 (auto-reload ON)"
echo "  MLX:     http://localhost:8422"
echo "  Tests:   pytest tests/ -v"
echo ""
echo "Korisne komande:"
echo "  nyx-test       → pokreni sve testove"
echo "  nyx-test-fast  → samo promijenjene module"
echo "  nyx-reload     → force reload API-ja"
echo "  nyx-logs       → pratI logove"
echo "  nyx-status     → zdravlje sustava"
echo "  nyx-memory     → memory usage"
echo ""

# Aliasi
alias nyx-test="python -m pytest tests/ -v --tb=short"
alias nyx-test-fast="python -m pytest tests/ -v --tb=short -x --lf"
alias nyx-reload="kill -HUP \$(pgrep -f uvicorn) 2>/dev/null || echo 'API not running'"
alias nyx-logs="tail -f /Users/nyx/nyx-data/logs/*.log"
alias nyx-status="python -c 'from nyx_light.deployment import HealthMonitor; import json; print(json.dumps(HealthMonitor().check_all(), indent=2))'"
alias nyx-memory="python -c '
from nyx_light.deployment import recommend_stack
import json
r = recommend_stack(256)
print(json.dumps(r, indent=2))
'"

# Start watcher u pozadini
python -c "
from nyx_light.deployment import HotReloadWatcher, ModuleReloader
import signal, sys

watcher = HotReloadWatcher(watch_dirs=['src/nyx_light'])
reloader = ModuleReloader()
watcher.on_change(lambda c: reloader.reload_module(c.path) if c.action != 'deleted' else None)
watcher.start()
print('👀 Hot-reload watcher aktivan. Editiraj kod — automatski se reloada.')
print('Ctrl+C za izlaz.')
signal.signal(signal.SIGINT, lambda s, f: (watcher.stop(), sys.exit(0)))
signal.pause()
" &

# Interaktivni shell
exec bash --rcfile <(echo 'PS1="🌙 nyx> "')"
