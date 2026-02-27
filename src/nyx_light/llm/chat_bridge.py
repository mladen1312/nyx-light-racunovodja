"""
Nyx Light — LLM Chat Bridge

Spaja korisnički chat na lokalni vllm-mlx server.

Tijek obrade upita:
  1. Korisnik šalje poruku kroz Web UI
  2. ChatBridge dohvaća kontekst:
     a) RAG — relevantni zakoni (Time-Aware)
     b) L2 Semantic Memory — pravila kontiranja za klijenta
     c) L1 Episodic Memory — danas korisnikove interakcije
     d) Working context — trenutni pipeline
  3. Gradi system prompt + user kontekst
  4. Šalje na vllm-mlx (lokalni OpenAI-kompatibilan endpoint)
  5. Streama odgovor natrag korisniku
  6. Sprema interakciju u L1 memoriju

Endpoint: http://localhost:8080/v1/chat/completions (OpenAI format)
"""

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Optional

logger = logging.getLogger("nyx_light.llm.chat_bridge")


SYSTEM_PROMPT = """Ti si Nyx Light — Računovođa, privatni AI asistent za računovodstveni ured u Hrvatskoj.

TVOJA ULOGA:
• Pomaži u kontiranju, poreznim pitanjima, obračunima i interpretaciji zakona RH
• Pripremaš, razvrstavas, predlažeš i kontroliraš — ali NIKAD ne knjiži autonomno
• Ljudski računovođa UVIJEK donosi konačnu odluku (Human-in-the-Loop)

TVOJE ZNANJE:
• Zakon o računovodstvu (NN 78/15, 120/16, 116/18, 42/20, 47/20, 114/22)
• Zakon o PDV-u (NN 73/13 i izmjene)
• Zakon o porezu na dobit, dohodak, doprinose
• Mišljenja Porezne uprave, HSFI/MSFI standardi
• Hrvatski kontni plan (razredi 0-9)

TVRDE GRANICE:
• NIKAD ne sastavlja ugovore, tužbe ili pravne savjete izvan računovodstva
• NIKAD ne daje medicinske, financijske investicijske ili pravne savjete
• Sve odgovore veže uz VREMENSKI KONTEKST (koji zakon je vrijedio u tom trenutku)
• Ako nije siguran — kaže "Trebam konzultirati" i preporuča ljudsku provjeru

ODGOVARAJ:
• Jasno, precizno, s citiranjem relevantnog zakona i članka
• Na hrvatskom jeziku
• S brojevima konta kad je relevantno
• Ako je upit dvosmislen, postavi potpitanje za pojašnjenje"""


@dataclass
class ChatContext:
    """Kontekst za LLM upit — RAG + memorija."""
    rag_results: List[Dict] = field(default_factory=list)
    semantic_facts: List[str] = field(default_factory=list)
    episodic_recent: List[str] = field(default_factory=list)
    client_info: Dict[str, Any] = field(default_factory=dict)
    pipeline_context: str = ""


@dataclass
class ChatMessage:
    role: str  # system, user, assistant
    content: str
    timestamp: float = 0.0


@dataclass
class ChatResponse:
    content: str
    tokens_used: int = 0
    latency_ms: float = 0.0
    context_used: bool = False
    model: str = ""


