"""
Nyx Light — Računovođa: FastAPI Application

Web/Chat sučelje za 15 zaposlenika.
REST API + WebSocket za streaming.
"""

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Optional

try:
    from fastapi import FastAPI, Request, HTTPException, WebSocket
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse, HTMLResponse
    from fastapi.staticfiles import StaticFiles
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

logger = logging.getLogger("nyx_light.api")


class AppState:
    """Globalno stanje aplikacije."""

    def __init__(self):
        self.llm = None
        self.memory = None
        self.rag = None
        self.overseer = None
        self.bank_parser = None
        self.invoice_ocr = None
        self.ios_module = None
        self.exporter = None
        self.sessions = None
        self.storage = None
        self.start_time = datetime.now(timezone.utc)
        self.request_count = 0


state = AppState()


@asynccontextmanager
async def lifespan(app):
    logger.info("🌙 Nyx Light — Računovođa starting...")

    # Initialize components
    from ..llm.provider import NyxLightLLM
    from ..memory.system import MemorySystem
    from ..safety.overseer import AccountingOverseer
    from ..modules.bank_parser.parser import BankStatementParser
    from ..modules.invoice_ocr.extractor import InvoiceExtractor
    from ..export import ERPExporter
    from ..sessions.manager import SessionManager
    from ..storage.sqlite_store import SQLiteStorage
    from ..core.config import config

    config.ensure_dirs()

    state.llm = NyxLightLLM()
    state.memory = MemorySystem()
    state.overseer = AccountingOverseer()
    state.bank_parser = BankStatementParser()
    state.invoice_ocr = InvoiceExtractor()
    state.exporter = ERPExporter()
    state.sessions = SessionManager(max_sessions=15)
    state.storage = SQLiteStorage()

    logger.info("✅ Svi moduli inicijalizirani")
    yield
    logger.info("🌙 Nyx Light shutting down...")


