"""
Nyx Light — Modul D: Novčani tokovi (NTI Obrazac)

Izvještaj o novčanim tokovima prema HSFI 1 / MRS 7.
Indirektna metoda (najčešća za mala/srednja poduzeća u RH).

Struktura:
A. Novčani tokovi od POSLOVNIH AKTIVNOSTI (indirektna metoda)
   - Dobit + amortizacija + promjene radnog kapitala
B. Novčani tokovi od INVESTICIJSKIH AKTIVNOSTI
   - Kupnja/prodaja dugotrajne imovine
C. Novčani tokovi od FINANCIJSKIH AKTIVNOSTI
   - Krediti, otplata, dividende

Neto povećanje/smanjenje novca = A + B + C
"""

from decimal import Decimal, ROUND_HALF_UP
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List

logger = logging.getLogger("nyx_light.modules.novcani_tokovi")


def _d(val) -> "Decimal":
    """Convert to Decimal for precise money calculations."""
    if isinstance(val, Decimal):
        return val
    if isinstance(val, float):
        return Decimal(str(val))
    return Decimal(str(val) if val else '0')


def _r2(val) -> float:
    """Round Decimal to 2 places and return float for JSON compat."""
    return float(Decimal(str(val)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))



@dataclass
class CashFlowData:
    """Ulazni podaci za izračun novčanih tokova."""
    # Iz RDG-a
    neto_dobit: float = 0.0
    amortizacija: float = 0.0
    rashodi_kamata: float = 0.0
    prihodi_kamata: float = 0.0
    porez_na_dobit: float = 0.0

    # Promjene radnog kapitala (tekuća - prethodna godina)
    promjena_zaliha: float = 0.0           # Pozitivno = povećanje zaliha (odljev)
    promjena_potrazivanja: float = 0.0     # Pozitivno = povećanje (odljev)
    promjena_obveze_dobavljaci: float = 0.0  # Pozitivno = povećanje (priljev)
    promjena_ostale_obveze: float = 0.0
    promjena_razgranicenja: float = 0.0

    # Investicije
    kupnja_materijalne_imovine: float = 0.0  # Pozitivan iznos
    prodaja_materijalne_imovine: float = 0.0
    kupnja_nematerijalne: float = 0.0
    kupnja_financijske: float = 0.0
    prodaja_financijske: float = 0.0
    primljene_kamate: float = 0.0

    # Financijske aktivnosti
    primljeni_krediti: float = 0.0
    otplata_kredita: float = 0.0
    placene_kamate: float = 0.0
    isplacene_dividende: float = 0.0
    dokapitalizacija: float = 0.0

    # Početni novac
    novac_pocetak: float = 0.0


@dataclass
class NTIObrazac:
    """Izvještaj o novčanim tokovima."""
    godina: int = 0

    # A: Poslovne aktivnosti (indirektna metoda)
    dobit_prije_poreza: float = 0.0
    amortizacija: float = 0.0
    promjene_radnog_kapitala: float = 0.0
    placeni_porez: float = 0.0
    neto_poslovne: float = 0.0

    # B: Investicijske aktivnosti
    neto_investicijske: float = 0.0

    # C: Financijske aktivnosti
    neto_financijske: float = 0.0

    # Ukupno
    neto_promjena_novca: float = 0.0
    novac_pocetak: float = 0.0
    novac_kraj: float = 0.0

    # Detalji za obrazac
    detalji_poslovne: List[Dict] = field(default_factory=list)
    detalji_investicijske: List[Dict] = field(default_factory=list)
    detalji_financijske: List[Dict] = field(default_factory=list)