class ChatBridge:
    """Most između korisnika i lokalnog LLM-a."""

    def __init__(self, llm_url: str = "http://localhost:8080",
                 model_name: str = "default",
                 max_context_tokens: int = 8192,
                 temperature: float = 0.3,
                 max_tokens: int = 2048):
        self.llm_url = llm_url.rstrip("/")
        self.model_name = model_name
        self.max_context_tokens = max_context_tokens
        self.temperature = temperature
        self.max_tokens = max_tokens

        # Chat historije po sesiji
        self._histories: Dict[str, List[ChatMessage]] = {}
        self._stats = {"total_queries": 0, "total_tokens": 0,
                       "avg_latency_ms": 0.0}

    def build_messages(self, user_msg: str, session_id: str,
                       context: Optional[ChatContext] = None
                       ) -> List[Dict[str, str]]:
        """Izgradi messages array za LLM — system + context + history + user."""
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        # Dodaj RAG kontekst
        if context:
            ctx_parts = []

            if context.rag_results:
                ctx_parts.append("RELEVANTNI ZAKONI:")
                for r in context.rag_results[:5]:
                    ctx_parts.append(f"  [{r.get('source', '')}] {r.get('text', '')[:500]}")

            if context.semantic_facts:
                ctx_parts.append("\nPRAVILA KONTIRANJA (naučeno iz prakse):")
                for fact in context.semantic_facts[:10]:
                    ctx_parts.append(f"  • {fact}")

            if context.client_info:
                ci = context.client_info
                ctx_parts.append(f"\nKLIJENT: {ci.get('name', 'N/A')} "
                                 f"(OIB: {ci.get('oib', 'N/A')}, "
                                 f"Tip: {ci.get('type', 'N/A')})")

            if context.pipeline_context:
                ctx_parts.append(f"\nTRENUTNI RAD: {context.pipeline_context}")

            if ctx_parts:
                messages.append({
                    "role": "system",
                    "content": "KONTEKST ZA OVAJ UPIT:\n" + "\n".join(ctx_parts),
                })

        # Chat history (zadnjih 10 poruka za sesiju)
        history = self._histories.get(session_id, [])
        for msg in history[-10:]:
            messages.append({"role": msg.role, "content": msg.content})

        # User poruka
        messages.append({"role": "user", "content": user_msg})

        return messages

    async def chat(self, user_msg: str, session_id: str,
                   context: Optional[ChatContext] = None
                   ) -> ChatResponse:
        """Pošalji upit na lokalni LLM i vrati odgovor."""
        messages = self.build_messages(user_msg, session_id, context)
        start = time.time()

        try:
            import httpx
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    f"{self.llm_url}/v1/chat/completions",
                    json={
                        "model": self.model_name,
                        "messages": messages,
                        "temperature": self.temperature,
                        "max_tokens": self.max_tokens,
                        "stream": False,
                    },
                )

                if resp.status_code != 200:
                    return ChatResponse(
                        content=f"⚠️ LLM server greška ({resp.status_code}). "
                                f"Provjerite da je vllm-mlx pokrenut na {self.llm_url}",
                        latency_ms=(time.time() - start) * 1000,
                    )

                data = resp.json()
                choice = data.get("choices", [{}])[0]
                content = choice.get("message", {}).get("content", "")
                tokens = data.get("usage", {}).get("total_tokens", 0)

        except ImportError:
            return ChatResponse(
                content="⚠️ httpx nije instaliran. Pokrenite: pip install httpx",
                latency_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            # Fallback: simulirani odgovor za razvoj
            content = self._fallback_response(user_msg)
            tokens = 0
            logger.warning("LLM nedostupan (%s) — fallback odgovor", e)

        latency = (time.time() - start) * 1000

        # Spremi u historiju
        if session_id not in self._histories:
            self._histories[session_id] = []
        self._histories[session_id].append(
            ChatMessage("user", user_msg, time.time()))
        self._histories[session_id].append(
            ChatMessage("assistant", content, time.time()))

        # Trim history
        if len(self._histories[session_id]) > 30:
            self._histories[session_id] = self._histories[session_id][-20:]

        # Stats
        self._stats["total_queries"] += 1
        self._stats["total_tokens"] += tokens

        return ChatResponse(
            content=content,
            tokens_used=tokens,
            latency_ms=latency,
            context_used=context is not None,
            model=self.model_name,
        )

    async def chat_stream(self, user_msg: str, session_id: str,
                          context: Optional[ChatContext] = None
                          ) -> AsyncIterator[str]:
        """Streaming chat — yield-a tokene jedan po jedan."""
        messages = self.build_messages(user_msg, session_id, context)
        full_response = ""

        try:
            import httpx
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream(
                    "POST",
                    f"{self.llm_url}/v1/chat/completions",
                    json={
                        "model": self.model_name,
                        "messages": messages,
                        "temperature": self.temperature,
                        "max_tokens": self.max_tokens,
                        "stream": True,
                    },
                ) as resp:
                    async for line in resp.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str.strip() == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data_str)
                                delta = chunk.get("choices", [{}])[0].get(
                                    "delta", {}).get("content", "")
                                if delta:
                                    full_response += delta
                                    yield delta
                            except json.JSONDecodeError:
                                continue

        except Exception as e:
            fallback = self._fallback_response(user_msg)
            full_response = fallback
            yield fallback

        # Spremi u historiju
        if session_id not in self._histories:
            self._histories[session_id] = []
        self._histories[session_id].append(
            ChatMessage("user", user_msg, time.time()))
        self._histories[session_id].append(
            ChatMessage("assistant", full_response, time.time()))

    def clear_history(self, session_id: str):
        """Obriši chat historiju za sesiju."""
        self._histories.pop(session_id, None)

    def get_stats(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "active_sessions": len(self._histories),
        }

    def _fallback_response(self, user_msg: str) -> str:
        """Pametni fallback kad LLM server nije dostupan — koristi RAG i module."""
        msg_lower = user_msg.lower()

        # 1. Pokušaj RAG pretragu zakona
        try:
            from nyx_light.rag import EmbeddedVectorStore
            store = EmbeddedVectorStore()
            results = store.search(user_msg, top_k=3)
            if results and len(results) > 0:
                chunks = []
                for r in results[:2]:
                    text = getattr(r, "text", "") if not isinstance(r, dict) else r.get("text", "")
                    source = getattr(r, "law_name", "") if not isinstance(r, dict) else r.get("source", "")
                    if not text:
                        text = r.get("text", r.get("content", "")) if isinstance(r, dict) else ""
                    if text:
                        chunks.append(f"📜 {source}: {text[:300]}")
                if chunks:
                    return ("Pronašao sam relevantne odredbe iz zakona:\n\n"
                            + "\n\n".join(chunks)
                            + "\n\n⚠️ Ovo je automatski izvadak iz baze zakona. "
                            "Za detaljniju analizu, pokrenite AI server (`./start.sh llm`).")
        except Exception:
            pass

        # 2. Module-specific responses
        if any(w in msg_lower for w in ["pdv", "porez na dodanu"]):
            return ("Pitanje o PDV-u. Prema Zakonu o PDV-u (NN 73/13), "
                    "standardna stopa je 25%, snižene 13% (ugostiteljstvo, namirnice) "
                    "i 5% (knjige, lijekovi, dječja hrana). "
                    "Za preciznu analizu, specificirajte situaciju.\n"
                    "⚠️ AI model nije pokrenut — koristim bazu zakona.")

        if any(w in msg_lower for w in ["konto", "kontir", "knjižen"]):
            return ("Za kontiranje trebam: vrstu dokumenta, iznos, klijenta i tip transakcije. "
                    "Primjer: 'Ulazni račun 1.250 EUR za uredski materijal od XY d.o.o.'\n"
                    "⚠️ AI model nije pokrenut — pokrenite `./start.sh llm`.")

        if any(w in msg_lower for w in ["plaća", "placa", "bruto", "neto"]):
            try:
                # Try to extract number and calculate
                import re
                nums = re.findall(r'[\d.,]+', user_msg)
                if nums:
                    bruto = float(nums[0].replace(',', '.'))
                    if bruto > 100:
                        from nyx_light.modules.place import PayrollCalculator, ObracunPlaceInput
                        r = PayrollCalculator().obracun(ObracunPlaceInput(bruto=bruto))
                        return (f"💰 Obračun plaće:\n"
                                f"   Bruto: {r.bruto_ukupno:,.2f} EUR\n"
                                f"   MIO I+II: {r.mio_i + r.mio_ii:,.2f}\n"
                                f"   Porez+prirez: {r.porez + r.prirez:,.2f}\n"
                                f"   Za isplatu: {r.za_isplatu:,.2f} EUR\n\n"
                                "⚠️ Izračun za Zagreb bez olakšica.")
            except Exception:
                pass
            return ("Za obračun plaće idite na stranicu Plaće (izbornik lijevo) "
                    "ili mi recite bruto iznos.\n"
                    "⚠️ AI model nije pokrenut.")

        if any(w in msg_lower for w in ["rok", "deadline", "porezn"]):
            return ("Porezni rokovi: PDV prijava do 20. u mjesecu, "
                    "JOPPD do 15. u mjesecu za prethodni, "
                    "Porez na dobit godišnje do 30.04.\n"
                    "Pogledajte stranicu 📅 Rokovi za detalje.")

        if any(w in msg_lower for w in ["bok", "hej", "zdravo", "pozdrav", "dobar"]):
            return ("Pozdrav! 👋 Ja sam Nyx Light, vaš AI računovodstveni asistent.\n"
                    "Pitajte me o PDV-u, kontiranju, plaćama ili zakonima.\n"
                    "⚠️ AI model nije pokrenut — osnovna funkcionalnost je dostupna.")

        return ("Primio sam vaš upit. Osnovna funkcionalnost radi — "
                "pokušajte pitanja o PDV-u, plaćama, kontiranju ili rokovima.\n"
                "Za potpune AI odgovore pokrenite: `./start.sh llm`")
