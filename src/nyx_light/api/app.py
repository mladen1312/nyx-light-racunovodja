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
        self.session_mgr: Optional[SessionManager] = None
        self.monitor: Optional[SystemMonitor] = None
        self.backup: Optional[BackupManager] = None
        self.llm_queue = None  # LLMRequestQueue
        self.nyx_app = None    # NyxLightApp — centralni orchestrator
        self.executor = None   # ModuleExecutor — most router↔moduli
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
    state.session_mgr = state.sessions  # Alias
    state.monitor = SystemMonitor()
    state.backup = BackupManager()

    # NyxLightApp — centralni orchestrator (spaja SVE module)
    try:
        from nyx_light.app import NyxLightApp
        state.nyx_app = NyxLightApp(db_path="data/nyx.db")
        logger.info("NyxLightApp inicijaliziran (svi moduli spojeni)")
    except Exception as e:
        logger.warning("NyxLightApp not started: %s", e)

    # ModuleExecutor — most između routera i modula
    try:
        from nyx_light.api.module_executor import ModuleExecutor
        state.executor = ModuleExecutor(app=state.nyx_app, storage=state.storage)
        logger.info("ModuleExecutor inicijaliziran (44 modula)")
    except Exception as e:
        logger.warning("ModuleExecutor not started: %s", e)

    # LLM Request Queue — max 3 concurrent, 10/min per user
    try:
        from nyx_light.llm.request_queue import LLMRequestQueue
        state.llm_queue = LLMRequestQueue(max_concurrent=3, max_per_minute=10)
        logger.info("LLM Request Queue: max 3 concurrent, 10/min rate limit")
    except Exception as e:
        logger.warning("LLM Queue not started: %s", e)

    # Start nightly scheduler in background
    try:
        from nyx_light.scheduler import NyxScheduler
        state._scheduler = NyxScheduler()
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
    user_id = user.get("user_id", user.get("username", "unknown"))

    # RAG search — relevantni zakoni
    try:
        from nyx_light.rag.embedded_store import EmbeddedVectorStore
        rag_store = EmbeddedVectorStore()
        rag_results = rag_store.search(req.message, top_k=3)
        if rag_results:
            context.rag_results = [
                {"text": getattr(r, "text", ""), "source": getattr(r, "law_name", ""),
                 "article": getattr(r, "article_number", ""),
                 "score": getattr(r, "score", 0)}
                for r in rag_results if getattr(r, "text", "")
            ]
    except Exception as e:
        logger.debug("RAG search: %s", e)

    # ═══════════════════════════════════════════
    # MODULE ROUTING + EXECUTION (NOVA INTEGRACIJA)
    # ═══════════════════════════════════════════
    module_result = None
    try:
        from nyx_light.router import ModuleRouter
        route = ModuleRouter().route(req.message)

        # Ako router ima visoku confidence (>0.6), IZVRŠI modul
        if route.confidence > 0.6 and route.module != "general" and state.executor:
            module_result = state.executor.execute(
                module=route.module,
                sub_intent=route.sub_intent,
                data=route.entities,
                client_id=req.client_id,
                user_id=user_id,
            )

            # Dodaj rezultat modula kao kontekst za LLM
            if module_result and module_result.llm_context:
                context.semantic_facts.append(
                    f"[Modul {route.module} ({route.confidence:.0%}): "
                    f"{module_result.llm_context}]"
                )
            if module_result and module_result.data:
                context.pipeline_context = (
                    f"Modul '{route.module}' izvršen. Rezultat: {module_result.summary}. "
                    f"Podaci: {str(module_result.data)[:500]}"
                )
        elif route.confidence > 0.4 and route.module != "general":
            # Srednja confidence — dodaj hint ali ne izvršavaj
            context.semantic_facts.append(
                f"[Router: moguć modul '{route.module}' "
                f"(confidence: {route.confidence:.0%}) — korisnik možda želi ovaj modul]"
            )
    except Exception as e:
        logger.debug("Module routing/execution: %s", e)

    # Call LLM — through request queue for fair scheduling
    try:
        if state.llm_queue:
            response = await state.llm_queue.submit(
                user_id,
                state.chat_bridge.chat,
                req.message, session_id, context,
            )
        else:
            response = await state.chat_bridge.chat(req.message, session_id, context)
    except Exception as e:
        error_msg = str(e)
        if "Previše zahtjeva" in error_msg or "rate" in error_msg.lower():
            return {"content": f"⏳ {error_msg}", "rate_limited": True}
        elif "preopterećen" in error_msg.lower() or "queue" in error_msg.lower():
            return {"content": f"⏳ {error_msg}", "queue_full": True}
        # Fallback — try direct call
        response = await state.chat_bridge.chat(req.message, session_id, context)

    # Store in episodic memory
    state.memory.l1_episodic.store(
        query=req.message,
        response=response.content[:500],
        user_id=user["user_id"],
        session_id=session_id,
    )

    result = {
        "content": response.content,
        "tokens": response.tokens_used,
        "latency_ms": round(response.latency_ms, 1),
        "model": response.model,
    }

    # Dodaj module metadata ako je modul izvršen
    if module_result:
        result["module_used"] = module_result.module
        result["module_action"] = module_result.action
        result["module_success"] = module_result.success
        if module_result.data:
            result["module_data"] = module_result.data

    return result

