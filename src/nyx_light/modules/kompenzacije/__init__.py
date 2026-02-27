"""
Nyx Light — Kompenzacije (Prijeboj, Cesija, Asignacija)

Prema Zakonu o obveznim odnosima (NN 35/05-156/22), čl. 195-205.

Vrste:
  1. Kompenzacija (prijeboj) — obostrane tražbine iste vrste
  2. Cesija — ustupanje tražbine trećoj osobi
  3. Asignacija — nalog za plaćanje trećem
  4. Multilateralni obračun — 3+ stranke u krug

Proces:
  1. Identificiraj otvorene stavke (IOS)
  2. Pronađi matching parove (A duguje B, B duguje A)
  3. Izračunaj kompenzabilni iznos (min obostrani)
  4. Generiraj Izjavu o kompenzaciji
  5. Evidentiraj knjiženja (zatvaranje stavki)
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("nyx_light.modules.kompenzacije")


@dataclass
class OtvorenaStavka:
    """Jedna otvorena stavka (dugovanje/potraživanje)."""
    partner_oib: str
    partner_naziv: str = ""
    broj_dokumenta: str = ""
    datum: str = ""
    datum_dospijeca: str = ""
    iznos: float = 0.0
    preostalo: float = 0.0  # Neplaćeni dio
    tip: str = "dugovanje"  # dugovanje, potrazivanje
    konto: str = ""
    opis: str = ""


@dataclass
class KompenzacijaPar:
    """Par za kompenzaciju između dva partnera."""
    partner_oib: str
    partner_naziv: str
    nas_dug: float = 0.0       # Mi dugujemo njima
    njihov_dug: float = 0.0    # Oni duguju nama
    kompenzabilno: float = 0.0  # min(nas_dug, njihov_dug)
    stavke_nase: List[OtvorenaStavka] = field(default_factory=list)
    stavke_njihove: List[OtvorenaStavka] = field(default_factory=list)


@dataclass
class KompenzacijaIzjava:
    """Izjava o kompenzaciji (dokument)."""
    broj: str = ""
    datum: str = ""
    nas_oib: str = ""
    nas_naziv: str = ""
    partner_oib: str = ""
    partner_naziv: str = ""
    iznos: float = 0.0
    stavke_zatvorene: List[Dict] = field(default_factory=list)
    napomena: str = ""
    pravni_temelj: str = "Zakon o obveznim odnosima, čl. 195-205 (NN 35/05)"


@dataclass
class MultilateralniObracun:
    """Multilateralna kompenzacija (3+ stranke)."""
    sudionici: List[Dict] = field(default_factory=list)
    # [{oib, naziv, duguje_kome: [{oib, iznos}], potrazuje_od: [{oib, iznos}]}]
    ukupno_kompenzirano: float = 0.0
    lanac: List[Dict] = field(default_factory=list)


class KompenzacijeEngine:
    """Motor za pronalaženje i izvršavanje kompenzacija."""

    def __init__(self):
        self._stats = {"kompenzacije": 0, "multilateralne": 0, "total_kompenzirano": 0.0}

    def find_bilateral(self, stavke: List[OtvorenaStavka]) -> List[KompenzacijaPar]:
        """
        Pronađi bilateralne kompenzacijske parove.

        Grupira stavke po partneru i traži obostrana dugovanja.
        """
        # Group by partner
        by_partner: Dict[str, Dict[str, List[OtvorenaStavka]]] = {}

        for s in stavke:
            key = s.partner_oib
            if key not in by_partner:
                by_partner[key] = {"dugovanje": [], "potrazivanje": [], "naziv": s.partner_naziv}
            by_partner[key][s.tip].append(s)

        # Find pairs
        pairs = []
        for oib, data in by_partner.items():
            dugovanja = data["dugovanje"]  # Mi dugujemo njima
            potrazivanja = data["potrazivanje"]  # Oni duguju nama

            if not dugovanja or not potrazivanja:
                continue

            nas_dug = sum(s.preostalo for s in dugovanja)
            njihov_dug = sum(s.preostalo for s in potrazivanja)
            kompenzabilno = min(nas_dug, njihov_dug)

            if kompenzabilno > 0:
                pairs.append(KompenzacijaPar(
                    partner_oib=oib,
                    partner_naziv=data["naziv"],
                    nas_dug=round(nas_dug, 2),
                    njihov_dug=round(njihov_dug, 2),
                    kompenzabilno=round(kompenzabilno, 2),
                    stavke_nase=sorted(dugovanja, key=lambda x: x.datum_dospijeca or ""),
                    stavke_njihove=sorted(potrazivanja, key=lambda x: x.datum_dospijeca or ""),
                ))

        # Sort by kompenzabilno (biggest first)
        pairs.sort(key=lambda p: p.kompenzabilno, reverse=True)
        return pairs

    def execute_bilateral(self, par: KompenzacijaPar, nas_oib: str, nas_naziv: str
                          ) -> KompenzacijaIzjava:
        """
        Izvrši bilateralnu kompenzaciju — generiraj izjavu i zatvori stavke.
        """
        preostalo = par.kompenzabilno
        zatvorene = []

        # Zatvori naše dugovanje (najstarije prvo)
        for s in par.stavke_nase:
            if preostalo <= 0:
                break
            zatvori = min(s.preostalo, preostalo)
            zatvorene.append({
                "tip": "nase_dugovanje",
                "dokument": s.broj_dokumenta,
                "iznos_zatvoren": round(zatvori, 2),
                "konto": s.konto,
            })
            preostalo -= zatvori

        # Zatvori njihovo dugovanje
        preostalo = par.kompenzabilno
        for s in par.stavke_njihove:
            if preostalo <= 0:
                break
            zatvori = min(s.preostalo, preostalo)
            zatvorene.append({
                "tip": "njihovo_dugovanje",
                "dokument": s.broj_dokumenta,
                "iznos_zatvoren": round(zatvori, 2),
                "konto": s.konto,
            })
            preostalo -= zatvori

        izjava = KompenzacijaIzjava(
            broj=f"KOMP-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            datum=date.today().isoformat(),
            nas_oib=nas_oib,
            nas_naziv=nas_naziv,
            partner_oib=par.partner_oib,
            partner_naziv=par.partner_naziv,
            iznos=par.kompenzabilno,
            stavke_zatvorene=zatvorene,
        )

        self._stats["kompenzacije"] += 1
        self._stats["total_kompenzirano"] += par.kompenzabilno

        return izjava

    def find_multilateral(self, stavke_po_tvrtki: Dict[str, List[OtvorenaStavka]]
                          ) -> Optional[MultilateralniObracun]:
        """
        Pronađi multilateralni kompenzacijski lanac (3+ stranke).

        stavke_po_tvrtki: {oib_tvrtke: [OtvorenaStavka, ...]}
        Traži ciklus: A→B→C→A gdje svaki duguje sljedećem.
        """
        # Build adjacency: who owes whom
        graph: Dict[str, Dict[str, float]] = {}

        for tvrtka_oib, stavke in stavke_po_tvrtki.items():
            for s in stavke:
                if s.tip == "dugovanje" and s.preostalo > 0:
                    if tvrtka_oib not in graph:
                        graph[tvrtka_oib] = {}
                    partner = s.partner_oib
                    graph[tvrtka_oib][partner] = graph[tvrtka_oib].get(partner, 0) + s.preostalo

        # Simple cycle detection (max 3-5 nodes)
        for start in graph:
            path = [start]
            visited = {start}
            if self._find_cycle(graph, start, start, path, visited, max_depth=5):
                # Calculate minimum along cycle
                min_amount = float("inf")
                for i in range(len(path) - 1):
                    a, b = path[i], path[i + 1]
                    min_amount = min(min_amount, graph.get(a, {}).get(b, 0))

                if min_amount > 0:
                    lanac = []
                    for i in range(len(path) - 1):
                        lanac.append({
                            "od": path[i],
                            "prema": path[i + 1],
                            "iznos": round(min_amount, 2),
                        })
                    return MultilateralniObracun(
                        sudionici=[{"oib": p} for p in path[:-1]],
                        ukupno_kompenzirano=round(min_amount, 2),
                        lanac=lanac,
                    )

        return None

    def _find_cycle(self, graph, current, target, path, visited, max_depth):
        """DFS cycle detection."""
        if len(path) > max_depth:
            return False
        for neighbor in graph.get(current, {}):
            if neighbor == target and len(path) > 2:
                path.append(target)
                return True
            if neighbor not in visited:
                visited.add(neighbor)
                path.append(neighbor)
                if self._find_cycle(graph, neighbor, target, path, visited, max_depth):
                    return True
                path.pop()
                visited.discard(neighbor)
        return False

    def generate_knjizenje(self, izjava: KompenzacijaIzjava) -> List[Dict]:
        """Generiraj knjiženja za kompenzaciju."""
        knjizenja = []
        for s in izjava.stavke_zatvorene:
            if s["tip"] == "nase_dugovanje":
                # Smanjujemo obvezu prema dobavljaču
                knjizenja.append({
                    "konto_duguje": s.get("konto", "2200"),  # Dobavljači
                    "konto_potrazuje": "1200",  # Kupci (ili 2200 cross)
                    "iznos": s["iznos_zatvoren"],
                    "opis": f"Kompenzacija {izjava.broj} — {izjava.partner_naziv}",
                    "dokument": izjava.broj,
                })
        return knjizenja

    def get_stats(self) -> Dict[str, Any]:
        return {**self._stats}
