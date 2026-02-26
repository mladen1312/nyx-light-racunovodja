"""
Nyx Light — Web UI (FastAPI Backend)

Chat sučelje + Approval Workflow + Dashboard za 15 zaposlenika.
Frontend: HTML/JS (single-page) ili React.
Backend: FastAPI s WebSocket za real-time updates.

Endpoints:
- /chat — AI chat (pitanja, kontiranje, savjeti)
- /pending — Lista pending knjiženja za odobrenje
- /approve/{id} — Odobri knjiženje
- /reject/{id} — Odbij knjiženje
- /correct/{id} — Ispravi i odobri
- /export/{client_id} — Eksport u CPP/Synesis
- /dashboard — KPI, rokovi, statistike
- /clients — Lista klijenata
"""

import json
import logging
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nyx_light.ui")

# Try imports — graceful fallback if FastAPI not installed
try:
    from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import HTMLResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles
    from pydantic import BaseModel
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False


class ChatMessage(BaseModel if HAS_FASTAPI else object):
    """Chat poruka od korisnika."""
    user_id: str = ""
    message: str = ""
    client_id: str = ""


class ApprovalRequest(BaseModel if HAS_FASTAPI else object):
    """Zahtjev za odobrenje/odbijanje."""
    user_id: str = ""
    reason: str = ""


class CorrectionRequest(BaseModel if HAS_FASTAPI else object):
    """Zahtjev za ispravak."""
    user_id: str = ""
    corrections: dict = {}