# WebSocket chat (streaming) — s JWT autentikacijom
@app.websocket("/api/ws/chat")
async def ws_chat(ws: WebSocket):
    # ── 1. Autentikacija ──
    token = ws.query_params.get("token", "")
    if not token:
        # Provjeri i subprotocol header
        token = ws.headers.get("sec-websocket-protocol", "")

    user = None
    if token and state.auth:
        try:
            user = state.auth.verify_token(token)
        except Exception:
            pass

    if not user:
        await ws.close(code=4001, reason="Niste prijavljeni")
        return

    await ws.accept()
    user_id = user.get("user_id", user.get("username", "unknown"))
    session_id = f"ws_{user_id}"

    # Track WebSocket connection
    state.ws_connections[user_id] = ws
    logger.info("WebSocket: %s spojen", user_id)

    try:
        while True:
            data = await ws.receive_json()
            msg = data.get("message", "")
            if not msg:
                continue

            # ── 2. Rate limit check ──
            if hasattr(state, 'llm_queue') and state.llm_queue:
                user_stats = state.llm_queue.get_user_stats(user_id)
                if user_stats["rate_remaining"] <= 0:
                    await ws.send_json({
                        "type": "error",
                        "content": f"Previše zahtjeva. Pokušajte za {int(user_stats['rate_reset_in'])}s."
                    })
                    continue

            # ── 3. Module Routing + Execution (ista logika kao /api/chat) ──
            context = ChatContext()
            client_id = data.get("client_id", "")

            # Memory kontekst
            if client_id:
                hint = state.memory.get_kontiranje_hint(client_id)
                if hint:
                    context.semantic_facts.append(hint["hint"])
                context.client_info = {"id": client_id}

            # L1 episodic
            try:
                today_eps = state.memory.l1_episodic.search_today(msg[:50])
                for ep in today_eps[:3]:
                    context.episodic_recent.append(f"Ranije: {ep.query} → {ep.response[:100]}")
            except Exception:
                pass

            # RAG
            try:
                from nyx_light.rag.embedded_store import EmbeddedVectorStore
                rag_store = EmbeddedVectorStore()
                rag_results = rag_store.search(msg, top_k=3)
                if rag_results:
                    context.rag_results = [
                        {"text": getattr(r, "text", ""), "source": getattr(r, "law_name", ""),
                         "article": getattr(r, "article_number", ""),
                         "score": getattr(r, "score", 0)}
                        for r in rag_results if getattr(r, "text", "")
                    ]
            except Exception:
                pass

            # Module Executor — ISTA LOGIKA KAO /api/chat
            module_result = None
            try:
                from nyx_light.router import ModuleRouter
                route = ModuleRouter().route(msg)

                if route.confidence > 0.6 and route.module != "general" and state.executor:
                    module_result = state.executor.execute(
                        module=route.module,
                        sub_intent=route.sub_intent,
                        data=route.entities,
                        client_id=client_id,
                        user_id=user_id,
                    )
                    if module_result and module_result.llm_context:
                        context.semantic_facts.append(
                            f"[Modul {route.module} ({route.confidence:.0%}): "
                            f"{module_result.llm_context}]"
                        )
                    if module_result and module_result.data:
                        context.pipeline_context = (
                            f"Modul '{route.module}' izvršen. Rezultat: {module_result.summary}. "
                            f"Podaci: {str(module_result.data)[:500]}"
                        )
                elif route.confidence > 0.4 and route.module != "general":
                    context.semantic_facts.append(
                        f"[Router: moguć modul '{route.module}' "
                        f"(confidence: {route.confidence:.0%})]"
                    )
            except Exception as e:
                logger.debug("WS module routing: %s", e)

            # ── 4. Stream LLM response s kontekstom ──
            full = ""
            async for token_str in state.chat_bridge.chat_stream(msg, session_id, context):
                full += token_str
                await ws.send_json({"type": "token", "content": token_str})

            done_msg = {"type": "done", "content": full}
            if module_result:
                done_msg["module_used"] = module_result.module
                done_msg["module_action"] = module_result.action
                done_msg["module_success"] = module_result.success
                if module_result.data:
                    done_msg["module_data"] = module_result.data
            await ws.send_json(done_msg)

            # ── 5. Episodic memory ──
            try:
                state.memory.l1_episodic.store(
                    query=msg, response=full[:500],
                    user_id=user_id, session_id=session_id,
                )
            except Exception:
                pass

            # ── 6. Track u session manageru ──
            if state.session_mgr:
                state.session_mgr.record_message(
                    state.session_mgr.get_session_by_user(user_id).session_id
                    if state.session_mgr.get_session_by_user(user_id) else ""
                )

    except WebSocketDisconnect:
        state.ws_connections.pop(user_id, None)
        logger.info("WebSocket: %s odspojio se", user_id)
    except Exception as e:
        state.ws_connections.pop(user_id, None)
        logger.error("WebSocket error %s: %s", user_id, e)

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
    from nyx_light.modules.bank_parser.parser import BankStatementParser
    try:
        return BankStatementParser().parse(data["filepath"], data.get("bank", ""))
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
    bv = BlagajnaValidator()
    if data.get("pocetno_stanje"):
        bv.set_pocetno_stanje(float(data["pocetno_stanje"]))
    return bv.validate_and_report(data)

@app.post("/api/blagajna/dnevni-izvjestaj")
async def blagajna_dnevni(request: Request, user=Depends(get_current_user)):
    data = await request.json()
    from nyx_light.modules.blagajna.validator import BlagajnaValidator
    bv = BlagajnaValidator()
    # Process all nalozi for the day
    nalozi = data.get("nalozi", [])
    if data.get("pocetno_stanje"):
        bv.set_pocetno_stanje(float(data["pocetno_stanje"]))
    results = [bv.validate_and_report(n) for n in nalozi]
    report = bv.dnevni_izvjestaj(data.get("datum", ""), float(data.get("pocetno_stanje", 0)))
    return {"nalozi": results, "izvjestaj": {
        "datum": report.datum, "pocetno": report.pocetno_stanje,
        "uplate": report.ukupno_uplate, "isplate": report.ukupno_isplate,
        "zavrsno": report.zavrsno_stanje, "br_uplatnica": report.broj_uplatnica,
        "br_isplatnica": report.broj_isplatnica,
    }}

@app.post("/api/putni-nalog/calculate")
async def calculate_putni_nalog(request: Request, user=Depends(get_current_user)):
    data = await request.json()
    from nyx_light.modules.putni_nalozi.checker import PutniNalogChecker
    pnc = PutniNalogChecker()
    pn = pnc.calculate(data)
    return pnc.to_dict(pn)

@app.get("/api/putni-nalog/dnevnice")
async def list_dnevnice(user=Depends(get_current_user)):
    from nyx_light.modules.putni_nalozi.checker import PutniNalogChecker
    return {"dnevnice": PutniNalogChecker().list_zemlje(), "km_naknada_eur": 0.40}

@app.post("/api/putni-nalog/check")
async def check_putni_nalog(request: Request, user=Depends(get_current_user)):
    """Legacy endpoint — redirects to calculate."""
    data = await request.json()
    from nyx_light.modules.putni_nalozi.checker import PutniNalogChecker
    pnc = PutniNalogChecker()
    pn = pnc.calculate(data)
    return pnc.to_dict(pn)

@app.post("/api/kontiranje/suggest")
async def suggest_kontiranje(request: Request, user=Depends(get_current_user)):
    data = await request.json()
    from nyx_light.modules.kontiranje.engine import KontiranjeEngine
    engine = KontiranjeEngine()
    # Try to get memory hint
    memory_hint = None
    if data.get("supplier_oib") and state.memory:
        memory_hint = state.memory.get_kontiranje_hint(
            data.get("client_id", ""), data.get("supplier_oib", ""))
    result = engine.suggest_konto(
        description=data.get("opis", ""),
        tip_dokumenta=data.get("tip", "ulazni"),
        client_id=data.get("client_id", ""),
        supplier_oib=data.get("supplier_oib", ""),
        supplier_name=data.get("supplier_name", data.get("dobavljac", "")),
        iznos=float(data.get("iznos", 0)),
        pdv_stopa=float(data.get("pdv_stopa", 25)),
        memory_hint=memory_hint,
    )
    return {
        "duguje": result.duguje_konto, "duguje_naziv": result.duguje_naziv,
        "potrazuje": result.potrazuje_konto, "potrazuje_naziv": result.potrazuje_naziv,
        "pdv_konto": result.pdv_konto, "pdv_iznos": result.pdv_iznos,
        "confidence": result.confidence, "source": result.source,
        "rule_id": result.rule_id, "napomena": result.napomena,
        "alternativni": result.alternativni,
        "requires_approval": result.requires_approval,
    }

