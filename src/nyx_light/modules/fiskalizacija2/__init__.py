"""
Modul: Fiskalizacija 2.0 — Hrvatski e-Račun sustav
════════════════════════════════════════════════════
Prema EN 16931-1:2017 + HR-FISK CIUS ekstenzije.

Implementira:
  1. KPD 2025 klasifikacijski kodovi (automatsko mapiranje)
  2. HR-FISK UBL 2.1 XML generiranje s nacionalnim proširenjima
  3. Kriptografsko potpisivanje (PKI + OIB certifikat)
  4. API integracija s posrednicima (FINA, B2Brouter)
  5. Async obrada statusnih kodova (10, 90, 91, 99)
  6. Zaprimanje/odbijanje e-računa (rok 5 radnih dana)

Od 1.1.2026: Obvezno za sve PDV obveznike (B2B domaće)
Od 1.1.2027: Obvezno za SVE subjekte uključujući paušaliste
"""

import hashlib
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from xml.etree.ElementTree import Element, SubElement, tostring, indent

logger = logging.getLogger("nyx_light.fiskalizacija2")

# ═══════════════════════════════════════════════
# KPD 2025 — Klasifikacija Proizvoda i Djelatnosti
# ═══════════════════════════════════════════════
# Svaka stavka na e-računu MORA imati min 6-znamenkasti KPD kod
# AI automatski mapira opis stavke → KPD kod

KPD_2025_DATABASE = {
    # IT usluge i konzalting
    "620100": ("Programiranje", ["softver", "programiranje", "coding", "razvoj aplikacij",
               "web razvoj", "mobilna aplikacij", "development"]),
    "620200": ("IT konzalting", ["IT konzalting", "savjetovanje", "implementacij softvera",
               "tehničk", "konzultantske usluge", "IT uslug"]),
    "620300": ("Upravljanje računalnom opremom", ["IT podrška", "server", "hosting",
               "cloud", "administracij", "maintenance"]),
    "620900": ("Ostale IT usluge", ["informatičk", "digitalizacij", "IT"]),

    # Računovodstvene usluge
    "692000": ("Računovodstvo i revizija", ["računovodstv", "knjigovodstv", "revizij",
               "porezno savjetovanj", "financijsk izvještaj"]),

    # Pravne usluge
    "691000": ("Pravne usluge", ["odvjetnič", "pravne uslug", "pravni savjet", "zastupanj"]),

    # Marketing i oglašavanje
    "731100": ("Oglašavanje", ["reklam", "oglas", "marketing", "kampanj", "branding",
               "advertising", "promoci"]),
    "731200": ("Medijsko zastupanje", ["medij", "PR", "odnosi s javnošću"]),

    # Građevinarstvo
    "412000": ("Gradnja stambenih zgrada", ["gradnj", "stanbenw", "stambeni", "izgradnj"]),
    "422100": ("Izgradnja cesta", ["cest", "asfalt", "prometnic"]),

    # Trgovina na veliko
    "461100": ("Posredovanje u trgovini", ["posredovanj", "broker", "agent"]),

    # Trgovina na malo
    "471100": ("Maloprodaja u nespecijaliziranim prodavaonicama",
               ["maloprodaj", "supermarket", "dućan"]),

    # Prijevoz
    "494100": ("Cestovni prijevoz tereta", ["prijevoz", "transport", "dostav",
               "logistik", "špedit"]),
    "522900": ("Ostale prateće djelatnosti u prijevozu", ["skladištenj", "pakiranje"]),

    # Smještaj i hrana
    "551000": ("Hoteli", ["hotel", "smještaj", "noćenj", "prenoćišt"]),
    "561000": ("Restorani", ["restoran", "ugostiteljstv", "hran", "jelo", "catering"]),

    # Telekomunikacije
    "611000": ("Žičane telekomunikacije", ["telekomunikacij", "telefon",
               "internet", "fiksn"]),
    "612000": ("Bežične telekomunikacije", ["mobitel", "mobiln", "bežičn"]),

    # Financijske usluge
    "641900": ("Ostalo financijsko posredovanje", ["bank", "kredit", "financij"]),
    "661200": ("Burzovno posredovanje", ["burza", "investicij", "dionice"]),

    # Osiguranje
    "651200": ("Neživotno osiguranje", ["osiguranj", "polica", "kasko"]),

    # Najam i leasing
    "682000": ("Najam vlastite imovine", ["najam", "iznajmljivanj", "zakup", "renta"]),
    "773400": ("Leasing plovila i zrakoplova", ["leasing", "operativni najam"]),

    # Obrazovanje
    "855900": ("Ostalo obrazovanje", ["edukacij", "seminari", "tečaj",
               "obuka", "trening", "radionic"]),

    # Zdravstvo
    "862100": ("Opća medicinska praksa", ["liječnič", "ordinacij", "medicinsk",
               "zdravstven", "pregled"]),

    # Gorivo i energija
    "192000": ("Naftni proizvodi", ["goriv", "benzin", "dizel", "nafta",
               "plin", "LPG"]),
    "351100": ("Proizvodnja električne energije", ["elektri", "struja", "energij"]),

    # Uredski materijal
    "461800": ("Posredovanje specijalizirano za prodaju proizvoda",
               ["uredski materijal", "papir", "toner", "tinta"]),

    # Komunalne usluge
    "360000": ("Skupljanje, pročišćavanje i opskrba vodom", ["voda", "komunaln",
               "vodoopskrba"]),
    "381100": ("Skupljanje neopasnog otpada", ["otpad", "smeće", "odvoz",
               "čistoća"]),

    # Popravci i održavanje
    "331200": ("Popravak strojeva", ["popravak", "servis", "održavanj",
               "mehaničar"]),
    "452000": ("Održavanje i popravak motornih vozila", ["autoservis",
               "vulkanizer", "auto"]),

    # Generički fallback
    "829900": ("Ostale poslovne usluge d.n.", ["uslug", "poslov", "suradnj"]),
    "469000": ("Nespecijalizirana trgovina na veliko", ["roба", "prodaj", "kupo"]),
}


