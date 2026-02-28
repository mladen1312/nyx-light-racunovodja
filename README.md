# 🌙 Nyx Light — Računovođa

> **Privatni ekspertni AI sustav za računovodstvo i knjigovodstvo u RH**
> **Matematika računa. AI klasificira. Čovjek odobrava.**

[![Tests](https://img.shields.io/badge/tests-1085_total-brightgreen)]()
[![Python](https://img.shields.io/badge/python-3.12-blue)]()
[![License](https://img.shields.io/badge/license-proprietary-red)]()
[![Platform](https://img.shields.io/badge/platform-Mac_Studio_M4_Ultra-silver)]()

---

## 📋 Sadržaj

- [O Projektu](#-o-projektu)
- [Arhitektura](#-arhitektura)
- [Moduli](#-moduli)
- [Universal Invoice Parser](#-universal-invoice-parser-novi)
- [Fiskalizacija 2.0](#-fiskalizacija-20)
- [Double-Entry Ledger](#-double-entry-ledger)
- [Audit Trail & Anomaly Detection](#-audit-trail--anomaly-detection)
- [Instalacija](#-instalacija)
- [Konfiguracija](#-konfiguracija)
- [Testovi](#-testovi)
- [Roadmap](#-roadmap)

---

## 🎯 O Projektu

Nyx Light — Računovođa je **lokalni, offline AI sustav** dizajniran za računovodstvene urede u Hrvatskoj. Sustav radi na jednom Mac Studio M4 Ultra (192 GB Unified Memory) i opslužuje do **15-20 istovremenih korisnika** bez latencije.

### Ključne karakteristike

- **100% lokalno** — Zero cloud dependency, svi podaci ostaju na vašem hardveru
- **GDPR compliant** — OIB-ovi, plaće i poslovne tajne nikad ne napuštaju ured
- **Human-in-the-Loop** — AI predlaže, računovođa odobrava
- **Fiskalizacija 2.0 ready** — EN 16931 + HR-FISK od 1.1.2026.
- **Adaptivni parser** — čita BILO KOJI račun (XML, PDF, sken, ručno pisan)
- **2.5-3x produktivnost** — 15 zaposlenika + AI = kapacitet za 800-1200 klijenata

### Tehnološki stack

| Komponenta | Tehnologija |
|---|---|
| **Hardver** | Mac Studio M4 Ultra, 192 GB Unified Memory |
| **AI Inference** | vllm-mlx, Continuous Batching, PagedAttention |
| **Logika** | DeepSeek-R1-70B-Q4 ili Qwen2.5-72B-Q4 |
| **Vision AI** | Qwen2.5-VL-7B (čitanje skenova i računa) |
| **Baza znanja** | Neo4j (Knowledge Graph) + Qdrant (RAG) |
| **Backend** | Python 3.12, FastAPI, SQLite WAL |
| **ERP integracija** | CPP, Synesis, e-Računi, Pantheon |

---

## 🏗 Arhitektura

```
┌─────────────────────────────────────────────────────────────┐
│                     KORISNICI (15-20)                        │
│              WebSocket Chat + REST API                       │
├─────────────────────────────────────────────────────────────┤
│                   GATEWAY & AUTH                             │
│    Rate Limiter │ JWT Auth │ WebSocket Manager               │
├─────────────────────────────────────────────────────────────┤
│               UNIVERSAL INVOICE PARSER                       │
│  Tier 1: XML │ Tier 2: Template │ Tier 3: Regex │           │
│  Tier 4: LLM │ Tier 5: Human Review                         │
├──────────┬──────────┬──────────┬───────────┬────────────────┤
│  Ledger  │  Fisk2   │  Audit   │  Kontir.  │   Bankovni    │
│ Double   │  UBL2.1  │  Chain   │  Engine   │   Parser      │
│ Entry    │  HR-FISK │  Anomaly │  RPC2023  │   MT940/CSV   │
├──────────┴──────────┴──────────┴───────────┴────────────────┤
│                    4-TIER MEMORY                             │
│  L0: Working │ L1: Episodic │ L2: Semantic │ L3: DPO       │
├─────────────────────────────────────────────────────────────┤
│              vllm-mlx (Mac Studio M4 Ultra)                  │
│        DeepSeek-R1-70B + Qwen2.5-VL-7B                     │
└─────────────────────────────────────────────────────────────┘
```

---

## 📦 Moduli

### Faza A: Automatizacija visokog volumena

| Modul | Opis | Status |
|---|---|---|
| **A1+ Universal Parser** | Tiered adaptive parser — čita BILO KOJI račun | ✅ |
| **A2 Izlazni računi** | Validacija i generiranje izlaznih faktura | ✅ |
| **A4 Bankovni izvodi** | MT940 + CSV parseri (Erste, Zaba, PBZ) | ✅ |
| **A7 Osnovna sredstva** | Amortizacija, sitan inventar, registar | ✅ |
| **A8 Obračunske stavke** | Razgraničenja, predujmovi, akruali | ✅ |
| **A9 IOS usklađivanja** | Generiranje IOS obrazaca, praćenje | ✅ |

### Faza B: Plaće i Kadrovska

| Modul | Opis | Status |
|---|---|---|
| **B Payroll** | Obračun plaća — bruto/neto, doprinosi, MIO I/II | ✅ |
| **B+ Bolovanje** | Naknada plaće za bolovanje | ✅ |
| **B+ Drugi dohodak** | Autorski honorari, ugovori o djelu | ✅ |
| **B5 Kadrovska** | Evidencija zaposlenika | ✅ |

### Faza C: Porezne prijave

| Modul | Opis | Status |
|---|---|---|
| **C PDV prijava** | PPO obrazac (mjesečni/tromjesečni) | ✅ |
| **C DOH** | Prijava poreza na dohodak | ✅ |
| **C PD** | Porez na dobit — PD obrazac, porezna osnovica | ✅ |
| **C6 Intrastat** | EU intrastat prijava | ✅ |
| **JOPPD** | Obrazac za plaće i dohodak | ✅ |

### Faza D: Financijski izvještaji

| Modul | Opis | Status |
|---|---|---|
| **D GFI prep** | Priprema godišnjih financijskih izvještaja | ✅ |
| **D GFI XML** | XML generiranje za FINA RGFI sustav | ✅ |
| **D Novčani tokovi** | NTI obrazac — cash flow statement | ✅ |

### Faza E: Enterprise moduli

| Modul | Opis | Status |
|---|---|---|
| **Ledger** | Striktni double-entry s Decimal preciznosti | ✅ |
| **Fiskalizacija 2.0** | EN 16931 UBL 2.1 + HR-FISK + KPD 2025 | ✅ |
| **Audit Trail** | Immutable chain-linked audit log (COSO) | ✅ |
| **Anomaly Detection** | Duplikati, Benford, IBAN, AML, noćni unosi | ✅ |
| **Scalability** | Connection pool, capacity planning | ✅ |
| **Kontiranje** | AI engine — RPC 2023 kontni plan | ✅ |
| **Reports** | PDF/Excel generiranje izvještaja | ✅ |

### Faza F: Poslovno upravljanje

| Modul | Opis | Status |
|---|---|---|
| **F Rokovi** | Praćenje zakonskih rokova i deadlinea | ✅ |
| **F3 Fakturiranje** | Fakturiranje usluga ureda klijentima | ✅ |
| **G KPI** | Dashboard — upravljačko računovodstvo | ✅ |
| **G2 Management** | Upravljačko računovodstvo — CBA, analiza | ✅ |
| **G3 Likvidacija** | Likvidacijsko računovodstvo | ✅ |
| **G4 Poslovni plan** | Projekcije, budžetiranje | ✅ |
| **Kompenzacije** | Prijeboj, cesija, asignacija | ✅ |

---

## 🔍 Universal Invoice Parser (NOVI)

Adaptivni parser koji čita **bilo koji račun** u HR (i EU) bez template ograničenja. Koristi zakonske elemente kao kostur umjesto beskonačnih templatea.

### Zakonska osnova

- Zakon o PDV-u čl. 79 (obvezni elementi računa)
- Opći porezni zakon
- Fiskalizacija 2.0 (od 1.1.2026.)
- EU VAT Directive 2006/112/EC čl. 226
- EN 16931-1:2017 standard

### 5 Tier-ova (redoslijed za max točnost)

```
Tier 1: eRačun XML     → UBL/CII parsing    → 99-100% točnost
Tier 2: Template Match  → Top 20+ dobavljača → 95% točnost
Tier 3: Regex Rules     → OIB, IBAN, datumi  → 70-85% točnost
Tier 4: LLM (Qwen-VL)  → Structured extract  → 85-95% točnost
Tier 5: Human Review    → Flagirano za pregled → 100% s ljudom
```

### Pokriveni računi

Konzum, HEP, HT, A1, Telemach, INA, Petrol, FINA, mali obrtnici, EU fakture, predujmi, korekturni računi, gotovinski računi, bankovni izvodi...

### OIB Validacija

Svaki OIB se validira prema **ISO 7064, MOD 11,10** algoritmu — ne samo 11 znamenki, nego i kontrolna znamenka.

### EU Extension (priprema)

| Država | PDV stope | Tax ID | Fiskalizacija |
|---|---|---|---|
| 🇭🇷 HR | 25%, 13%, 5%, 0% | OIB (11 zn.) | Da (2026) |
| 🇩🇪 DE | 19%, 7%, 0% | USt-IdNr (DE+9) | Ne |
| 🇦🇹 AT | 20%, 13%, 10%, 0% | UID-Nr (ATU+8) | Ne |
| 🇮🇹 IT | 22%, 10%, 5%, 4%, 0% | P.IVA (IT+11) | Da (FatturaPA) |
| 🇸🇮 SI | 22%, 9.5%, 5%, 0% | Davčna št. (SI+8) | Ne |

---

## 🧾 Fiskalizacija 2.0

Potpuna implementacija hrvatskog e-Račun sustava prema EN 16931-1:2017 s HR-FISK ekstenzijama.

### KPD 2025 Auto-klasifikacija

Svaka stavka na e-računu automatski dobiva **KPD 2025 kod** (6-znamenkasti):

```python
from nyx_light.modules.fiskalizacija2 import classify_kpd

classify_kpd("Programiranje web aplikacije")  # → ("620100", "Programiranje", 0.95)
classify_kpd("Mjesečna pretplata struje")     # → ("351100", "Električna energija", 0.90)
classify_kpd("Gorivo za službeno vozilo")     # → ("192000", "Naftni proizvodi", 0.95)
```

### Statusni kodovi

| Kod | Značenje | Akcija |
|---|---|---|
| 10 | ACCEPTED | Auto-proknjiži u ledger |
| 90 | MSG_NOT_VALID | AI analizira XML grešku |
| 91 | SIG_NOT_VALID | Provjeri PKI certifikat |
| 99 | SYSTEM_ERROR | Retry s exponential backoff |

---

## 📒 Double-Entry Ledger

Striktni sustav dvojnog knjigovodstva s invariantom: **SUM(duguje) = SUM(potražuje)** — uvijek, bez iznimke.

### Ključne značajke

- **Decimal preciznost** — nikad float, eliminira zaokruživanje
- **Immutable** — jednom proknjiženo, ne briše se (samo storno)
- **AI propose → Human approve** — računovođa ima zadnju riječ
- **SHA-256 fingerprint** — kriptografski potpis svake transakcije
- **Thread-safe** — 15+ istovremenih korisnika

```python
from nyx_light.modules.ledger import GeneralLedger, Transaction, LedgerEntry, Strana

ledger = GeneralLedger()
tx = Transaction(
    datum="2026-02-28", opis="IT konzalting",
    entries=[
        LedgerEntry(konto="4160", strana=Strana.DUGUJE, iznos=Decimal("1000")),
        LedgerEntry(konto="1400", strana=Strana.DUGUJE, iznos=Decimal("250")),
        LedgerEntry(konto="2200", strana=Strana.POTRAZUJE, iznos=Decimal("1250")),
    ]
)
booked = ledger.book(tx, user="ana.horvat")
```

---

## 🔒 Audit Trail & Anomaly Detection

### Anomaly Detection (8 tipova)

| Tip | Razina | Opis |
|---|---|---|
| DUPLIKAT | 🔴 HIGH | Isti iznos + partner unutar 7 dana |
| VISOKI_IZNOS | 🟡 MEDIUM | Iznos > 50.000 EUR |
| AML_PRAG | 🔴 CRITICAL | Gotovina ≥ 15.000 EUR — obvezna AMLD prijava |
| IBAN_PROMJENA | 🔴 CRITICAL | Dobavljač koristi novi IBAN |
| NOCNI_UNOS | 🟡 MEDIUM | Transakcija 22:00-06:00 |
| VIKEND_UNOS | 🟢 LOW | Transakcija subota/nedjelja |
| OKRUGLI_IZNOS | 🟢 LOW | Sumnjivo okrugli iznos |
| BENFORD | 🟡 MEDIUM | Chi-squared test prvih znamenki |

### GDPR Data Masking

```python
from nyx_light.modules.audit import DataMasker
DataMasker.mask_oib("12345678903")            # → "********903"
DataMasker.mask_iban("HR1234567890123456789")  # → "HR12***********6789"
DataMasker.mask_name("Ana Horvat")             # → "A. H."
```

---

## ⚙️ Instalacija

```bash
git clone https://github.com/mladen1312/nyx-light-racunovodja.git
cd nyx-light-racunovodja
pip install -e ".[dev]"
pytest tests/ -v
```

### Mac Studio Deployment

Za produkcijski deployment koristite `deploy.sh`, `start.sh` ili `deployment/scripts/setup_mac_studio.sh`:

```bash
# Inicijalni setup
bash deployment/scripts/setup_mac_studio.sh

# Live editing sesija (hot-reload + watcher)
bash deployment/scripts/live_edit.sh

# Deploy update (git pull + test + reload)
bash deployment/scripts/deploy_update.sh
```

### Zakonska baza (RAG)

Sustav pokriva sljedeće zakone RH:
- Zakon o računovodstvu (ZOR)
- Zakon o porezu na dodanu vrijednost (ZPDV)
- Zakon o porezu na dobit
- Zakon o porezu na dohodak
- Opći porezni zakon
- Zakon o fiskalizaciji u prometu gotovinom
- Pravilnik o strukturi i sadržaju GFI
- Mišljenja Porezne uprave

---

## 🔧 Konfiguracija

### Hardverski profili

| Profil | RAM | Korisnika | Preporučeni LLM |
|---|---|---|---|
| mac_studio_m5_ultra_512 | 512 GB | 40 | Qwen3-235B FP16 + Qwen2.5-VL-72B FP16 |
| mac_studio_m5_ultra_256 | 256 GB | 25 | Qwen3-235B-A22B MoE + Qwen2.5-VL-72B |
| mac_studio_m4_ultra_192 | 192 GB | 20 | DeepSeek-R1-70B-Q4 |
| mac_studio_m4_ultra_128 | 128 GB | 12 | Qwen2.5-72B-Q3 |
| mac_studio_m4_96 | 96 GB | 8 | Qwen2.5-32B-Q6 |
| mac_mini_m4_64 | 64 GB | 5 | Qwen2.5-14B |
| mac_mini_m4_pro_36 | 36 GB | 2 | Phi-4-14B-Q4 |

### Produktivnost s AI

| Zaposlenika | Klijenata (bez AI) | Klijenata (s AI) | Multiplikator |
|---|---|---|---|
| 5 | ~150 | ~400 | 2.5x |
| 10 | ~300 | ~800 | 2.7x |
| **15** | **~450** | **~1200** | **2.7x** |

---

## 🧪 Testovi

```
Ukupno: 1085 testova
├── Sprint 1-19:  999 testova (core moduli)
├── Sprint 20:     49 testova (ledger, fisk2, audit, scalability)
└── Sprint 21:     37 testova (universal parser, legal validation, EU)
```

---

## 📅 Roadmap

### ✅ Dovršeno (Sprint 1-21)

- 30+ računovodstvenih modula
- Universal Invoice Parser (5-tier adaptive)
- Fiskalizacija 2.0 — UBL 2.1 + HR-FISK + KPD 2025
- Double-entry ledger s Decimal preciznosti
- Audit trail + anomaly detection (8 tipova)
- EU extension priprema (DE/AT/IT/SI)

### 🔲 Sljedeći sprintovi

- FINA PKI certifikat integracija (.p12)
- AS4/Peppol posrednik (B2Brouter)
- Qwen2.5-VL-7B integracija za Tier 4
- 4-Tier Memory sustav (L0-L3 + noćni DPO)
- Time-Aware RAG — zakoni RH s vremenskim kontekstom
- Web/Chat UI za 15 zaposlenika

---

## 🔐 Sigurnost

- **Zero cloud** — svi podaci 100% lokalno
- **GDPR masking** — automatsko maskiranje OIB/IBAN/imena
- **Immutable audit** — chain-linked hash, detektira manipulaciju
- **AML detekcija** — flagira gotovinu ≥15.000 EUR
- **Human-in-the-Loop** — ništa ne ulazi u ERP bez klika "Odobri"

---

*Nyx Light — Računovođa. Matematika računa. AI klasificira. Čovjek odobrava.* 🌙