def create_app(nyx_app=None, db_path: str = None) -> "FastAPI":
    """Factory za kreiranje FastAPI aplikacije."""
    if not HAS_FASTAPI:
        raise ImportError("FastAPI nije instaliran. Pokrenite: pip install fastapi uvicorn")

    app = FastAPI(
        title="Nyx Light — Računovođa",
        description="AI sustav za računovodstvo RH",
        version="1.0.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Lazy init NyxLightApp
    if nyx_app is None:
        from nyx_light.app import NyxLightApp
        nyx_app = NyxLightApp(db_path=db_path or "data/memory_db/nyx_light.db")

    # Connected WebSocket clients
    ws_clients: List[WebSocket] = []

    async def broadcast(event: str, data: dict):
        """Pošalji real-time update svim spojenim klijentima."""
        msg = json.dumps({"event": event, "data": data})
        dead = []
        for ws in ws_clients:
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            ws_clients.remove(ws)

    # ═══════════════════════════════════════
    # HEALTH & STATUS
    # ═══════════════════════════════════════

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "timestamp": datetime.now().isoformat()}

    @app.get("/api/status")
    async def system_status():
        return nyx_app.get_system_status()

    # ═══════════════════════════════════════
    # CHAT
    # ═══════════════════════════════════════

    @app.post("/api/chat")
    async def chat(msg: ChatMessage):
        """AI chat — odgovori na pitanja zaposlenika."""
        # Overseer check
        safety = nyx_app.overseer.evaluate(msg.message)
        if not safety["approved"]:
            return {
                "response": safety.get("message", "Ovo pitanje je izvan domene sustava."),
                "blocked": True,
                "boundary": safety.get("boundary_type", ""),
            }

        # Za sada: return structured info (LLM inference dolazi s vllm-mlx)
        return {
            "response": f"[AI odgovor na: {msg.message[:100]}]",
            "user_id": msg.user_id,
            "client_id": msg.client_id,
            "note": "LLM inference putem vllm-mlx servera (konfigurirati pri deploy-u)",
        }

    # ═══════════════════════════════════════
    # PENDING / APPROVAL WORKFLOW
    # ═══════════════════════════════════════

    @app.get("/api/pending")
    async def get_pending(client_id: str = ""):
        pending = nyx_app.pipeline.get_pending(client_id)
        return {"count": len(pending), "items": pending}

    @app.get("/api/approved")
    async def get_approved(client_id: str = ""):
        approved = nyx_app.pipeline.get_approved(client_id)
        return {"count": len(approved), "items": approved}

    @app.post("/api/approve/{proposal_id}")
    async def approve(proposal_id: str, req: ApprovalRequest):
        try:
            result = nyx_app.approve(proposal_id, req.user_id)
            await broadcast("approved", {"id": proposal_id, "user": req.user_id})
            return result
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/api/reject/{proposal_id}")
    async def reject(proposal_id: str, req: ApprovalRequest):
        try:
            result = nyx_app.reject(proposal_id, req.user_id, req.reason)
            await broadcast("rejected", {"id": proposal_id, "user": req.user_id})
            return result
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/api/correct/{proposal_id}")
    async def correct(proposal_id: str, req: CorrectionRequest):
        try:
            result = nyx_app.correct(proposal_id, req.user_id, req.corrections)
            await broadcast("corrected", {"id": proposal_id, "user": req.user_id})
            return result
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    # ═══════════════════════════════════════
    # EXPORT
    # ═══════════════════════════════════════

    @app.post("/api/export/{client_id}")
    async def export_to_erp(client_id: str):
        try:
            result = nyx_app.export_to_erp(client_id)
            return result
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    # ═══════════════════════════════════════
    # CLIENTS
    # ═══════════════════════════════════════

    @app.get("/api/clients")
    async def list_clients():
        clients = nyx_app.registry.list_all()
        return {"count": len(clients), "clients": [
            {"id": c.id, "naziv": c.naziv, "oib": c.oib,
             "erp": c.erp_target, "kategorija": c.kategorija}
            for c in clients
        ]}

    # ═══════════════════════════════════════
    # DASHBOARD
    # ═══════════════════════════════════════

    @app.get("/api/dashboard")
    async def dashboard():
        deadlines = nyx_app.get_upcoming_deadlines()
        status = nyx_app.get_system_status()
        pending = nyx_app.pipeline.get_pending()
        return {
            "upcoming_deadlines": deadlines[:10],
            "pending_count": len(pending),
            "modules": status.get("modules", {}),
        }

    # ═══════════════════════════════════════
    # WEBSOCKET (Real-time updates)
    # ═══════════════════════════════════════

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await websocket.accept()
        ws_clients.append(websocket)
        logger.info("WebSocket client connected (%d total)", len(ws_clients))
        try:
            while True:
                data = await websocket.receive_text()
                # Heartbeat or client messages
                if data == "ping":
                    await websocket.send_text("pong")
        except WebSocketDisconnect:
            ws_clients.remove(websocket)
            logger.info("WebSocket client disconnected (%d total)", len(ws_clients))

    # ═══════════════════════════════════════
    # FRONTEND (Single-Page HTML)
    # ═══════════════════════════════════════

    @app.get("/", response_class=HTMLResponse)
    async def frontend():
        return _FRONTEND_HTML

    return app


# ═══════════════════════════════════════════════════
# EMBEDDED FRONTEND (single file, no build needed)
# ═══════════════════════════════════════════════════

