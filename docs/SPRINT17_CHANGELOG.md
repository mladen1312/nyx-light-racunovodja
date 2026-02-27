# Sprint 17: Complete Software Implementation

**Datum:** 27. veljače 2026.  
**Status:** ✅ ZAVRŠEN  
**Testovi:** 866 passed  

## Metrični Pregled

| Metrika | Sprint 16 | Sprint 17 | Delta |
|---|---|---|---|
| Source LOC | 22,289 | 25,935 | +3,646 |
| Test LOC | 8,400 | 10,091 | +1,691 |
| Python files | ~90 | 107 | +17 |
| Tests passing | 791 | 866 | +75 |
| API endpoints | 40 | 58 | +18 |
| Law files | 5 | 25 | +20 |
| Modules | ~30 | 36 | +6 |

## Novi Moduli

### 1. Module Router (`src/nyx_light/router/`)
- Keyword-based intent detection (<1ms na Apple Silicon)
- 11 modula: bank_parser, invoice_ocr, kontiranje, blagajna, putni_nalozi, ios, rag, place, amortizacija, export, general
- Entity extraction: OIB, IBAN, iznos, konto, datum
- LLM-based routing pripremljen (za Qwen3 produkciju)

### 2. Payroll Calculator (`src/nyx_light/modules/place/`)
- Kompletni obračun plaća za 2026. (MIO I/II, porez, prirez, osobni odbitak)
- Bruto → neto i neto → bruto (Newton-Raphson iteracija)
- Neoporezivi primici (božićnica, dnevnice, prijevoz, prehrana)
- JOPPD generiranje (Strana B)
- Prirezi za 20+ gradova (Zagreb 18%, Split 15%, Vukovar 0%)

### 3. Knowledge Graph (`src/nyx_light/kg/`)
- Neo4j + in-memory fallback
- Kontni razredi, PDV stope, pravila kontiranja
- BFS shortest path, neighbor queries
- Klijent → Konto pravilo relacije

### 4. Prometheus Metrics (`src/nyx_light/metrics/`)
- Counter, Gauge, Histogram implementacije
- Apple Silicon specifične metrike (memory pressure, thermal, GPU)
- `/metrics` endpoint za Grafana dashboard

### 5. Law Ingestion Pipeline (`src/nyx_light/rag/ingest_laws.py`)
- YAML frontmatter parser
- Article splitter (Članak X.)
- Deterministic chunk IDs
- Batch ingestion svih 25 zakona

### 6. Embedded Vector Store (`src/nyx_light/rag/embedded_store.py`)
- Numpy cosine similarity (zamjena za Qdrant server)
- Hash-based fallback (za testove bez sentence-transformers)
- Time-aware filtering (effective_from/to)
- Pickle persistence

## Novi Zakoni (20 dodanih)
Pravilnik PDV, Fiskalizacija, OPZ, Zakon o radu, OIB, Platni promet, AML, Obvezni odnosi, JOPPD, ZTD, Neoporezivi primici, PPN, Devizno, Proračun, Revizija, Financijsko poslovanje, E-račun, Amortizacija, Porez na dobit (pravilnik), Lokalni porezi.

## Novi API Endpointi (18)
- `/api/route` — Module Router
- `/api/modules` — Lista modula
- `/api/payroll/calculate` — Obračun plaće
- `/api/payroll/neto-to-bruto` — Neto u bruto
- `/api/payroll/minimalna` — Min. plaća
- `/api/payroll/neoporezivi` — Neoporezivi limiti
- `/api/kg/stats` — KG statistike
- `/api/kg/query/{type}` — KG upit po tipu
- `/metrics` — Prometheus
- `/api/laws/ingest` — Učitaj zakone
- `/api/ingest/stats` — Email/folder watcher stats
- `/api/bank/parse` — MT940/CSV parser
- `/api/ios/generate` — IOS obrasci
- `/api/blagajna/validate` — Blagajna validacija
- `/api/putni-nalog/check` — Putni nalozi
- `/api/amortizacija/calculate` — Amortizacija
- `/api/erp/*` (5) — ERP pull endpointi

## Frontend v2
- Payroll kalkulator UI s detaljnim ispisom
- Amortizacija kalkulator s planom otpisa
- Light/dark theme toggle (persist u localStorage)
- Mobile hamburger menu
- Keyboard shortcuts (Alt+1-5, Alt+N, Esc)
- CSS charts grid za dashboard

## Apple Silicon Deploy
- `start.sh` — M3/M5 Ultra optimized deploy script
- Auto memory detection (192GB → full model, <64GB → smaller)
- LaunchDaemon plist za autostart
- Nginx SSL reverse proxy config
- Metal JIT, MALLOC_ARENA_MAX optimizacije

## Preostalo za Hardverski Deploy
- [ ] Sentence-transformers model download (384-dim)
- [ ] Qwen3-235B-A22B model download (~120GB)
- [ ] Qwen3-VL-8B model download (~8GB)
- [ ] vllm-mlx server testiranje na M3/M5 Ultra
- [ ] Real IMAP konfiguracija
- [ ] Production SSL certifikat
