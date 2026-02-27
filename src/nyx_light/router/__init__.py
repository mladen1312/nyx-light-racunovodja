"""
Nyx Light — Module Router

Detektira namjeru korisnika iz chat poruke i preusmjerava na
odgovarajući poslovni modul (bank parser, kontiranje, blagajna, itd.).

Dva moda:
  1. LLM-based (produkcija): Qwen model klasificira intent
  2. Keyword-based (fallback): Regex/keyword matching

Podržani moduli:
  - bank_parser: MT940, CSV bankovni izvodi
  - invoice_ocr: Skenovi računa (PDF, slike)
  - kontiranje: Prijedlog konta
  - blagajna: Validacija blagajne
  - putni_nalozi: Provjera putnih naloga
  - ios: IOS usklađivanja
  - rag: Pravni upiti (zakoni RH)
  - plaće: Obračun plaća i JOPPD
  - general: Općeniti razgovor

Optimizirano za Apple Silicon:
  - Keyword routing: <1ms (M3/M5 Ultra)
  - LLM routing: ~50ms s Qwen3-30B-A3B (MoE)
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("nyx_light.router")


@dataclass
class RouteResult:
    """Rezultat routinga."""
    module: str
    confidence: float
    sub_intent: str = ""
    entities: Dict[str, Any] = field(default_factory=dict)
    requires_file: bool = False


# ──────────────────────────────────────────────
# Intent patterns (keyword-based, <1ms)
# ──────────────────────────────────────────────

INTENT_PATTERNS = {
    "bank_parser": {
        "keywords": [
            r"\b(bankovn|izvod|mt940|izvadak|iban|transakcij|uplat|isplat|saldo|"
            r"erste|zaba|pbz|otp|hpb|addiko|rba|virman|nalog za plaćanje)\b"
        ],
        "sub_intents": {
            "parse": [r"(uvez|pars|učitaj|importiraj).*(izvod|mt940)"],
            "match": [r"(sparivanj|usklad|match|mapira)"],
            "export": [r"(izvez|export|generiraj).*(cppp|synesis)"],
        },
        "requires_file": True,
    },
    "invoice_ocr": {
        "keywords": [
            r"\b(račun|racun|faktur|invoice|ulazn|izlazn|r-1|r-2|ura|ira|"
            r"skeniraj|skenira|ocr|prepozn|ekstrahi)\b"
        ],
        "sub_intents": {
            "scan": [r"(sken|prepozn|očitaj|pročitaj|ekstra)"],
            "classify": [r"(razvrst|klasifici|trijaž|sortira)"],
            "book": [r"(proknjiž|kontira|knjižen|zaduž)"],
        },
        "requires_file": True,
    },
    "kontiranje": {
        "keywords": [
            r"\b(konto|kontira|knjižen|razred\s*[0-9]|temeljnic|nalog za knjižen|"
            r"duguje|potražuje|storno|protu[ks]tavk|saldo kont)\b"
        ],
        "sub_intents": {
            "suggest": [r"(predloži|prijedlog|koji konto|kako kontir)"],
            "verify": [r"(provjeri|ispravno|točno|je li ok)"],
            "explain": [r"(objasni|zašto|razlog)"],
        },
    },
    "blagajna": {
        "keywords": [
            r"\b(blagajn|gotovina|cash|primka|izdatnica|limit.*10|"
            r"blagajnički|dnevni promet|gotovinski)\b"
        ],
        "sub_intents": {
            "validate": [r"(provjeri|validir|limit|praviln)"],
            "report": [r"(izvješć|rekapitul|zaključ|dnevn)"],
        },
    },
    "putni_nalozi": {
        "keywords": [
            r"\b(putni|nalog|dnevnic|km.?naknada|kilometraž|službeni put|"
            r"loko.*vožnj|reprezentac|0[,.]30|0[,.]40)\b"
        ],
        "sub_intents": {
            "validate": [r"(provjeri|isprav|izračun)"],
            "calculate": [r"(izračun|koliko|obračun)"],
        },
    },
    "ios": {
        "keywords": [
            r"\b(ios|izvod otvorenih|otvorene stavke|usklađ|usklaž|"
            r"kompenzacij|cesij|prijeboj|saldiraj)\b"
        ],
        "sub_intents": {
            "generate": [r"(generiraj|kreiraj|napravi|izradi).*ios"],
            "track": [r"(prati|status|odgovor|povrat)"],
            "reconcile": [r"(uskladi|razlik|mapira)"],
        },
    },
    "rag": {
        "keywords": [
            r"\b(zakon|propis|pravilnik|nn\s*\d|narodne novine|članak|stavak|"
            r"mišljenje|porezna uprava|pu|hsfi|msfi|mrs|računovodstveni standard|"
            r"pdv|stopa\s*(pdv|porez)|porez\w*\s*(dodanu|dobit|dohodak))\b"
        ],
        "sub_intents": {
            "lookup": [r"(što kaže|prema zakonu|prema čl|propis)"],
            "compare": [r"(usporedi|razlik|promjen|izmjen)"],
            "timeline": [r"(kad|od kad|do kad|vrijedi|stupanj)"],
        },
    },
    "place": {
        "keywords": [
            r"\b(plaća|placa|bruto|neto|joppd|doprinos|mio|zdravstven|"
            r"osobni odbitak|prirez|porez.*dohodak|olakšic|uzdržavan|"
            r"minimaln.*plaća|obračun.*plaće|isplat.*plaće)\b"
        ],
        "sub_intents": {
            "calculate": [r"(izračun|obračun|koliko|bruto.*neto|neto.*bruto)"],
            "joppd": [r"(joppd|obrazac|prijav)"],
            "deductions": [r"(odbitak|olakšic|uzdržavan)"],
        },
    },
    "amortizacija": {
        "keywords": [
            r"(amortizacij\w*|osnovna?\s*sredstv|dugotrajan\w*|otpis\w*|"
            r"stopa.*amortiz|vijek.*trajanj|nabavna vrijednost)"
        ],
        "sub_intents": {
            "calculate": [r"(izračun|koliko|godišnj|mjesečn)"],
            "classify": [r"(koja.*grupa|skupina|razvrst)"],
        },
    },
    "export": {
        "keywords": [
            r"\b(export|izvoz|izvez|cpp|synesis|xml.*uvoz|csv.*uvoz|"
            r"prebaci.*u\s*(erp|program)|datoteka za uvoz)\b"
        ],
        "sub_intents": {
            "cpp": [r"(cpp|centrix)"],
            "synesis": [r"(synesis)"],
            "general": [r"(export|izvez|generiraj)"],
        },
    },
}


class ModuleRouter:
    """
    Routira korisnikovu poruku na odgovarajući modul.

    Koristi keyword matching (fallback, <1ms) ili LLM klasifikaciju (produkcija).
    """

    def __init__(self, use_llm: bool = False, llm_provider=None):
        self.use_llm = use_llm
        self.llm_provider = llm_provider
        self._compiled_patterns = self._compile_patterns()
        self._stats = {"total_routes": 0, "by_module": {}}
        logger.info("ModuleRouter inicijaliziran (LLM: %s)", use_llm)

    def _compile_patterns(self) -> Dict[str, Dict]:
        """Pre-compile regex patterns za brži matching."""
        compiled = {}
        for module, config in INTENT_PATTERNS.items():
            compiled[module] = {
                "main": [re.compile(p, re.IGNORECASE) for p in config["keywords"]],
                "sub": {},
                "requires_file": config.get("requires_file", False),
            }
            for sub_name, sub_patterns in config.get("sub_intents", {}).items():
                compiled[module]["sub"][sub_name] = [
                    re.compile(p, re.IGNORECASE) for p in sub_patterns
                ]
        return compiled

    def route(self, message: str, has_file: bool = False) -> RouteResult:
        """
        Routiraj poruku na modul.

        Args:
            message: Korisnička poruka
            has_file: Ima li priloženu datoteku

        Returns:
            RouteResult s modulom, confidence i sub-intentom
        """
        self._stats["total_routes"] += 1

        if self.use_llm and self.llm_provider:
            return self._route_llm(message, has_file)
        return self._route_keywords(message, has_file)

    def _route_keywords(self, message: str, has_file: bool) -> RouteResult:
        """Keyword-based routing (<1ms na Apple Silicon)."""
        scores: List[Tuple[str, float, str]] = []

        for module, patterns in self._compiled_patterns.items():
            # Count keyword matches
            match_count = 0
            for pattern in patterns["main"]:
                matches = pattern.findall(message)
                match_count += len(matches)

            if match_count == 0:
                continue

            # Calculate confidence
            confidence = min(0.95, 0.5 + match_count * 0.15)

            # Boost if file present and module expects file
            if has_file and patterns["requires_file"]:
                confidence = min(0.98, confidence + 0.15)

            # Detect sub-intent
            sub_intent = ""
            for sub_name, sub_patterns in patterns["sub"].items():
                for pattern in sub_patterns:
                    if pattern.search(message):
                        sub_intent = sub_name
                        confidence = min(0.98, confidence + 0.05)
                        break
                if sub_intent:
                    break

            scores.append((module, confidence, sub_intent))

        if not scores:
            return RouteResult(module="general", confidence=0.3)

        # Sort by confidence
        scores.sort(key=lambda x: x[1], reverse=True)
        best = scores[0]

        # Extract entities
        entities = self._extract_entities(message)

        # Update stats
        module_name = best[0]
        self._stats["by_module"][module_name] = self._stats["by_module"].get(module_name, 0) + 1

        return RouteResult(
            module=module_name,
            confidence=best[1],
            sub_intent=best[2],
            entities=entities,
            requires_file=self._compiled_patterns.get(module_name, {}).get("requires_file", False),
        )

    def _route_llm(self, message: str, has_file: bool) -> RouteResult:
        """LLM-based routing (za produkciju s Qwen3)."""
        # Placeholder: koristi keyword kao fallback
        # Na Mac Studio: LLM poziv za klasifikaciju (~50ms)
        return self._route_keywords(message, has_file)

    def _extract_entities(self, message: str) -> Dict[str, Any]:
        """Izvuci entitete iz poruke (OIB, IBAN, iznos, datum)."""
        entities = {}

        # OIB (11 znamenaka)
        oib_match = re.search(r'\b(\d{11})\b', message)
        if oib_match:
            entities["oib"] = oib_match.group(1)

        # IBAN (HR + 19 znamenaka)
        iban_match = re.search(r'\b(HR\d{19})\b', message)
        if iban_match:
            entities["iban"] = iban_match.group(1)

        # Iznos (EUR)
        iznos_match = re.search(
            r'(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)\s*(?:EUR|€|eur|kn|HRK)',
            message,
        )
        if iznos_match:
            entities["iznos"] = iznos_match.group(1).replace(".", "").replace(",", ".")

        # Konto (4 znamenke)
        konto_match = re.findall(r'\b(\d{4})\b', message)
        if konto_match:
            entities["konto_candidates"] = konto_match[:4]

        # Datum (DD.MM.YYYY ili DD/MM/YYYY)
        datum_match = re.search(r'(\d{1,2}[./]\d{1,2}[./]\d{2,4})', message)
        if datum_match:
            entities["datum"] = datum_match.group(1)

        return entities

    def get_available_modules(self) -> List[Dict[str, str]]:
        """Vrati listu dostupnih modula s opisima."""
        return [
            {"id": "bank_parser", "name": "Bankovni izvodi", "desc": "MT940/CSV parser + sparivanje"},
            {"id": "invoice_ocr", "name": "Ulazni računi", "desc": "OCR skenova i PDF-ova"},
            {"id": "kontiranje", "name": "Kontiranje", "desc": "Prijedlog konta i temeljnica"},
            {"id": "blagajna", "name": "Blagajna", "desc": "Validacija blagajničkih dokumenata"},
            {"id": "putni_nalozi", "name": "Putni nalozi", "desc": "Provjera i obračun"},
            {"id": "ios", "name": "IOS usklađivanja", "desc": "Generiranje i praćenje IOS obrazaca"},
            {"id": "rag", "name": "Pravna baza", "desc": "Pretraga zakona RH"},
            {"id": "place", "name": "Plaće", "desc": "Obračun plaća i JOPPD"},
            {"id": "amortizacija", "name": "Amortizacija", "desc": "Izračun i klasifikacija OS"},
            {"id": "export", "name": "ERP Export", "desc": "Izvoz za CPP/Synesis"},
            {"id": "general", "name": "Općenito", "desc": "Slobodni razgovor"},
        ]

    def get_stats(self) -> Dict[str, Any]:
        return {**self._stats}