@app.post("/api/kontiranje/batch")
async def batch_kontiranje(request: Request, user=Depends(get_current_user)):
    data = await request.json()
    from nyx_light.modules.kontiranje.engine import KontiranjeEngine
    engine = KontiranjeEngine()
    stavke = data.get("stavke", [])
    results = engine.suggest_batch(stavke, data.get("client_id", ""))
    return {"results": [
        {"duguje": r.duguje_konto, "potrazuje": r.potrazuje_konto,
         "confidence": r.confidence, "source": r.source, "napomena": r.napomena}
        for r in results
    ], "stats": engine.get_stats()}

@app.post("/api/kontiranje/search")
async def search_konta(request: Request, user=Depends(get_current_user)):
    data = await request.json()
    from nyx_light.modules.kontiranje.engine import suggest_konto_by_keyword
    return {"results": suggest_konto_by_keyword(data.get("keyword", ""), int(data.get("limit", 10)))}

@app.get("/api/llm/queue-stats")
async def llm_queue_stats(user=Depends(get_current_user)):
    if state.llm_queue:
        stats = state.llm_queue.get_stats()
        user_stats = state.llm_queue.get_user_stats(user.get("user_id", ""))
        return {"queue": stats, "user": user_stats}
    return {"queue": {"status": "disabled"}, "user": {}}

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

# ═══════════════════════════════════════════
# SPRINT 18: New Endpoints
# ═══════════════════════════════════════════

# ── e-Račun ──

@app.post("/api/e-racun/generate")
async def generate_e_racun(data: dict, user=Depends(get_current_user)):
    from nyx_light.modules.e_racun import ERacunGenerator, ERacunData, ERacunStavka
    gen = ERacunGenerator()
    stavke = [ERacunStavka(**s) for s in data.get("stavke", [])]
    edata = ERacunData(
        broj_racuna=data.get("broj_racuna", ""),
        datum_izdavanja=data.get("datum_izdavanja", ""),
        datum_dospijeca=data.get("datum_dospijeca", ""),
        izdavatelj_naziv=data.get("izdavatelj_naziv", ""),
        izdavatelj_oib=data.get("izdavatelj_oib", ""),
        izdavatelj_iban=data.get("izdavatelj_iban", ""),
        primatelj_naziv=data.get("primatelj_naziv", ""),
        primatelj_oib=data.get("primatelj_oib", ""),
        stavke=stavke,
    )
    xml = gen.generate_ubl(edata)
    summary = gen.generate_summary(edata)
    return {"xml": xml, "summary": summary}

@app.post("/api/e-racun/validate")
async def validate_e_racun(data: dict, user=Depends(get_current_user)):
    from nyx_light.modules.e_racun import ERacunGenerator, ERacunData, ERacunStavka
    gen = ERacunGenerator()
    stavke = [ERacunStavka(**s) for s in data.get("stavke", [])]
    edata = ERacunData(
        broj_racuna=data.get("broj_racuna", ""),
        izdavatelj_oib=data.get("izdavatelj_oib", ""),
        primatelj_oib=data.get("primatelj_oib", ""),
        stavke=stavke,
    )
    errors = gen.validate(edata)
    return {"valid": len(errors) == 0, "errors": errors}

# ── PDV Prijava ──

@app.post("/api/pdv-prijava/generate")
async def generate_pdv_prijava(data: dict, user=Depends(get_current_user)):
    from nyx_light.modules.pdv_prijava import PDVPrijavaEngine, PDVStavka
    engine = PDVPrijavaEngine()
    try:
        # Build PDVStavka list from incoming data
        stavke_raw = data.get("stavke", [])
        stavke = []
        for s in stavke_raw:
            stavke.append(PDVStavka(
                tip=s.get("tip", "izlazni"),
                broj_racuna=s.get("broj_racuna", ""),
                osnovica=s.get("osnovica", 0),
                pdv_stopa=s.get("pdv_stopa", 25),
                pdv_iznos=s.get("pdv_iznos", 0),
                oib_partnera=s.get("oib_partnera", ""),
            ))
        # If no stavke but has top-level fields (quick mode)
        if not stavke and data.get("isporuke_25"):
            stavke.append(PDVStavka(
                tip="izlazni",
                osnovica=data.get("isporuke_25", 0),
                pdv_stopa=25, pdv_iznos=data.get("pdv_25", 0),
            ))
        ppo = engine.calculate(
            stavke=stavke,
            oib_obveznika=data.get("oib_obveznik", ""),
            naziv_obveznika=data.get("naziv_obveznik", ""),
            period=data.get("period_od", "")[:7] if data.get("period_od") else "",
        )
        return engine.to_dict(ppo)
    except Exception as e:
        return {"error": str(e), "status": "fallback", "oib": data.get("oib_obveznik", "")}

# ── JOPPD XML ──

@app.post("/api/joppd/generate-xml")
async def generate_joppd_xml(data: dict, user=Depends(get_current_user)):
    try:
        from nyx_light.modules.joppd import JOPPDGenerator, JOPPDObrazac, JOPPDStavka
        from datetime import datetime
        gen = JOPPDGenerator()
        radnici = data.get("radnici", [])
        now = datetime.now()

        obrazac = JOPPDObrazac(
            oznaka=f"{now.year}-{now.month:03d}",
            datum_predaje=now.strftime("%Y-%m-%d"),
            datum_isplate=data.get("datum_obracuna", now.strftime("%Y-%m-%d")),
            oib_obveznika=data.get("obveznik_oib", ""),
            naziv_obveznika=data.get("obveznik_naziv", ""),
        )
        for i, r in enumerate(radnici, 1):
            obrazac.stavke.append(JOPPDStavka(
                redni_broj=i,
                oib_primatelja=r.get("oib", ""),
                ime_prezime=r.get("ime_prezime", ""),
                bruto=r.get("bruto", 0),
                mio_stup_1=r.get("mio_i", 0),
                mio_stup_2=r.get("mio_ii", 0),
                dohodak=r.get("dohodak", 0),
                porez=r.get("porez", 0),
                prirez=r.get("prirez", 0),
                neto=r.get("neto", 0),
            ))
        xml_str = gen.to_xml(obrazac)
        result = gen.to_dict(obrazac)
        result["xml"] = xml_str
        return result
    except Exception as e:
        return {"status": "error", "error": str(e), "data": data}

# ── Kompenzacije ──

@app.post("/api/kompenzacije/find")
async def find_kompenzacije(data: dict, user=Depends(get_current_user)):
    from nyx_light.modules.kompenzacije import KompenzacijeEngine, OtvorenaStavka
    engine = KompenzacijeEngine()
    stavke = [OtvorenaStavka(**s) for s in data.get("stavke", [])]
    pairs = engine.find_bilateral(stavke)
    return {"pairs": [{
        "partner_oib": p.partner_oib, "partner_naziv": p.partner_naziv,
        "nas_dug": p.nas_dug, "njihov_dug": p.njihov_dug,
        "kompenzabilno": p.kompenzabilno,
    } for p in pairs]}