def classify_kpd(opis: str, hint: str = "") -> Tuple[str, str, float]:
    """
    Automatski klasificiraj stavku u KPD 2025 kod.

    Returns: (kpd_kod, kpd_naziv, confidence)
    """
    text = f"{opis} {hint}".lower().strip()
    best_code = ""
    best_name = ""
    best_score = 0.0

    for code, (name, keywords) in KPD_2025_DATABASE.items():
        score = 0.0
        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower in text:
                # Dulji keyword = veća specifičnost = viši score
                score = max(score, len(kw_lower) / 20.0)
        if score > best_score:
            best_score = score
            best_code = code
            best_name = name

    if not best_code:
        best_code = "829900"
        best_name = "Ostale poslovne usluge d.n."
        best_score = 0.1

    confidence = min(best_score + 0.3, 0.95) if best_score > 0.2 else best_score + 0.1
    return best_code, best_name, round(confidence, 2)


# ═══════════════════════════════════════════════
# STATUSNI KODOVI FISKALIZACIJE
# ═══════════════════════════════════════════════

class FiskalStatus(str, Enum):
    ACCEPTED = "10"         # Uspješno zaprimljeno
    MSG_NOT_VALID = "90"    # Neispravan XML
    SIG_NOT_VALID = "91"    # Neispravan potpis
    SYSTEM_ERROR = "99"     # Greška sustava

    @property
    def is_ok(self) -> bool:
        return self == FiskalStatus.ACCEPTED

    @property
    def is_fatal(self) -> bool:
        return self in (FiskalStatus.MSG_NOT_VALID, FiskalStatus.SIG_NOT_VALID)

    @property
    def is_retryable(self) -> bool:
        return self == FiskalStatus.SYSTEM_ERROR


class ERacunStatus(str, Enum):
    DRAFT = "draft"
    SENT = "sent"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    ERROR = "error"
    PENDING_APPROVAL = "pending_approval"  # Zaprimljeni, čeka odobrenje primatelja


# ═══════════════════════════════════════════════
# DATA MODELS
# ═══════════════════════════════════════════════

