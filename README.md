# 🌙 Nyx Light — Računovođa

> **Privatni ekspertni AI sustav za računovodstvo i knjigovodstvo u RH**
> **Matematika računa. AI klasificira. Čovjek odobrava.**

![Python](https://img.shields.io/badge/python-3.12+-blue)
![Tests](https://img.shields.io/badge/tests-690%20passing-brightgreen)
![Laws](https://img.shields.io/badge/zakoni%20RH-27-red)
![License](https://img.shields.io/badge/licenca-privatna-black)

Nyx Light radi **100% lokalno** na Mac Studio, opslužuje do **15 zaposlenika** istovremeno.
Zero cloud dependency — svi OIB-ovi, plaće i poslovne tajne ostaju isključivo na vašem hardveru.

**Sustav predlaže, čovjek odobrava.** Nijedan podatak ne ulazi u CPP ili Synesis
bez eksplicitnog klika „Odobri" (Human-in-the-Loop).

---

## 📋 Sadržaj

1. [Matematika vs AI — granica](#-matematika-vs-ai--granica)
2. [Hardver](#-hardver)
3. [Što sustav radi](#-što-sustav-radi)
4. [Brza instalacija](#-brza-instalacija)
5. [Arhitektura](#-arhitektura)
6. [AI Modeli](#-ai-modeli)
7. [Moduli (31)](#-moduli-31)
8. [Apple Silicon optimizacija](#-apple-silicon-optimizacija)
9. [Knowledge Preservation](#-knowledge-preservation)
10. [Zakoni RH (27)](#-zakoni-rh-27)
11. [Real-Time praćenje zakona](#-real-time-praćenje-zakona)
12. [Fiskalizacija 2.0 i eRačun](#-fiskalizacija-20-i-eračun)
13. [4-Tier Memory (učenje)](#-4-tier-memory-učenje)
14. [Triple Verification](#-triple-verification-3)
15. [Sigurnost](#-sigurnost)

---

## 🔢 Matematika vs AI — granica

Ključni princip sustava: **AI nikada ne generira financijski iznos.** Svi iznosi dolaze
iz determinističkih Python formula. AI služi za klasifikaciju, prijedloge i objašnjenja.

| Modul | Tip | Što radi |
|-------|-----|----------|
| Payroll (bruto→neto) | **MATH** | MIO, porez, prirez, neto — formula |
| PDV prijava | **MATH** | Obveza, pretporez, razlika — zbroj stavki |
| Amortizacija | **MATH** | nabavna × stopa / 100 / 12 |
| Porez na dobit | **MATH** | Osnovica + uvećanja - umanjenja |
| Putni nalozi | **MATH** | 0,30 EUR/km, dnevnice, 50% reprezentacija |
| Blagajna | **MATH** | AML limit 10.000 EUR, stanje |
| Ugovor o djelu | **MATH** | 7,5% + 2,5% + 7,5% doprinosi + 20% porez |
| Autorski honorar | **MATH** | 30% normirani trošak + doprinosi |
| Kontiranje | **AI** | Prijedlog konta (nikad iznos!) |
| Invoice OCR | **AI** | Čitanje skenova (Vision model) |
| Report Explanation | **AI** | Objašnjenje bilanci |
| Business Plan | **AI** | Generiranje teksta |
| Management Accounting | **HYBRID** | AI analiza + MATH izračun |

Svaki matematički modul je testiran s ručno izračunatim kontrolnim brojevima.
Svaki AI prijedlog ima `requires_approval = True` — čovjek mora odobriti.

---

## 🖥 Hardver

### Trenutno dostupni Mac Studio (ožujak 2025.)

| Čip | RAM opcije | Max RAM | Cijena (osnovna) |
|-----|-----------|---------|-------------------|
| **M4 Max** (14c CPU, 32c GPU) | 36, 48, 64, 128 GB | **128 GB** | $1.999 |
| **M4 Max** (16c CPU, 40c GPU) | 36, 48, 64, 128 GB | **128 GB** | $2.499 |
| **M3 Ultra** (28c CPU, 60c GPU) | 96, 256, 512 GB | **512 GB** | $3.999 |
| **M3 Ultra** (32c CPU, 80c GPU) | 96, 256, 512 GB | **512 GB** | $5.499 |

### Preporučeni hardver

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

→ **Mac Studio M3 Ultra s 256 GB** unified memory ($6.599-$8.099)

Sustav automatski bira model prema RAM-u:
- **256+ GB** (M3 Ultra) → Qwen3-235B-A22B (MoE, optimalno)
- **128 GB** (M4 Max) → Qwen2.5-72B-Instruct (dense, solidno)
- **96 GB** (M3 Ultra base) → Qwen2.5-72B-Instruct
- **64 GB** (M4 Max base) → Qwen3-30B-A3B (MoE, lite)

Mac Studio s **M5 Ultra** čipom je najavljen za prvu polovicu 2026. Kad bude dostupan, sustav će ga automatski prepoznati.

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
3. Triple Check: 3 nezavisne provjere svake vrijednosti
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
│   │ Watch Folder      │  │ L2  Semantic     │  │ Excel/CSV     │  │
│   │ Time-Aware        │  │ L3  DPO Nightly  │  │ JSON/XML      │  │
│   └───────────────────┘  └──────────────────┘  └───────────────┘  │
│                                                                     │
│   ┌─ Silicon Layer ────────────────────────────────────────────┐   │
│   │  UMA Controller · Adaptive Batch · Thermal · KV Quant     │   │
│   │  Knowledge Vault · LoRA Migration · Prompt Cache           │   │
│   └────────────────────────────────────────────────────────────┘   │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│   vllm-mlx  ·  Continuous Batching  ·  PagedAttention               │
│   Qwen3-235B-A22B (logic) + Qwen3-VL-8B (vision) + MiniLM (emb)   │
├─────────────────────────────────────────────────────────────────────┤
│    Mac Studio · Apple Silicon Ultra · 256 GB Unified · Zero Cloud   │
└─────────────────────────────────────────────────────────────────────┘
```

**21.433 linija koda · 690 testova · 31 modul · 27 zakona**

---

## 🤖 AI Modeli

| RAM | Čip | Primarni LLM | VRAM modela |
|-----|-----|-------------|-------------|
| **256+ GB** | M3 Ultra | Qwen3-235B-A22B (MoE) | ~124 GB |
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

| Modul | Opis |
|-------|------|
| **A1 — Invoice OCR** | Čitanje HR računa (Vision AI + Regex + OIB validacija) |
| **A1-EU — EU Invoice** | EU/inozemni računi (UBL, Peppol, ZUGFeRD, FatturaPA) |
| **A2 — Izlazni računi** | Validacija, eRačun B2B od 01.01.2026 |
| **A4 — Bankovni izvodi** | MT940/CSV parser (Erste, Zaba, PBZ) |
| **A9 — IOS usklađivanja** | Otvorene stavke, IOS obrasci |

### Faza B — Ekspertna asistencija

| Modul | Opis |
|-------|------|
| **A3 — Kontiranje** | AI prijedlog konta + L2 memorija |
| **A5 — Blagajna** | AML limit 10.000 EUR, fiskalizacija, sekvencijalnost |
| **A6 — Putni nalozi** | Km 0,30 EUR, dnevnice 26,55 EUR, 50% reprezentacija |
| **A7 — Osnovna sredstva** | Linearna amortizacija, 11 kategorija, prag 665 EUR |
| **B1 — Plaće** | Bruto→neto, MIO I+II, progresivni porez, prirez, mladi, invalidi |

### Faza C — Porezna prijava

| Modul | Opis |
|-------|------|
| **C1 — PDV-S** | PDV prijava po stopama (25%, 13%, 5%, 0%), EU transakcije |
| **C2 — Porez na dobit** | PD obrazac (10%/18%), uvećanja/umanjenja, predujmovi |
| **C3 — Porez na dohodak** | DOH obrazac |
| **JOPPD** | XML generiranje, stranice A+B |
| **GFI-POD** | Bilanca, RDG, bilješke |

### Ostali moduli

Bolovanje, Kadrovska evidencija, Drugi dohodak, Fakturiranje, Likvidacija,
Novčani tokovi, KPI dashboard, Komunikacija, Rokovi, Business Plan,
Client Management, Management Accounting, Accruals, Intrastat, eRačuni parser.

---

## ⚡ Apple Silicon optimizacija

Sloj adaptiran iz NYX 47.0 „Stones" arhitekture za single-node operaciju.

### UMA Memory Management

| Komponenta | Budget | ~GB (256 GB) |
|-----------|--------|-------------|
| LLM weights | 50% | 128 GB |
| KV cache (15 korisnika) | 15% | 38 GB |
| Working buffers | 10% | 26 GB |
| Prompt cache | 5% | 13 GB |
| Vision model | 3% | 8 GB |
| Embeddings + RAG | 3% | 8 GB |
| LoRA adapteri | 2% | 5 GB |
| OS + headroom | 12% | 30 GB |

### Adaptive Batch Scaling

Automatska prilagodba prema memory pressure i termalnom stanju:

| Memory Pressure | Batch | Max Tokens |
|----------------|-------|------------|
| NOMINAL (< 70%) | 8 | 4096 |
| ELEVATED (70-80%) | 6 | 4096 |
| WARNING (80-88%) | 4 | 2048 |
| CRITICAL (88-95%) | 2 | 1024 |
| EMERGENCY (> 95%) | 1 | 512 |

Termalni multiplikator: COOL/NOMINAL 1.0×, WARM 0.85×, HOT 0.65×, THROTTLING 0.40×.

### Inference optimizacije

- **Continuous Batching** (vLLM-MLX) — 15 korisnika bez blokiranja
- **PagedAttention** — efikasno upravljanje KV cache memorijom
- **4-bit KV Quantization** — 4× ušteda memorije
- **Prompt Caching** — ~500ms brži TTFT za system prompt
- **Wired KV Cache** — sprječava macOS page-out
- **Fused Attention** — Metal-optimizirani GPU kerneli
- **LoRA Hot-Loading** — zamjena adaptera bez restarta

### MLX Environment

```bash
MLX_METAL_FAST_SYNCH=1         # Brža GPU komanda
MLX_METAL_PREALLOCATE=true     # Pre-alokacija Metal buffera
TOKENIZERS_PARALLELISM=false   # Bez fork deadlocka
MALLOC_NANO_ZONE=0             # Bolje large alloc performanse
```

---

## 🛡 Knowledge Preservation

Kad se base LLM zamijeni novom verzijom, **svo naučeno znanje ostaje**.

### 10 zaštićenih putanja (nikad se ne brišu)

| Znanje | Lokacija | Sadržaj |
|--------|----------|---------|
| L1+L2 memorija | `data/memory_db/` | SQLite — ispravci + pravila |
| Korisnici | `data/auth.db` | Autentikacija + audit log |
| RAG baza | `data/rag_db/` | Qdrant vektori — 27 zakona |
| DPO parovi | `data/dpo_datasets/` | Preference parovi (model-nezavisni JSONL) |
| LoRA adapteri | `data/models/lora/` | Naučene težine iz DPO treninga |
| Zakonski tekstovi | `data/laws/` | Originalni .txt s NN brojevima |
| Eksporti | `data/exports/` | Generirani CPP/Synesis fajlovi |
| Backupi | `data/backups/` | Backup stanja |
| Logovi | `data/logs/` | Audit trail |
| Konfiguracija | `config.json` | Postavke sustava |

### Safe Model Swap (10 faza)

1. **PRE_CHECK** — provjera svih 10 putanja
2. **SNAPSHOT** — SHA-256 integrity manifest
3. **BACKUP** — arhiviranje starog modela
4. **DOWNLOAD** — preuzimanje novog modela
5. **VALIDATE** — test inference
6. **LORA_CHECK** — provjera kompatibilnosti adaptera (architecture fingerprint)
7. **DPO_RETRAIN** — ako je adapter nekompatibilan → retrain iz DPO parova
8. **VERIFY** — provjera integrity manifesta
9. **ACTIVATE** — prelazak na novi model
10. **COMPLETE / ROLLBACK** — ako bilo koji korak padne → instant restore

LoRA kompatibilnost se provjerava po architecture fingerprintu (family + param count).
Ista arhitektura → direct load. Različita → automatski retrain iz DPO dataset-a.

---

## 📜 Zakoni RH (27)

Svaki zakon verificiran na zakon.hr i narodne-novine.nn.hr.

### Prioritet 1 — Kritični

| # | Zakon/Pravilnik | Narodne Novine | Zadnja izmjena |
|---|----------------|----------------|----------------|
| 1 | **Zakon o PDV-u** | NN 73/13 | NN 151/25 (01.01.2026) |
| 2 | **Zakon o računovodstvu** | NN 78/15 | NN 18/25 |
| 3 | **Zakon o porezu na dobit** | NN 177/04 | NN 151/25 (01.01.2026) |
| 4 | **Zakon o porezu na dohodak** | NN 115/16 | NN 152/24 (01.01.2025) |
| 5 | **Zakon o doprinosima** | NN 84/08 | NN 114/23 |
| 6 | **Zakon o fiskalizaciji** | NN 89/25 | Novi zakon od 01.09.2025 |
| 7 | **Pravilnik o fiskalizaciji** | NN 153/25 | Od 01.01.2026 |
| 8 | Pravilnik o PDV-u | NN 79/13 | NN 16/25 |
| 9 | Pravilnik o porezu na dobit | NN 95/05 | NN 16/25 |
| 10 | Pravilnik o porezu na dohodak | NN 10/17 | NN 43/23 |
| 11 | Pravilnik o JOPPD | NN 32/15 | NN 1/21 |
| 12 | Pravilnik o neoporezivim primicima | NN 1/23 | NN 43/23 |

### Prioritet 2 — Važni

| # | Zakon/Pravilnik | NN |
|---|----------------|-----|
| 13 | Opći porezni zakon | NN 115/16 + NN 151/25 |
| 14 | Zakon o radu | NN 93/14 + NN 64/23 |
| 15 | Zakon o trgovačkim društvima | NN 111/93 + NN 18/23 |
| 16-27 | Ostali pravilnici, standardi, uredbe | Vidi `law_downloader.py` |

### Ključne stope (2026.)

| Stavka | Iznos / Stopa |
|--------|--------------|
| Minimalna plaća | 1.050,00 EUR bruto (NN 132/25) |
| Min. za direktore | 1.295,45 EUR (NN 150/25) |
| MIO I. stup | 15% |
| MIO II. stup | 5% |
| Zdravstveno (na plaću) | 16,5% |
| Porez na dohodak | 20% do 4.200 EUR/mj, 30% iznad |
| Osobni odbitak | 560,00 EUR |
| Porez na dobit | 10% (≤ 1M EUR prihoda), 18% (> 1M) |
| PDV | 25%, 13%, 5% |
| Km naknada | 0,30 EUR/km |
| Dnevnica RH (>12h) | 26,55 EUR |
| Topli obrok | 7,96 EUR/dan |
| Prag dugotrajne imovine | 665,00 EUR |
| AML gotovinski limit | 10.000 EUR |
| PDV prijava rok | Zadnji dan u mjesecu (NN 151/25) |

---

## 📡 Real-Time praćenje zakona

```
┌──────────────────────────────────────────────────────────────┐
│                   Real-Time Law Monitor                       │
│                                                               │
│  1. NN Monitor (tjedno)                                       │
│     └─ Scraping narodne-novine.nn.hr (zadnjih 14 dana)       │
│     └─ Relevance scoring → obavijest admin-u                 │
│                                                               │
│  2. Watch Folder (real-time)                                  │
│     └─ data/incoming_laws/                                    │
│     └─ Čovjek stavi PDF/TXT → AI parsira → predloži update   │
│     └─ Admin POTVRDI → zakon ulazi u RAG bazu                │
│                                                               │
│  3. Cron Auto-Update (nedjelja 03:00)                         │
│     └─ Delta download novih izmjena                           │
│     └─ Re-embedding u Qdrant vektorsku bazu                  │
│     └─ Log u data/logs/update.log                             │
└──────────────────────────────────────────────────────────────┘
```

Nikad se zakon ne ažurira automatski bez ljudske potvrde.

---

## ⚡ Fiskalizacija 2.0 i eRačun

Zakon o fiskalizaciji (NN 89/25) — potpuno novi zakon od 01.09.2025,
zamjenjuje stari Zakon o fiskalizaciji u prometu gotovinom (NN 133/12).

| Datum | Obveza | Status |
|-------|--------|--------|
| 01.09.2025 | Zakon stupio na snagu | Implementirano |
| 01.01.2026 | eRačun obvezan za PDV obveznike (B2B) | Implementirano |
| 01.01.2026 | KPD klasifikacija roba/usluga | Implementirano |
| 01.01.2027 | eRačun obvezan za SVE subjekte | Pripremljeno |

Podržani formati: EN 16931, Peppol BIS 3.0, ZUGFeRD, FatturaPA, UBL 2.1, CII.

---

## 🧠 4-Tier Memory (učenje)

Sustav uči iz svakog ispravka:

| Tier | Naziv | Trajnost | Primjer |
|------|-------|----------|---------|
| **L0** | Working | Sesija | Trenutni ispravak u chatu |
| **L1** | Episodic | Dan | „Ne ponavljaj grešku od danas" |
| **L2** | Semantic | Trajno | „Klijent X → dobavljač Y → konto 4010" |
| **L3** | DPO Nightly | Model | Noćni LoRA trening iz odobrenih knjiženja |

**Noćni DPO**: Sakupi preference parove → `mlx_lm.lora` trening → novi LoRA adapter → model sutra bolji.

Confidence Decay System (CDS) s domain-specifičnim half-life:
LEGAL 90 dana, USER_PREFERENCE 30 dana, SCIENTIFIC 365 dana, MATHEMATICAL ∞.

---

## ✅ Triple Verification (3×)

Svaki podatak prolazi 3 nezavisne provjere:

```
         Ulazni podatak
              │
   ┌──────────┼──────────┐
   ▼          ▼          ▼
 CHECK 1   CHECK 2   CHECK 3
 AI model  Algoritam  Pravilo
   │          │          │
   └──────────┼──────────┘
              ▼
        KONSENZUS?
        3/3 = ✅ Prikaži
        2/3 = ⚠️ Upozori
        1/3 = ❌ Zaustavi
```

| Operacija | Check 1 (AI) | Check 2 (Algoritam) | Check 3 (Pravilo) |
|-----------|-------------|---------------------|-------------------|
| OCR račun | Vision AI | Regex ekstrakcija | OIB mod 11,10 |
| Iznos PDV-a | AI izračuna | Matematika (osnovica × stopa) | Usporedba s deklariranim |
| Kontiranje | AI predlaže | L2 memorija (povijest) | Kontni plan (RRiF) |
| Zakonski odgovor | RAG semantic | Keyword search | Datum važenja |
| Plaća | AI izračun | Deterministička formula | Min. plaća provjera |

---

## 🔒 Sigurnost

| Granica | Opis |
|---------|------|
| **Zero Cloud** | Nijedan bajt ne napušta lokalni stroj |
| **Human-in-the-Loop** | Ništa ne ide u CPP/Synesis bez klika „Odobri" |
| **Triple Verification** | Svaki podatak prolazi 3 nezavisne provjere |
| **Math ≠ AI** | AI nikad ne generira iznos — samo formula |
| **Zakoni s potvrdom** | Nijedan zakon se ne ažurira bez ljudske potvrde |
| **Nema pravnog savjeta** | Odbija upite o ugovorima, tužbama, radnom pravu |
| **Audit Trail** | Svaka radnja logirana s timestampom i korisnikom |
| **RBAC + JWT** | Role-based pristup: admin, računovođa, asistent |
| **Knowledge Preservation** | 10 zaštićenih putanja + SHA-256 integrity + rollback |

---

## 📊 Projekt u brojevima

| Metrika | Vrijednost |
|---------|-----------|
| Linija koda | 21.433 |
| Testova | 690 (svi prolaze) |
| Modula | 31 |
| Zakona RH | 27 |
| Silicon optimizacija | ~3.000 linija |
| Zaštićenih putanja znanja | 10 |
| Safe swap faza | 10 |
| Max korisnika | 15 istovremeno |

---

## 📄 Licenca

Privatni softver. © 2026 Dr. Mladen Mešter · Nexellum Lab d.o.o.