class NovcanitTokoviEngine:
    """Priprema NTI obrasca — indirektna metoda."""

    def __init__(self):
        self._count = 0

    def calculate(self, godina: int, data: CashFlowData) -> NTIObrazac:
        """Izračunaj novčane tokove."""
        nti = NTIObrazac(godina=godina, novac_pocetak=data.novac_pocetak)

        # ═══════════════════════════════════════
        # A: POSLOVNE AKTIVNOSTI
        # ═══════════════════════════════════════
        nti.dobit_prije_poreza = data.neto_dobit + data.porez_na_dobit
        nti.amortizacija = data.amortizacija

        # Promjene radnog kapitala
        wrk_cap = (
            - data.promjena_zaliha
            - data.promjena_potrazivanja
            + data.promjena_obveze_dobavljaci
            + data.promjena_ostale_obveze
            + data.promjena_razgranicenja
        )
        nti.promjene_radnog_kapitala = round(wrk_cap, 2)
        nti.placeni_porez = -abs(data.porez_na_dobit)

        nti.neto_poslovne = round(
            nti.dobit_prije_poreza + nti.amortizacija +
            nti.promjene_radnog_kapitala + nti.placeni_porez, 2
        )

        nti.detalji_poslovne = [
            {"aop": "001", "opis": "Dobit prije oporezivanja", "iznos": nti.dobit_prije_poreza},
            {"aop": "002", "opis": "Amortizacija", "iznos": nti.amortizacija},
            {"aop": "003", "opis": "Smanjenje/povećanje zaliha", "iznos": -data.promjena_zaliha},
            {"aop": "004", "opis": "Smanjenje/povećanje potraživanja", "iznos": -data.promjena_potrazivanja},
            {"aop": "005", "opis": "Povećanje/smanjenje obveza", "iznos": data.promjena_obveze_dobavljaci},
            {"aop": "006", "opis": "Ostale promjene radnog kapitala",
             "iznos": data.promjena_ostale_obveze + data.promjena_razgranicenja},
            {"aop": "007", "opis": "Plaćeni porez na dobit", "iznos": nti.placeni_porez},
            {"aop": "A", "opis": "NETO NOVČANI TOK OD POSLOVNIH AKTIVNOSTI",
             "iznos": nti.neto_poslovne, "bold": True},
        ]

        # ═══════════════════════════════════════
        # B: INVESTICIJSKE AKTIVNOSTI
        # ═══════════════════════════════════════
        invest = (
            - data.kupnja_materijalne_imovine
            + data.prodaja_materijalne_imovine
            - data.kupnja_nematerijalne
            - data.kupnja_financijske
            + data.prodaja_financijske
            + data.primljene_kamate
        )
        nti.neto_investicijske = round(invest, 2)

        nti.detalji_investicijske = [
            {"aop": "010", "opis": "Kupnja materijalne imovine", "iznos": -data.kupnja_materijalne_imovine},
            {"aop": "011", "opis": "Prodaja materijalne imovine", "iznos": data.prodaja_materijalne_imovine},
            {"aop": "012", "opis": "Kupnja nematerijalne imovine", "iznos": -data.kupnja_nematerijalne},
            {"aop": "013", "opis": "Kupnja financijske imovine", "iznos": -data.kupnja_financijske},
            {"aop": "014", "opis": "Prodaja financijske imovine", "iznos": data.prodaja_financijske},
            {"aop": "015", "opis": "Primljene kamate", "iznos": data.primljene_kamate},
            {"aop": "B", "opis": "NETO NOVČANI TOK OD INVESTICIJSKIH AKTIVNOSTI",
             "iznos": nti.neto_investicijske, "bold": True},
        ]

        # ═══════════════════════════════════════
        # C: FINANCIJSKE AKTIVNOSTI
        # ═══════════════════════════════════════
        fin = (
            data.primljeni_krediti
            - data.otplata_kredita
            - data.placene_kamate
            - data.isplacene_dividende
            + data.dokapitalizacija
        )
        nti.neto_financijske = round(fin, 2)

        nti.detalji_financijske = [
            {"aop": "020", "opis": "Primljeni krediti", "iznos": data.primljeni_krediti},
            {"aop": "021", "opis": "Otplata kredita", "iznos": -data.otplata_kredita},
            {"aop": "022", "opis": "Plaćene kamate", "iznos": -data.placene_kamate},
            {"aop": "023", "opis": "Isplaćene dividende", "iznos": -data.isplacene_dividende},
            {"aop": "024", "opis": "Dokapitalizacija", "iznos": data.dokapitalizacija},
            {"aop": "C", "opis": "NETO NOVČANI TOK OD FINANCIJSKIH AKTIVNOSTI",
             "iznos": nti.neto_financijske, "bold": True},
        ]

        # ═══════════════════════════════════════
        # UKUPNO
        # ═══════════════════════════════════════
        nti.neto_promjena_novca = round(
            nti.neto_poslovne + nti.neto_investicijske + nti.neto_financijske, 2
        )
        nti.novac_kraj = round(data.novac_pocetak + nti.neto_promjena_novca, 2)

        self._count += 1
        return nti

    def to_dict(self, nti: NTIObrazac) -> Dict[str, Any]:
        return {
            "obrazac": "NTI",
            "godina": nti.godina,
            "A_poslovne": nti.neto_poslovne,
            "B_investicijske": nti.neto_investicijske,
            "C_financijske": nti.neto_financijske,
            "neto_promjena": nti.neto_promjena_novca,
            "novac_pocetak": nti.novac_pocetak,
            "novac_kraj": nti.novac_kraj,
            "detalji": {
                "poslovne": nti.detalji_poslovne,
                "investicijske": nti.detalji_investicijske,
                "financijske": nti.detalji_financijske,
            },
            "requires_approval": True,
        }

    def get_stats(self):
        return {"nti_generated": self._count}


# ════════════════════════════════════════════════════════
# PROŠIRENJA: Direktna/indirektna metoda, likvidnost, burn rate
# ════════════════════════════════════════════════════════

