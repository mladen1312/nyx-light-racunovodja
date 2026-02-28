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
            r"\b(blagajn\w*|gotovina|cash|primka|izdatnica|limit.*10|"
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
    "porez_dobit": {
        "keywords": [
            r"\b(porez.*dobit|pd.*obrazac|pd-nn|porezna.*dobit|"
            r"porezna.*osnovica|nepriznati.*rashod|10%.*18%)\b"
        ],
        "sub_intents": {
            "calculate": [r"(izračun|obračun|koliko)"],
            "form": [r"(obrazac|pd|prijav)"],
        },
    },
    "porez_dohodak": {
        "keywords": [
            r"\b(porez.*dohodak|godišnj.*prijav|dohodak.*obrazac|"
            r"osobni odbitak|560|20%.*30%)\b"
        ],
        "sub_intents": {
            "calculate": [r"(izračun|obračun)"],
        },
    },
    "pdv_prijava": {
        "keywords": [
            r"\b(pdv.*prijav|pp-pdv|obrazac.*pdv|pdv.*obrazac|"
            r"pretporez|povrat.*pdv|knjiga.*ura|knjiga.*ira)\b"
        ],
        "sub_intents": {
            "generate": [r"(generiraj|kreiraj|pripremi)"],
        },
    },
    "joppd": {
        "keywords": [
            r"\b(joppd|obrazac.*joppd|joppd.*obrazac|stranica.*[ab]|"
            r"eporezna.*joppd|doprinosi.*obrazac)\b"
        ],
        "sub_intents": {
            "generate": [r"(generiraj|kreiraj|pripremi)"],
        },
    },
    "payroll": {
        "keywords": [
            r"\b(obračun.*plać|platna.*lista|isplata.*plać|bruto.*neto|"
            r"neto.*bruto|prosječna.*plaća|minimalna.*plaća)\b"
        ],
        "sub_intents": {
            "calculate": [r"(izračun|obračun|koliko)"],
        },
    },
    "bolovanje": {
        "keywords": [
            r"\b(bolovanje|bolesnički|hzzo|doznaka|privremena.*nesposobnost|"
            r"naknada.*bolovanje|refundacij|42.*dan)\b"
        ],
        "sub_intents": {
            "calculate": [r"(izračun|obračun|koliko)"],
        },
    },
    "drugi_dohodak": {
        "keywords": [
            r"\b(drugi.*dohodak|ugovor.*djel[ou]|autorsk.*honorar|"
            r"studentski.*rad|stipendij|nagrada)\b"
        ],
        "sub_intents": {
            "calculate": [r"(izračun|obračun|koliko)"],
        },
    },
    "osnovna_sredstva": {
        "keywords": [
            r"\b(osnovno.*sredstv|dugotrajan.*imovin|amortizacij|otpis|"
            r"nabavna.*vrijednost|vijek.*trajanj|inventur)\b"
        ],
        "sub_intents": {
            "calculate": [r"(izračun|koliko|stopa)"],
        },
    },
    "kompenzacije": {
        "keywords": [
            r"\b(kompenzacij|prijeboj|cesij|prebijanj|multilateral|"
            r"jednostran.*kompenz)\b"
        ],
        "sub_intents": {
            "find": [r"(pronađi|nađi|provjeri)"],
        },
    },
    "e_racun": {
        "keywords": [
            r"\b(e-račun|eračun|elektronički.*račun|ubl|cii|"
            r"zugferd|factur-x|xml.*račun)\b"
        ],
        "sub_intents": {
            "generate": [r"(generiraj|kreiraj|napravi)"],
            "validate": [r"(validiraj|provjeri)"],
        },
    },
    "peppol": {
        "keywords": [
            r"\b(peppol|as4|b2brouter|en.*16931|cius|"
            r"pristupna.*točka|access.*point)\b"
        ],
    },
    "fiskalizacija2": {
        "keywords": [
            r"\b(fiskalizacij|fisk|cis|jir|zki|qr.*kod|"
            r"naplatni.*uređaj|blagajn.*fisk)\b"
        ],
    },
    "intrastat": {
        "keywords": [
            r"\b(intrastat|eu.*robna|robn.*razmjen|dzs.*prijav|"
            r"unutar.*eu|400.*000)\b"
        ],
    },
    "gfi_xml": {
        "keywords": [
            r"\b(gfi|godišnj.*financijsk|bilanca|rdg|račun.*dobit.*gubit|"
            r"fina.*xml|gfi-pod)\b"
        ],
        "sub_intents": {
            "bilanca": [r"(bilanca|aktiv|pasiv)"],
            "rdg": [r"(rdg|prihod|rashod|dobit.*gubit)"],
        },
    },
    "reports": {
        "keywords": [
            r"\b(izvješt|izvještaj|report|bruto.*bilanc|analitičk|"
            r"rekapitulacij|pregled.*knjižen)\b"
        ],
    },
    "kpi": {
        "keywords": [
            r"\b(kpi|pokazatelj|likvidnost|solventnost|profitabilnost|"
            r"ebitda|roa|roe|tekući.*omjer)\b"
        ],
    },
    "fakturiranje": {
        "keywords": [
            r"\b(faktur|izlazni.*račun|izrada.*račun|novi.*račun|"
            r"fakturiraj|naplat|ponuda.*račun)\b"
        ],
    },
    "ledger": {
        "keywords": [
            r"\b(glavna.*knjiga|dnevnik.*knjižen|analitičk.*kartic|"
            r"temeljnica|sintetičk|protustavk)\b"
        ],
    },
    "kadrovska": {
        "keywords": [
            r"\b(kadrovsk|zaposlenik|ugovor.*rad|matičn.*podac|"
            r"godišnji.*odmor|evidencij.*rad)\b"
        ],
    },
    "deadlines": {
        "keywords": [
            r"\b(rok|rokovi|zakonsk.*rok|porezn.*rok|deadline|"
            r"prijava.*do|dostava.*do|predaj.*do)\b"
        ],
    },
    "likvidacija": {
        "keywords": [
            r"\b(likvidatur|likvidacij|kontrola.*račun|formajna.*kontrola|"
            r"stručna.*kontrola|ovjer)\b"
        ],
    },
    "accruals": {
        "keywords": [
            r"\b(pvr|avr|razgraničen|vremensko.*razgranič|"
            r"unaprijed.*plaćen|odgođen)\b"
        ],
    },
    "novcani_tokovi": {
        "keywords": [
            r"\b(novčan.*tok|cash.*flow|tijek.*novca|likvidnost.*plan|"
            r"priljev|odljev)\b"
        ],
    },
    "vision_llm": {
        "keywords": [
            r"\b(sken|skenira|ocr|prepozn.*tekst|čitaj.*sliku|"
            r"qwen.*vl|vision)\b"
        ],
        "requires_file": True,
    },
    "fiskalizacija2": {
        "keywords": [
            r"\b(fiskalizacij|fiskalni|cis|jir|zki|qr.*kod|"
            r"naplatni uređaj|blagajna.*fiskal)\b"
        ],
    },
    "eracuni_parser": {
        "keywords": [
            r"\b(eračun.*pars|e-račun.*uvoz|pantheon|eracuni|"
            r"erp.*uvoz|import.*xml.*račun)\b"
        ],
        "requires_file": True,
    },
    "universal_parser": {
        "keywords": [
            r"\b(parsiraj|pars.*datoteku|učitaj.*dokument|"
            r"prepoznaj.*format|import.*datoteku)\b"
        ],
        "requires_file": True,
    },
    "outgoing_invoice": {
        "keywords": [
            r"\b(izlazn.*račun|ira|izdan.*račun|"
            r"izlazn.*faktur|r-1.*izlaz|prodaj.*račun)\b"
        ],
    },
    "gfi_prep": {
        "keywords": [
            r"\b(gfi.*priprema|pripremi.*gfi|godišnj.*izvješć.*kontrol|"
            r"fina.*priprema)\b"
        ],
    },
    "client_management": {
        "keywords": [
            r"\b(klijent.*registar|registar.*klijenat|novi.*klijent|"
            r"erp.*postavk|klijent.*podaci)\b"
        ],
    },
    "communication": {
        "keywords": [
            r"\b(pošalji.*mail|email.*obavijest|sms.*podsjetnik|"
            r"automatsk.*poruk|šablon.*poruk)\b"
        ],
    },
    "management_accounting": {
        "keywords": [
            r"\b(upravljačk.*računovodstv|troškovno.*mjesto|centar.*odgovorn|"
            r"budžet|budget|controllin)\b"
        ],
    },
    "business_plan": {
        "keywords": [
            r"\b(poslovn.*plan|break.*even|financijsk.*projekcij|"
            r"investicijsk.*studij)\b"
        ],
    },
    "network": {
        "keywords": [
            r"\b(mreža|mrežn|mdns|tailscale|vpn|firewall|"
            r"nyx.*studio.*local)\b"
        ],
    },
    "scalability": {
        "keywords": [
            r"\b(skalabilnost|load.*balanc|performans.*server|"
            r"kapacitet|concurrent|paralelno)\b"
        ],
    },
    "audit": {
        "keywords": [
            r"\b(revizij|audit.*trail|kontroln.*točk|compliance|"
            r"trag.*promjen)\b"
        ],
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
            entities = self._extract_entities(message)
            return RouteResult(module="general", confidence=0.3, entities=entities)

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

        # Iznos (EUR) — podržava: 5000 EUR, 1.250,00 EUR, 500,00€
        iznos_match = re.search(
            r'(\d[\d.,]*\d)\s*(?:EUR|€|eur|kn|HRK)',
            message,
        )
        if not iznos_match:
            # Fallback: "iznos X" ili "za X" s brojem
            iznos_match = re.search(
                r'(?:iznos|za|od|bruto|neto)\s+(\d[\d.,]*\d)',
                message.lower(),
            )
        if iznos_match:
            raw = iznos_match.group(1)
            # HR format: 1.250,00 → 1250.00
            if "," in raw and "." in raw:
                raw = raw.replace(".", "").replace(",", ".")
            elif "," in raw:
                raw = raw.replace(",", ".")
            entities["iznos"] = raw

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
            {"id": "porez_dobit", "name": "Porez na dobit", "desc": "PD/PD-NN obrasci"},
            {"id": "porez_dohodak", "name": "Porez na dohodak", "desc": "Godišnja prijava"},
            {"id": "pdv_prijava", "name": "PDV prijava", "desc": "PP-PDV obrazac"},
            {"id": "joppd", "name": "JOPPD", "desc": "XML za ePorezna"},
            {"id": "payroll", "name": "Obračun plaća", "desc": "Bruto→neto, doprinosi"},
            {"id": "bolovanje", "name": "Bolovanje", "desc": "HZZO obrasci, naknada"},
            {"id": "drugi_dohodak", "name": "Drugi dohodak", "desc": "Ugovor o djelu, autorski"},
            {"id": "osnovna_sredstva", "name": "Osnovna sredstva", "desc": "OS evidencija, amortizacija"},
            {"id": "kompenzacije", "name": "Kompenzacije", "desc": "Jednostrane i multilateralne"},
            {"id": "e_racun", "name": "E-račun", "desc": "UBL/CII generiranje"},
            {"id": "peppol", "name": "Peppol", "desc": "AS4 protokol, EN 16931"},
            {"id": "fiskalizacija2", "name": "Fiskalizacija", "desc": "CIS, QR kodovi"},
            {"id": "intrastat", "name": "Intrastat", "desc": "DZS EU robna razmjena"},
            {"id": "gfi_xml", "name": "GFI", "desc": "XML za FINA-u"},
            {"id": "reports", "name": "Izvještaji", "desc": "Bilanca, RDG, bruto bilanca"},
            {"id": "kpi", "name": "KPI", "desc": "Financijski pokazatelji"},
            {"id": "fakturiranje", "name": "Fakturiranje", "desc": "Izlazni računi"},
            {"id": "ledger", "name": "Glavna knjiga", "desc": "Dnevnik, analitika"},
            {"id": "kadrovska", "name": "Kadrovska", "desc": "Evidencija zaposlenika"},
            {"id": "deadlines", "name": "Rokovi", "desc": "Zakonski porezni rokovi"},
            {"id": "likvidacija", "name": "Likvidatura", "desc": "Kontrola dokumenata"},
            {"id": "accruals", "name": "PVR/AVR", "desc": "Vremensko razgraničenje"},
            {"id": "novcani_tokovi", "name": "Novčani tokovi", "desc": "Cash flow izvještaj"},
            {"id": "vision_llm", "name": "Vision AI", "desc": "OCR skenova (Qwen2.5-VL)"},
            {"id": "universal_parser", "name": "Universal Parser", "desc": "Auto-detekcija formata"},
            {"id": "eracuni_parser", "name": "eRačuni Parser", "desc": "Pantheon/eRačuni XML"},
            {"id": "outgoing_invoice", "name": "Izlazni računi", "desc": "Validacija R1/R2"},
            {"id": "gfi_prep", "name": "GFI priprema", "desc": "Kontrola prije GFI XML"},
            {"id": "client_management", "name": "Klijenti", "desc": "Registar, ERP postavke"},
            {"id": "communication", "name": "Komunikacija", "desc": "Email/SMS obavijesti"},
            {"id": "management_accounting", "name": "Upravljačko RV", "desc": "Troškovna mjesta, budžet"},
            {"id": "business_plan", "name": "Poslovni plan", "desc": "Projekcije, break-even"},
            {"id": "network", "name": "Mreža", "desc": "mDNS, Tailscale, firewall"},
            {"id": "scalability", "name": "Skalabilnost", "desc": "Load balancing, resursi"},
            {"id": "audit", "name": "Revizijski trag", "desc": "Compliance, kontrolne točke"},
            {"id": "general", "name": "Općenito", "desc": "Slobodni razgovor"},
        ]

    def get_stats(self) -> Dict[str, Any]:
        return {**self._stats}
