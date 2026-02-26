# Nyx Light — Računovođa: GAP ANALIZA v3.0
## Ažurirano nakon Sprint 8 (26.02.2026.)

---

## STATISTIKA PROJEKTA

| Metrika | Vrijednost |
|---|---|
| Git commitovi | 8 |
| Python moduli | 68+ |
| Linije koda | ~9.500 |
| Linije testova | ~2.800 |
| **Testovi** | **228 ✅** |
| Kontni plan | 153 konta (razredi 0-9) |

---

## GRUPA A — Dnevni dokumentni tok

| Modul | Status | Implementacija | Kompletnost |
|---|---|---|---|
| A1. Ulazni računi (Vision OCR) | ✅ **Gotov** | `invoice_ocr/` + Pipeline | 85% |
| A2. Izlazni računi (validacija) | ✅ **Gotov** | `outgoing_invoice/` | 70% |
| A3. Kontiranje (prijedlog konta) | ✅ **Gotov** | `kontiranje/` + L2 Memory | 75% |
| A4. Bankovni izvodi (MT940/CSV) | ✅ **Gotov** | `bank_parser/` + Pipeline | 90% |
| A5. Blagajna V2 | ✅ **Gotov** | `blagajna/validator.py` V2 | 95% |
| A6. Putni nalozi V2 | ✅ **Gotov** | `putni_nalozi/checker.py` V2 | 90% |
| A7. Osnovna sredstva | ✅ **Gotov** | `osnovna_sredstva/` | 85% |
| A8. Obračunske stavke | ✅ **Gotov** | `accruals/` | 70% |
| A9. IOS usklađivanja | ✅ **Gotov** | `ios_reconciliation/` | 75% |

**Grupa A: 9/9 modula ✅**

---

## GRUPA B — Plaće i kadrovska

| Modul | Status | Implementacija | Kompletnost |
|---|---|---|---|
| B1. Obračun plaće (bruto/neto) | ✅ **Gotov** | `payroll/` | 90% |
| B2. JOPPD obrazac | ✅ **Gotov** | `joppd/` → XML | 85% |
| B3. Bolovanje (teret posl./HZZO) | ✅ **Gotov** | `bolovanje/` | 80% |
| B4. Autorski honorari / ugovor o djelu | 🟡 Djelomično | Payroll ima osnovu | 30% |
| B5. Kadrovska evidencija | 🔴 Nedostaje | — | 0% |

**Grupa B: 3/5 gotovo, 1 djelomično, 1 nedostaje**

---

## GRUPA C — Porezne prijave

| Modul | Status | Implementacija | Kompletnost |
|---|---|---|---|
| C1. PDV prijava (PPO obrazac) | ✅ **Gotov** | `pdv_prijava/` | 85% |
| C2. EC Sales List (EU) | ✅ **Gotov** | `pdv_prijava/ec_sales_list()` | 80% |
| C3. PD obrazac (porez na dobit) | ✅ **Gotov** | `porez_dobit/` | 85% |
| C4. DOH obrazac (porez na dohodak) | ✅ **Gotov** | `porez_dohodak/` | 85% |
| C5. Paušalni obrt | ✅ **Gotov** | `porez_dohodak/calculate_pausalni()` | 80% |
| C6. Intrastat prijava | 🔴 Nedostaje | — | 0% |

**Grupa C: 5/6 gotovo, 1 nedostaje**

---

## GRUPA D — Godišnji financijski izvještaji (GFI)

| Modul | Status | Implementacija | Kompletnost |
|---|---|---|---|
| D1. Kategorija poduzetnika | ✅ **Gotov** | `gfi_prep/` | 90% |
| D2. Bilanca (BIL obrazac) | ✅ **Gotov** | `gfi_prep/bilanca_struktura()` | 70% |
| D3. RDG obrazac | ✅ **Gotov** | `gfi_prep/rdg_struktura()` | 70% |
| D4. Zaključna knjiženja | ✅ **Gotov** | `gfi_prep/zakljucna_knjizenja_checklist()` | 80% |
| D5. Novčani tokovi (NTI/NTD) | 🔴 Nedostaje | — | 0% |
| D6. GFI predaja FINA (XML) | 🔴 Nedostaje | — | 0% |

**Grupa D: 4/6 gotovo, 2 nedostaje**

