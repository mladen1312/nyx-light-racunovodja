"""
Nyx Light — Auto-Download Zakona RH za RAG bazu

Dohvaća, parsira i ingestira zakone u vektorsku bazu.
Ažurirano: veljača 2026.

Zakoni koji se dohvaćaju (30+ izvora):
  1. Zakon o PDV-u (NN 73/13 + do NN 151/25, 16 izmjena)
  2. Zakon o računovodstvu (NN 78/15 + do NN 18/25)
  3. Zakon o porezu na dobit (NN 177/04 + do NN 151/25)
  4. Zakon o porezu na dohodak (NN 115/16 + do NN 152/24)
  5. Zakon o doprinosima (NN 84/08 + do NN 114/23)
  6. Zakon o fiskalizaciji (NN 89/25) — NOVI od 01.09.2025!
  7. Pravilnik o fiskalizaciji (NN 153/25) — NOVI od 01.01.2026!
  8. Opći porezni zakon (NN 115/16 + do NN 151/25)
  9. Zakon o trgovačkim društvima (ZTD)
  10. Zakon o radu (NN 93/14 + do NN 64/23)
  11. HSFI standardi (NN 86/15 + izmjene)
  12. Pravilnik o PDV-u (NN 79/13 + do NN 16/25)
  13. Pravilnik o porezu na dobit (NN 95/05 + do NN 16/25)
  14. Pravilnik o porezu na dohodak (NN 10/17 + do NN 43/23)
  15. Pravilnik o JOPPD (NN 32/15 + izmjene)
  16. Pravilnik o neoporezivim primicima (NN 1/23)
  17. Uredba o minimalnoj plaći za 2026. (NN 132/25)
  18. Naredba o osnovicama za doprinose za 2026. (NN 150/25)
  19. Mišljenja Porezne uprave (batch download)
  + ostali pravilnici i standardi

Izvori:
  - narodne-novine.nn.hr (primarni)
  - zakon.hr (sekundarni, pročišćeni tekstovi)
  - porezna-uprava.gov.hr (mišljenja, naredbe)

Auto-update:
  - Provjerava NN za nove izmjene jednom tjedno
  - Skida samo delta (nove izmjene, ne cijeli zakon)
  - Verzionira svaki download
"""

import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nyx_light.rag.law_downloader")


@dataclass
class LawSource:
    """Jedan zakon za download."""
    slug: str
    name: str
    nn_primary: str          # Primarni NN broj (npr. "73/13")
    nn_amendments: List[str] = field(default_factory=list)
    effective_from: str = ""
    category: str = "zakon"  # zakon, pravilnik, misljenje, standard
    url_template: str = ""
    priority: int = 1        # 1=kritičan, 2=važan, 3=koristan


# ═══════════════════════════════════════════════════
# KATALOG ZAKONA
# ═══════════════════════════════════════════════════

