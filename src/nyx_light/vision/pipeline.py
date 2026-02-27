"""
Nyx Light — Vision AI Pipeline (Qwen3-VL-8B-Instruct)

Čita skenove, PDF-ove i slike dokumenata putem multimodalnog LLM-a.
Podržava:
  - Računi (ulazni/izlazni, HR + EU + inozemni)
  - Bankovni izvodi
  - Blagajnički primci
  - Putni nalozi
  - Ugovori (samo detekcija, ne pravna analiza)
  - IOS obrasci
  - EU e-fakture (Peppol, ZUGFeRD, FatturaPA vizualno)

Dva moda rada:
  1. vLLM-MLX server (produkcija): HTTP POST s base64 slikom
  2. Direct MLX (development): Lokalni model poziv

Model: Qwen3-VL-8B-Instruct (4-bit MLX, ~5GB RAM)
  - OCR u 32 jezika (uključujući HR, DE, IT, SI, FR, EN)
  - DeepStack arhitektura za fine-grained detalje
  - Tolerantan na blur, tilt, low-light skenove
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("nyx_light.vision")


class DocumentType(str, Enum):
    """Tipovi dokumenata koje Vision AI prepoznaje."""
    ULAZNI_RACUN = "ulazni_racun"
    IZLAZNI_RACUN = "izlazni_racun"
    EU_RACUN = "eu_racun"
    INOZEMNI_RACUN = "inozemni_racun"
    BANKOVNI_IZVOD = "bankovni_izvod"
    BLAGAJNICKI_PRIMAK = "blagajnicki_primak"
    PUTNI_NALOG = "putni_nalog"
    IOS_OBRAZAC = "ios_obrazac"
    UGOVOR = "ugovor"
    NEPOZNATO = "nepoznato"


@dataclass
class VisionResult:
    """Rezultat Vision AI ekstrakcije."""
    document_type: DocumentType = DocumentType.NEPOZNATO
    raw_text: str = ""
    structured_data: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    processing_time_ms: float = 0.0
    model_used: str = ""
    pages_processed: int = 0
    warnings: List[str] = field(default_factory=list)
    error: Optional[str] = None


# Prompt za ekstrakciju podataka iz računa
INVOICE_EXTRACTION_PROMPT = """Analiziraj ovaj skenirani dokument (račun/fakturu).
Izvuci TOČNO ove podatke u JSON formatu:

{
  "tip_dokumenta": "ulazni_racun" ili "izlazni_racun",
  "izdavatelj": {
    "naziv": "...",
    "oib": "...",
    "adresa": "...",
    "iban": "..."
  },
  "primatelj": {
    "naziv": "...",
    "oib": "...",
    "adresa": "..."
  },
  "racun": {
    "broj": "...",
    "datum_izdavanja": "DD.MM.YYYY.",
    "datum_dospijeca": "DD.MM.YYYY.",
    "datum_isporuke": "DD.MM.YYYY.",
    "poziv_na_broj": "..."
  },
  "stavke": [
    {
      "opis": "...",
      "kolicina": 0.0,
      "cijena_bez_pdv": 0.00,
      "pdv_stopa": 25,
      "pdv_iznos": 0.00,
      "ukupno": 0.00
    }
  ],
  "rekapitulacija": {
    "osnovica_25": 0.00,
    "pdv_25": 0.00,
    "osnovica_13": 0.00,
    "pdv_13": 0.00,
    "osnovica_5": 0.00,
    "pdv_5": 0.00,
    "ukupno_bez_pdv": 0.00,
    "ukupno_pdv": 0.00,
    "ukupno_za_platiti": 0.00
  },
  "napomene": "..."
}

