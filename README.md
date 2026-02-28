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
| Računalo | Mac Studio M4 Ultra | Mac Studio M5 Ultra |
| RAM | 128 GB Unified Memory | 192 GB Unified Memory |
| Disk | 1 TB SSD | 2 TB SSD |
| OS | macOS 15 Sequoia | macOS 15.3+ |

Apple Silicon Unified Memory opcije: 36 GB, 64 GB, 96 GB, 128 GB, 192 GB, 256 GB, 512 GB.
Za Qwen3-235B potrebno minimalno 128 GB; za Qwen 72B dovoljno 64 GB.

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

## Moduli

| Modul | Opis | LOC |
|-------|------|-----|
| Bankovni izvodi (A4) | Parser za Erste, Zaba, PBZ — CSV i MT940 | ~600 |
| Ulazni računi (A1) | 4-tier parser (XML → PDF → template → Vision AI) | ~500 |
| Kontiranje (A3) | Rule engine + AI prijedlog konta | ~800 |
| Blagajna (A5) | Provjera limita gotovine, PDV validacija | ~400 |
| Putni nalozi (A6) | km-naknada, dnevnice, porezno nepriznati troškovi | ~450 |
| Osnovna sredstva (A7) | Amortizacija, registar OS | ~350 |
| IOS usklađivanja (A9) | Generiranje obrazaca, praćenje odgovora | ~300 |
| Peppol e-računi | AS4 protokol, EN 16931, Fiskalizacija 2.0 | ~520 |
| Vision LLM | Qwen2.5-VL integracija, tiered fallback | ~340 |
| DPO Memory (L3) | Noćna optimizacija modela iz ispravaka | ~370 |
| Time-Aware RAG | Pretraga zakona s vremenskim kontekstom | ~480 |
| Web/Chat UI | FastAPI + WebSocket, 15 korisnika | ~680 |
| Network | mDNS, Tailscale, firewall, onboarding | ~890 |
| Security | PBKDF2 hash, vault, uloge, JWT tokeni | ~550 |
| DevOps | SSH remote management, deploy, debug | ~580 |
| Fiskalizacija 2.0 | CIS komunikacija, QR kodovi, e-računi | ~600 |
| GFI Izvještaji | XML za FINA-u (bilanca, RDG, bilješke) | ~500 |
| Porez na dobit | Obračun, PD/PD-NN obrasci | ~400 |
| Obračun plaća | JOPPD, doprinosi, porezne kartice | ~700 |

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

| Konfiguracija | RAM | Model | Korisnici |
|--------------|-----|-------|-----------|
| Mac Studio M4 Max | 36 GB | Qwen 7B | do 5 |
| Mac Studio M4 Max | 64 GB | Qwen 32B | do 8 |
| Mac Studio M4 Ultra | 128 GB | Qwen 72B | do 12 |
| Mac Studio M5 Ultra | 192 GB | Qwen3-235B-A22B (4-bit) | do 15 |

## Sigurnost

- **100% lokalno** — nema cloud servisa, nema slanja podataka na internet
- **Enkriptirane lozinke** — PBKDF2-HMAC-SHA256, 600.000 iteracija, 32-byte salt
- **Account lockout** — 5 krivih pokušaja → zaključaj 15 minuta
- **Privatne mreže** — pristup samo s LAN i Tailscale IP adresa
- **MLX izolacija** — LLM port (8422) dostupan samo s localhost-a
- **Human-in-the-Loop** — AI nikada samostalno ne šalje podatke u ERP
- **Auth logging** — svaka prijava se bilježi (IP, vrijeme, uspjeh/neuspjeh)

## Testovi

```bash
python -m pytest tests/ -v
```

Trenutno: **1.300+ testova**, 0 grešaka.

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

---

*Nyx Light — Računovođa v3.0 • Veljača 2026.*
