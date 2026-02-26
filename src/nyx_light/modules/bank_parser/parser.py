"""
Modul A4 — Parser bankovnih izvoda

Podržava:
- MT940 (SWIFT standard) — Erste, Zaba, PBZ
- CSV formati — specifični za svaku banku
- Automatsko prepoznavanje platitelja (IBAN, poziv na broj)
- Sparivanje s otvorenim stavkama
- Generiranje datoteke za uvoz u CPP/Synesis
"""

import csv
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nyx_light.modules.bank_parser")


@dataclass
class BankTransaction:
    """Pojedinačna transakcija s bankovnog izvoda."""
    datum: datetime
    iban_platitelj: str = ""
    naziv_platitelj: str = ""
    iban_primatelj: str = ""
    naziv_primatelj: str = ""
    iznos: float = 0.0
    valuta: str = "EUR"
    poziv_na_broj: str = ""
    opis: str = ""
    tip: str = ""  # "uplata" | "isplata"
    matched_client: Optional[str] = None
    matched_invoice: Optional[str] = None
    confidence: float = 0.0


class BankStatementParser:
    """Parser za bankovne izvode (MT940 + CSV)."""

    # IBAN prefiksi za hrvatske banke
    BANK_PREFIXES = {
        "HR17": "PBZ",
        "HR23": "Erste",
        "HR25": "Zaba",
        "HR36": "OTP",
        "HR69": "Addiko",
    }

    def __init__(self):
        self._parsed_count = 0
        self._matched_count = 0
        logger.info("BankStatementParser inicijaliziran")

    def parse(self, file_path: str, bank: str = "") -> List[Dict[str, Any]]:
        """Parsiraj bankovni izvod."""
        path = Path(file_path)
        
        if not path.exists():
            logger.error("Datoteka ne postoji: %s", file_path)
            return []

        ext = path.suffix.lower()
        
        if ext == ".sta" or ext == ".mt940":
            transactions = self._parse_mt940(path)
        elif ext == ".csv":
            transactions = self._parse_csv(path, bank)
        else:
            logger.warning("Nepodržani format: %s", ext)
            return []

        self._parsed_count += len(transactions)
        logger.info("Parsirano %d transakcija iz %s", len(transactions), path.name)

        return [self._transaction_to_dict(t) for t in transactions]

    def _parse_mt940(self, path: Path) -> List[BankTransaction]:
        """Parse MT940 (SWIFT) format."""
        transactions = []
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            
            # MT940 tag patterns
            # :61: — Statement line (date, amount)
            # :86: — Information to account owner
            stmt_pattern = re.compile(
                r":61:(\d{6})(\d{4})?(C|D|RC|RD)(\d+,\d+)"
            )
            info_pattern = re.compile(r":86:(.*?)(?=:\d{2}:|$)", re.DOTALL)

            for match in stmt_pattern.finditer(content):
                date_str = match.group(1)
                dc = match.group(3)  # C=credit, D=debit
                amount_str = match.group(4).replace(",", ".")
                
                try:
                    datum = datetime.strptime(date_str, "%y%m%d")
                    iznos = float(amount_str)
                    if dc in ("D", "RD"):
                        iznos = -iznos
                except (ValueError, TypeError):
                    continue

                tx = BankTransaction(
                    datum=datum,
                    iznos=iznos,
                    tip="uplata" if iznos > 0 else "isplata",
                )
                transactions.append(tx)

        except Exception as e:
            logger.error("MT940 parse error: %s", e)

        return transactions

    def _parse_csv(self, path: Path, bank: str = "") -> List[BankTransaction]:
        """Parse CSV bankovni izvod (bank-specific formats)."""
        transactions = []
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                # Detect delimiter
                sample = f.read(4096)
                f.seek(0)
                delimiter = ";" if ";" in sample else ","
                
                reader = csv.DictReader(f, delimiter=delimiter)
                
                for row in reader:
                    tx = self._parse_csv_row(row, bank)
                    if tx:
                        transactions.append(tx)

        except Exception as e:
            logger.error("CSV parse error: %s", e)

        return transactions

    def _parse_csv_row(self, row: Dict[str, str], bank: str) -> Optional[BankTransaction]:
        """Parse jedan red CSV-a ovisno o banci."""
        try:
            # Generički mapping — prilagoditi za svaku banku
            datum_str = (
                row.get("Datum", "") or row.get("Datum knjiženja", "") or 
                row.get("Date", "") or row.get("Datum valute", "")
            )
            iznos_str = (
                row.get("Iznos", "") or row.get("Amount", "") or
                row.get("Duguje", "") or row.get("Potražuje", "")
            )
            opis = (
                row.get("Opis", "") or row.get("Opis plaćanja", "") or
                row.get("Description", "")
            )
            iban = (
                row.get("IBAN", "") or row.get("IBAN platitelja", "") or
                row.get("Račun platitelja", "")
            )
            poziv = (
                row.get("Poziv na broj", "") or row.get("Referenca", "") or
                row.get("Reference", "")
            )

            # Parse datum
            datum = None
            for fmt in ["%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y."]:
                try:
                    datum = datetime.strptime(datum_str.strip().rstrip("."), fmt.rstrip("."))
                    break
                except ValueError:
                    continue
            
            if not datum:
                return None

            # Parse iznos
            iznos_str = iznos_str.replace(".", "").replace(",", ".").strip()
            try:
                iznos = float(iznos_str) if iznos_str else 0.0
            except ValueError:
                iznos = 0.0

            return BankTransaction(
                datum=datum,
                iznos=iznos,
                opis=opis.strip(),
                iban_platitelj=iban.strip(),
                poziv_na_broj=poziv.strip(),
                tip="uplata" if iznos > 0 else "isplata",
            )
        except Exception:
            return None

    def _transaction_to_dict(self, tx: BankTransaction) -> Dict[str, Any]:
        return {
            "datum": tx.datum.isoformat(),
            "iznos": tx.iznos,
            "valuta": tx.valuta,
            "tip": tx.tip,
            "iban_platitelj": tx.iban_platitelj,
            "naziv_platitelj": tx.naziv_platitelj,
            "poziv_na_broj": tx.poziv_na_broj,
            "opis": tx.opis,
            "matched_client": tx.matched_client,
            "matched_invoice": tx.matched_invoice,
            "confidence": tx.confidence,
        }

    def detect_bank(self, iban: str) -> str:
        """Detektiraj banku iz IBAN-a."""
        for prefix, bank in self.BANK_PREFIXES.items():
            if iban.startswith(prefix):
                return bank
        return "Nepoznata"
