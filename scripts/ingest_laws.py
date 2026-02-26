#!/usr/bin/env python3
"""
Nyx Light — RAG Ingest: Učitavanje zakona RH u vektorsku bazu

Učitava zakonske tekstove iz data/laws/ u Qdrant vektorsku bazu
s time-awareness metapodacima (datum stupanja na snagu, izmjene).

Podržani formati: .txt, .pdf, .md
Struktura imenovanja: ZAKON_O_PDV_NN_73_13_izmjena_2024.txt

Korištenje:
    python -m scripts.ingest_laws
    python -m scripts.ingest_laws --dir data/laws --collection hr_zakoni
"""

import argparse
import hashlib
import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logger = logging.getLogger("nyx_light.ingest")

# Chunk settings
CHUNK_SIZE = 1000  # tokena (≈ 4000 znakova)
CHUNK_OVERLAP = 200  # znakova preklapanja
MAX_CHUNK_CHARS = 4000
OVERLAP_CHARS = 800


def extract_law_metadata(filename: str) -> Dict[str, Any]:
    """
    Izvuci metapodatke iz imena datoteke.
    
    Konvencija: ZAKON_O_PDV_NN_73_13_izmjena_2024.txt
    → law_name: "Zakon o PDV-u"
    → nn_number: "73/13"
    → amendment_year: 2024
    """
    name = Path(filename).stem.upper()
    
    metadata = {
        "filename": filename,
        "law_name": "",
        "nn_number": "",
        "nn_year": None,
        "amendment_year": None,
        "effective_from": None,
        "category": "zakon",
    }
    
    # Detect law category
    law_patterns = {
        "PDV": ("Zakon o porezu na dodanu vrijednost", "pdv"),
        "DOBIT": ("Zakon o porezu na dobit", "porez_dobit"),
        "DOHODAK": ("Zakon o porezu na dohodak", "porez_dohodak"),
        "RACUNOVODST": ("Zakon o računovodstvu", "racunovodstvo"),
        "FISKALIZACIJ": ("Zakon o fiskalizaciji", "fiskalizacija"),
        "TRGOVAC": ("Zakon o trgovačkim društvima", "trgovacka_drustva"),
    }
    
    for pattern, (full_name, cat) in law_patterns.items():
        if pattern in name:
            metadata["law_name"] = full_name
            metadata["category"] = cat
            break
    
    if not metadata["law_name"]:
        # Fallback: Clean up filename
        clean = Path(filename).stem.replace("_", " ").title()
        metadata["law_name"] = clean
    
    # Extract NN number
    nn_match = re.search(r"NN[_\s]*(\d+)[_/](\d+)", name)
    if nn_match:
        metadata["nn_number"] = f"{nn_match.group(1)}/{nn_match.group(2)}"
        metadata["nn_year"] = int(nn_match.group(2))
        if metadata["nn_year"] < 100:
            metadata["nn_year"] += 2000 if metadata["nn_year"] < 50 else 1900
    
    # Extract amendment year
    amend_match = re.search(r"IZMJEN\w*[_\s]*(\d{4})", name)
    if amend_match:
        metadata["amendment_year"] = int(amend_match.group(1))
    
    # Effective from (best guess)
    year = metadata["amendment_year"] or metadata["nn_year"]
    if year:
        metadata["effective_from"] = f"{year}-01-01"
    
    return metadata


