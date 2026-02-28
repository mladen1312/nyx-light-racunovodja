# Nyx Light — Računovođa

Privatni AI sustav za računovodstvo i knjigovodstvo, dizajniran za računovodstvene urede u Hrvatskoj.

**100% lokalno** — svi podaci ostaju na vašem serveru. Zero cloud dependency.

---

## Značajke

- **AI asistent za kontiranje** — predlaže konta, PDV stope, amortizaciju na temelju povijesnih podataka
- **Čitanje računa (Vision AI)** — automatska ekstrakcija podataka iz skenova, PDF-ova i e-računa
- **Bankovni izvodi** — parser za Erste, Zaba, PBZ (CSV i MT940 format)
- **Peppol e-računi** — AS4 protokol, EN 16931 standard, Fiskalizacija 2.0 kompatibilno
- **Pretraga zakona (RAG)** — hrvatski zakoni s vremenskim kontekstom (ZPDV, ZOR, ZPD, ZDOH...)
- **Blagajna i putni nalozi** — automatska provjera limita gotovine i km-naknade
- **GFI izvještaji** — XML generiranje za FINA-u
- **PDV i JOPPD** — priprema poreznih obrazaca
- **4-Tier Memory** — sustav uči iz vaših ispravaka i noćno se optimizira (DPO)
- **15 istovremenih korisnika** — WebSocket chat, real-time dashboard
- **Mrežni pristup** — LAN (Bonjour/mDNS), Tailscale VPN za rad od kuće

## Projekt u brojevima

| Metrika | Vrijednost |
|---------|-----------|
| Source LOC (Python) | 40.361 |
| WebUI LOC (React/JSX) | 1.050 |
| Test LOC | 14.343 |
| Alati (install.py, nyx-remote.py) | 663 |
| **Ukupno LOC** | **56.417** |
| Python source datoteka | 130 |
| Test datoteka | 35 |
| Operativnih modula | 44 |
| Testova | 1.200+ |

## RAG Baza zakona

Sustav sadrži kompletnu bazu hrvatskih propisa s vremenskim kontekstom:

- Zakon o PDV-u (ZPDV) — stope, oslobođenja, obračunska razdoblja
- Zakon o porezu na dobit (ZPD) — porezna osnovica, stope, olakšice
- Zakon o porezu na dohodak (ZDOH) — razredi, osobni odbitak
- Zakon o računovodstvu (ZOR) — razvrstavanje poduzetnika, rokovi
- Zakon o fiskalizaciji (ZFisk) — blagajnički računi, QR kodovi
- Pravilnik o km-naknadi — 0,30 EUR/km (do 31.12.2024), 0,40 EUR/km (od 1.1.2025)
- RPC 2023 — razrede, kontni plan
- ZSPNFT — sprječavanje pranja novca

## EU kompatibilnost

- **Peppol** — AS4 protokol za B2B/B2G e-račune
- **EN 16931** — europski standard za e-račune
- **ZUGFeRD/Factur-X** — PDF/A-3 hibridni format (DE/FR kompatibilno)
- **FatturaPA** — talijanski format (interoperabilnost)
- **SAF-T** — Standard Audit File for Tax (priprema za implementaciju)

## Hardverski zahtjevi

| Komponenta | Minimum | Preporučeno |
|-----------|---------|-------------|
| Računalo | Mac Studio M4 Max (2025) | Mac Studio M3 Ultra (2025) |
| RAM | 128 GB Unified Memory | 256 GB Unified Memory |
| Disk | 1 TB SSD | 2 TB SSD |
| OS | macOS 15 Sequoia | macOS 15.3+ |

**M4 Max** RAM opcije: 36 GB, 48 GB, 64 GB, 128 GB.
**M3 Ultra** RAM opcije: 96 GB, 256 GB, 512 GB.
Za Qwen3-235B-A22B (4-bit) potrebno minimalno 128 GB; optimalno 256 GB.

## Brza instalacija

