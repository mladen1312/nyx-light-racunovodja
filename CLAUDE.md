# CLAUDE.md — Nyx Light Računovođa

## Pregled
Ovo je repo za Nyx Light — Računovođa, privatni AI sustav za računovodstvo RH.
Vrti se na jednom Mac Studio M5 Ultra (192 GB) i opslužuje 15 zaposlenika.

## Ključne naredbe
- `python -m nyx_light.main` — pokreni server
- `pytest tests/` — pokreni testove
- `python -m scripts.first_boot` — prvi setup

## Arhitektura
- `src/nyx_light/api/` — FastAPI web sučelje
- `src/nyx_light/llm/` — vLLM-MLX inference engine
- `src/nyx_light/memory/` — 4-Tier Memory (L0-L3)
- `src/nyx_light/modules/` — Računovodstveni moduli (A1-A9)
- `src/nyx_light/safety/` — OVERSEER + Tvrde granice
- `src/nyx_light/rag/` — Time-Aware RAG (zakoni RH)

## Tvrde granice (NIKADA ne mijenjati!)
1. ZABRANA pravnog savjetovanja
2. ZABRANA autonomnog knjiženja
3. APSOLUTNA PRIVATNOST (zero cloud)