_FRONTEND_HTML = """<!DOCTYPE html>
<html lang="hr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Nyx Light — Računovođa</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: #0a0a1a; color: #e0e0f0; }
.container { max-width: 1200px; margin: 0 auto; padding: 20px; }
header { background: linear-gradient(135deg, #1a1a3e 0%, #0d0d2b 100%);
         padding: 20px; border-radius: 12px; margin-bottom: 20px;
         border: 1px solid #2a2a5e; }
header h1 { color: #8b8bf0; font-size: 1.8em; }
header p { color: #6a6a9a; margin-top: 5px; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
@media (max-width: 768px) { .grid { grid-template-columns: 1fr; } }
.card { background: #12122a; border: 1px solid #2a2a5e; border-radius: 12px;
        padding: 20px; }
.card h2 { color: #8b8bf0; font-size: 1.2em; margin-bottom: 15px; }
.chat-box { height: 300px; overflow-y: auto; border: 1px solid #2a2a5e;
            border-radius: 8px; padding: 10px; margin-bottom: 10px;
            background: #0a0a1a; }
.chat-msg { margin-bottom: 8px; padding: 8px 12px; border-radius: 8px; }
.chat-user { background: #1a1a4e; text-align: right; }
.chat-ai { background: #1a2a1a; }
.chat-input { display: flex; gap: 10px; }
.chat-input input { flex: 1; padding: 10px; border-radius: 8px;
                    border: 1px solid #2a2a5e; background: #0a0a1a;
                    color: #e0e0f0; font-size: 14px; }
.chat-input button { padding: 10px 20px; border-radius: 8px;
                     background: #4a4af0; color: white; border: none;
                     cursor: pointer; font-size: 14px; }
.chat-input button:hover { background: #5a5aff; }
.pending-item { background: #1a1a2e; border: 1px solid #2a2a5e;
                border-radius: 8px; padding: 12px; margin-bottom: 8px; }
.pending-item .type { color: #8b8bf0; font-weight: bold; }
.pending-item .amount { color: #4af04a; float: right; }
.btn-approve { background: #2a8a2a; color: white; border: none;
               padding: 6px 12px; border-radius: 6px; cursor: pointer; margin-right: 5px; }
.btn-reject { background: #8a2a2a; color: white; border: none;
              padding: 6px 12px; border-radius: 6px; cursor: pointer; }
.deadline { padding: 8px; border-left: 3px solid; margin-bottom: 6px; }
.deadline.critical { border-color: #ff4444; }
.deadline.high { border-color: #ffaa44; }
.deadline.normal { border-color: #44aaff; }
.stat { display: inline-block; margin: 10px; text-align: center; }
.stat .num { font-size: 2em; color: #8b8bf0; }
.stat .label { font-size: 0.85em; color: #6a6a9a; }
#status-bar { position: fixed; bottom: 0; left: 0; right: 0;
              background: #1a1a3e; padding: 8px 20px; font-size: 0.85em;
              color: #6a6a9a; border-top: 1px solid #2a2a5e;
              display: flex; justify-content: space-between; }
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>🌙 Nyx Light — Računovođa</h1>
    <p>AI sustav za računovodstvo RH • 15 korisnika • 100% lokalno</p>
  </header>

  <div id="stats" style="text-align:center;margin-bottom:20px;"></div>

  <div class="grid">
    <!-- Chat -->
    <div class="card">
      <h2>💬 Chat s AI-jem</h2>
      <div class="chat-box" id="chatBox"></div>
      <div class="chat-input">
        <input id="chatInput" placeholder="Postavi pitanje..." onkeydown="if(event.key==='Enter')sendChat()">
        <button onclick="sendChat()">Pošalji</button>
      </div>
    </div>

    <!-- Pending -->
    <div class="card">
      <h2>⏳ Čeka odobrenje</h2>
      <div id="pendingList"><p style="color:#6a6a9a">Učitavam...</p></div>
    </div>

    <!-- Deadlines -->
    <div class="card">
      <h2>📅 Nadolazeći rokovi</h2>
      <div id="deadlineList"><p style="color:#6a6a9a">Učitavam...</p></div>
    </div>

    <!-- Quick Actions -->
    <div class="card">
      <h2>⚡ Brze akcije</h2>
      <button class="btn-approve" onclick="exportAll()" style="margin:5px">📤 Export u ERP</button>
      <button class="btn-approve" onclick="loadDashboard()" style="margin:5px">📊 Osvježi</button>
      <p style="margin-top:15px;color:#6a6a9a;font-size:0.9em">
        Svi podaci ostaju 100% lokalno na Mac Studio.<br>
        Nijedan podatak ne napušta ured.
      </p>
    </div>
  </div>
</div>

<div id="status-bar">
  <span id="ws-status">● Povezivanje...</span>
  <span id="clock"></span>
</div>

<script>
const API = '';
let ws;

async function loadDashboard() {
  try {
    const r = await fetch(API+'/api/dashboard');
    const d = await r.json();
    document.getElementById('stats').innerHTML =
      '<div class="stat"><div class="num">'+d.pending_count+'</div><div class="label">Čeka odobrenje</div></div>' +
      '<div class="stat"><div class="num">'+d.upcoming_deadlines.length+'</div><div class="label">Rokovi</div></div>';
    renderPending();
    renderDeadlines(d.upcoming_deadlines);
  } catch(e) { console.error(e); }
}

async function renderPending() {
  try {
    const r = await fetch(API+'/api/pending');
    const d = await r.json();
    const el = document.getElementById('pendingList');
    if (!d.items.length) { el.innerHTML='<p style="color:#4af04a">✅ Sve odobreno!</p>'; return; }
    el.innerHTML = d.items.map(i =>
      '<div class="pending-item">' +
      '<span class="type">'+i.document_type+'</span>' +
      '<span class="amount">'+(i.iznos||0).toFixed(2)+' EUR</span>' +
      '<div style="margin-top:8px">'+(i.opis||'')+'</div>' +
      '<div style="margin-top:8px">' +
      '<button class="btn-approve" onclick="approveItem(\\''+i.id+'\\')">✅ Odobri</button>' +
      '<button class="btn-reject" onclick="rejectItem(\\''+i.id+'\\')">❌ Odbij</button>' +
      '</div></div>'
    ).join('');
  } catch(e) { console.error(e); }
}

function renderDeadlines(items) {
  const el = document.getElementById('deadlineList');
  if (!items || !items.length) { el.innerHTML='<p style="color:#6a6a9a">Nema rokova.</p>'; return; }
  el.innerHTML = items.slice(0,8).map(d =>
    '<div class="deadline '+(d.urgency||'normal')+'">' +
    '<strong>'+d.rok+'</strong> — '+d.opis +
    '</div>'
  ).join('');
}

async function sendChat() {
  const inp = document.getElementById('chatInput');
  const msg = inp.value.trim();
  if (!msg) return;
  inp.value = '';
  addChatMsg(msg, 'user');
  try {
    const r = await fetch(API+'/api/chat', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({user_id:'user1', message:msg})
    });
    const d = await r.json();
    addChatMsg(d.response || d.message || 'OK', d.blocked?'blocked':'ai');
  } catch(e) { addChatMsg('Greška: '+e.message, 'ai'); }
}

function addChatMsg(text, type) {
  const box = document.getElementById('chatBox');
  const div = document.createElement('div');
  div.className = 'chat-msg chat-'+(type==='user'?'user':'ai');
  div.textContent = text;
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
}

async function approveItem(id) {
  await fetch(API+'/api/approve/'+id, {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({user_id:'user1'})
  });
  loadDashboard();
}

async function rejectItem(id) {
  const reason = prompt('Razlog odbijanja?');
  await fetch(API+'/api/reject/'+id, {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({user_id:'user1', reason: reason||''})
  });
  loadDashboard();
}

async function exportAll() { alert('Export: odaberite klijenta u /api/export/{client_id}'); }

function connectWS() {
  const proto = location.protocol==='https:'?'wss':'ws';
  ws = new WebSocket(proto+'://'+location.host+'/ws');
  ws.onopen = () => { document.getElementById('ws-status').innerHTML='🟢 Spojeno'; };
  ws.onclose = () => { document.getElementById('ws-status').innerHTML='🔴 Prekinuto';
    setTimeout(connectWS, 3000); };
  ws.onmessage = (e) => { loadDashboard(); };
}

setInterval(()=>{document.getElementById('clock').textContent=new Date().toLocaleTimeString('hr');},1000);
loadDashboard();
connectWS();
</script>
</body>
</html>
"""


def run_server(host: str = "0.0.0.0", port: int = 8080, db_path: str = None):
    """Pokreni Nyx Light web server."""
    if not HAS_FASTAPI:
        print("ERROR: FastAPI nije instaliran.")
        print("Pokrenite: pip install fastapi uvicorn")
        return

    import uvicorn
    app = create_app(db_path=db_path)
    print(f"\n🌙 Nyx Light — Računovođa")
    print(f"   http://{host}:{port}")
    print(f"   WebSocket: ws://{host}:{port}/ws")
    print(f"   API docs: http://{host}:{port}/docs\n")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_server()