PRAVILA:
- OIB ima TOČNO 11 znamenki
- IBAN format: HR + 19 znamenki
- Iznosi u EUR (ili HRK ako je stariji dokument, 1 EUR = 7,53450 HRK)
- PDV stope u RH: 25%, 13%, 5%, 0%
- Ako podatak nije vidljiv, stavi null
- Datumi u formatu DD.MM.YYYY.
"""

# Prompt za generičku ekstrakciju
GENERIC_EXTRACTION_PROMPT = """Analiziraj ovaj dokument i izvuci sve relevantne podatke.
Odgovori u JSON formatu s ključevima:
- tip_dokumenta: vrsta dokumenta
- sadrzaj: ključni sadržaj
- datumi: svi datumi u dokumentu
- iznosi: svi novčani iznosi
- osobe_tvrtke: imena osoba ili tvrtki
- oib_brojevi: svi OIB-ovi
- iban_brojevi: svi IBAN-ovi
- napomene: dodatne bitne informacije
"""

# Prompt za bankovni izvod
BANK_STATEMENT_PROMPT = """Analiziraj ovaj bankovni izvod i za svaku transakciju izvuci:
{
  "banka": "naziv banke",
  "iban_vlasnika": "...",
  "datum_izvoda": "DD.MM.YYYY.",
  "pocetni_saldo": 0.00,
  "zavrsni_saldo": 0.00,
  "transakcije": [
    {
      "datum": "DD.MM.YYYY.",
      "opis": "...",
      "iznos": 0.00,
      "tip": "uplata" ili "isplata",
      "iban_druge_strane": "...",
      "poziv_na_broj": "...",
      "naziv_druge_strane": "..."
    }
  ]
}
"""


class VisionPipeline:
    """
    Glavni pipeline za Vision AI ekstrakciju dokumenata.

    Koristi Qwen2.5-VL-7B za čitanje slika i PDF-ova.
    Podržava vLLM-MLX server i direct MLX backend.
    """

    SUPPORTED_IMAGE_FORMATS = {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"}
    SUPPORTED_PDF_FORMATS = {".pdf"}
    MAX_IMAGE_SIZE_MB = 20
    MAX_PAGES_PER_DOC = 50

    def __init__(
        self,
        vllm_host: str = "127.0.0.1",
        vllm_port: int = 8080,
        vision_model: str = "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
        max_tokens: int = 4096,
        temperature: float = 0.1,  # Niska za preciznost ekstrakcije
    ):
        self.vllm_host = vllm_host
        self.vllm_port = vllm_port
        self.vision_model = vision_model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._stats = {
            "total_processed": 0,
            "successful": 0,
            "failed": 0,
            "total_time_ms": 0.0,
        }
        logger.info(
            "VisionPipeline inicijaliziran — model=%s, server=%s:%d",
            vision_model, vllm_host, vllm_port,
        )

    # ──────────────────────────────────────────────
    # Javni API
    # ──────────────────────────────────────────────

    async def process_document(
        self,
        file_path: str,
        document_type: Optional[DocumentType] = None,
        page_range: Optional[Tuple[int, int]] = None,
    ) -> VisionResult:
        """
        Procesiraj dokument — automatski detektira tip i ekstrahira podatke.

        Args:
            file_path: Put do datoteke (PDF, slika)
            document_type: Ako je poznat tip, preskoči klasifikaciju
            page_range: (start, end) za PDF-ove — 0-indexed, inclusive
        """
        start_time = time.monotonic()
        path = Path(file_path)

        # Validacija
        if not path.exists():
            return VisionResult(error=f"Datoteka ne postoji: {file_path}")

        suffix = path.suffix.lower()
        if suffix not in self.SUPPORTED_IMAGE_FORMATS | self.SUPPORTED_PDF_FORMATS:
            return VisionResult(
                error=f"Nepodržani format: {suffix}. "
                f"Podržani: {self.SUPPORTED_IMAGE_FORMATS | self.SUPPORTED_PDF_FORMATS}",
            )

        # Veličina datoteke
        size_mb = path.stat().st_size / (1024 * 1024)
        if size_mb > self.MAX_IMAGE_SIZE_MB:
            return VisionResult(
                error=f"Datoteka prevelika: {size_mb:.1f} MB (max {self.MAX_IMAGE_SIZE_MB} MB)",
            )

        try:
            # Konvertiranje u slike
            images = await self._load_document(path, page_range)
            if not images:
                return VisionResult(error="Nije moguće učitati dokument")

            # Korak 1: Klasifikacija tipa (ako nije zadan)
            if document_type is None:
                document_type = await self._classify_document(images[0])

            # Korak 2: Ekstrakcija prema tipu
            prompt = self._get_extraction_prompt(document_type)
            structured = await self._extract_with_vision(images, prompt)

            elapsed = (time.monotonic() - start_time) * 1000
            self._stats["total_processed"] += 1
            self._stats["successful"] += 1
            self._stats["total_time_ms"] += elapsed

            result = VisionResult(
                document_type=document_type,
                raw_text=structured.get("_raw_response", ""),
                structured_data=structured,
                confidence=structured.get("_confidence", 0.7),
                processing_time_ms=elapsed,
                model_used=self.vision_model,
                pages_processed=len(images),
            )

            # Validacija rezultata
            self._validate_result(result)
            return result

        except Exception as e:
            elapsed = (time.monotonic() - start_time) * 1000
            self._stats["total_processed"] += 1
            self._stats["failed"] += 1
            logger.error("Vision pipeline error: %s", e, exc_info=True)
            return VisionResult(
                error=str(e),
                processing_time_ms=elapsed,
            )

    async def process_batch(
        self,
        file_paths: List[str],
        max_concurrent: int = 3,
    ) -> List[VisionResult]:
        """Procesira više dokumenata paralelno (ograničeno na max_concurrent)."""
        semaphore = asyncio.Semaphore(max_concurrent)

        async def _process_one(fp: str) -> VisionResult:
            async with semaphore:
                return await self.process_document(fp)

        tasks = [_process_one(fp) for fp in file_paths]
        return await asyncio.gather(*tasks)

    def get_stats(self) -> Dict[str, Any]:
        """Statistike pipeline-a."""
        avg_time = (
            self._stats["total_time_ms"] / self._stats["total_processed"]
            if self._stats["total_processed"] > 0
            else 0
        )
        return {
            **self._stats,
            "avg_time_ms": round(avg_time, 1),
            "success_rate": (
                self._stats["successful"] / self._stats["total_processed"] * 100
                if self._stats["total_processed"] > 0
                else 0
            ),
        }

    # ──────────────────────────────────────────────
    # Interni metodi
    # ──────────────────────────────────────────────

    async def _load_document(
        self, path: Path, page_range: Optional[Tuple[int, int]] = None,
    ) -> List[str]:
        """Učitaj dokument i vrati listu base64-kodiranih slika."""
        suffix = path.suffix.lower()

        if suffix in self.SUPPORTED_IMAGE_FORMATS:
            # Direktno učitaj sliku
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            return [b64]

        elif suffix == ".pdf":
            return await self._pdf_to_images(path, page_range)

        return []

    async def _pdf_to_images(
        self, path: Path, page_range: Optional[Tuple[int, int]] = None,
    ) -> List[str]:
        """Konvertiraj PDF stranice u base64 slike koristeći pdf2image ili PyMuPDF."""
        images: List[str] = []

        try:
            # Pokušaj PyMuPDF (fitz) — brži i ne zahtijeva poppler
            import fitz  # type: ignore[import-untyped]

            doc = fitz.open(str(path))
            total_pages = len(doc)

            start = page_range[0] if page_range else 0
            end = min(
                page_range[1] if page_range else total_pages - 1,
                total_pages - 1,
                self.MAX_PAGES_PER_DOC - 1,
            )

            for page_num in range(start, end + 1):
                page = doc[page_num]
                # Render na 300 DPI za dobar OCR
                mat = fitz.Matrix(300 / 72, 300 / 72)
                pix = page.get_pixmap(matrix=mat)
                img_bytes = pix.tobytes("png")
                b64 = base64.b64encode(img_bytes).decode("utf-8")
                images.append(b64)

            doc.close()
            logger.info("PDF %s: %d stranica renderirano (PyMuPDF)", path.name, len(images))

        except ImportError:
            # Fallback: pdf2image (zahtijeva poppler)
            try:
                from pdf2image import convert_from_path  # type: ignore[import-untyped]

                pil_images = convert_from_path(
                    str(path),
                    dpi=300,
                    first_page=(page_range[0] + 1) if page_range else 1,
                    last_page=(page_range[1] + 1) if page_range else None,
                )
                for pil_img in pil_images[: self.MAX_PAGES_PER_DOC]:
                    buf = io.BytesIO()
                    pil_img.save(buf, format="PNG")
                    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
                    images.append(b64)

                logger.info("PDF %s: %d stranica (pdf2image)", path.name, len(images))

            except ImportError:
                logger.warning(
                    "Ni PyMuPDF ni pdf2image nisu instalirani. "
                    "Pokušavam čisti tekst iz PDF-a.",
                )
                # Zadnji fallback — čisti tekst bez slika
                # (neće raditi s Vision AI, ali može za regex parsing)

        return images

    async def _classify_document(self, image_b64: str) -> DocumentType:
        """Klasificiraj tip dokumenta pomoću Vision AI."""
        prompt = (
            "Pogledaj ovaj dokument i odredi njegov tip. "
            "Odgovori SAMO jednom riječju:\n"
            "- ulazni_racun\n"
            "- izlazni_racun\n"
            "- bankovni_izvod\n"
            "- blagajnicki_primak\n"
            "- putni_nalog\n"
            "- ios_obrazac\n"
            "- ugovor\n"
            "- nepoznato\n"
        )

        response = await self._call_vision_model(image_b64, prompt, max_tokens=50)
        response_lower = response.strip().lower()

        # Mapiraj odgovor na enum
        for dt in DocumentType:
            if dt.value in response_lower:
                logger.info("Dokument klasificiran kao: %s", dt.value)
                return dt

        logger.warning("Neprepoznat tip dokumenta: '%s'", response)
        return DocumentType.NEPOZNATO

    async def _extract_with_vision(
        self, images: List[str], prompt: str,
    ) -> Dict[str, Any]:
        """Ekstrahiraj strukturirane podatke iz slika pomoću Vision AI."""
        # Za višestranične dokumente, šalji prvu stranicu za ekstrakciju
        # (ili sve stranice za batch ekstrakciju)
        all_data: Dict[str, Any] = {}
        raw_responses: List[str] = []

        for i, img_b64 in enumerate(images):
            page_prompt = prompt
            if len(images) > 1:
                page_prompt = f"[Stranica {i + 1}/{len(images)}]\n{prompt}"

            response = await self._call_vision_model(img_b64, page_prompt)
            raw_responses.append(response)

            # Pokušaj parsirati JSON iz odgovora
            parsed = self._extract_json(response)
            if parsed:
                all_data = self._merge_page_data(all_data, parsed)

        all_data["_raw_response"] = "\n---\n".join(raw_responses)
        all_data["_confidence"] = self._calculate_confidence(all_data)
        return all_data

    async def _call_vision_model(
        self, image_b64: str, prompt: str, max_tokens: Optional[int] = None,
    ) -> str:
        """Pozovi Vision model (Qwen2.5-VL) putem vLLM-MLX servera ili direktno."""
        try:
            import aiohttp

            # OpenAI-kompatibilni API poziv za vision
            url = f"http://{self.vllm_host}:{self.vllm_port}/v1/chat/completions"

            payload = {
                "model": self.vision_model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{image_b64}",
                                },
                            },
                            {
                                "type": "text",
                                "text": prompt,
                            },
                        ],
                    },
                ],
                "max_tokens": max_tokens or self.max_tokens,
                "temperature": self.temperature,
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data["choices"][0]["message"]["content"]
                    else:
                        error_text = await resp.text()
                        logger.error("vLLM server error %d: %s", resp.status, error_text)
                        return f"ERROR: vLLM server returned {resp.status}"

        except ImportError:
            logger.warning("aiohttp nije instaliran, koristim fallback")
            return await self._call_vision_direct(image_b64, prompt)

        except Exception as e:
            logger.error("Vision API call failed: %s", e)
            return await self._call_vision_direct(image_b64, prompt)

    async def _call_vision_direct(self, image_b64: str, prompt: str) -> str:
        """Fallback: direktan poziv MLX modela (development mode)."""
        try:
            from mlx_vlm import load, generate  # type: ignore[import-untyped]

            model, processor = load(self.vision_model)
            output = generate(
                model,
                processor,
                prompt,
                image=base64.b64decode(image_b64),
                max_tokens=self.max_tokens,
                temp=self.temperature,
            )
            return output

        except ImportError:
            logger.warning(
                "mlx_vlm nije instaliran. Vision AI nije dostupan. "
                "Instalirajte: pip install mlx-vlm",
            )
            return '{"error": "Vision model nije dostupan", "_confidence": 0}'

    def _get_extraction_prompt(self, doc_type: DocumentType) -> str:
        """Vrati odgovarajući ekstrakcijski prompt za tip dokumenta."""
        prompts = {
            DocumentType.ULAZNI_RACUN: INVOICE_EXTRACTION_PROMPT,
            DocumentType.IZLAZNI_RACUN: INVOICE_EXTRACTION_PROMPT,
            DocumentType.BANKOVNI_IZVOD: BANK_STATEMENT_PROMPT,
            DocumentType.BLAGAJNICKI_PRIMAK: self._blagajna_prompt(),
            DocumentType.PUTNI_NALOG: self._putni_nalog_prompt(),
            DocumentType.IOS_OBRAZAC: self._ios_prompt(),
        }
        return prompts.get(doc_type, GENERIC_EXTRACTION_PROMPT)

    def _extract_json(self, text: str) -> Optional[Dict[str, Any]]:
        """Izvuci JSON iz odgovora modela (može biti umotan u markdown)."""
        # Pokušaj 1: Čisti JSON
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            pass

        # Pokušaj 2: JSON unutar ```json ... ``` bloka
        json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except (json.JSONDecodeError, ValueError):
                pass

        # Pokušaj 3: Traži prvi { ... } blok
        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except (json.JSONDecodeError, ValueError):
                pass

        logger.warning("Nije moguće parsirati JSON iz odgovora Vision modela")
        return None

    def _merge_page_data(
        self, existing: Dict[str, Any], new: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Spoji podatke s više stranica."""
        if not existing:
            return new.copy()

        merged = existing.copy()
        for key, value in new.items():
            if key.startswith("_"):
                continue
            if key not in merged:
                merged[key] = value
            elif isinstance(value, list) and isinstance(merged.get(key), list):
                merged[key].extend(value)
            elif isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = self._merge_page_data(merged[key], value)
            # Za skalarne vrijednosti, zadrži prvotnu (obično header stranica)
        return merged

    def _calculate_confidence(self, data: Dict[str, Any]) -> float:
        """Izračunaj razinu pouzdanosti na temelju kompletnosti podataka."""
        if not data or "error" in data:
            return 0.0

        score = 0.3  # Bazna pouzdanost ako je išta parsirano

        # Provjeri ključne podatke za račun
        if "izdavatelj" in data:
            izdavatelj = data["izdavatelj"]
            if isinstance(izdavatelj, dict):
                if izdavatelj.get("oib") and len(str(izdavatelj["oib"])) == 11:
                    score += 0.15
                if izdavatelj.get("naziv"):
                    score += 0.05
                if izdavatelj.get("iban") and str(izdavatelj.get("iban", "")).startswith("HR"):
                    score += 0.1

        if "racun" in data:
            racun = data["racun"]
            if isinstance(racun, dict):
                if racun.get("broj"):
                    score += 0.1
                if racun.get("datum_izdavanja"):
                    score += 0.1

        if "rekapitulacija" in data:
            rekap = data["rekapitulacija"]
            if isinstance(rekap, dict):
                if rekap.get("ukupno_za_platiti") and rekap["ukupno_za_platiti"] > 0:
                    score += 0.2

        return min(1.0, round(score, 2))

    def _validate_result(self, result: VisionResult) -> None:
        """Dodaj upozorenja za sumnjive podatke."""
        data = result.structured_data

        # Provjeri OIB checksum (mod 11)
        for key_path in [("izdavatelj", "oib"), ("primatelj", "oib")]:
            oib = data
            for k in key_path:
                if isinstance(oib, dict):
                    oib = oib.get(k, "")
                else:
                    oib = ""
                    break
            if oib and isinstance(oib, str) and len(oib) == 11:
                if not self._validate_oib(oib):
                    result.warnings.append(f"OIB {oib} ne prolazi provjeru kontrolne znamenke")

        # Provjeri IBAN format
        for key_path in [("izdavatelj", "iban")]:
            iban = data
            for k in key_path:
                if isinstance(iban, dict):
                    iban = iban.get(k, "")
                else:
                    iban = ""
                    break
            if iban and isinstance(iban, str):
                if not re.match(r"^HR\d{19}$", iban):
                    result.warnings.append(f"IBAN {iban} nije u ispravnom HR formatu")

        # Provjeri PDV stope
        if "stavke" in data and isinstance(data["stavke"], list):
            for stavka in data["stavke"]:
                if isinstance(stavka, dict):
                    pdv = stavka.get("pdv_stopa")
                    if pdv is not None and pdv not in (0, 5, 13, 25):
                        result.warnings.append(
                            f"Neuobičajena PDV stopa: {pdv}% (dozvoljene: 0%, 5%, 13%, 25%)",
                        )

        if result.confidence < 0.5:
            result.warnings.append("Niska pouzdanost — preporučena ručna provjera")

    @staticmethod
    def _validate_oib(oib: str) -> bool:
        """Validacija OIB-a (mod 11, ISO 7064)."""
        if not oib.isdigit() or len(oib) != 11:
            return False
        remainder = 10
        for i in range(10):
            remainder = (remainder + int(oib[i])) % 10
            if remainder == 0:
                remainder = 10
            remainder = (remainder * 2) % 11
        control = 11 - remainder
        if control == 10:
            control = 0
        return control == int(oib[10])

    # ──────────────────────────────────────────────
    # Specifični promptovi za tipove dokumenata
    # ──────────────────────────────────────────────

    @staticmethod
    def _blagajna_prompt() -> str:
        return """Analiziraj blagajnički dokument i izvuci:
{
  "tip": "primitak" ili "izdatak",
  "broj": "...",
  "datum": "DD.MM.YYYY.",
  "opis": "...",
  "iznos": 0.00,
  "primio_od": "...",
  "isplatio": "...",
  "saldo_prije": 0.00,
  "saldo_nakon": 0.00
}
"""

    @staticmethod
    def _putni_nalog_prompt() -> str:
        return """Analiziraj putni nalog i izvuci:
{
  "broj_naloga": "...",
  "ime_zaposlenika": "...",
  "oib_zaposlenika": "...",
  "odrediste": "...",
  "svrha_puta": "...",
  "datum_polaska": "DD.MM.YYYY.",
  "datum_povratka": "DD.MM.YYYY.",
  "prijevozno_sredstvo": "osobni_automobil" ili "sluzbeno_vozilo" ili "autobus" ili "vlak",
  "kilometri": 0,
  "km_naknada_eur": 0.30,
  "dnevnica_eur": 0.00,
  "smjestaj_eur": 0.00,
  "ostali_troskovi_eur": 0.00,
  "ukupno_eur": 0.00,
  "reprezentacija_eur": 0.00
}
Napomena: km-naknada max 0,30 EUR/km. Reprezentacija 50% porezno nepriznato.
"""

    @staticmethod
    def _ios_prompt() -> str:
        return """Analiziraj IOS obrazac (Izvod otvorenih stavki) i izvuci:
{
  "izdavatelj": {"naziv": "...", "oib": "..."},
  "primatelj": {"naziv": "...", "oib": "..."},
  "datum_ios": "DD.MM.YYYY.",
  "datum_stanja": "DD.MM.YYYY.",
  "stavke": [
    {
      "broj_dokumenta": "...",
      "datum_dokumenta": "DD.MM.YYYY.",
      "datum_dospijeca": "DD.MM.YYYY.",
      "duguje": 0.00,
      "potrazuje": 0.00,
      "saldo": 0.00
    }
  ],
  "ukupno_duguje": 0.00,
  "ukupno_potrazuje": 0.00,
  "razlika": 0.00,
  "status": "suglasan" ili "nesuglasan"
}
"""