from datetime import date, timedelta


class CashFlowEngine:
    """Izvještaj o novčanim tokovima prema HSFI/MRS 7."""

    def __init__(self):
        self._count = 0

    def direktna_metoda(
        self,
        primici_od_kupaca: float = 0,
        placanja_dobavljacima: float = 0,
        place_i_naknade: float = 0,
        porezi_placeni: float = 0,
        ostali_poslovni_primici: float = 0,
        ostali_poslovni_izdaci: float = 0,
        # Investicijske
        kupnja_dugotrajne: float = 0,
        prodaja_dugotrajne: float = 0,
        # Financijske
        primljeni_krediti: float = 0,
        otplate_kredita: float = 0,
        isplacene_dividende: float = 0,
        # Stanje
        stanje_pocetno: float = 0,
    ) -> dict:
        """Izvještaj direktnom metodom."""

        poslovne = _r2(
            _d(primici_od_kupaca) + _d(ostali_poslovni_primici)
            - _d(placanja_dobavljacima) - _d(place_i_naknade)
            - _d(porezi_placeni) - _d(ostali_poslovni_izdaci)
        )

        investicijske = _r2(
            _d(prodaja_dugotrajne) - _d(kupnja_dugotrajne)
        )

        financijske = _r2(
            _d(primljeni_krediti) - _d(otplate_kredita) - _d(isplacene_dividende)
        )

        neto_promjena = _r2(_d(poslovne) + _d(investicijske) + _d(financijske))
        stanje_zavrsno = _r2(_d(stanje_pocetno) + _d(neto_promjena))

        self._count += 1
        return {
            "metoda": "direktna",
            "poslovne_aktivnosti": {
                "primici_od_kupaca": _r2(_d(primici_od_kupaca)),
                "placanja_dobavljacima": _r2(_d(placanja_dobavljacima)),
                "place_i_naknade": _r2(_d(place_i_naknade)),
                "porezi": _r2(_d(porezi_placeni)),
                "neto_poslovne": poslovne,
            },
            "investicijske_aktivnosti": {
                "kupnja_dugotrajne": _r2(_d(kupnja_dugotrajne)),
                "prodaja_dugotrajne": _r2(_d(prodaja_dugotrajne)),
                "neto_investicijske": investicijske,
            },
            "financijske_aktivnosti": {
                "primljeni_krediti": _r2(_d(primljeni_krediti)),
                "otplate_kredita": _r2(_d(otplate_kredita)),
                "dividende": _r2(_d(isplacene_dividende)),
                "neto_financijske": financijske,
            },
            "neto_promjena": neto_promjena,
            "stanje_pocetno": _r2(_d(stanje_pocetno)),
            "stanje_zavrsno": stanje_zavrsno,
        }

    def burn_rate(
        self,
        stanje: float,
        mjesecni_izdaci: float,
        mjesecni_primici: float = 0,
    ) -> dict:
        """Izračunaj burn rate i runway."""
        neto_burn = _r2(_d(mjesecni_izdaci) - _d(mjesecni_primici))
        if neto_burn > 0 and stanje > 0:
            runway_mjeseci = int(float(_d(stanje) / _d(neto_burn)))
        else:
            runway_mjeseci = -1  # Beskonačan (primici > izdaci)

        return {
            "stanje": _r2(_d(stanje)),
            "mjesecni_izdaci": _r2(_d(mjesecni_izdaci)),
            "mjesecni_primici": _r2(_d(mjesecni_primici)),
            "neto_burn": neto_burn,
            "runway_mjeseci": runway_mjeseci,
            "runway_datum": (
                (date.today() + timedelta(days=30 * runway_mjeseci)).isoformat()
                if runway_mjeseci > 0 else "neograničen"
            ),
            "status": (
                "kritično" if 0 < runway_mjeseci <= 3
                else "upozorenje" if 0 < runway_mjeseci <= 6
                else "stabilno"
            ),
        }

    def likvidnost_koeficijenti(
        self,
        kratkotrajna_imovina: float,
        kratkorocne_obveze: float,
        zalihe: float = 0,
        novac: float = 0,
    ) -> dict:
        """Koeficijenti likvidnosti."""
        ko = kratkorocne_obveze or 1  # Avoid division by zero
        return {
            "koef_tekuce_likvidnosti": _r2(_d(kratkotrajna_imovina) / _d(ko)),
            "koef_ubrzane_likvidnosti": _r2((_d(kratkotrajna_imovina) - _d(zalihe)) / _d(ko)),
            "koef_trenutne_likvidnosti": _r2(_d(novac) / _d(ko)),
            "preporuke": {
                "tekuca": "≥ 2.0 (idealno)",
                "ubrzana": "≥ 1.0",
                "trenutna": "≥ 0.1",
            },
        }

    def get_stats(self):
        return {"cashflow_count": self._count}
