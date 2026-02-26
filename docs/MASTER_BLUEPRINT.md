# TEMELJNI DOKUMENT ZA RAZVOJ (MASTER BLUEPRINT)

## PROJEKT: Nyx Light — Računovođa (Privatni ekspertni AI sustav)
**Verzija:** 1.3 — MoE Architecture Edition
**Datum izrade:** 26. veljače 2026.
**Posljednja izmjena:** 26. veljače 2026.

---

## 1. Vizija i Obuhvat Projekta

Svrha projekta je implementacija **Nyx Light — Računovođa** sustava, lokalne, offline AI
superinteligencije prilagođene isključivo za računovodstvene procese u RH. Sustav je
dizajniran da opslužuje do **15 djelatnika** ureda istovremeno, bez latencije.

Nyx Light — Računovođa djeluje kao prvi sloj obrade (priprema, razvrstava, predlaže,
kontrolira) i kao ekspertni savjetnik za poreze, dok ljudski računovođa zadržava
**konačni autoritet** (Human-in-the-Loop).

---

## 2. Hardverska i Tehnološka Osnova

### 2.1 Hardverski čvor
- **Server:** 1x Mac Studio M3 Ultra (256 GB Unified Memory)
- **SSD:** Interno ~7 GB/s sekvencionalno čitanje (kritično za MoE swap)
- **Svi podaci:** 100% lokalno (Zero cloud dependency)

### 2.2 Inference Engine
- **vllm-mlx** s tehnologijama:
  - **Continuous Batching** — istovremeno posluživanje 15 korisnika
  - **PagedAttention** — KV cache u blokovima, swap neaktivnih na SSD
  - **MLX Lazy Evaluation** — ništa se ne učitava dok nije potrebno

### 2.3 AI Modeli

| Model | Uloga | Ukupno param. | Aktivno (MoE) | Peak VRAM (4-bit) |
|-------|-------|---------------|----------------|-------------------|
| **Qwen3-235B-A22B** | Logika, zaključivanje, kontiranje | 235B | ~22B | ~124 GB |
| **Qwen3-VL-8B** | OCR/Vid (skenovi, računi, PDF) | 8B | 8B (dense) | ~5 GB |

#### Zašto Qwen3-235B-A22B (MoE)?
- **Mixture-of-Experts (MoE):** Od 235 milijardi parametara, u svakom trenutku
  aktivno je samo **~22 milijarde** (routing mehanizam bira 8–16 eksperata po upitu)
- **Ostalih 213B:** leže neaktivno — na SSD-u ili u lazy-loaded segmentima unified memorije
- **Kvaliteta odgovora:** Na razini modela od 235B (pristup cijelom znanju)
- **Brzina:** Na razini modela od 22B (samo aktivni eksperti se procesiraju)
- **Rezultat:** Dobivamo 235B razinu inteligencije uz 22B razinu resursa

### 2.4 Dynamic Memory Management (MoE + Lazy Loading)

**Arhitektonski princip:** Sustav NIKADA ne drži sve u RAM-u istovremeno.

| Komponenta | Peak memorija | Napomena |
|-----------|---------------|----------|
| Qwen3-235B-A22B (4-bit, aktivni eksperti) | 124 GB | Ne 235B — samo 22B aktivno |
| Qwen3-VL-8B (OCR — on-demand) | 5 GB | Učitava se samo kod slike/PDF-a |
| Neo4j + Qdrant + 4-Tier Memory | 12–18 GB | Većina na SSD-u |
| KV cache (15 konekcija) | 25–35 GB | PagedAttention — pagira se |
| OS + servisi + bufferi | 12–18 GB | macOS + Python + Docker |
| **UKUPNO PEAK** | **178–200 GB** | **56–78 GB slobodno** |

**Mehanizmi zaštite:**
- **MLX lazy evaluation:** Parametri eksperata se ne učitavaju dok routing ne odluči da su potrebni
- **vllm-mlx PagedAttention:** KV cache se dijeli u blokove; neaktivni blokovi se swapaju na SSD
- **On-demand model loading:** OCR model se učitava samo kada korisnik šalje sliku/PDF
- **SSD swap brzina:** ~7 GB/s na M3 Ultra — swap je gotovo neprimjetan za korisnika
- **OOM zaštita:** Čak i pri 15 istovremenih korisnika (rijedak scenarij), sustav stabilno radi

### 2.5 Baza znanja
- **Neo4j** — Knowledge Graph (relacije između klijenata, dobavljača, konta)
- **Qdrant** — Vektorska baza za RAG zakona RH (time-aware)

---

## 3. Arhitektura Podatkovnog Toka i Integracije

### 3.1 Ulazni kanali (Ingestija)
- **IMAP** — automatski nadzor e-maila za dolazeće račune
- **Watch Folderi** — monitoring lokalne mreže za nove dokumente
- **REST API** — ručni upload kroz Web UI
- **Dashboard** — drag-and-drop upload (PDF, CSV, MT940, Excel)

### 3.2 Izlazni kanali (ERP Kompatibilnost)
- **CPP** — XML format izvoza
- **Synesis** — CSV/JSON format izvoza
- Svaki klijent može koristiti različiti ERP sustav

