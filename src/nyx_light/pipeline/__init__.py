"""
Nyx Light — Unified Booking Pipeline (Kostur sustava)

Ovo je CENTRALNI KOSTUR koji povezuje SVE module s CPP/Synesis izvozom.

Tok podataka:
  1. ULAZ (Invoice OCR, Banka, Blagajna, Plaća, Putni nalog...)
     ↓
  2. AI OBRADA (Kontiranje, Validacija, Memory lookup)
     ↓
  3. PRIJEDLOG KNJIŽENJA (pending → čeka odobrenje)
     ↓
  4. HUMAN APPROVAL (računovođa klikne Odobri/Ispravi/Odbij)
     ↓
  5. EXPORT (CPP XML ili Synesis CSV/JSON)
     ↓
  6. OZNAČI KAO IZVEZENO (audit trail)

Svaki modul generira BookingProposal → Pipeline → Approval → Export.
NIKADA se ne preskače korak 4 (Human-in-the-Loop).
"""

import json
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nyx_light.pipeline")


# ════════════════════════════════════════════════════════
# Tipovi
# ════════════════════════════════════════════════════════

class BookingStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    CORRECTED = "corrected"
    REJECTED = "rejected"
    EXPORTED = "exported"
    ERROR = "error"


class DocumentType(Enum):
    ULAZNI_RACUN = "ulazni_racun"          # A1
    IZLAZNI_RACUN = "izlazni_racun"        # A2
    BANKOVNI_IZVOD = "bankovni_izvod"      # A4
    BLAGAJNA = "blagajna"                  # A5
    PUTNI_NALOG = "putni_nalog"            # A6
    OSNOVNO_SREDSTVO = "osnovno_sredstvo"  # A7
    OBRACUNSKA_STAVKA = "obracunska"       # A8
    IOS = "ios"                            # A9
    PLACA = "placa"                        # B
    UGOVOR_O_DJELU = "ugovor_o_djelu"     # B
    AUTORSKI_HONORAR = "autorski_honorar"  # B
    PDV_OBRACUN = "pdv_obracun"           # C
    AMORTIZACIJA = "amortizacija"          # D
    RAZGRANICENJE = "razgranicenje"        # D
    OSTALO = "ostalo"


class ERPTarget(Enum):
    CPP = "CPP"
    SYNESIS = "Synesis"
    E_RACUNI = "eRacuni"
    PANTHEON = "Pantheon"


@dataclass
class BookingLine:
    """Jedna stavka knjiženja (jedno duguje/potražuje)."""
    konto: str
    strana: str           # "duguje" ili "potrazuje"
    iznos: float
    opis: str = ""
    oib: str = ""
    pdv_stopa: float = 0.0
    pdv_iznos: float = 0.0
    poziv_na_broj: str = ""
    partner_naziv: str = ""