@app.post("/api/kompenzacije/execute")
async def execute_kompenzacija(data: dict, user=Depends(get_current_user)):
    from nyx_light.modules.kompenzacije import (
        KompenzacijeEngine, KompenzacijaPar, OtvorenaStavka
    )
    engine = KompenzacijeEngine()
    par = KompenzacijaPar(
        partner_oib=data.get("partner_oib", ""),
        partner_naziv=data.get("partner_naziv", ""),
        nas_dug=data.get("nas_dug", 0),
        njihov_dug=data.get("njihov_dug", 0),
        kompenzabilno=data.get("kompenzabilno", 0),
    )
    izjava = engine.execute_bilateral(par, data.get("nas_oib", ""), data.get("nas_naziv", ""))
    knjizenja = engine.generate_knjizenje(izjava)
    return {"izjava": {"broj": izjava.broj, "iznos": izjava.iznos, "datum": izjava.datum},
            "knjizenja": knjizenja}

# ── Reports ──

@app.post("/api/reports/bilanca")
async def report_bilanca(data: dict, user=Depends(get_current_user)):
    from nyx_light.modules.reports import ReportGenerator
    gen = ReportGenerator(data.get("firma", ""), data.get("oib", ""))
    path = gen.generate_bilanca(data, data.get("period", ""))
    return {"path": path, "status": "generated"}

@app.post("/api/reports/rdg")
async def report_rdg(data: dict, user=Depends(get_current_user)):
    from nyx_light.modules.reports import ReportGenerator
    gen = ReportGenerator(data.get("firma", ""), data.get("oib", ""))
    path = gen.generate_rdg(data, data.get("period", ""))
    return {"path": path, "status": "generated"}

@app.post("/api/reports/bruto-bilanca")
async def report_bruto_bilanca(data: dict, user=Depends(get_current_user)):
    from nyx_light.modules.reports import ReportGenerator
    gen = ReportGenerator(data.get("firma", ""), data.get("oib", ""))
    path = gen.generate_bruto_bilanca(data.get("stavke", []), data.get("period", ""))
    return {"path": path, "status": "generated"}

@app.post("/api/reports/pdv-recap")
async def report_pdv_recap(data: dict, user=Depends(get_current_user)):
    from nyx_light.modules.reports import ReportGenerator
    gen = ReportGenerator(data.get("firma", ""), data.get("oib", ""))
    path = gen.generate_pdv_recap(data, data.get("period", ""))
    return {"path": path, "status": "generated"}

# ── Audit Export ──

@app.get("/api/audit/export")
async def audit_export(format: str = "json", period_from: str = "",
                       period_to: str = "", user_filter: str = "",
                       user=Depends(get_current_user)):
    from nyx_light.audit.export import AuditExporter
    exporter = AuditExporter()
    entries = exporter.get_entries(period_from=period_from, period_to=period_to,
                                   user=user_filter)
    if format == "xlsx":
        path = exporter.export_excel(entries)
        return {"path": path, "count": len(entries)}
    elif format == "csv":
        path = exporter.export_csv(entries)
        return {"path": path, "count": len(entries)}
    else:
        return {"entries": entries, "count": len(entries),
                "summary": exporter.summary(entries)}

@app.get("/api/audit/summary")
async def audit_summary(period_from: str = "", period_to: str = "",
                        user=Depends(get_current_user)):
    from nyx_light.audit.export import AuditExporter
    exporter = AuditExporter()
    entries = exporter.get_entries(period_from=period_from, period_to=period_to)
    return exporter.summary(entries)

# ── Notifications ──

@app.get("/api/notifications")
async def get_notifications(user=Depends(get_current_user)):
    from nyx_light.notifications import NotificationManager
    mgr = NotificationManager()
    return {"notifications": mgr.get_all(user["username"]),
            "unread": len(mgr.get_unread(user["username"]))}

@app.post("/api/notifications/read/{notification_id}")
async def mark_notification_read(notification_id: str, user=Depends(get_current_user)):
    from nyx_light.notifications import NotificationManager
    mgr = NotificationManager()
    mgr.mark_read(user["username"], notification_id)
    return {"status": "ok"}

@app.post("/api/notifications/read-all")
async def mark_all_read(user=Depends(get_current_user)):
    from nyx_light.notifications import NotificationManager
    mgr = NotificationManager()
    count = mgr.mark_all_read(user["username"])
    return {"marked": count}

# ── WebSocket Notifications ──

@app.websocket("/api/ws/notifications")
async def ws_notifications(ws: WebSocket):
    await ws.accept()
    from nyx_light.notifications import NotificationManager
    mgr = NotificationManager()
    username = "anonymous"
    try:
        # Wait for auth message
        data = await ws.receive_json()
        username = data.get("username", "anonymous")
        await mgr.register(username, ws)
        while True:
            msg = await ws.receive_json()
            if msg.get("type") == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        await mgr.unregister(username, ws)

# ── Pipeline ──

@app.post("/api/pipeline/ingest")
async def pipeline_ingest(data: dict, user=Depends(get_current_user)):
    from nyx_light.pipeline.multi_client import MultiClientPipeline
    pipeline = MultiClientPipeline()
    doc = pipeline.ingest(
        filepath=data.get("filepath", ""),
        source=data.get("source", "api"),
        text_content=data.get("text_content", ""),
        client_hint=data.get("client_id", ""),
    )
    return {"doc_id": doc.doc_id, "type": doc.detected_type,
            "client": doc.detected_client_name, "module": doc.assigned_module,
            "confidence": doc.confidence}

@app.get("/api/pipeline/queue")
async def pipeline_queue(status: str = "", client_id: str = "",
                         user=Depends(get_current_user)):
    from nyx_light.pipeline.multi_client import MultiClientPipeline
    pipeline = MultiClientPipeline()
    return {"queue": pipeline.get_queue(status, client_id),
            "stats": pipeline.get_stats()}

# ── Dashboard Chart Data ──

@app.get("/api/dashboard/chart-data")
async def dashboard_chart_data(period: str = "week", user=Depends(get_current_user)):
    """Podaci za Chart.js grafove na dashboardu."""
    from datetime import datetime, timedelta
    import random

    now = datetime.now()
    if period == "week":
        labels = [(now - timedelta(days=6-i)).strftime("%d.%m.") for i in range(7)]
        days = 7
    elif period == "month":
        labels = [(now - timedelta(days=29-i)).strftime("%d.%m.") for i in range(30)]
        days = 30
    else:
        labels = [f"Mj {i+1}" for i in range(12)]
        days = 12

    # Pull real stats from bookings db if available
    try:
        bookings_data = []
        approvals_data = []
        for label in labels:
            # Placeholder — in production query SQLite
            bookings_data.append(random.randint(5, 25))
            approvals_data.append(random.randint(3, 20))
    except Exception:
        bookings_data = [0] * len(labels)
        approvals_data = [0] * len(labels)

    return {
        "bookings_chart": {
            "labels": labels,
            "datasets": [
                {"label": "Knjiženja", "data": bookings_data, "color": "#6366f1"},
                {"label": "Odobrena", "data": approvals_data, "color": "#22c55e"},
            ]
        },
        "module_usage": {
            "labels": ["Chat", "Bank", "Računi", "IOS", "Plaće", "RAG"],
            "data": [random.randint(10, 80) for _ in range(6)],
        },
        "client_distribution": {
            "labels": ["Klijent A", "Klijent B", "Klijent C", "Ostali"],
            "data": [35, 28, 22, 15],
        },
    }

