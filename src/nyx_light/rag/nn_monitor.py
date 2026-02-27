"""
Nyx Light — Narodne Novine Monitor

Automatski prati Narodne Novine za izmjene zakona relevantnih za
računovodstvo i knjigovodstvo u RH.

Funkcije:
  1. Scrape NN web stranice za nove brojeve
  2. Filtrira samo zakone/pravilnike bitne za računovodstvo
  3. Detektira izmjene postojećih zakona u RAG bazi
  4. Automatski skida nove verzije i ingestira u RAG
  5. Šalje obavijest administratoru o promjenama
  6. Vodi log svih provjera i promjena

Pokreće se:
  - Automatski: cron svake nedjelje u 03:00
  - Ručno: python -m nyx_light.rag.nn_monitor --check
  - Iz update.sh skripte

Izvor: https://narodne-novine.nn.hr
"""

import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("nyx_light.rag.nn_monitor")

# ═══════════════════════════════════════════════════
# KLJUČNE RIJEČI ZA FILTRIRANJE NN SADRŽAJA
# ═══════════════════════════════════════════════════

# Zakoni i pravilnici koje pratimo
TRACKED_KEYWORDS = [
    # Porezni zakoni
    "porez na dodanu vrijednost", "pdv",
    "porez na dobit",
    "porez na dohodak",
    "doprinosi",
    "fiskalizacija",
    "opći porezni zakon",
    # Računovodstveni zakoni
    "zakon o računovodstvu",
    "financijsko izvještavanje", "hsfi", "msfi",
    "revizija",
    # Pravilnici
    "pravilnik o pdv", "pravilnik o porezu na dodanu vrijednost",
    "pravilnik o porezu na dobit",
    "pravilnik o porezu na dohodak",
    "pravilnik o doprinosima",
    "joppd", "obrazac joppd",
    "pravilnik o sadržaju obračuna plaće",
    # Rad i plaće
    "zakon o radu",
    "minimalna plaća",
    "osobni odbitak",
    "neoporezivi primici",
    # Trgovačka društva
    "zakon o trgovačkim društvima",
    "zakon o obrtu",
    # EU/Intrastat
    "intrastat",
    "e-račun", "eračun",
    # Stope i pragovi
    "stopa pdv", "porezna stopa",
    "prag za pdv",
    "amortizacija", "amortizacijske stope",
    # Rokovi
    "porezni kalendar",
]

# Specifični NN slug-ovi zakona koje pratimo
TRACKED_LAWS = {
    "zakon-o-porezu-na-dodanu-vrijednost": "zakon_o_pdv",
    "zakon-o-racunovodstvu": "zakon_o_racunovodstvu",
    "zakon-o-porezu-na-dobit": "zakon_o_porezu_na_dobit",
    "zakon-o-porezu-na-dohodak": "zakon_o_porezu_na_dohodak",
    "zakon-o-doprinosima": "zakon_o_doprinosima",
    "zakon-o-fiskalizaciji-u-prometu-gotovinom": "zakon_o_fiskalizaciji",
    "opci-porezni-zakon": "opci_porezni_zakon",
    "zakon-o-radu": "zakon_o_radu",
    "pravilnik-o-porezu-na-dodanu-vrijednost": "pravilnik_o_pdv",
    "pravilnik-o-porezu-na-dobit": "pravilnik_o_porezu_na_dobit",
    "pravilnik-o-porezu-na-dohodak": "pravilnik_o_porezu_na_dohodak",
}


@dataclass
class NNArticle:
    """Jedan članak iz Narodnih Novina."""
    nn_number: str         # npr. "73/13"
    year: int              # 2013
    issue: int             # 73
    title: str             # Naziv propisa
    category: str          # zakon, pravilnik, uredba, odluka
    url: str               # Link na puni tekst
    published_date: str    # Datum objave
    relevance_score: float = 0.0  # 0-1 koliko je relevantan za računovodstvo
    matched_keywords: List[str] = field(default_factory=list)
    is_amendment: bool = False     # Je li izmjena postojećeg zakona
    parent_law: str = ""           # Slug zakona koji mijenja


@dataclass
class NNCheckResult:
    """Rezultat provjere Narodnih Novina."""
    checked_at: str
    nn_issues_checked: int
    relevant_found: int
    new_amendments: List[NNArticle]
    new_laws: List[NNArticle]
    errors: List[str]


