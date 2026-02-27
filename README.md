# 🌙 Nyx Light — Računovođa

**Privatni ekspertni AI sustav za računovodstvo i knjigovodstvo u Republici Hrvatskoj.**

Lokalni, offline AI koji radi na jednom Mac Studio M5 Ultra (192 GB RAM), opslužuje do 15 zaposlenika istovremeno — bez oblaka, bez latencije, 100% privatnost.

---

## Što sustav radi

Nyx Light obrađuje, razvrstava, predlaže i kontrolira računovodstvene dokumente. Ljudski računovođa zadržava konačni autoritet — sustav **nikada ne knjiži autonomno** (Human-in-the-Loop).

### Moduli

| Modul | Opis | Status |
|-------|------|--------|
| **A1 — Ulazni računi** | OCR skenova i PDF-ova, ekstrakcija OIB-a/PDV-a/iznosa, multi-PDV, R1/R2 | ✅ |
| **A1-EU — EU/Inozemni računi** | UBL, Peppol, ZUGFeRD, FatturaPA; reverse charge; 5 jezika; 27 EU zemalja | ✅ |
| **A2 — Izlazni računi** | Validacija, fiskalizacija JIR/ZKI | ✅ |
| **A3 — Kontiranje** | AI prijedlog konta temeljen na opisu i L2 memoriji | ✅ |
| **A4 — Bankovni izvodi** | MT940, CSV (Erste/Zaba/PBZ), auto-sparivanje po IBAN/pozivu | ✅ |
| **A5 — Blagajna** | Provjera limita gotovine (10.000 EUR), validacija | ✅ |
| **A6 — Putni nalozi** | Provjera km-naknade (0,30 EUR), nepriznati troškovi | ✅ |
| **A7 — Osnovna sredstva** | Amortizacija, obračun, praćenje | ✅ |
| **A8 — Plaće** | JOPPD, doprinosi, neoporezivi primici, bolovanja | ✅ |
| **A9 — IOS usklađivanja** | Generiranje obrazaca, praćenje povrata | ✅ |
| **B1 — PDV prijava** | Obračun, PP-PDV, ZP obrazac | ✅ |
| **B2 — Porez na dobit** | PD obrazac, pregled priznatih troškova | ✅ |
| **B3 — Porez na dohodak** | DOH obrazac | ✅ |
| **B4 — Intrastat** | EU robna razmjena, CN kodovi | ✅ |
| **C1 — RAG zakoni** | 27 zakona/pravilnika, time-aware odgovori | ✅ |
| **C2 — NN Monitor** | Automatsko praćenje Narodnih Novina za izmjene | ✅ |
| **C3 — GFI** | Financijski izvještaji, XML za eFINA | ✅ |

---

## Brzi start

### Jedan-naredba deploy

```bash
git clone https://github.com/mladen1312/nyx-light-racunovodja.git
cd nyx-light-racunovodja
chmod +x deploy.sh && ./deploy.sh
```

Deploy automatski:
1. Provjerava sustav (RAM, disk, Apple Silicon)
2. Instalira Python, Homebrew, ovisnosti
3. Kreira virtualnu okolinu s 35+ paketa
4. Postavlja baze (Qdrant, Neo4j, SQLite)
5. Skida LLM model (ovisno o RAM-u)
6. Skida embedding model za RAG
7. Skida 27 zakona/pravilnika RH
8. Konfigurira sustav i auth
9. Pokreće testove i postavlja auto-update cron

### Opcije deploya

```bash
./deploy.sh                 # Puna instalacija (~60-90 min s modelima)
./deploy.sh --skip-models   # Sve osim modela (~5 min)
./deploy.sh --models-only   # Samo LLM modeli
./deploy.sh --laws-only     # Samo zakoni RH
./deploy.sh --resume        # Nastavi prekinutu instalaciju
./deploy.sh --status        # Provjeri status
```

### Pokretanje

```bash
source .venv/bin/activate
python -m uvicorn src.nyx_light.ui.web:create_app --host 0.0.0.0 --port 8080
```

Otvori http://localhost:8080 u pregledniku. Svih 15 zaposlenika može pristupiti istovremeno.

---

## Hardver

