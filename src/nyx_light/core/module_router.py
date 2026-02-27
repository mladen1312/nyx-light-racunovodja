"""
Nyx Light — Module Router

Detektira intent korisničke poruke i routira na specifični poslovni modul.
Chat endpoint koristi ovaj router za pametno delegiranje.

Intent kategorije:
  - bank_statement → BankParser
  - invoice → InvoiceOCR (Vision)
  - kontiranje → KontniEngine
  - blagajna → BlagajnaValidator
  - putni_nalog → PutniNaloziChecker
  - ios → IOSReconciliation
  - pdv → RAG (Zakon o PDV-u)
  - porez_dobit → RAG (Zakon o porezu na dobit)
  - porez_dohodak → RAG (Zakon o porezu na dohodak)
  - place → RAG (JOPPD, doprinosi)
  - amortizacija → KontniEngine + RAG
  - general → LLM generalni odgovor
"""

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("nyx_light.router")


@dataclass
class Intent:
    """Detektirani intent iz korisničke poruke."""
    category: str
    confidence: float
    keywords: List[str]
    module: str  # koji modul pozvati
    needs_llm: bool = True  # treba li LLM za odgovor
    needs_rag: bool = False  # treba li RAG pretragu
    rag_filter: str = ""  # filter za specifični zakon


# Keyword patterns za detekciju intenta
INTENT_PATTERNS = {
    "bank_statement": {
        "keywords": [
            "izvod", "bankovni", "mt940", "banka", "transakcij",
            "uplat", "isplat", "iban", "erste", "zaba", "pbz",
            "privredna", "otp", "rba", "sparivanje", "saldo",
        ],
        "module": "bank_parser",
        "needs_rag": False,
    },
    "invoice": {
        "keywords": [
            "račun", "racun", "faktur", "ulazn", "izlazn",
            "e-račun", "eracun", "dobavljač", "kupac",
            "r-1", "r-2", "ponuda", "predračun",
        ],
        "module": "invoice_ocr",
        "needs_rag": False,
    },
    "kontiranje": {
        "keywords": [
            "kontir", "konto", "knjižen", "knjizen", "proknjiz",
            "duguje", "potražuje", "potrazuje", "strana", "razred",
            "4010", "2200", "1200", "3100", "7",
        ],
        "module": "kontiranje",
        "needs_rag": False,
    },
    "blagajna": {
        "keywords": [
            "blagajn", "gotovina", "blagajnički", "primka",
            "izdatn", "limit", "10.000", "10000", "cash",
            "gotovinski", "isplata gotov",
        ],
        "module": "blagajna",
        "needs_rag": False,
    },
    "putni_nalog": {
        "keywords": [
            "putni", "nalog", "dnevnic", "kilometar", "km",
            "0,30", "0,40", "službeni put", "prijevoz",
            "loko vožn", "cestarin",
        ],
        "module": "putni_nalozi",
        "needs_rag": False,
    },
    "ios": {
        "keywords": [
            "ios", "izvod otvorenih", "usklađen", "uskladen",
            "otvorene stavke", "kompenzacij", "prijeboj",
        ],
        "module": "ios",
        "needs_rag": False,
    },
    "pdv": {
        "keywords": [
            "pdv", "porez na dodanu", "pretporez", "odbitak",
            "stopa pdv", "25%", "13%", "5%", "oslobođen",
            "pdv prijav", "obračun pdv", "pdv obrazac",
            "intrastats", "eu isporuk",
        ],
        "module": "rag",
        "needs_rag": True,
        "rag_filter": "PDV",
    },
    "porez_dobit": {
        "keywords": [
            "porez na dobit", "dobit", "pd obrazac", "prijava poreza na dobit",
            "porezna osnovica", "porezno nepriznat", "reprezentacij",
            "amortizacij", "transfer", "10%", "18%",
        ],
        "module": "rag",
        "needs_rag": True,
        "rag_filter": "dobit",
    },
    "porez_dohodak": {
        "keywords": [
            "dohodak", "porez na dohodak", "osobni odbitak",
            "20%", "30%", "prirez", "godišnj",
            "neoporeziv", "joppd",
        ],
        "module": "rag",
        "needs_rag": True,
        "rag_filter": "dohodak",
    },
    "place": {
        "keywords": [
            "plaća", "placa", "plaće", "obračun plaće", "neto",
            "bruto", "doprinosi", "mio", "zdravstven",
            "joppd", "regres", "božićnic", "isplata plaće",
            "bolovanje", "porodiljn", "godišnji odmor",
        ],
        "module": "rag",
        "needs_rag": True,
        "rag_filter": "doprinosi",
    },
    "amortizacija": {
        "keywords": [
            "amortizacij", "osnovno sredstvo", "osnovna sredstv",
            "dugotrajna imovina", "otpis", "stopa amortizacij",
            "vijek trajanja", "nabavna vrijednost",
        ],
        "module": "kontiranje",
        "needs_rag": True,
        "rag_filter": "amortizacija",
    },
    "fiskalizacija": {
        "keywords": [
            "fiskalizacij", "jir", "zki", "blagajn", "fiskaln",
            "promet gotvoin", "cis",
        ],
        "module": "rag",
        "needs_rag": True,
        "rag_filter": "fiskalizacija",
    },
    "rok_placanja": {
        "keywords": [
            "rok plaćanja", "dospijeće", "zatezn", "kamat",
            "opomena", "ovrha", "blokada", "fina",
        ],
        "module": "rag",
        "needs_rag": True,
        "rag_filter": "financijsko poslovanje",
    },
    "aml": {
        "keywords": [
            "pranje novca", "aml", "sumnjiv", "uunp",
            "dubinska analiz", "kyc",
        ],
        "module": "rag",
        "needs_rag": True,
        "rag_filter": "pranje novca",
    },
    "trgovacko_drustvo": {
        "keywords": [
            "d.o.o", "d.d.", "temeljni kapital", "osnivanj",
            "skupštin", "uprava društva",
        ],
        "module": "rag",
        "needs_rag": True,
        "rag_filter": "trgovačkim društvima",
    },
}


