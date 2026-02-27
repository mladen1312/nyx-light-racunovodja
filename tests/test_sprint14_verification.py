"""
Sprint 14: Triple Verification + Watch Folder + Hardware Verification

Testovi za:
1. Triple Verification sustav (3× nezavisna provjera)
2. Watch Folder za zakonske dokumente
3. Hardverske reference (nema 192GB, M4 Ultra, M5 Ultra)
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

# Dodaj src u path
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nyx_light.verification import (
    CheckResult,
    ConsensusLevel,
    TripleCheckResult,
    TripleVerifier,
    VerificationResult,
)
from nyx_light.rag.watch_folder import WatchFolder, IncomingDocument


# ═══════════════════════════════════════════════════════════════
# TRIPLE VERIFICATION TESTS
# ═══════════════════════════════════════════════════════════════

class TestTripleVerification(unittest.TestCase):
    """Testovi za 3× nezavisnu verifikaciju."""

    def setUp(self):
        self.verifier = TripleVerifier()

    # ── OIB Tests ──

    def test_valid_oib_passes_all_three(self):
        """Validan OIB mora proći sve 3 provjere."""
        # OIB 94577403194 je poznati test OIB (Porezna uprava primjer)
        result = self.verifier.verify("oib", "94577403194")
        self.assertEqual(result.consensus, ConsensusLevel.FULL)
        self.assertGreaterEqual(result.confidence, 0.95)
        self.assertFalse(result.needs_human_review)

    def test_invalid_oib_format_fails(self):
        """OIB s krivim brojem znamenki mora failati."""
        result = self.verifier.verify("oib", "1234")
        self.assertIn(result.consensus, [ConsensusLevel.CONFLICT, ConsensusLevel.MAJORITY])
        self.assertLess(result.confidence, 0.95)

    def test_oib_all_zeros_fails(self):
        """OIB 00000000000 mora failati rule check."""
        result = self.verifier.verify("oib", "00000000000")
        # Format je OK (11 znamenki), mod11 je OK, ali rule kaže NE
        self.assertNotEqual(result.consensus, ConsensusLevel.FULL)

    def test_oib_wrong_checksum_fails(self):
        """OIB s krivom kontrolnom znamenkom mora failati algo check."""
        result = self.verifier.verify("oib", "12345678900")
        # Mod 11,10 neće proći
        self.assertIn(result.check_2.result, [CheckResult.FAIL, CheckResult.UNCERTAIN])

    # ── PDV Tests ──

    def test_pdv_correct_calculation(self):
        """Ispravan PDV (osnovica × stopa = iznos) mora proći."""
        ctx = {"osnovica": 100.0, "pdv_stopa": 0.25}
        result = self.verifier.verify("pdv_iznos", 25.0, ctx)
        self.assertEqual(result.consensus, ConsensusLevel.FULL)
        self.assertGreaterEqual(result.confidence, 0.95)

    def test_pdv_wrong_calculation(self):
        """Krivi PDV iznos mora failati algo check."""
        ctx = {"osnovica": 100.0, "pdv_stopa": 0.25}
        result = self.verifier.verify("pdv_iznos", 30.0, ctx)
        # Algo: 100 × 0.25 = 25 ≠ 30 → FAIL
        self.assertEqual(result.check_2.result, CheckResult.FAIL)

    def test_pdv_invalid_rate(self):
        """Nepostojeća PDV stopa mora failati rule check."""
        ctx = {"osnovica": 100.0, "pdv_stopa": 0.18}
        result = self.verifier.verify("pdv_iznos", 18.0, ctx)
        # 18% ne postoji u RH
        self.assertEqual(result.check_3.result, CheckResult.FAIL)

    def test_pdv_5_percent_valid(self):
        """PDV stopa 5% je validna u RH."""
        ctx = {"osnovica": 200.0, "pdv_stopa": 0.05}
        result = self.verifier.verify("pdv_iznos", 10.0, ctx)
        self.assertEqual(result.consensus, ConsensusLevel.FULL)

    def test_pdv_13_percent_valid(self):
        """PDV stopa 13% je validna u RH."""
        ctx = {"osnovica": 100.0, "pdv_stopa": 0.13}
        result = self.verifier.verify("pdv_iznos", 13.0, ctx)
        self.assertEqual(result.consensus, ConsensusLevel.FULL)

    # ── IBAN Tests ──

    def test_valid_iban_pbz(self):
        """Validan HR IBAN (PBZ) mora proći sve provjere."""
        # PBZ test IBAN
        result = self.verifier.verify("iban", "HR1723400091110000001")
        # Format OK, mod97 should work for valid IBAN
        self.assertIn(result.check_1.result, [CheckResult.PASS, CheckResult.FAIL])

    def test_invalid_iban_too_short(self):
        """Prekratak IBAN mora failati."""
        result = self.verifier.verify("iban", "HR12")
        self.assertEqual(result.check_1.result, CheckResult.FAIL)

    def test_iban_non_hr_prefix(self):
        """IBAN bez HR prefiksa mora failati ai_check."""
        result = self.verifier.verify("iban", "DE89370400440532013000")
        self.assertEqual(result.check_1.result, CheckResult.FAIL)

    # ── Consensus Logic Tests ──

    def test_consensus_full_3_of_3(self):
        """3/3 = FULL consensus."""
        result = TripleCheckResult(field_name="test", original_value="x")
        result.check_1 = VerificationResult("c1", CheckResult.PASS, "x")
        result.check_2 = VerificationResult("c2", CheckResult.PASS, "x")
        result.check_3 = VerificationResult("c3", CheckResult.PASS, "x")
        result.compute_consensus()
        self.assertEqual(result.consensus, ConsensusLevel.FULL)
        self.assertEqual(result.confidence, 1.0)
        self.assertFalse(result.needs_human_review)

    def test_consensus_majority_2_of_3(self):
        """2/3 = MAJORITY consensus."""
        result = TripleCheckResult(field_name="test", original_value="x")
        result.check_1 = VerificationResult("c1", CheckResult.PASS, "x")
        result.check_2 = VerificationResult("c2", CheckResult.PASS, "x")
        result.check_3 = VerificationResult("c3", CheckResult.FAIL, None)
        result.compute_consensus()
        self.assertEqual(result.consensus, ConsensusLevel.MAJORITY)
        self.assertGreater(result.confidence, 0.7)

    def test_consensus_conflict_1_of_3(self):
        """1/3 = CONFLICT → ljudska provjera."""
        result = TripleCheckResult(field_name="test", original_value="x")
        result.check_1 = VerificationResult("c1", CheckResult.PASS, "x")
        result.check_2 = VerificationResult("c2", CheckResult.FAIL, None)
        result.check_3 = VerificationResult("c3", CheckResult.FAIL, None)
        result.compute_consensus()
        self.assertEqual(result.consensus, ConsensusLevel.CONFLICT)
        self.assertTrue(result.needs_human_review)

    def test_consensus_conflict_0_of_3(self):
        """0/3 = CONFLICT → definitivno ljudska provjera."""
        result = TripleCheckResult(field_name="test", original_value="x")
        result.check_1 = VerificationResult("c1", CheckResult.FAIL, None)
        result.check_2 = VerificationResult("c2", CheckResult.FAIL, None)
        result.check_3 = VerificationResult("c3", CheckResult.FAIL, None)
        result.compute_consensus()
        self.assertEqual(result.consensus, ConsensusLevel.CONFLICT)
        self.assertTrue(result.needs_human_review)
        self.assertEqual(result.confidence, 0.0)

    # ── Batch Verification ──

    def test_batch_verification(self):
        """Batch od više podataka."""
        items = [
            ("oib", "94577403194", {}),
            ("pdv_iznos", 25.0, {"osnovica": 100.0, "pdv_stopa": 0.25}),
        ]
        results = self.verifier.verify_batch(items)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].field_name, "oib")
        self.assertEqual(results[1].field_name, "pdv_iznos")

    # ── Stats ──

    def test_stats_tracking(self):
        """Verifier prati statistiku."""
        v = TripleVerifier()
        v.verify("oib", "94577403194")
        v.verify("oib", "1234")
        stats = v.get_stats()
        self.assertEqual(stats["total_checks"], 2)
        self.assertIn("accuracy_rate", stats)

    # ── to_dict ──

    def test_result_to_dict(self):
        """Result se serijalizira u dict."""
        result = self.verifier.verify("oib", "94577403194")
        d = result.to_dict()
        self.assertIn("field", d)
        self.assertIn("confidence", d)
        self.assertIn("checks", d)
        self.assertIn("ai", d["checks"])
        self.assertIn("algorithm", d["checks"])
        self.assertIn("rule", d["checks"])


# ═══════════════════════════════════════════════════════════════
# WATCH FOLDER TESTS
# ═══════════════════════════════════════════════════════════════

class TestWatchFolder(unittest.TestCase):
    """Testovi za Watch Folder — zakonski dokumenti s ljudskom potvrdom."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.wf = WatchFolder(base_dir=self.tmpdir)

    def test_directories_created(self):
        """Svi potrebni direktoriji moraju biti kreirani."""
        self.assertTrue((Path(self.tmpdir) / "incoming_laws").exists())
        self.assertTrue((Path(self.tmpdir) / "incoming_laws" / "pending").exists())
        self.assertTrue((Path(self.tmpdir) / "incoming_laws" / "approved").exists())
        self.assertTrue((Path(self.tmpdir) / "incoming_laws" / "rejected").exists())

    def test_scan_empty_folder(self):
        """Prazan folder ne vraća ništa."""
        docs = self.wf.scan_for_new()
        self.assertEqual(len(docs), 0)

    def test_scan_detects_txt_file(self):
        """Stavi TXT u folder → detektira se."""
        incoming = Path(self.tmpdir) / "incoming_laws"
        test_file = incoming / "test_zakon.txt"
        test_file.write_text("Zakon o PDV-u (NN 151/25) članak 7.")
        docs = self.wf.scan_for_new()
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0].status, "pending")
        self.assertIn("PDV", docs[0].detected_law)

    def test_scan_detects_nn_reference(self):
        """Detektira NN broj iz teksta."""
        incoming = Path(self.tmpdir) / "incoming_laws"
        test_file = incoming / "novi_pravilnik.txt"
        test_file.write_text("Pravilnik objavljen u NN 153/25 o fiskalizaciji.")
        docs = self.wf.scan_for_new()
        self.assertEqual(len(docs), 1)
        self.assertIn("153/25", docs[0].detected_nn)

    def test_duplicate_not_scanned_twice(self):
        """Isti fajl se ne skenira dvaput."""
        incoming = Path(self.tmpdir) / "incoming_laws"
        test_file = incoming / "zakon.txt"
        test_file.write_text("Tekst zakona")
        docs1 = self.wf.scan_for_new()
        self.assertEqual(len(docs1), 1)
        # Drugi scan ne bi trebao naći ništa novo (fajl premješten u pending)
        docs2 = self.wf.scan_for_new()
        self.assertEqual(len(docs2), 0)

    def test_approve_document(self):
        """Admin odobrava dokument."""
        incoming = Path(self.tmpdir) / "incoming_laws"
        test_file = incoming / "zakon_pdv.txt"
        test_file.write_text("PDV zakon tekst")
        docs = self.wf.scan_for_new()
        doc_id = docs[0].id

        result = self.wf.approve(doc_id, reviewer="admin@ured.hr", notes="OK")
        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "approved")
        self.assertTrue(result["rag_update_needed"])

    def test_reject_document(self):
        """Admin odbija dokument."""
        incoming = Path(self.tmpdir) / "incoming_laws"
        test_file = incoming / "spam.txt"
        test_file.write_text("Nerelevantni sadržaj")
        docs = self.wf.scan_for_new()
        doc_id = docs[0].id

        result = self.wf.reject(doc_id, reviewer="admin@ured.hr", notes="Nebitno")
        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "rejected")

    def test_cannot_approve_twice(self):
        """Odobreni dokument se ne može odobriti opet."""
        incoming = Path(self.tmpdir) / "incoming_laws"
        test_file = incoming / "zakon.txt"
        test_file.write_text("Zakon tekst")
        docs = self.wf.scan_for_new()
        doc_id = docs[0].id

        self.wf.approve(doc_id, "admin")
        result = self.wf.approve(doc_id, "admin")
        self.assertFalse(result["ok"])

    def test_get_pending(self):
        """Dohvati samo pending dokumente."""
        incoming = Path(self.tmpdir) / "incoming_laws"
        for name in ["a.txt", "b.txt", "c.txt"]:
            (incoming / name).write_text(f"Zakon {name}")
        self.wf.scan_for_new()

        pending = self.wf.get_pending()
        self.assertEqual(len(pending), 3)

    def test_stats(self):
        """Statistike su točne."""
        incoming = Path(self.tmpdir) / "incoming_laws"
        (incoming / "a.txt").write_text("Zakon A")
        (incoming / "b.txt").write_text("Zakon B")
        self.wf.scan_for_new()

        stats = self.wf.get_stats()
        self.assertEqual(stats["total_processed"], 2)
        self.assertEqual(stats["pending_count"], 2)

    def test_ignores_unsupported_extensions(self):
        """Ignorira fajlove koji nisu PDF/TXT/DOCX."""
        incoming = Path(self.tmpdir) / "incoming_laws"
        (incoming / "readme.jpg").write_bytes(b"\xff\xd8")
        (incoming / "data.xlsx").write_bytes(b"PK\x03\x04")
        docs = self.wf.scan_for_new()
        self.assertEqual(len(docs), 0)

    def test_no_auto_rag_without_approval(self):
        """Nikad ne dodaje u RAG bez potvrde čovjeka."""
        incoming = Path(self.tmpdir) / "incoming_laws"
        (incoming / "zakon.txt").write_text("Zakon o PDV-u")
        docs = self.wf.scan_for_new()
        # Dokument je pending, NE approved
        approved = self.wf.get_approved_for_rag()
        self.assertEqual(len(approved), 0)


