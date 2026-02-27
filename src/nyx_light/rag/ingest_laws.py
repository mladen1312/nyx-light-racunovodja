"""
Nyx Light — Law Ingestion Pipeline

Učitava .md datoteke zakona iz data/laws/ u EmbeddedVectorStore.
Parsira YAML metadata, splitta po člancima, kreira chunks za RAG.
"""

import logging
import re
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid5, NAMESPACE_DNS

logger = logging.getLogger("nyx_light.rag.ingest_laws")


def parse_law_file(filepath: Path) -> Dict[str, Any]:
    """
    Parsiraj .md law file s YAML frontmatter i markdown sadržajem.

    Returns:
        {
            "metadata": {"zakon": ..., "nn": ..., ...},
            "articles": [{"number": "1", "text": "..."}, ...],
            "raw_text": "..."
        }
    """
    text = filepath.read_text(encoding="utf-8")

    # Extract YAML frontmatter
    metadata = {}
    content = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            try:
                metadata = yaml.safe_load(parts[1]) or {}
            except yaml.YAMLError:
                pass
            content = parts[2].strip()

    # Split by articles (Članak X.)
    articles = []
    # Pattern: "Članak X." or "Članak X\n"
    article_pattern = re.compile(
        r'^(?:Članak|Članak)\s+(\d+[a-z]?)\s*\.?\s*$',
        re.MULTILINE
    )

    splits = article_pattern.split(content)
    if len(splits) > 1:
        # splits = [preamble, "1", text1, "2", text2, ...]
        preamble = splits[0].strip()
        if preamble:
            articles.append({"number": "preambula", "text": preamble})

        for i in range(1, len(splits), 2):
            num = splits[i]
            txt = splits[i + 1].strip() if i + 1 < len(splits) else ""
            if txt:
                articles.append({"number": num, "text": txt})
    else:
        # No article headers — split by double newlines into paragraphs
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        for i, para in enumerate(paragraphs):
            articles.append({"number": str(i + 1), "text": para})

    return {
        "metadata": metadata,
        "articles": articles,
        "raw_text": content,
        "filename": filepath.name,
    }


def create_chunks_from_law(parsed: Dict) -> List[Dict[str, Any]]:
    """Kreiraj chunk-ove za vektorsku bazu iz parsiranog zakona."""
    from nyx_light.rag.embedded_store import LawChunk

    meta = parsed["metadata"]
    law_name = meta.get("zakon", parsed["filename"].replace(".md", ""))
    nn = meta.get("nn", "")
    eff_from = meta.get("datum_stupanja", "")
    eff_to = meta.get("datum_prestanka", None)

    chunks = []
    for article in parsed["articles"]:
        # Deterministic ID based on law + article
        chunk_id = str(uuid5(NAMESPACE_DNS, f"{law_name}::{article['number']}"))

        chunk = LawChunk(
            text=f"[{law_name}] Članak {article['number']}:\n{article['text']}",
            law_name=law_name,
            article_number=article["number"],
            effective_from=str(eff_from) if eff_from else None,
            effective_to=str(eff_to) if eff_to else None,
            source_nn=str(nn),
            chunk_id=chunk_id,
            metadata={"filename": parsed["filename"]},
        )
        chunks.append(chunk)

    return chunks


def ingest_all_laws(
    laws_dir: str = "data/laws",
    store=None,
) -> Dict[str, Any]:
    """
    Učitaj sve zakone iz direktorija u vector store.

    Args:
        laws_dir: Putanja do .md datoteka
        store: EmbeddedVectorStore instanca (kreira se ako None)

    Returns:
        {"laws_processed": N, "chunks_ingested": M, "errors": [...]}
    """
    laws_path = Path(laws_dir)
    if not laws_path.exists():
        return {"error": f"Dir {laws_dir} ne postoji", "laws_processed": 0}

    # Create store if not provided
    if store is None:
        from nyx_light.rag.embedded_store import EmbeddedVectorStore
        store = EmbeddedVectorStore()
        store.initialize()

    law_files = sorted(laws_path.glob("*.md"))
    total_chunks = 0
    errors = []
    laws_meta = []

    for lf in law_files:
        try:
            parsed = parse_law_file(lf)
            chunks = create_chunks_from_law(parsed)

            if chunks:
                result = store.ingest_chunks(chunks)
                total_chunks += result.get("ingested", 0)

            laws_meta.append({
                "file": lf.name,
                "law": parsed["metadata"].get("zakon", lf.stem),
                "nn": parsed["metadata"].get("nn", ""),
                "articles": len(parsed["articles"]),
                "chunks": len(chunks),
            })

            logger.info("Ingested %s: %d chunks", lf.name, len(chunks))
        except Exception as e:
            errors.append({"file": lf.name, "error": str(e)})
            logger.error("Error ingesting %s: %s", lf.name, e)

    return {
        "laws_processed": len(law_files),
        "chunks_ingested": total_chunks,
        "total_in_store": store.get_stats()["documents"],
        "laws": laws_meta,
        "errors": errors,
    }
