"""Regression tests for official RFP qualification evidence coverage."""
import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("refresh_worklinks_rfp", ROOT / "scripts" / "refresh_worklinks_rfp.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class QualificationCoverageTests(unittest.TestCase):
    def scan(self, text):
        clauses = mod.extract_rule_candidates(text, "official.pdf")
        return mod.audit_qualification_scan(text, clauses), clauses

    def test_wrapped_long_paragraph_with_explicit_code(self):
        filler = "과업 안내 및 세부 시행 기준을 참고합니다. " * 28
        text = filler + " 소프트웨어사업자 업종코드 1468 등록업체만 입찰할 수 있습니다. " + filler
        result, clauses = self.scan(text)
        self.assertTrue(any("1468" in c["codes"] for c in clauses))
        self.assertTrue(result["sourceTextScanComplete"], result)

    def test_unrepresented_mandatory_qualification_stays_pending(self):
        text = "소프트웨어사업자 업종코드 1468 등록업체만 입찰할 수 있습니다."
        result = mod.audit_qualification_scan(text, [])
        self.assertFalse(result["sourceTextScanComplete"])
        self.assertGreater(result["unmatchedQualificationAnchorCount"], 0)

    def test_jeju_region_is_not_ignored(self):
        text = "입찰참가자격: 본점 소재지가 제주특별자치도인 업체만 참여 가능."
        result, clauses = self.scan(text)
        self.assertTrue(any(c["type"] == "region_restriction" for c in clauses))
        self.assertTrue(any("제주특별자치도" in c["sourceText"] for c in clauses))

    def test_candidate_count_is_not_silently_capped_at_240(self):
        text = "\n".join(f"직접생산 확인증명서 품목번호 8111189901 관련 등록조건 {i}번을 확인하여야 합니다."
                         for i in range(260))
        _, clauses = self.scan(text)
        self.assertGreaterEqual(len(clauses), 260)


if __name__ == "__main__":
    unittest.main()
