"""
Nyx Light — AS4/Peppol Posrednik (B2Brouter)
═════════════════════════════════════════════
Slanje i primanje e-Računa putem Peppol mreže.

Zakonski okvir:
  - Fiskalizacija 2.0 (od 1.1.2026.) — obvezni e-računi za B2G
  - EN 16931-1:2017 — europski standard strukturiranog računa
  - AS4 protocol (CEF eDelivery) — transport sloj Peppol mreže
  - FINA eRačun — nacionalni Peppol Access Point za RH

Arhitektura:
  Nyx Light → B2Brouter/FINA API → Peppol SMP → Primatelj
  Primatelj → Peppol SMP → B2Brouter/FINA API → Nyx Light

Podržani posrednici:
  1. B2Brouter (https://b2brouter.net) — popularni EU SaaS AP
  2. FINA eRačun (https://eracun.fina.hr) — nacionalni AP
  3. Moj-eRacun (https://moj-eracun.hr) — alternativni HR AP
"""

import asyncio
import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("nyx_light.peppol")


# ═══════════════════════════════════════════
# ENUMS & TYPES
# ═══════════════════════════════════════════

class PeppolProvider(str, Enum):
    """Podržani Peppol Access Point posrednici."""
    B2BROUTER = "b2brouter"
    FINA_ERACUN = "fina_eracun"
    MOJ_ERACUN = "moj_eracun"


class DocumentType(str, Enum):
    """Tipovi dokumenata prema Peppol BIS."""
    INVOICE = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
    CREDIT_NOTE = "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2"
    INVOICE_RESPONSE = "urn:fdc:peppol.eu:poacc:trns:invoice_response:3"


class DeliveryStatus(str, Enum):
    """Status dostave e-računa."""
    QUEUED = "queued"           # Čeka slanje
    SENDING = "sending"         # Šalje se
    DELIVERED = "delivered"     # Uspješno dostavljeno
    ACCEPTED = "accepted"       # Primatelj prihvatio
    REJECTED = "rejected"       # Primatelj odbio
    FAILED = "failed"           # Greška u dostavi
    RETRY = "retry"             # Ponovni pokušaj


class InvoiceDirection(str, Enum):
    """Smjer e-računa."""
    OUTBOUND = "outbound"  # Šaljemo
    INBOUND = "inbound"    # Primamo


# ═══════════════════════════════════════════
# PEPPOL PARTICIPANT ID
# ═══════════════════════════════════════════

@dataclass
class PeppolParticipant:
    """Peppol identifikator sudionika."""
    scheme: str = "0192"  # HR: 0192 (OIB scheme u Peppol SML)
    id: str = ""          # OIB (11 znamenki)
    name: str = ""
    country: str = "HR"

    @property
    def full_id(self) -> str:
        """Puni Peppol Participant ID (scheme::id)."""
        return f"{self.scheme}::{self.id}"

    @staticmethod
    def from_oib(oib: str, name: str = "") -> "PeppolParticipant":
        """Kreiraj participant iz OIB-a."""
        if len(oib) != 11 or not oib.isdigit():
            raise ValueError(f"Neispravan OIB: {oib}")
        return PeppolParticipant(scheme="0192", id=oib, name=name, country="HR")

    @staticmethod
    def from_vat_id(vat_id: str, name: str = "") -> "PeppolParticipant":
        """Kreiraj participant iz EU VAT ID-a (npr. HR12345678903)."""
        country = vat_id[:2].upper()
        schemes = {
            "HR": "0192",  # OIB
            "DE": "9930",  # USt-IdNr
            "AT": "9915",  # UID-Nr
            "IT": "0211",  # Partita IVA
            "SI": "9948",  # Davčna številka
        }
        scheme = schemes.get(country, "0192")
        tax_id = vat_id[2:] if country in schemes else vat_id
        return PeppolParticipant(scheme=scheme, id=tax_id, name=name, country=country)


# ═══════════════════════════════════════════
# PEPPOL ENVELOPE
# ═══════════════════════════════════════════

@dataclass
class PeppolEnvelope:
    """AS4 envelope za Peppol dokument."""
    envelope_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sender: Optional[PeppolParticipant] = None
    receiver: Optional[PeppolParticipant] = None
    document_type: DocumentType = DocumentType.INVOICE
    process_id: str = "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0"
    payload_xml: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    # Delivery tracking
    status: DeliveryStatus = DeliveryStatus.QUEUED
    direction: InvoiceDirection = InvoiceDirection.OUTBOUND
    delivery_attempts: int = 0
    max_attempts: int = 5
    last_error: str = ""
    delivered_at: str = ""
    message_id: str = ""  # Peppol Message ID od posrednika

    @property
    def payload_hash(self) -> str:
        return hashlib.sha256(self.payload_xml.encode()).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "envelope_id": self.envelope_id,
            "sender": self.sender.full_id if self.sender else "",
            "receiver": self.receiver.full_id if self.receiver else "",
            "document_type": self.document_type.value,
            "status": self.status.value,
            "direction": self.direction.value,
            "attempts": self.delivery_attempts,
            "payload_hash": self.payload_hash,
            "created_at": self.created_at,
            "delivered_at": self.delivered_at,
            "message_id": self.message_id,
            "last_error": self.last_error,
        }


