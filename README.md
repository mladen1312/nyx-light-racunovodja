# 🌙 Nyx Light — Računovođa

**Privatni ekspertni AI sustav za računovodstvo i knjigovodstvo u RH**
**V1.3 — MoE Architecture: Qwen3-235B-A22B**

> *"Ex nocte, lux."* — Iz noći, svjetlo.

## 🎯 Vizija

Lokalna, offline AI superinteligencija za računovodstvene procese u Republici Hrvatskoj.
Opslužuje do 15 djelatnika ureda istovremeno na Mac Studio M3 Ultra (256 GB).

### Ključna načela:
- **100% lokalno** — Zero cloud dependency
- **Human-in-the-Loop** — AI predlaže, računovođa odobrava
- **Kontinuirano učenje** — Sustav uči iz ispravaka zaposlenika
- **Pravna svijest** — Time-Aware RAG za zakone RH
- **MoE efikasnost** — 235B inteligencija uz 22B resursa

## 🧠 MoE Arhitektura (V1.3)

**Qwen3-235B-A22B** koristi Mixture-of-Experts — od 235 milijardi parametara,
samo ~22B je aktivno u svakom trenutku. Rezultat: kvaliteta odgovora na razini
235B modela, a brzina i memorija na razini 22B.

```
┌─────────────────────────────────────────────────────────┐
│  Mac Studio M3 Ultra — 256 GB Unified Memory            │
│                                                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │  Qwen3-235B-A22B (MoE)              ~124 GB     │    │
│  │  ├── 128 eksperata (na SSD/RAM)                 │    │
│  │  ├── 8-16 aktivnih po tokenu (~22B)             │    │
│  │  └── MLX lazy evaluation + PagedAttention       │    │
│  └─────────────────────────────────────────────────┘    │
│                                                         │
│  ┌───────────┐ ┌──────────┐ ┌────────────────────┐     │
│  │ Qwen3-VL  │ │ KV Cache │ │ Neo4j + Qdrant     │     │
│  │ 8B (OCR)  │ │ 15 sesija│ │ + 4-Tier Memory    │     │
│  │ ~5 GB     │ │ ~30 GB   │ │ ~15 GB             │     │
│  │ on-demand │ │ PagedAtt.│ │                    │     │
│  └───────────┘ └──────────┘ └────────────────────┘     │
│                                                         │
│  Peak: ~178-200 GB │ Slobodno: ~56-78 GB               │
└─────────────────────────────────────────────────────────┘
```

## 🏗️ Arhitektura sustava

```
Web UI (15 korisnika) → FastAPI Gateway → AI Engine (vllm-mlx)
    ├── Qwen3-235B-A22B (MoE — Logika, kontiranje, porezi)
    ├── Qwen3-VL-8B (Vision OCR — on-demand)
    ├── RAG Engine (Zakoni RH / Qdrant / time-aware)
    ├── 4-Tier Memory (L0→L3 + Nightly DPO)
    ├── ERP Export (CPP XML + Synesis CSV/JSON)
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