| Komponenta | Minimum | Preporučeno |
|-----------|---------|-------------|
| Mac Studio | M4 Ultra 64GB | **M5 Ultra 192GB** |
| RAM | 64 GB | **192 GB** |
| Disk | 200 GB SSD | 500 GB SSD |
| Mreža | LAN (offline) | LAN (offline) |

### Automatski odabir modela po RAM-u

| RAM | Primarni LLM | Vision | Ukupno |
|-----|-------------|--------|--------|
| **192 GB+** | Qwen3-235B-A22B (MoE, 22B aktivno, ~124GB) | Qwen3-VL-8B (~5GB) | ~130 GB |
| **96 GB+** | Qwen2.5-72B-Instruct (~42GB) | Qwen3-VL-8B (~5GB) | ~48 GB |
| **64 GB+** | Qwen3-30B-A3B (MoE, 3B aktivno, ~18GB) | Qwen3-VL-8B (~5GB) | ~24 GB |

---

## AI Modeli

### Primarni LLM: Qwen3-235B-A22B (4-bit MLX)
- **MoE arhitektura**: 235B ukupno, samo 22B aktivno po tokenu
- Odlična podrška za hrvatski jezik
- 8K context window, temperature 0.1 za preciznost
- Continuous Batching za 15 paralelnih korisnika

### Vision: Qwen3-VL-8B-Instruct (4-bit MLX)
- **OCR u 32 jezika** uključujući HR, DE, IT, SI, FR, EN
- DeepStack arhitektura za fine-grained detalje (mali tekst na računima)
- Tolerantan na blur, tilt, low-light skenove
- Čita: PDF, JPEG, PNG, TIFF skenove

### Embedding: paraphrase-multilingual-MiniLM-L12-v2
- 384-dimenzionalni vektori
- Podržava 50+ jezika za RAG pretragu
- ~500 MB, brz i efikasan

---

## EU i Inozemni računi

Sustav automatski prepoznaje porijeklo računa i primjenjuje ispravni PDV tretman.

### Podržani formati

**Strukturirani (100% accuracy):**
- EN 16931 (EU e-faktura standard)
- Peppol BIS 3.0 (pan-europski UBL)
- ZUGFeRD 2.x / Factur-X (DE/FR/AT)
- FatturaPA (IT obavezni format)
- UBL 2.1, CII (UN/CEFACT)

**Vizualni (AI OCR):**
- Računi na HR, EN, DE, IT, SI, FR jeziku
- Automatska detekcija valute (EUR, USD, GBP, CHF, ...)
- VAT ID prepoznavanje za svih 27 EU zemalja

### Automatski PDV tretman

| Situacija | Tretman | Članak ZPDV |
|-----------|---------|------------|
| HR → HR | Standardni PDV | — |
| EU → HR (reverse charge) | Obratni obračun | čl. 75/1/6 |
| EU → HR (roba) | EU stjecanje | čl. 4/1/2 |
| Treća zemlja → HR | Uvoz (JCD) | čl. 32 |
| Non-EUR valuta | Automatski traži HNB tečaj | — |

---

## RAG — Pravna baza znanja

### 27 Zakona i pravilnika

**Prioritet 1 — Kritični:**
1. Zakon o PDV-u (NN 73/13 + 14 izmjena)
2. Zakon o računovodstvu (NN 78/15 + 6 izmjena)
3. Zakon o porezu na dobit (NN 177/04 + 15 izmjena)
4. Zakon o porezu na dohodak (NN 115/16 + 7 izmjena)
5. Zakon o doprinosima (NN 84/08 + 12 izmjena)
6. Pravilnik o PDV-u (NN 79/13 + 15 izmjena)
7. Pravilnik o porezu na dobit (NN 95/05 + 18 izmjena)
8. Pravilnik o porezu na dohodak (NN 10/17 + 12 izmjena)
9. Pravilnik o JOPPD (NN 32/15 + 8 izmjena)
10. Pravilnik o neoporezivim primicima (NN 1/23)
11. Neoporezivi osobni odbitak i porezne stope (NN 9/25)

