"""
Nyx Light — Law Ingestion Pipeline

Parsira .md zakonske datoteke → chunking → embeddings → vector store.
Podržava YAML frontmatter za metadata.

Chunk strategija:
  - Svaki Članak = 1 chunk
  - Ako je članak > 500 chars, dijeli po stavkama/točkama
  - Dodaje kontekst (naziv zakona, NN) u svaki chunk
"""

import logging
import re
import yaml
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("nyx_light.rag.ingest")


class LawChunkData:
    """Parsed law chunk ready for vector store."""

    def __init__(
        self,
        text: str,
        law_name: str,
        article_number: str = "",
        source_nn: str = "",
        effective_from: str = "",
        effective_to: str = "",
    ):
        self.text = text
        self.law_name = law_name
        self.article_number = article_number
        self.source_nn = source_nn
        self.effective_from = effective_from
        self.effective_to = effective_to

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "law_name": self.law_name,
            "article_number": self.article_number,
            "source_nn": self.source_nn,
            "effective_from": self.effective_from,
            "effective_to": self.effective_to,
        }


class LawIngestor:
    """
    Parsira zakonske .md datoteke i priprema ih za vector store.

    Pipeline:
      1. Čita .md datoteke iz data/laws/
      2. Parsira YAML frontmatter (zakon, nn, datumi)
      3. Dijeli tekst na chunks po člancima
      4. Obogaćuje svaki chunk kontekstom
      5. Šalje u EmbeddedVectorStore
    """

    def __init__(self, laws_dir: str = "data/laws"):
        self.laws_dir = Path(laws_dir)
        self._stats = {"files_parsed": 0, "chunks_created": 0, "errors": 0}

    def parse_all_laws(self) -> List[LawChunkData]:
        """Parsiraj sve .md zakone u chunks."""
        all_chunks = []

        if not self.laws_dir.exists():
            logger.warning("Laws directory not found: %s", self.laws_dir)
            return []

        for md_file in sorted(self.laws_dir.glob("*.md")):
            try:
                chunks = self.parse_law_file(md_file)
                all_chunks.extend(chunks)
                self._stats["files_parsed"] += 1
            except Exception as e:
                self._stats["errors"] += 1
                logger.error("Error parsing %s: %s", md_file.name, e)

        self._stats["chunks_created"] = len(all_chunks)
        logger.info("Parsed %d law files → %d chunks",
                    self._stats["files_parsed"], len(all_chunks))
        return all_chunks

    def parse_law_file(self, filepath: Path) -> List[LawChunkData]:
        """Parsiraj jednu .md zakonsku datoteku."""
        text = filepath.read_text(encoding="utf-8")

        # Parse YAML frontmatter
        metadata = self._parse_frontmatter(text)
        law_name = metadata.get("zakon", filepath.stem.replace("_", " ").title())
        nn = metadata.get("nn", "")
        effective_from = metadata.get("datum_stupanja", "")
        effective_to = ""  # Current laws don't have end date

        # Remove frontmatter from text
        body = self._strip_frontmatter(text)

        # Split into article chunks
        articles = self._split_by_articles(body)

        chunks = []
        for article_num, article_text in articles:
            # Create enriched chunk text with context
            enriched = self._enrich_chunk(article_text, law_name, article_num, nn)

            # If article is very long, split further
            if len(enriched) > 800:
                sub_chunks = self._split_long_article(enriched, article_num)
                for i, sub_text in enumerate(sub_chunks):
                    chunks.append(LawChunkData(
                        text=sub_text,
                        law_name=law_name,
                        article_number=f"{article_num}-{i+1}" if len(sub_chunks) > 1 else article_num,
                        source_nn=str(nn),
                        effective_from=str(effective_from),
                        effective_to=effective_to,
                    ))
            else:
                chunks.append(LawChunkData(
                    text=enriched,
                    law_name=law_name,
                    article_number=article_num,
                    source_nn=str(nn),
                    effective_from=str(effective_from),
                    effective_to=effective_to,
                ))

        # If no articles found, treat whole file as one chunk
        if not chunks and body.strip():
            chunks.append(LawChunkData(
                text=f"[{law_name}, NN {nn}]\n{body.strip()[:1000]}",
                law_name=law_name,
                article_number="opće",
                source_nn=str(nn),
                effective_from=str(effective_from),
            ))

        return chunks

    def _parse_frontmatter(self, text: str) -> Dict[str, Any]:
        """Parse YAML frontmatter between --- delimiters."""
        match = re.match(r'^---\s*\n(.*?)\n---\s*\n', text, re.DOTALL)
        if not match:
            return {}
        try:
            return yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError:
            return {}

    def _strip_frontmatter(self, text: str) -> str:
        """Remove YAML frontmatter."""
        return re.sub(r'^---\s*\n.*?\n---\s*\n', '', text, count=1, flags=re.DOTALL)

    def _split_by_articles(self, text: str) -> List[Tuple[str, str]]:
        """Split text by Članak N. headings."""
        # Pattern: Članak followed by number
        pattern = r'(Članak\s+\d+[a-z]?\.?)'
        parts = re.split(pattern, text, flags=re.IGNORECASE)

        articles = []
        i = 1
        while i < len(parts):
            header = parts[i].strip()
            body = parts[i + 1].strip() if i + 1 < len(parts) else ""

            # Extract article number
            num_match = re.search(r'(\d+[a-z]?)', header)
            art_num = num_match.group(1) if num_match else str(len(articles) + 1)

            if body:
                articles.append((f"čl. {art_num}", f"{header}\n{body}"))
            i += 2

        # Also capture non-article sections (e.g., numbered lists, tables)
        if not articles:
            # Try splitting by numbered sections
            sections = re.split(r'\n(?=\d+\.\s)', text)
            for j, section in enumerate(sections):
                if section.strip():
                    articles.append((f"stavka {j+1}", section.strip()))

        return articles

    def _enrich_chunk(self, text: str, law_name: str, article: str, nn: str) -> str:
        """Add context to chunk for better retrieval."""
        return f"[{law_name}, {article}, NN {nn}]\n{text}"

    def _split_long_article(self, text: str, article_num: str) -> List[str]:
        """Split long article by numbered points or paragraphs."""
        # Try splitting by numbered items (1., 2., 3.)
        items = re.split(r'\n(?=\d+[\.\)]\s)', text)
        if len(items) > 1:
            # Keep header with each chunk
            header = items[0] if len(items[0]) < 200 else ""
            result = []
            current = header
            for item in (items[1:] if header else items):
                if len(current) + len(item) > 600 and current:
                    result.append(current.strip())
                    current = header + "\n" + item
                else:
                    current += "\n" + item
            if current.strip():
                result.append(current.strip())
            return result

        # Fallback: split by double newlines
        paragraphs = text.split("\n\n")
        if len(paragraphs) > 1:
            result = []
            current = ""
            for para in paragraphs:
                if len(current) + len(para) > 600 and current:
                    result.append(current.strip())
                    current = para
                else:
                    current += "\n\n" + para
            if current.strip():
                result.append(current.strip())
            return result

        # Can't split further
        return [text]

    def ingest_to_store(self, store) -> Dict[str, Any]:
        """Parse all laws and ingest into vector store."""
        chunks = self.parse_all_laws()
        if not chunks:
            return {"status": "no_chunks", "files": 0}

        # Convert to store format
        from nyx_light.rag.embedded_store import LawChunk
        store_chunks = []
        for c in chunks:
            store_chunks.append(LawChunk(
                text=c.text,
                law_name=c.law_name,
                article_number=c.article_number,
                source_nn=c.source_nn,
                effective_from=c.effective_from,
                effective_to=c.effective_to,
            ))

        result = store.ingest_chunks(store_chunks)
        return {
            "status": "ok",
            "files_parsed": self._stats["files_parsed"],
            "chunks_created": len(store_chunks),
            "store_result": result,
        }

    def get_stats(self) -> Dict[str, Any]:
        return {**self._stats}
