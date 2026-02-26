"""Tests za Modul A4 — Bank Statement Parser."""

import pytest
from nyx_light.modules.bank_parser.parser import BankStatementParser, BankTransaction


class TestBankStatementParser:
    def setup_method(self):
        self.parser = BankStatementParser()

    def test_detect_bank_pbz(self):
        assert self.parser.detect_bank("HR1723600001101234567") == "PBZ"

    def test_detect_bank_erste(self):
        assert self.parser.detect_bank("HR2324020061100123456") == "Erste"

    def test_detect_bank_zaba(self):
        assert self.parser.detect_bank("HR2523600001101234567") == "Zaba"

    def test_detect_unknown_bank(self):
        assert self.parser.detect_bank("DE89370400440532013000") == "Nepoznata"

    def test_parse_nonexistent_file(self):
        result = self.parser.parse("/nonexistent/file.csv")
        assert result == []
