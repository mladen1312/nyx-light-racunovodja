# 🌙 Nyx Light — Računovođa

> **Privatni ekspertni AI sustav za računovodstvo i knjigovodstvo u RH**
> **Točnost je najbitnija. Svaki podatak se provjerava 3× nezavisno.**

![Python](https://img.shields.io/badge/python-3.12+-blue)
![Tests](https://img.shields.io/badge/tests-511%20passing-brightgreen)
![Triple-Check](https://img.shields.io/badge/verifikacija-3×_nezavisna-critical)
![Laws](https://img.shields.io/badge/zakoni%20RH-27-red)
![License](https://img.shields.io/badge/licenca-privatna-black)

Nyx Light radi **100% lokalno** na Mac Studio, opslužuje do **15 zaposlenika** istovremeno.
Zero cloud dependency — svi OIB-ovi, plaće i poslovne tajne ostaju isključivo na vašem hardveru.

**Sustav predlaže, čovjek odobrava.** Nijedan podatak ne ulazi u CPP ili Synesis
bez eksplicitnog klika "Odobri" (Human-in-the-Loop).

---

## 📋 Sadržaj

1. [Hardver — VERIFICIRANE specifikacije](#-hardver--verificirane-specifikacije)
2. [Triple Verification sustav (3×)](#-triple-verification-sustav-3)
3. [Što sustav radi](#-što-sustav-radi)
4. [Brza instalacija](#-brza-instalacija)
5. [Arhitektura](#-arhitektura)
6. [AI Modeli](#-ai-modeli)
7. [Moduli (31)](#-moduli-31)
8. [Zakoni RH (27)](#-zakoni-rh-27)
9. [Real-Time praćenje zakona](#-real-time-praćenje-zakona)
10. [Fiskalizacija 2.0 i eRačun](#-fiskalizacija-20-i-eračun)
11. [4-Tier Memory (učenje)](#-4-tier-memory-učenje)
12. [Knowledge Preservation](#-knowledge-preservation)
13. [Sigurnost](#-sigurnost)
14. [Changelog](#-changelog)

---

## 🖥 Hardver — VERIFICIRANE specifikacije

> **Svaki hardverski podatak u ovom dokumentu provjeravan je na apple.com/mac-studio/specs/**
> **Zadnja verifikacija: 27. veljače 2026.**

### Trenutno dostupni Mac Studio (ožujak 2025.)

| Čip | RAM opcije | Max RAM | Cijena (osnovna) |
|-----|-----------|---------|-------------------|
| **M4 Max** (14-core CPU, 32-core GPU) | 36, 48, 64, 128 GB | **128 GB** | $1.999 |
| **M4 Max** (16-core CPU, 40-core GPU) | 36, 48, 64, 128 GB | **128 GB** | $2.499 |
| **M3 Ultra** (28-core CPU, 60-core GPU) | 96, 256, 512 GB | **512 GB** | $3.999 |
| **M3 Ultra** (32-core CPU, 80-core GPU) | 96, 256, 512 GB | **512 GB** | $5.499 |


### Preporučeni hardver za Nyx Light

**Za Qwen3-235B-A22B (124 GB model) + Vision + 15 korisnika:**

| Komponenta | Zauzeće |
|-----------|---------|
| Qwen3-235B-A22B (4-bit) | ~124 GB |
| Qwen3-VL-8B (Vision) | ~5 GB |
| MiniLM-L12 (embedding) | ~0.5 GB |
| KV-cache (15 korisnika × 8K) | ~20-30 GB |
| Qdrant + RAG | ~2-4 GB |
| macOS + sustav | ~8-12 GB |
| **UKUPNO** | **~170-185 GB** |

→ **Mac Studio M3 Ultra s 256 GB** unified memory ($6.599-$8.099 ovisno o konfiguraciji)

Sustavi s manje RAM-a automatski dobivaju manji model:
- 128 GB (M4 Max) → Qwen2.5-72B (42 GB model, solidna kvaliteta)
- 96 GB (M3 Ultra base) → Qwen2.5-72B
- 64 GB (M4 Max base) → Qwen3-30B-A3B (MoE, 18 GB)

### Budući hardver (očekivano 2026.)

Mac Studio s **M5 Max** i **M5 Ultra** čipovima je najavljen za prvu polovicu 2026.
(Izvor: Bloomberg/Gurman, studeni 2025; 9to5Mac, veljača 2026)
Kada bude dostupan, deploy.sh će automatski prepoznati M5 Ultra i odabrati optimalni model.

---

## ✅ Triple Verification sustav (3×)

> **Točnost je apsolutni prioritet.** U knjigovodstvu, jedna greška može značiti pogrešnu poreznu prijavu.
> Zato SVAKI podatak prolazi kroz 3 nezavisne provjere prije nego što se prikaže korisniku.

### Kako radi

```
         Ulazni podatak (npr. OCR račun, kontiranje, zakon)
                            │
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │ CHECK 1  │ │ CHECK 2  │ │ CHECK 3  │
        │ Primarni │ │ Sekundar.│ │ Pravilo  │
        │ AI model │ │ metoda   │ │ validac. │
        └────┬─────┘ └────┬─────┘ └────┬─────┘
             │             │             │
             └─────────────┼─────────────┘
                           ▼
                    ┌──────────────┐
                    │  KONSENZUS?  │
                    │  3/3 = ✅    │
                    │  2/3 = ⚠️    │
                    │  1/3 = ❌    │
                    └──────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
         3/3 match    2/3 match    Neslaganje
         → Prikaži    → Prikaži    → ZAUSTAVI
           korisniku    + upozori    → Zatraži
                         korisnika    ljudsku
                                      provjeru
```

### Primjeri Triple Verification

| Operacija | Check 1 (AI) | Check 2 (Algoritam) | Check 3 (Pravilo) |
|-----------|-------------|---------------------|-------------------|
| **OCR račun** | Vision AI čita | Regex ekstrakcija | OIB mod 11,10 validacija |
| **Iznos PDV-a** | AI izračuna | Matematička provjera (osnovica × stopa) | Usporedba s deklariranim na računu |
| **Kontiranje** | AI predlaže konto | L2 memorija (povijest) | Kontni plan pravila (RRiF) |
| **Zakonski odgovor** | RAG semantic search | Keyword search (nezavisno) | Provjera datuma važenja zakona |
| **Plaća** | AI izračun bruto→neto | Deterministička formula | Usporedba s min. plaćom (NN 132/25) |
| **PDV prijava** | AI popuni obrazac | Zbrojevi po stopama | Cross-check s ulaznim/izlaznim fakturama |
| **Bankovni izvod** | AI prepozna platitelja | IBAN lookup baza | Poziv na broj parsing |
| **eRačun** | XML parser | Schema validacija (EN 16931) | Poslovni pravila (iznosi, datumi) |

### Confidence Score

Svaki izlaz ima **confidence score** (0.00 — 1.00):

| Score | Značenje | Akcija |
|-------|---------|--------|
| **0.95 — 1.00** | Sve 3 provjere se slažu | ✅ Prikaži korisniku za odobrenje |
| **0.70 — 0.94** | 2 od 3 se slažu | ⚠️ Prikaži + istakni nesigurnost |
| **< 0.70** | Neslaganje | ❌ NE prikazuj — zatraži ljudsku provjeru |

### Triple Check za zakone

Kada AI odgovara na pravno pitanje:
1. **RAG Search**: Semantic search po vektorskoj bazi zakona
2. **Keyword Search**: Nezavisni keyword search po istim zakonima
3. **Date Validation**: Je li pronađeni zakon bio na snazi na relevantni datum?

Ako se sva 3 slažu → citira članak, stavak, NN broj.
Ako ne → kaže "Nisam siguran, provjerite ručno" + pokazuje kandidate.

---

## 🎯 Što sustav radi

| Faza | Opis | Primjeri modula |
|------|------|-----------------|
| **A** | Automatizacija visokog volumena | OCR računa, Bankovni izvodi, IOS |
| **B** | Ekspertna asistencija | Kontiranje, Osnovna sredstva, Blagajna, Putni nalozi |
| **C** | Porezna prijava | PDV-S, PD, DOH, JOPPD, GFI-POD |
| **D** | Pravna baza (RAG) | 27 zakona RH, Narodne Novine monitor |
| **E** | Učenje | 4-Tier Memory, noćni DPO fine-tune |

**Tipičan radni tok:**
1. Zaposlenik uploada račun (PDF, slika, XML, eRačun)
2. Vision AI čita → OCR u strukturirane podatke
3. **Triple Check**: 3 nezavisne provjere svake vrijednosti
4. AI predlaže kontiranje na temelju povijesti
5. Računovođa pregledava → Odobri / Ispravi / Odbij
6. Odobreno → eksport u CPP ili Synesis (XML/CSV)
7. Memorija pamti ispravak → sljedeći put točnije

---

## 🚀 Brza instalacija

```bash
git clone https://github.com/mladen1312/nyx-light-racunovodja.git
cd nyx-light-racunovodja
chmod +x deploy.sh
./deploy.sh
```

**Korisne komande:**
```bash
./start.sh              # Pokreni sustav
./stop.sh               # Zaustavi
./update.sh --check     # Provjeri nove modele/zakone
./update.sh --laws      # Ažuriraj samo zakone
./update.sh --model     # Upgrade LLM modela (safe, s rollback-om)
```

Deploy automatski detektira RAM i bira model:
- **256+ GB** (M3 Ultra) → Qwen3-235B-A22B (MoE, optimalno)
- **96-255 GB** → Qwen2.5-72B (dense, solidno)
- **64-95 GB** → Qwen3-30B-A3B (MoE, lite)

---

## 🏗 Arhitektura

```
┌────────────────────────────────────────────────────────────────────┐
│                    Web UI  ×  15 korisnika                         │
│            /chat  /pending  /approve  /dashboard  /upload          │
├────────────────────────────┬───────────────────────────────────────┤
│        FastAPI + WS        │          Pipeline (HITL)              │
│     ChatBridge (LLM) ──────┤  pending → approve → export          │
│                            │  + OVERSEER (safety)                  │
│                            │  + TRIPLE CHECK (3× verifikacija)    │
├────────────────────────────┴───────────────────────────────────────┤
│                                                                     │
│   ┌─ A ──────────────┐  ┌─ B ──────────────┐  ┌─ C ───────────┐  │
│   │ A1  Invoice OCR   │  │ A3  Kontiranje   │  │ C1  PDV-S     │  │
│   │ A1+ EU Invoice    │  │ A7  Osn.sredstva │  │ C2  Dobit     │  │
│   │ A4  Banka MT940   │  │ A5  Blagajna     │  │ C3  Dohodak   │  │
│   │ A9  IOS           │  │ A6  Putni nalozi │  │ C4-C6 GFI     │  │
│   └───────────────────┘  │ B1  Plaće        │  │     JOPPD     │  │
│                           └──────────────────┘  └───────────────┘  │
│                                                                     │
│   ┌─ D ──────────────┐  ┌─ E ──────────────┐  ┌─ F ───────────┐  │
│   │ RAG (27 zakona)   │  │ L0  Working      │  │ CPP Export    │  │
│   │ NN Monitor (RT)   │  │ L1  Episodic     │  │ Synesis Exp.  │  │
│   │ Watch Folder 📁   │  │ L2  Semantic     │  │ Excel/CSV     │  │
│   │ Time-Aware        │  │ L3  DPO Nightly  │  │ JSON/XML      │  │
│   └───────────────────┘  └──────────────────┘  └───────────────┘  │
│                                                                     │
│   ┌─ TRIPLE VERIFICATION ──────────────────────────────────────┐   │
│   │  Svaki izlaz: AI Check + Algoritam Check + Pravilo Check   │   │
│   │  Confidence Score: 3/3=✅  2/3=⚠️  1/3=❌→ljudska provjera │   │
│   └────────────────────────────────────────────────────────────┘   │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│   vllm-mlx  ·  Continuous Batching  ·  PagedAttention               │
│   Qwen3-235B-A22B (logic) + Qwen3-VL-8B (vision) + MiniLM (emb)   │
├─────────────────────────────────────────────────────────────────────┤
│     Mac Studio M3 Ultra  ·  256 GB Unified Memory  ·  Zero Cloud    │
│        (ili M5 Ultra kad bude dostupan, ili M4 Max 128GB lite)      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 🤖 AI Modeli

| RAM | Čip | Primarni LLM | VRAM modela |
|-----|-----|-------------|-------------|
| **256+ GB** | M3 Ultra / M5 Ultra | Qwen3-235B-A22B (MoE) | ~124 GB |
| **128 GB** | M4 Max (16c/40c) | Qwen2.5-72B-Instruct | ~42 GB |
| **96 GB** | M3 Ultra base | Qwen2.5-72B-Instruct | ~42 GB |
| **64 GB** | M4 Max base | Qwen3-30B-A3B (MoE) | ~18 GB |

| Pomoćni model | Uloga | VRAM |
|---------|-------|------|
| **Qwen3-VL-8B** | Vision OCR (skenovi, računi) | ~5 GB |
| **MiniLM-L12-v2** | Embedding za RAG | ~500 MB |

---

## 🧩 Moduli (31)

### Faza A — Automatizacija

| Modul | Opis | Triple Check |
|-------|------|-------------|
| **A1 — Invoice OCR** | Čitanje HR računa | AI OCR + Regex + OIB validacija |
| **A1-EU — EU Invoice** | EU/inozemni računi (UBL, Peppol, ZUGFeRD, FatturaPA) | XML parser + Schema valid. + Business rules |
| **A2 — Izlazni računi** | Validacija, eRačun B2B od 01.01.2026 | Fiskalizacija + format + iznosi |
| **A4 — Bankovni izvodi** | MT940/CSV (Erste, Zaba, PBZ) | AI match + IBAN lookup + Poziv na broj |
| **A9 — IOS usklađivanja** | Otvorene stavke, IOS obrasci | AI + salda + period match |

### Faza B — Ekspertna asistencija

| Modul | Opis | Triple Check |
|-------|------|-------------|
| **A3 — Kontiranje** | AI prijedlog konta | AI + L2 memorija + kontni plan |
| **A5 — Blagajna** | Limit 10.000 EUR, dnevnik | AI + formula + zakonski limit |
| **A6 — Putni nalozi** | Km 0,30 EUR, dnevnice | AI + kalkulacija + pravilnik |
| **A7 — Osnovna sredstva** | Amortizacija | AI + Pravilnik stope + matematika |
| **B1 — Plaće** | Bruto→neto, JOPPD | AI + formula + min.plaća NN 132/25 |

### Faza C — Porezna prijava

| Modul | Opis | Ključna promjena 2026 |
|-------|------|----------------------|
| **C1 — PDV-S** | PDV prijava | **Rok: zadnji dan mjeseca** (NN 151/25), ukidanje U-RA i PPO |
| **C2 — Porez na dobit** | PD obrazac | Transferne cijene — nove metode (NN 151/25) |
| **C3 — Porez na dohodak** | DOH | Stope po JLS za 2026. (NN 152/24) |
| **JOPPD** | Obrazac JOPPD | XML generiranje, stranice A+B |

---

## 📜 Zakoni RH (27)

**Zadnje ažuriranje kataloga: 27. veljače 2026.**
**Svaki zakon verificiran na zakon.hr i narodne-novine.nn.hr**

### Prioritet 1 — Kritični

| # | Zakon/Pravilnik | Narodne Novine | Zadnja izmjena |
|---|----------------|----------------|----------------|
| 1 | **Zakon o PDV-u** | NN 73/13 | **NN 151/25** (01.01.2026) — 16 izmjena |
| 2 | **Zakon o računovodstvu** | NN 78/15 | NN 18/25 — 7 izmjena |
| 3 | **Zakon o porezu na dobit** | NN 177/04 | **NN 151/25** (01.01.2026) — 16 izmjena |
| 4 | **Zakon o porezu na dohodak** | NN 115/16 | NN 152/24 (01.01.2025) — 7 izmjena |
| 5 | **Zakon o doprinosima** | NN 84/08 | NN 114/23 — 12 izmjena |
| 6 | **Zakon o fiskalizaciji** | **NN 89/25** | **NOVI ZAKON** od 01.09.2025 ⚡ |
| 7 | **Pravilnik o fiskalizaciji** | **NN 153/25** | **NOVI** od 01.01.2026 ⚡ |
| 8 | Pravilnik o PDV-u | NN 79/13 | NN 16/25 — 16 izmjena |
| 9 | Pravilnik o porezu na dobit | NN 95/05 | NN 16/25 — 20 izmjena |
| 10 | Pravilnik o porezu na dohodak | NN 10/17 | NN 43/23 — 12 izmjena |
| 11 | Pravilnik o JOPPD | NN 32/15 | NN 1/21 — 7 izmjena |
| 12 | Pravilnik o neoporezivim primicima | NN 1/23 | NN 43/23 |

### Prioritet 2 — Važni

| # | Zakon/Pravilnik | NN |
|---|----------------|-----|
| 13 | **Opći porezni zakon** | NN 115/16 + **NN 151/25** |
| 14 | Zakon o radu | NN 93/14 + NN 64/23 |
| 15 | Zakon o trgovačkim društvima | NN 111/93 + NN 18/23 |
| 16-27 | Ostali pravilnici, standardi, uredbe | Vidi `law_downloader.py` |

### Ključne izmjene od 01.01.2026. (NN 151/25)

- **PDV**: Rok prijave produžen na **zadnji dan u mjesecu** (bio 20.). Ukidanje **U-RA i PPO** obrazaca. eRačun bez suglasnosti.
- **Dobit**: Transferne cijene — 3 nove metode. Prethodni sporazumi TP. Donacije zdravstvo.
- **OPZ**: Ukidanje OPZ-STAT-1 (zamjena eIzvještavanjem). Porezna tajna — razmjena s JLS.
- **Min. plaća 2026**: 1.050,00 EUR bruto (NN 132/25). Direktori: 1.295,45 EUR (NN 150/25).

---

## 📡 Real-Time praćenje zakona

### Automatsko praćenje (3 izvora)

```
┌──────────────────────────────────────────────────────────────┐
│                   Real-Time Law Monitor                       │
│                                                               │
│  1. NN Monitor (tjedno)                                       │
│     └─ Scraping narodne-novine.nn.hr (zadnjih 14 dana)       │
│     └─ Relevance scoring → obavijest admin-u                 │
│                                                               │
│  2. Watch Folder 📁 (real-time)                               │
│     └─ data/incoming_laws/                                    │
│     └─ Čovjek stavi PDF/TXT → AI parsira → predloži update   │
│     └─ Čovjek POTVRDI → zakon ulazi u RAG bazu               │
│                                                               │
│  3. Cron Auto-Update (nedjelja 03:00)                         │
│     └─ Delta download novih izmjena                           │
│     └─ Re-embedding u Qdrant vektorsku bazu                  │
│     └─ Log u data/logs/update.log                             │
└──────────────────────────────────────────────────────────────┘
```

### Watch Folder — čovjek daje dokumente

Korisnik može staviti dokumente u **`data/incoming_laws/`** folder:
- PDF-ovi novih zakona
- TXT datoteke s propisima
- Službeni dopisi PU
- Interna pravila ureda

Sustav automatski:
1. Detektira novi fajl (filesystem watch, <5 sekundi)
2. AI parsira sadržaj (OCR ako je PDF)
3. Identificira koji zakon/pravilnik je relevantan
4. **Prikaže adminu za potvrdu** — NE dodaje automatski u bazu!
5. Admin odobri → zakon ulazi u RAG bazu → re-embedding
6. Admin odbije → fajl se arhivira u `data/incoming_laws/rejected/`

### Ažuriranje s potvrdom čovjeka

**NIKAD se zakon ne ažurira automatski bez ljudske potvrde.**

```
Novi NN objavljen → NN Monitor detektira → Obavijest adminu
                                                 │
                                          Admin pregleda
                                                 │
                                    ┌────────────┼────────────┐
                                    ▼            ▼            ▼
                               Odobri       Odgodi      Odbij
                               → Update     → Queue     → Ignoriraj
                               RAG baze     za kasnije
```

---

## ⚡ Fiskalizacija 2.0 i eRačun

**Zakon o fiskalizaciji (NN 89/25) — POTPUNO NOVI ZAKON od 01.09.2025.**
Zamjenjuje stari Zakon o fiskalizaciji u prometu gotovinom (NN 133/12).

| Datum | Obveza | Nyx Light podrška |
|-------|--------|--------------------|
| 01.09.2025 | Zakon stupio na snagu | ✅ RAG baza sadrži kompletan zakon |
| 01.01.2026 | eRačun obvezan za PDV obveznike (B2B) | ✅ EU Invoice modul |
| 01.01.2026 | KPD klasifikacija roba/usluga | ✅ KPD šifre u Invoice OCR |
| 01.01.2027 | eRačun obvezan za SVE subjekte | ✅ Pripremljeno |

Podržani formati: EN 16931, Peppol BIS 3.0, ZUGFeRD, FatturaPA, UBL 2.1, CII

---

## 🧠 4-Tier Memory (učenje)

Sustav uči iz svakog ispravka:

| Tier | Naziv | Trajnost | Primjer |
|------|-------|----------|---------|
| **L0** | Working | Sesija | Trenutni ispravak u chatu |
| **L1** | Episodic | Dan | "Ne ponavljaj grešku od danas" |
| **L2** | Semantic | Trajno | "Klijent X → dobavljač Y → konto 4010" |
| **L3** | DPO Nightly | Model | Noćni LoRA trening iz odobrenih knjiženja |

**Noćni DPO**: Sakupi preference parove → `mlx_lm.lora` trening → novi LoRA adapter → model sutra bolji.

---

## 🛡 Knowledge Preservation

**Kad se base LLM zamijeni novom verzijom, SVE naučeno znanje ostaje.**

Znanje je ODVOJENO od modela u 5 sustava:

| Znanje | Lokacija | Što sadrži |
|--------|----------|------------|
| L1+L2 memorija | `data/memory_db/` | SQLite — ispravci + pravila |
| DPO parovi | `data/dpo_datasets/` | Preference parovi (chosen/rejected) |
| LoRA adapteri | `data/models/lora/` | Naučene težine iz DPO treninga |
| RAG baza | `data/rag_db/` | Qdrant vektori — 27 zakona |
| Zakonski tekstovi | `data/laws/` | Originalni .txt s NN brojevima |

**Safe Upgrade**: Backup → Download → Test → Switch (ili Rollback).
LoRA adapteri i svi podaci se **NIKAD ne brišu**.

---

## 🔒 Sigurnost

| Granica | Opis |
|---------|------|
| **Zero Cloud** | Nijedan bajt ne napušta lokalni stroj. Nema OpenAI, Anthropic, Google. |
| **Human-in-the-Loop** | Ništa ne ide u CPP/Synesis bez klika "Odobri". |
| **Triple Verification** | Svaki podatak prolazi 3 nezavisne provjere. |
| **Zakoni s potvrdom** | Nijedan zakon se ne ažurira u RAG bazi bez ljudske potvrde. |
| **Nema pravnog savjeta** | Odbija upite o ugovorima, tužbama, radnom pravu. |
| **Audit Trail** | Svaka radnja logirana s timestampom, korisnikom, IP-jem. |
| **RBAC + JWT** | Role-based pristup: admin, računovođa, asistent. |

---

## 📝 Changelog

### Sprint 14 (27.02.2026.) — Hardver verifikacija + Triple Check + Zakoni 2026

**Hardver — ispravke:**
- ❌→✅ Uklonjeno: "M5 Ultra" (ne postoji na dan 27.02.2026.)
- ❌→✅ Uklonjeno: "M4 Ultra" (Apple je preskočio)
- ❌→✅ Uklonjeno: "192 GB RAM" (nije dostupna konfiguracija)
- ✅ Ispravno: **Mac Studio M3 Ultra s 256 GB** (pravi Apple konfiguracija)
- ✅ Sve RAM opcije verificirane na apple.com/mac-studio/specs/

**Triple Verification sustav:**
- ✅ NOVO: 3× nezavisna provjera svakog podatka
- ✅ NOVO: Confidence Score (3/3, 2/3, 1/3)
- ✅ NOVO: Neslaganje → zaustavi → zatraži ljudsku provjeru

**Real-time praćenje zakona:**
- ✅ NOVO: Watch Folder (`data/incoming_laws/`) za ljudske dokumente
- ✅ NOVO: Ažuriranje zakona SAMO uz potvrdu čovjeka
- ✅ Poboljšano: NN Monitor (tjedno skeniranje novih NN)

**Zakoni:**
- ✅ Zakon o fiskalizaciji: NN 133/12 → **NN 89/25** (novi zakon)
- ✅ Pravilnik o fiskalizaciji: NN 153/25 (novo)
- ✅ NN 151/25 paket: PDV, Dobit, OPZ
- ✅ NN 152/24: PDV, Dohodak
- ✅ NN 52/25: PDV 5%
- ✅ Min. plaća: NN 132/25 (1.050 EUR)
- ✅ Doprinosi: NN 150/25
- ✅ 27 zakona bez duplikata

**Testovi:** 511 testova — svi prolaze.

---

## 📄 Licenca

Privatni softver. © 2026 Dr. Mladen Mešter · Nexellum Lab d.o.o.