```bash
# 1. Kloniraj repo
git clone https://github.com/mladen1312/nyx-light-racunovodja.git
cd nyx-light-racunovodja

# 2. Pokreni installer (automatski sve postavlja)
python3 install.py
# Alternativno: bash install.sh ili bash deploy.sh (legacy skripta)
# Za pokretanje servisa: bash start.sh

# 3. Otvori u pregledniku
open http://nyx-studio.local:8420
```

Installer automatski:
- Provjerava hardver (M-series, RAM)
- Instalira Python pakete
- Kreira bazu podataka i direktorije
- Inicijalizira admin račun
- Učitava RAG bazu zakona (17 zakonskih chunk-ova)
- Postavlja launchd servise (auto-start)
- Registrira Bonjour mDNS servis

## Pristup sustavu

| Lokacija | Adresa |
|----------|--------|
| Ured (Mac/iOS) | `http://nyx-studio.local:8420` |
| Ured (Windows) | `http://<IP_ADRESA>:8420` |
| Od kuće (VPN) | `http://nyx-studio:8420` (potreban Tailscale) |

## Korisničke uloge

| Uloga | Opis |
|-------|------|
| **Admin** | Upravljanje korisnicima, postavke sustava, backup, + sve ispod |
| **Računovođa** | Chat, računi, knjiženja (odobri/ispravi/odbij), zakoni, izvještaji |
| **Pripravnik** | Chat s AI-jem, pregled računa, pretraga zakona |
| **Samo čitanje** | Pretraga zakona i propisa |

Admin dodaje nove korisnike putem Web sučelja ili Python CLI-a:

```python
from nyx_light.security import CredentialVault, UserRole

vault = CredentialVault(db_path="data/vault.db")
vault.create_user("ime.prezime", "Lozinka123!", "Ime Prezime", UserRole.RACUNOVODA)
```

## Arhitektura

```
┌─────────────────────────────────────────────────┐
│              UREDSKA MREŽA (LAN)                │
│  💻 Djelatnik 1   💻 Djelatnik 2   💻 Djelatnik N │
│     └──────────────┼──────────────┘              │
│                    │ HTTP :8420                   │
│            ┌───────┴────────┐                    │
│            │   Mac Studio   │                    │
│            │                │                    │
│            │  FastAPI :8420 │ ← Web UI + API     │
│            │  MLX    :8422 │ ← LLM (localhost)  │
│            │  SQLite       │ ← Podaci           │
│            │  Qdrant       │ ← Vektorska baza   │
│            └───────┬────────┘                    │
│              Tailscale VPN                       │
│  🏠 Djelatnik (od kuće)   📱 Djelatnik (mobitel) │
└─────────────────────────────────────────────────┘
```

## AI Modeli

| Model | Namjena | RAM |
|-------|---------|-----|
| Qwen3-235B-A22B (4-bit) | Logika, kontiranje, porezno savjetovanje | ~130 GB |
| Qwen2.5-VL-7B | Čitanje skenova i fotografija računa | ~8 GB |
| bge-m3 | Embeddings za RAG pretragu zakona | ~2 GB |

## Operativni moduli (44 modula, 17.381 LOC)

### Faza A — Automatizacija visokog volumena

| Modul | Opis | LOC |
|-------|------|-----|
| invoice_ocr | 4-tier parser (XML → PDF → template → Vision AI), EU računi | 1.665 |
| universal_parser | Univerzalni parser dokumenata, auto-detekcija formata | 1.356 |
| bank_parser | Erste, Zaba, PBZ — CSV i MT940 izvodi | 495 |
| eracuni_parser | Parser za eRačuni.hr XML format | 248 |
| ios_reconciliation | IOS obrasci, praćenje odgovora, Excel export | 527 |

### Faza B — Kontiranje i financije

| Modul | Opis | LOC |
|-------|------|-----|
| kontiranje | Rule engine + kontni plan + AI prijedlog | 543 |
| blagajna | Provjera limita gotovine (10.000 EUR), PDV | 423 |
| putni_nalozi | km-naknada, dnevnice, porezno nepriznati troškovi | 539 |
| osnovna_sredstva | Amortizacija, registar, rashodovanje | 220 |
| ledger | Glavna knjiga, dnevnik knjiženja | 301 |
| fakturiranje | Izlazni računi, predlošci | 238 |
| outgoing_invoice | Izlazne fakture, serijski ispis | 219 |
| kompenzacije | Jednostrana i multilateralna kompenzacija | 258 |
| likvidacija | Likvidatura ulaznih računa | 179 |
| accruals | Vremensko razgraničenje, PVR/AVR | 219 |
| novcani_tokovi | Cash flow izvještaji, projekcije | 211 |

