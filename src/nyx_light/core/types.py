"""Shared types for Nyx Light."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class ApprovalStatus(Enum):
    """Status odobrenja knjiženja."""
    PENDING = "pending"          # Čeka odobrenje
    APPROVED = "approved"        # Odobreno od računovođe
    REJECTED = "rejected"        # Odbijeno
    AUTO_APPROVED = "auto"       # Auto-odobreno (nisko-rizično)


class ClientERP(Enum):
    """ERP sustav klijenta."""
    CPP = "cpp"
    SYNESIS = "synesis"
    CUSTOM = "custom"


class DocumentType(Enum):
    """Tip dokumenta."""
    INVOICE_IN = "ulazni_racun"
    INVOICE_OUT = "izlazni_racun"
    BANK_STATEMENT = "bankovni_izvod"
    CASH_REPORT = "blagajna"
    TRAVEL_ORDER = "putni_nalog"
    IOS_FORM = "ios_obrazac"
    TAX_FORM = "porezni_obrazac"


@dataclass
class BookingProposal:
    """Prijedlog knjiženja od AI sustava."""
    id: str
    document_type: DocumentType
    client_id: str
    client_name: str
    konto_duguje: str
    konto_potrazuje: str
    iznos: float
    pdv_stopa: float = 0.0
    pdv_iznos: float = 0.0
    opis: str = ""
    datum_dokumenta: Optional[datetime] = None
    datum_knjizenja: Optional[datetime] = None
    oib_dobavljaca: str = ""
    confidence: float = 0.0
    reasoning: str = ""
    status: ApprovalStatus = ApprovalStatus.PENDING
    approved_by: Optional[str] = None
    erp_target: ClientERP = ClientERP.CPP
    metadata: Dict[str, Any] = field(default_factory=dict)
