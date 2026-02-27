# 🌙 Nyx Light — Računovođa

> **Privatni ekspertni AI sustav za računovodstvo i knjigovodstvo u RH**

![Python](https://img.shields.io/badge/python-3.12+-blue)
![Tests](https://img.shields.io/badge/tests-509%20passing-brightgreen)
![Modules](https://img.shields.io/badge/moduli-31-orange)
![Laws](https://img.shields.io/badge/zakoni%20RH-27-red)
![Lines](https://img.shields.io/badge/LOC-17.642-lightgrey)
![License](https://img.shields.io/badge/licenca-privatna-black)

Nyx Light radi **100% lokalno** na jednom Mac Studio M5 Ultra (192 GB RAM), opslužuje do **15 zaposlenika** istovremeno. Zero cloud dependency — svi OIB-ovi, plaće i poslovne tajne ostaju isključivo na vašem hardveru.

**Sustav predlaže, čovjek odobrava.** Nijedan podatak ne ulazi u CPP ili Synesis bez eksplicitnog klika "Odobri" (Human-in-the-Loop).

---

## 📋 Sadržaj

1. [Što sustav radi](#-što-sustav-radi)
2. [Brza instalacija](#-brza-instalacija)
3. [Arhitektura](#-arhitektura)
4. [AI Modeli](#-ai-modeli)
5. [Moduli (31)](#-moduli-31)
6. [Zakoni RH (27)](#-zakoni-rh-27)
7. [EU i inozemni računi](#-eu-i-inozemni-računi)
8. [4-Tier Memory (učenje)](#-4-tier-memory-učenje)
9. [Auto-Update sustav](#-auto-update-sustav)
10. [API Endpointi](#-api-endpointi)
11. [Deployment](#-deployment)
12. [Testovi](#-testovi)
13. [Sigurnost](#-sigurnost)
14. [Changelog](#-changelog)

---

## 🎯 Što sustav radi

| Faza | Opis | Primjeri modula |
|------|------|-----------------|
| **A — Automatizacija** | Veliki volumen, brzi ROI | OCR računa, Bankovni izvodi, IOS usklađivanja |
| **B — Ekspertna asistencija** | AI predlaže, čovjek odobrava | Kontiranje, Osnovna sredstva, Blagajna, Putni nalozi |
| **C — Porezna prijava** | Priprema obrazaca za PU | PDV-S, PD, DOH, JOPPD, GFI-POD |
| **D — Pravna baza** | RAG s vremenskim kontekstom | 27 zakona RH, Narodne Novine monitor |
| **E — Učenje** | Automatsko poboljšanje iz ispravaka | 4-Tier Memory, noćni DPO fine-tune |

### Tipičan radni tok

```
1. Zaposlenik skenira/uploada račun (PDF, slika, XML)
2. Vision AI čita dokument → OCR u strukturirane podatke
3. Modul obrađuje (npr. Invoice OCR izvlači OIB, iznos, PDV)
4. AI predlaže kontiranje na temelju povijesti i pravila
5. Računovođa pregledava → Odobri / Ispravi / Odbij
6. Odobreno knjiženje → eksport u CPP ili Synesis (XML/CSV)
7. Memorija pamti ispravak → sljedeći put točnije
```

---

## 🚀 Brza instalacija

```bash
git clone https://github.com/mladen1312/nyx-light-racunovodja.git
cd nyx-light-racunovodja
chmod +x deploy.sh
./deploy.sh
```

Deploy automatski:
1. Detektira RAM → bira optimalni model (192GB→Qwen3-235B, 96GB→Qwen2.5-72B, 64GB→Qwen3-30B)
2. Kreira Python venv + instalira 35 paketa
3. Podiže Qdrant vektorsku bazu
4. Skida LLM + Vision model s HuggingFace (~60-90 min prvi put)
5. Skida 27 zakona/pravilnika RH u RAG bazu
6. Kreira konfiguraciju, auth bazu, log direktorije
7. Pokreće 509 testova za verifikaciju
8. Postavlja cron za tjedni auto-update (nedjelja 03:00)

### Deploy opcije

```bash
./deploy.sh                 # Kompletna instalacija
./deploy.sh --skip-models   # Sve osim LLM modela (~5 min)
./deploy.sh --models-only   # Samo preuzimanje modela (~60 min)
./deploy.sh --laws-only     # Samo zakoni RH za RAG
./deploy.sh --resume        # Nastavi prekinutu instalaciju
./deploy.sh --status        # Prikaži status instalacije
```

### Pokretanje servera

```bash
source .venv/bin/activate
python -m nyx_light.main --host 0.0.0.0 --port 8000
```

Otvoriti `http://mac-studio.local:8000` u pregledniku (do 15 korisnika).

---

## 🏗 Arhitektura

```
┌───────────────────────────────────────────────────────────────────┐
│                    Web UI  ×  15 korisnika                        │
│            /chat  /pending  /approve  /dashboard  /upload         │
├────────────────────────────┬──────────────────────────────────────┤
│        FastAPI + WS        │          Pipeline (HITL)             │
│     ChatBridge (LLM) ──────┤  pending → approve → export         │
│                            │  + Overseer (safety boundaries)      │
├────────────────────────────┴──────────────────────────────────────┤
│                                                                    │
│   ┌─ A ─────────────┐  ┌─ B ─────────────┐  ┌─ C ──────────┐    │
│   │ A1  Invoice OCR  │  │ A3  Kontiranje  │  │ C1  PDV-S    │    │
│   │ A1+ EU Invoice   │  │ A7  Osn.sredstva│  │ C2  Dobit    │    │
│   │ A4  Banka MT940  │  │ A5  Blagajna    │  │ C3  Dohodak  │    │
│   │ A9  IOS          │  │ A6  Putni nalozi│  │ C4  GFI      │    │
│   │ A2  Izlaz.računi │  │ B1  Plaće       │  │ C5  GFI-XML  │    │
│   └──────────────────┘  │ B2  Bolovanja   │  │ C6  Intrastat│    │
│                          │ B3  Drugi doh.  │  │     JOPPD    │    │
│                          └─────────────────┘  └──────────────┘    │
│                                                                    │
│   ┌─ D ─────────────┐  ┌─ E ─────────────┐  ┌─ F ──────────┐    │
│   │ RAG (27 zakona)  │  │ L0  Working     │  │ CPP Export   │    │
│   │ + NN Monitor     │  │ L1  Episodic    │  │ Synesis Exp. │    │
│   │ + Embeddings     │  │ L2  Semantic    │  │ Excel/CSV    │    │
│   │ + Time-Aware     │  │ L3  DPO Nightly │  │ JSON/XML     │    │
│   └──────────────────┘  └─────────────────┘  └──────────────┘    │
│                                                                    │
├────────────────────────────────────────────────────────────────────┤
│   vllm-mlx  ·  Continuous Batching  ·  PagedAttention              │
│   Qwen3-235B-A22B (logic) + Qwen3-VL-8B (vision) + MiniLM (emb)  │
├────────────────────────────────────────────────────────────────────┤
│              Mac Studio M5 Ultra  ·  192 GB Unified Memory         │
│              macOS  ·  Apple Silicon  ·  Zero Cloud                │
└────────────────────────────────────────────────────────────────────┘
```

---

## 🤖 AI Modeli

Deploy skripta automatski bira model prema RAM-u:

| RAM | Primarni LLM | Active Params | VRAM | Kontekst |
|-----|-------------|---------------|------|----------|
| **192 GB** | Qwen3-235B-A22B (MoE) | 22B | ~124 GB | 128K |
| **96 GB** | Qwen2.5-72B-Instruct | 72B (dense) | ~42 GB | 128K |
| **64 GB** | Qwen3-30B-A3B (MoE) | 3B | ~18 GB | 128K |

| Pomoćni | Uloga | VRAM |
|---------|-------|------|
| **Qwen3-VL-8B-Instruct** | Vision OCR (32 jezika, skenovi, računi) | ~5 GB |
| **MiniLM-L12-v2** | Embedding za RAG semantic search | ~500 MB |

**Zašto Qwen3-235B-A22B?**
- MoE arhitektura: 235B parametara ali samo 22B aktivno → brzina 30B modela s razumijevanjem 200B+ modela
- Izvrsna tokenizacija i razumijevanje hrvatskog jezika
- 128K kontekst → čitav zakon u jednom promptu
- 4-bit MLX kvantizacija → stane u 124 GB unified memory

---

## 🧩 Moduli (31)

### Faza A — Automatizacija (Quick Wins)

| Modul | Opis | Ključne značajke |
|-------|------|-------------------|
| **A1 — Invoice OCR** | Čitanje HR računa | 14 regex patterna, OIB validacija (ISO 7064 mod 11,10), multi-PDV (5%, 13%, 25%), eRačun XML |
| **A1-EU — EU Invoice** | Čitanje EU/inozemnih računa | UBL 2.1, Peppol BIS 3.0, ZUGFeRD, FatturaPA, EN 16931, CII; 27 EU zemalja VAT ID; reverse charge detekcija |
| **A2 — Izlazni računi** | Validacija izlaznih računa | R1/R2 provjera, fiskalizacija (JIR/ZKI), kontrola OIB-a kupca |
| **A4 — Bankovni izvodi** | Parsiranje izvoda | MT940 parser (Erste, Zaba, PBZ), CSV parser, IBAN sparivanje s otvorenim stavkama |
| **A9 — IOS usklađivanja** | Otvorene stavke | Generiranje IOS obrazaca, praćenje povrata emailom, Excel radna lista razlika |

### Faza B — Ekspertna asistencija

| Modul | Opis | Ključne značajke |
|-------|------|-------------------|
| **A3 — Kontiranje** | AI prijedlog konta | Učenje iz povijesti (L2 memorija), RRiF kontni plan, predlaže → računovođa odobrava |
| **A5 — Blagajna** | Gotovinski promet | Kontrola limita 10.000 EUR, dnevnik blagajne, automatska revizija |
| **A6 — Putni nalozi** | Službena putovanja | Km-naknada 0,30 EUR/km, dnevnice (HR + inozemstvo), provjera reprezentacije |
| **A7 — Osnovna sredstva** | Dugotrajna imovina | Amortizacijske stope po Pravilniku, evidencija, rashodovanje |
| **B1 — Plaće** | Obračun plaća | Bruto→neto, svi doprinosi, osobni odbitak 2024/2025, JOPPD XML generiranje |
| **B2 — Bolovanja** | Obračun bolovanja | Naknada plaće, HZZO refundacija, 42/70 dana pravilo |
| **B3 — Drugi dohodak** | Honorari | Ugovor o djelu, autorski honorar, prirez, porez |

### Faza C — Porezna prijava i izvještaji

| Modul | Opis | Ključne značajke |
|-------|------|-------------------|
| **C1 — PDV prijava** | PDV-S obrazac | Automatski iz odobrenih knjiženja, provjera ulaznog/izlaznog PDV-a |
| **C2 — Porez na dobit** | PD obrazac | Porezna osnovica, nepriznati troškovi, transferne cijene |
| **C3 — Porez na dohodak** | DOH obrazac | Godišnji obračun, osobni odbitak, razlike |
| **C4 — GFI** | Financijski izvještaji | Bilanca, RDG, bilješke — za mikro/male/srednje |
| **C5 — GFI-XML** | eFINA izvještaji | GFI-POD XML format za FINA, AOP pozicije |
| **C6 — Intrastat** | EU roba | Pragovi prijave, CN kodovi, mjesečne prijave |
| **JOPPD** | Obrazac JOPPD | XML generiranje, stranice A+B, kontrole |

### Faza D — Pomoćni moduli

| Modul | Opis |
|-------|------|
| **Kadrovska** | Evidencija zaposlenika, godišnji odmor, staž, minimalna plaća |
| **Fakturiranje** | Izdavanje računa za knjigovodstvene usluge klijentima |
| **Likvidacija** | Vođenje postupka likvidacije d.o.o. (faze, rokovi, knjiženja) |
| **Novčani tokovi** | Cash flow analiza, projekcije |
| **KPI** | Financijski pokazatelji (likvidnost, zaduženost, ROE) |
| **Deadlines** | Rokovi PU (PDV do 20., PD do 30.4., JOPPD do 15.) |
| **Communication** | Predlošci za PU, HZZO, banke |
| **Business Plan** | Poslovni plan za START/kredite |
| **Accruals** | Razgraničenja, PVR, AVR |
| **Management Accounting** | Upravljačko računovodstvo, centri troškova |

---

## 📜 Zakoni RH (27)

Sustav automatski skida, indeksira i ažurira 27 zakona i pravilnika putem **Time-Aware RAG** sustava:

### Prioritet 1 — Kritični

| # | Zakon/Pravilnik | Narodne Novine | Izmjene |
|---|----------------|----------------|---------|
| 1 | **Zakon o PDV-u** | NN 73/13 | do NN 9/25 (14 izmjena) |
| 2 | **Zakon o računovodstvu** | NN 78/15 | do NN 18/25 (6 izmjena) |
| 3 | **Zakon o porezu na dobit** | NN 177/04 | do NN 9/25 (15 izmjena) |
| 4 | **Zakon o porezu na dohodak** | NN 115/16 | do NN 9/25 (7 izmjena) |
| 5 | **Zakon o doprinosima** | NN 84/08 | do NN 114/23 (12 izmjena) |
| 6 | **Pravilnik o PDV-u** | NN 79/13 | do NN 43/23 (16 izmjena) |
| 7 | **Pravilnik o porezu na dobit** | NN 95/05 | do NN 43/23 (17 izmjena) |
| 8 | **Pravilnik o porezu na dohodak** | NN 10/17 | do NN 43/23 (12 izmjena) |
| 9 | **Pravilnik o JOPPD** | NN 32/15 | do NN 1/21 (7 izmjena) |
| 10 | **Pravilnik o neoporezivim primicima** | NN 1/23 | 1 izmjena |

### Prioritet 2 — Važni

| # | Zakon/Pravilnik | NN |
|---|----------------|-----|
| 11 | Zakon o fiskalizaciji | 133/12 |
| 12 | Opći porezni zakon | 115/16 |
| 13 | Zakon o radu | 93/14 |
| 14 | Zakon o trgovačkim društvima | 111/93 |
| 15 | Zakon o obrtu | 143/13 |
| 16 | Pravilnik o amortizaciji | 1/01 |
| 17 | Pravilnik o kontnom planu | 95/16 |
| 18 | Pravilnik o doprinosima | 2/09 |
| 19 | HSFI standardi | 86/15 |
| 20 | Uredba o minimalnoj plaći | 156/23 |
| 21 | Neoporezivi osobni odbitak | 9/25 |

### Prioritet 3 — Korisni

| # | Zakon/Pravilnik | NN |
|---|----------------|-----|
| 22 | RRiF kontni plan 2024 | — |
| 23 | Pravilnik o e-Računu | 1/19 |
| 24 | Zakon o provedbi ovrhe | 68/18 |
| 25–27 | Dodatni pravilnici | razni |

### Time-Aware RAG

Pitanje: *"Koja je stopa PDV-a na hranu?"* + datum: 2024-01-15
→ Sustav vraća verziju Zakona o PDV-u koja je **vrijedila 15. siječnja 2024.**, ne današnju.

Algoritam:
1. Semantic search (cosine similarity na MiniLM embeddingima)
2. Time boost: +10% za zakone aktivne na zadani datum, -50% za buduće izmjene
3. Keyword fallback ako embedding nije dostupan
4. Citira članak, stavak i NN broj

---

## 🇪🇺 EU i inozemni računi

### Podržani XML formati (100% točnost parsiranja)

| Format | Standard | Zemlje |
|--------|----------|--------|
| **EN 16931** | EU norma za e-račune | EU-27 |
| **Peppol BIS 3.0** | Pan-europski UBL | EU-27 + EEA |
| **ZUGFeRD 2.x / Factur-X** | Hybrid PDF+XML | DE, FR, AT |
| **FatturaPA** | Obavezni XML | IT |
| **UBL 2.1** | ISO/IEC 19845 | Globalno |
| **CII** | UN/CEFACT D16B | Globalno |

### AI OCR za nestrukturirane račune

| Jezik | Polja | Accuracy |
|-------|-------|----------|
| 🇬🇧 Engleski | Invoice, VAT, Amount Due | ~92% |
| 🇩🇪 Njemački | Rechnung, MwSt, Gesamtbetrag | ~90% |
| 🇮🇹 Talijanski | Fattura, IVA, Totale | ~90% |
| 🇫🇷 Francuski | Facture, TVA, Total TTC | ~90% |
| 🇸🇮 Slovenski | Račun, DDV, Skupaj | ~88% |

### VAT ID validacija — svih 27 EU članica

AT, BE, BG, CY, CZ, DE, DK, EE, EL, ES, FI, FR, HR, HU, IE, IT, LT, LU, LV, MT, NL, PL, PT, RO, SE, SI, SK

### Automatsko određivanje PDV tretmana

| Situacija | Tretman | Pravna osnova |
|-----------|---------|---------------|
| EU račun bez PDV-a | **Reverse charge** | Čl. 75. st. 1. t. 6. ZPDV |
| EU stjecanje robe | **Obratni obračun** | Čl. 4. st. 1. t. 2. ZPDV |
| EU primanje usluge | **Obratni obračun** | Čl. 17. st. 1. ZPDV |
| Uvoz iz treće zemlje | **Carinski PDV** | Čl. 7. ZPDV |
| Strana valuta | **Tečaj HNB** | Na datum računa |

### Automatsko kontiranje EU računa

```
Reverse charge primjer:
  4xxx  Trošak              5.000,00 EUR
  1406  Pretporez EU         1.250,00 EUR (25%)
  2401  Obveza PDV EU        1.250,00 EUR (25%)
```

### Podržane valute

EUR, USD, GBP, CHF, CZK, PLN, HUF, RON, BGN, SEK, DKK, NOK

---

## 🧠 4-Tier Memory (učenje)

Sustav uči iz svakog ispravka koji računovođa napravi — bez programiranja:

```
┌─────────────────────────────────────────────────────────────┐
│  L0 — Working Memory                                        │
│  Trenutni ispravak u chatu. Nestaje nakon sesije.           │
├─────────────────────────────────────────────────────────────┤
│  L1 — Episodic Memory                                       │
│  Dnevnik danas. "Ne ponavljaj grešku koju sam ispravio      │
│  prije 2 sata."                                             │
├─────────────────────────────────────────────────────────────┤
│  L2 — Semantic Memory                                       │
│  Trajno pravilo: "Klijent X — račun od Dobavljača Y        │
│  uvijek ide na konto 4010, ne 4110."                        │
├─────────────────────────────────────────────────────────────┤
│  L3 — DPO Nightly Fine-Tune                                 │
│  Noćna optimizacija: Sva odobrena knjiženja → preference    │
│  parovi → LoRA adapter → model sutra ujutro bolji.          │
└─────────────────────────────────────────────────────────────┘
```

**Knowledge Preservation:** Pri update-u modela (nove verzije Qwen-a), L1/L2 memorija, DPO parovi i LoRA adapteri se **nikad ne brišu** — sustav ih verificira prije i poslije svakog upgrade-a.

---

## 🔄 Auto-Update sustav

### Automatski (cron — svake nedjelje 03:00)

```bash
# Instalira se automatski prilikom deploy-a
# Ili ručno dodaj:
crontab -e
0 3 * * 0 /path/to/update.sh --auto >> /path/to/data/logs/update.log 2>&1
```

### Ručne opcije

```bash
./update.sh                # Interaktivno: NN + zakoni + modeli
./update.sh --auto         # Tihi mod za cron
./update.sh --laws         # Samo update zakona
./update.sh --check-nn     # Provjeri Narodne Novine za izmjene
./update.sh --models       # Provjeri nove verzije modela na HuggingFace
./update.sh --force        # Forsiraj download svega + model upgrade
./update.sh --rollback     # Vrati prethodni model iz arhive
./update.sh --status       # Prikaži kompletni status sustava
```

### Što se ažurira

| Komponenta | Metoda | Frekvencija |
|-----------|--------|-------------|
| **Zakoni RH** | LawDownloader → delta download | Tjedno |
| **Narodne Novine** | NNMonitor → web scraping | Tjedno (14 dana unazad) |
| **RAG indeks** | Re-embedding novih/izmijenjenih zakona | Automatski |
| **AI modeli** | HuggingFace check → safe upgrade | Mjesečno |

### Što se NIKAD ne briše

| Podatak | Lokacija |
|---------|----------|
| L1+L2 memorija | `data/memory_db/` |
| DPO parovi | `data/dpo_datasets/` |
| LoRA adapteri | `data/models/lora/` |
| RAG vektori | `data/rag_db/` |
| Zakoni (tekst) | `data/laws/` |
| Korisnici + audit | `data/auth.db` |

---

## 📡 API Endpointi

### Core

| Endpoint | Metoda | Opis |
|----------|--------|------|
| `/chat` | POST | AI razgovor — pitanja, kontiranje, savjeti |
| `/upload` | POST | Upload dokumenta (PDF/slika/XML → OCR pipeline) |
| `/pending` | GET | Lista knjiženja čekaju odobrenje |
| `/approve/{id}` | POST | Odobri knjiženje → ide u ERP export |
| `/reject/{id}` | POST | Odbij knjiženje |
| `/correct/{id}` | POST | Ispravi i odobri (AI uči iz ispravka) |

### Obrada

| Endpoint | Metoda | Opis |
|----------|--------|------|
| `/process/invoice` | POST | Obradi ulazni račun (HR + EU + inozemni) |
| `/process/bank-statement` | POST | Obradi bankovni izvod (MT940/CSV) |
| `/process/payroll` | POST | Obračunaj plaće za klijenta |

### Izvoz i izvještaji

| Endpoint | Metoda | Opis |
|----------|--------|------|
| `/export/{client_id}` | GET | Export odobrenih knjiženja → CPP XML ili Synesis CSV |
| `/dashboard` | GET | KPI dashboard — rokovi, statistike, upozorenja |
| `/clients` | GET | Lista klijenata ureda |
| `/health` | GET | Health check sustava |

---

## 🔧 Deployment

### Minimalni zahtjevi

| Komponenta | Minimum | Preporučeno |
|-----------|---------|-------------|
| **RAM** | 64 GB | 192 GB (Mac Studio M5 Ultra) |
| **Disk** | 200 GB SSD | 500 GB NVMe |
| **OS** | macOS 14+ / Ubuntu 22.04+ | macOS 15 (Apple Silicon) |
| **Python** | 3.11+ | 3.12 |
| **Čip** | Apple M3+ / x86_64 | Apple M5 Ultra |

### Struktura projekta

```
nyx-light-racunovodja/
├── deploy.sh                        # One-file instalacija (450 linija)
├── update.sh                        # Auto-update (200 linija)
├── config.json                      # Konfiguracija
├── pyproject.toml                   # Python paketi
├── README.md                        # Ovaj dokument
│
├── src/nyx_light/                   # 89 Python datoteka, 17.642 LOC
│   ├── app.py                       # NyxLightApp — centralni orchestrator
│   ├── main.py                      # FastAPI entry point
│   ├── modules/                     # 31 modul (vidi tablicu gore)
│   │   ├── invoice_ocr/             #   OCR + EU Invoice Recognition
│   │   ├── bank_parser/             #   MT940 + CSV parseri
│   │   ├── kontiranje/              #   AI kontiranje
│   │   ├── payroll/                 #   Plaće + doprinosi
│   │   ├── pdv_prijava/             #   PDV-S obrazac
│   │   ├── porez_dobit/             #   PD obrazac
│   │   ├── gfi_xml/                 #   GFI-POD za eFINA
│   │   ├── intrastat/               #   EU roba
│   │   └── ... (31 ukupno)
│   ├── rag/                         # Time-Aware RAG sustav
│   │   ├── legal_rag.py             #   Semantic search + time context
│   │   ├── law_downloader.py        #   27 zakona RH
│   │   ├── nn_monitor.py            #   Narodne Novine praćenje
│   │   ├── law_loader.py            #   Chunking po člancima
│   │   └── qdrant_store.py          #   Vektorska baza
│   ├── pipeline/                    # Booking → Approval → Export
│   ├── llm/                         # Chat Bridge (vllm-mlx)
│   ├── vision/                      # Vision AI (Qwen3-VL-8B)
│   ├── memory/                      # 4-Tier Memory
│   ├── export/                      # CPP XML + Synesis CSV
│   ├── auth/                        # RBAC + JWT
│   ├── safety/                      # OVERSEER + hard boundaries
│   ├── finetune/                    # DPO nightly optimization
│   └── ui/                          # Web sučelje
│
├── tests/                           # 509 testova
│   ├── test_sprint13_deploy_eu.py   # Deploy + EU + NN testovi
│   ├── test_full_suite.py           # Svi moduli A-F
│   └── ...
│
└── data/                            # Kreira se kod deploy-a
    ├── models/                      # LLM (~124GB) + Vision (~5GB) + Emb (~500MB)
    │   ├── primary/                 # Qwen3-235B-A22B
    │   ├── vision/                  # Qwen3-VL-8B
    │   ├── embeddings/              # MiniLM-L12
    │   ├── lora/                    # LoRA adapteri (učenje)
    │   └── archive/                 # Stare verzije za rollback
    ├── laws/                        # 27 zakona (.txt)
    ├── rag_db/                      # Qdrant vektori
    ├── memory_db/                   # L1+L2 SQLite
    ├── dpo_datasets/                # DPO preference parovi
    ├── auth.db                      # Korisnici + audit log
    └── logs/                        # deploy.log, update.log
```

---

## 🧪 Testovi

```bash
source .venv/bin/activate

# Svi testovi (509)
python -m pytest tests/ -v

# Quick check
python -m pytest tests/ -q

# Samo najnoviji sprint
python -m pytest tests/test_sprint13_deploy_eu.py -v

# S code coverage
python -m pytest tests/ --cov=src/nyx_light --cov-report=term-missing
```

**Trenutni status: 509 testova — svi prolaze.**

---

## 🔒 Sigurnost

### Tvrde granice (hardcoded — ne mogu se isključiti)

| Granica | Opis |
|---------|------|
| **Zero Cloud** | Nijedan bajt ne napušta lokalni stroj. Nema poziva prema OpenAI, Anthropic, Google ili bilo kojem vanjskom API-ju. |
| **Human-in-the-Loop** | Nijedan podatak ne ulazi u CPP ili Synesis bez eksplicitnog klika "Odobri". |
| **Nema pravnog savjeta** | Sustav odbija upite o ugovorima, tužbama, radnom pravu (izvan obračuna plaća). |
| **Audit Trail** | Svaka radnja (login, pregled, odobrenje, ispravak, export) se logira s timestampom, korisnikom i IP-jem. |
| **RBAC** | Role-based pristup: admin, računovođa, asistent. Svaka rola ima definirane dozvole. |
| **Token auth** | JWT tokeni s expiry-jem. Max 5 neuspjelih pokušaja → account lock. |

### Podaci koji se obrađuju lokalno

- OIB-ovi fizičkih i pravnih osoba
- Plaće zaposlenika klijenata ureda
- Financijski izvještaji
- Poslovne tajne klijenata
- Bankarski izvodi

**Sve ostaje na Mac Studio-u. Nema cloud poziva. Nikad.**

---

## 📝 Changelog

### Sprint 13 (27.02.2026.) — Deploy + EU + NN + RAG
- `deploy.sh` (450 linija) — one-file deploy, 9 faza, auto model selection
- `update.sh` (200 linija) — auto-update zakoni + modeli + NN + rollback
- `eu_invoice.py` (825 linija) — EU/inozemni: 6 XML formata, 5 OCR jezika, 27 VAT ID
- `nn_monitor.py` (480 linija) — Narodne Novine scraping, relevance scoring
- `legal_rag.py` (300 linija) — Time-Aware RAG v2, semantic + keyword
- `law_downloader.py` proširena na 27 zakona
- LegalRAG ↔ NNMonitor ↔ LawDownloader potpuna integracija
- app.py: automatski routing EU računa
- 509 testova, svi prolaze

### Sprint 11 — Auth + Model Manager + DPO
- JWT autentikacija s RBAC ulogama
- ModelManager: katalog 5 modela, safe upgrade, rollback
- ChatBridge: LLM integracija s vllm-mlx
- DPO: noćna optimizacija iz odobrenih knjiženja
- Auto-update mehanizam

### Sprint 9 — Svi moduli 100%
- 36 modula kompletno (A1-A9, B1-B3, C1-C6, D1-D4, E1-E4, F1-F4, G1-G4)
- 289 testova

### Raniji sprintovi
- Sprint 1-8: Core architecture, Pipeline, Memory, ERP Export, OCR, Vision

---

## 📄 Licenca

Privatni softver. © 2026 Dr. Mladen Mešter · Nexellum Lab d.o.o.

Sva prava pridržana. Neovlašteno korištenje, kopiranje ili distribucija zabranjena.
