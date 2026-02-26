"""
Nyx Light — Law Loader za RAG bazu

Parsira zakone RH iz tekstualnih datoteka i razbija ih na chunksove
pogodne za vektorsku bazu. Podržava:
  - Zakon o PDV-u (NN 73/13 + izmjene)
  - Zakon o porezu na dobit (NN 177/04 + izmjene)
  - Zakon o porezu na dohodak (NN 115/16 + izmjene)
  - Zakon o računovodstvu (NN 78/15 + izmjene)
  - Pravilnici i mišljenja Porezne uprave

Format ulaznih datoteka:
  data/laws/{zakon_slug}.txt ili .md
  S metapodacima u header-u:
    ---
    zakon: Zakon o porezu na dodanu vrijednost
    nn: 73/13, 99/13, 148/13, ...
    datum_stupanja: 2013-07-01
    ---
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .qdrant_store import LawChunk

logger = logging.getLogger("nyx_light.rag.loader")

# Regex za prepoznavanje članaka
ARTICLE_RE = re.compile(
    r"^(?:Članak|Čl\.)\s+(\d+[a-z]?)\.?\s*$",
    re.MULTILINE | re.IGNORECASE,
)

# Regex za stavke unutar članka
PARAGRAPH_RE = re.compile(r"^\((\d+)\)\s+", re.MULTILINE)

# Regex za glave/odjeljke
HEADING_RE = re.compile(
    r"^(?:GLAVA|DIO|ODJELJAK|POGLAVLJE)\s+[IVX\d]+\.?\s*[-–—]?\s*(.+)$",
    re.MULTILINE | re.IGNORECASE,
)


@dataclass
class LawMetadata:
    """Metapodaci zakona iz header-a datoteke."""
    name: str = ""
    nn_references: List[str] = None  # type: ignore[assignment]
    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None
    slug: str = ""

    def __post_init__(self):
        if self.nn_references is None:
            self.nn_references = []


class LawLoader:
    """
    Učitavanje i parsiranje zakona RH za RAG ingestion.

    Tok rada:
      1. load_file(path) → parsira header + članci
      2. chunk() → razbija u LawChunk objekte
      3. Prosljeđuje u QdrantStore.ingest_chunks()
    """

    def __init__(self, laws_dir: str = "data/laws"):
        self.laws_dir = Path(laws_dir)
        self._loaded_laws: Dict[str, LawMetadata] = {}
        logger.info("LawLoader: laws_dir=%s", self.laws_dir)

    def load_all(self) -> List[LawChunk]:
        """Učitaj sve zakone iz laws direktorija."""
        all_chunks: List[LawChunk] = []

        if not self.laws_dir.exists():
            logger.warning("Laws direktorij ne postoji: %s", self.laws_dir)
            return all_chunks

        for law_file in sorted(self.laws_dir.glob("*.txt")):
            chunks = self.load_file(law_file)
            all_chunks.extend(chunks)
            logger.info("Učitan: %s → %d chunks", law_file.name, len(chunks))

        for law_file in sorted(self.laws_dir.glob("*.md")):
            chunks = self.load_file(law_file)
            all_chunks.extend(chunks)
            logger.info("Učitan: %s → %d chunks", law_file.name, len(chunks))

        logger.info("Ukupno učitano: %d chunks iz %d datoteka", len(all_chunks), len(self._loaded_laws))
        return all_chunks

    def load_file(self, path: Path) -> List[LawChunk]:
        """Učitaj jednu zakonsku datoteku i vrati chunksove."""
        text = path.read_text(encoding="utf-8")

        # Parsiraj header
        metadata = self._parse_header(text)
        metadata.slug = path.stem
        self._loaded_laws[metadata.slug] = metadata

        # Ukloni header
        content = self._strip_header(text)

        # Parsiraj u člancima
        articles = self._split_into_articles(content)

        # Konvertiraj u LawChunks
        chunks: List[LawChunk] = []
        current_heading = ""

        for article_num, article_text in articles:
            # Detektiraj heading (glava/odjeljak) iznad članka
            heading_match = HEADING_RE.search(article_text)
            if heading_match:
                current_heading = heading_match.group(1).strip()

            # Razbij veliki članak na stavke
            paragraphs = self._split_into_paragraphs(article_text)

            if len(paragraphs) <= 1 or len(article_text) < 1500:
                # Jedan chunk za cijeli članak
                chunks.append(
                    LawChunk(
                        text=article_text.strip(),
                        law_name=metadata.name,
                        article_number=article_num,
                        effective_from=metadata.effective_from,
                        effective_to=metadata.effective_to,
                        source_nn=", ".join(metadata.nn_references),
                        metadata={"heading": current_heading},
                    )
                )
            else:
                # Razbij na stavke s kontekstom
                for para_num, para_text in paragraphs:
                    # Dodaj kontekst (naziv članka) svakom chunku
                    contextual_text = (
                        f"[{metadata.name}, Članak {article_num}, "
                        f"Stavak {para_num}]\n{para_text.strip()}"
                    )
                    chunks.append(
                        LawChunk(
                            text=contextual_text,
                            law_name=metadata.name,
                            article_number=article_num,
                            paragraph=para_num,
                            effective_from=metadata.effective_from,
                            effective_to=metadata.effective_to,
                            source_nn=", ".join(metadata.nn_references),
                            metadata={"heading": current_heading},
                        )
                    )

        return chunks

    def _parse_header(self, text: str) -> LawMetadata:
        """Parsiraj YAML-like header iz zakonske datoteke."""
        metadata = LawMetadata()

        # Traži --- ... --- blok
        header_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
        if not header_match:
            return metadata

        header_text = header_match.group(1)
        for line in header_text.split("\n"):
            line = line.strip()
            if ":" in line:
                key, value = line.split(":", 1)
                key = key.strip().lower()
                value = value.strip()

                if key == "zakon":
                    metadata.name = value
                elif key == "nn":
                    metadata.nn_references = [ref.strip() for ref in value.split(",")]
                elif key == "datum_stupanja":
                    try:
                        metadata.effective_from = datetime.fromisoformat(value)
                    except ValueError:
                        pass
                elif key == "datum_prestanka":
                    try:
                        metadata.effective_to = datetime.fromisoformat(value)
                    except ValueError:
                        pass

        return metadata

    def _strip_header(self, text: str) -> str:
        """Ukloni header iz teksta."""
        return re.sub(r"^---\s*\n.*?\n---\s*\n", "", text, count=1, flags=re.DOTALL)

    def _split_into_articles(self, content: str) -> List[Tuple[str, str]]:
        """Razbij zakon na (article_number, article_text) parove."""
        matches = list(ARTICLE_RE.finditer(content))
        if not matches:
            # Nema strukturiranih članaka — vrati kao jedan chunk
            return [("0", content)]

        articles: List[Tuple[str, str]] = []

        # Tekst prije prvog članka (naslov, preambula)
        preamble = content[: matches[0].start()].strip()
        if preamble:
            articles.append(("preambula", preamble))

        # Članci
        for i, match in enumerate(matches):
            article_num = match.group(1)
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            article_text = content[start:end].strip()
            articles.append((article_num, article_text))

        return articles

    def _split_into_paragraphs(self, article_text: str) -> List[Tuple[str, str]]:
        """Razbij članak na stavke (1), (2), (3)..."""
        matches = list(PARAGRAPH_RE.finditer(article_text))
        if not matches:
            return []

        paragraphs: List[Tuple[str, str]] = []
        for i, match in enumerate(matches):
            para_num = match.group(1)
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(article_text)
            paragraphs.append((para_num, article_text[start:end]))

        return paragraphs

    def get_loaded_laws(self) -> Dict[str, LawMetadata]:
        return self._loaded_laws.copy()


def create_example_law_files(laws_dir: str = "data/laws") -> None:
    """Kreiraj primjere zakonskih datoteka za testiranje."""
    laws_path = Path(laws_dir)
    laws_path.mkdir(parents=True, exist_ok=True)

    # Primjer: Zakon o PDV-u (skraćeni)
    pdv_content = """---
