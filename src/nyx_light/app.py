"""
Nyx Light — Računovođa: Unified Application Skeleton (Kostur)

OVO JE CENTRALNA KLASA CIJELOG SUSTAVA.

Tok: Dokument → Modul → Pipeline (pending) → Approval → Export (CPP/Synesis)

Svaki tip dokumenta ima svoj put:
  Ulazni račun:  OCR → Kontiranje → Pipeline → Approve → CPP/Synesis XML/CSV
  Bankovni izvod: Parser → Sparivanje → Pipeline → Approve → CPP/Synesis
  Plaća:         PayrollEngine → Pipeline → Approve → CPP/Synesis + JOPPD
  Blagajna:      Validator → Kontiranje → Pipeline → Approve → CPP/Synesis
  Putni nalog:   Checker → Pipeline → Approve → CPP/Synesis
  Osnovno sred:  OS Engine → Pipeline → Approve → CPP/Synesis
  IOS:           IOS Modul → Pipeline → Approve → CPP/Synesis
  PDV:           PDV Engine → Pipeline → ePorezna (ručno)
  GFI:           GFI Prep → Pipeline → eFINA (ručno)
"""

import logging
from typing import Any, Dict, List, Optional

# Core
from nyx_light.pipeline import BookingPipeline, BookingProposal
from nyx_light.pipeline.persistent import PersistentPipeline
from nyx_light.pipeline.persistent import PersistentPipeline
from nyx_light.export import ERPExporter
from nyx_light.erp import ERPConnector, ERPConnectionConfig, create_cpp_connector, create_synesis_connector
from nyx_light.registry import ClientRegistry, ClientConfig

# Moduli — Grupa A
from nyx_light.modules.invoice_ocr.extractor import InvoiceExtractor
from nyx_light.modules.invoice_ocr.eu_invoice import EUInvoiceRecognizer
from nyx_light.modules.outgoing_invoice import OutgoingInvoiceValidator
from nyx_light.modules.kontiranje.engine import KontiranjeEngine
from nyx_light.modules.kontiranje.kontni_plan import get_full_kontni_plan, suggest_konto_by_keyword
from nyx_light.modules.bank_parser.parser import BankStatementParser
from nyx_light.modules.blagajna.validator import BlagajnaValidator
from nyx_light.modules.putni_nalozi.checker import PutniNalogChecker
from nyx_light.modules.osnovna_sredstva import OsnovnaSredstvaEngine
from nyx_light.modules.accruals import AccrualsChecklist
from nyx_light.modules.ios_reconciliation.ios import IOSReconciliation

# Moduli — Grupa B
from nyx_light.modules.payroll import PayrollEngine, Employee

# Moduli — Grupa C
from nyx_light.modules.pdv_prijava import PDVPrijavaEngine
from nyx_light.modules.joppd import JOPPDGenerator
from nyx_light.modules.porez_dobit import PorezDobitiEngine
from nyx_light.modules.porez_dohodak import PorezDohodakEngine

# Moduli — Grupa D
from nyx_light.modules.gfi_prep import GFIPrepEngine

# Moduli — Grupa B+
from nyx_light.modules.bolovanje import BolovanjeEngine
from nyx_light.modules.drugi_dohodak import DrugiDohodakEngine

# Moduli — Grupa G
from nyx_light.modules.kpi import KPIDashboard

# Moduli — Grupa D extra
from nyx_light.modules.novcani_tokovi import NovcanitTokoviEngine
from nyx_light.modules.gfi_xml import GFIXMLGenerator

# Moduli — Grupa C extra
from nyx_light.modules.intrastat import IntrastatEngine

# Moduli — Grupa B+ extra
from nyx_light.modules.kadrovska import KadrovskaEvidencija

# Moduli — Grupa F
from nyx_light.modules.fakturiranje import FakturiranjeEngine

# Moduli — Grupa G extra
from nyx_light.modules.likvidacija import LikvidacijaEngine

# Moduli — Grupa F
from nyx_light.modules.deadlines import DeadlineTracker

# Parseri za sekundarne ERP sustave
from nyx_light.modules.eracuni_parser import ERacuniParser, PantheonParser

# Safety
from nyx_light.safety.overseer import AccountingOverseer

logger = logging.getLogger("nyx_light.app")


