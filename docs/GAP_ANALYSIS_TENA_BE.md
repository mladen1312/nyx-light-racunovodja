# GAP ANALIZA: TENA BE Projektni Zahtjev vs Nyx Light V1.3

## Datum: 26. veljače 2026.
## Verzija: 1.0

---

## EXECUTIVE SUMMARY

TENA BE dokument je **izvanredno temeljit** — pokriva 7 procesnih grupa, 40+ specifičnih procesa, kompletni softverski ekosustav i jasne granice sustava. Naš Nyx Light V1.3 trenutno pokriva otprilike **45% zahtjeva na razini koda/modula**, ali s Qwen3-235B-A22B modelom i RAG sustavom, potencijal za pokrivanje **85%+ zahtjeva** postoji uz nadogradnje opisane u ovom dokumentu.

### Ključni nalaz:
TENA BE dokument je **bolji od našeg Blueprinta** u tri bitna aspekta:
1. **Širina znanja** — pokriva Grupe B–G koje mi nemamo kao module
2. **Softverski ekosustam** — mapira 20+ alata i platformi (mi imamo samo CPP/Synesis)
3. **Eksplicitne granice** — definirane su i "šire zone" i "što NE pokrivamo"

Naš Blueprint je **bolji** u:
1. **MoE arhitektura** — TENA BE ne specificira hardver/model
2. **4-Tier Memory + DPO** — sustav učenja iz ispravaka
3. **Konkretna implementacija** — imamo radni kod, ne samo specifikaciju

---

## DETALJNA MATRICA POKRIVANJA

### TEMA 1: Područja znanja (Jezgra)

| Zahtjev (TENA BE) | Nyx Light Status | Implementacija | Prioritet |
|---|---|---|---|
| 2.1 Porezni sustav RH (PDV, dobit, dohodak) | 🟡 Djelomično | RAG s 2 sample zakona; treba puni corpus | **P1** |
| 2.2 Obračun plaće i kadrovska evidencija | 🔴 Nedostaje | Nema modula za plaće | **P1** |
| 2.3 HSFI i MSFI standardi | 🔴 Nedostaje | Nema u RAG bazi | P2 |
| 2.4 Financijsko izvještavanje (GFI) | 🔴 Nedostaje | Nema modula | P2 |
| 2.5 Vrste poslovnih oblika (d.o.o., obrt, j.d.o.o.) | 🟡 Djelomično | LLM zna, ali nema specifične prompta | P2 |
| 2.6 PDV — posebna kompleksnost (EU, OSS, reverse charge) | 🟡 Djelomično | Osnovni RAG; nedostaje EU specifika | **P1** |
| 2.7 Fiskalizacija i digitalni ekosustam | 🟡 Djelomično | Blagajna validator; nedostaje ePorezna/eFINA | P2 |

### TEMA 1: Šira zona

| Zahtjev | Status | Napomena |
|---|---|---|
| 3.1 Radno pravo (osnove za obračun) | 🔴 Nedostaje | Blokirano safety pravilom — treba refined granica |
| 3.2 Upravljačko računovodstvo i KPI | 🔴 Nedostaje | Novi modul |
| 3.3 Osnivanje/zatvaranje subjekata | 🟡 LLM znanje | Nema specifičnog modula |
| 3.4 EU fondovi i potpore | 🟡 LLM znanje | Nema specifičnog modula |

### TEMA 1: Eksplicitne granice

| Granica | Nyx Light Status |
|---|---|
| Zabrana pravnog savjetovanja | ✅ Implementirano (OVERSEER) |
| Zabrana autonomnog knjiženja | ✅ Implementirano |
| Zabrana cloud API-ja | ✅ Implementirano |
| Usmjeravanje na stručnjaka | 🟡 Djelomično — treba specifičnije poruke |
| Vremenski svjestan sustav | ✅ Time-Aware RAG postoji |

---

### TEMA 2: Grupe procesa

#### GRUPA A — Unos i obrada dokumentacije

| Proces | Nyx Light Modul | Status | Dubina |
|---|---|---|---|
| A1. Ulazni računi (OCR + razvrstavanje) | `invoice_ocr/extractor.py` | ✅ Postoji | 70% — treba detekcija duplih, anomalija |
| A2. Izlazni računi (formalna kontrola) | — | 🔴 **Nedostaje** | 0% |
| A3. Kontiranje | `kontiranje/engine.py` | 🟡 Osnovni | 40% — treba širi kontni plan, obrazloženja |
| A4. Bankovni izvodi | `bank_parser/parser.py` | ✅ Solidan | 80% — MT940, CSV, IBAN sparivanje |
| A5. Blagajna | `blagajna/validator.py` | 🟡 Minimalan | 30% — samo limit provjera |
| A6. Putni nalozi | `putni_nalozi/checker.py` | 🟡 Minimalan | 30% — samo km-naknada |
| A7. Osnovna sredstva | `kontiranje/engine.py` (dio) | 🟡 Osnovni | 25% — samo amortizacijske stope |
| A8. Obračunske stavke | — | 🔴 **Nedostaje** | 0% |
| A9. IOS usklađivanja | `ios_reconciliation/ios.py` | ✅ Postoji | 60% — generiranje + praćenje |

#### GRUPA B — Obračun plaće