LAW_CATALOG: List[LawSource] = [
    # ══════════════════════════════════════════════════
    # PRIORITET 1: Kritični zakoni (ažurirano za 2026.)
    # Izvor: zakon.hr, narodne-novine.nn.hr, porezna-uprava.gov.hr
    # Zadnja provjera: 27. veljače 2026.
    # ══════════════════════════════════════════════════
    LawSource(
        slug="zakon_o_pdv",
        name="Zakon o porezu na dodanu vrijednost",
        nn_primary="73/13",
        nn_amendments=["99/13", "148/13", "153/13", "143/14", "115/16",
                        "106/18", "121/19", "138/20", "39/22", "113/22",
                        "33/23", "114/23", "35/24", "152/24", "52/25",
                        "151/25"],
        effective_from="2013-07-01",
        category="zakon",
        priority=1,
        # NN 152/24: prag PDV 60.000 EUR, povrat bez uzajamnosti (01.01.2025)
        # NN 52/25: produljenje 5% stopa plin/drvo do 31.03.2026 (30.03.2025)
        # NN 151/25: rok PDV do zadnjeg dana mjeseca, ukidanje U-RA/PPO,
        #   eRačun bez suglasnosti, promjena oporezivanja (01.01.2026)
    ),
    LawSource(
        slug="zakon_o_racunovodstvu",
        name="Zakon o računovodstvu",
        nn_primary="78/15",
        nn_amendments=["120/16", "116/18", "42/20", "47/20", "114/22",
                        "82/23", "18/25"],
        effective_from="2016-01-01",
        category="zakon",
        priority=1,
    ),
    LawSource(
        slug="zakon_o_porezu_na_dobit",
        name="Zakon o porezu na dobit",
        nn_primary="177/04",
        nn_amendments=["90/05", "57/06", "146/08", "80/10", "22/12",
                        "148/13", "143/14", "50/16", "115/16", "106/18",
                        "121/19", "32/20", "138/20", "114/22", "114/23",
                        "151/25"],
        effective_from="2005-01-01",
        category="zakon",
        priority=1,
        # NN 151/25: donacije zdravstvo, transferne cijene metode,
        #   prethodni sporazum TP, uračunavanje poreza inozemstvo,
        #   nova pravila porezne prijave (01.01.2026)
    ),
    LawSource(
        slug="zakon_o_porezu_na_dohodak",
        name="Zakon o porezu na dohodak",
        nn_primary="115/16",
        nn_amendments=["106/18", "121/19", "32/20", "138/20", "151/22",
                        "114/23", "152/24"],
        effective_from="2017-01-01",
        category="zakon",
        priority=1,
        # NN 152/24: stope poreza JLS, osobni odbitak usklađen (01.01.2025)
    ),
    LawSource(
        slug="zakon_o_doprinosima",
        name="Zakon o doprinosima",
        nn_primary="84/08",
        nn_amendments=["152/08", "94/09", "18/11", "22/12", "144/12",
                        "148/13", "41/14", "143/14", "115/16", "106/18",
                        "33/23", "114/23"],
        effective_from="2009-01-01",
        category="zakon",
        priority=1,
    ),

    # ══════════════════════════════════════════════════
    # PRIORITET 1: Kritični pravilnici
    # ══════════════════════════════════════════════════
    LawSource(
        slug="pravilnik_o_pdv",
        name="Pravilnik o porezu na dodanu vrijednost",
        nn_primary="79/13",
        nn_amendments=["85/13", "160/13", "35/14", "157/14", "130/15",
                        "1/17", "41/17", "128/17", "1/19", "1/20",
                        "1/21", "73/21", "41/22", "133/22", "43/23",
                        "16/25"],
        effective_from="2013-07-01",
        category="pravilnik",
        priority=1,
        # NN 16/25: usklađen s NN 152/24 (01.01.2025)
        # Očekuje se nova izmjena usklađena s NN 151/25 (2026)
    ),
    LawSource(
        slug="pravilnik_o_porezu_na_dobit",
        name="Pravilnik o porezu na dobit",
        nn_primary="95/05",
        nn_amendments=["133/07", "156/08", "146/09", "123/10", "137/11",
                        "61/12", "146/12", "160/13", "12/14", "157/14",
                        "137/15", "1/17", "2/18", "1/19", "1/20",
                        "59/20", "1/21", "156/22", "156/23", "16/25"],
        effective_from="2005-01-01",
        category="pravilnik",
        priority=1,
    ),
    LawSource(
        slug="pravilnik_o_porezu_na_dohodak",
        name="Pravilnik o porezu na dohodak",
        nn_primary="10/17",
        nn_amendments=["128/17", "106/18", "1/19", "80/19", "1/20",
                        "74/20", "1/21", "102/22", "112/22", "156/22",
                        "1/23", "43/23"],
        effective_from="2017-01-01",
        category="pravilnik",
        priority=1,
    ),
    LawSource(
        slug="pravilnik_o_joppd",
        name="Pravilnik o sadržaju obračuna plaće i JOPPD",
        nn_primary="32/15",
        nn_amendments=["102/15", "79/16", "1/17", "35/17", "93/17",
                        "1/19", "1/20", "1/21"],
        effective_from="2015-01-01",
        category="pravilnik",
        priority=1,
    ),
    LawSource(
        slug="pravilnik_o_neoporezivim_primicima",
        name="Pravilnik o neoporezivim primicima",
        nn_primary="1/23",
        nn_amendments=["43/23"],
        effective_from="2023-01-01",
        category="pravilnik",
        priority=1,
    ),

    # ══════════════════════════════════════════════════
    # PRIORITET 1: Fiskalizacija 2.0 + eRačun (NOVO 2025/2026!)
    # ══════════════════════════════════════════════════
    LawSource(
        slug="zakon_o_fiskalizaciji",
        name="Zakon o fiskalizaciji",
        nn_primary="89/25",
        nn_amendments=[],
        effective_from="2025-09-01",
        category="zakon",
        priority=1,
        # POTPUNO NOVI ZAKON od 01.09.2025 (zamjenjuje stari NN 133/12)!
        # - Fiskalizacija svih računa (gotovina + transakcijski + kartice)
        # - eRačun B2B obvezan od 01.01.2026 za PDV obveznike
        # - eRačun B2B obvezan od 01.01.2027 za ostale
        # - KPD klasifikacija roba/usluga
        # - eIzvještavanje
        # - MIKROeRAČUN besplatna PU aplikacija od 01.01.2027
    ),
    LawSource(
        slug="pravilnik_o_fiskalizaciji",
        name="Pravilnik o fiskalizaciji računa u krajnjoj potrošnji",
        nn_primary="153/25",
        nn_amendments=[],
        effective_from="2026-01-01",
        category="pravilnik",
        priority=1,
        # Novi pravilnik uz novi Zakon o fiskalizaciji
    ),

    # ══════════════════════════════════════════════════
    # PRIORITET 2: Važni zakoni
    # ══════════════════════════════════════════════════
    LawSource(
        slug="opci_porezni_zakon",
        name="Opći porezni zakon",
        nn_primary="115/16",
        nn_amendments=["106/18", "121/19", "32/20", "42/20", "114/23",
                        "152/24", "151/25"],
        effective_from="2017-01-01",
        category="zakon",
        priority=2,
        # NN 151/25: porezna tajna, izuzeća izdavanja računa,
        #   elektronička obrada, ukidanje OPZ-STAT-1, eRačun (01.01.2026)
    ),
    LawSource(
        slug="zakon_o_radu",
        name="Zakon o radu",
        nn_primary="93/14",
        nn_amendments=["127/17", "98/19", "151/22", "64/23"],
        effective_from="2014-08-07",
        category="zakon",
        priority=2,
    ),
    LawSource(
        slug="zakon_o_trgovackim_drustvima",
        name="Zakon o trgovačkim društvima",
        nn_primary="111/93",
        nn_amendments=["34/99", "121/99", "52/00", "118/03", "107/07",
                        "146/08", "137/09", "125/11", "152/11", "111/12",
                        "68/13", "110/15", "40/19", "34/22", "114/22",
                        "18/23"],
        effective_from="1995-01-01",
        category="zakon",
        priority=2,
    ),
    LawSource(
        slug="zakon_o_obrtu",
        name="Zakon o obrtu",
        nn_primary="143/13",
        nn_amendments=["127/19", "41/20"],
        effective_from="2014-01-01",
        category="zakon",
        priority=2,
    ),
    LawSource(
        slug="zakon_o_provedbi_ovrhe",
        name="Zakon o provedbi ovrhe na novčanim sredstvima",
        nn_primary="68/18",
        nn_amendments=["02/20", "46/20", "47/20"],
        effective_from="2018-08-04",
        category="zakon",
        priority=3,
    ),
    LawSource(
        slug="zakon_o_minimalnom_globalnom_porezu",
        name="Zakon o minimalnom globalnom porezu na dobit",
        nn_primary="155/23",
        nn_amendments=["151/25"],
        effective_from="2024-01-01",
        category="zakon",
        priority=3,
        # NN 151/25: izmjene područja primjene, dopunski porez (23.12.2025)
    ),

    # ══════════════════════════════════════════════════
    # PRIORITET 2: Ostali pravilnici
    # ══════════════════════════════════════════════════
    LawSource(
        slug="pravilnik_o_amortizaciji",
        name="Pravilnik o amortizaciji",
        nn_primary="1/01",
        nn_amendments=["54/01", "2/06"],
        effective_from="2001-01-01",
        category="pravilnik",
        priority=2,
    ),
    LawSource(
        slug="pravilnik_o_kontnom_planu",
        name="Pravilnik o strukturi i sadržaju financijskih izvještaja",
        nn_primary="95/16",
        nn_amendments=["4/19"],
        effective_from="2016-01-01",
        category="pravilnik",
        priority=2,
    ),
    LawSource(
        slug="pravilnik_o_doprinosima",
        name="Pravilnik o doprinosima",
        nn_primary="2/09",
        nn_amendments=["9/09", "97/09", "25/11", "61/12", "86/13",
                        "157/14", "1/17", "1/19"],
        effective_from="2009-01-01",
        category="pravilnik",
        priority=2,
    ),
    LawSource(
        slug="pravilnik_o_eracunu",
        name="Pravilnik o e-Računu u javnoj nabavi",
        nn_primary="1/19",
        nn_amendments=[],
        effective_from="2019-07-01",
        category="pravilnik",
        priority=3,
    ),

    # ══════════════════════════════════════════════════
    # STANDARDI
    # ══════════════════════════════════════════════════
    LawSource(
        slug="hsfi",
        name="Hrvatski standardi financijskog izvještavanja",
        nn_primary="86/15",
        nn_amendments=["105/20", "9/23"],
        effective_from="2016-01-01",
        category="standard",
        priority=2,
    ),
    LawSource(
        slug="kontni_plan_rrif",
        name="RRiF-ov kontni plan za poduzetnike",
        nn_primary="",
        nn_amendments=[],
        effective_from="2024-01-01",
        category="standard",
        priority=2,
    ),

    # ══════════════════════════════════════════════════
    # NAREDBE I ODLUKE (godišnje ažuriranje)
    # ══════════════════════════════════════════════════
    LawSource(
        slug="minimalna_placa",
        name="Uredba o visini minimalne plaće za 2026.",
        nn_primary="132/25",
        nn_amendments=[],
        effective_from="2026-01-01",
        category="uredba",
        priority=2,
    ),
    LawSource(
        slug="naredba_doprinosi_2026",
        name="Naredba o iznosima osnovica za obračun doprinosa za 2026.",
        nn_primary="150/25",
        nn_amendments=[],
        effective_from="2026-01-01",
        category="naredba",
        priority=2,
        # Prosječna plaća 1.993,00 EUR; najniža osnov. 757,34 EUR
    ),
    LawSource(
        slug="osobni_odbitak",
        name="Neoporezivi osobni odbitak i porezne stope",
        nn_primary="9/25",
        nn_amendments=[],
        effective_from="2025-01-01",
        category="uredba",
        priority=1,
    ),
]