# ── Audit Query ──

@app.get("/api/audit/query")
async def audit_query(event_type: str = "", user_filter: str = "",
                      date_from: str = "", date_to: str = "",
                      severity: str = "", limit: int = 50,
                      offset: int = 0, user=Depends(get_current_user)):
    """Pretraži audit trail."""
    try:
        from nyx_light.audit import AuditLogger
        audit = AuditLogger()
        entries = audit.query(
            event_type=event_type, user=user_filter,
            date_from=date_from, date_to=date_to,
            severity=severity, limit=limit, offset=offset)
        stats = audit.get_stats()
        return {"entries": entries, "total": stats["total_entries"], "stats": stats}
    except Exception as e:
        return {"entries": [], "total": 0, "error": str(e)}

@app.get("/api/audit/stats")
async def audit_stats(user=Depends(get_current_user)):
    try:
        from nyx_light.audit import AuditLogger
        return AuditLogger().get_stats()
    except Exception as e:
        return {"total_entries": 0, "error": str(e)}

# ── Kompenzacije extended ──

@app.post("/api/kompenzacije/multilateral")
async def kompenzacije_multilateral(data: dict, user=Depends(get_current_user)):
    """Pronađi multilateralnu kompenzaciju."""
    from nyx_light.modules.kompenzacije import KompenzacijeEngine, OtvorenaStavka
    engine = KompenzacijeEngine()
    stavke_po_tvrtki = {}
    for tvrtka in data.get("tvrtke", []):
        oib = tvrtka.get("oib", "")
        stavke = [OtvorenaStavka(**s) for s in tvrtka.get("stavke", [])]
        stavke_po_tvrtki[oib] = stavke
    result = engine.find_multilateral(stavke_po_tvrtki)
    if result:
        return {"found": True, "sudionici": result.sudionici,
                "ukupno": result.ukupno_kompenzirano, "lanac": result.lanac}
    return {"found": False}

# ═══════════════════════════════════════════
# BLAGAJNA ENDPOINTS
# ═══════════════════════════════════════════

@app.post("/api/blagajna/nalog")
async def blagajna_nalog(request: Request, user=Depends(get_current_user)):
    """Kreiraj blagajnički nalog."""
    data = await request.json()
    from nyx_light.modules.blagajna.validator import BlagajnaValidator
    bv = BlagajnaValidator()
    nalog = bv.kreiraj_nalog(
        tip=data.get("tip", "isplatnica"),
        iznos=float(data.get("iznos", 0)),
        opis=data.get("opis", ""),
        partner=data.get("partner", ""),
        partner_oib=data.get("partner_oib", ""),
        kategorija=data.get("kategorija", "ostalo"),
        dokument_ref=data.get("dokument_ref", ""),
    )
    return {
        "broj": nalog.redni_broj, "tip": nalog.tip, "iznos": nalog.iznos,
        "konto_duguje": nalog.konto_duguje, "konto_potrazuje": nalog.konto_potrazuje,
        "valid": len(nalog.validacijske_greske) == 0,
        "greske": nalog.validacijske_greske, "upozorenja": nalog.upozorenja,
        "saldo": bv.get_saldo(),
    }

# ═══════════════════════════════════════════
# PUTNI NALOZI ENDPOINTS (extended)
# ═══════════════════════════════════════════

@app.post("/api/putni-nalog/create")
async def putni_nalog_create(request: Request, user=Depends(get_current_user)):
    """Kreiraj i obračunaj putni nalog."""
    data = await request.json()
    from nyx_light.modules.putni_nalozi.checker import PutniNaloziChecker
    pnc = PutniNaloziChecker()
    pn = pnc.kreiraj_putni_nalog(
        zaposlenik=data.get("zaposlenik", ""),
        odrediste=data.get("odrediste", ""),
        svrha=data.get("svrha", ""),
        datum_polaska=data.get("datum_polaska", ""),
        vrijeme_polaska=data.get("vrijeme_polaska", "08:00"),
        datum_povratka=data.get("datum_povratka", ""),
        vrijeme_povratka=data.get("vrijeme_povratka", "17:00"),
        km_ukupno=float(data.get("km_ukupno", 0)),
        prijevozno_sredstvo=data.get("prijevozno_sredstvo", "osobni_auto"),
        zemlja=data.get("zemlja", "rh"),
        nocenja=int(data.get("nocenja", 0)),
        troskovi=data.get("troskovi", []),
        akontacija=float(data.get("akontacija", 0)),
        relacija=data.get("relacija", ""),
    )
    return pnc.to_dict(pn)

@app.get("/api/putni-nalog/zemlje")
async def putni_nalog_zemlje(user=Depends(get_current_user)):
    """Lista svih zemalja s dnevnicama."""
    from nyx_light.modules.putni_nalozi.checker import PutniNaloziChecker
    return {"zemlje": PutniNaloziChecker().list_zemlje()}

# ═══════════════════════════════════════════
# POREZ NA DOBIT ENDPOINTS
# ═══════════════════════════════════════════

@app.post("/api/porez-dobit/calculate")
async def porez_dobit_calc(request: Request, user=Depends(get_current_user)):
    """Izračunaj PD obrazac."""
    data = await request.json()
    from nyx_light.modules.porez_dobit import PorezNaDobitEngine
    engine = PorezNaDobitEngine()
    pd = engine.calculate(
        prihodi=float(data.get("prihodi", 0)),
        rashodi=float(data.get("rashodi", 0)),
        reprezentacija=float(data.get("reprezentacija", 0)),
        amortizacija_iznad=float(data.get("amortizacija_iznad", 0)),
        kazne=float(data.get("kazne", 0)),
        osobni_auto_30=float(data.get("osobni_auto_30", 0)),
        darovanja_iznad=float(data.get("darovanja_iznad", 0)),
        otpis_nepriznati=float(data.get("otpis_nepriznati", 0)),
        dividende=float(data.get("dividende", 0)),
        reinvestirana_dobit=float(data.get("reinvestirana_dobit", 0)),
        preneseni_gubitak=float(data.get("preneseni_gubitak", 0)),
        placeni_predujmovi=float(data.get("placeni_predujmovi", 0)),
    )
    return engine.to_dict(pd)

# ═══════════════════════════════════════════
# GFI ENDPOINTS
# ═══════════════════════════════════════════

@app.post("/api/gfi/bilanca")
async def gfi_bilanca(request: Request, user=Depends(get_current_user)):
    """Generiraj bilancu."""
    data = await request.json()
    from nyx_light.modules.gfi_xml import GFIXMLGenerator
    gen = GFIXMLGenerator()
    izvj = gen.generate_bilanca(
        data=data.get("aop", {}),
        prethodno=data.get("prethodno", {}),
        oib=data.get("oib", ""), naziv=data.get("naziv", ""),
        godina=int(data.get("godina", 0)),
    )
    return {"izvjestaj": gen.to_dict(izvj), "xml": gen.to_xml(izvj)}

