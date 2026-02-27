# 🌙 Nyx Light — Računovođa

**Privatni ekspertni AI sustav za računovodstvo i knjigovodstvo u Republici Hrvatskoj.**

Nyx Light radi 100% lokalno na jednom Mac Studio M5 Ultra (192 GB RAM), opslužuje do 15 zaposlenika istovremeno, bez ijednog poziva prema cloudu. Svi OIB-ovi, plaće i poslovne tajne ostaju unutar ureda.

---

## Ključne sposobnosti

| Kategorija | Što radi |
|---|---|
| **OCR računa** | Čita skenirane račune (HR + EU + inozemni), PDF, slike — izvlači OIB, iznose, PDV |
| **EU e-fakture** | Parsira UBL 2.1, Peppol BIS 3.0, ZUGFeRD/Factur-X, FatturaPA, EN 16931, CII |
| **Reverse charge** | Automatski detektira obrnuto oporezivanje (čl. 75 ZPDV) za EU račune |
| **Bankovni izvodi** | MT940 + CSV parseri (Erste, Zaba, PBZ), sparivanje s otvorenim stavkama |
| **Kontiranje** | AI predlaže konto, računovođa odobrava (Human-in-the-Loop) |
| **Plaće** | Obračun bruto→neto, doprinosi, osobni odbitak 2024/2025, JOPPD XML |
| **PDV prijava** | Automatski PDV-S obrazac iz odobrenih knjiženja |
| **Porez na dobit/dohodak** | Priprema obrasca PD i DOH |
| **Blagajna** | Validacija limita (10.000 EUR), kontrola ispravnosti |
| **Putni nalozi** | Provjera km-naknade (0,30 EUR/km), reprezentacija |
| **Osnovna sredstva** | Amortizacija po HR stopama, evidencija |
| **IOS usklađivanja** | Generiranje IOS obrazaca, praćenje povrata |
| **GFI/FINA** | Priprema GFI-POD XML za eFINA |
| **Intrastat** | Provjera pragova i kreiranje Intrastat prijava |
| **Fakturiranje** | Izdavanje računa za knjigovodstvene usluge |
| **Likvidacija** | Vođenje postupka likvidacije društva |
| **Kadrovska** | Evidencija zaposlenika, godišnji odmor, staž |
| **RAG zakoni** | 27 zakona/pravilnika RH u vektorskoj bazi s vremenskim kontekstom |
| **NN monitor** | Automatsko praćenje Narodnih Novina za izmjene zakona |
| **Memorija** | 4-Tier sustav učenja iz ispravaka (L0→L3 + noćni DPO) |
| **CPP/Synesis** | Izvoz u XML/CSV/JSON formate za oba ERP sustava |

---

## Arhitektura