class ModuleRouter:
    """
    Routira korisničke upite na odgovarajuće module.

    Koristi keyword-based intent detection s fuzzy matchingom.
    """

    def __init__(self):
        self._intent_cache: Dict[str, Intent] = {}
        self._stats = {"routed": 0, "by_category": {}}

    def detect_intent(self, message: str) -> Intent:
        """Detektiraj intent iz korisničke poruke."""
        msg_lower = message.lower()

        # Score each category
        scores: List[Tuple[str, float, List[str]]] = []

        for category, config in INTENT_PATTERNS.items():
            matched_kw = []
            for kw in config["keywords"]:
                if kw.lower() in msg_lower:
                    matched_kw.append(kw)

            if matched_kw:
                # Score: number of matches * weight
                score = len(matched_kw) / len(config["keywords"])
                # Bonus for exact matches
                score += 0.1 * len(matched_kw)
                scores.append((category, score, matched_kw))

        if not scores:
            return Intent(
                category="general",
                confidence=0.5,
                keywords=[],
                module="llm",
                needs_llm=True,
                needs_rag=False,
            )

        # Best match
        scores.sort(key=lambda x: x[1], reverse=True)
        best_cat, best_score, best_kw = scores[0]
        config = INTENT_PATTERNS[best_cat]

        confidence = min(1.0, best_score)
        intent = Intent(
            category=best_cat,
            confidence=confidence,
            keywords=best_kw,
            module=config["module"],
            needs_llm=True,
            needs_rag=config.get("needs_rag", False),
            rag_filter=config.get("rag_filter", ""),
        )

        self._stats["routed"] += 1
        self._stats["by_category"][best_cat] = self._stats["by_category"].get(best_cat, 0) + 1

        logger.debug("Intent: %s (conf=%.2f, kw=%s)", best_cat, confidence, best_kw)
        return intent

    def get_module_context(self, intent: Intent, **kwargs) -> Dict[str, Any]:
        """
        Dohvati kontekst iz modula za obogaćivanje LLM prompta.

        Ovo se poziva PRIJE slanja upita LLM-u, kako bi LLM imao
        kontekst specifičan za modul.
        """
        context = {
            "intent": intent.category,
            "module": intent.module,
            "confidence": intent.confidence,
        }

        if intent.module == "bank_parser":
            context["system_hint"] = (
                "Korisnik pita o bankovnim izvodima. Možeš pomoći s: "
                "parsiranjem MT940/CSV izvoda, sparivanjem transakcija, "
                "prepoznavanjem platitelja po IBAN-u ili pozivu na broj."
            )

        elif intent.module == "invoice_ocr":
            context["system_hint"] = (
                "Korisnik pita o računima. Možeš pomoći s: "
                "čitanjem skenova (OCR), ekstrakcijom OIB/iznos/PDV, "
                "triažom prema klijentu, validacijom e-računa."
            )

        elif intent.module == "kontiranje":
            context["system_hint"] = (
                "Korisnik pita o kontiranju. Koristi kontni plan RH: "
                "razred 0=dugotrajna imovina, 1=kratkotrajna, 2=obveze, "
                "3=kapital, 4=troškovi, 5=rashodi, 6=proizvodnja, "
                "7=prihodi, 8=izvanredni, 9=obračun."
            )
            # Add kontni plan search if query provided
            if "query" in kwargs:
                context["kontni_plan_search"] = kwargs["query"]

        elif intent.module == "blagajna":
            context["system_hint"] = (
                "Korisnik pita o blagajni. Ključna pravila: "
                "limit gotovine 10.000 EUR, blagajnički primci/izdatci, "
                "obveza fiskalizacije prometa gotovinom."
            )

        elif intent.module == "putni_nalozi":
            context["system_hint"] = (
                "Korisnik pita o putnim nalozima. Ključno: "
                "dnevnica RH 26,54 EUR (12-24h), "
                "naknada za km 0,40 EUR/km, "
                "provjera porezno nepriznatih troškova."
            )

        elif intent.module == "ios":
            context["system_hint"] = (
                "Korisnik pita o IOS usklađivanjima. "
                "IOS = Izvod Otvorenih Stavki. "
                "Proces: generira se Excel, šalje partneru, "
                "partner potvrdi ili ospori, mapiraju se razlike."
            )

        elif intent.needs_rag:
            context["system_hint"] = (
                f"Korisnik pita o pravnom pitanju ({intent.rag_filter}). "
                "Koristi RAG za pretragu relevantnog zakona. "
                "Citiraj članak i NN broj u odgovoru."
            )
            context["rag_query"] = kwargs.get("message", "")
            context["rag_filter"] = intent.rag_filter

        return context

    def get_stats(self) -> Dict[str, Any]:
        return {**self._stats}