### Faza C — Porezi i plaće

| Modul | Opis | LOC |
|-------|------|-----|
| porez_dobit | Obračun, PD/PD-NN obrasci | 521 |
| porez_dohodak | Godišnji obračun, porezne kartice | 242 |
| pdv_prijava | PDV obrazac, PP-PDV, ZP obrasci | 205 |
| payroll | Obračun plaća, doprinosi, neto/bruto | 355 |
| joppd | JOPPD obrazac, XML export za ePorezna | 236 |
| drugi_dohodak | Ugovori o djelu, autorski honorari | 213 |
| bolovanje | HZZO obrasci, refundacije | 179 |

### Faza D — E-računi i fiskalizacija

| Modul | Opis | LOC |
|-------|------|-----|
| peppol | AS4 protokol, EN 16931, B2B/B2G | 521 |
| fiskalizacija2 | CIS komunikacija, QR kodovi, Fiskalizacija 2.0 | 707 |
| e_racun | E-račun validacija i slanje | 307 |
| intrastat | Intrastat izvještaji za DZS | 185 |

### Faza E — Izvještavanje i analitika

| Modul | Opis | LOC |
|-------|------|-----|
| gfi_xml | GFI XML za FINA-u (bilanca, RDG) | 330 |
| gfi_prep | Priprema podataka za GFI | 203 |
| reports | Financijski izvještaji, bruto bilanca | 450 |
| kpi | Ključni pokazatelji poslovanja | 192 |
| management_accounting | Upravljačko računovodstvo, troškovna mjesta | 257 |
| business_plan | Poslovni planovi, projekcije | 208 |
| audit | Revizijski trag, kontrolne točke | 359 |

### Faza F — Upravljanje i komunikacija

| Modul | Opis | LOC |
|-------|------|-----|
| web_ui | FastAPI + WebSocket, dashboard, 15 korisnika | 894 |
| network | mDNS, Tailscale, firewall, onboarding | 629 |
| vision_llm | Qwen2.5-VL integracija, tiered fallback | 413 |
| rag | Time-Aware RAG pretraga zakona | 584 |
| scalability | Load balancing, queue management | 411 |
| client_management | Registar klijenata, CRM | 232 |
| communication | Email/SMS obavijesti, notifikacije | 236 |
| kadrovska | Kadrovska evidencija, ugovori | 186 |
| deadlines | Porezni kalendar, podsjetnici na rokove | 165 |
| place | Šifarnik mjesta, poštanski brojevi | 319 |

## Sistemski slojevi (22.980 LOC)

| Sloj | Opis | LOC |
|------|------|-----|
| rag/ | RAG engine, vektorska baza, law loader, NN monitor | 3.168 |
| silicon/ | Apple Silicon optimizacija, vLLM-MLX, speculative decoding | 2.992 |
| api/ | FastAPI aplikacija, REST endpointi | 1.752 |
| pipeline/ | Multi-client pipeline, persistent obrada | 1.347 |
| deployment/ | Deployment skripte, launchd konfiguracija | 1.233 |
| devops/ | SSH remote management, deploy, debug, monitoring | 965 |
| llm/ | LLM provider, chat bridge, request queue sa semaphore | 951 |
| vision/ | Vision pipeline, document classifier | 921 |
| core/ | Config, knowledge graph, module router, types | 806 |
| memory/ | 4-Tier Memory (working, episodic, semantic, DPO) | 751 |
| erp/ | CPP/Synesis integracija, XML/JSON/CSV export | 610 |
| security/ | PBKDF2 vault, uloge, tokeni, stealth mode | 605 |
| model_manager/ | Download, kvantizacija, verzioniranje modela | 598 |
| ingest/ | Email watcher, folder watcher | 506 |
| auth/ | Autentikacija, WebSocket auth | 487 |
| ui/ | Web UI backend | 479 |
| verification/ | Verifikacija podataka i izračuna | 439 |
| audit/ | Audit export, revizijski trag | 396 |
| ostalo | router, kg, notifications, storage, export, monitoring, metrics, backup, safety, finetune, sessions, scheduler, prompts, registry | 2.974 |