zakon: Zakon o porezu na dodanu vrijednost
nn: 73/13, 99/13, 148/13, 153/13, 143/14, 115/16, 106/18, 121/19, 138/20, 39/22, 113/22, 33/23, 35/23, 72/24
datum_stupanja: 2013-07-01
---

ZAKON O POREZU NA DODANU VRIJEDNOST

DIO I. — OPĆE ODREDBE

Članak 1.
(1) Ovim se Zakonom uređuje sustav poreza na dodanu vrijednost (u daljnjem tekstu: PDV).
(2) PDV je prihod državnog proračuna Republike Hrvatske.

Članak 2.
Predmet oporezivanja PDV-om je:
1. isporuka dobara u tuzemstvu uz naknadu koju obavi porezni obveznik koji djeluje kao takav
2. stjecanje dobara unutar Europske unije u tuzemstvu uz naknadu
3. uvoz dobara.

DIO II. — POREZNI OBVEZNIK

Članak 6.
(1) Porezni obveznik u smislu ovoga Zakona je svaka osoba koja samostalno obavlja bilo koju gospodarsku djelatnost bez obzira na svrhu i rezultat obavljanja te djelatnosti.
(2) Gospodarskom djelatnošću smatra se svaka djelatnost proizvođača, trgovaca ili osoba koje obavljaju usluge, uključujući rudarske i poljoprivredne djelatnosti te djelatnosti slobodnih zanimanja.