```
┌─────────────────────────────────────────────────────────────────┐
│                    WEB UI (15 korisnika)                        │
│              /chat  /pending  /approve  /dashboard              │
├─────────────────────────────────────────────────────────────────┤
│                     FastAPI Backend                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────────┐  │
│  │  Chat    │  │ Pipeline │  │ Approval │  │  ERP Export   │  │
│  │  Bridge  │  │ (HITL)   │  │ Workflow │  │  CPP/Synesis  │  │
│  └────┬─────┘  └────┬─────┘  └──────────┘  └───────────────┘  │
│       │              │                                          │
│  ┌────┴──────────────┴──────────────────────────────────────┐  │
│  │              MODULI (31 modul)                            │  │
│  │  OCR · EU Invoice · Banka · Kontiranje · Plaće · PDV     │  │
│  │  Blagajna · Putni · OS · IOS · GFI · Intrastat · JOPPD  │  │
│  │  Fakturiranje · Likvidacija · Kadrovska · KPI · ...      │  │
│  └──────────────────────────────────────────────────────────┘  │
│       │              │              │                           │
│  ┌────┴────┐  ┌──────┴──────┐  ┌───┴──────────────────────┐   │
│  │ Vision  │  │   LegalRAG  │  │   4-Tier Memory          │   │
│  │ Qwen3-  │  │   27 zakona │  │   L0 Working → L3 DPO   │   │
│  │ VL-8B   │  │   + NN Mon  │  │   + Semantic Memory      │   │
│  └─────────┘  └─────────────┘  └──────────────────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│              vllm-mlx Inference Engine                          │
│         Qwen3-235B-A22B (MoE, 22B active params)              │
│         Continuous Batching + PagedAttention                    │
├─────────────────────────────────────────────────────────────────┤
│              Mac Studio M5 Ultra — 192 GB RAM                  │
│              Sve 100% lokalno. Zero cloud.                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## Brza instalacija

### Preduvjeti
- Mac Studio M5 Ultra (192 GB) ili Mac s Apple Silicon (min. 64 GB)
- macOS 14+ ili Ubuntu 22.04+
- Python 3.12+

### One-File Deploy

```bash
git clone https://github.com/mladen1312/nyx.git
cd nyx
chmod +x deploy.sh
./deploy.sh
```

Deploy.sh automatski:
1. Detektira RAM i bira optimalni model (192GB→Qwen3-235B, 96GB→Qwen2.5-72B, 64GB→Qwen3-30B)
2. Instalira Python okruženje + 35 paketa
3. Podiže Qdrant vektorsku bazu
4. Skida LLM + Vision model (~60-90 min za prvi put)
5. Skida 27 zakona/pravilnika RH
6. Kreira konfiguraciju i auth bazu
7. Pokreće testove
8. Postavlja cron za tjedni auto-update

### Opcije deploy.sh

```bash
./deploy.sh                 # Puna instalacija
./deploy.sh --skip-models   # Sve osim modela (~5 min)
./deploy.sh --models-only   # Samo modeli (~60 min)
./deploy.sh --laws-only     # Samo zakoni RH
./deploy.sh --resume        # Nastavi prekinutu instalaciju
./deploy.sh --status        # Provjeri status
```

### Pokretanje

```bash
source .venv/bin/activate
python -m nyx_light.main --host 0.0.0.0 --port 8000
```

Otvori `http://localhost:8000` u pregledniku.

---

## Auto-Update sustav

Nyx Light automatski prati izmjene zakona putem Narodnih Novina i ažurira RAG bazu.

### Tjedni cron (automatski postavljen)
```
# Svake nedjelje u 03:00 — provjera NN + update zakona
0 3 * * 0 /path/to/update.sh --auto >> /path/to/data/logs/update.log 2>&1
```

### Ručni update

```bash
./update.sh                # Interaktivno: NN + zakoni + modeli
./update.sh --auto         # Tiho (za cron)
./update.sh --laws         # Samo zakoni
./update.sh --check-nn     # Provjeri Narodne Novine
./update.sh --models       # Provjeri modele
./update.sh --force        # Forsiraj sve
./update.sh --rollback     # Vrati prethodni model
./update.sh --status       # Status sustava
```

### Što se ažurira
- **27 zakona/pravilnika** — automatski download novih verzija
- **NN Monitor** — skenira narodne-novine.nn.hr za izmjene
- **RAG baza** — re-indeksira nove verzije zakona
- **Znanje se NE gubi** — memorija, DPO, LoRA, auth ostaju intaktni

---

## Zakoni u sustavu (27)

### Prioritet 1 — Kritični (10)
| # | Zakon/Pravilnik | NN |
|---|---|---|
| 1 | Zakon o PDV-u | NN 73/13 + 14 izmjena |
| 2 | Zakon o računovodstvu | NN 78/15 + 6 izmjena |
| 3 | Zakon o porezu na dobit | NN 177/04 + 15 izmjena |
| 4 | Zakon o porezu na dohodak | NN 115/16 + 7 izmjena |
| 5 | Zakon o doprinosima | NN 84/08 + 12 izmjena |
| 6 | Pravilnik o PDV-u | NN 79/13 + 16 izmjena |
| 7 | Pravilnik o porezu na dobit | NN 95/05 + 17 izmjena |
| 8 | Pravilnik o porezu na dohodak | NN 10/17 + 12 izmjena |
| 9 | Pravilnik o JOPPD | NN 32/15 + 7 izmjena |
| 10 | Pravilnik o neoporezivim primicima | NN 1/23 + 1 izmjena |

### Prioritet 2 — Važni (8)
| # | Zakon/Pravilnik | NN |
|---|---|---|
| 11 | Zakon o fiskalizaciji | NN 133/12 |
| 12 | Opći porezni zakon | NN 115/16 |
| 13 | Zakon o radu | NN 93/14 |
| 14 | Zakon o trgovačkim društvima | NN 111/93 |
| 15 | Zakon o obrtu | NN 143/13 |
| 16 | Pravilnik o amortizaciji | NN 1/01 |
| 17 | Pravilnik o kontnom planu | NN 95/16 |
| 18 | Pravilnik o doprinosima | NN 2/09 |

