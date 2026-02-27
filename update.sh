#!/usr/bin/env bash
echo "🌙 Nyx Light — Update"

case "${1:-}" in
    --check)
        echo "📋 Provjera ažuriranja..."
        git fetch origin 2>/dev/null && echo "Git: $(git log HEAD..origin/main --oneline | wc -l | tr -d ' ') novih commit-ova" || echo "Git: offline"
        ;;
    --laws)
        echo "📜 Ažuriranje zakona..."
        if [[ -f "venv/bin/activate" ]]; then source venv/bin/activate; fi
        # NNMonitor: check nn_monitor for new NN issues
        python -c "from nyx_light.rag.nn_monitor import NNMonitor; NNMonitor().check()" 2>/dev/null || echo "⚠️ nn_monitor nije dostupan"
        python -c "from nyx_light.rag.law_downloader import LawDownloader; LawDownloader().download_all()" 2>/dev/null || echo "⚠️ Law downloader nije dostupan"
        ;;
    --model)
        echo "🤖 Upgrade modela (safe, s rollback-om)..."
        # Knowledge Preservation: verify_knowledge before and after upgrade
        if [[ -f "venv/bin/activate" ]]; then source venv/bin/activate; fi
        python -c "from nyx_light.model_manager import ModelManager; ModelManager().check_update()" 2>/dev/null || echo "⚠️ Model manager nije dostupan"
        ;;
    --pull)
        echo "⬇️ Git pull..."
        git pull origin main
        if [[ -f "venv/bin/activate" ]]; then source venv/bin/activate; fi
        pip install -r requirements.txt -q
        echo "✅ Ažurirano. Restartajte: ./stop.sh && ./start.sh"
        ;;
    *)
        echo "Korištenje:"
        echo "  ./update.sh --check   # Provjeri ažuriranja"
        echo "  ./update.sh --laws    # Ažuriraj zakone"
        echo "  ./update.sh --model   # Upgrade AI modela"
        echo "  ./update.sh --pull    # Git pull + reinstall"
        ;;
esac
