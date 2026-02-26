"""Tests za 4-Tier Memory System."""

from nyx_light.memory.system import MemorySystem


class TestMemorySystem:
    def setup_method(self):
        self.memory = MemorySystem()

    def test_record_correction(self):
        self.memory.record_correction(
            user_id="user1",
            client_id="client_ABC",
            original_konto="7800",
            corrected_konto="7200",
            document_type="ulazni_racun",
            supplier="Dobavljač XYZ",
        )
        # Should be stored in L2
        hint = self.memory.get_kontiranje_hint(
            client_id="client_ABC",
            supplier="Dobavljač XYZ",
        )
        assert hint is not None
        assert "7200" in hint["hint"]