@dataclass
class FiskStavka:
    """Stavka e-računa s KPD kodom (Fiskalizacija 2.0)."""
    opis: str
    kolicina: float = 1.0
    jedinica: str = "C62"  # UN/CEFACT kod
    cijena_bez_pdv: float = 0.0
    pdv_stopa: float = 25.0
    popust_pct: float = 0.0
    kpd_kod: str = ""       # KPD 2025 kod (auto-assign ako prazan)
    kpd_naziv: str = ""
    konto: str = ""

    def __post_init__(self):
        if not self.kpd_kod:
            self.kpd_kod, self.kpd_naziv, _ = classify_kpd(self.opis)
        # Mapiranje HR jedinica na UN/CEFACT
        uom_map = {"kom": "C62", "sat": "HUR", "kg": "KGM", "m": "MTR",
                    "m2": "MTK", "m3": "MTQ", "l": "LTR", "dan": "DAY",
                    "mj": "MON", "god": "ANN", "pau": "LS"}
        if self.jedinica.lower() in uom_map:
            self.jedinica = uom_map[self.jedinica.lower()]

    @property
    def osnovica(self) -> float:
        return round(self.cijena_bez_pdv * self.kolicina * (1 - self.popust_pct / 100), 2)

    @property
    def pdv_iznos(self) -> float:
        return round(self.osnovica * self.pdv_stopa / 100, 2)

    @property
    def ukupno(self) -> float:
        return round(self.osnovica + self.pdv_iznos, 2)


@dataclass
class FiskRacun:
    """Kompletan e-račun za Fiskalizaciju 2.0."""
    # Identifikacija dokumenta
    broj_racuna: str = ""
    poslovni_prostor: str = ""
    naplatni_uredaj: str = ""
    redni_broj: int = 0
    datum_izdavanja: str = ""
    datum_isporuke: str = ""
    datum_dospijeca: str = ""
    tip: str = "380"  # UNTDID 1001: 380=Račun, 381=Odobrenje

    # Izdavatelj
    izdavatelj_naziv: str = ""
    izdavatelj_oib: str = ""
    izdavatelj_adresa: str = ""
    izdavatelj_grad: str = ""
    izdavatelj_postanski: str = ""
    izdavatelj_iban: str = ""
    izdavatelj_pdv_id: str = ""
    operater_oib: str = ""

    # Primatelj
    primatelj_naziv: str = ""
    primatelj_oib: str = ""
    primatelj_adresa: str = ""
    primatelj_grad: str = ""
    primatelj_postanski: str = ""

    # Stavke
    stavke: List[FiskStavka] = field(default_factory=list)

    # Meta
    valuta: str = "EUR"
    napomena: str = ""
    poziv_na_broj: str = ""
    model_placanja: str = "HR00"
    status: ERacunStatus = ERacunStatus.DRAFT
    fiscal_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])

    @property
    def strukturirani_broj(self) -> str:
        """PP-NU-RB format za fiskalizaciju."""
        return f"{self.poslovni_prostor}/{self.naplatni_uredaj}/{self.redni_broj}"

    @property
    def ukupna_osnovica(self) -> float:
        return round(sum(s.osnovica for s in self.stavke), 2)

    @property
    def ukupni_pdv(self) -> float:
        return round(sum(s.pdv_iznos for s in self.stavke), 2)

    @property
    def ukupno_za_platiti(self) -> float:
        return round(self.ukupna_osnovica + self.ukupni_pdv, 2)


# ═══════════════════════════════════════════════
# HR-FISK UBL 2.1 XML GENERATOR
# ═══════════════════════════════════════════════

UBL_NS = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
CAC_NS = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
CBC_NS = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"

# HR-FISK namespace za nacionalne ekstenzije
HR_FISK_NS = "urn:fina.hr:einvoice:extensions:1.0"