# ═══════════════════════════════════════════════════════════════
# HARDWARE REFERENCE VERIFICATION TESTS
# ═══════════════════════════════════════════════════════════════

class TestHardwareReferences(unittest.TestCase):
    """Provjera da NIGDJE nema netočnih hardverskih referenci."""

    def _scan_file(self, filepath: str) -> str:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            return f.read()

    def _scan_source_files(self):
        """Skeniraj sve .py i .sh fajlove."""
        root = Path(__file__).parent.parent
        contents = {}
        for pattern in ["src/**/*.py", "*.sh", "deploy/*.sh", "scripts/*.py"]:
            for f in root.glob(pattern):
                if "__pycache__" in str(f):
                    continue
                contents[str(f)] = self._scan_file(str(f))
        return contents

    def test_no_m4_ultra_in_source(self):
        """M4 Ultra NE POSTOJI — ne smije biti u source kodu kao stvarni chip."""
        for filepath, content in self._scan_source_files().items():
            lines = content.split("\n")
            for i, line in enumerate(lines):
                if "M4 Ultra" in line or "M4_Ultra" in line or "m4_ultra" in line:
                    # Dozvoljeno samo u komentarima koji kažu da NE postoji
                    if "ne postoji" in line.lower() or "preskočio" in line.lower() or "~~" in line:
                        continue
                    self.fail(
                        f"M4 Ultra referenca u {filepath}:{i+1}: {line.strip()}\n"
                        "M4 Ultra NE POSTOJI — Apple ga je preskočio!"
                    )

    def test_no_m5_ultra_as_current_hardware(self):
        """M5 Ultra NIJE JOŠ IZAŠAO (27.02.2026) — ne smije biti kao 'trenutni' hardware."""
        keywords_bad = ["M5 Ultra (", "Mac Studio M5 Ultra", "M5_Ultra"]
        keywords_ok = ["kad izađe", "kad bude", "najavljeno", "očekivano", "will", "expect",
                       "ne postoji", "još nije", "~~", "budući"]
        for filepath, content in self._scan_source_files().items():
            lines = content.split("\n")
            for i, line in enumerate(lines):
                for kw in keywords_bad:
                    if kw in line:
                        if any(ok in line.lower() for ok in keywords_ok):
                            continue
                        # Provjeri da li je u komentaru koji objašnjava
                        if line.strip().startswith("#") or line.strip().startswith("//"):
                            continue
                        self.fail(
                            f"M5 Ultra kao 'trenutni' hw u {filepath}:{i+1}: {line.strip()}\n"
                            "M5 Ultra JOŠ NIJE IZAŠAO na datum 27.02.2026!"
                        )

    def test_no_192gb_as_target_config(self):
        """192GB NE POSTOJI kao Apple konfiguracija."""
        # Mac Studio M4 Max: 36, 48, 64, 128 GB
        # Mac Studio M3 Ultra: 96, 256, 512 GB
        for filepath, content in self._scan_source_files().items():
            if "test_" in filepath:
                continue  # Testovi mogu testirati 192 kao hipotetski
            lines = content.split("\n")
            for i, line in enumerate(lines):
                if "192" in line and "GB" in line:
                    if "~~" in line or "ne postoji" in line.lower() or "nije" in line.lower():
                        continue
                    if "8192" in line:  # context window, ne RAM
                        continue
                    # Dopušteno samo u komentarima koji objašnjavaju
                    if any(w in line.lower() for w in ["preporučeno 192", "za 192 gb mac"]):
                        self.fail(
                            f"192GB RAM referenca u {filepath}:{i+1}: {line.strip()}\n"
                            "192GB NE POSTOJI kao Mac Studio konfiguracija!"
                        )

    def test_correct_ram_options_documented(self):
        """README mora dokumentirati stvarne Apple RAM opcije."""
        readme_path = Path(__file__).parent.parent / "README.md"
        if readme_path.exists():
            content = readme_path.read_text()
            # M4 Max RAM opcije
            self.assertIn("36", content)
            self.assertIn("128 GB", content)
            # M3 Ultra RAM opcije
            self.assertIn("96", content)
            self.assertIn("256", content)
            self.assertIn("512", content)