### Prioritet 3 — Korisni (9)
| # | Zakon/Pravilnik | NN |
|---|---|---|
| 19 | Pravilnik o e-Računu | NN 1/19 |
| 20 | HSFI standardi | NN 86/15 |
| 21 | RRiF kontni plan 2024 | — |
| 22 | Zakon o provedbi ovrhe | NN 68/18 |
| 23 | Uredba o minimalnoj plaći | NN 156/23 |
| 24 | Neoporezivi osobni odbitak | NN 9/25 |
| 25-27 | Dodatni pravilnici i standardi | — |

---

## EU / Inozemni računi

Nyx Light prepoznaje račune iz svih EU zemalja i trećih država:

### Strukturirani formati (100% točnost)
- **EN 16931** — EU standard za e-račune
- **Peppol BIS 3.0** — pan-europski UBL format
- **ZUGFeRD 2.x / Factur-X** — DE/FR/AT hibridni PDF+XML
- **FatturaPA** — IT obavezni XML format
- **UBL 2.1** — generički
- **CII** — UN/CEFACT Cross Industry Invoice

### Vizualni OCR (AI)
- Jezici: hrvatski, engleski, njemački, talijanski, slovenski, francuski
- Valute: EUR, USD, GBP, CHF, CZK, PLN, HUF, RON, BGN, SEK, DKK, NOK
- VAT ID validacija za svih 27 EU zemalja

### Automatski PDV tretman
| Situacija | Tretman | Temelj |
|---|---|---|
| Stjecanje robe iz EU | Reverse charge | Čl. 4.1.2 ZPDV |
| Primanje usluge iz EU | Reverse charge | Čl. 17.1 ZPDV |
| Uvoz iz trećih zemalja | Carinska prijava | Čl. 7 ZPDV |
| Reverse charge | Obrnuto oporezivanje | Čl. 75 ZPDV |

---

## AI Modeli

| Model | Uloga | Veličina | RAM |
|---|---|---|---|
| Qwen3-235B-A22B | Logika, kontiranje, savjeti | ~124 GB | 192 GB |
| Qwen2.5-72B-Instruct | Alternativa za 96 GB | ~42 GB | 96 GB |
| Qwen3-30B-A3B | Alternativa za 64 GB | ~18 GB | 64 GB |
| Qwen3-VL-8B-Instruct | Vision OCR (skenovi, računi) | ~5 GB | +5 GB |
| MiniLM-L12-v2 | Embedding za RAG | ~500 MB | +500 MB |

Svi modeli su kvantizirani za Apple Silicon MLX.

---

## 4-Tier Memory sustav

```
L0 (Working)   → Trenutni ispravak u chatu (nestaje nakon sesije)
L1 (Episodic)  → Dnevnik interakcija (sprječava ponavljanje grešaka)
L2 (Semantic)  → Trajna pravila ("Klijent X → konto Y za dobavljača Z")
L3 (DPO)       → Noćna optimizacija modela iz odobrenih knjiženja
```

AI uči iz svakog ispravka koji računovođa napravi, bez programiranja.

---

## Sigurnosne granice

- **Zero cloud** — nijedan bajt ne napušta lokalni stroj
- **Human-in-the-Loop** — ništa ne ulazi u CPP/Synesis bez klika "Odobri"
- **Nema pravnog savjetovanja** — odbija ugovore, tužbe, radno pravo
- **Audit trail** — svaki klik, svaki ispravak, svaki izvoz je zapisan
- **RBAC** — role-based pristup (admin, računovođa, asistent)
- **OIB zaštita** — OIB-ovi, plaće i poslovne tajne nikad ne izlaze iz sustava

---

## Struktura projekta

