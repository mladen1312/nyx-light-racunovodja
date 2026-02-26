# 📊 GAP ANALYSIS — Nyx Light Računovođa
## Stanje nakon Sprint 8 (26.02.2026.)

---

## GRUPA A — Primarna obrada dokumenata

| Modul | Status | Pokrivenost | Napomena |
|-------|--------|-------------|----------|
| A1. Ulazni računi (OCR) | ✅ Implementirano | 85% | Vision AI, ekstrakcija OIB/PDV/iznos, Pipeline→CPP/Synesis |
| A2. Izlazni računi (validacija) | ✅ Implementirano | 75% | Formalna kontrola, sekvencijalnost, PDV provjera |
| A3. Kontiranje | ✅ Implementirano | 70% | 153 konta, L2 memorija, AI prijedlog + Human approval |
| A4. Bankovni izvodi | ✅ Implementirano | 90% | MT940, CSV (Erste/Zaba/PBZ), IBAN sparivanje, batch→CPP |
| A5. Blagajna | ✅ V2 Implementirano | 95% | AML >10k EUR, sekvencijalnost, stanje, fiskalizacija flag |
| A6. Putni nalozi | ✅ V2 Implementirano | 90% | Km 0.30€, dnevnice, repr. 50%, dokumentacija, Pipeline |
| A7. Osnovna sredstva | ✅ Implementirano | 85% | Evidencija, amortizacija, inventura, prag 665 EUR |
| A8. Obračunske stavke | ✅ Implementirano | 80% | Monthly/yearly checklist, razgraničenja, rezerviranja |
| A9. IOS usklađivanja | ✅ Implementirano | 75% | Generiranje obrazaca, praćenje, Pipeline |

## GRUPA B — Plaće i kadrovska evidencija

| Modul | Status | Pokrivenost | Napomena |
|-------|--------|-------------|----------|
| Bruto/neto kalkulacija | ✅ Sprint 6 | 90% | PayrollEngine: MIO I/II, zdravstveno, porez, prirez |
| Doprinosi | ✅ Sprint 6 | 90% | Sve stope 2026 |
| Porezne olakšice (mladi) | ✅ Sprint 6 | 85% | <25: 100%, 25-30: 50% |
| JOPPD obrazac | ✅ Sprint 7 | 85% | XML za ePorezna, stranica B |
| Bolovanja (HZZO) | ✅ Sprint 8 | 80% | 42 dana poslodavac, HZZO od 43., ozljeda na radu 100% |
| Autorski honorari | 🟡 Djelomično | 30% | LLM znanje, nema specifičnog modula |

## GRUPA C — Porezne prijave

| Modul | Status | Pokrivenost | Napomena |
|-------|--------|-------------|----------|
| PDV prijava (PPO) | ✅ Sprint 7 | 85% | 25/13/5/0%, EU reverse charge, EC Sales List |
| PD obrazac (dobit) | ✅ Sprint 8 | 85% | 10%/18%, uvećanja/umanjenja, checklist, predujmovi |
| DOH obrazac (dohodak) | ✅ Sprint 8 | 85% | Obrt, paušalni obrt, progresija, olakšice mladi |
| JOPPD | ✅ Sprint 7 | 85% | XML output |
| EC Sales List | ✅ Sprint 7 | 80% | Zbirna prijava EU |
| Intrastat | 🟡 Djelomično | 20% | Struktura poznata, nema generatora |

## GRUPA D — Godišnji financijski izvještaji

| Modul | Status | Pokrivenost | Napomena |
|-------|--------|-------------|----------|
| Kategorija poduzetnika | ✅ Sprint 7 | 95% | Mikro/mali/srednji/veliki — 2 od 3 kriterija |
| Bilanca (BIL) | ✅ Sprint 7 | 80% | Struktura s AOP brojevima, konta |
| RDG | ✅ Sprint 7 | 80% | Prihodi/rashodi struktura |
| Zaključna knjiženja | ✅ Sprint 7 | 85% | 13 stavki checklist |
| Novčani tokovi | 🟡 Djelomično | 30% | Struktura poznata, nema generatora |
| GFI predaja FINA | 🟡 Pripremljeno | 60% | Podaci spremni, ručna predaja |

## GRUPA E — Komunikacija s klijentima

| Modul | Status | Pokrivenost |
|-------|--------|-------------|
| Obavijesti o rokovima | ✅ Sprint 6 | 80% | DeadlineTracker: 13+ rokova, urgency |
| Pojašnjenje izvještaja | ✅ LLM + RAG | 70% |
| Onboarding klijenta | ✅ Sprint 7 | 75% | ClientRegistry |

## GRUPA F — Upravljanje uredom

| Modul | Status | Pokrivenost |
|-------|--------|-------------|
| Upravljanje rokovima | ✅ Sprint 6 | 85% |
| Fakturiranje usluga | 🟡 Djelomično | 30% |

## GRUPA G — Specijalizirani zadaci

| Modul | Status | Pokrivenost |
|-------|--------|-------------|
| KPI Dashboard | ✅ Sprint 8 | 80% | ROA, ROE, likvidnost, zaduženost, EBITDA, health score |
| Upravljačko računovodstvo | ✅ Sprint 8 | 70% | KPI + per-employee metrike |
| Poslovni planovi | 🟡 LLM može | 40% |
| Likvidacijsko računovodstvo | 🟡 LLM znanje | 20% |

---

## INFRASTRUKTURA

| Komponenta | Status | Napomena |
|-----------|--------|----------|
| Pipeline (Submit→Approve→Export) | ✅ | BookingPipeline — centralni tok |
| CPP Export (XML) | ✅ | Svi moduli → CPP format |
| Synesis Export (CSV) | ✅ | Svi moduli → Synesis format |
| ClientRegistry | ✅ | Klijent → ERP routing |
| 4-Tier Memory | ✅ | L0-L2 + DPO hook |
| OVERSEER Safety | ✅ V1.3 | Rafinirane granice |
| Kontni plan (153 konta) | ✅ | Razredi 0-9 |
| RAG (zakoni RH) | ✅ Osnovno | 6 zakona, Qdrant spremno |
| SQLite Persistence | 🔴 Nedostaje | Pipeline drži u memoriji |
| Web UI (Chat sučelje) | 🟡 Skeleton | Dashboard postoji, chat nedostaje |
| Nightly DPO Training | ✅ Hook | Korekcije se skupljaju, trening spreman |

---

## SAŽETAK

| Kategorija | Ukupno stavki | ✅ Done | 🟡 Partial | 🔴 Missing |
|-----------|---------------|---------|------------|------------|
| Grupa A (Dokumenti) | 9 | 9 | 0 | 0 |
| Grupa B (Plaće) | 6 | 5 | 1 | 0 |
| Grupa C (Porezi) | 6 | 5 | 1 | 0 |
| Grupa D (GFI) | 6 | 4 | 2 | 0 |
| Grupa E (Komunikacija) | 3 | 3 | 0 | 0 |
| Grupa F (Ured) | 2 | 1 | 1 | 0 |
| Grupa G (Specijalizirano) | 4 | 2 | 2 | 0 |
| Infrastruktura | 10 | 8 | 1 | 1 |
| **UKUPNO** | **46** | **37 (80%)** | **8 (17%)** | **1 (2%)** |

**Preostalo za punu produkciju:**
1. SQLite persistence za Pipeline (🔴 jedini critical gap)
2. Intrastat generator
3. Novčani tokovi generator
4. Autorski honorari modul
5. Web Chat UI za zaposlenike