@app.post("/api/gfi/rdg")
async def gfi_rdg(request: Request, user=Depends(get_current_user)):
    """Generiraj RDG."""
    data = await request.json()
    from nyx_light.modules.gfi_xml import GFIXMLGenerator
    gen = GFIXMLGenerator()
    izvj = gen.generate_rdg(
        data=data.get("aop", {}),
        prethodno=data.get("prethodno", {}),
        oib=data.get("oib", ""), naziv=data.get("naziv", ""),
    )
    return {"izvjestaj": gen.to_dict(izvj), "xml": gen.to_xml(izvj)}

# ═══════════════════════════════════════════
# LLM QUEUE STATS (Admin)
# ═══════════════════════════════════════════

@app.get("/api/queue/stats")
async def queue_stats(user=Depends(get_current_user)):
    """LLM request queue statistike."""
    if state.llm_queue:
        return state.llm_queue.get_stats()
    return {"status": "queue_not_active", "note": "Direct LLM calls (no queueing)"}

@app.get("/api/queue/user/{user_id}")
async def queue_user_stats(user_id: str, user=Depends(get_current_user)):
    """Per-user queue statistike."""
    if state.llm_queue:
        return state.llm_queue.get_user_stats(user_id)
    return {"status": "queue_not_active"}


# ═══════════════════════════════════════════
# MODULE EXECUTOR — UNIFIED ENDPOINT
# ═══════════════════════════════════════════

@app.post("/api/module/execute")
async def execute_module(request: Request, user=Depends(get_current_user)):
    """Izvrši bilo koji modul putem unified endpointa."""
    data = await request.json()
    module = data.get("module", "")
    if not module:
        raise HTTPException(400, "Nedostaje 'module' parametar")
    if not state.executor:
        raise HTTPException(503, "ModuleExecutor nije inicijaliziran")
    result = state.executor.execute(
        module=module,
        sub_intent=data.get("sub_intent", ""),
        data=data.get("data", {}),
        client_id=data.get("client_id", ""),
        user_id=user.get("user_id", ""),
    )
    return {"success": result.success, "module": result.module, "action": result.action,
            "data": result.data, "summary": result.summary, "errors": result.errors}

@app.get("/api/module/list")
async def list_all_modules(user=Depends(get_current_user)):
    """Lista svih dostupnih modula."""
    if state.executor:
        return {"modules": state.executor.get_available_modules(), "count": len(state.executor.get_available_modules())}
    from nyx_light.router import ModuleRouter
    return {"modules": ModuleRouter().get_available_modules()}

@app.get("/api/module/stats")
async def module_stats(user=Depends(get_current_user)):
    """Statistike izvršavanja modula."""
    stats = {}
    if state.executor:
        stats["executor"] = state.executor.get_stats()
    return stats

# ═══════════════════════════════════════════
# MODUL: OSNOVNA SREDSTVA (Amortizacija)
# ═══════════════════════════════════════════

@app.post("/api/osnovna-sredstva/depreciation")
async def calculate_depreciation(request: Request, user=Depends(get_current_user)):
    data = await request.json()
    from nyx_light.modules.osnovna_sredstva import OsnovnaSredstvaEngine
    engine = OsnovnaSredstvaEngine()
    result = engine.calculate_depreciation(
        nabavna_vrijednost=data.get("nabavna_vrijednost", 0),
        skupina=data.get("skupina", ""),
        datum_nabave=data.get("datum_nabave", ""),
        naziv=data.get("naziv", ""),
    )
    return result

# ═══════════════════════════════════════════
# MODUL: PAYROLL (full engine)
# ═══════════════════════════════════════════

@app.post("/api/payroll/full-calculate")
async def payroll_full(request: Request, user=Depends(get_current_user)):
    data = await request.json()
    from nyx_light.modules.payroll import PayrollEngine, Employee
    engine = PayrollEngine()
    emp = Employee(**data.get("employee", {})) if data.get("employee") else None
    if emp:
        result = engine.calculate(emp)
        return result if isinstance(result, dict) else {"raw": str(result)}
    return {"error": "Potrebni podaci zaposlenika (bruto, osobni_odbitak, prirez...)"}

# ═══════════════════════════════════════════
# MODUL: FAKTURIRANJE
# ═══════════════════════════════════════════

@app.post("/api/fakturiranje/create")
async def create_invoice(request: Request, user=Depends(get_current_user)):
    data = await request.json()
    from nyx_light.modules.fakturiranje import FakturiranjeEngine
    engine = FakturiranjeEngine()
    result = engine.create_invoice(
        client_id=data.get("client_id", ""),
        kupac_oib=data.get("kupac_oib", ""),
        stavke=data.get("stavke", []),
        datum=data.get("datum", ""),
    )
    return result if isinstance(result, dict) else {"raw": str(result)}

# ═══════════════════════════════════════════
# MODUL: PEPPOL
# ═══════════════════════════════════════════

@app.post("/api/peppol/validate")
async def peppol_validate(request: Request, user=Depends(get_current_user)):
    data = await request.json()
    from nyx_light.modules.peppol import PeppolIntegration
    proc = PeppolIntegration()
    result = proc.validate(data.get("xml", ""), data.get("format", "UBL"))
    return result if isinstance(result, dict) else {"valid": bool(result)}

@app.get("/api/peppol/formats")
async def peppol_formats(user=Depends(get_current_user)):
    return {"formats": ["UBL 2.1", "CII", "ZUGFeRD 2.1", "FatturaPA", "EN 16931"]}

# ═══════════════════════════════════════════
# MODUL: FISKALIZACIJA 2.0
# ═══════════════════════════════════════════

@app.post("/api/fiskalizacija/fiscalize")
async def fiskalize(request: Request, user=Depends(get_current_user)):
    data = await request.json()
    from nyx_light.modules.fiskalizacija2 import Fiskalizacija2Engine
    engine = Fiskalizacija2Engine()
    result = engine.fiscalize(data)
    return result if isinstance(result, dict) else {"raw": str(result)}

@app.get("/api/fiskalizacija/status")
async def fiskalizacija_status(user=Depends(get_current_user)):
    from nyx_light.modules.fiskalizacija2 import Fiskalizacija2Engine
    engine = Fiskalizacija2Engine()
    return engine.get_status() if hasattr(engine, "get_status") else {"status": "ready"}

# ═══════════════════════════════════════════
# MODUL: INTRASTAT
# ═══════════════════════════════════════════

@app.post("/api/intrastat/check")
async def intrastat_check(request: Request, user=Depends(get_current_user)):
    data = await request.json()
    from nyx_light.modules.intrastat import IntrastatEngine
    engine = IntrastatEngine()
    result = engine.check_obligation(
        primitak_ytd=data.get("primitak_ytd", 0),
        otprema_ytd=data.get("otprema_ytd", 0),
    )
    return result if isinstance(result, dict) else {"raw": str(result)}

# ═══════════════════════════════════════════
# MODUL: BOLOVANJE
# ═══════════════════════════════════════════