class NyxLightApp:
    """
    Unified Skeleton — spaja SVE module u jedan sustav.
    
    Primjer korištenja:
    
        app = NyxLightApp()
        app.register_client(ClientConfig(id="K001", naziv="ABC d.o.o.",
                                          erp_target="CPP"))
    
        # Ulazni račun
        result = app.process_invoice(ocr_data, client_id="K001")
        # → result["status"] == "pending", result["id"] == "abc123"
    
        # Odobri
        app.approve("abc123", user_id="ana")
    
        # Export u CPP
        export = app.export_to_erp(client_id="K001")
        # → CPP XML datoteka generirana
    """

    def __init__(self, export_dir: str = "data/exports", db_path: str = None):
        # ── Core ──
        self.exporter = ERPExporter(export_dir=export_dir)
        if db_path:
            self._persistent = PersistentPipeline(db_path)
            self.pipeline = self._persistent.pipeline
            self.pipeline.exporter = self.exporter
        else:
            self._persistent = None
            self.pipeline = BookingPipeline(exporter=self.exporter)
        self.registry = ClientRegistry()
        self.overseer = AccountingOverseer()

        # ── Dvosmjerni ERP konektori ──
        self._erp_connectors: Dict[str, ERPConnector] = {}

        # ── Grupa A — Obrada dokumentacije ──
        self.invoice_ocr = InvoiceExtractor()          # A1
        self.eu_invoice = EUInvoiceRecognizer()         # A1-EU
        self.outgoing_validator = OutgoingInvoiceValidator()  # A2
        self.kontiranje = KontiranjeEngine()            # A3
        self.bank_parser = BankStatementParser()        # A4
        self.blagajna = BlagajnaValidator()             # A5
        self.putni_nalozi = PutniNalogChecker()         # A6
        self.osnovna_sredstva = OsnovnaSredstvaEngine()  # A7
        self.accruals = AccrualsChecklist()              # A8
        self.ios = IOSReconciliation()                  # A9

        # ── Grupa B — Plaće ──
        self.payroll = PayrollEngine()
        self.joppd = JOPPDGenerator()

        # ── Grupa C — Porezne prijave ──
        self.pdv = PDVPrijavaEngine()
        self.porez_dobit = PorezDobitiEngine()
        self.porez_dohodak = PorezDohodakEngine()

        # ── Grupa D — GFI ──
        self.gfi = GFIPrepEngine()

        # ── Grupa B+ — Bolovanje, Drugi dohodak ──
        self.bolovanje = BolovanjeEngine()
        self.drugi_dohodak = DrugiDohodakEngine()

        # ── Grupa G — KPI ──
        self.kpi = KPIDashboard()

        # ── Grupa D extra — Novčani tokovi, GFI XML ──
        self.novcani_tokovi = NovcanitTokoviEngine()
        self.gfi_xml = GFIXMLGenerator()

        # ── Grupa C extra — Intrastat ──
        self.intrastat = IntrastatEngine()

        # ── Grupa B+ extra — Kadrovska ──
        self.kadrovska = KadrovskaEvidencija()

        # ── Grupa F — Fakturiranje ──
        self.fakturiranje = FakturiranjeEngine()

        # ── Grupa G extra — Likvidacija ──
        self.likvidacija = LikvidacijaEngine()

        # ── Grupa F — Rokovi ──
        self.deadlines = DeadlineTracker()

        # ── Parseri za sekundarne ERP ──
        self.eracuni_parser = ERacuniParser()
        self.pantheon_parser = PantheonParser()

        # ── Kontni plan ──
        self.kontni_plan = get_full_kontni_plan()

        logger.info("NyxLightApp inicijaliziran — svi moduli spojeni")

    def _submit(self, proposal: BookingProposal) -> Dict[str, Any]:
        """Route submit through persistent pipeline when available."""
        if self._persistent:
            return self._persistent.submit(proposal)
        return self.pipeline.submit(proposal)

    # ════════════════════════════════════════════════════
    # CLIENT REGISTRY
    # ════════════════════════════════════════════════════

    def register_client(self, config: ClientConfig) -> Dict[str, Any]:
        return self.registry.register(config)

    def get_client_erp(self, client_id: str) -> str:
        return self.registry.get_erp_target(client_id)

    # ════════════════════════════════════════════════════
    # A1: ULAZNI RAČUNI
    # ════════════════════════════════════════════════════

    def process_invoice(
        self, invoice_data: Dict, client_id: str, auto_kontiranje: bool = True
    ) -> Dict[str, Any]:
        """
        Obradi ulazni račun: OCR → Kontiranje → Pipeline (pending).
        Automatski detektira EU/inozemne račune i rutira ih.
        Vraća prijedlog koji čeka odobrenje.
        """
        # Provjeri je li EU/inozemni račun
        text = invoice_data.get("raw_text", "")
        xml = invoice_data.get("xml_content", "")
        vat_id = invoice_data.get("oib_izdavatelja", "") or invoice_data.get("seller_vat_id", "")

        origin = self.eu_invoice.detect_origin(text=text, xml=xml, vat_id=vat_id)
        if origin.value != "hr":
            return self.process_eu_invoice(invoice_data, client_id, origin)

        erp = self.get_client_erp(client_id)

        # Kontiranje
        konto_result = {"suggested_konto": "7800", "confidence": 0.3}
        if auto_kontiranje:
            desc = invoice_data.get("opis", "") or invoice_data.get("dobavljac", "")
            konto_result = self.kontiranje.suggest_konto(desc)

        # Pipeline
        proposal = self.pipeline.from_invoice(invoice_data, konto_result, client_id, erp)
        return self._submit(proposal)

    def process_eu_invoice(
        self, invoice_data: Dict, client_id: str, origin=None
    ) -> Dict[str, Any]:
        """
        Obradi EU/inozemni račun s automatic reverse charge detekcijom.

        Koraci:
          1. Parse XML (UBL/CII/Peppol) ili OCR tekst
          2. Detektiraj VAT ID, valutu, zemlju
          3. Odredi PDV tretman (reverse charge, EU stjecanje, uvoz)
          4. Predloži kontiranje s HR kontima
          5. Šalji u Pipeline za odobrenje
        """
        from nyx_light.modules.invoice_ocr.eu_invoice import InvoiceOrigin

        xml = invoice_data.get("xml_content", "")
        text = invoice_data.get("raw_text", "")

        # Parse
        if xml:
            eu_data = self.eu_invoice.parse_xml(xml)
        else:
            eu_data = self.eu_invoice.parse_ocr_text(text)

        erp = self.get_client_erp(client_id)

        # Kontiranje na temelju PDV tretmana
        konto = "4xxx"
        if eu_data.vat_treatment.value == "reverse_charge":
            konto = eu_data.suggested_accounts.get("trošak", "4300")
        elif eu_data.vat_treatment.value == "import":
            konto = eu_data.suggested_accounts.get("trošak", "4200")
        elif eu_data.vat_treatment.value == "eu_acquisition":
            konto = "4100"  # Nabava iz EU

        # Build proposal
        proposal = self.pipeline.from_invoice(
            {
                "oib_izdavatelja": eu_data.seller_vat_id,
                "dobavljac": eu_data.seller_name,
                "iznos_ukupno": eu_data.total,
                "iznos_pdv": eu_data.total_vat,
                "iznos_osnovica": eu_data.subtotal,
                "valuta": eu_data.currency,
                "datum": eu_data.invoice_date,
                "broj_racuna": eu_data.invoice_number,
                "origin": eu_data.origin.value,
                "vat_treatment": eu_data.vat_treatment.value,
                "reverse_charge": eu_data.reverse_charge,
                "seller_country": eu_data.seller_country,
                "needs_exchange_rate": eu_data.needs_exchange_rate,
                "warnings": eu_data.warnings,
            },
            {"suggested_konto": konto, "confidence": eu_data.confidence},
            client_id,
            erp,
        )
        return self._submit(proposal)

    # ════════════════════════════════════════════════════
    # A2: IZLAZNI RAČUNI
    # ════════════════════════════════════════════════════

    def validate_outgoing_invoice(self, invoice_data: Dict) -> Dict[str, Any]:
        """Validiraj izlazni račun prema Zakonu o PDV-u."""
        result = self.outgoing_validator.validate(invoice_data)
        return {
            "valid": result.valid,
            "errors": result.errors,
            "warnings": result.warnings,
            "pdv_status": result.pdv_status,
        }

    # ════════════════════════════════════════════════════
    # A4: BANKOVNI IZVODI
    # ════════════════════════════════════════════════════

    def process_bank_statement(
        self, content: str, bank: str, client_id: str
    ) -> Dict[str, Any]:
        """
        Obradi bankovni izvod: Parse → Sparivanje → Pipeline batch.
        """
        import tempfile
        erp = self.get_client_erp(client_id)

        # Save content to temp file and parse
        suffix = ".sta" if bank.lower() == "mt940" else ".csv"
        with tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False) as f:
            f.write(content)
            f.flush()
            transactions = self.bank_parser.parse(f.name, bank)
            import os
            os.unlink(f.name)

        # Convert & submit batch
        proposals = self.pipeline.from_bank_statement(transactions, client_id, erp)
        return self.pipeline.submit_batch(proposals)

    # ════════════════════════════════════════════════════
    # A5: BLAGAJNA
    # ════════════════════════════════════════════════════

    def process_petty_cash(
        self, tx_data: Dict, client_id: str
    ) -> Dict[str, Any]:
        """Blagajna: Validacija → Kontiranje → Pipeline."""
        erp = self.get_client_erp(client_id)

        # Validate
        from nyx_light.modules.blagajna.validator import BlagajnaTx
        tx = BlagajnaTx(**{k: v for k, v in tx_data.items() if k in BlagajnaTx.__dataclass_fields__})
        validation = self.blagajna.validate_transaction(tx)

        if not validation.valid:
            return {"status": "rejected", "errors": validation.errors}

        # Kontiranje
        konto = self.kontiranje.suggest_konto(tx_data.get("opis", ""))

        # Pipeline
        proposal = self.pipeline.from_petty_cash(tx_data, konto, client_id, erp)
        proposal.warnings.extend(validation.warnings)
        return self._submit(proposal)

    # ════════════════════════════════════════════════════
    # A6: PUTNI NALOZI
    # ════════════════════════════════════════════════════

    def process_travel_expense(
        self, putni_data: Dict, client_id: str
    ) -> Dict[str, Any]:
        """Putni nalog: Validacija → Pipeline."""
        erp = self.get_client_erp(client_id)
        proposal = self.pipeline.from_travel_expense(putni_data, client_id, erp)
        return self._submit(proposal)

    # ════════════════════════════════════════════════════
    # A7: OSNOVNA SREDSTVA
    # ════════════════════════════════════════════════════

    def add_fixed_asset(self, asset_data: Dict) -> Dict[str, Any]:
        return self.osnovna_sredstva.add_asset(asset_data)

    def run_monthly_depreciation(self, client_id: str) -> Dict[str, Any]:
        """Mjesečna amortizacija → Pipeline za svako sredstvo."""
        erp = self.get_client_erp(client_id)
        depr = self.osnovna_sredstva.calculate_monthly_depreciation()
        proposals = []
        for d in depr:
            p = self.pipeline.from_depreciation(
                d["naziv"], d["mjesecna_amortizacija"], client_id, erp
            )
            proposals.append(p)
        if proposals:
            return self.pipeline.submit_batch(proposals)
        return {"status": "empty", "message": "Nema sredstava za amortizaciju"}

    # ════════════════════════════════════════════════════
    # A8: OBRAČUNSKE STAVKE
    # ════════════════════════════════════════════════════

    def get_period_checklist(self, period: str = "monthly", client_id: str = "") -> Dict:
        return self.accruals.get_checklist(period, client_id)

    # ════════════════════════════════════════════════════
    # A9: IOS USKLAĐIVANJA
    # ════════════════════════════════════════════════════

    def process_ios(self, ios_data: Dict, client_id: str) -> Dict[str, Any]:
        erp = self.get_client_erp(client_id)
        proposal = self.pipeline.from_ios(ios_data, client_id, erp)
        return self._submit(proposal)

    # ════════════════════════════════════════════════════
    # B: PLAĆE
    # ════════════════════════════════════════════════════

    def process_payroll(
        self, employees: List[Employee], client_id: str,
        generate_joppd: bool = True,
    ) -> Dict[str, Any]:
        """
        Obračunaj plaće za sve zaposlenike → Pipeline + JOPPD.
        """
        erp = self.get_client_erp(client_id)
        client = self.registry.get(client_id)

        results = []
        proposals = []
        for emp in employees:
            pr = self.payroll.calculate(emp)
            results.append(pr)
            p = self.pipeline.from_payroll(pr, client_id, erp)
            proposals.append(p)

        batch_result = self.pipeline.submit_batch(proposals)

        # JOPPD
        joppd_data = None
        if generate_joppd:
            oib = client.oib if client else ""
            naziv = client.naziv if client else ""
            joppd_obrazac = self.joppd.from_payroll_results(results, oib, naziv)
            joppd_data = self.joppd.to_dict(joppd_obrazac)

        return {
            **batch_result,
            "payroll_results": [
                {"name": r.employee_name, "bruto": r.bruto_placa, "neto": r.neto_placa}
                for r in results
            ],
            "joppd": joppd_data,
        }

    # ════════════════════════════════════════════════════
    # C: PDV PRIJAVA
    # ════════════════════════════════════════════════════

    def prepare_pdv_prijava(
        self, stavke: List, client_id: str
    ) -> Dict[str, Any]:
        """Pripremi PDV prijavu za klijenta."""
        client = self.registry.get(client_id)
        oib = client.oib if client else ""
        naziv = client.naziv if client else ""
        mjesecna = client.pdv_period == "monthly" if client else True

        ppo = self.pdv.calculate(stavke, oib, naziv, mjesecna=mjesecna)
        return self.pdv.to_dict(ppo)

    # ════════════════════════════════════════════════════
    # C: POREZ NA DOBIT (PD obrazac)
    # ════════════════════════════════════════════════════

    def prepare_porez_dobit(
        self, client_id: str, godina: int,
        ukupni_prihodi: float, ukupni_rashodi: float,
        uvecanja: Dict = None, umanjenja: Dict = None,
        predujmovi: float = 0.0,
    ) -> Dict[str, Any]:
        """Pripremi PD obrazac za klijenta."""
        client = self.registry.get(client_id)
        pd = self.porez_dobit.calculate(
            godina, ukupni_prihodi, ukupni_rashodi,
            uvecanja, umanjenja, predujmovi,
            oib=client.oib if client else "",
            naziv=client.naziv if client else "",
        )
        return self.porez_dobit.to_dict(pd)

    # ════════════════════════════════════════════════════
    # C: POREZ NA DOHODAK (DOH obrazac)
    # ════════════════════════════════════════════════════

    def prepare_porez_dohodak(
        self, client_id: str, godina: int,
        primitci: float, izdatci: float,
        djeca: int = 0, grad: str = "Zagreb",
        predujmovi: float = 0.0,
    ) -> Dict[str, Any]:
        """Pripremi DOH obrazac za obrtnika."""
        client = self.registry.get(client_id)
        doh = self.porez_dohodak.calculate_obrt(
            godina, primitci, izdatci,
            djeca=djeca, grad=grad,
            placeni_predujmovi=predujmovi,
            oib=client.oib if client else "",
            ime=client.naziv if client else "",
        )
        return self.porez_dohodak.to_dict(doh)

    # ════════════════════════════════════════════════════
    # B+: BOLOVANJE
    # ════════════════════════════════════════════════════

    def process_sick_leave(
        self, djelatnik: str, vrsta: str, dani: int,
        prosjecna_placa: float, client_id: str,
    ) -> Dict[str, Any]:
        """Obračun bolovanja → Pipeline."""
        erp = self.get_client_erp(client_id)
        result = self.bolovanje.calculate(djelatnik, vrsta, dani, prosjecna_placa)
        lines = self.bolovanje.booking_lines(result)

        proposal = BookingProposal(
            client_id=client_id,
            document_type="bolovanje",
            erp_target=erp,
            lines=lines,
            opis=f"Bolovanje: {djelatnik} — {dani} dana ({vrsta})",
            ukupni_iznos=result.naknada_ukupno,
            confidence=0.9,
            source_module="bolovanje",
            warnings=result.warnings,
        )
        submit = self._submit(proposal)
        submit["bolovanje"] = {
            "teret_poslodavac": result.naknada_teret_poslodavac,
            "teret_hzzo": result.naknada_teret_hzzo,
            "dani_poslodavac": result.dani_poslodavac,
            "dani_hzzo": result.dani_hzzo,
            "naknada_dnevna": result.naknada_dnevna,
        }
        return submit

    # ════════════════════════════════════════════════════
    # B+: DRUGI DOHODAK (Autorski honorari, Ugovor o djelu)
    # ════════════════════════════════════════════════════

    def process_drugi_dohodak(
        self, ime: str, oib: str, bruto: float,
        vrsta: str, client_id: str, grad: str = "Zagreb",
    ) -> Dict[str, Any]:
        """Obračun autorskog honorara ili ugovora o djelu → Pipeline."""
        erp = self.get_client_erp(client_id)
        result = self.drugi_dohodak.calculate(ime, oib, bruto, vrsta, grad)
        lines = self.drugi_dohodak.booking_lines(result)

        proposal = BookingProposal(
            client_id=client_id,
            document_type="drugi_dohodak",
            erp_target=erp,
            lines=lines,
            opis=f"{vrsta}: {ime} — bruto {bruto:.2f} EUR",
            ukupni_iznos=result.ukupni_trosak,
            confidence=0.95,
            source_module="drugi_dohodak",
            warnings=result.warnings,
        )
        submit = self._submit(proposal)
        submit["obracun"] = {
            "bruto": result.bruto,
            "neto": result.neto,
            "mio": result.ukupno_mio,
            "porez_prirez": result.ukupno_porez_prirez,
            "zdravstveno_isplatitelj": result.zdravstveno,
            "ukupni_trosak": result.ukupni_trosak,
        }
        return submit

    # ════════════════════════════════════════════════════
    # D: NOVČANI TOKOVI (NTI Obrazac)
    # ════════════════════════════════════════════════════

    def prepare_novcani_tokovi(self, client_id: str, godina: int,
                                cf_data) -> Dict[str, Any]:
        """Pripremi NTI obrazac."""
        nti = self.novcani_tokovi.calculate(godina, cf_data)
        return self.novcani_tokovi.to_dict(nti)

    # ════════════════════════════════════════════════════
    # D6: GFI XML ZA FINA
    # ════════════════════════════════════════════════════

    def generate_gfi_xml(self, client_id: str, godina: int,
                          bilanca: Dict, rdg: Dict,
                          novcani_tokovi: Dict = None) -> Dict[str, Any]:
        """Generiraj GFI XML za predaju na FINA RGFI."""
        client = self.registry.get(client_id)
        return self.gfi_xml.generate(
            oib=client.oib if client else "",
            naziv=client.naziv if client else "",
            godina=godina,
            kategorija=client.kategorija if client else "mikro",
            bilanca=bilanca, rdg=rdg,
            novcani_tokovi=novcani_tokovi,
        )

    # ════════════════════════════════════════════════════
    # C6: INTRASTAT
    # ════════════════════════════════════════════════════

    def check_intrastat_obligation(self, primitak_ytd: float = 0,
                                    otprema_ytd: float = 0) -> Dict[str, Any]:
        return self.intrastat.check_obligation(primitak_ytd, otprema_ytd)

    def create_intrastat(self, client_id: str, godina: int, mjesec: int,
                          vrsta: str, stavke: List) -> Dict[str, Any]:
        client = self.registry.get(client_id)
        prijava = self.intrastat.create_prijava(
            godina, mjesec, vrsta, stavke,
            oib=client.oib if client else "",
            naziv=client.naziv if client else "",
        )
        return self.intrastat.to_dict(prijava)

    # ════════════════════════════════════════════════════
    # F3: FAKTURIRANJE USLUGA UREDA
    # ════════════════════════════════════════════════════

    def create_service_invoice(self, client_id: str,
                                broj_zaposlenih: int = 0,
                                extra_items: List = None) -> Dict[str, Any]:
        client = self.registry.get(client_id)
        if not client:
            return {"error": "Klijent nije pronađen"}
        racun = self.fakturiranje.create_monthly_invoice(
            client_id, client.naziv, client.oib,
            kategorija=client.kategorija,
            broj_zaposlenih=broj_zaposlenih,
            extra_items=extra_items,
        )
        return self.fakturiranje.to_dict(racun)

    # ════════════════════════════════════════════════════
    # G3: LIKVIDACIJA
    # ════════════════════════════════════════════════════

    def start_liquidation(self, client_id: str, datum_odluke: str,
                           likvidator: str) -> Dict[str, Any]:
        client = self.registry.get(client_id)
        if not client:
            return {"error": "Klijent nije pronađen"}
        status = self.likvidacija.start(
            client_id, client.naziv, client.oib, datum_odluke, likvidator
        )
        return self.likvidacija.to_dict(status)

    # ════════════════════════════════════════════════════
    # G: KPI DASHBOARD
    # ════════════════════════════════════════════════════

    def calculate_kpi(self, financial_data) -> Dict[str, Any]:
        """Izračunaj KPI pokazatelje za klijenta."""
        return self.kpi.calculate_all(financial_data)

    # ════════════════════════════════════════════════════
    # D: GFI PRIPREMA
    # ════════════════════════════════════════════════════

    def prepare_gfi(self, client_id: str, godina: int) -> Dict[str, Any]:
        """Pripremi GFI — checklist + struktura."""
        client = self.registry.get(client_id)
        return {
            "checklist": self.gfi.zakljucna_knjizenja_checklist(godina),
            "bilanca": self.gfi.bilanca_struktura(),
            "rdg": self.gfi.rdg_struktura(),
            "klijent": client.naziv if client else client_id,
        }

    # ════════════════════════════════════════════════════
    # APPROVAL & EXPORT
    # ════════════════════════════════════════════════════

    def approve(self, proposal_id: str, user_id: str) -> Dict[str, Any]:
        """Računovođa odobrava prijedlog."""
        if self._persistent:
            return self._persistent.approve(proposal_id, user_id)
        return self.pipeline.approve(proposal_id, user_id)

    def approve_batch(self, proposal_ids: List[str], user_id: str) -> List[Dict]:
        return [self.approve(pid, user_id) for pid in proposal_ids]

    def correct(self, proposal_id: str, user_id: str, corrections: Dict) -> Dict:
        if self._persistent:
            return self._persistent.correct(proposal_id, user_id, corrections)
        return self.pipeline.correct(proposal_id, user_id, corrections)

    def reject(self, proposal_id: str, user_id: str, reason: str = "") -> Dict:
        if self._persistent:
            return self._persistent.reject(proposal_id, user_id, reason)
        return self.pipeline.reject(proposal_id, user_id, reason)

    def export_to_erp(
        self, client_id: str, fmt: str = ""
    ) -> Dict[str, Any]:
        """
        KONAČNI EXPORT — šalje odobrena knjiženja u CPP ili Synesis.
        
        Automatski odabire format prema registru klijenata.
        """
        erp = self.get_client_erp(client_id)
        export_fmt = fmt or self.registry.get_export_format(client_id)
        if self._persistent:
            return self._persistent.export_approved(
                client_id=client_id, erp=erp, fmt=export_fmt,
            )
        return self.pipeline.export_approved(
            client_id=client_id, erp_target=erp, fmt=export_fmt,
        )

    # ════════════════════════════════════════════════════
    # ERP DVOSMJERNA KOMUNIKACIJA
    # ════════════════════════════════════════════════════

    def configure_erp(self, client_id: str, config: ERPConnectionConfig) -> Dict[str, Any]:
        """Konfiguriraj ERP konekciju za klijenta."""
        connector = ERPConnector(config)
        self._erp_connectors[client_id] = connector
        test = connector.test_connection()
        return {"client_id": client_id, "erp": config.erp_type,
                "method": config.method, "auto_book": config.auto_book,
                "test": test}

    def configure_erp_from_dict(self, client_id: str, cfg: Dict) -> Dict[str, Any]:
        """Konfiguriraj ERP iz config dict-a (iz config.json)."""
        config = ERPConnectionConfig(**cfg)
        return self.configure_erp(client_id, config)

    def get_erp_connector(self, client_id: str) -> Optional[ERPConnector]:
        """Dohvati konektor za klijenta."""
        return self._erp_connectors.get(client_id)

    def erp_pull_kontni_plan(self, client_id: str) -> List[Dict]:
        """Dohvati kontni plan iz ERP-a klijenta."""
        conn = self._erp_connectors.get(client_id)
        if not conn:
            return []
        return conn.pull_kontni_plan()

    def erp_pull_otvorene_stavke(self, client_id: str,
                                  konto: str = "", oib: str = "") -> List[Dict]:
        """Dohvati otvorene stavke iz ERP-a."""
        conn = self._erp_connectors.get(client_id)
        if not conn:
            return []
        return conn.pull_otvorene_stavke(konto, oib)

    def erp_pull_saldo(self, client_id: str, konto: str) -> Dict[str, Any]:
        """Dohvati saldo konta iz ERP-a."""
        conn = self._erp_connectors.get(client_id)
        if not conn:
            return {"konto": konto, "saldo": 0, "source": "no_connector"}
        return conn.pull_saldo_konta(konto)

    def erp_pull_bruto_bilanca(self, client_id: str, period: str = "") -> List[Dict]:
        """Dohvati bruto bilancu iz ERP-a."""
        conn = self._erp_connectors.get(client_id)
        if not conn:
            return []
        return conn.pull_bruto_bilanca(period)

    def erp_pull_partner_kartice(self, client_id: str, oib: str) -> List[Dict]:
        """Dohvati karticu partnera iz ERP-a."""
        conn = self._erp_connectors.get(client_id)
        if not conn:
            return []
        return conn.pull_partner_kartice(oib)

    def erp_scan_watch_folder(self, client_id: str) -> List[Dict]:
        """Skeniraj watch folder klijenta za nove dokumente."""
        conn = self._erp_connectors.get(client_id)
        if not conn:
            return []
        return conn.scan_watch_folder()

    def erp_push_auto(self, client_id: str, bookings: List[Dict],
                       confidence: float) -> Dict[str, Any]:
        """Autonomno knjiženje — BUDUĆA OPCIJA za kad sustav bude 100% testiran.

        PO DEFAULT-U ISKLJUČENO. Za aktivaciju potrebno:
        1. Računovođa eksplicitno uključi auto_book=True za klijenta
        2. Sustav mora biti potpuno testiran na tom klijentu (min. 6 mj.)
        3. Confidence >= 95% za svako knjiženje
        4. Iznos <= max_amount (default 50k EUR)
        5. OVERSEER provjera svake stavke
        6. Audit log SVAKOG autonomnog knjiženja
        7. Dnevni izvještaj računovođi o svim auto-knjiženjima
        """
        conn = self._erp_connectors.get(client_id)
        if not conn:
            return {"status": "error", "reason": "Nema ERP konektora za klijenta"}

        # OVERSEER provjera svake stavke
        for b in bookings:
            opis = b.get("opis", "")
            safety = self.overseer.evaluate(opis)
            if not safety["approved"]:
                return {"status": "blocked_overseer",
                        "reason": safety.get("message", "OVERSEER blokirao"),
                        "booking": opis}

        return conn.push_auto(bookings, client_id, confidence)

    def erp_get_audit_log(self, client_id: str) -> List[Dict]:
        """Audit log autonomnih knjiženja."""
        conn = self._erp_connectors.get(client_id)
        if not conn:
            return []
        return conn.get_audit_log()

    # ════════════════════════════════════════════════════
    # STATUS & PREGLED
    # ════════════════════════════════════════════════════

    def get_pending(self, client_id: str = "") -> List[Dict]:
        return self.pipeline.get_pending(client_id)

    def get_approved(self, client_id: str = "") -> List[Dict]:
        return self.pipeline.get_approved(client_id)

    def get_upcoming_deadlines(self, days: int = 14) -> List[Dict]:
        return self.deadlines.get_upcoming(days)

    def search_konto(self, keyword: str) -> List[Dict]:
        return suggest_konto_by_keyword(keyword)

    def get_system_status(self) -> Dict[str, Any]:
        """Kompletan status sustava."""
        return {
            "pipeline": self.pipeline.get_stats(),
            "clients": self.registry.get_stats(),
            "modules": {
                "payroll": self.payroll.get_stats(),
                "pdv": self.pdv.get_stats(),
                "joppd": self.joppd.get_stats(),
                "porez_dobit": self.porez_dobit.get_stats(),
                "porez_dohodak": self.porez_dohodak.get_stats(),
                "bolovanje": self.bolovanje.get_stats(),
                "drugi_dohodak": self.drugi_dohodak.get_stats(),
                "novcani_tokovi": self.novcani_tokovi.get_stats(),
                "gfi_xml": self.gfi_xml.get_stats(),
                "intrastat": self.intrastat.get_stats(),
                "kadrovska": self.kadrovska.get_stats(),
                "fakturiranje": self.fakturiranje.get_stats(),
                "likvidacija": self.likvidacija.get_stats(),
                "osnovna_sredstva": self.osnovna_sredstva.get_stats(),
                "deadlines": self.deadlines.get_stats(),
                "blagajna": self.blagajna.get_stats(),
                "putni_nalozi": self.putni_nalozi.get_stats(),
                "kpi": self.kpi.get_stats(),
                "erp_connectors": {
                    cid: c.get_stats() for cid, c in self._erp_connectors.items()
                },
            },
            "kontni_plan_konta": len(self.kontni_plan),
        }
