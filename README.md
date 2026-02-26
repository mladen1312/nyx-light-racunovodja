# 🌙 Nyx Light — Računovođa

**Privatni ekspertni AI sustav za računovodstvo i knjigovodstvo u Republici Hrvatskoj**

> Lokalna, offline AI superinteligencija na Mac Studio M5 Ultra (192GB RAM).  
> Opslužuje do 15 djelatnika ureda istovremeno. Zero cloud dependency.

---

## Brzi start

```bash
git clone https://github.com/mladen1312/nyx-light-racunovodja.git
cd nyx-light-racunovodja
chmod +x install.sh
./install.sh        # Instalira SVE jednim klikom
./start.sh          # Pokreće sustav → http://localhost:8080
```

Opcije installera:
- `./install.sh --deps-only` — samo Python dependencies (bez LLM modela)
- `./install.sh --model-only` — samo preuzimanje AI modela

---

## Što Nyx Light radi?

AI sustav koji automatizira 80%+ rutinskog računovodstvenog posla: čita račune, kontira, obračunava plaće, priprema porezne prijave, generira GFI — sve lokalno, bez slanja podataka u cloud.

**Ljudski računovođa zadržava konačni autoritet** (Human-in-the-Loop). AI predlaže, čovjek odobrava. Opcionalno: za klijente s visokim povjerenjem može se uključiti **autonomni mod**.

### Tok podataka

```
Dokument (PDF/CSV/XML) → AI Modul → BookingProposal → Pending
       → Računovođa odobri → Export → CPP XML / Synesis CSV → ERP sustav
```

---

## 36 modula — sve grupe 100%

### A: Dnevni tok (9) | B: Plaće (5) | C: Porezne (6) | D: GFI (6) | E: Komunikacija (3) | F: Ured (3) | G: Specijalizirani (4)

| Modul | Opis |
|---|---|
| A1-A9 | OCR računa, kontiranje, banka (MT940), blagajna (AML 10k), putni nalozi, OS, IOS |
| B1-B5 | Plaće (bruto/neto), JOPPD XML, bolovanje (HZZO), autorski honorari, kadrovska |
| C1-C6 | PDV (PPO), EC Sales List, PD obrazac (10%/18%), DOH (20%/30%), paušal, Intrastat |
| D1-D6 | Kategorija poduzetnika, BIL, RDG, zaključna knjiženja, NTI, GFI XML za FINA |
| E1-E3 | Rokovi, AI chat, onboarding klijenta |
| F1-F3 | Kalendar, client routing (CPP/Synesis), fakturiranje usluga ureda |
| G1-G4 | KPI dashboard, upravljačko, likvidacija (20 koraka ZTD), poslovni planovi |

---

## ERP Integracija — Dvosmjerna komunikacija s CPP i Synesis

### 3 metode konekcije

| Metoda | Smjer | Kad koristiti |
|---|---|---|
| **File** | ↔ | XML/CSV datoteke u watch folderima — najjednostavnije |
| **API** | ↔ | REST pozivi na lokalni CPP/Synesis server |
| **ODBC** | ← | Direktno čitanje iz SQL baze ERP-a |

### Export (Nyx → ERP)

```python
app.process_invoice(ocr_data, "K001")   # AI obradi → pending
app.approve("BP-001", "ana")             # Računovođa odobri
app.export_to_erp("K001")               # → CPP XML ili Synesis CSV
```

### Import (ERP → Nyx)

```python
from nyx_light.erp import create_cpp_connector

cpp = create_cpp_connector(method="odbc", db_connection_string="/path/to/cpp.db")
kontni_plan = cpp.pull_kontni_plan()
otvorene = cpp.pull_otvorene_stavke(konto="1200")
saldo = cpp.pull_saldo_konta("1200")
bilanca = cpp.pull_bruto_bilanca("2026-01")
```