| Proces | Status | Napomena |
|---|---|---|
| Bruto/neto kalkulacija | 🔴 Nedostaje | **Kritičan modul** |
| Doprinosi (MIO I, II, zdrav.) | 🔴 Nedostaje | |
| Porezne olakšice (mladi, invalidi) | 🔴 Nedostaje | |
| JOPPD obrazac | 🔴 Nedostaje | |
| Bolovanja (HZZO) | 🔴 Nedostaje | |
| Autorski honorari/ugovori o djelu | 🔴 Nedostaje | |

#### GRUPA C — Porezne prijave

| Proces | Status | Napomena |
|---|---|---|
| PDV prijava (PPO obrazac) | 🔴 Nedostaje | |
| EC Sales List | 🔴 Nedostaje | |
| Intrastat | 🔴 Nedostaje | |
| PD obrazac (dobit) | 🔴 Nedostaje | |
| DOH obrazac (dohodak) | 🔴 Nedostaje | |
| JOPPD | 🔴 Nedostaje | |

#### GRUPA D — Godišnji financijski izvještaji

| Proces | Status |
|---|---|
| Zaključna knjiženja | 🔴 Nedostaje |
| Bilanca (BIL) | 🔴 Nedostaje |
| Račun dobiti i gubitka (RDG) | 🔴 Nedostaje |
| Novčani tokovi | 🔴 Nedostaje |
| GFI predaja FINA | 🔴 Nedostaje |

#### GRUPA E — Komunikacija s klijentima

| Proces | Status | Napomena |
|---|---|---|
| Odgovori na upite (porezni, zakonski) | ✅ Chat postoji | Jezgra sustava |
| Obavijesti o rokovima | 🔴 Nedostaje | Treba calendar modul |
| Pojašnjenje izvještaja | 🟡 LLM može | Nema specifičnog modula |

#### GRUPA F — Interni procesi

| Proces | Status |
|---|---|
| Upravljanje rokovima | 🔴 Nedostaje |
| Onboarding klijenta | 🔴 Nedostaje |
| Fakturiranje usluga | 🔴 Nedostaje |

#### GRUPA G — Specijalizirani zadaci

| Proces | Status |
|---|---|
| Likvidacijsko računovodstvo | 🔴 LLM znanje |
| Upravljačko računovodstvo / BI | 🔴 Nedostaje |
| Poslovni planovi | 🟡 LLM može |

---

### TEMA 4: Programski alati

| Alat | Nyx Light Podrška | Status |
|---|---|---|
| CPP (export/import) | ✅ XML export | 70% |
| Synesis (export/import) | ✅ CSV/JSON export | 70% |
| e-Računi | 🔴 Nedostaje | 0% |
| Pantheon | 🔴 Nedostaje | 0% |
| ePorezna | 🔴 Ne može pristupiti | Priprema podataka moguća |
| eFINA | 🔴 Ne može pristupiti | Priprema podataka moguća |
| HZMO/HZZO/HZZ | 🔴 Ne može pristupiti | Informativno moguće |
| Excel generiranje | ✅ openpyxl | 80% |
| MT940/CSV bankovni | ✅ Parser postoji | 80% |
| E-mail monitoring | ✅ IMAP watcher | 60% |

---

## PRIORITETNA MAPA NADOGRADNJE

### Faza 1 (Hitno — Sprint 6-7)
1. **Modul B: Obračun plaće** — bruto/neto kalkulator, doprinosi, olakšice
2. **Modul A2: Izlazni računi** — formalna kontrola PDV elemenata
3. **Proširenje RAG korpusa** — puni tekstovi svih 6 zakona
4. **Proširenje kontnog plana** — minimalno 100 konta (RRiF standard)

### Faza 2 (Važno — Sprint 8-9)
1. **Modul A8: Obračunske stavke** — checklist + podsjetnik
2. **Modul C: Porezne prijave** — PPO validator, JOPPD priprema
3. **Modul F: Rokovi** — kalendar zakonskih obveza
4. **Proširenje A5/A6** — dublja validacija blagajne i putnih naloga

### Faza 3 (Korisno — Sprint 10-11)
1. **Modul D: GFI priprema** — BIL/RDG checklist
2. **Modul E: Klijent komunikacija** — predlošci odgovora
3. **e-Računi / Pantheon** — import parseri
4. **HSFI/MSFI** — standardi u RAG bazu

### Faza 4 (Optimizacija — Sprint 12+)
1. **Modul G: BI dashboardi** — KPI za klijente
2. **Onboarding/offboarding** — workflow
3. **DMS integracija** — strukturirano arhiviranje

---

## ZAKLJUČAK

TENA BE dokument je **komplementaran** našem Blueprintu — oni definiraju ŠTO sustav mora znati i raditi, mi definiramo KAKO to tehnički implementirati. Preporučujem:

1. **Usvojiti TENA BE dokument kao funkcionalni zahtjev** (Faza 1 Analiza)
2. **Zadržati naš Blueprint V1.3 kao tehničku arhitekturu** (MoE, Memory, Safety)
3. **Implementirati nedostajuće module po prioritetu** (Plaće → A2 → RAG → Kontiranje)

Sustav Qwen3-235B-A22B **već posjeduje znanje** o većini tema (HSFI, poslovni oblici, EU transakcije) — ali to znanje treba biti **strukturirano, verificirano i vremenski kontekstualizirano** kroz RAG i specijalizirane module, a ne prepušteno općem znanju modela.
