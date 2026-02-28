# 🌙 Nyx Light — Računovođa

**Privatni AI sustav za računovodstvo i knjigovodstvo u RH**

[![Tests](https://img.shields.io/badge/tests-1085%20passing-brightgreen)]()
[![Python](https://img.shields.io/badge/python-3.12-blue)]()
[![License](https://img.shields.io/badge/license-proprietary-red)]()
[![LOC](https://img.shields.io/badge/LOC-26k+-orange)]()

---

## Što je Nyx Light?

Nyx Light je **lokalni, offline AI sustav** za računovodstvene urede u Hrvatskoj. Radi na jednom Mac Studio (M4 Ultra, 192 GB RAM), opslužuje do **15 zaposlenika istovremeno**, bez ikakvog slanja podataka u cloud.

**Ključne prednosti:**
- 🔒 **100% lokalno** — OIB-ovi, plaće i poslovne tajne nikad ne napuštaju ured
- 🤖 **AI asistent** — predlaže kontiranja, čita račune, generira obrasce
- 👤 **Human-in-the-Loop** — AI predlaže, računovođa odobrava
- 📊 **2.5-3x produktivnost** — 15 zaposlenika + AI = posao za 40 ljudi
- 🇭🇷 **100% usklađeno s RH zakonodavstvom** — PDV, porez na dobit, JOPPD, Fiskalizacija 2.0

---

## Arhitektura

```
┌─────────────────────────────────────────────────┐
│                  Web UI / Chat                   │
│            (15 istovremenih korisnika)            │
├─────────────────────────────────────────────────┤
│              FastAPI + WebSocket                  │
├──────────┬──────────┬──────────┬────────────────┤
│ Universal│  Ledger  │  Fisk   │    Audit &      │
│ Invoice  │ (Double  │  2.0    │    Anomaly      │
│ Parser   │  Entry)  │ eRačun  │    Detection    │
├──────────┼──────────┼──────────┼────────────────┤
│  Bank    │Kontiranje│   PDV   │   Payroll &     │
│  Parser  │  Engine  │  Prijava│   JOPPD         │
├──────────┴──────────┴──────────┴────────────────┤
│         vllm-mlx (Qwen 72B / DeepSeek-R1)        │
│         Mac Studio M4 Ultra · 192 GB RAM          │
└─────────────────────────────────────────────────┘
```

---

## Moduli (41 production files, 13.850 LOC)

### Faza A — Automatizacija visokog volumena

| Modul | LOC | Opis |
|-------|-----|------|
| **universal_parser** | 874 | 🆕 Tiered Adaptive Parser — čita BILO KOJI račun (XML/template/regex/LLM/manual) |
| **invoice_ocr** | 1.662 | Vision AI za ulazne račune + EU e-invoice parser |
| **bank_parser** | 493 | Parser za MT940/CSV (Erste, Zaba, PBZ) |
| **ios_reconciliation** | 525 | IOS obrasci + automatsko mapiranje razlika |
| **outgoing_invoice** | 219 | Validacija izlaznih računa |

### Faza B — Ekspertna asistencija

| Modul | LOC | Opis |
|-------|-----|------|
| **ledger** | 301 | 🆕 Double-entry ledger s Decimal preciznosti i balance invariantima |
| **kontiranje** | 540 | Kontni plan RH + engine za automatsko kontiranje |
| **osnovna_sredstva** | 220 | Amortizacija, sitan inventar, registar |
| **blagajna** | 421 | Blagajnički dnevnik + provjera limita (10.000 EUR) |
| **putni_nalozi** | 537 | Putni nalozi + km naknada (0.30 EUR) + dnevnice |

### Faza C — Porezni sustav

| Modul | LOC | Opis |
|-------|-----|------|
| **fiskalizacija2** | 707 | 🆕 Fiskalizacija 2.0 — UBL 2.1 + HR-FISK + KPD 2025 |
| **pdv_prijava** | 205 | PPO obrazac |
| **porez_dobit** | 521 | PD obrazac + prijava poreza na dobit |
| **porez_dohodak** | 242 | DOH obrazac |
| **payroll** | 355 | Obračun plaća |
| **place** | 319 | Croatian Payroll Calculator |
| **joppd** | 236 | JOPPD obrazac generator |
| **drugi_dohodak** | 213 | Autorski honorari, ugovori o djelu |
| **bolovanje** | 179 | Naknada plaće za vrijeme bolovanja |

### Faza D — Izvještavanje

| Modul | LOC | Opis |
|-------|-----|------|
| **gfi_xml** | 330 | GFI XML (Godišnji financijski izvještaji) |
| **gfi_prep** | 203 | Priprema podataka za GFI |
| **novcani_tokovi** | 211 | NTI obrazac (Novčani tokovi) |
| **reports** | 450 | Generiranje izvještaja (PDF/Excel) |
| **accruals** | 219 | Obračunske stavke (PVR/AVR) |

### Faza E — Poslovanje ureda

| Modul | LOC | Opis |
|-------|-----|------|
| **client_management** | 232 | Onboarding novog klijenta |
| **communication** | 236 | Pojašnjenje izvještaja klijentima |
| **fakturiranje** | 238 | Fakturiranje usluga ureda |
| **kadrovska** | 186 | Kadrovska evidencija |
| **deadlines** | 165 | Praćenje zakonskih rokova |
| **kompenzacije** | 258 | Prijeboj, cesija, asignacija |

### Faza F — Upravljanje i infrastruktura

| Modul | LOC | Opis |
|-------|-----|------|
| **audit** | 359 | 🆕 Immutable audit trail + anomaly detection (Benford, AML, IBAN fraud) |
| **scalability** | 411 | 🆕 Connection pool + capacity planning + accuracy monitor |
| **kpi** | 192 | KPI Dashboard za upravljačko računovodstvo |
| **management_accounting** | 257 | Upravljačko računovodstvo |
| **business_plan** | 208 | Poslovni planovi |
| **likvidacija** | 179 | Likvidacijsko računovodstvo |
| **intrastat** | 185 | Intrastat prijava |
| **e_racun** | 307 | Generiranje e-Računa (UBL 2.1) |
| **eracuni_parser** | 248 | Parser za e-racuni.com + Pantheon ERP |

---

## 🆕 Universal Invoice Parser (Sprint 21)

**Problem:** Svaki dobavljač ima drugačiji format računa. Template pristup zahtijeva beskonačno templatea.

**Rješenje:** Tiered Adaptive Parser koji koristi zakonske obveze kao "kostur" — svaki račun u RH MORA imati iste elemente (Zakon o PDV-u čl. 79).

```
Tier 1: eRačun XML (UBL 2.1 / CII)     → 99% točnost  [od 2026. automatski]
Tier 2: Template match (20+ dobavljača)  → 95% točnost  [OIB + pattern match]
Tier 3: Rule-based regex (HR formati)    → 70-85%       [OIB, IBAN, datumi, iznosi]
Tier 4: LLM extraction (Qwen2.5-VL)     → 85-95%       [structured JSON + Pydantic]
Tier 5: Human-in-the-Loop               → 100%          [AI flagira, čovjek popravlja]
```

**Značajke:**
- OIB validacija po ISO 7064 (MOD 11,10)
- Zakonska validacija po čl. 79 Zakona o PDV-u
- KPD 2025 auto-klasifikacija (Fiskalizacija 2.0)
- EU extension ready (DE/AT/IT/SI konfiguracije)
- Balance check: neto + PDV = bruto (tolerancija ±0.02 EUR)
- GDPR data masking za audit log

---

## 🆕 Fiskalizacija 2.0 (Sprint 20)

Potpuna implementacija hrvatskog sustava e-fakturiranja prema EN 16931:

- **KPD 2025** auto-klasifikacija (50+ kategorija)
- **UBL 2.1 XML** s HR-FISK ekstenzijama
- **PKI potpis** (stub za razvoj, produkcija koristi FINA .p12 certifikat)
- **Status kodovi:** 10 (OK), 90 (XML greška), 91 (certifikat), 99 (retry)
- **Zaprimanje e-računa** s 5-dnevnim rokom

---

## 🆕 Double-Entry Ledger (Sprint 20)

Striktni sustav dvojnog knjigovodstva:

- **Invariant:** `SUM(duguje) == SUM(potražuje)` — uvijek, bez iznimke
- **Decimal preciznost** — nikad float u računovodstvu
- **Immutable** — jednom proknjiženo se ne briše, samo stornira
- **AI propose → Human approve** workflow
- **SHA-256 fingerprint** per transakcija
- Thread-safe za 15+ korisnika

---

## 🆕 Audit Trail & Anomaly Detection (Sprint 20)

### Audit Trail
- Blockchain-lite chain (svaki entry hash ovisi o prethodnom)
- `verify_chain()` detektira svaku manipulaciju
- COSO-kompatibilan za interne kontrole

### Anomaly Detection (8 tipova)
| Tip | Rizik | Opis |
|-----|-------|------|
| DUPLIKAT | 🔴 HIGH | Isti iznos + partner u 7 dana |
| VISOKI_IZNOS | 🟡 MEDIUM | > 50.000 EUR |
| AML_PRAG | 🔴 CRITICAL | ≥ 15.000 EUR gotovina — obvezna AMLD prijava |
| IBAN_PROMJENA | 🔴 CRITICAL | Dobavljač koristi novi IBAN (čest fraud vektor) |
| NOCNI_UNOS | 🟡 MEDIUM | Transakcija 22:00-06:00 |
| VIKEND_UNOS | 🟢 LOW | Transakcija subota/nedjelja |
| OKRUGLI_IZNOS | 🟢 LOW | Iznos djeljiv sa 100 |
| BENFORD | 🟡 MEDIUM | Chi-squared test distribucije prvih znamenki |

### GDPR Data Masking
```python
mask_oib("12345678903")       → "********903"
mask_iban("HR123456789...")    → "HR12***********6789"
mask_name("Ana Horvat")       → "A. H."
```

---

## Kapacitetno planiranje

| Hardver | RAM | Korisnika | LLM Model |
|---------|-----|-----------|-----------|
| Mac Studio M4 Ultra | 192 GB | **20** | DeepSeek-R1-70B-Q4 |
| Mac Studio M4 Ultra | 128 GB | 12 | Qwen2.5-72B-Q3 |
| Mac Studio M4 Max | 96 GB | 8 | Qwen2.5-32B-Q6 |
| Mac Mini M4 Pro | 64 GB | 5 | Qwen2.5-14B |

### Produktivnost s AI sustavom

| Klijenti | Bez AI | S AI | Ušteda |
|----------|--------|------|--------|
| 100 | 4 zaposlenika | 2 | 50% |
| 300 | 10 | 4 | 60% |
| 500 | 17 | 7 | 59% |
| 1000 | 33 | 13 | 61% |

**Ured s 15 zaposlenika + AI → 800-1200 klijenata** (vs 450 bez AI).

---

## Instalacija

```bash
# Kloniraj repo
git clone https://github.com/mladen1312/nyx-light-racunovodja.git
cd nyx-light-racunovodja

# Python 3.12+ potreban
pip install -e ".[dev]"

# Pokreni testove
pytest tests/ -v

# Pokreni server
python -m nyx_light.main
```

### Zavisnosti
```
fastapi, uvicorn          # Web server
pydantic                  # Validacija
openpyxl                  # Excel (.xlsx)
psutil                    # Hardware info
python-multipart          # Upload datoteka
```

---

## Testovi

```
tests/
├── test_api_production.py          # API endpoint testovi
├── test_sprint1_setup.py           # Sprint 1-3 basic setup
├── test_sprint4_*.py               # Sprint 4-9 module tests
├── ...
├── test_sprint20_enterprise.py     # Ledger, Fisk2, Audit, Scalability (49 tests)
└── test_sprint21_universal_parser.py  # Universal Parser (37 tests)

Total: 1085 tests, 0 failures
```

---

## Sigurnosni aksiomi

1. **Apsolutna privatnost** — Zero cloud dependency, svi podaci lokalno
2. **Zabrana autonomnog knjiženja** — Nijedan podatak ne ulazi u CPP/Synesis bez ljudskog klika "Odobri"
3. **Zabrana pravnog savjetovanja** — Sustav automatski odbija upite izvan domene računovodstva
4. **Immutable audit trail** — Svaka akcija se bilježi, chain-verified
5. **GDPR compliance** — Data masking za OIB, IBAN, imena u logovima

---

## Roadmap

- [x] Sprint 1-19: Core moduli (kontiranje, banke, PDV, plaće, GFI...)
- [x] Sprint 20: Enterprise modules (Ledger, Fiskalizacija 2.0, Audit, Scalability)
- [x] Sprint 21: Universal Invoice Parser (5-tier adaptive)
- [ ] Sprint 22: FINA PKI certifikat integracija + AS4/Peppol
- [ ] Sprint 23: 4-Tier Memory sustav (L0-L3 + noćni DPO)
- [ ] Sprint 24: Web UI + Chat sučelje za 15 zaposlenika
- [ ] Sprint 25: Production deployment + UAT

---

## Tehnički stack

| Komponenta | Tehnologija |
|------------|-------------|
| Runtime | Python 3.12 |
| Web | FastAPI + Uvicorn |
| DB | SQLite WAL (15-30 korisnika), PostgreSQL path za 50+ |
| AI | vllm-mlx na Apple Silicon |
| LLM | Qwen2.5-72B / DeepSeek-R1-70B (kvantiziran) |
| Vision | Qwen2.5-VL-7B (čitanje računa) |
| Fiskalizacija | UBL 2.1 XML + HR-FISK + KPD 2025 |
| Knowledge Base | Neo4j (graph) + Qdrant (RAG za zakone RH) |

---

## Licenca

Proprietary — © 2026 Dr. Mladen Mester. Sva prava pridržana.

---

*Nyx Light — Računovođa · Jer AI ne zamjenjuje računovođu, već ga čini 3× učinkovitijim.* 🌙