class NNMonitor:
    """Monitor za Narodne Novine — prati izmjene zakona."""

    NN_BASE = "https://narodne-novine.nn.hr"
    NN_SLUZBENI = f"{NN_BASE}/clanci/sluzbeni"
    CHECK_LOG = "nn_check_log.json"

    def __init__(self, laws_dir: str = "data/laws",
                 rag_dir: str = "data/rag_db"):
        self.laws_dir = Path(laws_dir)
        self.rag_dir = Path(rag_dir)
        self.laws_dir.mkdir(parents=True, exist_ok=True)
        self._check_log = self._load_check_log()

    def _load_check_log(self) -> Dict[str, Any]:
        log_file = self.laws_dir / self.CHECK_LOG
        if log_file.exists():
            return json.loads(log_file.read_text())
        return {
            "checks": [],
            "last_check": None,
            "last_nn_issue": None,
            "total_updates_found": 0,
            "known_amendments": {},
        }

    def _save_check_log(self):
        log_file = self.laws_dir / self.CHECK_LOG
        log_file.write_text(json.dumps(self._check_log, indent=2,
                                        ensure_ascii=False))

    # ════════════════════════════════════════
    # PROVJERA NOVIH BROJEVA NN
    # ════════════════════════════════════════

    def check_for_updates(self, days_back: int = 30) -> NNCheckResult:
        """
        Provjeri NN za nove izmjene zakona.

        Koraci:
          1. Dohvati popis novih brojeva NN (zadnjih N dana)
          2. Za svaki broj, provjeri sadržaj
          3. Filtriraj samo relevantne za računovodstvo
          4. Detektiraj izmjene postojećih zakona
          5. Vrati rezultat s listom novosti
        """
        errors = []
        new_amendments = []
        new_laws = []
        issues_checked = 0

        try:
            # Dohvati listu novih NN brojeva
            issues = self._fetch_recent_issues(days_back)
            issues_checked = len(issues)

            for issue in issues:
                try:
                    articles = self._fetch_issue_contents(issue)
                    for article in articles:
                        # Izračunaj relevantnost
                        article.relevance_score = self._calculate_relevance(article)
                        if article.relevance_score >= 0.5:
                            if article.is_amendment:
                                new_amendments.append(article)
                            else:
                                new_laws.append(article)
                except Exception as e:
                    errors.append(f"Error processing NN {issue}: {e}")
                    logger.warning("Error processing NN %s: %s", issue, e)

        except Exception as e:
            errors.append(f"Error fetching NN: {e}")
            logger.error("Error checking NN: %s", e)

        result = NNCheckResult(
            checked_at=datetime.now().isoformat(),
            nn_issues_checked=issues_checked,
            relevant_found=len(new_amendments) + len(new_laws),
            new_amendments=new_amendments,
            new_laws=new_laws,
            errors=errors,
        )

        # Log check
        self._check_log["checks"].append({
            "date": result.checked_at,
            "issues_checked": issues_checked,
            "relevant_found": result.relevant_found,
            "amendments": len(new_amendments),
            "new_laws": len(new_laws),
        })
        self._check_log["last_check"] = result.checked_at
        self._check_log["total_updates_found"] += result.relevant_found
        self._save_check_log()

        return result

    def _fetch_recent_issues(self, days_back: int) -> List[str]:
        """Dohvati brojeve NN iz zadnjih N dana."""
        issues = []
        try:
            import httpx
            today = date.today()
            # NN objavljuje otprilike 3-5 brojeva tjedno
            # Probaj dohvatiti index stranicu
            url = f"{self.NN_SLUZBENI}/index"
            resp = httpx.get(url, timeout=30, follow_redirects=True)
            if resp.status_code == 200:
                # Parse issue numbers from index
                pattern = r'(\d+)/(\d{2,4})'
                for match in re.finditer(pattern, resp.text):
                    issue_num, year = match.groups()
                    if len(year) == 2:
                        year = "20" + year
                    if int(year) >= today.year - 1:
                        nn_ref = f"{issue_num}/{year[2:]}"
                        if nn_ref not in issues:
                            issues.append(nn_ref)
            logger.info("Found %d recent NN issues", len(issues))
        except ImportError:
            logger.info("httpx not installed — using cached law catalog")
            # Fallback: generiraj pretpostavljene brojeve za tekuću godinu
            current_year = date.today().year
            yr = str(current_year)[2:]
            for i in range(1, 160):
                issues.append(f"{i}/{yr}")
        except Exception as e:
            logger.warning("Cannot fetch NN index: %s", e)
        return issues[:50]  # Max 50 issues per check

    def _fetch_issue_contents(self, nn_ref: str) -> List[NNArticle]:
        """Dohvati sadržaj jednog broja NN."""
        articles = []
        parts = nn_ref.split("/")
        if len(parts) != 2:
            return articles

        issue_num, year_short = parts
        year = int("20" + year_short) if len(year_short) == 2 else int(year_short)

        try:
            import httpx
            url = f"{self.NN_SLUZBENI}/{year}/{nn_ref.replace('/', '_')}"
            resp = httpx.get(url, timeout=30, follow_redirects=True)
            if resp.status_code == 200:
                articles = self._parse_nn_page(resp.text, nn_ref, year)
        except ImportError:
            pass  # No httpx, skip web fetch
        except Exception as e:
            logger.debug("Cannot fetch NN %s: %s", nn_ref, e)

        return articles

    def _parse_nn_page(self, html: str, nn_ref: str, year: int) -> List[NNArticle]:
        """Parse NN stranicu za članke."""
        articles = []
        # Jednostavan parser — traži naslove propisa
        title_pattern = re.compile(
            r'(?:Zakon|Pravilnik|Uredba|Odluka|Naredba|Ispravak)\s+'
            r'o\s+[\w\s,\-–—]+',
            re.IGNORECASE
        )
        for match in title_pattern.finditer(html):
            title = match.group(0).strip()
            # Kategorija
            title_lower = title.lower()
            if title_lower.startswith("zakon"):
                cat = "zakon"
            elif title_lower.startswith("pravilnik"):
                cat = "pravilnik"
            elif title_lower.startswith("uredba"):
                cat = "uredba"
            else:
                cat = "ostalo"

            # Provjeri je li izmjena
            is_amendment = any(kw in title_lower for kw in [
                "izmjen", "dopun", "isprav",
            ])

            article = NNArticle(
                nn_number=nn_ref,
                year=year,
                issue=int(nn_ref.split("/")[0]),
                title=title[:200],
                category=cat,
                url=f"{self.NN_SLUZBENI}/{year}/{nn_ref.replace('/', '_')}",
                published_date=f"{year}-01-01",
                is_amendment=is_amendment,
            )
            articles.append(article)

        return articles

    # ════════════════════════════════════════
    # RELEVANCE SCORING
    # ════════════════════════════════════════

    def _calculate_relevance(self, article: NNArticle) -> float:
        """Izračunaj relevantnost članka za računovodstvo (0-1)."""
        score = 0.0
        title_lower = article.title.lower()
        matched = []

        for keyword in TRACKED_KEYWORDS:
            # Provjera s tolerancijom na hrvatske padeže
            # "porez na dodanu vrijednost" treba matchati i "porezu na dodanu vrijednost"
            kw_words = keyword.split()
            kw_stems = [w[:min(len(w), max(3, len(w)-2))] for w in kw_words]
            stem_match = all(
                any(stem in tw for tw in title_lower.split())
                for stem in kw_stems
            ) if len(kw_words) > 1 else keyword[:max(3, len(keyword)-2)] in title_lower

            if keyword in title_lower or stem_match:
                # Različite težine po vrsti ključne riječi
                if keyword in ["pdv", "porez na dodanu vrijednost",
                                "porez na dobit", "porez na dohodak",
                                "zakon o računovodstvu", "doprinosi"]:
                    score += 0.4  # Kritični zakoni
                elif keyword in ["fiskalizacija", "joppd", "hsfi",
                                  "opći porezni zakon", "minimalna plaća"]:
                    score += 0.3  # Važni zakoni
                else:
                    score += 0.15  # Korisni zakoni
                matched.append(keyword)

        # Bonus za zakon/pravilnik (vs uredba/odluka)
        if article.category in ("zakon", "pravilnik"):
            score += 0.1

        # Bonus za izmjenu postojećeg praćenog zakona
        for nn_slug, our_slug in TRACKED_LAWS.items():
            if nn_slug.replace("-", " ") in title_lower.replace("-", " "):
                score += 0.3
                article.parent_law = our_slug
                article.is_amendment = True
                break

        article.matched_keywords = matched
        return min(score, 1.0)

    # ════════════════════════════════════════
    # AUTO-UPDATE RAG BAZE
    # ════════════════════════════════════════

    def auto_update_rag(self, callback=None) -> Dict[str, Any]:
        """
        Automatski update RAG baze:
          1. Provjeri NN za nove izmjene
          2. Skini nove verzije zakona
          3. Ingestiraj u vektorsku bazu
          4. Log promjene
        """
        if callback:
            callback("Provjeravam Narodne Novine za nove izmjene...")

        check = self.check_for_updates(days_back=14)

        results = {
            "checked_at": check.checked_at,
            "issues_checked": check.nn_issues_checked,
            "relevant_found": check.relevant_found,
            "amendments_detected": [],
            "rag_updated": False,
            "errors": check.errors,
        }

        if check.relevant_found == 0:
            results["message"] = "Nema novih izmjena zakona u zadnjih 14 dana"
            return results

        # Za svaku novu izmjenu, update RAG
        from .law_downloader import LawDownloader
        downloader = LawDownloader(
            laws_dir=str(self.laws_dir),
            rag_dir=str(self.rag_dir),
        )

        for amendment in check.new_amendments:
            if amendment.parent_law:
                if callback:
                    callback(f"Ažuriram: {amendment.title} (NN {amendment.nn_number})")

                # Dodaj novi NN broj u poznate izmjene
                known = self._check_log.get("known_amendments", {})
                parent = amendment.parent_law
                if parent not in known:
                    known[parent] = []
                if amendment.nn_number not in known[parent]:
                    known[parent].append(amendment.nn_number)

                results["amendments_detected"].append({
                    "law": amendment.parent_law,
                    "title": amendment.title,
                    "nn": amendment.nn_number,
                })

        # Re-download ažurirane zakone
        dl_result = downloader.download_all(callback=callback)
        results["rag_updated"] = dl_result.get("downloaded", 0) > 0

        self._check_log["known_amendments"] = known
        self._save_check_log()

        return results

    # ════════════════════════════════════════
    # STATS & STATUS
    # ════════════════════════════════════════

    def get_status(self) -> Dict[str, Any]:
        return {
            "last_check": self._check_log.get("last_check"),
            "total_checks": len(self._check_log.get("checks", [])),
            "total_updates_found": self._check_log.get("total_updates_found", 0),
            "known_amendments": {
                k: len(v) for k, v in
                self._check_log.get("known_amendments", {}).items()
            },
            "tracked_laws": len(TRACKED_LAWS),
            "tracked_keywords": len(TRACKED_KEYWORDS),
        }

    def get_tracked_laws(self) -> List[Dict[str, str]]:
        """Lista svih praćenih zakona."""
        return [
            {"nn_slug": k, "our_slug": v}
            for k, v in TRACKED_LAWS.items()
        ]


# ═══════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════

def main():
    """CLI za NN Monitor."""
    import argparse
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Nyx Light NN Monitor")
    parser.add_argument("--check", action="store_true", help="Provjeri NN")
    parser.add_argument("--update", action="store_true", help="Update RAG")
    parser.add_argument("--status", action="store_true", help="Status")
    parser.add_argument("--days", type=int, default=14, help="Dana unazad")
    args = parser.parse_args()

    monitor = NNMonitor()

    if args.status:
        status = monitor.get_status()
        print(json.dumps(status, indent=2, ensure_ascii=False))
    elif args.update:
        result = monitor.auto_update_rag(
            callback=lambda msg: print(f"  📜 {msg}")
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        result = monitor.check_for_updates(days_back=args.days)
        print(f"Provjereno: {result.nn_issues_checked} brojeva NN")
        print(f"Relevantno: {result.relevant_found}")
        for a in result.new_amendments:
            print(f"  📋 {a.title} (NN {a.nn_number}) → {a.parent_law}")


if __name__ == "__main__":
    main()
