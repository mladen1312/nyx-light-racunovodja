# Changelog — Nyx Light Računovođa

## v3.1.0 (2026-02-28) — Sprint 25

### Frontend komplet — 21 stranica za 15 zaposlenika
- **10 novih module pages:** Banka, Kontiranje, Blagajna, Putni nalozi, PDV, Porez dobit, JOPPD, GFI, IOS, E-račun
- `fetchAPI()` helper s auth i error handling
- `showToast()` notifikacije
- `loadClientSelects()` auto-punjenje dropdowna
- CSS komponente: stat-card, data-table
- Keyboard shortcuts: Alt+1-6 za module
- Fix: dupli chart.js import, health endpoint path

### Sprint 24b: WebSocket + Fallback integracija
- WebSocket chat koristi Router → Executor → ChatBridge
- ChatBridge fallback koristi ModuleExecutor (radi i bez LLM-a)
- Router: `blagajn\w*` za hrvatske sufikse, poboljšana entity extraction
- Dead code cleanup: `core/module_router.py` → 16 LOC proxy
- Uklonjeni 3 dupla endpointa

### Sprint 24: Full Integration — 47 modula na LLM mozak
- **ModuleExecutor** (831 LOC): 47 handlera, svaki modul spojen na chat
- **Router** (613 LOC): 46 intent patterna, entity extraction
- **API**: 138 endpointa (100% module coverage)
- Chat flow: User → Router → Executor → Module → LLM → Response

## v3.0.0 (2026-02-27) — Sprintovi 20-23

### Sprint 23: LLM Queue + Multi-user
- Semaphore-based queue za 15 paralelnih korisnika
- Per-user rate limiting
- WebSocket autentikacija

### Sprint 22: Memory System
- 4-Tier Memory: L0 Working, L1 Episodic, L2 Semantic
- Noćna DPO optimizacija
- RLHF feedback loop

### Sprint 21: Peppol + E-račun
- AS4 protokol implementacija
- EN 16931 validator
- UBL/CII/ZUGFeRD generiranje

### Sprint 20: RAG + Zakoni
- Time-Aware RAG sustav
- Embedded vector store (SQLite-based)
- 8+ zakona RH učitano

## v2.0.0 (2026-02-26) — Sprintovi 10-19

### Highlights
- GFI XML generiranje za FINA-u
- PDV prijava + JOPPD XML
- Porez na dobit (PD obrazac)
- Obračun plaća (bruto→neto)
- Bankovni parseri (Erste, Zaba, PBZ)
- Blagajna validacija (limit 10K EUR)
- Putni nalozi + dnevnice
- Kontiranje engine (rule-based)
- Amortizacija (linearna + ubrzana)
- IOS usklađivanja

## v1.0.0 (2026-02-25) — Sprintovi 1-9

### Inicijalna arhitektura
- FastAPI + WebSocket server
- Auth sustav (JWT + RBAC)
- SQLite storage
- Vision AI integracija (Qwen2.5-VL)
- Basic chat interface
- start.sh deployment script