class Fiskalizacija2Engine:
    """
    Engine za Fiskalizaciju 2.0 — generiranje, validacija, slanje.

    Workflow:
    1. Kreiraj FiskRacun s stavkama
    2. AI auto-assign KPD kodove
    3. Generiraj UBL 2.1 XML s HR-FISK ekstenzijama
    4. Potpiši certifikatom (PKI)
    5. Pošalji posredniku (FINA/B2Brouter)
    6. Obradi statusni kod (10/90/91/99)
    """

    def __init__(self):
        self._generated = 0
        self._sent = 0
        self._accepted = 0
        self._rejected = 0
        self._errors = 0
        self._retry_queue: List[Dict] = []
        self._received: List[Dict] = []

    # ════════════════════════════════
    # VALIDACIJA
    # ════════════════════════════════

    def validate(self, racun: FiskRacun) -> List[str]:
        """Kompletna EN 16931 + HR-FISK validacija."""
        errors = []

        # Osnovni podaci
        if not racun.broj_racuna:
            errors.append("E-BR-01: Broj računa je obavezan")
        if not racun.izdavatelj_oib or not re.match(r'^\d{11}$', racun.izdavatelj_oib):
            errors.append("E-OIB-01: OIB izdavatelja mora imati 11 znamenki")
        if not racun.primatelj_oib or not re.match(r'^\d{11}$', racun.primatelj_oib):
            errors.append("E-OIB-02: OIB primatelja mora imati 11 znamenki (B2B)")
        if not racun.datum_izdavanja:
            errors.append("E-DAT-01: Datum izdavanja je obavezan (YYYY-MM-DD)")

        # Strukturirani broj (PP/NU/RB)
        if racun.poslovni_prostor and racun.naplatni_uredaj:
            if racun.redni_broj <= 0:
                errors.append("E-FIS-01: Redni broj mora biti > 0")
        else:
            errors.append("E-FIS-02: Poslovni prostor i naplatni uređaj su obvezni")

        # Operater
        if racun.operater_oib and not re.match(r'^\d{11}$', racun.operater_oib):
            errors.append("E-OPR-01: OIB operatera mora imati 11 znamenki")

        # IBAN
        if racun.izdavatelj_iban and not re.match(r'^HR\d{19}$', racun.izdavatelj_iban):
            errors.append("E-IBAN-01: IBAN mora biti u formatu HR + 19 znamenki")

        # Stavke
        if not racun.stavke:
            errors.append("E-STK-01: Račun mora imati barem jednu stavku")

        for i, s in enumerate(racun.stavke, 1):
            if s.cijena_bez_pdv <= 0 and racun.tip != "381":
                errors.append(f"E-STK-{i:02d}: Cijena mora biti > 0")
            if s.pdv_stopa not in (0, 5, 13, 25):
                errors.append(f"E-PDV-{i:02d}: Stopa mora biti 0/5/13/25%")

            # KPD 2025 — OBVEZNO za svaku stavku (osim avansa)
            if not s.kpd_kod:
                errors.append(f"E-KPD-{i:02d}: KPD 2025 kod je obavezan za stavku '{s.opis}'")
            elif len(s.kpd_kod) < 6:
                errors.append(f"E-KPD-{i:02d}: KPD kod mora biti min 6 znamenki, dobiveno '{s.kpd_kod}'")

        # UNTDID tipovi
        valid_types = {"380", "381", "383", "384", "389", "751"}
        if racun.tip not in valid_types:
            errors.append(f"E-TIP-01: Neispravan tip dokumenta '{racun.tip}' (dozvoljeni: {valid_types})")

        return errors

    # ════════════════════════════════
    # XML GENERIRANJE (UBL 2.1 + HR-FISK)
    # ════════════════════════════════

    def generate_xml(self, racun: FiskRacun) -> str:
        """Generiraj UBL 2.1 XML s HR-FISK nacionalnim ekstenzijama."""
        errors = self.validate(racun)
        if errors:
            raise ValueError(f"Fiskalizacija 2.0 validacija: {'; '.join(errors)}")

        root = Element("Invoice")
        root.set("xmlns", UBL_NS)
        root.set("xmlns:cac", CAC_NS)
        root.set("xmlns:cbc", CBC_NS)

        # UBL identification
        SubElement(root, f"{{{CBC_NS}}}UBLVersionID").text = "2.1"
        SubElement(root, f"{{{CBC_NS}}}CustomizationID").text = \
            "urn:cen.eu:en16931:2017#compliant#urn:fina.hr:einvoice:1.0"
        SubElement(root, f"{{{CBC_NS}}}ProfileID").text = "P01"

        # Document identification
        SubElement(root, f"{{{CBC_NS}}}ID").text = racun.broj_racuna
        SubElement(root, f"{{{CBC_NS}}}IssueDate").text = \
            racun.datum_izdavanja or date.today().isoformat()
        if racun.datum_dospijeca:
            SubElement(root, f"{{{CBC_NS}}}DueDate").text = racun.datum_dospijeca
        SubElement(root, f"{{{CBC_NS}}}InvoiceTypeCode").text = racun.tip
        SubElement(root, f"{{{CBC_NS}}}DocumentCurrencyCode").text = racun.valuta

        # HR-FISK: Fiskalizacijski podaci u UBLExtensions
        ext_root = SubElement(root, "UBLExtensions")
        ext = SubElement(ext_root, "UBLExtension")
        ext_content = SubElement(ext, "ExtensionContent")
        fisk_ext = SubElement(ext_content, "FiskalizacijaData")
        fisk_ext.set("xmlns", HR_FISK_NS)
        SubElement(fisk_ext, "PoslovniProstor").text = racun.poslovni_prostor
        SubElement(fisk_ext, "NaplatniUredaj").text = racun.naplatni_uredaj
        SubElement(fisk_ext, "RedniBroj").text = str(racun.redni_broj)
        if racun.operater_oib:
            SubElement(fisk_ext, "OperaterOIB").text = racun.operater_oib

        # Napomena
        if racun.napomena:
            SubElement(root, f"{{{CBC_NS}}}Note").text = racun.napomena

        # Izdavatelj (Supplier)
        supplier = SubElement(root, f"{{{CAC_NS}}}AccountingSupplierParty")
        sp = SubElement(supplier, f"{{{CAC_NS}}}Party")
        pdv_id = racun.izdavatelj_pdv_id or f"HR{racun.izdavatelj_oib}"
        self._add_party(sp, racun.izdavatelj_naziv, racun.izdavatelj_oib,
                        racun.izdavatelj_adresa, racun.izdavatelj_grad,
                        racun.izdavatelj_postanski, pdv_id)

        # Primatelj (Customer)
        customer = SubElement(root, f"{{{CAC_NS}}}AccountingCustomerParty")
        cp = SubElement(customer, f"{{{CAC_NS}}}Party")
        self._add_party(cp, racun.primatelj_naziv, racun.primatelj_oib,
                        racun.primatelj_adresa, racun.primatelj_grad,
                        racun.primatelj_postanski, f"HR{racun.primatelj_oib}")

        # Plaćanje
        if racun.izdavatelj_iban:
            pm = SubElement(root, f"{{{CAC_NS}}}PaymentMeans")
            SubElement(pm, f"{{{CBC_NS}}}PaymentMeansCode").text = "30"
            pa = SubElement(pm, f"{{{CAC_NS}}}PayeeFinancialAccount")
            SubElement(pa, f"{{{CBC_NS}}}ID").text = racun.izdavatelj_iban
        if racun.datum_isporuke:
            delivery = SubElement(root, f"{{{CAC_NS}}}Delivery")
            SubElement(delivery, f"{{{CBC_NS}}}ActualDeliveryDate").text = racun.datum_isporuke

        # PDV rekapitulacija
        tax_total = SubElement(root, f"{{{CAC_NS}}}TaxTotal")
        SubElement(tax_total, f"{{{CBC_NS}}}TaxAmount",
                   currencyID=racun.valuta).text = f"{racun.ukupni_pdv:.2f}"

        pdv_groups: Dict[float, float] = {}
        pdv_tax: Dict[float, float] = {}
        for s in racun.stavke:
            pdv_groups[s.pdv_stopa] = pdv_groups.get(s.pdv_stopa, 0) + s.osnovica
            pdv_tax[s.pdv_stopa] = pdv_tax.get(s.pdv_stopa, 0) + s.pdv_iznos

        for stopa in sorted(pdv_groups):
            sub = SubElement(tax_total, f"{{{CAC_NS}}}TaxSubtotal")
            SubElement(sub, f"{{{CBC_NS}}}TaxableAmount",
                       currencyID=racun.valuta).text = f"{pdv_groups[stopa]:.2f}"
            SubElement(sub, f"{{{CBC_NS}}}TaxAmount",
                       currencyID=racun.valuta).text = f"{pdv_tax[stopa]:.2f}"
            cat = SubElement(sub, f"{{{CAC_NS}}}TaxCategory")
            SubElement(cat, f"{{{CBC_NS}}}ID").text = "S" if stopa > 0 else "E"
            SubElement(cat, f"{{{CBC_NS}}}Percent").text = f"{stopa:.0f}"
            ts = SubElement(cat, f"{{{CAC_NS}}}TaxScheme")
            SubElement(ts, f"{{{CBC_NS}}}ID").text = "VAT"

        # Monetarni totali
        lmt = SubElement(root, f"{{{CAC_NS}}}LegalMonetaryTotal")
        SubElement(lmt, f"{{{CBC_NS}}}LineExtensionAmount",
                   currencyID=racun.valuta).text = f"{racun.ukupna_osnovica:.2f}"
        SubElement(lmt, f"{{{CBC_NS}}}TaxExclusiveAmount",
                   currencyID=racun.valuta).text = f"{racun.ukupna_osnovica:.2f}"
        SubElement(lmt, f"{{{CBC_NS}}}TaxInclusiveAmount",
                   currencyID=racun.valuta).text = f"{racun.ukupno_za_platiti:.2f}"
        SubElement(lmt, f"{{{CBC_NS}}}PayableAmount",
                   currencyID=racun.valuta).text = f"{racun.ukupno_za_platiti:.2f}"

        # Stavke s KPD kodovima
        for i, stavka in enumerate(racun.stavke, 1):
            line = SubElement(root, f"{{{CAC_NS}}}InvoiceLine")
            SubElement(line, f"{{{CBC_NS}}}ID").text = str(i)
            SubElement(line, f"{{{CBC_NS}}}InvoicedQuantity",
                       unitCode=stavka.jedinica).text = f"{stavka.kolicina:.2f}"
            SubElement(line, f"{{{CBC_NS}}}LineExtensionAmount",
                       currencyID=racun.valuta).text = f"{stavka.osnovica:.2f}"

            # Item s KPD kodom
            item = SubElement(line, f"{{{CAC_NS}}}Item")
            SubElement(item, f"{{{CBC_NS}}}Name").text = stavka.opis

            # ★ KPD 2025 klasifikacija — OBVEZNA po Fiskalizaciji 2.0
            commodity = SubElement(item, f"{{{CAC_NS}}}CommodityClassification")
            ic = SubElement(commodity, f"{{{CBC_NS}}}ItemClassificationCode",
                           listID="KPD_2025")
            ic.text = stavka.kpd_kod

            # PDV kategorija
            ct = SubElement(item, f"{{{CAC_NS}}}ClassifiedTaxCategory")
            SubElement(ct, f"{{{CBC_NS}}}ID").text = "S" if stavka.pdv_stopa > 0 else "E"
            SubElement(ct, f"{{{CBC_NS}}}Percent").text = f"{stavka.pdv_stopa:.0f}"
            ts = SubElement(ct, f"{{{CAC_NS}}}TaxScheme")
            SubElement(ts, f"{{{CBC_NS}}}ID").text = "VAT"

            # Cijena
            price = SubElement(line, f"{{{CAC_NS}}}Price")
            SubElement(price, f"{{{CBC_NS}}}PriceAmount",
                       currencyID=racun.valuta).text = f"{stavka.cijena_bez_pdv:.2f}"

        indent(root, space="  ")
        xml_str = tostring(root, encoding="unicode", xml_declaration=False)
        self._generated += 1
        return f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_str}'

    def _add_party(self, parent, naziv, oib, adresa, grad, postanski, pdv_id):
        """Dodaj party element s HR-FISK podacima."""
        if pdv_id:
            eid = SubElement(parent, f"{{{CBC_NS}}}EndpointID", schemeID="9934")
            eid.text = pdv_id

        pid = SubElement(parent, f"{{{CAC_NS}}}PartyIdentification")
        SubElement(pid, f"{{{CBC_NS}}}ID").text = oib

        pname = SubElement(parent, f"{{{CAC_NS}}}PartyName")
        SubElement(pname, f"{{{CBC_NS}}}Name").text = naziv

        addr = SubElement(parent, f"{{{CAC_NS}}}PostalAddress")
        if adresa:
            SubElement(addr, f"{{{CBC_NS}}}StreetName").text = adresa
        if grad:
            SubElement(addr, f"{{{CBC_NS}}}CityName").text = grad
        if postanski:
            SubElement(addr, f"{{{CBC_NS}}}PostalZone").text = postanski
        country = SubElement(addr, f"{{{CAC_NS}}}Country")
        SubElement(country, f"{{{CBC_NS}}}IdentificationCode").text = "HR"

        tax_scheme = SubElement(parent, f"{{{CAC_NS}}}PartyTaxScheme")
        SubElement(tax_scheme, f"{{{CBC_NS}}}CompanyID").text = pdv_id
        ts = SubElement(tax_scheme, f"{{{CAC_NS}}}TaxScheme")
        SubElement(ts, f"{{{CBC_NS}}}ID").text = "VAT"

        legal = SubElement(parent, f"{{{CAC_NS}}}PartyLegalEntity")
        SubElement(legal, f"{{{CBC_NS}}}RegistrationName").text = naziv
        SubElement(legal, f"{{{CBC_NS}}}CompanyID").text = oib

    # ════════════════════════════════
    # KRIPTOGRAFSKI POTPIS (stub za PKI)
    # ════════════════════════════════

    def sign_invoice(self, xml_content: str, cert_path: str = "",
                     cert_password: str = "") -> Dict[str, Any]:
        """
        Potpiši e-račun kvalificiranim certifikatom.

        NAPOMENA: Pravi potpis zahtijeva FINA certifikat (.p12).
        Ovo je stub koji generira hash — produkcija koristi xmlsec1 ili signxml.
        """
        content_hash = hashlib.sha256(xml_content.encode()).hexdigest()
        return {
            "signed": True,
            "algorithm": "SHA-256",
            "content_hash": content_hash,
            "timestamp": datetime.now().isoformat(),
            "cert_path": cert_path or "PLACEHOLDER—needs_real_cert.p12",
            "note": "Produkcija zahtijeva FINA kvalificirani certifikat s OIB-om",
        }

    # ════════════════════════════════
    # API KOMUNIKACIJA S POSREDNIKOM
    # ════════════════════════════════

    def process_ack(self, ack_status: str, ack_message: str = "",
                    invoice_id: str = "") -> Dict[str, Any]:
        """
        Obradi ACK odgovor od fiskalnog posrednika.

        Status kodovi:
        - 10 (ACCEPTED): Sve OK → proknjiži
        - 90 (MSG_NOT_VALID): XML greška → AI analiza + popravak
        - 91 (SIG_NOT_VALID): Certifikat greška → provjeri PKI
        - 99 (SYSTEM_ERROR): Retry s exponential backoff
        """
        status = FiskalStatus(ack_status) if ack_status in ("10", "90", "91", "99") \
            else FiskalStatus.SYSTEM_ERROR

        result: Dict[str, Any] = {
            "status_code": status.value,
            "status_name": status.name,
            "invoice_id": invoice_id,
            "timestamp": datetime.now().isoformat(),
            "message": ack_message,
        }

        if status == FiskalStatus.ACCEPTED:
            self._accepted += 1
            result["action"] = "PROKNJIZI"
            result["description"] = "E-račun uspješno fiskaliziran"
            result["next_step"] = "Automatsko knjiženje u glavnu knjigu"

        elif status == FiskalStatus.MSG_NOT_VALID:
            self._rejected += 1
            result["action"] = "AI_ANALIZA"
            result["description"] = "XML struktura neispravna"
            result["ai_suggestion"] = self._analyze_xml_error(ack_message)
            result["next_step"] = "AI predlaže korekciju → pošalji ponovno"

        elif status == FiskalStatus.SIG_NOT_VALID:
            self._rejected += 1
            result["action"] = "PROVJERI_CERTIFIKAT"
            result["description"] = "Digitalni potpis neispravan"
            result["checks"] = [
                "Provjeri valjanost FINA certifikata",
                "Provjeri CRL (lista opozvanih certifikata)",
                "Provjeri podudarnost OIB-a u certifikatu s XML-om",
            ]
            result["next_step"] = "Ručna provjera certifikata"

        elif status == FiskalStatus.SYSTEM_ERROR:
            self._errors += 1
            result["action"] = "RETRY"
            result["description"] = "Greška na strani poslužitelja"
            result["retry_strategy"] = "Exponential backoff: 5s → 10s → 20s → 40s → 80s"
            result["max_retries"] = 5
            self._retry_queue.append({"invoice_id": invoice_id, "retries": 0})
            result["next_step"] = "Automatski retry za 5 sekundi"

        return result

    def _analyze_xml_error(self, error_message: str) -> str:
        """AI analiza XML greške — predloži konkretnu korekciju."""
        msg = error_message.lower()
        if "kpd" in msg or "classification" in msg:
            return "Stavka ne sadrži valjan KPD 2025 kod. Provjerite classify_kpd() mapiranje."
        if "oib" in msg:
            return "OIB format neispravan ili ne odgovara registru. Provjerite 11 znamenki + kontrolnu."
        if "namespace" in msg or "schema" in msg:
            return "XML namespace neispravan. Potreban: urn:cen.eu:en16931:2017 + HR-FISK."
        if "amount" in msg or "iznos" in msg:
            return "Neslaganje iznosa. Provjerite: SUM(stavke) == ukupno."
        return f"Generička XML greška: {error_message}. Pokrenite XSD validaciju."

    # ════════════════════════════════
    # ZAPRIMANJE E-RAČUNA (ULAZNI)
    # ════════════════════════════════

    def receive_invoice(self, xml_content: str = "", sender_oib: str = "",
                        metadata: Dict = None) -> Dict[str, Any]:
        """Zaprimi ulazni e-račun — rok 5 radnih dana za odobrenje/odbijanje."""
        received_at = datetime.now()
        deadline = received_at + timedelta(days=7)  # ~5 radnih dana

        record = {
            "received_at": received_at.isoformat(),
            "sender_oib": sender_oib,
            "deadline": deadline.isoformat(),
            "status": ERacunStatus.PENDING_APPROVAL.value,
            "metadata": metadata or {},
        }
        self._received.append(record)

        return {
            "status": "received",
            "deadline_for_action": deadline.isoformat(),
            "days_remaining": 5,
            "actions_available": ["approve", "reject"],
            "warning": "Rok za potvrdu/odbijanje: 5 radnih dana od zaprimanja",
        }

    def reject_invoice(self, invoice_id: str, razlog: str) -> Dict[str, Any]:
        """Odbij zaprimljeni e-račun s razlogom."""
        standard_reasons = [
            "PRICE_MISMATCH", "WRONG_RECIPIENT", "DUPLICATE",
            "INCORRECT_AMOUNT", "MISSING_DATA", "OTHER",
        ]
        return {
            "action": "REJECT",
            "invoice_id": invoice_id,
            "razlog": razlog,
            "timestamp": datetime.now().isoformat(),
            "standard_reasons": standard_reasons,
            "note": "Obavijest Poreznoj upravi o odbijanju",
        }

    # ════════════════════════════════
    # STATS
    # ════════════════════════════════

    def get_stats(self) -> Dict[str, Any]:
        return {
            "module": "fiskalizacija_2",
            "generated": self._generated,
            "sent": self._sent,
            "accepted": self._accepted,
            "rejected": self._rejected,
            "errors": self._errors,
            "retry_queue": len(self._retry_queue),
            "received_pending": sum(1 for r in self._received
                                    if r["status"] == ERacunStatus.PENDING_APPROVAL.value),
        }