@app.post("/api/bolovanje/calculate")
async def bolovanje_calc(request: Request, user=Depends(get_current_user)):
    data = await request.json()
    from nyx_light.modules.bolovanje import BolovanjeEngine
    engine = BolovanjeEngine()
    result = engine.calculate(
        dani=data.get("dani", 0),
        bruto_placa=data.get("bruto_placa", 0),
        tip=data.get("tip", "bolest"),
    )
    return result if isinstance(result, dict) else {"raw": str(result)}

# ═══════════════════════════════════════════
# MODUL: DRUGI DOHODAK
# ═══════════════════════════════════════════

@app.post("/api/drugi-dohodak/calculate")
async def drugi_dohodak_calc(request: Request, user=Depends(get_current_user)):
    data = await request.json()
    from nyx_light.modules.drugi_dohodak import DrugiDohodakEngine
    engine = DrugiDohodakEngine()
    result = engine.calculate(bruto=data.get("bruto", 0), tip=data.get("tip", "ugovor_o_djelu"))
    return result if isinstance(result, dict) else {"raw": str(result)}

# ═══════════════════════════════════════════
# MODUL: POREZ NA DOHODAK
# ═══════════════════════════════════════════

@app.post("/api/porez-dohodak/calculate")
async def porez_dohodak_calc(request: Request, user=Depends(get_current_user)):
    data = await request.json()
    from nyx_light.modules.porez_dohodak import PorezDohodakEngine
    engine = PorezDohodakEngine()
    result = engine.calculate(
        ukupni_dohodak=data.get("ukupni_dohodak", 0),
        osobni_odbitak=data.get("osobni_odbitak", 560),
    )
    return result if isinstance(result, dict) else {"raw": str(result)}

# ═══════════════════════════════════════════
# MODUL: LEDGER (Glavna knjiga)
# ═══════════════════════════════════════════

@app.get("/api/ledger/dnevnik")
async def ledger_dnevnik(user=Depends(get_current_user)):
    from nyx_light.modules.ledger import GeneralLedger
    engine = GeneralLedger()
    return {"available": True, "reports": ["dnevnik", "glavna_knjiga", "analitika"]}

# ═══════════════════════════════════════════
# MODUL: LIKVIDACIJA
# ═══════════════════════════════════════════

@app.post("/api/likvidacija/start")
async def likvidacija_start(request: Request, user=Depends(get_current_user)):
    data = await request.json()
    from nyx_light.modules.likvidacija import LikvidacijaEngine
    engine = LikvidacijaEngine()
    result = engine.start(data)
    return result if isinstance(result, dict) else {"raw": str(result)}

# ═══════════════════════════════════════════
# MODUL: ACCRUALS (PVR/AVR)
# ═══════════════════════════════════════════

@app.get("/api/accruals/checklist")
async def accruals_checklist(period: str = "monthly", user=Depends(get_current_user)):
    from nyx_light.modules.accruals import AccrualsChecklist
    checklist = AccrualsChecklist()
    result = checklist.get_checklist(period=period)
    return result if isinstance(result, dict) else {"items": result}

# ═══════════════════════════════════════════
# MODUL: NOVČANI TOKOVI
# ═══════════════════════════════════════════

@app.post("/api/novcani-tokovi/report")
async def novcani_tokovi(request: Request, user=Depends(get_current_user)):
    data = await request.json()
    from nyx_light.modules.novcani_tokovi import NovcanitTokoviEngine
    engine = NovcanitTokoviEngine()
    result = engine.generate(client_id=data.get("client_id", ""),
                             godina=data.get("godina", 2025))
    return result if isinstance(result, dict) else {"raw": str(result)}

# ═══════════════════════════════════════════
# MODUL: KPI Dashboard
# ═══════════════════════════════════════════

@app.post("/api/kpi/calculate")
async def kpi_calculate(request: Request, user=Depends(get_current_user)):
    data = await request.json()
    from nyx_light.modules.kpi import KPIDashboard
    dashboard = KPIDashboard()
    result = dashboard.calculate(data)
    return result if isinstance(result, dict) else {"raw": str(result)}

# ═══════════════════════════════════════════
# MODUL: MANAGEMENT ACCOUNTING
# ═══════════════════════════════════════════

@app.post("/api/management-accounting/report")
async def mgmt_accounting(request: Request, user=Depends(get_current_user)):
    data = await request.json()
    from nyx_light.modules.management_accounting import ManagementAccounting
    engine = ManagementAccounting()
    result = engine.generate_report(data)
    return result if isinstance(result, dict) else {"raw": str(result)}

# ═══════════════════════════════════════════
# MODUL: BUSINESS PLAN
# ═══════════════════════════════════════════

@app.post("/api/business-plan/generate")
async def business_plan(request: Request, user=Depends(get_current_user)):
    data = await request.json()
    from nyx_light.modules.business_plan import BusinessPlanGenerator
    engine = BusinessPlanGenerator()
    result = engine.generate(data)
    return result if isinstance(result, dict) else {"raw": str(result)}

# ═══════════════════════════════════════════
# MODUL: KADROVSKA EVIDENCIJA
# ═══════════════════════════════════════════

@app.get("/api/kadrovska/employees")
async def kadrovska_list(user=Depends(get_current_user)):
    from nyx_light.modules.kadrovska import KadrovskaEvidencija
    engine = KadrovskaEvidencija()
    return engine.list_employees() if hasattr(engine, "list_employees") else {"employees": []}

# ═══════════════════════════════════════════
# MODUL: COMMUNICATION
# ═══════════════════════════════════════════

@app.post("/api/communication/send")
async def communication_send(request: Request, user=Depends(get_current_user)):
    data = await request.json()
    from nyx_light.modules.communication import ReportExplainer
    engine = ReportExplainer()
    result = engine.send(
        tip=data.get("tip", "email"),
        primatelj=data.get("primatelj", ""),
        predmet=data.get("predmet", ""),
        sadrzaj=data.get("sadrzaj", ""),
    )
    return result if isinstance(result, dict) else {"sent": bool(result)}

# ═══════════════════════════════════════════
# MODUL: CLIENT MANAGEMENT
# ═══════════════════════════════════════════

@app.get("/api/client-management/list")
async def client_mgmt_list(user=Depends(get_current_user)):
    from nyx_light.modules.client_management import ClientOnboarding
    engine = ClientOnboarding()
    return engine.list_clients() if hasattr(engine, "list_clients") else {"clients": []}

# ═══════════════════════════════════════════
# MODUL: DEADLINES (Porezni rokovi)
# ═══════════════════════════════════════════

@app.get("/api/deadlines/upcoming")
async def deadlines_upcoming(days: int = 30, user=Depends(get_current_user)):
    from nyx_light.modules.deadlines import DeadlineTracker
    tracker = DeadlineTracker()
    result = tracker.get_upcoming(days=days)
    return result if isinstance(result, dict) else {"deadlines": result if isinstance(result, list) else []}

# ═══════════════════════════════════════════
# MODUL: ERACUNI PARSER
# ═══════════════════════════════════════════