## Podržani zakoni (RAG baza)

- Zakon o PDV-u (ZPDV) — sva mišljenja Porezne uprave
- Zakon o porezu na dobit (ZPD)
- Zakon o porezu na dohodak (ZDOH)
- Zakon o računovodstvu (ZOR)
- Zakon o fiskalizaciji
- Računski Plan za Poduzetnike (RPC 2023)
- Pravilnici i uredbe — automatski ažurirani s vremenskim kontekstom

## EU e-računi i interoperabilnost

Sustav podržava europske standarde e-fakturiranja:
- **Peppol BIS 3.0** — AS4 protokol za B2B i B2G
- **EN 16931** (UBL 2.1 + CII) — europska norma za e-račune
- **ZUGFeRD 2.1 / Factur-X** — PDF/A-3 s ugrađenim XML-om (DE/FR standard)
- **FatturaPA** — talijanski standard (za prekogranične transakcije)
- **Fiskalizacija 2.0 RH** — CIS komunikacija, QR kodovi

## Hardverske opcije

**Trenutno dostupno (Mac Studio 2025):**

| Konfiguracija | Chip | RAM | Model | Korisnici |
|--------------|------|-----|-------|-----------|
| Mac Studio M4 Max (14-core) | M4 Max | 36 GB | Qwen 7B | do 5 |
| Mac Studio M4 Max (16-core) | M4 Max | 64 GB | Qwen 32B | do 8 |
| Mac Studio M4 Max (16-core) | M4 Max | 128 GB | Qwen 72B (Q8) | do 12 |
| Mac Studio M3 Ultra (28-core) | M3 Ultra | 96 GB | Qwen 72B (Q4) | do 10 |
| Mac Studio M3 Ultra (32-core) | M3 Ultra | 256 GB | Qwen3-235B-A22B (4-bit) | do 15 |
| Mac Studio M3 Ultra (32-core) | M3 Ultra | 512 GB | Qwen3-235B + VL-72B | do 15+ |

**Uskoro (Mac Studio M5 — očekivano 2026):**

M5 Max i M5 Ultra najavljeni su za prvu polovicu 2026. Očekuju se iste ili veće RAM opcije uz bolje performanse.

## Sigurnost

- **100% lokalno** — nema cloud servisa, nema slanja podataka na internet
- **Enkriptirane lozinke** — PBKDF2-HMAC-SHA256, 600.000 iteracija, 32-byte salt
- **Account lockout** — 5 krivih pokušaja → zaključaj 15 minuta
- **Privatne mreže** — pristup samo s LAN i Tailscale IP adresa
- **MLX izolacija** — LLM port (8422) dostupan samo s localhost-a
- **Human-in-the-Loop** — AI nikada samostalno ne šalje podatke u ERP
- **Auth logging** — svaka prijava se bilježi (IP, vrijeme, uspjeh/neuspjeh)
- **Role-Based Access Control** — 4 uloge s granularnim dozvolama

## Testovi

```bash
python -m pytest tests/ -v
```

35 test datoteka, **1.200+ testova** (14.343 LOC testnog koda).

## Razvoj

Za remote development putem SSH-a:

```bash
python nyx-remote.py connect          # Test konekcije
python nyx-remote.py deploy           # Git pull + test + restart
python nyx-remote.py deploy --quick   # Git pull + restart (bez testova)
python nyx-remote.py logs nyx-api     # Zadnjih 50 linija logova
python nyx-remote.py errors           # Greške od danas
python nyx-remote.py restart nyx-api  # Restart API servisa
python nyx-remote.py health           # Health check
python nyx-remote.py tests            # Pokreni testove
```

## Licenca

Privatni softver. Sva prava pridržana.
Kreator: **Mladen Mešter**

---

*Nyx Light — Računovođa v3.0 • 56.417 LOC • 130 modula • Veljača 2026.*
