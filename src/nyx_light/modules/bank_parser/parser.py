"""
Modul A4 — Parser bankovnih izvoda za RH banke

Podržani formati:
- MT940 (SWIFT standard) — univerzalni
- Erste CSV (EB izvodi)
- Zaba CSV (ZabaNet izvodi)
- PBZ CSV (PBZ365 izvodi)
- OTP CSV
- RBA CSV (Raiffeisen)
- HPB CSV
- Generički CSV fallback

Automatsko prepoznavanje banke po IBAN prefixu.
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
    datum: str = ""
    datum_valute: str = ""
    opis: str = ""
    iznos: float = 0.0
    tip: str = ""              # uplata / isplata
    iban_platitelj: str = ""
    naziv_platitelj: str = ""
    iban_primatelj: str = ""
    naziv_primatelj: str = ""
    poziv_na_broj: str = ""    # model-poziv (HR00, HR01, HR67...)
    sifra_namjene: str = ""
    referenca: str = ""
    saldo_nakon: float = 0.0
    banka: str = ""
    raw_data: Dict = field(default_factory=dict)


class BankStatementParser:
    """Parser za bankovne izvode — podržava 6+ banaka."""

    # Croatian IBAN: HRcc BBBBBBB AAAAAAAAAA
    # cc = check digits (variable), BBBBBBB = bank code (positions 4-10)
    BANK_CODES = {
        "2402006": "Erste",
        "2340009": "Erste",  # Erste alt
        "2360000": "Zaba",
        "2484008": "PBZ",
        "2407000": "PBZ",    # PBZ alt
        "2500009": "RBA",
        "2386002": "OTP",
        "2390001": "HPB",
        "2503007": "Addiko",
        "2483009": "Agram",
    }

    # Legacy 4-char prefix fallback
    BANK_PREFIXES = {
        "HR02": "Erste", "HR25": "Erste",
        "HR17": "PBZ", "HR69": "PBZ",
        "HR23": "Zaba", "HR62": "Zaba",
        "HR15": "RBA",
        "HR36": "OTP",
        "HR72": "HPB",
        "HR56": "Addiko",
        "HR95": "Agram",
    }

    # ═══ Erste CSV format ═══
    # Kolone: Datum knjiženja;Datum valute;Opis;Iznos;Valuta;Tečaj;Saldo
    ERSTE_COLUMNS = {
        "datum": ["Datum knjiženja", "Datum knjizenja", "Datum"],
        "datum_valute": ["Datum valute"],
        "opis": ["Opis", "Opis plaćanja", "Opis placanja"],
        "iznos": ["Iznos", "Amount"],
        "saldo": ["Saldo", "Balance"],
        "iban": ["IBAN platitelja", "IBAN"],
        "naziv": ["Naziv platitelja", "Platitelj", "Primatelj"],
        "poziv": ["Poziv na broj", "Reference"],
    }

    # ═══ Zaba CSV format ═══
    # Kolone: Datum;Opis transakcije;Terećenje;Odobrenje;Saldo
    ZABA_COLUMNS = {
        "datum": ["Datum", "Datum transakcije"],
        "opis": ["Opis transakcije", "Opis"],
        "terecenje": ["Terećenje", "Terecenje", "Debit"],
        "odobrenje": ["Odobrenje", "Credit"],
        "saldo": ["Saldo", "Balance"],
        "partner": ["Platitelj/Primatelj", "Partner"],
        "poziv": ["Poziv na broj", "Poziv na br"],
    }

    # ═══ PBZ CSV format ═══
    # Kolone: Datum;Vrsta;Opis;Iznos;Valuta;Stanje
    PBZ_COLUMNS = {
        "datum": ["Datum", "Datum promjene"],
        "vrsta": ["Vrsta", "Vrsta transakcije"],
        "opis": ["Opis", "Opis promjene"],
        "iznos": ["Iznos", "Amount"],
        "stanje": ["Stanje", "Stanje računa", "Balance"],
        "partner_naziv": ["Naziv", "Platitelj/Primatelj"],
        "partner_iban": ["IBAN", "Račun platitelja"],
        "poziv": ["Poziv na broj primatelja", "Poziv na broj"],
    }

    def __init__(self):
        self._parsed_count = 0
        self._error_count = 0

    def parse(self, file_path: str, bank: str = "") -> List[Dict[str, Any]]:
        """Parsiraj bankovni izvod."""
        path = Path(file_path)
        if not path.exists():
            self._error_count += 1
            return []

        ext = path.suffix.lower()
        transactions = []

        if ext in (".sta", ".mt940", ".swi"):
            transactions = self._parse_mt940(path)
        elif ext == ".csv":
            # Auto-detect banka iz headera ili hint-a
            detected_bank = bank or self._detect_bank_from_csv(path)
            transactions = self._parse_csv(path, detected_bank)
        elif ext == ".xlsx":
            transactions = self._parse_xlsx(path, bank)
        else:
            raise ValueError(f"Nepodržani format: {ext}")

        self._parsed_count += len(transactions)
        return [self._to_dict(t) for t in transactions]

    def _parse_mt940(self, path: Path) -> List[BankTransaction]:
        """Parse MT940 (SWIFT) format."""
        transactions = []
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            # MT940 tag patterns
            tag_61 = re.findall(
                r':61:(\d{6})(\d{4})?([CD])(\d+[,.]?\d*)\n?:86:(.*?)(?=:6[012]:|:62[AFM]:|-})',
                content, re.DOTALL,
            )
            for match in tag_61:
                date_str, valuta, dc, amount_str, desc = match
                try:
                    datum = datetime.strptime(date_str, "%y%m%d").strftime("%Y-%m-%d")
                except ValueError:
                    datum = date_str
                amount = float(amount_str.replace(",", "."))
                if dc == "D":
                    amount = -amount

                # Extract partner from :86: field
                desc_clean = desc.strip().replace("\n", " ")
                iban_match = re.search(r"(HR\d{19})", desc_clean)
                poziv_match = re.search(r"HR\d{2}[-\s]?([\d-]+)", desc_clean)

                tx = BankTransaction(
                    datum=datum,
                    opis=desc_clean[:200],
                    iznos=amount,
                    tip="uplata" if dc == "C" else "isplata",
                    iban_platitelj=iban_match.group(1) if iban_match and dc == "C" else "",
                    iban_primatelj=iban_match.group(1) if iban_match and dc == "D" else "",
                    poziv_na_broj=poziv_match.group(0) if poziv_match else "",
                    banka="MT940",
                )
                transactions.append(tx)

        except Exception as e:
            logger.error("MT940 parse error: %s", e)
            self._error_count += 1
        return transactions

    def _detect_bank_from_csv(self, path: Path) -> str:
        """Auto-detect banku iz CSV headera."""
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                first_lines = f.read(500).lower()
            if "terećenje" in first_lines or "terecenje" in first_lines:
                return "zaba"
            if "vrsta transakcije" in first_lines or "stanje računa" in first_lines:
                return "pbz"
            if "datum knjiženja" in first_lines or "datum knjizenja" in first_lines:
                return "erste"
            if "raiffeisen" in first_lines:
                return "rba"
            if "otp" in first_lines:
                return "otp"
        except Exception:
            pass
        return ""

    def _parse_csv(self, path: Path, bank: str) -> List[BankTransaction]:
        """Parse CSV — delegira na bank-specific parser."""
        bank_lower = bank.lower() if bank else ""

        if bank_lower in ("erste", "eb"):
            return self._parse_erste_csv(path)
        elif bank_lower in ("zaba", "zagrebacka"):
            return self._parse_zaba_csv(path)
        elif bank_lower in ("pbz", "pbz365"):
            return self._parse_pbz_csv(path)
        elif bank_lower in ("otp",):
            return self._parse_otp_csv(path)
        elif bank_lower in ("rba", "raiffeisen"):
            return self._parse_rba_csv(path)
        else:
            return self._parse_generic_csv(path)

    def _find_col(self, row: Dict[str, str], candidates: List[str]) -> str:
        """Find column by candidate names (case-insensitive)."""
        for c in candidates:
            for key in row:
                if c.lower() in key.lower():
                    return row[key].strip()
        return ""

    def _parse_amount(self, val: str) -> float:
        """Parse iznos — podržava 1.234,56 i 1234.56 formate."""
        if not val:
            return 0.0
        val = val.strip().replace(" ", "")
        # HR format: 1.234,56 → remove dots, replace comma with dot
        if "," in val and "." in val:
            val = val.replace(".", "").replace(",", ".")
        elif "," in val:
            val = val.replace(",", ".")
        try:
            return float(val)
        except ValueError:
            return 0.0

    def _parse_erste_csv(self, path: Path) -> List[BankTransaction]:
        """Erste Bank CSV format."""
        txs = []
        try:
            with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
                # Erste uses ; delimiter
                reader = csv.DictReader(f, delimiter=";")
                for row in reader:
                    datum = self._find_col(row, self.ERSTE_COLUMNS["datum"])
                    opis = self._find_col(row, self.ERSTE_COLUMNS["opis"])
                    iznos_str = self._find_col(row, self.ERSTE_COLUMNS["iznos"])
                    saldo_str = self._find_col(row, self.ERSTE_COLUMNS["saldo"])
                    iban = self._find_col(row, self.ERSTE_COLUMNS["iban"])
                    naziv = self._find_col(row, self.ERSTE_COLUMNS["naziv"])
                    poziv = self._find_col(row, self.ERSTE_COLUMNS["poziv"])

                    iznos = self._parse_amount(iznos_str)
                    if iznos == 0:
                        continue

                    txs.append(BankTransaction(
                        datum=datum, opis=opis[:200], iznos=iznos,
                        tip="uplata" if iznos > 0 else "isplata",
                        iban_platitelj=iban if iznos > 0 else "",
                        naziv_platitelj=naziv if iznos > 0 else "",
                        iban_primatelj=iban if iznos < 0 else "",
                        naziv_primatelj=naziv if iznos < 0 else "",
                        poziv_na_broj=poziv,
                        saldo_nakon=self._parse_amount(saldo_str),
                        banka="Erste",
                    ))
        except Exception as e:
            logger.error("Erste CSV: %s", e)
            self._error_count += 1
        return txs

    def _parse_zaba_csv(self, path: Path) -> List[BankTransaction]:
        """Zagrebačka banka CSV — terećenje/odobrenje u odvojenim stupcima."""
        txs = []
        try:
            with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
                reader = csv.DictReader(f, delimiter=";")
                for row in reader:
                    datum = self._find_col(row, self.ZABA_COLUMNS["datum"])
                    opis = self._find_col(row, self.ZABA_COLUMNS["opis"])
                    terecenje = self._parse_amount(self._find_col(row, self.ZABA_COLUMNS["terecenje"]))
                    odobrenje = self._parse_amount(self._find_col(row, self.ZABA_COLUMNS["odobrenje"]))
                    saldo_str = self._find_col(row, self.ZABA_COLUMNS["saldo"])
                    partner = self._find_col(row, self.ZABA_COLUMNS["partner"])
                    poziv = self._find_col(row, self.ZABA_COLUMNS["poziv"])

                    if terecenje == 0 and odobrenje == 0:
                        continue

                    if odobrenje > 0:
                        iznos = odobrenje
                        tip = "uplata"
                    else:
                        iznos = -terecenje if terecenje > 0 else terecenje
                        tip = "isplata"

                    txs.append(BankTransaction(
                        datum=datum, opis=opis[:200], iznos=iznos if tip == "uplata" else -abs(iznos),
                        tip=tip,
                        naziv_platitelj=partner if tip == "uplata" else "",
                        naziv_primatelj=partner if tip == "isplata" else "",
                        poziv_na_broj=poziv,
                        saldo_nakon=self._parse_amount(saldo_str),
                        banka="Zaba",
                    ))
        except Exception as e:
            logger.error("Zaba CSV: %s", e)
            self._error_count += 1
        return txs

    def _parse_pbz_csv(self, path: Path) -> List[BankTransaction]:
        """PBZ CSV format."""
        txs = []
        try:
            with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
                reader = csv.DictReader(f, delimiter=";")
                for row in reader:
                    datum = self._find_col(row, self.PBZ_COLUMNS["datum"])
                    opis = self._find_col(row, self.PBZ_COLUMNS["opis"])
                    iznos = self._parse_amount(self._find_col(row, self.PBZ_COLUMNS["iznos"]))
                    stanje = self._parse_amount(self._find_col(row, self.PBZ_COLUMNS["stanje"]))
                    partner = self._find_col(row, self.PBZ_COLUMNS["partner_naziv"])
                    partner_iban = self._find_col(row, self.PBZ_COLUMNS["partner_iban"])
                    poziv = self._find_col(row, self.PBZ_COLUMNS["poziv"])

                    if iznos == 0:
                        continue

                    txs.append(BankTransaction(
                        datum=datum, opis=opis[:200], iznos=iznos,
                        tip="uplata" if iznos > 0 else "isplata",
                        iban_platitelj=partner_iban if iznos > 0 else "",
                        naziv_platitelj=partner if iznos > 0 else "",
                        iban_primatelj=partner_iban if iznos < 0 else "",
                        naziv_primatelj=partner if iznos < 0 else "",
                        poziv_na_broj=poziv,
                        saldo_nakon=stanje,
                        banka="PBZ",
                    ))
        except Exception as e:
            logger.error("PBZ CSV: %s", e)
            self._error_count += 1
        return txs

    def _parse_otp_csv(self, path: Path) -> List[BankTransaction]:
        """OTP CSV — sličan Erste formatu."""
        return self._parse_erste_csv(path)  # OTP koristi sličan format

    def _parse_rba_csv(self, path: Path) -> List[BankTransaction]:
        """Raiffeisen CSV."""
        return self._parse_erste_csv(path)  # RBA koristi sličan format

    def _parse_generic_csv(self, path: Path) -> List[BankTransaction]:
        """Generički CSV fallback — pokušava matchirati kolone."""
        txs = []
        try:
            # Detect delimiter
            with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
                sample = f.read(500)
            delimiter = ";" if sample.count(";") > sample.count(",") else ","

            with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
                reader = csv.DictReader(f, delimiter=delimiter)
                for row in reader:
                    # Try to find amount column
                    iznos = 0.0
                    for key in row:
                        kl = key.lower()
                        if any(w in kl for w in ["iznos", "amount", "suma", "ukupno"]):
                            iznos = self._parse_amount(row[key])
                            break
                    if iznos == 0:
                        # Try terecenje/odobrenje
                        for key in row:
                            if "terec" in key.lower() or "debit" in key.lower():
                                iznos = -abs(self._parse_amount(row[key]))
                            elif "odobre" in key.lower() or "credit" in key.lower():
                                iznos = abs(self._parse_amount(row[key]))

                    if iznos == 0:
                        continue

                    # Find date
                    datum = ""
                    for key in row:
                        if "datum" in key.lower() or "date" in key.lower():
                            datum = row[key].strip()
                            break

                    # Find description
                    opis = ""
                    for key in row:
                        if any(w in key.lower() for w in ["opis", "desc", "namjena"]):
                            opis = row[key].strip()
                            break

                    # Find IBAN
                    iban = ""
                    for key in row:
                        if "iban" in key.lower() or "racun" in key.lower():
                            val = row[key].strip()
                            if re.match(r"HR\d{19}", val):
                                iban = val
                            break

                    txs.append(BankTransaction(
                        datum=datum, opis=opis[:200], iznos=iznos,
                        tip="uplata" if iznos > 0 else "isplata",
                        iban_platitelj=iban if iznos > 0 else "",
                        iban_primatelj=iban if iznos < 0 else "",
                        banka="generic",
                    ))
        except Exception as e:
            logger.error("Generic CSV: %s", e)
            self._error_count += 1
        return txs

    def _parse_xlsx(self, path: Path, bank: str) -> List[BankTransaction]:
        """Parse Excel izvod."""
        try:
            import openpyxl
            wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
            ws = wb.active
            rows = list(ws.iter_rows(values_only=True))
            if len(rows) < 2:
                return []
            headers = [str(h or "").strip() for h in rows[0]]
            txs = []
            for row in rows[1:]:
                row_dict = {headers[i]: str(row[i] or "") for i in range(min(len(headers), len(row)))}
                # Reuse CSV logic
                iznos = 0.0
                for k, v in row_dict.items():
                    if "iznos" in k.lower() or "amount" in k.lower():
                        iznos = self._parse_amount(v)
                        break
                if iznos == 0:
                    continue
                datum = ""
                for k, v in row_dict.items():
                    if "datum" in k.lower():
                        datum = v
                        break
                opis = ""
                for k, v in row_dict.items():
                    if "opis" in k.lower():
                        opis = v
                        break
                txs.append(BankTransaction(
                    datum=datum, opis=opis[:200], iznos=iznos,
                    tip="uplata" if iznos > 0 else "isplata", banka=bank or "xlsx",
                ))
            return txs
        except Exception as e:
            logger.error("XLSX parse: %s", e)
            self._error_count += 1
            return []

    def detect_bank(self, iban: str) -> str:
        """Detect bank from IBAN. Uses bank code (positions 4-11) first."""
        iban = iban.strip().replace(" ", "")
        # Try bank code (positions 4-11)
        if len(iban) >= 11:
            bank_code = iban[4:11]
            if bank_code in self.BANK_CODES:
                return self.BANK_CODES[bank_code]
        # Fallback to prefix
        for prefix, bank in self.BANK_PREFIXES.items():
            if iban.startswith(prefix):
                return bank
        return "Nepoznata"

    def _to_dict(self, tx: BankTransaction) -> Dict[str, Any]:
        return {
            "datum": tx.datum, "datum_valute": tx.datum_valute,
            "opis": tx.opis, "iznos": tx.iznos, "tip": tx.tip,
            "iban_platitelj": tx.iban_platitelj, "naziv_platitelj": tx.naziv_platitelj,
            "iban_primatelj": tx.iban_primatelj, "naziv_primatelj": tx.naziv_primatelj,
            "poziv_na_broj": tx.poziv_na_broj, "sifra_namjene": tx.sifra_namjene,
            "saldo_nakon": tx.saldo_nakon, "banka": tx.banka,
        }

    def get_stats(self):
        return {"parsed": self._parsed_count, "errors": self._error_count,
                "supported_banks": list(set(self.BANK_PREFIXES.values()))}