DIO V. — POREZNA STOPA

Članak 38.
(1) PDV se obračunava i plaća po stopi od 25%.
(2) PDV se obračunava i plaća po sniženoj stopi od 13% na:
a) usluge smještaja ili smještaja s doručkom, polupansiona ili punog pansiona u hotelima
b) novine i časopise novinskog nakladnika
c) jestiva ulja i masti
(3) PDV se obračunava i plaća po sniženoj stopi od 5% na:
a) sve vrste kruha
b) sve vrste mlijeka
c) knjige
d) lijekove
e) medicinsku opremu, pomagala i druge sprave
"""

    pdv_path = laws_path / "zakon_pdv.txt"
    if not pdv_path.exists():
        pdv_path.write_text(pdv_content, encoding="utf-8")
        logger.info("Kreiran primjer: %s", pdv_path)

    # Primjer: Zakon o porezu na dobit (skraćeni)
    dobit_content = """---
zakon: Zakon o porezu na dobit
nn: 177/04, 90/05, 57/06, 146/08, 80/10, 22/12, 148/13, 143/14, 50/16, 115/16, 106/18, 121/19, 32/20, 138/20, 114/22, 113/22, 114/23
datum_stupanja: 2005-01-01
---

ZAKON O POREZU NA DOBIT

Članak 1.
Ovim se Zakonom uređuje sustav oporezivanja dobiti.

Članak 5.
(1) Porezna osnovica je dobit koja se utvrđuje prema računovodstvenim propisima kao razlika prihoda i rashoda prije obračuna poreza na dobit, uvećana i umanjena prema odredbama ovoga Zakona.

Članak 28.
(1) Porez na dobit plaća se na utvrđenu poreznu osnovicu po stopi od 18%.
(2) Iznimno od stavka 1. ovoga članka, porez na dobit plaća se po stopi od 10% ako su u poreznom razdoblju ostvareni prihodi do 1.000.000,00 eura.

Članak 7.
(1) Porezno nepriznati rashodi su:
1. 50% troškova reprezentacije
2. troškovi kazni za prekršaje i prijestupe
3. zatezne kamate između povezanih osoba
4. darovanja iznad propisanih iznosa
"""

    dobit_path = laws_path / "zakon_porez_dobit.txt"
    if not dobit_path.exists():
        dobit_path.write_text(dobit_content, encoding="utf-8")
        logger.info("Kreiran primjer: %s", dobit_path)

    # Primjer: Zakon o računovodstvu (skraćeni)
    rac_content = """---
zakon: Zakon o računovodstvu
nn: 78/15, 134/15, 120/16, 116/18, 42/20, 47/20, 114/22
datum_stupanja: 2016-01-01
---

ZAKON O RAČUNOVODSTVU

Članak 1.
Ovim se Zakonom uređuje računovodstvo poduzetnika, razvrstavanje poduzetnika i grupa poduzetnika, knjigovodstvene isprave i poslovne knjige, popis imovine i obveza, primjena standarda financijskog izvještavanja, godišnji financijski izvještaji i konsolidacija godišnjih financijskih izvještaja, izvještaj o plaćanjima javnom sektoru, revizija godišnjih financijskih izvještaja, sadržaj godišnjeg izvješća, javna objava godišnjih financijskih izvještaja, Registar godišnjih financijskih izvještaja te obavljanje nadzora.

Članak 5.
(1) Poduzetnici se razvrstavaju na mikro, male, srednje i velike poduzetnike ovisno o iznosima ukupne aktive, prihoda i prosječnom broju radnika tijekom poslovne godine.
(2) Mikro poduzetnici su oni koji ne prelaze granične pokazatelje u dva od sljedeća tri uvjeta:
- ukupna aktiva 350.000,00 eura
- prihod 700.000,00 eura
- prosječan broj radnika tijekom poslovne godine — 10 radnika.
"""

    rac_path = laws_path / "zakon_racunovodstvo.txt"
    if not rac_path.exists():
        rac_path.write_text(rac_content, encoding="utf-8")
        logger.info("Kreiran primjer: %s", rac_path)