# ═══════════════════════════════════════════
# PEPPOL AP CLIENT (B2Brouter / FINA)
# ═══════════════════════════════════════════

@dataclass
class APCredentials:
    """Akreditivi za Access Point posrednika."""
    provider: PeppolProvider
    api_url: str
    api_key: str = ""
    api_secret: str = ""
    certificate_path: str = ""     # .p12 FINA certifikat
    certificate_password: str = ""
    company_oib: str = ""
    sandbox: bool = True           # True = test okruženje

    @staticmethod
    def b2brouter_sandbox() -> "APCredentials":
        return APCredentials(
            provider=PeppolProvider.B2BROUTER,
            api_url="https://app.b2brouter.net/api/v2",
            sandbox=True,
        )

    @staticmethod
    def fina_eracun_sandbox() -> "APCredentials":
        return APCredentials(
            provider=PeppolProvider.FINA_ERACUN,
            api_url="https://test-eracun.fina.hr/api/v1",
            sandbox=True,
        )


class PeppolAPClient:
    """
    Klijent za komunikaciju s Peppol Access Point-om.

    Podržava:
    1. B2Brouter REST API (JSON)
    2. FINA eRačun SOAP/REST API
    3. Moj-eRacun REST API

    Retry logika: exponential backoff (5s → 10s → 20s → 40s → 80s)
    """

    def __init__(self, credentials: APCredentials):
        self.cred = credentials
        self._outbox: List[PeppolEnvelope] = []
        self._inbox: List[PeppolEnvelope] = []
        self._delivery_log: List[Dict] = []

    async def send_invoice(self, envelope: PeppolEnvelope) -> Dict[str, Any]:
        """Pošalji e-račun putem Peppol mreže."""
        envelope.direction = InvoiceDirection.OUTBOUND
        envelope.status = DeliveryStatus.SENDING
        envelope.delivery_attempts += 1

        try:
            if self.cred.provider == PeppolProvider.B2BROUTER:
                result = await self._send_b2brouter(envelope)
            elif self.cred.provider == PeppolProvider.FINA_ERACUN:
                result = await self._send_fina(envelope)
            else:
                result = await self._send_generic(envelope)

            envelope.status = DeliveryStatus.DELIVERED
            envelope.delivered_at = datetime.now().isoformat()
            envelope.message_id = result.get("message_id", "")
            self._outbox.append(envelope)

            self._log_delivery(envelope, "SUCCESS")
            return {
                "success": True,
                "envelope_id": envelope.envelope_id,
                "message_id": envelope.message_id,
                "status": envelope.status.value,
            }

        except Exception as e:
            envelope.last_error = str(e)
            if envelope.delivery_attempts < envelope.max_attempts:
                envelope.status = DeliveryStatus.RETRY
                delay = 5 * (2 ** (envelope.delivery_attempts - 1))
                self._log_delivery(envelope, f"RETRY in {delay}s: {e}")
                return {
                    "success": False,
                    "retry": True,
                    "retry_delay_s": delay,
                    "attempt": envelope.delivery_attempts,
                    "error": str(e),
                }
            else:
                envelope.status = DeliveryStatus.FAILED
                self._log_delivery(envelope, f"FAILED: {e}")
                return {
                    "success": False,
                    "retry": False,
                    "error": str(e),
                    "attempts_exhausted": True,
                }

    async def fetch_inbox(self, since: str = "") -> List[PeppolEnvelope]:
        """Dohvati nove primljene e-račune iz inbox-a posrednika."""
        if self.cred.provider == PeppolProvider.B2BROUTER:
            invoices = await self._fetch_b2brouter_inbox(since)
        elif self.cred.provider == PeppolProvider.FINA_ERACUN:
            invoices = await self._fetch_fina_inbox(since)
        else:
            invoices = []

        for inv in invoices:
            inv.direction = InvoiceDirection.INBOUND
            inv.status = DeliveryStatus.DELIVERED
            self._inbox.append(inv)

        return invoices

    async def check_status(self, envelope_id: str) -> Dict[str, Any]:
        """Provjeri status poslanog e-računa."""
        for env in self._outbox:
            if env.envelope_id == envelope_id:
                return env.to_dict()
        return {"error": f"Envelope {envelope_id} not found"}

    async def reject_invoice(self, message_id: str,
                             reason: str = "INCORRECT_AMOUNT",
                             note: str = "") -> Dict[str, Any]:
        """Odbij primljeni e-račun (5 radnih dana rok)."""
        valid_reasons = [
            "PRICE_MISMATCH", "WRONG_RECIPIENT", "DUPLICATE",
            "INCORRECT_AMOUNT", "GOODS_NOT_RECEIVED", "OTHER",
        ]
        if reason not in valid_reasons:
            return {"error": f"Invalid reason. Valid: {valid_reasons}"}

        rejection = {
            "message_id": message_id,
            "response_type": "REJECTED",
            "reason_code": reason,
            "note": note,
            "timestamp": datetime.now().isoformat(),
        }
        self._delivery_log.append({"action": "REJECT", **rejection})
        return {"success": True, **rejection}

    # ── B2Brouter API ──

    async def _send_b2brouter(self, env: PeppolEnvelope) -> Dict:
        """B2Brouter REST API v2 — slanje UBL XML-a."""
        # Production: POST /api/v2/invoices
        # Headers: Authorization: Bearer {api_key}
        # Body: multipart/form-data s UBL XML
        if self.cred.sandbox:
            await asyncio.sleep(0.01)
            return {
                "message_id": f"b2b-{uuid.uuid4().hex[:12]}",
                "status": "accepted",
                "provider": "b2brouter",
            }
        # Real implementation would use httpx:
        # async with httpx.AsyncClient() as client:
        #     resp = await client.post(
        #         f"{self.cred.api_url}/invoices",
        #         headers={"Authorization": f"Bearer {self.cred.api_key}"},
        #         files={"file": ("invoice.xml", env.payload_xml, "application/xml")},
        #     )
        #     return resp.json()
        raise NotImplementedError("B2Brouter production not configured")

    async def _send_fina(self, env: PeppolEnvelope) -> Dict:
        """FINA eRačun API — slanje s PKI certifikatom."""
        if self.cred.sandbox:
            await asyncio.sleep(0.01)
            return {
                "message_id": f"fina-{uuid.uuid4().hex[:12]}",
                "status": "accepted",
                "provider": "fina_eracun",
            }
        raise NotImplementedError("FINA production not configured")

    async def _send_generic(self, env: PeppolEnvelope) -> Dict:
        """Generic fallback."""
        await asyncio.sleep(0.01)
        return {"message_id": f"gen-{uuid.uuid4().hex[:12]}", "status": "queued"}

    async def _fetch_b2brouter_inbox(self, since: str) -> List[PeppolEnvelope]:
        """Dohvati inbox s B2Brouter-a."""
        # Production: GET /api/v2/invoices/received?since={since}
        return []

    async def _fetch_fina_inbox(self, since: str) -> List[PeppolEnvelope]:
        """Dohvati inbox s FINA eRačun-a."""
        return []

    def _log_delivery(self, env: PeppolEnvelope, result: str):
        self._delivery_log.append({
            "timestamp": datetime.now().isoformat(),
            "envelope_id": env.envelope_id,
            "sender": env.sender.full_id if env.sender else "",
            "receiver": env.receiver.full_id if env.receiver else "",
            "result": result,
            "attempt": env.delivery_attempts,
        })

    def get_stats(self) -> Dict[str, Any]:
        return {
            "provider": self.cred.provider.value,
            "sandbox": self.cred.sandbox,
            "outbox_count": len(self._outbox),
            "inbox_count": len(self._inbox),
            "total_deliveries": len(self._delivery_log),
            "failed": sum(1 for e in self._outbox if e.status == DeliveryStatus.FAILED),
            "delivered": sum(1 for e in self._outbox if e.status == DeliveryStatus.DELIVERED),
        }