def create_app() -> "FastAPI":
    if not FASTAPI_AVAILABLE:
        raise RuntimeError("FastAPI not installed. pip install fastapi uvicorn")

    app = FastAPI(
        title="Nyx Light — Računovođa",
        description="Privatni AI sustav za računovodstvo RH",
        version="1.0.0",
        docs_url="/docs",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_routes(app)
    return app


def register_routes(app):
    """Registriraj sve API rute."""

    @app.get("/", response_class=HTMLResponse)
    async def root():
        """Serve dashboard UI."""
        import os
        dashboard_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
            "dashboard", "index.html"
        )
        if os.path.exists(dashboard_path):
            return HTMLResponse(content=open(dashboard_path).read())
        return HTMLResponse("""
        <html><head><title>Nyx Light — Računovođa</title></head>
        <body style="font-family:system-ui;max-width:800px;margin:40px auto;padding:20px;">
        <h1>🌙 Nyx Light — Računovođa</h1>
        <p>Privatni AI sustav za računovodstvo RH</p>
        <ul>
            <li><a href="/docs">📚 API Dokumentacija</a></li>
            <li><a href="/health">❤️ Health Check</a></li>
            <li><a href="/api/v1/stats">📊 Statistika</a></li>
        </ul>
        <p><em>Dashboard UI nije pronađen. Provjerite dashboard/index.html</em></p>
        </body></html>
        """)

    @app.get("/health")
    async def health():
        return {
            "status": "healthy",
            "version": "1.0.0",
            "sustav": "Nyx Light — Računovođa",
            "uptime_s": (datetime.now(timezone.utc) - state.start_time).total_seconds(),
            "vllm_running": state.llm._is_vllm_running() if state.llm else False,
            "requests": state.request_count,
        }

    @app.post("/api/v1/chat")
    async def chat(request: Request):
        """Chat endpoint — glavno sučelje za zaposlenike."""
        body = await request.json()
        message = body.get("message", "")
        user_id = body.get("user_id", "anonymous")
        client_id = body.get("client_id", "")

        if not message:
            raise HTTPException(400, "Poruka je obavezna")

        # System prompt za računovodstvo
        system = (
            "Ti si Nyx Light — Računovođa, ekspertni AI asistent za računovodstvo "
            "i knjigovodstvo u Republici Hrvatskoj. Odgovaraš na hrvatskom jeziku. "
            "Uvijek citiraj relevantni zakon ili propis. "
            "Ako nisi siguran, jasno to naznači. "
            "NIKADA ne daješ pravne savjete izvan računovodstvene domene."
        )

        response = await state.llm.generate(
            messages=[{"role": "user", "content": message}],
            system_prompt=system,
        )

        state.request_count += 1
        return {
            "response": response["content"],
            "model": response["model"],
            "tokens": response["tokens"],
            "user_id": user_id,
        }

    @app.post("/api/v1/bank/parse")
    async def parse_bank_statement(request: Request):
        """Parsiraj bankovni izvod (MT940/CSV)."""
        body = await request.json()
        file_path = body.get("file_path", "")
        bank = body.get("bank", "")
        client_id = body.get("client_id", "")

        if state.bank_parser:
            result = state.bank_parser.parse(file_path, bank)
            return {"status": "ok", "transactions": result}
        raise HTTPException(503, "Bank parser nije inicijaliziran")

    @app.post("/api/v1/invoice/extract")
    async def extract_invoice(request: Request):
        """Ekstrahiraj podatke iz skena/PDF računa."""
        body = await request.json()
        file_path = body.get("file_path", "")

        if state.invoice_ocr:
            result = state.invoice_ocr.extract(file_path)
            return {"status": "ok", "invoice_data": result}
        raise HTTPException(503, "Invoice OCR nije inicijaliziran")

    @app.post("/api/v1/booking/propose")
    async def propose_booking(request: Request):
        """Predloži knjiženje (AI → čeka odobrenje)."""
        body = await request.json()
        # AI analizira dokument i predlaže knjiženje
        return {
            "status": "pending_approval",
            "message": "Knjiženje predloženo — čeka odobrenje računovođe",
            "proposal": body,
        }

    @app.post("/api/v1/booking/approve")
    async def approve_booking(request: Request):
        """Odobri knjiženje (Human-in-the-Loop)."""
        body = await request.json()
        proposal_id = body.get("proposal_id", "")
        approved_by = body.get("approved_by", "")

        return {
            "status": "approved",
            "proposal_id": proposal_id,
            "approved_by": approved_by,
            "message": "Knjiženje odobreno i spremno za izvoz u ERP",
        }

    @app.post("/api/v1/export/{erp_system}")
    async def export_to_erp(erp_system: str, request: Request):
        """Generiraj izvoznu datoteku za CPP/Synesis."""
        body = await request.json()
        bookings = body.get("bookings", [])
        client_id = body.get("client_id", "default")
        fmt = body.get("format", "XML")

        if state.exporter:
            result = state.exporter.export(bookings, client_id, erp=erp_system, fmt=fmt)
            return result

        return {"status": "error", "message": "Exporter nije inicijaliziran"}

    @app.get("/api/v1/sessions")
    async def active_sessions():
        """Prikaži aktivne sesije (15 korisnika max)."""
        if state.sessions:
            return {
                "sessions": state.sessions.get_active_sessions(),
                "stats": state.sessions.get_stats(),
            }
        return {"sessions": [], "stats": {}}

    @app.get("/api/v1/bookings/pending")
    async def pending_bookings(client_id: str = ""):
        """Dohvati knjiženja koja čekaju odobrenje."""
        if state.storage:
            return {"bookings": state.storage.get_pending_bookings(client_id)}
        return {"bookings": []}

    @app.post("/api/v1/booking/correct")
    async def correct_booking(request: Request):
        """Zabilježi ispravak knjiženja — temelj za L2 učenje."""
        body = await request.json()
        if state.storage:
            state.storage.save_correction(body)
        if state.memory:
            state.memory.record_correction(
                user_id=body.get("user_id", ""),
                client_id=body.get("client_id", ""),
                original_konto=body.get("original_konto", ""),
                corrected_konto=body.get("corrected_konto", ""),
                document_type=body.get("document_type", ""),
                supplier=body.get("supplier", ""),
            )
        return {"status": "correction_recorded"}

    @app.get("/api/v1/stats")
    async def stats():
        return {
            "version": "1.0.0",
            "sustav": "Nyx Light — Računovođa",
            "uptime_s": (datetime.now(timezone.utc) - state.start_time).total_seconds(),
            "requests": state.request_count,
            "llm": state.llm.get_stats() if state.llm else None,
            "memory": state.memory.get_stats() if state.memory else None,
            "sessions": state.sessions.get_stats() if state.sessions else None,
            "storage": state.storage.get_stats() if state.storage else None,
            "exporter": state.exporter.get_stats() if state.exporter else None,
            "overseer": state.overseer.get_stats() if state.overseer else None,
        }

    @app.get("/api/v1/monitor")
    async def monitor():
        """Kompletni zdravstveni izvještaj sustava."""
        from ..monitoring.health import SystemMonitor
        mon = SystemMonitor()
        report = mon.get_full_report()
        report["sessions"] = state.sessions.get_stats() if state.sessions else None
        return report

    @app.post("/api/v1/upload")
    async def upload_file(request: Request):
        """Učitaj dokument (PDF, CSV, MT940, Excel)."""
        import aiofiles
        from fastapi import UploadFile, File

        form = await request.form()
        file = form.get("file")
        if not file:
            return {"error": "Nema datoteke"}

        upload_dir = Path("data/uploads")
        upload_dir.mkdir(parents=True, exist_ok=True)

        filepath = upload_dir / file.filename
        content = await file.read()
        filepath.write_bytes(content)

        # Auto-detect i obradi
        result = {"filename": file.filename, "size_kb": round(len(content) / 1024, 1)}

        suffix = Path(file.filename).suffix.lower()
        if suffix in (".sta", ".mt940", ".csv") and state.bank_parser:
            parsed = state.bank_parser.parse_file(str(filepath))
            result["type"] = "bank_statement"
            result["transactions"] = len(parsed.get("transactions", []))
        elif suffix in (".pdf", ".jpg", ".png") and state.invoice_ocr:
            extracted = state.invoice_ocr.extract(str(filepath))
            result["type"] = "invoice"
            result["extracted"] = extracted
        elif suffix in (".xlsx", ".xls"):
            result["type"] = "excel"

        return result

    @app.websocket("/ws/chat")
    async def websocket_chat(websocket: WebSocket):
        """WebSocket za streaming chat."""
        await websocket.accept()
        try:
            while True:
                data = await websocket.receive_json()
                message = data.get("message", "")

                async for token in state.llm.generate_stream(
                    messages=[{"role": "user", "content": message}]
                ):
                    await websocket.send_json({"token": token, "done": False})
                await websocket.send_json({"token": "", "done": True})
        except Exception:
            pass


app = create_app() if FASTAPI_AVAILABLE else None
