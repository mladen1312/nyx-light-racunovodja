# Nyx Light — Računovođa: Makefile
# ═══════════════════════════════════

.PHONY: help install dev test run run-prod lint clean vllm-start vllm-stop docker-up docker-down

help:  ## Prikaži pomoć
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install:  ## Instaliraj ovisnosti
	pip install -r requirements.txt

dev:  ## Instaliraj dev ovisnosti
	pip install -r requirements.txt
	pip install pytest pytest-asyncio ruff mypy

test:  ## Pokreni testove
	PYTHONPATH=src pytest tests/ -v

run:  ## Pokreni dev server
	PYTHONPATH=src python -m nyx_light.main --reload --debug

run-prod:  ## Pokreni produkcijski server
	PYTHONPATH=src python -m nyx_light.main --host 0.0.0.0 --port 8000

lint:  ## Provjeri kod s ruff
	ruff check src/ tests/

format:  ## Formatiraj kod
	ruff format src/ tests/

vllm-start:  ## Pokreni vLLM-MLX server (Qwen3-235B MoE)
	mlx_lm.server \
		--model mlx-community/Qwen3-235B-A22B-4bit \
		--port 8080 \
		--host 127.0.0.1 \
		--max-concurrency 15

vllm-start-small:  ## Pokreni vLLM-MLX (Qwen3-30B — fallback za manje RAM-a)
	mlx_lm.server \
		--model mlx-community/Qwen3-30B-A3B-4bit \
		--port 8080 \
		--host 127.0.0.1 \
		--max-concurrency 15

vllm-stop:  ## Zaustavi vLLM-MLX server
	pkill -f "mlx_lm.server" || true

docker-up:  ## Pokreni Qdrant + Neo4j
	docker compose up -d qdrant neo4j

docker-down:  ## Zaustavi Docker servise
	docker compose down

clean:  ## Očisti cache i temp datoteke
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache .mypy_cache
	rm -f data/nyx.db-shm data/nyx.db-wal

test-quick:  ## Brzi testovi (bez API e2e)
	PYTHONPATH=src pytest tests/ --ignore=tests/test_api_e2e.py --ignore=tests/test_api_production.py -q

test-sprint:  ## Samo zadnji sprint testovi
	PYTHONPATH=src pytest tests/test_sprint24_integration.py tests/test_sprint25_frontend.py -v

stats:  ## Statistike projekta
	@echo "=== Nyx Light v3.1 ===" && \
	echo "Python source:" && find src/ -name "*.py" -not -path "*__pycache__*" | xargs wc -l | tail -1 && \
	echo "Test LOC:" && find tests/ -name "*.py" | xargs wc -l | tail -1 && \
	echo "Frontend:" && wc -l static/index.html && \
	echo "Endpoints:" && python -c "from nyx_light.api.app import app; print(len(set(r.path for r in app.routes if hasattr(r,'path') and r.path.startswith('/api/'))))"

endpoints:  ## Lista API endpointa
	@PYTHONPATH=src python -c "from nyx_light.api.app import app; [print(f'{list(r.methods-{\"HEAD\",\"OPTIONS\"})[0]:6s} {r.path}') for r in sorted(app.routes, key=lambda r: getattr(r,'path','')) if hasattr(r,'methods') and r.path.startswith('/api/')]"

status:  ## Status servisa
	./start.sh status

stop:  ## Zaustavi sve
	./start.sh stop

backup:  ## Kreiraj backup
	./start.sh backup

ingest-laws:  ## Učitaj zakone u RAG bazu
	./start.sh ingest-laws

first-boot:  ## Prvi setup (kreiranje direktorija, provjera hardvera)
	PYTHONPATH=src python -m scripts.first_boot

deploy:  ## Deploy na Mac Studio (sudo)
	sudo bash deploy/deploy_mac_studio.sh