### 3.3 Radni medij
- Čitanje, generiranje i modifikacija Excel (.xlsx) i CSV datoteka
- IOS obrasci, radne liste, bankovni izvodi

---

## 4. Operativni Moduli

### Faza A: Automatizacija visokog volumena (Quick Wins)

**Modul A4 — Bankovni izvodi:**
- Parser za MT940 i CSV formate (Erste, Zaba, PBZ, OTP, Addiko)
- Automatsko prepoznavanje platitelja (IBAN, poziv na broj)
- Sparivanje s otvorenim stavkama
- Generiranje datoteke za uvoz u CPP/Synesis
- Očekivana uspješnost: 85–95%

**Modul A1 — Ulazni računi:**
- Qwen3-VL-8B Vision AI za OCR skenova i PDF-ova
- Ekstrakcija OIB-a, iznosa, PDV stopa i datuma
- Triaža prema klijentu
- Očekivana uspješnost: 80–90%

**Modul A9 — IOS Usklađivanja:**
- Generiranje IOS obrazaca
- Praćenje povrata putem maila
- Automatsko mapiranje razlika u Excel radnu listu

### Faza B: Ekspertna asistencija i Kontrola rizika

**Modul A3 & A7 — Kontiranje i Osnovna sredstva:**
- Prijedlog konta i amortizacijskih stopa (L2 Semantička memorija)
- Qwen3-235B-A22B za kompleksno zaključivanje o kontiranju
- Sustav predlaže, računovođa odobrava

**Modul A5 & A6 — Blagajna i Putni nalozi:**
- Automatska revizija
- Provjera limita gotovine (10.000 EUR)
- Provjera km-naknade (0,30 EUR/km)
- Upozorenja na porezno nepriznate troškove reprezentacije (50%)

### Faza C: Pravna baza i Vremenska svijest (RAG)

- **Time-Aware RAG** sustav s Qdrant vektorskom bazom
- Sadržaj: Zakon o računovodstvu, PDV, dobit, dohodak, mišljenja PU
- Odgovori strogo vezani uz vremenski kontekst poslovnog događaja

---

## 5. Sustav Učenja i Evolucije (4-Tier Memory)

| Tier | Naziv | Trajanje | Mehanizam |
|------|-------|----------|-----------|
| L0 | Working | Sesija | Trenutni ispravak u chatu |
| L1 | Episodic | 24h | Dnevnik interakcija (sprječava ponavljanje greške) |
| L2 | Semantic | 90–365 dana | Trajno pravilo ("Klijent X → konto Y") |
| L3 | Nightly DPO | Permanentno | Fine-tuning težina modela iz odobrenih knjiženja |

**Memory Decay (half-life):**
- kontiranje: 365 dana
- porezno_pravilo: 180 dana
- klijent_preferencija: 90 dana
- zakon: ∞ (nikad ne propada)

---

## 6. Sigurnosni Aksiomi i "Tvrde Granice"

### NIKADA NE MIJENJATI:

1. **Zabrana pravnog savjetovanja:** Sustav automatski odbija upite o ugovorima,
   tužbama ili radnom pravu izvan domene obračuna plaća.

2. **Zabrana autonomnog knjiženja:** Nijedan podatak ne ulazi u CPP ili Synesis
   bez eksplicitnog klika "Odobri" od strane ljudskog operatera.

3. **Apsolutna privatnost:** Isključen je svaki pristup vanjskim cloud API-jima
   (OpenAI, Anthropic, Google). OIB-ovi, plaće i poslovne tajne nikada ne
   napuštaju lokalni sustav.

### Dodatne validacije:
- Blagajna: limit gotovine 10.000 EUR (Zakon o fiskalizaciji)
- Putni nalozi: km-naknada max 0,30 EUR/km
- Reprezentacija: upozorenje na 50% porezno nepriznatog troška

---

## 7. Noćni Procesi

| Vrijeme | Proces | Opis |
|---------|--------|------|
| 02:00 | Nightly DPO | Prikuplja correction parove → generira DPO dataset → LoRA fine-tuning |
| 03:00 | Backup | SQLite hot-backup + gzip kompresija → zadnjih 30 backupa |

---

## 8. Roadmap (Plan Isporuke)

| Sprint | Fokus | Status |
|--------|-------|--------|
| Sprint 1 | Temelji: Mac Studio setup, vllm-mlx, Qwen3-235B-A22B | 🟡 Hardware pending |
| Sprint 2 | Banke (A4): MT940 parser, CPP/Synesis export | ✅ Kod spreman |
| Sprint 3 | Vid (A1): Qwen3-VL-8B OCR, JSON izlaz | ✅ Kod spreman |
| Sprint 4 | Memorija: 4-Tier + DPO pipeline | ✅ Kod spreman |
| Sprint 5 | RAG + UI: Zakoni RH + Web dashboard za 15 zaposlenika | ✅ Kod spreman |

---

## Changelog

| Verzija | Datum | Promjene |
|---------|-------|----------|
| 1.0 | 26.02.2026. | Inicijalni blueprint |
| 1.1 | 26.02.2026. | Arhitektonska definicija |
| 1.3 | 26.02.2026. | **MoE Architecture:** Qwen3-235B-A22B, Dynamic Memory Management, M3 Ultra 256 GB target |