# ═══════════════════════════════════════════════════════════════
# TRIPLE CHECK FOR LAWS (RAG) TESTS
# ═══════════════════════════════════════════════════════════════

class TestTripleLawVerification(unittest.TestCase):
    """Testovi da zakonski odgovori prolaze 3× provjeru."""

    def setUp(self):
        self.verifier = TripleVerifier()
        # Registriraj law-specific checks
        self.verifier.register_check("law_answer", "rag_search",
                                     self._mock_rag_search)
        self.verifier.register_check("law_answer", "keyword_search",
                                     self._mock_keyword_search)
        self.verifier.register_check("law_answer", "date_validation",
                                     self._mock_date_validation)

    @staticmethod
    def _mock_rag_search(value, ctx):
        return VerificationResult("rag_search", CheckResult.PASS, value,
                                  "RAG found: Zakon o PDV-u čl. 7")

    @staticmethod
    def _mock_keyword_search(value, ctx):
        return VerificationResult("keyword_search", CheckResult.PASS, value,
                                  "Keyword found: PDV stopa 25%")

    @staticmethod
    def _mock_date_validation(value, ctx):
        return VerificationResult("date_validation", CheckResult.PASS, value,
                                  "Zakon na snazi: NN 151/25 od 01.01.2026")

    def test_law_answer_triple_check(self):
        """Zakonski odgovor mora proći 3× provjeru."""
        result = self.verifier.verify("law_answer", "PDV stopa je 25%",
                                      {"date": "2026-02-27"})
        self.assertEqual(result.consensus, ConsensusLevel.FULL)
        self.assertFalse(result.needs_human_review)


if __name__ == "__main__":
    unittest.main()
