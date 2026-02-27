"""
Nyx Light — Računovođa: Production FastAPI Server

Kompletni REST API + WebSocket za 15 zaposlenika.
Svi podaci lokalni (Zero Cloud). Human-in-the-Loop.
"""

import asyncio
import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends, UploadFile, File, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Internal imports
from nyx_light.auth import AuthManager as AuthSystem, Role
from nyx_light.storage.sqlite_store import SQLiteStorage
from nyx_light.memory.system import MemorySystem
from nyx_light.llm.chat_bridge import ChatBridge, ChatContext
from nyx_light.llm.provider import NyxLightLLM
from nyx_light.safety.overseer import AccountingOverseer
from nyx_light.sessions.manager import SessionManager
from nyx_light.monitoring.health import SystemMonitor
from nyx_light.backup import BackupManager

logger = logging.getLogger("nyx_light.api")

# ═══════════════════════════════════════════
# PYDANTIC MODELS
# ═══════════════════════════════════════════

class LoginRequest(BaseModel):
    username: str
    password: str

class ChatRequest(BaseModel):
    message: str
    client_id: str = ""

class ApprovalRequest(BaseModel):
    reason: str = ""

class CorrectionRequest(BaseModel):
    konto_duguje: str = ""
    konto_potrazuje: str = ""
    reason: str = ""

class ClientRequest(BaseModel):
    name: str
    oib: str = ""
    erp_system: str = "CPP"

class ExportRequest(BaseModel):
    client_id: str
    format: str = "cpp_xml"

class BookingRequest(BaseModel):
    client_id: str
    document_type: str = ""
    konto_duguje: str = ""
    konto_potrazuje: str = ""
    iznos: float = 0
    pdv_stopa: float = 25
    opis: str = ""
    oib: str = ""
    datum_dokumenta: str = ""

# ═══════════════════════════════════════════
# GLOBAL STATE
# ═══════════════════════════════════════════

class AppState:
    def __init__(self):
        self.storage: Optional[SQLiteStorage] = None
        self.auth: Optional[AuthSystem] = None
        self.memory: Optional[MemorySystem] = None
        self.chat_bridge: Optional[ChatBridge] = None
        self.llm: Optional[NyxLightLLM] = None
        self.overseer: Optional[AccountingOverseer] = None
        self.sessions: Optional[SessionManager] = None
        self.monitor: Optional[SystemMonitor] = None
        self.backup: Optional[BackupManager] = None
        self.start_time = datetime.now(timezone.utc)
        self.ws_connections: Dict[str, WebSocket] = {}

state = AppState()

# ═══════════════════════════════════════════
# LIFESPAN
# ═══════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🌙 Nyx Light — Računovođa starting...")

    # Initialize all subsystems
    state.storage = SQLiteStorage()
    state.auth = AuthSystem()
    state.memory = MemorySystem()
    state.llm = NyxLightLLM()
    state.chat_bridge = ChatBridge()
    state.overseer = AccountingOverseer()
    state.sessions = SessionManager()
    state.monitor = SystemMonitor()
    state.backup = BackupManager()

    # Start nightly scheduler in background
    try:
        from nyx_light.scheduler import NightlyScheduler
        state._scheduler = NightlyScheduler()
        asyncio.create_task(state._scheduler.start())
        logger.info("Noćni scheduler pokrenut")
    except Exception as e:
        logger.warning("Scheduler not started: %s", e)

    # Ensure demo users exist
    _ensure_demo_users()

    logger.info("✅ Svi sustavi inicijalizirani — spremno za rad")
    yield

    # Shutdown
    if state.storage:
        state.storage.close()
    logger.info("🌙 Nyx Light — zaustavljeno")

def _ensure_demo_users():
    """Create demo users if none exist beyond default admin."""
    try:
        users = state.auth.list_users()
        usernames = {u.username for u in users}
        # Default admin has password "admin" from AuthManager._init_db
        # Change to "admin123" for production
        if "admin" in usernames:
            state.auth.change_password("admin", "admin123")
        if "racunovodja" not in usernames:
            state.auth.create_user("racunovodja", "nyx2026", "Ana Horvat", Role.RACUNOVODJA)
        if "asistent" not in usernames:
            state.auth.create_user("asistent", "nyx2026", "Marko Novak", Role.ASISTENT)
        logger.info("Korisnici: admin/admin123, racunovodja/nyx2026, asistent/nyx2026")
    except Exception as e:
        logger.warning("Demo users creation: %s", e)

# ═══════════════════════════════════════════
# APP CREATION
# ═══════════════════════════════════════════

