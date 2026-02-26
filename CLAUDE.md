# CLAUDE.md — Nyx Light Računovođa V1.3

## Pregled
Nyx Light — Računovođa: privatni AI sustav za računovodstvo RH.
**MoE Architecture:** Qwen3-235B-A22B (235B ukupno, ~22B aktivno)
Mac Studio M3 Ultra (256 GB), 15 zaposlenika, 100% offline.

## Ključne naredbe
```bash
make first-boot       # Provjeri hardver i ovisnosti
make docker-up        # Pokreni Qdrant + Neo4j
make vllm-start       # Pokreni vLLM-MLX (Qwen 72B)
make run              # Dev server
make run-prod         # Produkcija (0.0.0.0:8000)
make test             # Testovi
make deploy           # Deploy na Mac Studio (sudo)
python -m scripts.ingest_laws    # Učitaj zakone u RAG
python -m scripts.nightly_dpo    # DPO trening
python -m scripts.backup         # Backup
```

## Arhitektura
- `src/nyx_light/api/` — FastAPI + WebSocket (chat, upload, export)
- `src/nyx_light/llm/` — vLLM-MLX inference engine
- `src/nyx_light/memory/` — 4-Tier Memory (L0 Working → L3 DPO)
- `src/nyx_light/modules/` — Računovodstveni moduli (A1-A9)
- `src/nyx_light/safety/` — OVERSEER + Tvrde granice
- `src/nyx_light/rag/` — Time-Aware RAG (zakoni RH)
- `src/nyx_light/export/` — CPP XML + Synesis CSV/JSON
- `src/nyx_light/sessions/` — 15-user session manager
- `src/nyx_light/storage/` — SQLite (bookings, corrections, audit)
- `src/nyx_light/monitoring/` — System health (RAM, disk, vLLM)
- `src/nyx_light/prompts/` — HR accounting system prompts
- `dashboard/` — Web UI (chat, moduli, upload)
- `scripts/` — Ingest, DPO, backup, first-boot
- `deploy/` — Mac Studio deploy + LaunchDaemons

## API Endpoints
- `GET /` — Dashboard UI
- `POST /api/v1/chat` — Chat s AI
- `POST /api/v1/upload` — Upload dokumenata
- `POST /bank/parse` — Parse bankovnog izvoda
- `POST /invoice/extract` — OCR računa
- `POST /booking/propose` — Prijedlog knjiženja
- `POST /booking/approve` — Odobrenje (Human-in-the-Loop)
- `POST /api/v1/booking/correct` — Ispravak → L2 memorija
- `POST /api/v1/export/{erp}` — Export u CPP/Synesis
- `GET /api/v1/sessions` — Aktivne sesije
- `GET /api/v1/bookings/pending` — Čekaju odobrenje
- `GET /api/v1/monitor` — System health
- `GET /api/v1/stats` — Statistika
- `WS /ws/chat` — Streaming chat

## Noćni procesi (LaunchDaemons)
- 02:00 — DPO trening (com.nexellum.nyx-dpo)
- 03:00 — Backup (com.nexellum.nyx-backup)

## Tvrde granice (NIKADA ne mijenjati!)
1. ZABRANA pravnog savjetovanja
2. ZABRANA autonomnog knjiženja — SVE zahtijeva "Odobri" klik
3. APSOLUTNA PRIVATNOST — zero cloud, zero external APIs