---

## GRUPA E — Komunikacija s klijentima

| Modul | Status | Implementacija | Kompletnost |
|---|---|---|---|
| E1. Rokovi i upozorenja | ✅ **Gotov** | `deadlines/` | 85% |
| E2. Pojašnjenje izvještaja | 🟡 LLM može | RAG + Chat | 40% |
| E3. Onboarding klijenta | 🟡 Djelomično | `registry/ClientConfig` | 30% |

**Grupa E: 1/3 gotovo, 2 djelomično**

---

## GRUPA F — Upravljanje uredom

| Modul | Status | Implementacija | Kompletnost |
|---|---|---|---|
| F1. Rokovi kalendar | ✅ **Gotov** | `deadlines/` | 85% |
| F2. Client routing (CPP/Synesis) | ✅ **Gotov** | `registry/` + `pipeline/` | 90% |
| F3. Fakturiranje usluga | 🔴 Nedostaje | — | 0% |

**Grupa F: 2/3 gotovo, 1 nedostaje**

---

## GRUPA G — Specijalizirani

| Modul | Status | Implementacija | Kompletnost |
|---|---|---|---|
| G1. KPI Dashboard | ✅ **Gotov** | `kpi/` | 80% |
| G2. Upravljačko računovodstvo | 🟡 Djelomično | KPI pokriva osnovu | 40% |
| G3. Likvidacijsko računovodstvo | 🔴 LLM znanje | — | 0% |
| G4. Poslovni planovi | 🟡 LLM može | — | 20% |

**Grupa G: 1/4 gotovo, 2 djelomično, 1 nedostaje**

---

## INFRASTRUKTURA

| Komponenta | Status | Kompletnost |
|---|---|---|
| BookingPipeline (submit→approve→export) | ✅ **Gotov** | 90% |
| CPP XML Export | ✅ **Gotov** | 85% |
| Synesis CSV Export | ✅ **Gotov** | 85% |
| ClientRegistry | ✅ **Gotov** | 85% |
| 4-Tier Memory (L0-L3) | ✅ **Gotov** | 75% |
| OVERSEER Safety | ✅ **Gotov** | 90% |
| RAG (zakoni RH) | ✅ **Gotov** | 60% |
| SQLite Persistence | 🟡 Parcijalno | 40% |
| Web UI (Chat + Dashboard) | 🟡 Skelet | 30% |
| Nightly DPO Training | 🟡 Skelet | 30% |
| e-Računi Parser | ✅ **Gotov** | 80% |
| Pantheon Parser | ✅ **Gotov** | 75% |

---

## UKUPNI SCORECARD

| Grupa | Gotovo | Djelomično | Nedostaje | Score |
|---|---|---|---|---|
| A (Dnevni tok) | 9 | 0 | 0 | **100%** |
| B (Plaće) | 3 | 1 | 1 | **70%** |
| C (Porezne) | 5 | 0 | 1 | **83%** |
| D (GFI) | 4 | 0 | 2 | **67%** |
| E (Komunikacija) | 1 | 2 | 0 | **53%** |
| F (Ured) | 2 | 0 | 1 | **67%** |
| G (Specijalizirani) | 1 | 2 | 1 | **38%** |
| Infrastruktura | 9 | 3 | 0 | **75%** |
| **UKUPNO** | **34** | **8** | **6** | **~76%** |

---

## PREOSTALO ZA IMPLEMENTACIJU (Prioritet)

### P1 — Visoki prioritet
1. ~~Plaće (PayrollEngine)~~ ✅ Sprint 6
2. ~~PD obrazac~~ ✅ Sprint 8
3. ~~DOH obrazac~~ ✅ Sprint 8
4. ~~KPI Dashboard~~ ✅ Sprint 8
5. SQLite Persistence wiring (Pipeline → DB)
6. Web UI — funkcionalni chat + approval workflow

### P2 — Srednji prioritet
7. Autorski honorari / ugovori o djelu
8. Intrastat prijava
9. Novčani tokovi (NTI/NTD)
10. GFI XML za FINA predaju
11. RAG corpus expansion (više zakona)

### P3 — Niži prioritet
12. Kadrovska evidencija
13. Fakturiranje usluga ureda
14. Likvidacijsko računovodstvo
15. Nightly DPO training pipeline