def chunk_text(text: str, max_chars: int = MAX_CHUNK_CHARS, overlap: int = OVERLAP_CHARS) -> List[str]:
    """Razbij tekst na chunks s preklapanjem."""
    if len(text) <= max_chars:
        return [text]
    
    chunks = []
    start = 0
    while start < len(text):
        end = start + max_chars
        
        # Probaj prekinuti na kraju paragrafa ili rečenice
        if end < len(text):
            # Traži kraj paragrafa
            para_break = text.rfind("\n\n", start + max_chars // 2, end)
            if para_break > start:
                end = para_break + 2
            else:
                # Traži kraj rečenice
                sent_break = text.rfind(". ", start + max_chars // 2, end)
                if sent_break > start:
                    end = sent_break + 2
        
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        
        start = end - overlap
    
    return chunks


def extract_articles(text: str) -> List[Dict[str, str]]:
    """Izvuci pojedine članke iz zakonskog teksta."""
    # Regex za "Članak 1.", "Čl. 1.", "Članak 123."
    article_pattern = re.compile(
        r'(?:Članak|Čl\.?)\s+(\d+)\.?\s*\n(.*?)(?=(?:Članak|Čl\.?)\s+\d+\.?\s*\n|\Z)',
        re.DOTALL | re.IGNORECASE
    )
    
    articles = []
    for match in article_pattern.finditer(text):
        articles.append({
            "article_number": int(match.group(1)),
            "text": match.group(2).strip(),
        })
    
    return articles


def read_file(filepath: Path) -> str:
    """Čitaj datoteku (TXT, MD, ili PDF)."""
    suffix = filepath.suffix.lower()
    
    if suffix in (".txt", ".md"):
        return filepath.read_text(encoding="utf-8")
    
    elif suffix == ".pdf":
        try:
            import PyPDF2
            reader = PyPDF2.PdfReader(str(filepath))
            text = ""
            for page in reader.pages:
                text += page.extract_text() + "\n"
            return text
        except ImportError:
            logger.warning("PyPDF2 nije instaliran. Preskačem PDF: %s", filepath)
            return ""
    
    else:
        logger.warning("Nepodržani format: %s", filepath)
        return ""


def compute_hash(text: str) -> str:
    """SHA256 hash za deduplication."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class LawIngestor:
    """Učitava zakone u Qdrant vektorsku bazu."""
    
    def __init__(
        self,
        qdrant_url: str = "http://localhost:6333",
        collection: str = "hr_zakoni",
        embedding_dim: int = 384,  # sentence-transformers default
    ):
        self.qdrant_url = qdrant_url
        self.collection = collection
        self.embedding_dim = embedding_dim
        self._client = None
        self._encoder = None
        self.stats = {
            "files_processed": 0,
            "chunks_created": 0,
            "articles_extracted": 0,
            "errors": 0,
        }
    
    def _init_qdrant(self):
        """Inicijaliziraj Qdrant klijent i kolekciju."""
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams
            
            self._client = QdrantClient(url=self.qdrant_url)
            
            # Kreiraj kolekciju ako ne postoji
            collections = [c.name for c in self._client.get_collections().collections]
            if self.collection not in collections:
                self._client.create_collection(
                    collection_name=self.collection,
                    vectors_config=VectorParams(
                        size=self.embedding_dim,
                        distance=Distance.COSINE,
                    ),
                )
                logger.info("Kreirana Qdrant kolekcija: %s", self.collection)
            
            return True
        except Exception as e:
            logger.error("Qdrant nije dostupan: %s", e)
            return False
    
    def _init_encoder(self):
        """Inicijaliziraj sentence encoder."""
        try:
            from sentence_transformers import SentenceTransformer
            self._encoder = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
            logger.info("Encoder učitan: paraphrase-multilingual-MiniLM-L12-v2")
            return True
        except ImportError:
            logger.warning("sentence-transformers nije instaliran. Koristim dummy vektore.")
            return False
    
    def _encode(self, texts: List[str]) -> List[List[float]]:
        """Generiraj embedding vektore."""
        if self._encoder:
            return self._encoder.encode(texts).tolist()
        # Dummy vectors za testiranje bez modela
        import random
        return [[random.gauss(0, 0.1) for _ in range(self.embedding_dim)] for _ in texts]
    
    def ingest_directory(self, law_dir: str = "data/laws") -> Dict[str, Any]:
        """Procesiraj sve zakonske datoteke iz direktorija."""
        law_path = Path(law_dir)
        if not law_path.exists():
            logger.error("Direktorij ne postoji: %s", law_dir)
            return self.stats
        
        files = list(law_path.glob("*.txt")) + list(law_path.glob("*.md")) + list(law_path.glob("*.pdf"))
        
        if not files:
            logger.warning("Nema zakonskih datoteka u %s", law_dir)
            logger.info("Dodajte datoteke u format: ZAKON_O_PDV_NN_73_13.txt")
            return self.stats
        
        # Init
        qdrant_ok = self._init_qdrant()
        self._init_encoder()
        
        logger.info("Pronađeno %d datoteka za obradu", len(files))
        
        all_chunks = []
        
        for filepath in sorted(files):
            logger.info("Obrađujem: %s", filepath.name)
            
            try:
                text = read_file(filepath)
                if not text.strip():
                    continue
                
                metadata = extract_law_metadata(filepath.name)
                
                # Pokušaj izvući članke
                articles = extract_articles(text)
                
                if articles:
                    # Svaki članak je chunk
                    for art in articles:
                        chunk_meta = {
                            **metadata,
                            "article_number": art["article_number"],
                            "chunk_type": "article",
                            "hash": compute_hash(art["text"]),
                        }
                        all_chunks.append({
                            "text": f"Članak {art['article_number']}.\n{art['text']}",
                            "metadata": chunk_meta,
                        })
                    self.stats["articles_extracted"] += len(articles)
                    logger.info("  → %d članaka izvučeno", len(articles))
                else:
                    # Padback na chunking
                    chunks = chunk_text(text)
                    for i, chunk in enumerate(chunks):
                        chunk_meta = {
                            **metadata,
                            "chunk_index": i,
                            "chunk_type": "segment",
                            "hash": compute_hash(chunk),
                        }
                        all_chunks.append({
                            "text": chunk,
                            "metadata": chunk_meta,
                        })
                    logger.info("  → %d chunkova kreirano", len(chunks))
                
                self.stats["files_processed"] += 1
                
            except Exception as e:
                logger.error("Greška pri obradi %s: %s", filepath.name, e)
                self.stats["errors"] += 1
        
        self.stats["chunks_created"] = len(all_chunks)
        
        # Upload to Qdrant
        if qdrant_ok and all_chunks:
            self._upload_to_qdrant(all_chunks)
        
        # Spremi i lokalni JSON index
        self._save_local_index(all_chunks, law_dir)
        
        logger.info("═══ Ingest završen ═══")
        logger.info("  Datoteka: %d", self.stats["files_processed"])
        logger.info("  Chunkova: %d", self.stats["chunks_created"])
        logger.info("  Članaka: %d", self.stats["articles_extracted"])
        logger.info("  Grešaka: %d", self.stats["errors"])
        
        return self.stats
    
    def _upload_to_qdrant(self, chunks: List[Dict]):
        """Upload chunkova u Qdrant."""
        from qdrant_client.models import PointStruct
        
        texts = [c["text"] for c in chunks]
        vectors = self._encode(texts)
        
        points = [
            PointStruct(
                id=i,
                vector=vec,
                payload={
                    "text": chunk["text"][:2000],  # Limit payload size
                    **chunk["metadata"],
                },
            )
            for i, (chunk, vec) in enumerate(zip(chunks, vectors))
        ]
        
        # Batch upload (100 per batch)
        batch_size = 100
        for i in range(0, len(points), batch_size):
            batch = points[i:i + batch_size]
            self._client.upsert(
                collection_name=self.collection,
                points=batch,
            )
            logger.info("  Uploaded %d/%d points", min(i + batch_size, len(points)), len(points))
        
        logger.info("✅ %d chunkova učitano u Qdrant kolekciju '%s'", len(points), self.collection)
    
    def _save_local_index(self, chunks: List[Dict], law_dir: str):
        """Spremi lokalni JSON index (fallback bez Qdrant-a)."""
        index_path = Path(law_dir) / "_index.json"
        index_data = {
            "generated_at": datetime.now().isoformat(),
            "total_chunks": len(chunks),
            "chunks": [
                {
                    "text": c["text"][:500],
                    "metadata": c["metadata"],
                }
                for c in chunks
            ],
        }
        index_path.write_text(json.dumps(index_data, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Lokalni index spremljen: %s", index_path)


def main():
    parser = argparse.ArgumentParser(description="Nyx Light — Učitavanje zakona RH u RAG bazu")
    parser.add_argument("--dir", default="data/laws", help="Direktorij sa zakonskim tekstovima")
    parser.add_argument("--collection", default="hr_zakoni", help="Qdrant kolekcija")
    parser.add_argument("--qdrant-url", default="http://localhost:6333", help="Qdrant URL")
    args = parser.parse_args()
    
    ingestor = LawIngestor(
        qdrant_url=args.qdrant_url,
        collection=args.collection,
    )
    
    stats = ingestor.ingest_directory(args.dir)
    
    if stats["files_processed"] == 0:
        print("\n⚠️  Nema zakonskih datoteka za obradu!")
        print(f"Dodajte .txt/.pdf/.md datoteke u: {args.dir}/")
        print("Primjer: ZAKON_O_PDV_NN_73_13.txt")
        print("\nPotrebni zakoni:")
        print("  - Zakon o računovodstvu (NN 78/15)")
        print("  - Zakon o PDV-u (NN 73/13)")
        print("  - Zakon o porezu na dobit (NN 177/04)")
        print("  - Zakon o porezu na dohodak (NN 115/16)")
        print("  - Zakon o fiskalizaciji (NN 133/12)")
        print("  - Mišljenja Porezne uprave")


if __name__ == "__main__":
    main()
