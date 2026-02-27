# Nyx Light API Documentation

## Base URL
```
http://localhost:7860/api
```

## Authentication
All endpoints require JWT token in `Authorization: Bearer {token}` header (except /health and /api/auth/login).

### POST /api/auth/login
```json
{ "username": "admin", "password": "admin123" }
→ { "ok": true, "token": "eyJ...", "user": { "username": "admin", "role": "admin" } }
```

### GET /api/auth/me
Returns current user info.

### GET /api/auth/users (admin only)
Returns list of all users.

---

## Chat (AI Inference)

### POST /api/chat
```json
{ "message": "Koja je stopa PDV-a na hranu?", "client_id": "K001" }
→ { "content": "...", "model": "Qwen3-235B-A22B", "tokens": 150, "latency_ms": 800 }
```

### WebSocket /api/ws/chat
Streaming chat with token-by-token response.

---

## Bookings (Human-in-the-Loop)

### POST /api/bookings — Create pending booking
```json
{
  "client_id": "K001", "document_type": "ulazni_racun",
  "konto_duguje": "4010", "konto_potrazuje": "2200",
  "iznos": 1250.00, "pdv_stopa": 25, "opis": "Uredski materijal"
}
```

### GET /api/pending — Pending bookings
### GET /api/bookings — All bookings (filter: ?status=approved&client_id=K001)
### POST /api/approve/{id} — Approve booking
### POST /api/reject/{id} — Reject booking
### POST /api/correct/{id} — Correct and approve (triggers L2 memory update)
```json
{ "konto_duguje": "4620", "konto_potrazuje": "2200", "reason": "IT usluge = 4620" }
```

---

## Clients

### GET /api/clients — List clients
### POST /api/clients — Create client
```json
{ "name": "ABC d.o.o.", "oib": "12345678901", "erp_system": "CPP" }
```

---

## Upload

### POST /api/upload (multipart/form-data)
- file: PDF, image, CSV, MT940, XML
- client_id: Required

---

## Export (ERP)

### POST /api/export
```json
{ "client_id": "K001", "format": "cpp_xml" }
```
Formats: `cpp_xml`, `synesis_csv`, `json`, `excel`

---

## Dashboard & Status

### GET /api/dashboard — Stats (pending, approved, corrections, clients)
### GET /api/deadlines — Tax deadlines (PDV, JOPPD, GFI, PD)
### GET /api/system/status — LLM model, memory, tokens, uptime

---

## Monitoring

### GET /api/monitor — Full health report (CPU, RAM, disk, vLLM, Qdrant)
### GET /api/monitor/memory — RAM stats (macOS Unified Memory)
### GET /api/monitor/inference — Inference latency stats (avg, p50, p95)

---

## Backup

### GET /api/backups — List backups
### POST /api/backups/daily — Create daily backup
### POST /api/backups/weekly — Create weekly backup
### POST /api/backups/restore/{name} — Restore from backup

---

## DPO Training

### GET /api/dpo/stats — Training stats (pairs, runs, adapters)
### GET /api/dpo/adapters — List LoRA adapters
### POST /api/dpo/train — Manual DPO training run

---

## Laws (RAG)

### GET /api/laws — List available laws
### GET /api/laws/search?q=PDV stopa — Search laws

---

## Other

### GET /api/audit — Audit log (admin/racunovodja)
### GET /api/scheduler/status — Nightly scheduler status
### POST /api/scheduler/run?task=backup — Manual scheduler run
### GET /api/konto/search?q=uredski — Search kontni plan
### GET /health — Health check
### GET /api/health — Detailed health

---

## Roles & Permissions

| Role | Permissions |
|------|------------|
| admin | All (manage_users, backup, update_model, ...) |
| racunovodja | chat, approve, reject, correct, export, manage_clients |
| asistent | chat, view_dashboard |

## Demo Credentials

| Username | Password | Role |
|----------|----------|------|
| admin | admin123 | admin |
| racunovodja | nyx2026 | racunovodja |
| asistent | nyx2026 | asistent |
