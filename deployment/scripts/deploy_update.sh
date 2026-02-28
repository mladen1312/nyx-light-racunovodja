#!/bin/bash
# Nyx Light — Deploy Update (zero-downtime)
set -euo pipefail

PROJECT="/Users/nyx/nyx-light-racunovodja"
cd "$PROJECT"

echo "🌙 Nyx Light Deploy"
echo "$(date)"

# 1. Git pull
echo "📥 Git pull..."
git fetch origin
git reset --hard origin/main

# 2. Install dependencies (if changed)
if git diff HEAD~1 --name-only | grep -q "pyproject.toml\|requirements"; then
    echo "📦 Updating dependencies..."
    source .venv/bin/activate
    pip install -e ".[dev]" -q
fi

# 3. Run tests
echo "🧪 Testovi..."
source .venv/bin/activate
python -m pytest tests/ -q --tb=short -x
if [ $? -ne 0 ]; then
    echo "❌ Testovi pali! Deploy PREKINUT."
    exit 1
fi

# 4. Reload API (graceful — uvicorn --reload handles it)
echo "♻️  API se automatski reloada (uvicorn --reload)..."

# 5. Log
echo "✅ Deploy uspješan: $(git log -1 --oneline)"
echo "$(date) $(git log -1 --oneline)" >> /Users/nyx/nyx-data/logs/deploy.log
