# 🌙 Nyx Light — Računovođa

**Privatni ekspertni AI sustav za računovodstvo i knjigovodstvo u RH**

> *"Ex nocte, lux."* — Iz noći, svjetlo.

## 🎯 Vizija

Lokalna, offline AI superinteligencija za računovodstvene procese u Republici Hrvatskoj.
Opslužuje do 15 djelatnika ureda istovremeno na Mac Studio M5 Ultra (192 GB).

### Ključna načela:
- **100% lokalno** — Zero cloud dependency
- **Human-in-the-Loop** — AI predlaže, računovođa odobrava
- **Kontinuirano učenje** — Sustav uči iz ispravaka zaposlenika
- **Pravna svijest** — Time-Aware RAG za zakone RH

## 🏗️ Arhitektura

```
Web UI (15 korisnika) → FastAPI Gateway → AI Engine (vllm-mlx)
    ├── DeepSeek-R1 / Qwen 72B (Logika)
    ├── Qwen2.5-VL-7B (Vision OCR)
    ├── RAG Engine (Zakoni RH / Qdrant)
    ├── 4-Tier Memory (L0→L3 + Nightly DPO)
    └── OVERSEER Safety + Tvrde Granice
```

## 📦 Moduli

| Modul | Opis | Uspješnost |
|-------|------|-----------|
| A4 — Bankovni izvodi | MT940/CSV parser (Erste, Zaba, PBZ) | 85-95% |
| A1 — Ulazni računi | Vision AI OCR skenova/PDF | 80-90% |
| A9 — IOS usklađivanja | IOS obrasci, praćenje povrata | 90%+ |
| A3/A7 — Kontiranje | Prijedlog konta, amortizacija | L2 memory |
| A5 — Blagajna | Revizija limita (10.000 EUR) | 100% |
| A6 — Putni nalozi | km-naknada (0,30 EUR), repr. | 100% |

## 🚀 Quick Start

```bash
git clone https://github.com/mladen1312/nyx-light-racunovodja.git
cd nyx-light-racunovodja
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m scripts.first_boot
python -m nyx_light.main
```

## 🔒 Sigurnost
1. Zabrana pravnog savjetovanja
2. Zabrana autonomnog knjiženja (bez "Odobri" klika)
3. Apsolutna privatnost (OIB, plaće — ZERO cloud)

© 2026 Dr. Mladen Mešter | Nexellum Lab d.o.o.
