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

vllm-start:  ## Pokreni vLLM-MLX server (Qwen 72B)
	mlx_lm.server \
		--model mlx-community/Qwen2.5-72B-Instruct-4bit \
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

first-boot:  ## Prvi setup (kreiranje direktorija, provjera hardvera)
	PYTHONPATH=src python -m scripts.first_boot

deploy:  ## Deploy na Mac Studio (sudo)
	sudo bash deploy/deploy_mac_studio.sh