**Prioritet 2 — Važni:**
12. Zakon o fiskalizaciji (NN 133/12)
13. Opći porezni zakon (NN 115/16)
14. Zakon o radu (NN 93/14)
15. Zakon o trgovačkim društvima (NN 111/93)
16. Zakon o obrtu (NN 143/13)
17. HSFI standardi (NN 86/15)
18. Pravilnik o amortizaciji (NN 1/01)
19. Pravilnik o kontnom planu (NN 95/16)
20. Pravilnik o doprinosima (NN 2/09)
21. Uredba o minimalnoj plaći (NN 156/23)
22. RRiF-ov kontni plan

**Prioritet 3 — Korisni:**
23. Zakon o provedbi ovrhe (NN 68/18)
24. Pravilnik o e-Računu (NN 1/19)

### Time-Aware odgovori

RAG sustav zna **koja verzija zakona je vrijedila u kojem trenutku**. Pitanje o PDV-u iz 2023. daje odgovor temeljen na zakonu koji je tada bio na snazi.

### Auto-update iz Narodnih Novina

Svake nedjelje u 03:00, sustav automatski:
1. Provjerava Narodne Novine za nove brojeve
2. Filtrira samo zakone bitne za računovodstvo (27 ključnih riječi)
3. Skida nove izmjene
4. Ažurira RAG vektorsku bazu
5. Logira sve promjene

```bash
./update.sh --check-nn     # Ručna provjera NN
./update.sh --laws          # Update zakona
./update.sh --auto          # Automatski (za cron)
./update.sh --status        # Status sustava
```

---

## Arhitektura

```
┌─────────────────────────────────────────────────────┐
│  15 zaposlenika (Browser → http://server:8080)      │
└──────────────┬──────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────┐
│  FastAPI + WebSocket (Chat, Approval, Dashboard)     │
│  Auth (JWT, 12h token, audit log)                    │
└──────────────┬──────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────┐
│  Chat Bridge → vLLM-MLX (Qwen3-235B-A22B)           │
│  + RAG kontekst (zakoni) + L2 memorija (pravila)     │
│  + L1 memorija (današnje interakcije)                │
└──────────────┬──────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────┐
│  Booking Pipeline (pending → approval → export)      │
│  ┌──────┐ ┌──────┐ ┌────┐ ┌───────┐ ┌─────┐       │
│  │OCR+EU│ │Banka │ │Plaće│ │Blagajna│ │Putni│ ...   │
│  │14 reg│ │MT940 │ │JOPPD│ │Limiti │ │km   │       │
│  └──┬───┘ └──┬───┘ └──┬─┘ └──┬────┘ └──┬──┘       │
│     └────────┴────────┴──────┴─────────┘            │
│                       │                              │
│              Kontiranje (AI + L2 memorija)            │
│                       │                              │
│              OVERSEER (tvrde granice)                 │
└──────────────┬──────────────────────────────────────┘
               │ ✅ Odobri / ❌ Odbij / ✏️ Ispravi
┌──────────────▼──────────────────────────────────────┐
│  ERP Export: CPP (XML) / Synesis (CSV/JSON)          │
└─────────────────────────────────────────────────────┘
```

### Memorija (4-Tier)

| Tier | Opis | Trajanje |
|------|------|----------|
| L0 — Working | Trenutni ispravak u chatu | Sesija |
| L1 — Episodic | Dnevnik današnjih interakcija | 30 dana |
| L2 — Semantic | Trajna pravila kontiranja | Zauvijek |
| Noćni DPO | Optimizacija modela iz odobrenih knjiženja | Noćno |

### Baze podataka

| Baza | Svrha | Obavezna |
|------|-------|----------|
| **Qdrant** | Vektorska pretraga zakona (RAG) | ✅ |
| **SQLite** | Memorija, DPO, auth, audit log | ✅ |
| **Neo4j** | Knowledge graph (entiteti, relacije) | Opcionalno |

---

## Sigurnost

- **100% lokalno** — nema cloud API poziva, nema slanja podataka van ureda
- **Zero cloud dependency** — radi offline
- **Auth** — JWT tokeni, 12h istek, 5 krivih pokušaja → 15 min lockout
- **Audit log** — svaka akcija se bilježi
- **Tvrde granice:**
  - Zabrana pravnog savjetovanja izvan računovodstva
  - Zabrana autonomnog knjiženja — uvijek Human-in-the-Loop
  - Zabrana pristupa vanjskim API-jima

---

## Struktura projekta