### Autonomni mod (BUDUĆA OPCIJA — po default-u ISKLJUČENO)

U `config.json` — aktivirati **tek kad sustav bude 100% testiran** na klijentu (min. 6 mj.):
```json
{
  "erp": {
    "cpp": {
      "auto_book": true,
      "auto_book_min_confidence": 0.95,
      "auto_book_max_amount": 50000
    }
  }
}
```

Kad se jednog dana uključi, AI automatski knjiži **bez čekanja odobrenja** — ali samo ako:
- Sustav je testiran minimum 6 mjeseci na tom klijentu
- Računovođa eksplicitno uključi `auto_book: true`
- Confidence ≥ 95% za svako knjiženje
- Iznos ≤ 50.000 EUR
- OVERSEER sigurnosne granice prolaze (AML, limiti)
- Svako autonomno knjiženje se bilježi u audit log
- Računovođa dobiva dnevni izvještaj svih auto-knjiženja
- Računovođa može isključiti u **svakom trenutku**

---

## Konfiguracija

### config.json (kreira se automatski pri instalaciji)

```json
{
  "nyx_light": { "max_sessions": 15, "port": 8080 },
  "llm": {
    "primary_model": "mlx-community/Qwen2.5-72B-Instruct-4bit",
    "vision_model": "Qwen/Qwen2.5-VL-7B-Instruct"
  },
  "erp": {
    "cpp": {
      "method": "file",
      "export_dir": "data/exports/cpp",
      "import_dir": "data/imports/cpp",
      "auto_book": false
    },
    "synesis": {
      "method": "api",
      "api_url": "http://192.168.1.100:9090/api",
      "auto_book": false
    }
  },
  "safety": {
    "require_human_approval": true,
    "aml_limit_eur": 10000,
    "cloud_api_blocked": true
  }
}
```

---

## Hardverski zahtjevi

| Komponenta | Minimum | Preporučeno |
|---|---|---|
| Stroj | Mac Studio M4 Ultra | Mac Studio M5 Ultra |
| RAM | 96 GB (Qwen 72B) | 192 GB (Qwen 235B) |
| Disk | 500 GB SSD | 1 TB SSD |
| OS | macOS Sonoma 14+ | macOS Sequoia 15+ |

---

## Sigurnost

- **Zero Cloud** — nijedan podatak ne napušta Mac Studio
- **Human-in-the-Loop** — svako knjiženje zahtijeva odobrenje (osim auto-mod)
- **AML** — gotovinske transakcije > 10.000 EUR automatski blokirane
- **OVERSEER** — zabrana pravnog savjetovanja izvan domene
- **Audit Trail** — svaka akcija (approve/reject/correct) se bilježi
- **DPO Training** — ispravci se koriste za noćno poboljšanje modela

---

## API (http://localhost:8080/docs)

| Endpoint | Metoda | Opis |
|---|---|---|
| `/api/chat` | POST | AI chat |
| `/api/pending` | GET | Knjiženja za odobrenje |
| `/api/approve/{id}` | POST | Odobri |
| `/api/reject/{id}` | POST | Odbij |
| `/api/export/{client_id}` | POST | Export u ERP |
| `/api/dashboard` | GET | KPI, rokovi |
| `/api/clients` | GET | Lista klijenata |
| `/ws` | WebSocket | Real-time updates |

---

## Testovi

```bash
source .venv/bin/activate
PYTHONPATH=src python -m pytest tests/ -v    # 289 testova ✅
```

---

## Statistika projekta

| Metrika | Vrijednost |
|---|---|
| Python moduli | 78 |
| Linije koda | 11.476+ |
| Testovi | 289 ✅ |
| Kontni plan | 153 konta |
| Module direktorija | 27 |

---

## Licenca

Proprietary — Dr. Mladen Mešter / Nexellum

## Autor

**Dr. Mladen Mešter** — Zagreb, Croatia — mladen@nexellum.com
