"""
Nyx Light — Module Executor

MOST IZMEĐU ROUTERA I STVARNIH MODULA.

Kad router detektira intent s confidence > 0.6, executor poziva
odgovarajući modul i vraća strukturirani rezultat.

Tok:
  1. Router: "bank_parser" (confidence: 0.85)
  2. Executor: BankStatementParser.parse(data) → rezultat
  3. Chat: LLM formatira rezultat u odgovor korisniku

Podržani moduli (svi 44):
  Grupa A: bank_parser, invoice_ocr, universal_parser, eracuni_parser, ios
  Grupa B: kontiranje, blagajna, putni_nalozi, osnovna_sredstva, ledger,
           fakturiranje, outgoing_invoice, kompenzacije, likvidacija, accruals,
           novcani_tokovi
  Grupa C: porez_dobit, porez_dohodak, pdv_prijava, payroll, joppd,
           drugi_dohodak, bolovanje
  Grupa D: peppol, fiskalizacija2, e_racun, intrastat
  Grupa E: gfi_xml, gfi_prep, reports, kpi, management_accounting,
           business_plan, audit
  Grupa F: network, vision_llm, rag, scalability, client_management,
           communication, kadrovska, deadlines, web_ui, place
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nyx_light.executor")


@dataclass
class ModuleResult:
    """Rezultat izvršenja modula."""
    success: bool
    module: str
    action: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    errors: List[str] = field(default_factory=list)
    llm_context: str = ""  # Kontekst za LLM da formatira odgovor


class ModuleExecutor:
    """
    Izvršava poslovne module na temelju router rezultata.

    Primjer:
        executor = ModuleExecutor(app=nyx_app)
        result = executor.execute("bank_parser", "parse",
                                  {"file_content": csv_data, "bank": "erste"})
        # → ModuleResult(success=True, data={transactions: [...]}, summary="12 transakcija")
    """

    def __init__(self, app=None, storage=None):
        """
        Args:
            app: NyxLightApp instanca (centralni orchestrator)
            storage: SQLiteStorage za pristup podacima
        """
        self.app = app
        self.storage = storage
        self._stats = {"total_executions": 0, "by_module": {}, "errors": 0}

    def execute(self, module: str, sub_intent: str = "",
                data: Dict[str, Any] = None, client_id: str = "",
                user_id: str = "") -> ModuleResult:
        """
        Izvrši modul i vrati strukturirani rezultat.

        Args:
            module: Ime modula (npr. "bank_parser", "kontiranje")
            sub_intent: Pod-intent (npr. "parse", "suggest", "validate")
            data: Ulazni podaci za modul
            client_id: ID klijenta
            user_id: ID korisnika

        Returns:
            ModuleResult sa podacima ili greškom
        """
        data = data or {}
        self._stats["total_executions"] += 1
        self._stats["by_module"][module] = self._stats["by_module"].get(module, 0) + 1

        # Dispatch to module handler
        handler = self._handlers.get(module)
        if not handler:
            return ModuleResult(
                success=False, module=module,
                summary=f"Modul '{module}' nema handler",
                errors=[f"Nepoznat modul: {module}"],
            )

        try:
            return handler(self, sub_intent, data, client_id, user_id)
        except Exception as e:
            self._stats["errors"] += 1
            logger.error("Modul %s greška: %s", module, e, exc_info=True)
            return ModuleResult(
                success=False, module=module,
                summary=f"Greška u modulu {module}: {str(e)}",
                errors=[str(e)],
            )

    # ═══════════════════════════════════════════
    # GRUPA A: Automatizacija visokog volumena
    # ═══════════════════════════════════════════

    def _handle_bank_parser(self, sub_intent, data, client_id, user_id):
        from nyx_light.modules.bank_parser.parser import BankStatementParser
        parser = BankStatementParser()

        if sub_intent in ("parse", "") and data.get("file_path"):
            result = parser.parse(data["file_path"], bank=data.get("bank", ""))
            count = len(result) if isinstance(result, list) else result.get("count", 0) if isinstance(result, dict) else 0
            return ModuleResult(
                success=True, module="bank_parser", action="parse",
                data={"transactions": result if isinstance(result, list) else [],
                      "count": count,
                      "bank": data.get("bank", "")},
                summary=f"Parsirano {count} transakcija ({data.get('bank', 'auto-detect')})",
                llm_context=f"Bankovni izvod parsiran: {count} transakcija, banka: {data.get('bank', '?')}",
            )
        return ModuleResult(
            success=False, module="bank_parser",
            summary="Za parsiranje izvoda potrebna je datoteka (CSV ili MT940)",
            llm_context="Korisnik želi parsirati bankovni izvod ali nije priložio datoteku.",
        )

    def _handle_invoice_ocr(self, sub_intent, data, client_id, user_id):
        from nyx_light.modules.invoice_ocr.extractor import InvoiceExtractor
        extractor = InvoiceExtractor()

        if data.get("file_path"):
            result = extractor.extract(file_path=data["file_path"])
            return ModuleResult(
                success=True, module="invoice_ocr", action="extract",
                data=result if isinstance(result, dict) else {"raw": str(result)},
                summary=f"Račun ekstrairan: OIB {result.get('oib', '?')}, "
                        f"iznos {result.get('ukupno', '?')} EUR",
                llm_context=f"OCR rezultat: {result}",
            )
        return ModuleResult(
            success=False, module="invoice_ocr",
            summary="Za čitanje računa potreban je sken (PDF, JPG, PNG). Priložite datoteku.",
            llm_context="Korisnik želi OCR računa ali nema priloženu datoteku.",
        )

    def _handle_universal_parser(self, sub_intent, data, client_id, user_id):
        from nyx_light.modules.universal_parser import UniversalInvoiceParser
        parser = UniversalInvoiceParser()
        content = data.get("file_content", b"")
        if content:
            if isinstance(content, str):
                content = content.encode("utf-8")
            result = parser.parse(content=content)
            rdict = result.to_dict() if hasattr(result, "to_dict") else (result if isinstance(result, dict) else {"raw": str(result)})
            return ModuleResult(
                success=True, module="universal_parser", action="parse",
                data=rdict,
                summary=f"Dokument parsiran",
                llm_context=f"Universal parser rezultat: {rdict}",
            )
        return ModuleResult(success=False, module="universal_parser",
                            summary="Priložite datoteku za parsiranje.")

    def _handle_eracuni_parser(self, sub_intent, data, client_id, user_id):
        from nyx_light.modules.eracuni_parser import ERacuniParser
        parser = ERacuniParser()
        xml = data.get("xml_content", data.get("xml", data.get("file_content", "")))
        if xml:
            content = xml if isinstance(xml, str) else xml.decode("utf-8", errors="replace")
            result = parser.parse_xml(content)
            return ModuleResult(
                success=True, module="eracuni_parser", action="parse",
                data={"invoices": result if isinstance(result, list) else [result]},
                summary=f"eRačun parsiran: {len(result) if isinstance(result, list) else 1} račun(a)",
                llm_context=f"eRačun XML parsiran: {len(result) if isinstance(result, list) else 1} stavki",
            )
        return ModuleResult(
            success=False, module="eracuni_parser",
            summary="Priložite XML datoteku eRačuna za parsiranje.",
        )

    def _handle_ios(self, sub_intent, data, client_id, user_id):
        from nyx_light.modules.ios_reconciliation.ios import IOSReconciliation
        ios = IOSReconciliation()

        if sub_intent == "generate":
            result = ios.generate(
                client_id=client_id,
                partner_oib=data.get("partner_oib", ""),
                datum=data.get("datum", ""),
                stavke=data.get("stavke", []),
            )
            return ModuleResult(
                success=True, module="ios", action="generate",
                data=result if isinstance(result, dict) else {"raw": str(result)},
                summary="IOS obrazac generiran",
                llm_context=f"IOS generiran za klijenta {client_id}",
            )
        return ModuleResult(
            success=True, module="ios", action="info",
            summary="IOS modul spreman. Za generiranje potrebni: partner OIB, datum, otvorene stavke.",
            llm_context="Korisnik pita o IOS-u. Modul je spreman za generiranje obrazaca.",
        )

    # ═══════════════════════════════════════════
    # GRUPA B: Kontiranje i financije
    # ═══════════════════════════════════════════

    def _handle_kontiranje(self, sub_intent, data, client_id, user_id):
        from nyx_light.modules.kontiranje.engine import KontiranjeEngine
        engine = KontiranjeEngine()

        if sub_intent in ("suggest", ""):
            desc = data.get("description", data.get("opis", ""))
            tip = data.get("document_type", data.get("tip", ""))
            if desc or tip:
                result = engine.suggest_konto(
                    description=desc,
                    tip_dokumenta=tip,
                    client_id=client_id,
                )
                rdict = result.to_dict() if hasattr(result, "to_dict") else (result if isinstance(result, dict) else {"suggestion": str(result)})
                return ModuleResult(
                    success=True, module="kontiranje", action="suggest",
                    data=rdict,
                    summary=f"Prijedlog kontiranja: {getattr(result, 'konto_duguje', rdict.get('konto_duguje', '?'))} / {getattr(result, 'konto_potrazuje', rdict.get('konto_potrazuje', '?'))}",
                    llm_context=f"Kontiranje prijedlog: {rdict}",
                )
        return ModuleResult(
            success=True, module="kontiranje", action="info",
            summary="Za prijedlog kontiranja potrebni: tip dokumenta, opis, iznos.",
            llm_context="Korisnik pita o kontiranju bez dovoljno podataka.",
        )

    def _handle_blagajna(self, sub_intent, data, client_id, user_id):
        from nyx_light.modules.blagajna.validator import BlagajnaValidator
        validator = BlagajnaValidator()

        if sub_intent in ("validate", "") and data.get("iznos"):
            try:
                iznos_val = float(str(data.get("iznos", 0)).replace(",", "."))
            except (ValueError, TypeError):
                iznos_val = 0.0
            result = validator.validate_transaction(
                iznos=iznos_val,
                partner_oib=data.get("partner_oib", data.get("oib", "")),
            )
            return ModuleResult(
                success=True, module="blagajna", action="validate",
                data=result if isinstance(result, dict) else {"raw": str(result)},
                summary=f"Blagajna validacija: {'OK' if result.get('valid', False) else 'UPOZORENJE'}",
                llm_context=f"Blagajna provjera: {result}",
            )
        return ModuleResult(
            success=True, module="blagajna", action="info",
            summary="Blagajna modul: provjera limita gotovine (10.000 EUR), PDV validacija, dnevni izvještaj.",
            llm_context="Korisnik pita o blagajni. Limit gotovine: 10.000 EUR.",
        )

    def _handle_putni_nalozi(self, sub_intent, data, client_id, user_id):
        from nyx_light.modules.putni_nalozi.checker import PutniNalogChecker
        checker = PutniNalogChecker()

        if sub_intent in ("calculate", "") and data.get("zemlja"):
            result = checker.get_dnevnica_info(zemlja=data.get("zemlja", "rh"))
            return ModuleResult(
                success=True, module="putni_nalozi", action="dnevnica_info",
                data=result if isinstance(result, dict) else {"raw": str(result)},
                summary=f"Dnevnica za {data.get('zemlja', 'RH')}: {result.get('puni_iznos', '?')} EUR",
                llm_context=f"Putni nalog dnevnica: {result}",
            )
        if sub_intent == "validate" and data.get("km"):
            # Fallback: basic km calculation
            km = data.get("km", 0)
            km_naknada = km * 0.40
            return ModuleResult(
                success=True, module="putni_nalozi", action="calculate",
                data={"km": km, "km_naknada_eur": km_naknada, "stopa": 0.40},
                summary=f"Putni nalog: {km} km × 0,40 EUR = {km_naknada:.2f} EUR",
                llm_context=f"Putni nalog: {km} km, naknada {km_naknada:.2f} EUR",
            )
        # List available countries
        zemlje = checker.list_zemlje()
        return ModuleResult(
            success=True, module="putni_nalozi", action="info",
            data={"stopa_km": 0.40, "zemlje_count": len(zemlje) if isinstance(zemlje, list) else 0},
            summary="Putni nalog: km-naknada 0,40 EUR/km (od 1.1.2025), dnevnice prema Pravilniku.",
            llm_context="Korisnik pita o putnim nalozima. Naknada: 0,40 EUR/km.",
        )

    def _handle_osnovna_sredstva(self, sub_intent, data, client_id, user_id):
        from nyx_light.modules.osnovna_sredstva import OsnovnaSredstvaEngine
        engine = OsnovnaSredstvaEngine()

        if data.get("nabavna_vrijednost") or data.get("naziv"):
            result = engine.calculate_depreciation(
                nabavna_vrijednost=data.get("nabavna_vrijednost", 0),
                skupina=data.get("skupina", ""),
                datum_nabave=data.get("datum_nabave", ""),
                naziv=data.get("naziv", ""),
            )
            return ModuleResult(
                success=True, module="osnovna_sredstva", action="calculate",
                data=result if isinstance(result, dict) else {"raw": str(result)},
                summary=f"Amortizacija: {result.get('godisnja_amortizacija', '?')} EUR/god",
                llm_context=f"OS izračun: {result}",
            )
        return ModuleResult(
            success=True, module="osnovna_sredstva", action="info",
            summary="Za izračun amortizacije potrebni: nabavna vrijednost, skupina, datum nabave.",
            llm_context="Korisnik pita o osnovnim sredstvima.",
        )

    def _handle_ledger(self, sub_intent, data, client_id, user_id):
        from nyx_light.modules.ledger import GeneralLedger
        engine = GeneralLedger()
        return ModuleResult(
            success=True, module="ledger", action="info",
            data={"available_reports": ["glavna_knjiga", "dnevnik", "analitika"]},
            summary="Ledger modul: glavna knjiga, dnevnik knjiženja, analitička kartica.",
            llm_context="Ledger modul dostupan za izvještaje.",
        )

    def _handle_fakturiranje(self, sub_intent, data, client_id, user_id):
        from nyx_light.modules.fakturiranje import FakturiranjeEngine
        engine = FakturiranjeEngine()

        if data.get("kupac_oib") or data.get("stavke"):
            result = engine.create_invoice(
                client_id=client_id,
                kupac_oib=data.get("kupac_oib", ""),
                stavke=data.get("stavke", []),
                datum=data.get("datum", ""),
            )
            return ModuleResult(
                success=True, module="fakturiranje", action="create",
                data=result if isinstance(result, dict) else {"raw": str(result)},
                summary=f"Faktura kreirana",
                llm_context=f"Izlazni račun: {result}",
            )
        return ModuleResult(
            success=True, module="fakturiranje", action="info",
            summary="Za kreiranje fakture potrebni: kupac OIB, stavke (opis, količina, cijena).",
            llm_context="Korisnik želi kreirati fakturu.",
        )

    def _handle_outgoing_invoice(self, sub_intent, data, client_id, user_id):
        from nyx_light.modules.outgoing_invoice import OutgoingInvoiceValidator
        validator = OutgoingInvoiceValidator()
        return ModuleResult(
            success=True, module="outgoing_invoice", action="info",
            summary="Modul za validaciju izlaznih računa. Provjera: PDV, R1/R2, fiskalizacija.",
            llm_context="Izlazni račun validator dostupan.",
        )

    def _handle_kompenzacije(self, sub_intent, data, client_id, user_id):
        from nyx_light.modules.kompenzacije import KompenzacijeEngine
        engine = KompenzacijeEngine()

        if data.get("stavke_a") and data.get("stavke_b"):
            result = engine.find_matches(data["stavke_a"], data["stavke_b"])
            return ModuleResult(
                success=True, module="kompenzacije", action="find",
                data=result if isinstance(result, dict) else {"raw": str(result)},
                summary=f"Kompenzacija: pronađeni parovi za prijeboj",
                llm_context=f"Kompenzacija rezultat: {result}",
            )
        return ModuleResult(
            success=True, module="kompenzacije", action="info",
            summary="Kompenzacija: jednostrana ili multilateralna. Potrebne otvorene stavke obje strane.",
            llm_context="Korisnik pita o kompenzacijama.",
        )

    def _handle_likvidacija(self, sub_intent, data, client_id, user_id):
        from nyx_light.modules.likvidacija import LikvidacijaEngine
        engine = LikvidacijaEngine()
        return ModuleResult(
            success=True, module="likvidacija", action="info",
            summary="Likvidatura: provjera ulaznih računa (formalna, računska, stručna kontrola).",
            llm_context="Likvidatura modul dostupan.",
        )

    def _handle_accruals(self, sub_intent, data, client_id, user_id):
        from nyx_light.modules.accruals import AccrualsChecklist
        checklist = AccrualsChecklist()
        result = checklist.get_checklist(period=data.get("period", "monthly"))
        return ModuleResult(
            success=True, module="accruals", action="checklist",
            data=result if isinstance(result, dict) else {"items": result},
            summary="Vremensko razgraničenje: PVR/AVR kontrolna lista.",
            llm_context=f"Accruals checklist: {result}",
        )

    def _handle_novcani_tokovi(self, sub_intent, data, client_id, user_id):
        from nyx_light.modules.novcani_tokovi import NovcanitTokoviEngine
        engine = NovcanitTokoviEngine()
        return ModuleResult(
            success=True, module="novcani_tokovi", action="info",
            summary="Cash flow izvještaj: direktna/indirektna metoda, projekcije novčanih tokova.",
            llm_context="Cash flow modul dostupan.",
        )

    # ═══════════════════════════════════════════
    # GRUPA C: Porezi i plaće
    # ═══════════════════════════════════════════

    def _handle_porez_dobit(self, sub_intent, data, client_id, user_id):
        from nyx_light.modules.porez_dobit import PorezNaDobitEngine
        engine = PorezNaDobitEngine()

        if data.get("prihod") or data.get("prihodi") or data.get("dobit"):
            result = engine.calculate(
                prihodi=float(data.get("prihodi", data.get("prihod", 0))),
                rashodi=float(data.get("rashodi", data.get("rashod", 0))),
                reprezentacija=float(data.get("nepriznati_rashodi", data.get("reprezentacija", 0))),
            )
            rdict = result.__dict__ if hasattr(result, "__dict__") else (result if isinstance(result, dict) else {"raw": str(result)})
            porez_iznos = getattr(result, "porez_za_uplatu", getattr(result, "porez", "?"))
            return ModuleResult(
                success=True, module="porez_dobit", action="calculate",
                data=rdict,
                summary=f"Porez na dobit: {porez_iznos} EUR",
                llm_context=f"Porez dobit: {rdict}",
            )
        return ModuleResult(
            success=True, module="porez_dobit", action="info",
            summary="Porez na dobit: 10% (prihod < 1M EUR), 18% (prihod ≥ 1M EUR). PD/PD-NN obrasci.",
            llm_context="Korisnik pita o porezu na dobit.",
        )

    def _handle_porez_dohodak(self, sub_intent, data, client_id, user_id):
        from nyx_light.modules.porez_dohodak import PorezDohodakEngine
        engine = PorezDohodakEngine()
        return ModuleResult(
            success=True, module="porez_dohodak", action="info",
            summary="Porez na dohodak: 20% (do 50.400 EUR), 30% (iznad). Osobni odbitak: 560 EUR.",
            llm_context="Porez dohodak: stope 20%/30%, OO 560 EUR.",
        )

    def _handle_pdv_prijava(self, sub_intent, data, client_id, user_id):
        from nyx_light.modules.pdv_prijava import PDVPrijavaEngine
        engine = PDVPrijavaEngine()

        if data.get("stavke"):
            result = engine.generate(stavke=data["stavke"], period=data.get("period", ""))
            return ModuleResult(
                success=True, module="pdv_prijava", action="generate",
                data=result if isinstance(result, dict) else {"raw": str(result)},
                summary=f"PDV prijava generirana za period {data.get('period', '?')}",
                llm_context=f"PDV obrazac: {result}",
            )
        return ModuleResult(
            success=True, module="pdv_prijava", action="info",
            summary="PDV prijava: PP-PDV obrazac, stope 25%/13%/5%, rok do 20. sljedećeg mjeseca.",
            llm_context="PDV modul. Stope: 25%, 13%, 5%.",
        )

    def _handle_payroll(self, sub_intent, data, client_id, user_id):
        from nyx_light.modules.payroll import PayrollEngine
        engine = PayrollEngine()
        return ModuleResult(
            success=True, module="payroll", action="info",
            summary="Obračun plaća: bruto→neto, doprinosi, porez, prirez. JOPPD generiranje.",
            llm_context="Payroll engine dostupan.",
        )

    def _handle_joppd(self, sub_intent, data, client_id, user_id):
        from nyx_light.modules.joppd import JOPPDGenerator
        generator = JOPPDGenerator()
        return ModuleResult(
            success=True, module="joppd", action="info",
            summary="JOPPD obrazac: XML za ePorezna. Automatsko popunjavanje iz obračuna plaća.",
            llm_context="JOPPD generator dostupan.",
        )

    def _handle_drugi_dohodak(self, sub_intent, data, client_id, user_id):
        from nyx_light.modules.drugi_dohodak import DrugiDohodakEngine
        engine = DrugiDohodakEngine()

        if data.get("bruto"):
            result = engine.calculate(
                bruto=data["bruto"],
                tip=data.get("tip", "ugovor_o_djelu"),
            )
            return ModuleResult(
                success=True, module="drugi_dohodak", action="calculate",
                data=result if isinstance(result, dict) else {"raw": str(result)},
                summary=f"Drugi dohodak obračun: neto {result.get('neto', '?')} EUR",
                llm_context=f"Drugi dohodak: {result}",
            )
        return ModuleResult(
            success=True, module="drugi_dohodak", action="info",
            summary="Drugi dohodak: ugovor o djelu, autorski honorar, doprinos 7,5% + porez 20%.",
            llm_context="Drugi dohodak modul.",
        )

    def _handle_bolovanje(self, sub_intent, data, client_id, user_id):
        from nyx_light.modules.bolovanje import BolovanjeEngine
        engine = BolovanjeEngine()
        return ModuleResult(
            success=True, module="bolovanje", action="info",
            summary="Bolovanje: HZZO obrasci, refundacija, obračun naknade (70%/100% bruto plaće).",
            llm_context="Bolovanje modul: 42 dana poslodavac, nakon toga HZZO.",
        )

    # ═══════════════════════════════════════════
    # GRUPA D: E-računi i fiskalizacija
    # ═══════════════════════════════════════════

    def _handle_peppol(self, sub_intent, data, client_id, user_id):
        from nyx_light.modules.peppol import PeppolIntegration
        processor = PeppolIntegration()
        return ModuleResult(
            success=True, module="peppol", action="info",
            data={"supported_formats": ["UBL 2.1", "CII", "ZUGFeRD", "FatturaPA"]},
            summary="Peppol: AS4 protokol, EN 16931, B2B/B2G e-računi.",
            llm_context="Peppol modul: UBL 2.1, CII, ZUGFeRD formati.",
        )

    def _handle_fiskalizacija2(self, sub_intent, data, client_id, user_id):
        from nyx_light.modules.fiskalizacija2 import Fiskalizacija2Engine
        engine = Fiskalizacija2Engine()
        return ModuleResult(
            success=True, module="fiskalizacija2", action="info",
            summary="Fiskalizacija 2.0: CIS komunikacija, QR kodovi, e-računi.",
            llm_context="Fiskalizacija 2.0 modul dostupan.",
        )

    def _handle_e_racun(self, sub_intent, data, client_id, user_id):
        from nyx_light.modules.e_racun import ERacunGenerator
        generator = ERacunGenerator()
        return ModuleResult(
            success=True, module="e_racun", action="info",
            summary="E-račun: generiranje, validacija, slanje. UBL 2.1 / CII format.",
            llm_context="E-račun generator dostupan.",
        )

    def _handle_intrastat(self, sub_intent, data, client_id, user_id):
        from nyx_light.modules.intrastat import IntrastatEngine
        engine = IntrastatEngine()

        if data.get("primitak_ytd") or data.get("otprema_ytd"):
            result = engine.check_obligation(
                primitak_ytd=data.get("primitak_ytd", 0),
                otprema_ytd=data.get("otprema_ytd", 0),
            )
            return ModuleResult(
                success=True, module="intrastat", action="check",
                data=result if isinstance(result, dict) else {"raw": str(result)},
                summary=f"Intrastat obveza: {result.get('obveznik', 'provjera')}",
                llm_context=f"Intrastat: {result}",
            )
        return ModuleResult(
            success=True, module="intrastat", action="info",
            summary="Intrastat: obveza izvještavanja DZS-u za EU robnu razmjenu. Prag: 400.000 EUR.",
            llm_context="Intrastat modul. Prag: 400k EUR.",
        )

    # ═══════════════════════════════════════════
    # GRUPA E: Izvještavanje i analitika
    # ═══════════════════════════════════════════

    def _handle_gfi_xml(self, sub_intent, data, client_id, user_id):
        from nyx_light.modules.gfi_xml import GFIXMLGenerator
        generator = GFIXMLGenerator()
        return ModuleResult(
            success=True, module="gfi_xml", action="info",
            summary="GFI: XML za FINA-u (bilanca, RDG, bilješke). Rok: 30.4. za prethodnu godinu.",
            llm_context="GFI XML generator dostupan.",
        )

    def _handle_gfi_prep(self, sub_intent, data, client_id, user_id):
        from nyx_light.modules.gfi_prep import GFIPrepEngine
        engine = GFIPrepEngine()
        return ModuleResult(
            success=True, module="gfi_prep", action="info",
            summary="GFI priprema: kontrola podataka prije generiranja XML-a.",
            llm_context="GFI prep modul.",
        )

    def _handle_reports(self, sub_intent, data, client_id, user_id):
        from nyx_light.modules.reports import ReportGenerator
        generator = ReportGenerator()
        return ModuleResult(
            success=True, module="reports", action="info",
            data={"available": ["bilanca", "rdg", "bruto_bilanca", "pdv_recap", "analitika"]},
            summary="Izvještaji: bilanca, RDG, bruto bilanca, PDV rekapitulacija, analitička kartica.",
            llm_context="Report generator s 5 vrsta izvještaja.",
        )

    def _handle_kpi(self, sub_intent, data, client_id, user_id):
        from nyx_light.modules.kpi import KPIDashboard
        dashboard = KPIDashboard()
        return ModuleResult(
            success=True, module="kpi", action="info",
            data={"metrics": ["likvidnost", "solventnost", "profitabilnost", "efikasnost"]},
            summary="KPI: likvidnost, solventnost, profitabilnost, efikasnost naplate.",
            llm_context="KPI dashboard dostupan.",
        )

    def _handle_management_accounting(self, sub_intent, data, client_id, user_id):
        from nyx_light.modules.management_accounting import ManagementAccounting
        engine = ManagementAccounting()
        return ModuleResult(
            success=True, module="management_accounting", action="info",
            summary="Upravljačko računovodstvo: troškovna mjesta, centri odgovornosti, budžet.",
            llm_context="Management accounting modul.",
        )

    def _handle_business_plan(self, sub_intent, data, client_id, user_id):
        from nyx_light.modules.business_plan import BusinessPlanGenerator
        engine = BusinessPlanGenerator()
        return ModuleResult(
            success=True, module="business_plan", action="info",
            summary="Poslovni plan: financijske projekcije, break-even analiza, cash flow plan.",
            llm_context="Business plan modul.",
        )

    def _handle_audit(self, sub_intent, data, client_id, user_id):
        from nyx_light.modules.audit import AuditTrail
        engine = AuditTrail()
        return ModuleResult(
            success=True, module="audit", action="info",
            summary="Revizijski trag: sve promjene, kontrolne točke, compliance provjere.",
            llm_context="Audit trail modul.",
        )

    # ═══════════════════════════════════════════
    # GRUPA F: Upravljanje i komunikacija
    # ═══════════════════════════════════════════

    def _handle_client_management(self, sub_intent, data, client_id, user_id):
        from nyx_light.modules.client_management import ClientOnboarding
        engine = ClientOnboarding()
        return ModuleResult(
            success=True, module="client_management", action="info",
            summary="Registar klijenata: OIB, kontakti, ERP postavke, aktivne usluge.",
            llm_context="Client management modul.",
        )

    def _handle_communication(self, sub_intent, data, client_id, user_id):
        from nyx_light.modules.communication import ReportExplainer
        engine = ReportExplainer()
        return ModuleResult(
            success=True, module="communication", action="info",
            summary="Komunikacija: email/SMS obavijesti, šablone poruka, automatski podsjetnici.",
            llm_context="Communication modul.",
        )

    def _handle_kadrovska(self, sub_intent, data, client_id, user_id):
        from nyx_light.modules.kadrovska import KadrovskaEvidencija
        engine = KadrovskaEvidencija()
        return ModuleResult(
            success=True, module="kadrovska", action="info",
            summary="Kadrovska evidencija: ugovori o radu, matični podaci, godišnji odmori.",
            llm_context="Kadrovska modul.",
        )

    def _handle_deadlines(self, sub_intent, data, client_id, user_id):
        from nyx_light.modules.deadlines import DeadlineTracker
        tracker = DeadlineTracker()
        result = tracker.get_upcoming(days_ahead=data.get("days", 30))
        return ModuleResult(
            success=True, module="deadlines", action="upcoming",
            data=result if isinstance(result, dict) else {"deadlines": result if isinstance(result, list) else []},
            summary=f"Rokovi: nadolazeći porezni i zakonski rokovi.",
            llm_context=f"Rokovi: {result}",
        )

    def _handle_place(self, sub_intent, data, client_id, user_id):
        from nyx_light.modules.place import PayrollCalculator, ObracunPlaceInput
        calc = PayrollCalculator()

        if data.get("bruto"):
            inp = ObracunPlaceInput(
                bruto=float(data["bruto"]),
                osobni_odbitak_faktor=float(data.get("osobni_odbitak_faktor", 1.0)),
                grad=data.get("grad", "zagreb"),
            )
            result = calc.obracun(inp)
            rdict = result.to_dict() if hasattr(result, "to_dict") else {"neto": getattr(result, "neto", 0)}
            return ModuleResult(
                success=True, module="place", action="calculate",
                data=rdict if isinstance(rdict, dict) else {"raw": str(rdict)},
                summary=f"Plaća: bruto {data['bruto']} → neto {getattr(result, 'neto', '?')} EUR",
                llm_context=f"Obračun plaće: bruto={data['bruto']}, neto={getattr(result, 'neto', '?')}",
            )
        return ModuleResult(
            success=True, module="place", action="info",
            summary="Obračun plaća: bruto→neto, doprinosi MIO 20%, ZO 16,5%, porez 20%/30%.",
            llm_context="Plaće modul. MIO 20%, ZO 16.5%.",
        )

    def _handle_rag(self, sub_intent, data, client_id, user_id):
        """RAG se obrađuje posebno u chat flow-u, ovo je fallback."""
        return ModuleResult(
            success=True, module="rag", action="search",
            summary="RAG pretraga zakona aktivna. Postavi pitanje o zakonu.",
            llm_context="RAG modul aktiviran — pretraga zakona RH.",
        )

    def _handle_vision_llm(self, sub_intent, data, client_id, user_id):
        from nyx_light.modules.vision_llm import VisionLLMClient
        processor = VisionLLMClient()
        return ModuleResult(
            success=True, module="vision_llm", action="info",
            summary="Vision AI: Qwen2.5-VL za čitanje skenova. Priložite sliku ili PDF.",
            llm_context="Vision LLM modul — čeka datoteku za OCR.",
        )

    def _handle_network(self, sub_intent, data, client_id, user_id):
        from nyx_light.modules.network import NetworkSetupGenerator
        manager = NetworkSetupGenerator()
        return ModuleResult(
            success=True, module="network", action="info",
            summary="Mrežni modul: mDNS (nyx-studio.local), Tailscale VPN, firewall.",
            llm_context="Network modul.",
        )

    def _handle_scalability(self, sub_intent, data, client_id, user_id):
        from nyx_light.modules.scalability import TaskQueue
        engine = TaskQueue()
        return ModuleResult(
            success=True, module="scalability", action="info",
            summary="Scalability: load balancing, queue management, resource monitoring.",
            llm_context="Scalability modul.",
        )

    def _handle_web_ui(self, sub_intent, data, client_id, user_id):
        return ModuleResult(
            success=True, module="web_ui", action="info",
            summary="Web UI: React dashboard, WebSocket chat, HITL workflow.",
            llm_context="Web UI modul.",
        )

    # ═══════════════════════════════════════════
    # GENERAL / FALLBACK
    # ═══════════════════════════════════════════

    def _handle_general(self, sub_intent, data, client_id, user_id):
        return ModuleResult(
            success=True, module="general", action="chat",
            summary="Općeniti razgovor — LLM odgovara slobodno.",
            llm_context="Nema specifičnog modula, koristi opće znanje.",
        )

    def _handle_export(self, sub_intent, data, client_id, user_id):
        from nyx_light.erp import ERPConnector
        return ModuleResult(
            success=True, module="export", action="info",
            summary="ERP Export: CPP XML, Synesis CSV, JSON. Izvoz odobrenih knjiženja.",
            llm_context="Export modul — CPP/Synesis formati.",
        )

    def _handle_amortizacija(self, sub_intent, data, client_id, user_id):
        result = self._handle_osnovna_sredstva(sub_intent, data, client_id, user_id)
        result.module = "amortizacija"  # Zadrži originalni module name
        return result

    # ═══════════════════════════════════════════
    # HANDLER REGISTRY
    # ═══════════════════════════════════════════

    _handlers = {
        # Grupa A
        "bank_parser": _handle_bank_parser,
        "invoice_ocr": _handle_invoice_ocr,
        "universal_parser": _handle_universal_parser,
        "eracuni_parser": _handle_eracuni_parser,
        "ios": _handle_ios,
        # Grupa B
        "kontiranje": _handle_kontiranje,
        "blagajna": _handle_blagajna,
        "putni_nalozi": _handle_putni_nalozi,
        "osnovna_sredstva": _handle_osnovna_sredstva,
        "ledger": _handle_ledger,
        "fakturiranje": _handle_fakturiranje,
        "outgoing_invoice": _handle_outgoing_invoice,
        "kompenzacije": _handle_kompenzacije,
        "likvidacija": _handle_likvidacija,
        "accruals": _handle_accruals,
        "novcani_tokovi": _handle_novcani_tokovi,
        # Grupa C
        "porez_dobit": _handle_porez_dobit,
        "porez_dohodak": _handle_porez_dohodak,
        "pdv_prijava": _handle_pdv_prijava,
        "payroll": _handle_payroll,
        "joppd": _handle_joppd,
        "drugi_dohodak": _handle_drugi_dohodak,
        "bolovanje": _handle_bolovanje,
        "place": _handle_place,
        # Grupa D
        "peppol": _handle_peppol,
        "fiskalizacija2": _handle_fiskalizacija2,
        "e_racun": _handle_e_racun,
        "intrastat": _handle_intrastat,
        # Grupa E
        "gfi_xml": _handle_gfi_xml,
        "gfi_prep": _handle_gfi_prep,
        "reports": _handle_reports,
        "kpi": _handle_kpi,
        "management_accounting": _handle_management_accounting,
        "business_plan": _handle_business_plan,
        "audit": _handle_audit,
        # Grupa F
        "client_management": _handle_client_management,
        "communication": _handle_communication,
        "kadrovska": _handle_kadrovska,
        "deadlines": _handle_deadlines,
        "network": _handle_network,
        "vision_llm": _handle_vision_llm,
        "rag": _handle_rag,
        "scalability": _handle_scalability,
        "web_ui": _handle_web_ui,
        # Aliasi
        "amortizacija": _handle_amortizacija,
        "export": _handle_export,
        "general": _handle_general,
    }

    def get_stats(self) -> Dict[str, Any]:
        return {**self._stats}

    def get_available_modules(self) -> List[str]:
        return sorted(self._handlers.keys())