```
nyx-light-racunovodja/
├── deploy.sh                    # One-file deploy (sve 9 faza)
├── update.sh                    # Auto-update zakoni + modeli
├── config.json                  # Konfiguracija sustava
├── src/nyx_light/
│   ├── app.py                   # Centralna klasa (NyxLightApp)
│   ├── main.py                  # Entry point (FastAPI server)
│   ├── pipeline/                # Booking pipeline (pending→approve→export)
│   ├── llm/                     # Chat bridge + system prompt
│   ├── vision/                  # Vision AI (Qwen3-VL-8B)
│   ├── rag/
│   │   ├── legal_rag.py         # Time-Aware RAG (centralna klasa)
│   │   ├── law_downloader.py    # 27 zakona, auto-download
│   │   ├── nn_monitor.py        # Narodne Novine praćenje
│   │   ├── law_loader.py        # Chunking po člancima
│   │   └── qdrant_store.py      # Vektorska baza
│   ├── modules/
│   │   ├── invoice_ocr/
│   │   │   ├── extractor.py     # HR računi (14 regex, OIB validacija)
│   │   │   └── eu_invoice.py    # EU/inozemni (UBL, Peppol, ZUGFeRD...)
│   │   ├── bank_parser/         # MT940, CSV (Erste/Zaba/PBZ)
│   │   ├── kontiranje/          # AI kontiranje + kontni plan
│   │   ├── payroll/             # Plaće, JOPPD
│   │   ├── blagajna/            # Gotovinski limiti
│   │   ├── putni_nalozi/        # Km-naknada, nepriznati troškovi
│   │   ├── osnovna_sredstva/    # Amortizacija
│   │   ├── pdv_prijava/         # PP-PDV
│   │   ├── porez_dobit/         # PD obrazac
│   │   ├── intrastat/           # EU robna razmjena
│   │   └── ...                  # 30+ modula ukupno
│   ├── auth/                    # JWT + role-based access
│   ├── memory/                  # 4-Tier memory system
│   ├── finetune/                # Noćni DPO optimizator
│   ├── model_manager/           # Model catalog + safe swap
│   ├── safety/                  # OVERSEER hard boundaries
│   ├── erp/                     # CPP + Synesis konektori
│   ├── export/                  # XML/CSV/JSON export
│   └── ui/                      # FastAPI + WebSocket UI
├── tests/                       # 509 testova
├── data/
│   ├── models/                  # LLM + Vision + Embedding
│   ├── laws/                    # 27 zakona (txt)
│   ├── rag_db/                  # Qdrant vektori
│   ├── memory_db/               # L1+L2 memorija
│   ├── dpo_datasets/            # DPO preference parovi
│   └── logs/                    # Logovi sustava
└── scripts/                     # Pomoćne skripte
```

---

## Testovi

```bash
source .venv/bin/activate
python -m pytest tests/ -v              # Svi testovi (509)
python -m pytest tests/ -v -k "eu"      # Samo EU invoice testovi
python -m pytest tests/ -v -k "rag"     # Samo RAG testovi
python -m pytest tests/ -v -k "sprint13" # Sprint 13 testovi (40)
```

---

## Update sustava

### Automatski (cron)
Svake nedjelje u 03:00, `update.sh --auto` automatski:
- Provjerava Narodne Novine za izmjene zakona
- Skida nove verzije zakona i pravilnika
- Ažurira RAG vektorsku bazu
- Provjerava dostupnost novih verzija LLM modela

### Ručno
```bash
./update.sh                 # Interaktivno (zakoni + modeli + NN)
./update.sh --laws          # Samo zakoni
./update.sh --check-nn      # Provjeri Narodne Novine
./update.sh --models        # Provjeri modele
./update.sh --force         # Forsiraj update svega
./update.sh --rollback      # Vrati prethodni model
./update.sh --status        # Status sustava
```

### Znanje se ne gubi pri update-u
Svi podaci ostaju intaktni:
- L1+L2 memorija, DPO dataseti, LoRA adapteri
- RAG vektorska baza, auth baza, konfiguracija
- `update.sh` automatski verificira integritet prije i poslije

---

## Licenca

Privatni sustav — © 2026 Dr. Mladen Mešter | Nexellum Lab d.o.o.
