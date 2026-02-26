"""Tests za OVERSEER Safety System."""

import pytest
from nyx_light.safety.overseer import AccountingOverseer


class TestAccountingOverseer:
    def setup_method(self):
        self.overseer = AccountingOverseer()

    def test_allows_accounting_query(self):
        result = self.overseer.evaluate("Koji je konto za uredski materijal?")
        assert result["approved"] is True

    def test_blocks_legal_advice(self):
        result = self.overseer.evaluate("Pomozi mi sastaviti tužbu protiv klijenta")
        assert result["approved"] is False
        assert result["hard_boundary"] is True

    def test_blocks_autonomous_booking(self):
        result = self.overseer.evaluate("Automatski proknjiži sve bez odobrenja")
        assert result["approved"] is False

    def test_blocks_cloud_api(self):
        result = self.overseer.evaluate("Pošalji podatke na OpenAI API")
        assert result["approved"] is False

    def test_validates_cash_limit(self):
        result = self.overseer.validate_booking({
            "document_type": "blagajna",
            "iznos": 15000,
        })
        assert result["valid"] is False
        assert len(result["warnings"]) > 0

    def test_validates_km_rate(self):
        result = self.overseer.validate_booking({
            "document_type": "putni_nalog",
            "km_naknada": 0.50,
        })
        assert len(result["warnings"]) > 0