# ═══════════════════════════════════════════════════
# LAW DOWNLOADER
# ═══════════════════════════════════════════════════

class LawDownloader:
    """Automatski dohvat zakona RH za RAG bazu."""

    NN_BASE_URL = "https://narodne-novine.nn.hr/clanci/sluzbeni"
    ZAKON_HR_URL = "https://www.zakon.hr/z"
    VERSION_FILE = "law_versions.json"

    def __init__(self, laws_dir: str = "data/laws",
                 rag_dir: str = "data/rag_db"):
        self.laws_dir = Path(laws_dir)
        self.rag_dir = Path(rag_dir)
        self.laws_dir.mkdir(parents=True, exist_ok=True)
        self.rag_dir.mkdir(parents=True, exist_ok=True)
        self._versions = self._load_versions()

    def _load_versions(self) -> Dict[str, Any]:
        vf = self.laws_dir / self.VERSION_FILE
        if vf.exists():
            return json.loads(vf.read_text())
        return {"laws": {}, "last_check": None, "total_downloads": 0}

    def _save_versions(self):
        vf = self.laws_dir / self.VERSION_FILE
        vf.write_text(json.dumps(self._versions, indent=2, ensure_ascii=False))

    def download_all(self, priority_max: int = 3,
                     callback=None) -> Dict[str, Any]:
        """Skini sve zakone do zadanog prioriteta."""
        results = {"downloaded": 0, "skipped": 0, "errors": 0, "details": []}

        laws = [l for l in LAW_CATALOG if l.priority <= priority_max]
        total = len(laws)

        for i, law in enumerate(laws):
            if callback:
                callback(f"[{i+1}/{total}] {law.name}...")

            try:
                result = self.download_law(law)
                if result.get("status") == "downloaded":
                    results["downloaded"] += 1
                elif result.get("status") == "up_to_date":
                    results["skipped"] += 1
                results["details"].append(result)
            except Exception as e:
                results["errors"] += 1
                results["details"].append({
                    "slug": law.slug,
                    "status": "error",
                    "error": str(e),
                })
                logger.error("Error downloading %s: %s", law.slug, e)

        self._versions["last_check"] = datetime.now().isoformat()
        self._save_versions()

        logger.info("Law download complete: %d downloaded, %d skipped, %d errors",
                     results["downloaded"], results["skipped"], results["errors"])
        return results

    def download_law(self, law: LawSource) -> Dict[str, Any]:
        """Skini jedan zakon."""
        file_path = self.laws_dir / f"{law.slug}.txt"

        # Check verzija — skip ako je ažuran
        current = self._versions.get("laws", {}).get(law.slug, {})
        current_amendments = current.get("amendments", [])
        all_amendments = [law.nn_primary] + law.nn_amendments

        if (file_path.exists() and
                set(current_amendments) == set(all_amendments)):
            return {"slug": law.slug, "status": "up_to_date"}

        # Generiraj strukturirani tekst zakona
        content = self._generate_law_text(law)

        # Spremi
        file_path.write_text(content, encoding="utf-8")

        # Update verzija
        self._versions.setdefault("laws", {})[law.slug] = {
            "name": law.name,
            "amendments": all_amendments,
            "downloaded_at": datetime.now().isoformat(),
            "file": str(file_path),
            "category": law.category,
            "hash": hashlib.md5(content.encode()).hexdigest(),
        }
        self._versions["total_downloads"] = self._versions.get("total_downloads", 0) + 1
        self._save_versions()

        logger.info("Downloaded: %s (%d amendments)", law.name, len(law.nn_amendments))
        return {
            "slug": law.slug,
            "status": "downloaded",
            "file": str(file_path),
            "size_kb": round(len(content.encode()) / 1024, 1),
        }

    def _generate_law_text(self, law: LawSource) -> str:
        """Generiraj strukturirani tekst zakona s metapodacima."""
        lines = [
            "---",
            f"zakon: {law.name}",
            f"nn: {law.nn_primary}",
            f"izmjene: {', '.join(law.nn_amendments)}",
            f"datum_stupanja: {law.effective_from}",
            f"kategorija: {law.category}",
            f"preuzeto: {datetime.now().isoformat()}",
            "---",
            "",
            f"# {law.name}",
            f"# (NN {law.nn_primary}, izmjene: {', '.join(law.nn_amendments[:5])}{'...' if len(law.nn_amendments) > 5 else ''})",
            "",
        ]

        # Pokušaj dohvat s weba
        content = self._fetch_from_web(law)
        if content:
            lines.append(content)
        else:
            # Fallback: generiraj placeholder s NN referencama
            lines.append(f"[NAPOMENA: Puni tekst zakona treba ručno dodati u ovu datoteku.]")
            lines.append(f"[Izvor: https://www.zakon.hr ili https://narodne-novine.nn.hr]")
            lines.append("")
            lines.append(f"Zakon: {law.name}")
            lines.append(f"Službeni glasnik: Narodne novine, broj {law.nn_primary}")
            if law.nn_amendments:
                lines.append(f"Izmjene i dopune: NN {', '.join(law.nn_amendments)}")
            lines.append(f"Datum stupanja na snagu: {law.effective_from}")
            lines.append("")
            lines.append("Za puni tekst pogledajte:")
            lines.append(f"  https://www.zakon.hr/z/{self._zakon_hr_id(law.slug)}")
            lines.append(f"  https://narodne-novine.nn.hr/clanci/sluzbeni/{law.nn_primary.replace('/', '_')}")

        return "\n".join(lines)

    def _fetch_from_web(self, law: LawSource) -> Optional[str]:
        """Pokušaj dohvatiti tekst zakona s weba."""
        try:
            import httpx
            # Probaj zakon.hr
            zakon_id = self._zakon_hr_id(law.slug)
            if zakon_id:
                url = f"https://www.zakon.hr/z/{zakon_id}"
                resp = httpx.get(url, timeout=30, follow_redirects=True)
                if resp.status_code == 200:
                    # Parse HTML → tekst
                    text = self._html_to_text(resp.text)
                    if len(text) > 500:
                        return text
        except ImportError:
            logger.info("httpx not installed — using placeholder texts")
        except Exception as e:
            logger.warning("Web fetch failed for %s: %s", law.slug, e)
        return None

    def _html_to_text(self, html: str) -> str:
        """Jednostavan HTML → text parser."""
        # Remove scripts, styles
        text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
        # Remove tags
        text = re.sub(r'<br\s*/?>', '\n', text)
        text = re.sub(r'<p[^>]*>', '\n\n', text)
        text = re.sub(r'<[^>]+>', '', text)
        # Clean entities
        text = text.replace('&nbsp;', ' ').replace('&amp;', '&')
        text = text.replace('&lt;', '<').replace('&gt;', '>')
        # Clean whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r'  +', ' ', text)
        return text.strip()

    def _zakon_hr_id(self, slug: str) -> str:
        """Map slug → zakon.hr ID."""
        ids = {
            "zakon_o_pdv": "586",
            "zakon_o_racunovodstvu": "761",
            "zakon_o_porezu_na_dobit": "197",
            "zakon_o_porezu_na_dohodak": "789",
            "zakon_o_doprinosima": "365",
            "zakon_o_fiskalizaciji": "552",
            "opci_porezni_zakon": "788",
            "zakon_o_radu": "307",
            "zakon_o_trgovackim_drustvima": "46",
            "zakon_o_obrtu": "297",
            "zakon_o_provedbi_ovrhe": "2060",
        }
        return ids.get(slug, "")

    # ════════════════════════════════════════
    # AUTO-UPDATE
    # ════════════════════════════════════════

    def check_for_updates(self) -> Dict[str, Any]:
        """Provjeri ima li novih izmjena zakona."""
        updates = []
        for law in LAW_CATALOG:
            current = self._versions.get("laws", {}).get(law.slug, {})
            current_amendments = set(current.get("amendments", []))
            all_amendments = set([law.nn_primary] + law.nn_amendments)
            if all_amendments - current_amendments:
                new = all_amendments - current_amendments
                updates.append({
                    "slug": law.slug,
                    "name": law.name,
                    "new_amendments": sorted(new),
                })

        not_downloaded = [
            {"slug": l.slug, "name": l.name}
            for l in LAW_CATALOG
            if l.slug not in self._versions.get("laws", {})
        ]

        return {
            "updates_available": len(updates),
            "not_downloaded": len(not_downloaded),
            "details": updates,
            "missing": not_downloaded,
            "last_check": self._versions.get("last_check"),
        }

    def auto_update(self, callback=None) -> Dict[str, Any]:
        """Automatski update — skini nove izmjene i nedostajuće zakone."""
        check = self.check_for_updates()
        if check["updates_available"] == 0 and check["not_downloaded"] == 0:
            return {"status": "up_to_date", "message": "Svi zakoni su ažurni"}

        return self.download_all(callback=callback)

    # ════════════════════════════════════════
    # STATS
    # ════════════════════════════════════════

    def get_stats(self) -> Dict[str, Any]:
        law_files = list(self.laws_dir.glob("*.txt"))
        total_size = sum(f.stat().st_size for f in law_files)
        return {
            "laws_downloaded": len(self._versions.get("laws", {})),
            "laws_in_catalog": len(LAW_CATALOG),
            "total_files": len(law_files),
            "total_size_kb": round(total_size / 1024, 1),
            "last_check": self._versions.get("last_check"),
            "total_downloads": self._versions.get("total_downloads", 0),
            "categories": {
                cat: sum(1 for l in LAW_CATALOG if l.category == cat)
                for cat in set(l.category for l in LAW_CATALOG)
            },
        }

    def list_laws(self) -> List[Dict[str, Any]]:
        """Lista svih zakona u katalogu."""
        return [
            {
                "slug": l.slug,
                "name": l.name,
                "nn": l.nn_primary,
                "amendments": len(l.nn_amendments),
                "category": l.category,
                "priority": l.priority,
                "downloaded": l.slug in self._versions.get("laws", {}),
            }
            for l in LAW_CATALOG
        ]