app = FastAPI(
    title="Nyx Light — Računovođa",
    version="2.0.0",
    description="Privatni ekspertni AI sustav za računovodstvo RH",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
static_dir = Path(__file__).parent.parent.parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# ═══════════════════════════════════════════
# AUTH DEPENDENCY
# ═══════════════════════════════════════════

async def get_current_user(request: Request) -> Dict:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(401, "Niste prijavljeni")
    token = auth_header[7:]
    auth_token = state.auth.verify_token(token)
    if not auth_token:
        raise HTTPException(401, "Nevažeći token — prijavite se ponovo")
    return {
        "user_id": auth_token.user_id,
        "username": auth_token.username,
        "role": auth_token.role.value if hasattr(auth_token.role, 'value') else auth_token.role,
        "token": token,
    }

def require_permission(permission: str):
    async def checker(user=Depends(get_current_user)):
        if not state.auth.has_permission(user["token"], permission):
            raise HTTPException(403, f"Nemate dozvolu: {permission}")
        return user
    return checker

# ═══════════════════════════════════════════
# ROOT
# ═══════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
async def root():
    index = static_dir / "index.html"
    if index.exists():
        return HTMLResponse(index.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>🌙 Nyx Light — Računovođa API</h1><p>Frontend: /static/index.html</p>")

# ═══════════════════════════════════════════
# AUTH ENDPOINTS
# ═══════════════════════════════════════════

@app.post("/api/auth/login")
async def login(req: LoginRequest):
    result = state.auth.login(req.username, req.password)
    if not result or not result.get("ok"):
        raise HTTPException(401, result.get("error", "Neispravno korisničko ime ili lozinka") if result else "Greška pri prijavi")
    return {"token": result["token"], "user": result["user"]}

@app.get("/api/auth/me")
async def auth_me(user=Depends(get_current_user)):
    return user

@app.get("/api/auth/users")
async def list_users(user=Depends(require_permission("manage_users"))):
    return state.auth.list_users()

# ═══════════════════════════════════════════
# CHAT
# ═══════════════════════════════════════════

@app.post("/api/chat")
async def chat(req: ChatRequest, user=Depends(get_current_user)):
    # Safety check
    safety = state.overseer.evaluate(req.message)
    if not safety.get("approved", True):
        return {"content": f"⚠️ {safety.get('message', 'Upit izvan domene računovodstva.')}", "blocked": True}

    # Build context from memory
    context = ChatContext()
    if req.client_id:
        hint = state.memory.get_kontiranje_hint(req.client_id)
        if hint:
            context.semantic_facts.append(hint["hint"])
        context.client_info = {"id": req.client_id}

    # Get episodic context (today's interactions)
    today_eps = state.memory.l1_episodic.search_today(req.message[:50])
    for ep in today_eps[:3]:
        context.episodic_recent.append(f"Ranije: {ep.query} → {ep.response[:100]}")

    session_id = f"{user['user_id']}_{req.client_id or 'general'}"

    # Call LLM
    response = await state.chat_bridge.chat(req.message, session_id, context)

    # Store in episodic memory
    state.memory.l1_episodic.store(
        query=req.message,
        response=response.content[:500],
        user_id=user["user_id"],
        session_id=session_id,
    )

    return {
        "content": response.content,
        "tokens": response.tokens_used,
        "latency_ms": round(response.latency_ms, 1),
        "model": response.model,
    }

# WebSocket chat (streaming)
@app.websocket("/api/ws/chat")
async def ws_chat(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            data = await ws.receive_json()
            msg = data.get("message", "")
            session_id = data.get("session_id", "ws_default")

            # Stream response
            full = ""
            async for token in state.chat_bridge.chat_stream(msg, session_id):
                full += token
                await ws.send_json({"type": "token", "content": token})

            await ws.send_json({"type": "done", "content": full})
    except WebSocketDisconnect:
        pass

# ═══════════════════════════════════════════
# BOOKINGS & APPROVAL (HITL)
# ═══════════════════════════════════════════

@app.get("/api/pending")
async def get_pending(client_id: str = "", user=Depends(get_current_user)):
    items = state.storage.get_pending_bookings(client_id)
    return {"items": items, "count": len(items)}

@app.get("/api/bookings")
async def get_bookings(status: str = "", client_id: str = "", user=Depends(get_current_user)):
    if status == "approved":
        items = state.storage.get_approved_bookings(client_id, exported=True)
    elif status == "pending":
        items = state.storage.get_pending_bookings(client_id)
    else:
        # All bookings
        conn = state.storage._conn
        query = "SELECT * FROM bookings"
        params = []
        conditions = []
        if client_id:
            conditions.append("client_id=?")
            params.append(client_id)
        if status:
            conditions.append("status=?")
            params.append(status)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY created_at DESC LIMIT 200"
        rows = conn.execute(query, params).fetchall()
        items = [dict(r) for r in rows]
    return {"items": items, "count": len(items)}

@app.post("/api/bookings")
async def create_booking(req: BookingRequest, user=Depends(require_permission("chat"))):
    booking = {
        "id": f"bk_{int(time.time()*1000)}_{uuid.uuid4().hex[:6]}",
        "client_id": req.client_id,
        "document_type": req.document_type,
        "konto_duguje": req.konto_duguje,
        "konto_potrazuje": req.konto_potrazuje,
        "iznos": req.iznos,
        "pdv_stopa": req.pdv_stopa,
        "opis": req.opis,
        "oib": req.oib,
        "datum_dokumenta": req.datum_dokumenta or datetime.now().strftime("%Y-%m-%d"),
        "status": "pending",
        "confidence": 0.0,
    }
    bid = state.storage.save_booking(booking)
    return {"id": bid, "status": "pending"}

@app.post("/api/approve/{booking_id}")
async def approve(booking_id: str, user=Depends(require_permission("approve"))):
    ok = state.storage.approve_booking(booking_id, user["user_id"])
    if not ok:
        raise HTTPException(404, "Knjiženje nije pronađeno ili već obrađeno")
    # Notify WS clients
    for ws in state.ws_connections.values():
        try:
            await ws.send_json({"type": "approval", "booking_id": booking_id})
        except:
            pass
    return {"status": "approved", "booking_id": booking_id}

@app.post("/api/reject/{booking_id}")
async def reject(booking_id: str, req: ApprovalRequest = ApprovalRequest(), user=Depends(require_permission("reject"))):
    ok = state.storage.reject_booking(booking_id, user["user_id"], req.reason)
    if not ok:
        raise HTTPException(404, "Knjiženje nije pronađeno ili već obrađeno")
    return {"status": "rejected", "booking_id": booking_id}

@app.post("/api/correct/{booking_id}")
async def correct(booking_id: str, req: CorrectionRequest, user=Depends(require_permission("correct"))):
    # Get original booking
    row = state.storage._conn.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Knjiženje nije pronađeno")
    original = dict(row)

    # Save correction for L2 memory
    state.storage.save_correction({
        "booking_id": booking_id,
        "user_id": user["user_id"],
        "client_id": original.get("client_id", ""),
        "original_konto": original.get("konto_duguje", ""),
        "corrected_konto": req.konto_duguje,
        "document_type": original.get("document_type", ""),
        "supplier": "",
        "description": req.reason,
    })

    # Update booking with corrected values
    state.storage._conn.execute(
        """UPDATE bookings SET konto_duguje=?, konto_potrazuje=?,
           status='approved', approved_by=?, approved_at=datetime('now'), updated_at=datetime('now')
           WHERE id=?""",
        (req.konto_duguje or original["konto_duguje"],
         req.konto_potrazuje or original["konto_potrazuje"],
         user["user_id"], booking_id)
    )
    state.storage._conn.commit()

    # Record in memory system
    state.memory.record_correction(
        user_id=user["user_id"],
        client_id=original.get("client_id", ""),
        original_konto=original.get("konto_duguje", ""),
        corrected_konto=req.konto_duguje,
        document_type=original.get("document_type", ""),
        description=req.reason,
    )

    return {"status": "corrected", "booking_id": booking_id}

# ═══════════════════════════════════════════
# CLIENTS
# ═══════════════════════════════════════════

@app.get("/api/clients")
async def get_clients(user=Depends(get_current_user)):
    conn = state.storage._conn
    rows = conn.execute("SELECT * FROM clients WHERE active=1 ORDER BY name").fetchall()
    items = []
    for r in rows:
        d = dict(r)
        count = conn.execute("SELECT COUNT(*) FROM bookings WHERE client_id=?", (d["id"],)).fetchone()[0]
        d["bookings_count"] = count
        items.append(d)
    return {"items": items}

@app.post("/api/clients")
async def create_client(req: ClientRequest, user=Depends(require_permission("manage_clients"))):
    cid = f"K{int(time.time()) % 100000:05d}"
    try:
        state.storage._conn.execute(
            "INSERT INTO clients (id, name, oib, erp_system) VALUES (?, ?, ?, ?)",
            (cid, req.name, req.oib, req.erp_system)
        )
        state.storage._conn.commit()
    except Exception:
        # Client with same OIB already exists — return existing
        if req.oib:
            row = state.storage._conn.execute(
                "SELECT id, name FROM clients WHERE oib=?", (req.oib,)
            ).fetchone()
            if row:
                return {"id": row[0], "name": row[1], "existing": True}
        # Generate unique ID and retry
        import secrets
        cid = f"K{secrets.token_hex(4).upper()}"
        state.storage._conn.execute(
            "INSERT OR IGNORE INTO clients (id, name, oib, erp_system) VALUES (?, ?, ?, ?)",
            (cid, req.name, req.oib or "", req.erp_system)
        )
        state.storage._conn.commit()
    return {"id": cid, "name": req.name}

# ═══════════════════════════════════════════
# UPLOAD / DOCUMENT PROCESSING
# ═══════════════════════════════════════════

@app.post("/api/upload")
async def upload_document(
    file: UploadFile = File(...),
    client_id: str = Form(""),
    user=Depends(require_permission("chat"))
):
    if not client_id:
        raise HTTPException(400, "Odaberite klijenta")

    # Save file
    upload_dir = Path("data/uploads") / client_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / f"{int(time.time())}_{file.filename}"

    content = await file.read()
    file_path.write_bytes(content)

    fname = file.filename.lower()
    doc_type = "unknown"
    details = ""

    if fname.endswith(('.pdf', '.jpg', '.jpeg', '.png')):
        doc_type = "invoice_scan"
        details = f"Dokument spremljen za OCR obradu ({len(content)} bytes)"
        # Create pending booking for review
        booking = {
            "id": f"bk_{int(time.time()*1000)}_{uuid.uuid4().hex[:4]}",
            "client_id": client_id,
            "document_type": "ulazni_racun",
            "opis": f"Upload: {file.filename}",
            "status": "pending",
            "confidence": 0.5,
            "ai_reasoning": f"Dokument uploadan od {user['username']}, čeka OCR i klasifikaciju",
        }
        state.storage.save_booking(booking)

    elif fname.endswith('.mt940'):
        doc_type = "bank_statement"
        details = "MT940 bankovni izvod — parsiranje u tijeku"

    elif fname.endswith('.xml'):
        doc_type = "eracun"
        details = "XML eRačun — validacija u tijeku"

    elif fname.endswith(('.csv', '.xlsx')):
        doc_type = "spreadsheet"
        details = "Tablica podataka spremljena"

    state.storage._log_audit("upload", user["user_id"], details=f"{file.filename} → {doc_type}")

    return {
        "status": "processed",
        "document_type": doc_type,
        "filename": file.filename,
        "size": len(content),
        "details": details,
    }

# ═══════════════════════════════════════════
# EXPORT
# ═══════════════════════════════════════════

@app.post("/api/export")
async def export_bookings(req: ExportRequest, user=Depends(require_permission("export"))):
    bookings = state.storage.get_approved_bookings(req.client_id, exported=False)
    if not bookings:
        return {"count": 0, "filename": None, "message": "Nema novih odobrenih knjiženja za export"}

    export_dir = Path("data/exports") / req.client_id
    export_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    if req.format == "cpp_xml":
        filename = f"cpp_export_{ts}.xml"
        _export_cpp_xml(bookings, export_dir / filename)
    elif req.format == "synesis_csv":
        filename = f"synesis_export_{ts}.csv"
        _export_synesis_csv(bookings, export_dir / filename)
    elif req.format == "json":
        filename = f"export_{ts}.json"
        (export_dir / filename).write_text(json.dumps(bookings, indent=2, ensure_ascii=False, default=str))
    else:
        filename = f"export_{ts}.json"
        (export_dir / filename).write_text(json.dumps(bookings, indent=2, ensure_ascii=False, default=str))

    # Mark as exported
    ids = [b["id"] for b in bookings]
    state.storage.mark_exported(ids)
    state.storage._log_audit("export", user["user_id"], details=f"{len(bookings)} bookings → {filename}")

    return {"count": len(bookings), "filename": filename, "format": req.format}

def _export_cpp_xml(bookings: List[Dict], path: Path):
    """Generate CPP-compatible XML export."""
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<CPPImport>']
    for b in bookings:
        lines.append('  <Knjizenje>')
        lines.append(f'    <DatumDokumenta>{b.get("datum_dokumenta", "")}</DatumDokumenta>')
        lines.append(f'    <KontoDuguje>{b.get("konto_duguje", "")}</KontoDuguje>')
        lines.append(f'    <KontoPotrazuje>{b.get("konto_potrazuje", "")}</KontoPotrazuje>')
        lines.append(f'    <Iznos>{b.get("iznos", 0):.2f}</Iznos>')
        lines.append(f'    <Opis>{b.get("opis", "")}</Opis>')
        lines.append(f'    <OIB>{b.get("oib", "")}</OIB>')
        lines.append('  </Knjizenje>')
    lines.append('</CPPImport>')
    path.write_text('\n'.join(lines), encoding='utf-8')

def _export_synesis_csv(bookings: List[Dict], path: Path):
    """Generate Synesis-compatible CSV export."""
    lines = ['DatumDok;KontoDug;KontoPot;Iznos;Opis;OIB']
    for b in bookings:
        lines.append(f'{b.get("datum_dokumenta","")};{b.get("konto_duguje","")};'
                     f'{b.get("konto_potrazuje","")};{b.get("iznos",0):.2f};'
                     f'{b.get("opis","")};{b.get("oib","")}')
    path.write_text('\n'.join(lines), encoding='utf-8')

# ═══════════════════════════════════════════
# DASHBOARD & STATUS
# ═══════════════════════════════════════════

@app.get("/api/dashboard")
async def dashboard(user=Depends(get_current_user)):
    stats = state.storage.get_stats()
    clients = state.storage._conn.execute("SELECT COUNT(*) FROM clients WHERE active=1").fetchone()[0]
    return {
        "pending": stats["pending"],
        "approved": stats["approved"],
        "total_bookings": stats["total_bookings"],
        "corrections": stats["corrections"],
        "clients": clients,
        "active_sessions": len(state.sessions._sessions) if state.sessions else 0,
    }

@app.get("/api/deadlines")
async def deadlines(user=Depends(get_current_user)):
    """Return upcoming tax deadlines."""
    now = datetime.now()
    month = now.month
    year = now.year
    from calendar import monthrange
    last_day = monthrange(year, month)[1]

    items = [
        {"name": "PDV-S prijava", "description": f"Mjesečna PDV prijava za {month}/{year}",
         "due_date": f"{year}-{month:02d}-{last_day}", "days_remaining": max(0, last_day - now.day)},
        {"name": "JOPPD obrazac", "description": "Mjesečni JOPPD za plaće",
         "due_date": f"{year}-{month:02d}-15", "days_remaining": max(0, 15 - now.day)},
    ]
    # Next month deadlines
    nm = month + 1 if month < 12 else 1
    ny = year if month < 12 else year + 1
    nm_last = monthrange(ny, nm)[1]
    items.append({"name": f"PDV-S {nm}/{ny}", "description": "Sljedeći mjesec",
                  "due_date": f"{ny}-{nm:02d}-{nm_last}", "days_remaining": (nm_last - now.day + last_day) if nm > month else 30})

    if month in (3, 4):  # Yearly deadlines
        items.append({"name": "GFI-POD", "description": "Godišnji financijski izvještaj",
                       "due_date": f"{year}-04-30", "days_remaining": max(0, 120 - now.timetuple().tm_yday + 1)})
        items.append({"name": "PD obrazac", "description": "Prijava poreza na dobit",
                       "due_date": f"{year}-04-30", "days_remaining": max(0, 120 - now.timetuple().tm_yday + 1)})

    items.sort(key=lambda x: x.get("days_remaining", 999))
    return {"items": items}

@app.get("/api/system/status")
async def system_status(user=Depends(get_current_user)):
    llm_stats = state.llm.get_stats() if state.llm else {}
    mem_stats = state.memory.get_stats() if state.memory else {}
    storage_stats = state.storage.get_stats() if state.storage else {}

    return {
        "model": llm_stats.get("model", "N/A"),
        "vllm_status": "online" if llm_stats.get("vllm_running") else "offline (fallback)",
        "memory_used_gb": llm_stats.get("memory", {}).get("total_estimated_gb", "?"),
        "total_tokens": llm_stats.get("total_tokens", 0),
        "call_count": llm_stats.get("call_count", 0),
        "storage": storage_stats,
        "memory_system": mem_stats,
        "llm": llm_stats,
        "uptime_seconds": (datetime.now(timezone.utc) - state.start_time).total_seconds(),
    }

# ═══════════════════════════════════════════
# MONITORING
# ═══════════════════════════════════════════

@app.get("/api/monitor")
async def monitor_full(user=Depends(get_current_user)):
    """Kompletni zdravstveni izvještaj."""
    if state.monitor:
        return state.monitor.get_full_report()
    return {"status": "monitor not initialized"}

@app.get("/api/monitor/memory")
async def monitor_memory(user=Depends(get_current_user)):
    if state.monitor:
        return state.monitor.get_memory_stats()
    return {}

@app.get("/api/monitor/inference")
async def monitor_inference(user=Depends(get_current_user)):
    if state.monitor:
        return state.monitor.get_inference_stats()
    return {}

# ═══════════════════════════════════════════
# BACKUP
# ═══════════════════════════════════════════

@app.get("/api/backups")
async def list_backups(user=Depends(require_permission("backup"))):
    if state.backup:
        return {"backups": state.backup.list_backups(), "stats": state.backup.get_stats()}
    return {"backups": []}

@app.post("/api/backups/daily")
async def create_daily_backup(user=Depends(require_permission("backup"))):
    if state.backup:
        return state.backup.create_backup("daily")
    raise HTTPException(500, "Backup manager nije inicijaliziran")

@app.post("/api/backups/weekly")
async def create_weekly_backup(user=Depends(require_permission("backup"))):
    if state.backup:
        return state.backup.create_backup("weekly")
    raise HTTPException(500, "Backup manager nije inicijaliziran")

@app.post("/api/backups/restore/{backup_name}")
async def restore_backup(backup_name: str, user=Depends(require_permission("backup"))):
    if state.backup:
        return state.backup.restore_backup(backup_name)
    raise HTTPException(500, "Backup manager nije inicijaliziran")

# ═══════════════════════════════════════════
# DPO TRAINING
# ═══════════════════════════════════════════

@app.get("/api/dpo/stats")
async def dpo_stats(user=Depends(require_permission("view_audit"))):
    try:
        from nyx_light.finetune import NightlyDPOTrainer
        dpo = NightlyDPOTrainer()
        return dpo.get_stats()
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.get("/api/dpo/adapters")
async def dpo_adapters(user=Depends(require_permission("update_model"))):
    try:
        from nyx_light.finetune import NightlyDPOTrainer
        dpo = NightlyDPOTrainer()
        return {"adapters": dpo.list_lora_adapters()}
    except Exception as e:
        return {"adapters": [], "error": str(e)}

@app.post("/api/dpo/train")
async def dpo_train_manual(user=Depends(require_permission("update_model"))):
    try:
        from nyx_light.finetune import NightlyDPOTrainer
        dpo = NightlyDPOTrainer()
        result = await dpo.train_nightly()
        return result
    except Exception as e:
        return {"status": "error", "error": str(e)}

# ═══════════════════════════════════════════
# RAG / ZAKONI
# ═══════════════════════════════════════════

@app.get("/api/laws")
async def list_laws(user=Depends(get_current_user)):
    """Lista dostupnih zakona u RAG bazi."""
    laws_dir = Path("data/laws")
    if not laws_dir.exists():
        return {"laws": []}
    laws = []
    for f in sorted(laws_dir.glob("*.md")):
        content = f.read_text(encoding="utf-8")
        # Parse YAML header
        meta = {}
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                for line in parts[1].strip().split("\n"):
                    if ":" in line:
                        k, v = line.split(":", 1)
                        meta[k.strip()] = v.strip()
        laws.append({
            "file": f.name,
            "name": meta.get("zakon", f.stem),
            "nn": meta.get("nn", ""),
            "datum_stupanja": meta.get("datum_stupanja", ""),
            "zadnja_izmjena": meta.get("zadnja_izmjena", ""),
            "size_bytes": f.stat().st_size,
        })
    return {"laws": laws, "count": len(laws)}

@app.get("/api/laws/search")
async def search_laws(q: str = "", user=Depends(get_current_user)):
    """Pretraži zakone (RAG query)."""
    if not q:
        raise HTTPException(400, "Parametar 'q' je obavezan")
    try:
        from nyx_light.rag.legal_rag import LegalRAG
        rag = LegalRAG()
        rag.initialize(download=False)
        results = rag.query(q)
        return {"query": q, "results": results}
    except Exception as e:
        # Fallback: simple text search in law files
        laws_dir = Path("data/laws")
        results = []
        for f in laws_dir.glob("*.md"):
            content = f.read_text(encoding="utf-8")
            if q.lower() in content.lower():
                # Find matching lines
                for i, line in enumerate(content.split("\n")):
                    if q.lower() in line.lower():
                        results.append({"file": f.name, "line": i + 1, "text": line.strip()[:200]})
        return {"query": q, "results": results[:20], "method": "text_search"}

# ═══════════════════════════════════════════
# AUDIT LOG
# ═══════════════════════════════════════════

@app.get("/api/audit")
async def get_audit_log(limit: int = 100, user=Depends(require_permission("view_audit"))):
    if state.auth:
        return {"items": state.auth.get_audit_log(limit)}
    return {"items": []}

# ═══════════════════════════════════════════
# SCHEDULER
# ═══════════════════════════════════════════

@app.get("/api/scheduler/status")
async def scheduler_status(user=Depends(require_permission("view_audit"))):
    if hasattr(state, '_scheduler') and state._scheduler:
        return state._scheduler.get_stats()
    return {"running": False, "note": "Scheduler nije pokrenut"}

@app.post("/api/scheduler/run")
async def scheduler_run_manual(task: str = "all", user=Depends(require_permission("backup"))):
    if hasattr(state, '_scheduler') and state._scheduler:
        try:
            result = await state._scheduler.run_manual(task)
            return result
        except Exception as e:
            return {"status": "error", "error": str(e)}
    # Fallback: run task directly
    if task == "backup" and state.backup:
        return state.backup.create_backup("manual")
    return {"status": "error", "error": "Scheduler nije inicijaliziran"}

# ═══════════════════════════════════════════
# KONTO SEARCH
# ═══════════════════════════════════════════

@app.get("/api/konto/search")
async def search_konto(q: str = "", user=Depends(get_current_user)):
    """Pretraži kontni plan."""
    if not q:
        return {"results": []}
    try:
        from nyx_light.modules.kontiranje.kontni_plan import suggest_konto_by_keyword
        results = suggest_konto_by_keyword(q)
        return {"query": q, "results": results}
    except Exception as e:
        return {"query": q, "results": [], "error": str(e)}

# ═══════════════════════════════════════════
# HEALTH
# ═══════════════════════════════════════════

@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0.0", "time": datetime.now(timezone.utc).isoformat()}

@app.get("/api/health")
async def api_health():
    return {"status": "ok", "storage": state.storage is not None, "auth": state.auth is not None}


# ═══════════════════════════════════════════════════════
# MODULE ROUTER + PAYROLL + KG + METRICS + INGEST + MODULES
# ═══════════════════════════════════════════════════════

@app.post("/api/route")
async def route_message(request: Request, user=Depends(get_current_user)):
    data = await request.json()
    from nyx_light.router import ModuleRouter
    router = ModuleRouter()
    result = router.route(data.get("message", ""), data.get("has_file", False))
    return {"module": result.module, "confidence": result.confidence,
            "sub_intent": result.sub_intent, "entities": result.entities}

@app.get("/api/modules")
async def list_modules(user=Depends(get_current_user)):
    from nyx_light.router import ModuleRouter
    return {"modules": ModuleRouter().get_available_modules()}

@app.post("/api/payroll/calculate")
async def calculate_payroll(request: Request, user=Depends(get_current_user)):
    data = await request.json()
    from nyx_light.modules.place import PayrollCalculator, ObracunPlaceInput, UzdrzavaniClan
    uzdrzavani = [UzdrzavaniClan(tip=u.get("tip", "dijete_1")) for u in data.get("uzdrzavani", [])]
    inp = ObracunPlaceInput(bruto=float(data.get("bruto", 0)), grad=data.get("grad", "zagreb"),
                            uzdrzavani=uzdrzavani, bonus=float(data.get("bonus", 0)),
                            prehrana=float(data.get("prehrana", 0)), prijevoz=float(data.get("prijevoz", 0)))
    r = PayrollCalculator().obracun(inp)
    return {"bruto": r.bruto_ukupno, "mio_i": r.mio_i, "mio_ii": r.mio_ii,
            "dohodak": r.dohodak, "osobni_odbitak": r.osobni_odbitak,
            "porezna_osnovica": r.porezna_osnovica, "porez": r.porez, "prirez": r.prirez,
            "neto": r.neto, "za_isplatu": r.za_isplatu,
            "zdravstveno": r.zdravstveno, "trosak_poslodavca": r.trosak_poslodavca, "detalji": r.detalji}

@app.post("/api/payroll/neto-to-bruto")
async def neto_to_bruto(request: Request, user=Depends(get_current_user)):
    data = await request.json()
    from nyx_light.modules.place import PayrollCalculator, UzdrzavaniClan
    uzdrzavani = [UzdrzavaniClan(tip=u.get("tip", "dijete_1")) for u in data.get("uzdrzavani", [])]
    r = PayrollCalculator().bruto_iz_neto(float(data.get("neto", 0)), data.get("grad", "zagreb"), uzdrzavani)
    return {"bruto_potreban": r.bruto_ukupno, "neto": r.neto, "za_isplatu": r.za_isplatu,
            "trosak_poslodavca": r.trosak_poslodavca}

@app.get("/api/payroll/minimalna")
async def minimalna_placa(grad: str = "zagreb", user=Depends(get_current_user)):
    from nyx_light.modules.place import PayrollCalculator
    r = PayrollCalculator().minimalna_placa(grad)
    return {"bruto": r.bruto_ukupno, "neto": r.neto, "za_isplatu": r.za_isplatu, "grad": grad}

@app.get("/api/payroll/neoporezivi")
async def neoporezivi_primici(user=Depends(get_current_user)):
    from nyx_light.modules.place import NEOPOREZIVI, PRIREZI
    return {"neoporezivi": NEOPOREZIVI, "prirezi": PRIREZI}

@app.get("/api/kg/stats")
async def kg_stats(user=Depends(get_current_user)):
    from nyx_light.kg import KnowledgeGraph
    kg = KnowledgeGraph(); kg.seed_defaults()
    return kg.get_stats()

@app.get("/api/kg/query/{node_type}")
async def kg_query_type(node_type: str, user=Depends(get_current_user)):
    from nyx_light.kg import KnowledgeGraph
    kg = KnowledgeGraph(); kg.seed_defaults()
    return {"nodes": kg.query_by_type(node_type), "type": node_type}

@app.get("/metrics")
async def prometheus_metrics():
    from nyx_light.metrics import metrics
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(metrics.export(), media_type="text/plain; version=0.0.4")

@app.post("/api/laws/ingest")
async def ingest_laws(user=Depends(require_permission("update_model"))):
    from nyx_light.rag.ingest_laws import ingest_all_laws
    return ingest_all_laws()

@app.get("/api/ingest/stats")
async def ingest_stats(user=Depends(require_permission("view_audit"))):
    from nyx_light.ingest.email_watcher import EmailWatcher
    from nyx_light.ingest.folder_watcher import FolderWatcher
    return {"email": EmailWatcher().get_stats(), "folder": FolderWatcher().get_stats()}

@app.post("/api/bank/parse")
async def parse_bank_statement(request: Request, user=Depends(get_current_user)):
    data = await request.json()
    if not data.get("filepath"):
        raise HTTPException(400, "filepath obavezan")
    from nyx_light.modules.bank_parser.parser import BankParser
    try:
        return BankParser().parse(data["filepath"], data.get("bank", ""))
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/api/ios/generate")
async def generate_ios(request: Request, user=Depends(get_current_user)):
    data = await request.json()
    from nyx_light.modules.ios_reconciliation.ios import IOSReconciliation
    return IOSReconciliation().generate_ios_form(
        data.get("client_id", ""), data.get("partner_oib", ""),
        data.get("datum_od", ""), data.get("datum_do", ""))

@app.post("/api/blagajna/validate")
async def validate_blagajna(request: Request, user=Depends(get_current_user)):
    data = await request.json()
    from nyx_light.modules.blagajna.validator import BlagajnaValidator
    return BlagajnaValidator().validate(float(data.get("iznos", 0)), data.get("tip", "izdatak"))

@app.post("/api/putni-nalog/check")
async def check_putni_nalog(request: Request, user=Depends(get_current_user)):
    data = await request.json()
    from nyx_light.modules.putni_nalozi.checker import PutniNalogChecker
    return PutniNalogChecker().validate(
        km=float(data.get("km", 0)), dnevnica=float(data.get("dnevnica", 0)),
        reprezentacija=float(data.get("reprezentacija", 0)))

@app.post("/api/amortizacija/calculate")
async def calculate_amortizacija(request: Request, user=Depends(get_current_user)):
    data = await request.json()
    nabavna = float(data.get("nabavna_vrijednost", 0))
    grupa = str(data.get("grupa", "2"))
    metoda = data.get("metoda", "linearna")
    stope = {"1": 5, "2": 20, "3": 50, "4": 25, "5": 5}
    stopa = stope.get(grupa, 20)
    if metoda == "dvostruka":
        stopa *= 2
    godisnja = round(nabavna * stopa / 100, 2)
    porezno = min(nabavna, 40000) if grupa == "2" else nabavna
    return {"nabavna": nabavna, "grupa": grupa, "stopa_pct": stopa,
            "godisnja": godisnja, "mjesecna": round(godisnja / 12, 2),
            "vijek_god": round(100 / stopa, 1) if stopa else 0,
            "porezno_priznato": porezno}

# ── ERP PULL (Import from CPP/Synesis) ──

@app.get("/api/erp/kontni-plan")
async def erp_kontni_plan(user=Depends(get_current_user)):
    from nyx_light.erp import ERPConnector, ERPConnectionConfig
    conn = ERPConnector(ERPConnectionConfig())
    return {"kontni_plan": conn.pull_kontni_plan()}

@app.get("/api/erp/otvorene-stavke")
async def erp_otvorene(konto: str = "", partner_oib: str = "", user=Depends(get_current_user)):
    from nyx_light.erp import ERPConnector, ERPConnectionConfig
    conn = ERPConnector(ERPConnectionConfig())
    return {"stavke": conn.pull_otvorene_stavke(konto, partner_oib)}

@app.get("/api/erp/saldo/{konto}")
async def erp_saldo(konto: str, user=Depends(get_current_user)):
    from nyx_light.erp import ERPConnector, ERPConnectionConfig
    conn = ERPConnector(ERPConnectionConfig())
    return conn.pull_saldo_konta(konto)

@app.get("/api/erp/bruto-bilanca")
async def erp_bruto_bilanca(period: str = "", user=Depends(get_current_user)):
    from nyx_light.erp import ERPConnector, ERPConnectionConfig
    conn = ERPConnector(ERPConnectionConfig())
    return {"bilanca": conn.pull_bruto_bilanca(period)}

@app.get("/api/erp/partner-kartica/{oib}")
async def erp_partner_kartica(oib: str, user=Depends(get_current_user)):
    from nyx_light.erp import ERPConnector, ERPConnectionConfig
    conn = ERPConnector(ERPConnectionConfig())
    return {"kartica": conn.pull_partner_kartice(oib)}