@app.post("/api/eracuni/parse")
async def eracuni_parse(request: Request, user=Depends(get_current_user)):
    data = await request.json()
    from nyx_light.modules.eracuni_parser import ERacuniParser
    parser = ERacuniParser()
    result = parser.parse(data.get("xml", ""))
    return result if isinstance(result, dict) else {"raw": str(result)}

# ═══════════════════════════════════════════
# MODUL: UNIVERSAL PARSER
# ═══════════════════════════════════════════

@app.post("/api/universal-parser/parse")
async def universal_parse(
    file: UploadFile = File(...),
    user=Depends(get_current_user)
):
    content = await file.read()
    from nyx_light.modules.universal_parser import UniversalInvoiceParser
    parser = UniversalInvoiceParser()
    result = parser.parse(content, filename=file.filename)
    return result if isinstance(result, dict) else {"raw": str(result)}

# ═══════════════════════════════════════════
# MODUL: OUTGOING INVOICE
# ═══════════════════════════════════════════

@app.post("/api/outgoing-invoice/validate")
async def outgoing_invoice_validate(request: Request, user=Depends(get_current_user)):
    data = await request.json()
    from nyx_light.modules.outgoing_invoice import OutgoingInvoiceValidator
    validator = OutgoingInvoiceValidator()
    result = validator.validate(data)
    return result if isinstance(result, dict) else {"valid": bool(result)}

# ═══════════════════════════════════════════
# MODUL: VISION LLM
# ═══════════════════════════════════════════

@app.post("/api/vision/process")
async def vision_process(
    file: UploadFile = File(...),
    user=Depends(get_current_user)
):
    content = await file.read()
    from nyx_light.modules.vision_llm import VisionLLMClient
    processor = VisionLLMClient()
    result = processor.process(content, filename=file.filename)
    return result if isinstance(result, dict) else {"raw": str(result)}

# ═══════════════════════════════════════════
# MODUL: GFI PREP
# ═══════════════════════════════════════════

@app.post("/api/gfi/prep")
async def gfi_prep(request: Request, user=Depends(get_current_user)):
    data = await request.json()
    from nyx_light.modules.gfi_prep import GFIPrepEngine
    engine = GFIPrepEngine()
    result = engine.prepare(client_id=data.get("client_id", ""),
                            godina=data.get("godina", 2025))
    return result if isinstance(result, dict) else {"raw": str(result)}

# ═══════════════════════════════════════════
# MODUL: NETWORK
# ═══════════════════════════════════════════

@app.get("/api/network/status")
async def network_status(user=Depends(get_current_user)):
    from nyx_light.modules.network import NetworkSetupGenerator
    manager = NetworkSetupGenerator()
    return manager.get_status() if hasattr(manager, "get_status") else {"mdns": True, "tailscale": "check"}

# ═══════════════════════════════════════════
# MODUL: SCALABILITY
# ═══════════════════════════════════════════

@app.get("/api/scalability/metrics")
async def scalability_metrics(user=Depends(get_current_user)):
    from nyx_light.modules.scalability import TaskQueue
    engine = TaskQueue()
    return engine.get_metrics() if hasattr(engine, "get_metrics") else {"status": "ready"}

# ═══════════════════════════════════════════
# MODUL: AUDIT TRAIL
# ═══════════════════════════════════════════

@app.get("/api/audit/trail")
async def audit_trail_full(user=Depends(get_current_user)):
    from nyx_light.modules.audit import AuditTrail
    engine = AuditTrail()
    return engine.get_trail() if hasattr(engine, "get_trail") else {"entries": []}

# ═══════════════════════════════════════════
# NYSXLIGHTAPP — UNIFIED ORCHESTRATOR ENDPOINTS
# ═══════════════════════════════════════════

@app.post("/api/nyx/process-invoice")
async def nyx_process_invoice(request: Request, user=Depends(get_current_user)):
    """Procesuiraj račun kroz NyxLightApp orchestrator."""
    data = await request.json()
    if not state.nyx_app:
        raise HTTPException(503, "NyxLightApp nije inicijaliziran")
    result = state.nyx_app.process_invoice(
        ocr_data=data.get("ocr_data", {}),
        client_id=data.get("client_id", ""),
    )
    return result

@app.post("/api/nyx/process-bank")
async def nyx_process_bank(request: Request, user=Depends(get_current_user)):
    """Procesuiraj bankovni izvod kroz NyxLightApp orchestrator."""
    data = await request.json()
    if not state.nyx_app:
        raise HTTPException(503, "NyxLightApp nije inicijaliziran")
    result = state.nyx_app.process_bank_statement(
        raw_data=data.get("raw_data", ""),
        bank=data.get("bank", ""),
        format_hint=data.get("format", "csv"),
        client_id=data.get("client_id", ""),
    )
    return result

@app.post("/api/nyx/process-petty-cash")
async def nyx_process_petty_cash(request: Request, user=Depends(get_current_user)):
    data = await request.json()
    if not state.nyx_app:
        raise HTTPException(503, "NyxLightApp nije inicijaliziran")
    result = state.nyx_app.process_petty_cash(
        transaction=data.get("transaction", {}),
        client_id=data.get("client_id", ""),
    )
    return result

@app.post("/api/nyx/process-travel")
async def nyx_process_travel(request: Request, user=Depends(get_current_user)):
    data = await request.json()
    if not state.nyx_app:
        raise HTTPException(503, "NyxLightApp nije inicijaliziran")
    result = state.nyx_app.process_travel_expense(
        travel_data=data.get("travel_data", {}),
        client_id=data.get("client_id", ""),
    )
    return result

@app.post("/api/nyx/prepare-pdv")
async def nyx_prepare_pdv(request: Request, user=Depends(get_current_user)):
    data = await request.json()
    if not state.nyx_app:
        raise HTTPException(503, "NyxLightApp nije inicijaliziran")
    result = state.nyx_app.prepare_pdv_prijava(
        client_id=data.get("client_id", ""),
        period=data.get("period", ""),
    )
    return result

@app.post("/api/nyx/generate-gfi")
async def nyx_generate_gfi(request: Request, user=Depends(get_current_user)):
    data = await request.json()
    if not state.nyx_app:
        raise HTTPException(503, "NyxLightApp nije inicijaliziran")
    result = state.nyx_app.generate_gfi_xml(
        client_id=data.get("client_id", ""),
        godina=data.get("godina", 2025),
    )
    return result

@app.post("/api/nyx/export-erp")
async def nyx_export_erp(request: Request, user=Depends(get_current_user)):
    data = await request.json()
    if not state.nyx_app:
        raise HTTPException(503, "NyxLightApp nije inicijaliziran")
    result = state.nyx_app.export_to_erp(
        client_id=data.get("client_id", ""),
        format_hint=data.get("format", "cpp_xml"),
    )
    return result

@app.get("/api/nyx/status")
async def nyx_status(user=Depends(get_current_user)):
    """NyxLightApp status — svi moduli."""
    if not state.nyx_app:
        return {"status": "not_initialized"}
    return state.nyx_app.get_system_status()

