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
from nyx_light.registry import ClientRegistry, ClientConfig

# Moduli — Grupa A
from nyx_light.modules.invoice_ocr.extractor import InvoiceExtractor
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

# Moduli — Grupa G
from nyx_light.modules.kpi import KPIDashboard

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

        # ── Grupa A — Obrada dokumentacije ──
        self.invoice_ocr = InvoiceExtractor()          # A1
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

        # ── Grupa B+ — Bolovanje ──
        self.bolovanje = BolovanjeEngine()

        # ── Grupa G — KPI ──
        self.kpi = KPIDashboard()

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
        
        Vraća prijedlog koji čeka odobrenje.
        """
        erp = self.get_client_erp(client_id)

        # Kontiranje
        konto_result = {"suggested_konto": "7800", "confidence": 0.3}
        if auto_kontiranje:
            desc = invoice_data.get("opis", "") or invoice_data.get("dobavljac", "")
            konto_result = self.kontiranje.suggest_konto(desc)

        # Pipeline
        proposal = self.pipeline.from_invoice(invoice_data, konto_result, client_id, erp)
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
        erp = self.get_client_erp(client_id)

        # Parse
        if bank.lower() in ("mt940",):
            transactions = self.bank_parser.parse_mt940(content)
        else:
            transactions = self.bank_parser.parse_csv(content, bank)

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
                "osnovna_sredstva": self.osnovna_sredstva.get_stats(),
                "deadlines": self.deadlines.get_stats(),
                "blagajna": self.blagajna.get_stats(),
                "putni_nalozi": self.putni_nalozi.get_stats(),
                "kpi": self.kpi.get_stats(),
            },
            "kontni_plan_konta": len(self.kontni_plan),
        }
