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

    def test_legal_disqualifications_are_extracted(self):
        text = ("「중소기업제품 구매촉진 및 판로지원에 관한 법률」제8조의2에 해당하는 자는 "
                "입찰에 참여할 수 없습니다.\n"
                "조세포탈 등을 한 자로서 유죄판결이 확정된 날부터 2년이 지나지 아니한 자는 "
                "입찰에 참여할 수 없습니다.")
        result, clauses = self.scan(text)
        self.assertTrue(any(c["type"] == "legal_exclusion" for c in clauses))
        self.assertTrue(result["sourceTextScanComplete"], result)

    def test_original_bid_registration_cutoff_and_security(self):
        text = ("9-2. 입찰참가자격등록증상의 상호 및 대표자가 사업자등록증의 상호와 다르면 "
                "변경등록하고 입찰에 참여하여야 합니다.\n"
                "9-3. 입찰참가자격의 판단기준일은 입찰참가자격등록 마감일이며 "
                "마감일까지 참가자격을 갖추지 않은 경우 무효입찰입니다.\n"
                "8-1. 입찰보증금을 납부하여야 합니다.")
        result, clauses = self.scan(text)
        kinds = {c["type"] for c in clauses}
        self.assertTrue({"registration_identity","eligibility_cutoff","bid_security"} <= kinds)
        self.assertTrue(result["sourceTextScanComplete"], result)

    def test_evaluation_and_future_sanction_are_not_eligibility_gates(self):
        text = ("창업기업 신용평가등급 점수상의 배점 한도를 부여한다.\n"
                "담합에 의한 위반이 드러날 경우 입찰참가자격 제한처분을 받을 수 있습니다.")
        result, _ = self.scan(text)
        self.assertTrue(result["sourceTextScanComplete"], result)

    def test_pdf_wrapped_legal_citation_is_covered_by_neighboring_requirement(self):
        text = ("중소기업제품 구매촉진 및 판로지원에 관한 법률 제 조 및 같은 법 시행령\n"
                "제 조에 따라 다음 요건을 충족한 사업자여야 하며\n"
                "직접생산확인증명서 품목번호 8111189901을 소지한 자")
        result, clauses = self.scan(text)
        self.assertTrue(any(c["type"] == "direct_production" for c in clauses))
        self.assertTrue(result["sourceTextScanComplete"], result)

    def test_future_penalty_does_not_mask_current_exclusion(self):
        text = ("정보를 누출하는 경우 입찰참가자격을 제한함\n"
                "조세포탈 등을 한 자로서 유죄판결이 확정된 날부터 2년이 지나지 아니한 자는 "
                "입찰에 참여할 수 없습니다.")
        result, clauses = self.scan(text)
        self.assertTrue(any(c["type"] == "legal_exclusion" for c in clauses))
        self.assertTrue(result["sourceTextScanComplete"], result)

    def test_candidate_count_is_not_silently_capped_at_240(self):
        text = "\n".join(f"직접생산 확인증명서 품목번호 8111189901 관련 등록조건 {i}번을 확인하여야 합니다."
                         for i in range(260))
        _, clauses = self.scan(text)
        self.assertGreaterEqual(len(clauses), 260)

    def test_standalone_bidder_responsibility_tail_is_guidance(self):
        text = ("정부조달콜센터에 문의하지 않아 발생한 모든 책임은\n"
                "입찰참가자에게 있습니다.")
        result, _ = self.scan(text)
        self.assertTrue(result["sourceTextScanComplete"], result)

    def test_responsibility_tail_does_not_hide_eligibility(self):
        result = mod.audit_qualification_scan(
            "입찰참가자격의 판단기준일은 등록마감일입니다.", [])
        self.assertFalse(result["sourceTextScanComplete"])

if __name__ == "__main__":
    unittest.main()