```
nyx/
├── deploy.sh                    # One-file instalacija
├── update.sh                    # Auto-update zakoni + modeli
├── README.md                    # Ovaj dokument
├── pyproject.toml               # Python konfiguracija
├── src/nyx_light/
│   ├── app.py                   # Centralna klasa (NyxLightApp)
│   ├── main.py                  # FastAPI entry point
│   ├── pipeline/                # Booking Pipeline + Approval
│   ├── llm/chat_bridge.py       # LLM Chat Bridge (vllm-mlx)
│   ├── vision/pipeline.py       # Vision AI (Qwen3-VL-8B)
│   ├── rag/
│   │   ├── legal_rag.py         # Time-Aware RAG (Qdrant)
│   │   ├── law_downloader.py    # Download 27 zakona RH
│   │   ├── law_loader.py        # Chunking po člancima
│   │   ├── nn_monitor.py        # Narodne Novine auto-monitor
│   │   └── qdrant_store.py      # Qdrant vektorska baza
│   ├── memory/                  # 4-Tier Memory (L0-L3)
│   ├── model_manager/           # Model catalog + download + upgrade
│   ├── modules/
│   │   ├── invoice_ocr/         # OCR + EU Invoice Recognition
│   │   ├── bank_parser/         # MT940 + CSV parseri
│   │   ├── kontiranje/          # Kontni plan + AI prijedlog
│   │   ├── payroll/             # Plaće, doprinosi, JOPPD
│   │   ├── pdv_prijava/         # PDV-S obrazac
│   │   ├── porez_dobit/         # PD obrazac
│   │   ├── porez_dohodak/       # DOH obrazac
│   │   ├── blagajna/            # Blagajna validator
│   │   ├── putni_nalozi/        # Putni nalozi checker
│   │   ├── osnovna_sredstva/    # Amortizacija
│   │   ├── ios_reconciliation/  # IOS obrasci
│   │   ├── gfi_xml/             # GFI-POD za eFINA
│   │   ├── gfi_prep/            # GFI priprema
│   │   ├── intrastat/           # Intrastat prijave
│   │   ├── joppd/               # JOPPD XML
│   │   ├── fakturiranje/        # Izdavanje računa
│   │   ├── likvidacija/         # Postupak likvidacije
│   │   ├── kadrovska/           # Evidencija zaposlenika
│   │   ├── bolovanje/           # Bolovanja
│   │   ├── drugi_dohodak/       # Drugi dohodak
│   │   ├── novcani_tokovi/      # Cash flow
│   │   ├── kpi/                 # Financijski KPI
│   │   └── ...                  # 31 modul ukupno
│   ├── export/                  # ERP Export (CPP XML, Synesis CSV)
│   ├── erp/                     # ERP Connectors
│   ├── registry/                # Client Registry
│   ├── auth/                    # RBAC autentikacija
│   ├── safety/                  # OVERSEER + Hard Boundaries
│   ├── finetune/                # Nightly DPO optimization
│   ├── ui/web.py                # Web UI (FastAPI + WebSocket)
│   ├── ingest/                  # IMAP, Watch Folder, API
│   └── monitoring/              # Health, metrics, alerts
├── tests/                       # 509+ testova
│   ├── test_sprint13_deploy_eu.py
│   ├── test_full_suite.py
│   └── ...
├── data/
│   ├── models/                  # LLM + Vision + Embeddings
│   ├── laws/                    # 27 zakona (.txt)
│   ├── rag_db/                  # Qdrant vektori
│   ├── memory_db/               # L1+L2 SQLite
│   ├── dpo_datasets/            # DPO preference parovi
│   └── logs/                    # Logovi
└── scripts/                     # Pomoćne skripte
```

---

## Testiranje

```bash
source .venv/bin/activate

# Svi testovi
python -m pytest tests/ -v

# Samo Sprint 13 (deploy, EU, NN, RAG)
python -m pytest tests/test_sprint13_deploy_eu.py -v

# S pokrivanjem koda
python -m pytest tests/ --cov=src/nyx_light --cov-report=term-missing
```

Trenutni status: **509 testova, svi prolaze.**

---

## API Endpoints

```
POST /chat                    → AI chat (pitanja, kontiranje, savjeti)
GET  /pending                 → Lista pending knjiženja
POST /approve/{id}            → Odobri knjiženje
POST /reject/{id}             → Odbij knjiženje
POST /correct/{id}            → Ispravi i odobri
POST /process/invoice         → Obradi ulazni račun (HR + EU)
POST /process/bank-statement  → Obradi bankovni izvod
POST /process/payroll         → Obračunaj plaće
GET  /export/{client_id}      → Export u CPP/Synesis
GET  /dashboard               → KPI i statistike
GET  /clients                 → Lista klijenata
GET  /health                  → Health check
```

---

## Licenca

Privatni softver. © 2026 Dr. Mladen Mešter | Nexellum Lab d.o.o.

Sva prava pridržana. Neovlašteno korištenje, kopiranje ili distribucija je zabranjeno.
