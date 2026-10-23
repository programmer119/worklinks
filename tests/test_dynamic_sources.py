"""Regression checks for browser-only public investment/startup sources."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from worklinks_dynamic_sources import (
    project_record, ir_record, objects, date_value, record_id
)

class DynamicSourcesTest(unittest.TestCase):
    def test_project_real_code_and_verified_deadline_time(self):
        item = project_record({
            "projectCode": "PRJ007522",
            "projectName": "2026년 벤처확인 도전기업 비대면 밋업",
            "receiptEndDate": "2026-10-31 23:59",
            "organizationName": "서울 창업지원"
        })
        self.assertTrue(item)
        self.assertEqual(item["url"], "https://www.startup-plus.kr/project/PRJ007522")
        self.assertEqual(item["deadline"], "2026-10-31T23:59:00+09:00")
        self.assertEqual(item["eligibility"], "자격 확인 필요")

    def test_project_template_not_a_real_notice(self):
        self.assertIsNone(project_record({"projectCode":"{{projectCode}}","projectName":"투자 모집 공고"}))
        self.assertIsNone(project_record({"projectCode":"PRJ007522","projectName":""}))

    def test_operator_session_per_date_and_program(self):
        a = ir_record({"operatorName":"끌림벤처스","irDate":"2026-11-02","programId":"event-1",
                       "applicationStatus":"OPEN","remainCount":3})
        b = ir_record({"operatorName":"끌림벤처스","irDate":"2026-11-03","programId":"event-2"})
        self.assertTrue(a and b)
        self.assertNotEqual(a["id"], b["id"])
        self.assertEqual(a["deadline"], None)
        self.assertEqual(a["irDate"],"2026-11-02")
        self.assertEqual(a["url"],"https://irchallenge.jointips.or.kr/apply")
        self.assertIn("잔여 3",a["description"])

    def test_invalid_generic_investor_is_not_ir_session(self):
        self.assertIsNone(ir_record({"operatorName":"투자사소개","companyId":"xyz"}))
        self.assertIsNone(ir_record({"irDate":"2026-11-04","title":"IR"}))

    def test_no_invented_2359_and_nested_payload(self):
        self.assertEqual(date_value("2026.11.06"),"2026-11-06")
        self.assertEqual(date_value("20261106"),"2026-11-06")
        self.assertEqual(date_value("unknown"),None)
        nested={"data":{"list":[{"projectCode":"PRJ007525",
                                   "projectName":"스타트업 투자제안 상담회",
                                   "endDt":"2026-11-06"}]}}
        found=[project_record(x) for x in objects(nested)]
        self.assertEqual(sum(x is not None for x in found),1)

    def test_stable_identity(self):
        self.assertEqual(record_id("ir-session","abc"),record_id("ir-session","abc"))
if __name__=="__main__":
    unittest.main()
