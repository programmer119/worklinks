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

    def test_guidance_scoring_and_future_warning_are_not_eligibility(self):
        guidance = (
            "투찰업체는 입찰참가자격 및 과업지시서 등 반드시 확인바랍니다.",
            "발표 참석자 전원은 재직증명서와 신분증을 반드시 지참하여야 함.",
            "유사사업 수행실적 평가항목 10점 만점으로 배점합니다.",
            "서약내용이 허위로 판명될 경우 입찰 참가 자격의 제한을 받을 수 있음.",
        )
        for phrase in guidance:
            with self.subTest(phrase=phrase):
                self.assertTrue(mod.clearly_nonqualification_guidance(phrase), phrase)
                self.assertTrue(mod.nonqualification_context(phrase), phrase)
                self.assertFalse(mod.extract_rule_candidates(phrase, "공고.hwpx"))
                self.assertTrue(mod.audit_qualification_scan(phrase, [])["sourceTextScanComplete"])

    def test_explicit_bidder_prerequisites_are_not_hidden_by_guidance(self):
        requirements = (
            "투찰업체는 업종코드 1468 등록업체이어야 하며 공고를 확인 바랍니다.",
            "입찰참가자격으로 유사실적 3건 이상 보유한 업체",
            "본점 소재지는 경상북도이어야 하며 발표자는 신분증을 지참합니다.",
            "직접생산확인증명서 8111189901 필수 제출이며 배점은 별도입니다.",
            "현재 입찰참가자격 제한 기간 중인 자는 참가할 수 없습니다.",
        )
        for phrase in requirements:
            with self.subTest(phrase=phrase):
                self.assertFalse(mod.clearly_nonqualification_guidance(phrase), phrase)
                self.assertFalse(mod.nonqualification_context(phrase), phrase)
                self.assertFalse(mod.audit_qualification_scan(phrase, [])["sourceTextScanComplete"])

    def test_sme_project_background_is_not_bidder_requirement(self):
        background = (
            "가. C-레벨의 AI 데이터 기반 의사결정 역량 강화를 통해 "
            "중소기업의 성공적 AX 전환을 지원한다.\n"
            "다. 지역 중소기업과 네트워킹을 강화한다."
        )
        self.assertEqual(mod.audit_qualification_scan(background, [])["qualificationAnchorCount"], 0)
        self.assertEqual(mod.preserve_unclassified_qualification(
            background, "official.hwp", [])["unclassifiedQualificationCount"], 0)
        mandatory = "본 입찰은 중소기업만 참가 가능합니다."
        self.assertFalse(mod.audit_qualification_scan(
            mandatory, [])["sourceTextScanComplete"])
        self.assertFalse(mod.audit_qualification_scan(
            "소기업 확인서를 필수로 제출하여야 합니다.", [])["sourceTextScanComplete"])

    def test_unclassified_requirement_preserves_citation_and_never_claims_verification(self):
        text = ("입찰참가자격으로 발주기관이 지정한 보안교육 수료증을 반드시 "
                "입찰일 이전에 발급받은 업체만 참가 가능합니다.")
        original = mod.extract_rule_candidates(text, "official.hwpx")
        before = mod.audit_qualification_scan(text, original)
        self.assertFalse(before["sourceTextScanComplete"], (before, original))
        scan = mod.preserve_unclassified_qualification(text, "official.hwpx", original)
        extra = [r for r in original if r["type"] == "unclassified_qualification"]
        self.assertTrue(extra, original)
        self.assertTrue(scan["sourceTextScanComplete"], scan)
        self.assertEqual(scan["unmatchedQualificationAnchorCount"], 0)
        self.assertGreater(scan["preSupplementUnmatchedCount"], 0)
        self.assertTrue(all(c["explicitMust"] is False and
                            c["documentRequiresManualFullReview"] is True for c in extra))
        self.assertTrue(any("보안교육" in c["sourceText"] for c in extra))

    def test_document_read_instruction_is_not_a_bidder_condition(self):
        text = "투찰업체는 입찰참가자격 및 과업지시서 등을 반드시 확인 바랍니다."
        candidates = mod.extract_rule_candidates(text, "official.pdf")
        scan = mod.preserve_unclassified_qualification(text, "official.pdf", candidates)
        self.assertEqual(scan["unmatchedQualificationAnchorCount"], 0)
        self.assertFalse(any(c["type"] == "unclassified_qualification" for c in candidates))
        self.assertEqual(scan["unclassifiedQualificationCount"], 0)

    def test_uncited_evidence_cannot_override_long_text_truncation(self):
        text = "입찰참가자격 세부 규정을 검토해야 합니다.\n" + "무관한 부연설명.\n" * 50000
        candidates = mod.extract_rule_candidates(text, "official.hwpx")
        result = mod.preserve_unclassified_qualification(text, "official.hwpx", candidates)
        self.assertFalse(result["sourceTextScanComplete"], result)

    def test_hwpx_valid_large_xml_document_is_not_rejected(self):
        # Real HWPX often has large layout metadata but little extracted text.
        import io
        import zipfile
        phrase = "소프트웨어사업자 업종코드 1468 등록업체만 입찰할 수 있습니다."
        xml = "<root><!--" + "X" * 3_300_000 + "--><p><t>" + phrase * 3 + "</t></p></root>"
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("Contents/section0.xml", xml)
        result = mod.extract("공고.hwpx", output.getvalue())
        self.assertIn(phrase, result)
        self.assertTrue(mod.audit_qualification_scan(
            result, mod.extract_rule_candidates(result, "공고.hwpx"))["sourceTextScanComplete"])

    def test_hwpx_large_xml_still_has_bounded_limits(self):
        import io
        import zipfile
        output = io.BytesIO()
        xml = "<root><!--" + "X" * (mod.MAX_HWPX_XML_MEMBER + 1) + "--></root>"
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("Contents/section0.xml", xml)
        with self.assertRaisesRegex(ValueError, "large_xml_section"):
            mod.extract("공고.hwpx", output.getvalue())

    def test_previous_hwpx_size_failures_are_retried_once(self):
        old = {"files":[{"name":"입찰공고.hwpx","errorCategory":"large_xml_section"}]}
        self.assertTrue(mod.needs_hwpx_reader_retry(old))
        old["hwpxReaderVersion"] = mod.HWPX_READER_VERSION
        self.assertFalse(mod.needs_hwpx_reader_retry(old))
        self.assertFalse(mod.needs_hwpx_reader_retry({
            "files":[{"name":"낙찰.pdf","errorCategory":"large_xml_section"}]}))

    def test_ordinary_bidder_administration_is_not_an_eligibility_gate(self):
        guidance = (
            "다. 입찰참가자격 : 다음 조건을 충족하는 자",
            "3 견적 제출 참가자격: 다음의 자격을 모두 갖춘 업체",
            "견적 제출 참가자격",
            "콜센터로 문의하지 않아 발생하는 모든 책임은 입찰 참가자에게 있습니다.",
            "입찰 참가자 전원이 2개씩 추첨하여 예정가격을 결정합니다.",
            "제안사는 평가결과에 대해 이의를 제기할 수 없으며 입찰참가업체에 한하여 공개합니다.",
            "제안서를 위조하여 제출한 경우 공모참가자격 제한 등의 조치를 받을 수 있음.",
        )
        for line in guidance:
            with self.subTest(line=line):
                self.assertTrue(mod.nonqualification_context(line), line)
                result, _ = self.scan(line)
                self.assertTrue(result["sourceTextScanComplete"], (line, result))

    def test_call_center_phone_number_is_not_a_bidder_credential(self):
        contacts = (
            "○ 입찰참가자격 등록, 나라장터 시스템: 정부조달 콜센터(☎ 1588-0800)",
            "10.1. 전자입찰 이용, 입찰참가자격등록: 나라장터시스템 콜센터(☎1588-0800)",
        )
        for line in contacts:
            with self.subTest(line=line):
                self.assertTrue(mod.nonqualification_context(line), line)
                result, _ = self.scan(line)
                self.assertTrue(result["sourceTextScanComplete"], (line, result))
        required = "소프트웨어사업자 업종코드 1468 등록업체만 입찰할 수 있습니다."
        self.assertFalse(mod.nonqualification_context(required))
        self.assertFalse(mod.audit_qualification_scan(required, [])["sourceTextScanComplete"])

    def test_real_bidder_conditions_still_block_unrepresented_evidence(self):
        required = (
            "입찰참가자격: 본점 소재지가 제주특별자치도인 업체만 참여 가능.",
            "소프트웨어사업자 업종코드 1468 등록업체만 입찰할 수 있습니다.",
            "직접생산확인증명서 세부품명번호 8111189901 소지한 업체",
        )
        for line in required:
            with self.subTest(line=line):
                self.assertFalse(mod.nonqualification_context(line), line)
                scan = mod.audit_qualification_scan(line, [])
                self.assertFalse(scan["sourceTextScanComplete"], (line, scan))

    def test_bid_registration_identity_and_general_statutory_eligibility(self):
        text = (
            "규칙 제14조에 따른 참가 자격을 갖춘 업체\n"
            "사. 입찰 참가 자격 등록 사항에 변경 사항이 있는 업체는 반드시 "
            "입찰서 제출 마감일 전일까지 변경 등록하여야 합니다.\n"
            "입찰 참가 자격 제한기간 중에 있는 자는 참가할 수 없습니다."
        )
        check, clauses = self.scan(text)
        self.assertTrue(check["sourceTextScanComplete"],check)
        self.assertIn("registration_identity",{c["type"] for c in clauses})
        self.assertIn("legal_exclusion",{c["type"] for c in clauses})
        self.assertIn("submission_required",{c["type"] for c in clauses})
        self.assertFalse(mod.audit_qualification_scan(
            "입찰 참가 자격 등록 사항에 변경 사항이 있는 업체는 반드시 변경 등록하여야 합니다.",
            [])["sourceTextScanComplete"])

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

    def test_null_separated_official_document_preserves_bid_criteria(self):
        raw = (
            "입찰참가자격: 소프트웨어사업자(컴퓨터관련서비스사업)\x00업종코드\x001468 등록한 자\n"
            "직접생산확인증명서\x00세부품명번호\x008111189901 소지한 자"
        )
        clean = mod.normalize_extracted_text(raw)
        self.assertNotIn("\x00", clean)
        result, clauses = self.scan(clean)
        self.assertTrue(any(c["type"] == "industry_code" and
                            "1468" in c["codes"] for c in clauses))
        self.assertTrue(any(c["type"] == "direct_production" and
                            "8111189901" in c["codes"] for c in clauses))
        self.assertTrue(result["sourceTextScanComplete"], result)

    def test_standalone_bidder_responsibility_tail_is_guidance(self):
        text = ("정부조달콜센터에 문의하지 않아 발생한 모든 책임은\n"
                "입찰참가자에게 있습니다.")
        result, _ = self.scan(text)
        self.assertTrue(result["sourceTextScanComplete"], result)

    def test_responsibility_tail_does_not_hide_eligibility(self):
        result = mod.audit_qualification_scan(
            "입찰참가자격의 판단기준일은 등록마감일입니다.", [])
        self.assertFalse(result["sourceTextScanComplete"])

    def test_official_sme_certificate_separator_is_captured(self):
        text = ("바. 중소기업기본법에 따른 소기업 또는 소상공인으로서 "
                "발급된 소기업․ 소상공인확인서를 소지한 업체")
        for name in ("official.hwpx", "official.pdf"):
            clauses = mod.extract_rule_candidates(text, name)
            result = mod.audit_qualification_scan(text, clauses)
            self.assertTrue(any(c["type"] == "sme_certificate" and
                                "소지한 업체" in c["sourceText"] for c in clauses), (name, clauses))
            self.assertTrue(result["sourceTextScanComplete"], (name, result))

    def test_registration_and_specification_eligibility_is_not_lost(self):
        text = ("가. 법령에 따른 참가자격을 갖추고 나라장터에 "
                "입찰참가자격등록 마감일시까지 입찰참가 등록하고 "
                "규격서에 따라 납품 가능한 업체")
        for name in ("official.hwpx", "official.pdf"):
            clauses = mod.extract_rule_candidates(text, name)
            result = mod.audit_qualification_scan(text, clauses)
            self.assertTrue(any(c["type"] == "submission_required" for c in clauses), (name, clauses))
            self.assertTrue(result["sourceTextScanComplete"], (name, result))

    def test_bidder_proof_document_list_is_retained(self):
        text = ("※ 입찰참가자격 입증서류 : 부정당업자 제재처분확인서, "
                "면허등록증, 사업자등록증을 제출하여야 합니다.")
        clauses = mod.extract_rule_candidates(text, "official.hwpx")
        result = mod.audit_qualification_scan(text, clauses)
        self.assertTrue(any(c["type"] == "submission_required" for c in clauses))
        self.assertTrue(result["sourceTextScanComplete"], result)

    def test_procedural_heading_and_call_center_do_not_mask_sme_condition(self):
        text = ("4. 견적제출 참가자격(아래 조건을 모두 충족하여야 함)\n"
                "소기업․ 소상공인확인서를 소지한 업체\n"
                "투찰이 곤란할 경우 국가종합전자조달 콜센터 (1588-0800)에 "
                "문의하지 않아 발생되는 책임은 입찰 참가자에게 있습니다.")
        clauses = mod.extract_rule_candidates(text, "official.hwpx")
        result = mod.audit_qualification_scan(text, clauses)
        self.assertTrue(any(c["type"] == "sme_certificate" for c in clauses))
        self.assertTrue(result["sourceTextScanComplete"], result)


    def test_long_midlength_paragraph_retains_last_qualification(self):
        prefix = "공고 안내사항 참고. " * 23
        text = (prefix + "가. 국가계약법령 규정에 의한 참가자격을 갖추고 "
                "나라장터에 입찰참가자격등록 마감일시까지 입찰참가 등록하고 "
                "규격서에 따라 납품 가능한 업체")
        self.assertGreater(len(text), 270)
        self.assertLess(len(text), 800)
        for filename in ("공고.hwpx", "공고.pdf"):
            clauses = mod.extract_rule_candidates(text, filename)
            check = mod.audit_qualification_scan(text, clauses)
            self.assertTrue(any(c["type"]=="submission_required" and
                                "규격서" in c["sourceText"] for c in clauses), (filename, clauses))
            self.assertTrue(check["sourceTextScanComplete"], (filename,check))

    def test_wrapped_pdf_administrative_tail_does_not_hide_current_conditions(self):
        text = ("규정에 의한 참가자격을 갖추고, 「국가종합전자조달시스템 입찰참가자격등록규정」에 따라\\n"
                "까지 입찰참가 등록하고 규격서에 따라 납품 가능한 업체\\n"
                "입찰참가작격 등을 확인하기 위하여 협상대상자에게 필요한 서류 제출을 요청함\\n"
                "장애발생에도 불구하고 문의하지 않아 발생되는 모든 책임은 입찰참가자에 있습니다.")
        text = text.replace("\\n", "\n")
        clauses = mod.extract_rule_candidates(text, "공고.pdf")
        result = mod.audit_qualification_scan(text, clauses)
        self.assertTrue(any(c["type"]=="submission_required" for c in clauses), clauses)
        self.assertTrue(result["sourceTextScanComplete"], result)
        self.assertFalse(mod.audit_qualification_scan(
            "규정에 의한 참가자격을 갖추고", [])["sourceTextScanComplete"])

if __name__ == "__main__":
    unittest.main()