@dataclass
class BookingProposal:
    """
    Prijedlog knjiženja generiran od bilo kojeg modula.
    Ovo je STANDARDNI FORMAT koji svi moduli moraju proizvesti.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    client_id: str = ""
    document_type: str = "ostalo"
    erp_target: str = "CPP"

    # Stavke knjiženja (duguje/potražuje parovi)
    lines: List[Dict] = field(default_factory=list)

    # Metapodaci dokumenta
    datum_dokumenta: str = ""
    datum_knjizenja: str = ""
    broj_dokumenta: str = ""
    opis: str = ""
    oib_partnera: str = ""
    naziv_partnera: str = ""
    ukupni_iznos: float = 0.0
    valuta: str = "EUR"

    # PDV
    pdv_stopa: float = 0.0
    osnovica: float = 0.0
    pdv_iznos: float = 0.0

    # AI metapodaci
    confidence: float = 0.0
    ai_reasoning: str = ""
    source_module: str = ""

    # Status
    status: str = "pending"
    warnings: List[str] = field(default_factory=list)

    # Timestamps
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ExportBatch:
    """Batch za export u ERP."""
    batch_id: str = field(default_factory=lambda: f"BATCH-{int(time.time())}")
    client_id: str = ""
    erp_target: str = "CPP"
    proposals: List[BookingProposal] = field(default_factory=list)
    period: str = ""
    exported_at: str = ""
    export_file: str = ""


# ════════════════════════════════════════════════════════
# Pipeline
# ════════════════════════════════════════════════════════

class BookingPipeline:
    """
    Centralni pipeline: Modul → Prijedlog → Odobrenje → Export.
    
    Ovo je KOSTUR CIJELOG SUSTAVA.
    Svaki modul (Banka, Računi, Plaće...) šalje BookingProposal ovdje.
    Pipeline ga sprema, čeka odobrenje, pa exporta u CPP/Synesis.
    """

    def __init__(self, storage=None, exporter=None):
        self._pending: Dict[str, BookingProposal] = {}
        self._approved: Dict[str, BookingProposal] = {}
        self._exported: List[str] = []
        self._rejected: List[str] = []
        self._storage = storage
        self._exporter = exporter
        self._stats = {
            "received": 0, "approved": 0, "rejected": 0,
            "corrected": 0, "exported": 0, "errors": 0,
        }
        logger.info("BookingPipeline inicijaliziran")

    # ── 1. PRIMI PRIJEDLOG ──

    def submit(self, proposal: BookingProposal) -> Dict[str, Any]:
        """
        Primi prijedlog knjiženja od modula.
        Sprema ga kao 'pending' i čeka odobrenje.
        """
        proposal.status = BookingStatus.PENDING.value
        if not proposal.datum_knjizenja:
            proposal.datum_knjizenja = datetime.now().strftime("%Y-%m-%d")

        self._pending[proposal.id] = proposal
        self._stats["received"] += 1

        # Spremi u SQLite ako je dostupan
        if self._storage:
            self._persist_proposal(proposal)

        logger.info(
            "Pipeline: primljen %s (%s, %.2f EUR, confidence=%.0f%%)",
            proposal.id, proposal.document_type,
            proposal.ukupni_iznos, proposal.confidence * 100,
        )

        return {
            "id": proposal.id,
            "status": "pending",
            "document_type": proposal.document_type,
            "iznos": proposal.ukupni_iznos,
            "confidence": proposal.confidence,
            "warnings": proposal.warnings,
            "requires_approval": True,
            "message": "Prijedlog spreman za odobrenje računovođe",
        }

    def submit_batch(self, proposals: List[BookingProposal]) -> Dict[str, Any]:
        """Primi više prijedloga odjednom (npr. bankovni izvod)."""
        results = []
        for p in proposals:
            results.append(self.submit(p))
        return {
            "batch_size": len(proposals),
            "submitted": len(results),
            "ids": [r["id"] for r in results],
        }

    # ── 2. ODOBRENJE / ISPRAVAK / ODBIJANJE ──

    def approve(self, proposal_id: str, user_id: str) -> Dict[str, Any]:
        """Računovođa odobrava knjiženje."""
        if proposal_id not in self._pending:
            return {"error": f"Prijedlog {proposal_id} nije u pending statusu"}

        proposal = self._pending.pop(proposal_id)
        proposal.status = BookingStatus.APPROVED.value
        self._approved[proposal_id] = proposal
        self._stats["approved"] += 1

        if self._storage:
            self._update_status(proposal_id, "approved", user_id)

        return {
            "id": proposal_id,
            "status": "approved",
            "approved_by": user_id,
            "ready_for_export": True,
        }

    def correct(
        self,
        proposal_id: str,
        user_id: str,
        corrections: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Računovođa ispravlja prijedlog (koristi se za L2 memoriju + DPO)."""
        if proposal_id not in self._pending:
            return {"error": f"Prijedlog {proposal_id} nije u pending statusu"}

        proposal = self._pending.pop(proposal_id)
        original = {
            "lines": proposal.lines.copy(),
            "opis": proposal.opis,
        }

        # Primijeni ispravke
        for key, value in corrections.items():
            if hasattr(proposal, key):
                setattr(proposal, key, value)

        proposal.status = BookingStatus.CORRECTED.value
        self._approved[proposal_id] = proposal
        self._stats["corrected"] += 1

        # Spremi correction za DPO training
        correction_record = {
            "proposal_id": proposal_id,
            "user_id": user_id,
            "original": original,
            "corrected": corrections,
            "document_type": proposal.document_type,
            "client_id": proposal.client_id,
            "timestamp": datetime.now().isoformat(),
        }

        if self._storage:
            self._update_status(proposal_id, "corrected", user_id)

        return {
            "id": proposal_id,
            "status": "corrected",
            "corrected_by": user_id,
            "correction_record": correction_record,
            "ready_for_export": True,
            "note": "Ispravak spremljen za DPO noćni trening",
        }

    def reject(self, proposal_id: str, user_id: str, reason: str = "") -> Dict[str, Any]:
        """Računovođa odbija knjiženje."""
        if proposal_id not in self._pending:
            return {"error": f"Prijedlog {proposal_id} nije u pending statusu"}

        proposal = self._pending.pop(proposal_id)
        proposal.status = BookingStatus.REJECTED.value
        self._rejected.append(proposal_id)
        self._stats["rejected"] += 1

        return {
            "id": proposal_id,
            "status": "rejected",
            "rejected_by": user_id,
            "reason": reason,
        }

    # ── 3. EXPORT U ERP ──

    def export_approved(
        self,
        client_id: str = "",
        erp_target: str = "",
        fmt: str = "XML",
    ) -> Dict[str, Any]:
        """
        Exportaj sva odobrena knjiženja u CPP ili Synesis.
        Ovo je KONAČNI KORAK — podaci idu u ERP.
        """
        # Filtriraj odobrena po klijentu
        to_export = []
        for pid, proposal in list(self._approved.items()):
            if client_id and proposal.client_id != client_id:
                continue
            if erp_target and proposal.erp_target != erp_target:
                continue
            to_export.append(proposal)

        if not to_export:
            return {"status": "empty", "message": "Nema odobrenih knjiženja za export"}

        # Pretvori u format za ERPExporter
        erp = erp_target or to_export[0].erp_target or "CPP"
        cid = client_id or to_export[0].client_id

        bookings = []
        for p in to_export:
            if p.lines:
                # Multi-line booking
                for line in p.lines:
                    bookings.append({
                        "konto_duguje": line.get("konto", "") if line.get("strana") == "duguje" else "",
                        "konto_potrazuje": line.get("konto", "") if line.get("strana") == "potrazuje" else "",
                        "iznos": line.get("iznos", 0),
                        "opis": line.get("opis", p.opis),
                        "datum_dokumenta": p.datum_dokumenta,
                        "datum_knjizenja": p.datum_knjizenja,
                        "oib": line.get("oib", p.oib_partnera),
                        "pdv_stopa": line.get("pdv_stopa", p.pdv_stopa),
                        "pdv_iznos": line.get("pdv_iznos", p.pdv_iznos),
                        "poziv_na_broj": line.get("poziv_na_broj", ""),
                        "document_type": p.document_type,
                        "broj_dokumenta": p.broj_dokumenta,
                    })
            else:
                # Single-line fallback
                bookings.append({
                    "konto_duguje": "",
                    "konto_potrazuje": "",
                    "iznos": p.ukupni_iznos,
                    "opis": p.opis,
                    "datum_dokumenta": p.datum_dokumenta,
                    "datum_knjizenja": p.datum_knjizenja,
                    "oib": p.oib_partnera,
                    "pdv_stopa": p.pdv_stopa,
                    "pdv_iznos": p.pdv_iznos,
                    "document_type": p.document_type,
                })

        # Export
        result = {"status": "ready", "erp": erp, "records": len(bookings)}

        if self._exporter:
            result = self._exporter.export(bookings, cid, erp, fmt)

        # Označi kao izvezeno
        for p in to_export:
            p.status = BookingStatus.EXPORTED.value
            self._exported.append(p.id)
            del self._approved[p.id]

        self._stats["exported"] += len(to_export)
        result["proposals_exported"] = len(to_export)
        result["booking_lines"] = len(bookings)

        logger.info(
            "Pipeline EXPORT: %d prijedloga → %d stavki → %s %s",
            len(to_export), len(bookings), erp, fmt,
        )

        return result

    # ── 4. MODUL-SPECIFIČNE PRETVORBE ──

    def from_invoice(self, invoice_data: Dict, kontiranje_result: Dict,
                     client_id: str, erp: str = "CPP") -> BookingProposal:
        """Pretvori ulazni račun (A1) u BookingProposal."""
        iznos = invoice_data.get("iznos", 0)
        pdv = invoice_data.get("pdv_iznos", 0)
        osnovica = iznos - pdv if pdv else iznos

        return BookingProposal(
            client_id=client_id,
            document_type=DocumentType.ULAZNI_RACUN.value,
            erp_target=erp,
            lines=[
                {"konto": kontiranje_result.get("suggested_konto", "7800"),
                 "strana": "duguje", "iznos": osnovica,
                 "opis": invoice_data.get("opis", "Ulazni račun")},
                {"konto": "1230", "strana": "duguje", "iznos": pdv,
                 "opis": "Pretporez"},
                {"konto": "4000", "strana": "potrazuje", "iznos": iznos,
                 "opis": f"Obveza dobavljaču: {invoice_data.get('dobavljac', '')}"},
            ],
            datum_dokumenta=invoice_data.get("datum", ""),
            broj_dokumenta=invoice_data.get("broj_racuna", ""),
            opis=f"UR {invoice_data.get('broj_racuna', '')} — {invoice_data.get('dobavljac', '')}",
            oib_partnera=invoice_data.get("oib", ""),
            naziv_partnera=invoice_data.get("dobavljac", ""),
            ukupni_iznos=iznos,
            pdv_stopa=invoice_data.get("pdv_stopa", 25),
            osnovica=osnovica,
            pdv_iznos=pdv,
            confidence=kontiranje_result.get("confidence", 0),
            ai_reasoning=kontiranje_result.get("reasoning", ""),
            source_module="invoice_ocr + kontiranje",
        )

    def from_bank_statement(self, transactions: List[Dict],
                            client_id: str, erp: str = "CPP") -> List[BookingProposal]:
        """Pretvori bankovni izvod (A4) u listu BookingProposal-a."""
        proposals = []
        for tx in transactions:
            direction = tx.get("direction", "out")  # in/out
            iznos = abs(tx.get("amount", 0))

            if direction == "in":
                lines = [
                    {"konto": "1500", "strana": "duguje", "iznos": iznos,
                     "opis": "Uplata na žiro"},
                    {"konto": tx.get("suggested_konto", "1200"), "strana": "potrazuje",
                     "iznos": iznos, "opis": tx.get("opis", "Naplata")},
                ]
            else:
                lines = [
                    {"konto": tx.get("suggested_konto", "4000"), "strana": "duguje",
                     "iznos": iznos, "opis": tx.get("opis", "Plaćanje")},
                    {"konto": "1500", "strana": "potrazuje", "iznos": iznos,
                     "opis": "Isplata s žiro"},
                ]

            proposals.append(BookingProposal(
                client_id=client_id,
                document_type=DocumentType.BANKOVNI_IZVOD.value,
                erp_target=erp,
                lines=lines,
                datum_dokumenta=tx.get("date", ""),
                opis=tx.get("opis", ""),
                oib_partnera=tx.get("oib", ""),
                naziv_partnera=tx.get("partner", ""),
                ukupni_iznos=iznos,
                confidence=tx.get("confidence", 0.5),
                source_module="bank_parser",
            ))
        return proposals

    def from_payroll(self, payroll_result, client_id: str,
                     erp: str = "CPP") -> BookingProposal:
        """Pretvori obračun plaće (B) u BookingProposal."""
        r = payroll_result
        bruto = r.bruto_placa

        lines = [
            # Trošak plaće (duguje)
            {"konto": "5200", "strana": "duguje", "iznos": bruto,
             "opis": f"Bruto plaća: {r.employee_name}"},
            # Neto za isplatu (potražuje)
            {"konto": "4200", "strana": "potrazuje", "iznos": r.neto_placa,
             "opis": f"Neto plaća: {r.employee_name}"},
            # MIO I. stup
            {"konto": "4210", "strana": "potrazuje", "iznos": r.mio_stup_1,
             "opis": "MIO I. stup (15%)"},
            # MIO II. stup
            {"konto": "4211", "strana": "potrazuje", "iznos": r.mio_stup_2,
             "opis": "MIO II. stup (5%)"},
            # Porez na dohodak
            {"konto": "4220", "strana": "potrazuje", "iznos": r.porez,
             "opis": "Porez na dohodak"},
            # Prirez
            {"konto": "4221", "strana": "potrazuje", "iznos": r.prirez,
             "opis": "Prirez"},
            # Zdravstveno (NA plaću — teret poslodavca)
            {"konto": "5210", "strana": "duguje", "iznos": r.zdravstveno,
             "opis": "Doprinos za zdravstveno (16.5%)"},
            {"konto": "4230", "strana": "potrazuje", "iznos": r.zdravstveno,
             "opis": "Obveza za zdravstveno"},
        ]

        # Filtriraj nulte iznose
        lines = [l for l in lines if l["iznos"] > 0]

        return BookingProposal(
            client_id=client_id,
            document_type=DocumentType.PLACA.value,
            erp_target=erp,
            lines=lines,
            opis=f"Plaća {r.employee_name} — bruto {bruto:.2f} → neto {r.neto_placa:.2f}",
            ukupni_iznos=r.ukupni_trosak_poslodavca,
            confidence=0.95,
            ai_reasoning="Obračun prema Zakonu o doprinosima i Zakonu o porezu na dohodak",
            source_module="payroll",
            warnings=r.warnings,
        )

    def from_petty_cash(self, blagajna_tx: Dict, kontiranje: Dict,
                        client_id: str, erp: str = "CPP") -> BookingProposal:
        """Pretvori blagajničku stavku (A5) u BookingProposal."""
        iznos = blagajna_tx.get("iznos", 0)
        vrsta = blagajna_tx.get("vrsta", "isplata")  # uplata/isplata

        if vrsta == "isplata":
            lines = [
                {"konto": kontiranje.get("suggested_konto", "7800"),
                 "strana": "duguje", "iznos": iznos, "opis": blagajna_tx.get("opis", "")},
                {"konto": "1400", "strana": "potrazuje", "iznos": iznos,
                 "opis": "Blagajna — isplata"},
            ]
        else:
            lines = [
                {"konto": "1400", "strana": "duguje", "iznos": iznos,
                 "opis": "Blagajna — uplata"},
                {"konto": kontiranje.get("suggested_konto", "6600"),
                 "strana": "potrazuje", "iznos": iznos, "opis": blagajna_tx.get("opis", "")},
            ]

        warnings = []
        if iznos > 10_000:
            warnings.append("⚠️ LIMIT: Gotovinski promet > 10.000 EUR!")

        return BookingProposal(
            client_id=client_id,
            document_type=DocumentType.BLAGAJNA.value,
            erp_target=erp,
            lines=lines,
            opis=blagajna_tx.get("opis", ""),
            ukupni_iznos=iznos,
            confidence=kontiranje.get("confidence", 0.5),
            source_module="blagajna",
            warnings=warnings,
        )

    def from_travel_expense(self, putni_nalog: Dict,
                            client_id: str, erp: str = "CPP") -> BookingProposal:
        """Pretvori putni nalog (A6) u BookingProposal."""
        km = putni_nalog.get("km", 0)
        km_naknada = round(km * 0.30, 2)
        dnevnica = putni_nalog.get("dnevnica", 0)
        ostali_troskovi = putni_nalog.get("ostali_troskovi", 0)
        ukupno = km_naknada + dnevnica + ostali_troskovi

        lines = []
        if km_naknada > 0:
            lines.append({"konto": "5420", "strana": "duguje", "iznos": km_naknada,
                          "opis": f"Km naknada: {km} km × 0,30 EUR"})
        if dnevnica > 0:
            lines.append({"konto": "5410", "strana": "duguje", "iznos": dnevnica,
                          "opis": "Dnevnica"})
        if ostali_troskovi > 0:
            lines.append({"konto": "5440", "strana": "duguje", "iznos": ostali_troskovi,
                          "opis": "Ostali troškovi služb. puta"})
        lines.append({"konto": "4200", "strana": "potrazuje", "iznos": ukupno,
                       "opis": f"Obveza za putni nalog: {putni_nalog.get('djelatnik', '')}"})

        return BookingProposal(
            client_id=client_id,
            document_type=DocumentType.PUTNI_NALOG.value,
            erp_target=erp,
            lines=lines,
            opis=f"Putni nalog: {putni_nalog.get('djelatnik', '')} — {putni_nalog.get('odrediste', '')}",
            ukupni_iznos=ukupno,
            confidence=0.85,
            source_module="putni_nalozi",
        )

    def from_depreciation(self, asset_name: str, monthly_amount: float,
                          client_id: str, erp: str = "CPP") -> BookingProposal:
        """Pretvori amortizaciju (A7/A8) u BookingProposal."""
        return BookingProposal(
            client_id=client_id,
            document_type=DocumentType.AMORTIZACIJA.value,
            erp_target=erp,
            lines=[
                {"konto": "5300", "strana": "duguje", "iznos": monthly_amount,
                 "opis": f"Amortizacija: {asset_name}"},
                {"konto": "0290", "strana": "potrazuje", "iznos": monthly_amount,
                 "opis": f"Ispravak vrijednosti: {asset_name}"},
            ],
            opis=f"Mjesečna amortizacija: {asset_name}",
            ukupni_iznos=monthly_amount,
            confidence=0.99,
            source_module="osnovna_sredstva",
        )

    def from_ios(self, ios_data: Dict, client_id: str,
                 erp: str = "CPP") -> BookingProposal:
        """Pretvori IOS razliku (A9) u BookingProposal."""
        razlika = ios_data.get("razlika", 0)
        partner = ios_data.get("partner", "")

        if razlika > 0:
            lines = [
                {"konto": "1200", "strana": "duguje", "iznos": abs(razlika),
                 "opis": f"IOS korekcija — potraživanje od {partner}"},
                {"konto": "6300", "strana": "potrazuje", "iznos": abs(razlika),
                 "opis": "Prihod od IOS usklađivanja"},
            ]
        else:
            lines = [
                {"konto": "7800", "strana": "duguje", "iznos": abs(razlika),
                 "opis": f"IOS korekcija — rashod za {partner}"},
                {"konto": "4000", "strana": "potrazuje", "iznos": abs(razlika),
                 "opis": "Obveza iz IOS usklađivanja"},
            ]

        return BookingProposal(
            client_id=client_id,
            document_type=DocumentType.IOS.value,
            erp_target=erp,
            lines=lines,
            opis=f"IOS usklađivanje: {partner}",
            oib_partnera=ios_data.get("oib", ""),
            naziv_partnera=partner,
            ukupni_iznos=abs(razlika),
            confidence=0.7,
            source_module="ios_reconciliation",
        )

    # ── HELPERS ──

    def get_pending(self, client_id: str = "") -> List[Dict]:
        """Dohvati sve pending prijedloge."""
        result = []
        for pid, p in self._pending.items():
            if client_id and p.client_id != client_id:
                continue
            result.append({
                "id": p.id, "document_type": p.document_type,
                "iznos": p.ukupni_iznos, "opis": p.opis,
                "confidence": p.confidence, "warnings": p.warnings,
                "erp_target": p.erp_target, "source": p.source_module,
            })
        return result

    def get_approved(self, client_id: str = "") -> List[Dict]:
        """Dohvati sva odobrena knjiženja (spremna za export)."""
        result = []
        for pid, p in self._approved.items():
            if client_id and p.client_id != client_id:
                continue
            result.append({
                "id": p.id, "document_type": p.document_type,
                "iznos": p.ukupni_iznos, "lines": len(p.lines),
                "erp_target": p.erp_target,
            })
        return result

    def get_stats(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "pending": len(self._pending),
            "approved_waiting": len(self._approved),
            "exported_total": len(self._exported),
        }

    def _persist_proposal(self, proposal: BookingProposal):
        """Spremi u SQLite (ako storage postoji)."""
        pass  # Implementirano u SQLiteStorage

    def _update_status(self, proposal_id: str, status: str, user_id: str):
        """Ažuriraj status u SQLite."""
        pass
