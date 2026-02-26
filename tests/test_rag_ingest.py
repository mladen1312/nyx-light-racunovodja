"""Tests za RAG ingest — parsiranje zakona i chunk generiranje."""

import os
import tempfile
from pathlib import Path

from scripts.ingest_laws import (
    extract_law_metadata,
    extract_articles,
    chunk_text,
    compute_hash,
    read_file,
)


class TestLawMetadata:
    def test_pdv_metadata(self):
        meta = extract_law_metadata("ZAKON_O_PDV_NN_73_13.txt")
        assert "PDV" in meta["law_name"] or "dodanu" in meta["law_name"]
        assert meta["nn_number"] == "73/13"
        assert meta["category"] == "pdv"

    def test_racunovodstvo_metadata(self):
        meta = extract_law_metadata("ZAKON_O_RACUNOVODSTVU_NN_78_15.txt")
        assert "računovodstv" in meta["law_name"].lower()
        assert meta["nn_number"] == "78/15"

    def test_amendment_year(self):
        meta = extract_law_metadata("ZAKON_O_PDV_NN_73_13_izmjena_2024.txt")
        assert meta["amendment_year"] == 2024


class TestArticleExtraction:
    def test_extract_articles(self):
        text = """Članak 1.
Ovim se Zakonom uređuje sustav PDV-a.

Članak 2.
Predmet oporezivanja je isporuka dobara.

Članak 3.
Porezni obveznik je svaka osoba.
"""
        articles = extract_articles(text)
        assert len(articles) == 3
        assert articles[0]["article_number"] == 1
        assert "PDV" in articles[0]["text"]
        assert articles[1]["article_number"] == 2

    def test_no_articles(self):
        text = "Ovo je obični tekst bez članaka."
        articles = extract_articles(text)
        assert len(articles) == 0


class TestChunking:
    def test_short_text(self):
        text = "Kratki tekst."
        chunks = chunk_text(text)
        assert len(chunks) == 1

    def test_long_text(self):
        text = "Rečenica. " * 1000  # ~10000 znakova
        chunks = chunk_text(text, max_chars=500, overlap=100)
        assert len(chunks) > 1
        # Svaki chunk <= max_chars + malo
        for c in chunks:
            assert len(c) <= 600  # Malo tolerancije

    def test_overlap(self):
        text = "A" * 1000 + "B" * 1000
        chunks = chunk_text(text, max_chars=800, overlap=200)
        assert len(chunks) >= 2


class TestHash:
    def test_deterministic(self):
        h1 = compute_hash("test text")
        h2 = compute_hash("test text")
        assert h1 == h2

    def test_different(self):
        h1 = compute_hash("text a")
        h2 = compute_hash("text b")
        assert h1 != h2


class TestReadFile:
    def test_read_txt(self):
        tmpdir = tempfile.mkdtemp()
        filepath = Path(tmpdir) / "test.txt"
        filepath.write_text("Sadržaj zakona.", encoding="utf-8")
        content = read_file(filepath)
        assert "Sadržaj" in content

    def test_read_sample_laws(self):
        """Provjeri da sample zakoni mogu biti pročitani."""
        law_dir = Path("data/laws")
        if law_dir.exists():
            for f in law_dir.glob("*.txt"):
                content = read_file(f)
                assert len(content) > 0, f"Prazna datoteka: {f}"