# ═══════════════════════════════════════════
# PEPPOL DIRECTORY (SMP LOOKUP)
# ═══════════════════════════════════════════

class PeppolDirectory:
    """
    Peppol SMP Lookup — provjeri je li primatelj na Peppol mreži.

    SMP (Service Metadata Provider) = javni registar Peppol sudionika.
    Prije slanja e-računa, provjeravamo može li primatelj primiti
    dokument određenog tipa putem Peppola.
    """

    SML_ZONES = {
        "production": "edelivery.tech.ec.europa.eu",
        "test": "acc.edelivery.tech.ec.europa.eu",
    }

    # Cache poznatih HR Peppol sudionika
    HR_KNOWN_PARTICIPANTS = {
        "0192::85821130368": "Republika Hrvatska (Ministarstvo financija)",
        "0192::18683136487": "FINA",
        "0192::36632213498": "Grad Zagreb",
        "0192::13389812760": "HEP d.d.",
        "0192::81793146560": "Hrvatski Telekom",
    }

    def __init__(self, sandbox: bool = True):
        self.sandbox = sandbox
        self._cache: Dict[str, Dict] = {}

    async def lookup(self, participant_id: str) -> Dict[str, Any]:
        """Provjeri je li sudionik registriran na Peppol mreži."""
        if participant_id in self._cache:
            return self._cache[participant_id]

        # Check known participants
        if participant_id in self.HR_KNOWN_PARTICIPANTS:
            result = {
                "found": True,
                "participant_id": participant_id,
                "name": self.HR_KNOWN_PARTICIPANTS[participant_id],
                "supports_invoice": True,
                "supports_credit_note": True,
                "country": "HR",
            }
            self._cache[participant_id] = result
            return result

        # Production: DNS-based SMP lookup
        # hash = MD5(lowercase(participantId))
        # DNS: {hash}.iso6523-actorid-upis.{sml_zone}
        # Then fetch metadata from SMP URL

        return {
            "found": False,
            "participant_id": participant_id,
            "note": "Participant not found in Peppol directory. "
                    "May need to register with a Peppol Access Point.",
        }

    def is_b2g(self, receiver_oib: str) -> bool:
        """Provjeri je li primatelj javni sektor (B2G = obvezni e-račun)."""
        b2g_oibs = {
            "85821130368",  # Ministarstvo financija
            "18683136487",  # FINA
            "36632213498",  # Grad Zagreb
            "69099012420",  # Grad Split
            "81817902036",  # Grad Rijeka
        }
        return receiver_oib in b2g_oibs


