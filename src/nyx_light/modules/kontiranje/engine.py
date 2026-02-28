"""
Nyx Light — Modul A3: Kontiranje Engine (Ekspertni sustav)

Prioriteti:
  1. L2 Semantička memorija — prethodni obrasci za tog dobavljača
  2. Rule Engine — 65+ pravila iz RH računovodstvene prakse
  3. Supplier pattern matching — poznati dobavljači (HEP, A1, INA...)
  4. Keyword fallback
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("nyx_light.modules.kontiranje")


@dataclass
class KontiranjePrijedlog:
    duguje_konto: str = ""
    duguje_naziv: str = ""
    potrazuje_konto: str = ""
    potrazuje_naziv: str = ""
    iznos: float = 0.0
    pdv_konto: str = ""
    pdv_iznos: float = 0.0
    confidence: float = 0.0
    source: str = ""
    rule_id: str = ""
    requires_approval: bool = True
    alternativni: List[Dict] = field(default_factory=list)
    napomena: str = ""

    # Dict-style access for backward compatibility
    def __getitem__(self, key):
        if key == "suggested_konto":
            return self.duguje_konto
        return getattr(self, key)

    def __contains__(self, key):
        if key == "suggested_konto":
            return True
        return hasattr(self, key)

    def get(self, key, default=None):
        """Dict-style .get() for backward compatibility."""
        try:
            return self[key]
        except (AttributeError, KeyError):
            return default

    def __iter__(self):
        """Iterate over field names for 'for key in result' checks.
        Financial fields (iznos, pdv_iznos) are internal only — not exposed."""
        _HIDDEN = {"iznos", "pdv_iznos"}
        for f in self.__dataclass_fields__:
            if f not in _HIDDEN:
                yield f
        yield "suggested_konto"

    @property
    def suggested_konto(self):
        return self.duguje_konto


def _load_kontni_plan() -> Dict[str, str]:
    try:
        from nyx_light.modules.kontiranje.kontni_plan import (
            RAZRED_0, RAZRED_1, RAZRED_2, RAZRED_3, RAZRED_4,
            RAZRED_5, RAZRED_6, RAZRED_7, RAZRED_8, RAZRED_9,
        )
        plan = {}
        for r in [RAZRED_0, RAZRED_1, RAZRED_2, RAZRED_3, RAZRED_4,
                  RAZRED_5, RAZRED_6, RAZRED_7, RAZRED_8, RAZRED_9]:
            plan.update(r)
        return plan
    except ImportError:
        return {}


KONTNI_PLAN = _load_kontni_plan()

def konto_naziv(konto: str) -> str:
    return KONTNI_PLAN.get(konto, f"Konto {konto}")


PDV_KONTA = {
    25: {"pretporez": "1230", "obveza": "2400"},
    13: {"pretporez": "1231", "obveza": "2401"},
    5:  {"pretporez": "1232", "obveza": "2402"},
    0:  {"pretporez": "", "obveza": ""},
}

# (id, tip_pattern, opis_regex, duguje, potrazuje, pdv_konto, confidence, napomena)
_RAW_RULES = [
    ("UR-MAT-01", "ulazni", r"materijal|sirovine|repromaterijal", "4009", "2200", "1230", 0.85, "Nabava materijala"),
    ("UR-MAT-02", "ulazni", r"uredski materijal|toneri?|papir|olovk", "4091", "2200", "1230", 0.85, "Uredski materijal"),
    ("UR-USL-01", "ulazni", r"uslug[ae]|servis|odrzavanj|konzultan", "4120", "2200", "1230", 0.80, "Usluge"),
    ("UR-USL-02", "ulazni", r"knjigovodstv|racunovodstv|revizij", "4121", "2200", "1230", 0.90, "Raunovodstvo"),
    ("UR-USL-03", "ulazni", r"odvjetni|javni bilj|pravn", "4122", "2200", "1230", 0.85, "Pravne usluge"),
    ("UR-USL-04", "ulazni", r"oglasavanj|marketing|reklam|promoci", "4123", "2200", "1230", 0.80, "Marketing"),
    ("UR-USL-05", "ulazni", r"ciscenj|cleaning|higijena", "4124", "2200", "1230", 0.85, "Ciscenje"),
    ("UR-USL-06", "ulazni", r"zastit.*rad|HTZ|zastitna oprema", "4125", "2200", "1230", 0.85, "ZNR"),
    ("UR-ENE-01", "ulazni", r"struj|elektri|HEP|energi", "4030", "2200", "1230", 0.90, "Elektricna energija"),
    ("UR-ENE-02", "ulazni", r"plin|gas|energopl|toplana", "4031", "2200", "1230", 0.90, "Plin"),
    ("UR-ENE-03", "ulazni", r"vod[ae]|vodovod|kanalizacij|komunaln", "4032", "2200", "1230", 0.90, "Voda/komunalije"),
    ("UR-TEL-01", "ulazni", r"telefon|mobitel|A1|T-?[Cc]om|Telemach|Tele2", "4040", "2200", "1230", 0.90, "Telekom"),
    ("UR-TEL-02", "ulazni", r"internet|hosting|domena|cloud|server|SaaS", "4041", "2200", "1230", 0.85, "IT usluge"),
    ("UR-NAJ-01", "ulazni", r"najam|zakup|rent[ae]", "4130", "2200", "1230", 0.85, "Najam"),
    ("UR-NAJ-02", "ulazni", r"leasing.*auto|operativ.*leasing.*vozil", "4131", "2200", "1230", 0.85, "Leasing vozila"),
    ("UR-OSI-01", "ulazni", r"osiguran|polic|premij", "4140", "2200", "", 0.85, "Osiguranje (bez PDV)"),
    ("UR-GOR-01", "ulazni", r"goriv|benzin|dizel|INA|Petrol|MOL|OMV|Lukoil|Tifon", "4070", "2200", "1230", 0.90, "Gorivo"),
    ("UR-REP-01", "ulazni", r"reprezentacij|restoran|hotel|rucak|vecer|catering", "4094", "2200", "1230", 0.80, "Reprezentacija 30% nepriznato"),
    ("UR-EDU-01", "ulazni", r"edukacij|seminar|tecaj|konferencij", "4095", "2200", "1230", 0.85, "Edukacija"),
    ("UR-STR-01", "ulazni", r"strucn.*literatur|casopis|pretplat|knjig", "4096", "2200", "1230", 0.80, "Strucna literatura"),
    ("UR-POS-01", "ulazni", r"post[ae]|postarin|kurir|dostav|HP|GLS|DPD", "4050", "2200", "", 0.85, "Posta"),
    ("UR-BAN-01", "ulazni", r"bankov|provizij|naknad.*bank|SWIFT|platni promet", "4160", "2200", "", 0.90, "Bankarske naknade"),
    ("UR-PUT-01", "ulazni", r"putovanj|avion|smjestaj|hotel|Booking", "4093", "2200", "1230", 0.80, "Putni troskovi"),
    ("UR-AMO-01", "ulazni", r"nabav.*oprem|racunalo|laptop|monitor|printer", "0220", "2200", "1230", 0.80, "Nabava opreme OS"),
    ("UR-AMO-02", "ulazni", r"nabav.*namjestaj|stol|stolica|ormar", "0230", "2200", "1230", 0.80, "Nabava inventara OS"),
    ("UR-AMO-03", "ulazni", r"nabav.*vozil|auto|kombi", "0240", "2200", "1230", 0.80, "Nabava vozila OS"),
    ("UR-AMO-04", "ulazni", r"nabav.*softver|licen|program", "0120", "2200", "1230", 0.80, "Nabava softvera NI"),
    ("UR-SIT-01", "ulazni", r"sitan inventar|sitni|alat|pribor", "4092", "2200", "1230", 0.80, "Sitan inventar"),
    ("IR-ROB-01", "izlazni", r"prodaj.*rob|roba|maloprodaj", "1200", "7500", "2400", 0.85, "Prodaja robe"),
    ("IR-USL-01", "izlazni", r"uslug|izvrs|obavlj|isporuk.*uslug", "1200", "7510", "2400", 0.85, "Prihod usluge"),
    ("IR-PRO-01", "izlazni", r"prodaj.*proizvod|gotov.*proizvod", "1200", "7500", "2400", 0.80, "Prodaja proizvoda"),
    ("IR-NAJ-01", "izlazni", r"najam|zakupnin", "1200", "7800", "2400", 0.80, "Prihod najam"),
    ("BK-UPL-01", "banka_uplata", r"uplat.*kupac|naplat|po racunu", "1500", "1200", "", 0.90, "Uplata kupca"),
    ("BK-ISP-01", "banka_isplata", r"isplat.*dobavljac|placanj|po racunu", "2200", "1500", "", 0.90, "Placanje dobavljacu"),
    ("BK-PLA-01", "banka_isplata", r"plac[ae]|neto.*plac|obracun.*plac|JOPPD", "4500", "1500", "", 0.90, "Isplata placa"),
    ("BK-MIO-01", "banka_isplata", r"MIO|HZMO|mirovinsk|doprinos.*MIO", "4510", "1500", "", 0.90, "Doprinosi MIO"),
    ("BK-ZDR-01", "banka_isplata", r"HZZO|zdravstven|doprinos.*zdravstv", "4520", "1500", "", 0.90, "Doprinosi HZZO"),
    ("BK-POR-01", "banka_isplata", r"porez.*dohodak|JOPPD.*porez", "4530", "1500", "", 0.90, "Porez na dohodak"),
    ("BK-PDV-01", "banka_isplata", r"PDV|porez.*dodanu.*vrijednost", "2400", "1500", "", 0.90, "Uplata PDV"),
    ("BK-NAJ-01", "banka_isplata", r"najam|zakup|renta", "4130", "1500", "", 0.80, "Placanje najma"),
    ("PL-BRT-01", "placa", r"bruto.*plac|obracun.*plac", "4500", "2300", "", 0.90, "Obracun bruto place"),
    ("PL-MIO1",   "placa", r"MIO.*stup.*1|MIO.*I(?!I)", "4500", "2310", "", 0.90, "MIO I"),
    ("PL-MIO2",   "placa", r"MIO.*stup.*2|MIO.*II", "4500", "2320", "", 0.90, "MIO II"),
    ("PL-POR-01", "placa", r"porez.*dohodak", "4500", "2330", "", 0.90, "Porez dohodak"),
    ("PL-NET-01", "placa", r"neto.*plac|isplat.*neto", "2300", "1500", "", 0.90, "Isplata neto"),
    ("PL-ZDR-01", "placa", r"zdravstven.*doprinos|doprinos.*na.*plac", "4521", "2340", "", 0.90, "Zdravstveno na placu"),
    ("AM-NEM-01", "amortizacija", r"amort.*nematerijal|amort.*softver", "4300", "0190", "", 0.95, "Amortizacija NI"),
    ("AM-OPR-01", "amortizacija", r"amort.*oprem|amort.*stroj", "4302", "0292", "", 0.95, "Amortizacija opreme"),
    ("AM-VOZ-01", "amortizacija", r"amort.*vozil|amort.*auto", "4303", "0293", "", 0.95, "Amortizacija vozila"),
    ("AM-INV-01", "amortizacija", r"amort.*inventar|amort.*uredski", "4304", "0294", "", 0.95, "Amortizacija inventara"),
    ("OS-TEC-01", "", r"tecajn.*razlik|valut|devizn.*razlik", "4180", "7810", "", 0.80, "Tecajne razlike"),
    ("OS-OTP-01", "", r"otpis.*potrazivan|nenaplativ", "4320", "1209", "", 0.80, "Otpis potrazivanja"),
    ("OS-KAM-01", "", r"kamat|zakasnin|zatezn", "4170", "2200", "", 0.80, "Kamate"),
    ("OS-CAR-01", "", r"carin|spedicij|uvozn", "4060", "2200", "1230", 0.80, "Carine i spedicija"),
]

_COMPILED_RULES = []
for r in _RAW_RULES:
    try:
        _COMPILED_RULES.append((r[0], r[1], re.compile(r[2], re.IGNORECASE), *r[3:]))
    except re.error:
        pass

# Supplier patterns
_SUPPLIER_MAP = [
    (["a1 ", "t-com", "ht ", "telemach", "tele2", "iskon"], "4040", "Telekom"),
    (["hep", "hera", "elektra"], "4030", "Elektricna energija"),
    (["gradska plinara", "energo"], "4031", "Plin"),
    (["vodovod", "komunalac", "cistoća", "cistoca"], "4032", "Komunalije"),
    (["ina ", "petrol", "mol ", "omv", "lukoil", "tifon", "crodux"], "4070", "Gorivo"),
    (["hp-", "hrvatska posta", "gls", "dpd", "overseas"], "4050", "Posta"),
]


class KontiranjeEngine:
    def __init__(self, memory=None):
        self.memory = memory
        self._call_count = 0
        self._memory_hits = 0
        self._rule_hits = 0
        self._pattern_hits = 0
        self._fallback_hits = 0

    def suggest_konto(self, description: str, tip_dokumenta: str = "",
                      client_id: str = "", supplier_oib: str = "",
                      supplier_name: str = "", iznos: float = 0.0,
                      pdv_stopa: float = 25.0, memory_hint: Dict = None,
                      ) -> KontiranjePrijedlog:
        self._call_count += 1
        combined = f"{description} {supplier_name}".strip()

        # 1. L2 Semanticka memorija
        if memory_hint and memory_hint.get("hint"):
            self._memory_hits += 1
            pdv_info = PDV_KONTA.get(int(pdv_stopa), PDV_KONTA[25])
            pdv_k = pdv_info["pretporez"] if tip_dokumenta == "ulazni" else pdv_info.get("obveza", "")
            return KontiranjePrijedlog(
                duguje_konto=memory_hint.get("duguje", memory_hint["hint"]),
                duguje_naziv=konto_naziv(memory_hint.get("duguje", memory_hint["hint"])),
                potrazuje_konto=memory_hint.get("potrazuje", ""),
                potrazuje_naziv=konto_naziv(memory_hint.get("potrazuje", "")),
                iznos=iznos, pdv_konto=pdv_k,
                pdv_iznos=round(iznos * pdv_stopa / (100 + pdv_stopa), 2) if pdv_stopa else 0,
                confidence=min(memory_hint.get("confidence", 0.8), 0.95),
                source="L2_semantic_memory",
                napomena=f"Temeljem {memory_hint.get('count', 0)} prethodnih knjizenja",
            )

        # 2. Supplier pattern (prioritize when supplier_name explicitly provided)
        if supplier_name:
            sm = self._match_supplier(supplier_name)
            if sm:
                self._pattern_hits += 1
                return sm

        # 3. Rule Engine
        best = self._match_rules(combined, tip_dokumenta)
        if best:
            self._rule_hits += 1
            rule_id, _, _, duguje, potrazuje, pdv_k, conf, napomena = best
            pdv_info = PDV_KONTA.get(int(pdv_stopa), PDV_KONTA[25])
            actual_pdv = pdv_info["pretporez"] if pdv_k == "1230" else pdv_info.get("obveza","") if pdv_k == "2400" else pdv_k
            p = KontiranjePrijedlog(
                duguje_konto=duguje, duguje_naziv=konto_naziv(duguje),
                potrazuje_konto=potrazuje, potrazuje_naziv=konto_naziv(potrazuje),
                iznos=iznos, pdv_konto=actual_pdv,
                pdv_iznos=round(iznos * pdv_stopa / (100 + pdv_stopa), 2) if pdv_stopa else 0,
                confidence=conf, source="rule_engine", rule_id=rule_id, napomena=napomena,
            )
            if "reprezentacij" in combined.lower():
                p.napomena += " | 30% PDV nepriznato (cl.20 ZoPDV)"
            alt = self._match_rules(combined, tip_dokumenta, exclude=rule_id)
            if alt:
                p.alternativni.append({"duguje": alt[3], "potrazuje": alt[4], "conf": alt[6], "rule": alt[0]})
            return p

        # 4. Supplier pattern fallback (if not already checked)
        if not supplier_name:
            sm = self._match_supplier(supplier_name)
            if sm:
                self._pattern_hits += 1
                return sm

        # 5. Fallback
        self._fallback_hits += 1
        return self._keyword_fallback(combined, tip_dokumenta, iznos, pdv_stopa)

    def suggest_batch(self, stavke: List[Dict], client_id: str = "") -> List[KontiranjePrijedlog]:
        return [self.suggest_konto(
            description=s.get("opis", ""), tip_dokumenta=s.get("tip", ""),
            client_id=client_id, supplier_name=s.get("naziv", ""),
            iznos=s.get("iznos", 0), pdv_stopa=s.get("pdv_stopa", 25),
            memory_hint=s.get("memory_hint"),
        ) for s in stavke]

    def _match_rules(self, text, tip, exclude=""):
        best, best_c = None, 0
        for rule in _COMPILED_RULES:
            rid, rtip, pat, *rest = rule
            if rid == exclude: continue
            if rtip and tip and rtip != tip: continue
            if pat.search(text):
                c = rest[3]
                if rtip == tip: c = min(c + 0.05, 0.98)
                if c > best_c: best, best_c = rule, c
        return best

    def _match_supplier(self, supplier):
        if not supplier: return None
        s = supplier.lower()
        for names, konto, label in _SUPPLIER_MAP:
            for n in names:
                if n in s:
                    return KontiranjePrijedlog(
                        duguje_konto=konto, duguje_naziv=konto_naziv(konto),
                        potrazuje_konto="2200", potrazuje_naziv="Dobavljaci",
                        pdv_konto="1230", confidence=0.90,
                        source="supplier_pattern", napomena=f"{label}: {supplier}",
                    )
        return None

    def _keyword_fallback(self, text, tip, iznos, pdv_stopa):
        if tip in ("ulazni", ""): d, p = "4099", "2200"
        elif tip == "izlazni": d, p = "1200", "7510"
        elif tip == "banka_uplata": d, p = "1500", "1200"
        elif tip == "banka_isplata": d, p = "2200", "1500"
        else: d, p = "4099", "2200"
        pdv_info = PDV_KONTA.get(int(pdv_stopa), PDV_KONTA[25])
        pdv_k = pdv_info["pretporez"] if tip == "ulazni" else pdv_info.get("obveza","") if tip == "izlazni" else ""
        return KontiranjePrijedlog(
            duguje_konto=d, duguje_naziv=konto_naziv(d),
            potrazuje_konto=p, potrazuje_naziv=konto_naziv(p),
            iznos=iznos, pdv_konto=pdv_k,
            pdv_iznos=round(iznos*pdv_stopa/(100+pdv_stopa),2) if pdv_stopa else 0,
            confidence=0.30, source="keyword_fallback",
            napomena="Nisam siguran — molim provjeru racunovodje",
        )

    def get_stats(self):
        return {
            "total": self._call_count, "memory_hits": self._memory_hits,
            "rule_hits": self._rule_hits, "pattern_hits": self._pattern_hits,
            "fallback": self._fallback_hits, "rules_count": len(_COMPILED_RULES),
            "kontni_plan_count": len(KONTNI_PLAN),
        }


def suggest_konto_by_keyword(keyword: str, limit: int = 5) -> List[Dict[str, str]]:
    kw = keyword.lower()
    return [{"konto": k, "naziv": v} for k, v in KONTNI_PLAN.items() if kw in v.lower() or kw in k][:limit]