# ═══════════════════════════════════════════
# INTEGRATION WITH FISKALIZACIJA 2.0
# ═══════════════════════════════════════════

class PeppolIntegration:
    """
    Integracija Peppol posrednika s Nyx Light sustavom.

    Workflow:
    1. Fiskalizacija2Engine generira UBL 2.1 XML
    2. PeppolIntegration wrap-a u AS4 envelope
    3. PeppolAPClient šalje putem odabranog AP-a
    4. Status tracking s exponential backoff retry
    """

    def __init__(self, credentials: APCredentials = None):
        self.cred = credentials or APCredentials.b2brouter_sandbox()
        self.client = PeppolAPClient(self.cred)
        self.directory = PeppolDirectory(sandbox=self.cred.sandbox)
        self._sent_invoices: Dict[str, PeppolEnvelope] = {}

    async def send_eracun(self, ubl_xml: str,
                          sender_oib: str, sender_name: str,
                          receiver_oib: str, receiver_name: str) -> Dict[str, Any]:
        """Pošalji e-račun kompletnim workflow-om."""
        # 1. Kreiraj participant ID-ove
        sender = PeppolParticipant.from_oib(sender_oib, sender_name)
        receiver = PeppolParticipant.from_oib(receiver_oib, receiver_name)

        # 2. Provjeri je li primatelj na Peppol mreži
        lookup = await self.directory.lookup(receiver.full_id)

        # 3. Kreiraj envelope
        envelope = PeppolEnvelope(
            sender=sender,
            receiver=receiver,
            document_type=DocumentType.INVOICE,
            payload_xml=ubl_xml,
        )

        # 4. Pošalji
        result = await self.client.send_invoice(envelope)
        if result.get("success"):
            self._sent_invoices[envelope.envelope_id] = envelope

        result["peppol_lookup"] = {
            "receiver_found": lookup.get("found", False),
            "b2g": self.directory.is_b2g(receiver_oib),
        }
        return result

    async def receive_eracuni(self) -> List[Dict[str, Any]]:
        """Dohvati nove primljene e-račune."""
        envelopes = await self.client.fetch_inbox()
        results = []
        for env in envelopes:
            results.append({
                "envelope_id": env.envelope_id,
                "sender": env.sender.full_id if env.sender else "",
                "xml_hash": env.payload_hash,
                "received_at": env.delivered_at or env.created_at,
                "status": "ready_for_processing",
            })
        return results

    async def get_delivery_status(self, envelope_id: str) -> Dict[str, Any]:
        """Provjeri status dostave."""
        return await self.client.check_status(envelope_id)

    def get_stats(self) -> Dict[str, Any]:
        return {
            "module": "peppol",
            "provider": self.cred.provider.value,
            "sandbox": self.cred.sandbox,
            "sent_total": len(self._sent_invoices),
            **self.client.get_stats(),
        }
