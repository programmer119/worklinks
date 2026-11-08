"""Strict offline merge tests for KIMSE official-source audit records."""
import datetime as dt
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from worklinks_kimse_merge_audit import merge_verified_deadlines,safe_official_url,KST

NOW=dt.datetime(2026,11,8,21,0,tzinfo=KST)
URL="https://www.khidi.or.kr/board/view?menuId=MENU01484&linkId=48952358"
SOURCE="KHIDI 기관별 의료·연구지원 사업"

class DeepAuditMergeTests(unittest.TestCase):
    def entry(self,**changes):
        r={"title":"2027년 제1차 식약처 연구개발 공고",
           "url":URL,"source":SOURCE,
           "applicationDeadline":"2026-12-07T11:00:00+09:00",
           "status":"deadline_verified_eligibility_pending",
           "deadlineEvidenceSource":"official_article_application_period",
           "kimseFit":"높음"}
        r.update(changes)
        return r

    def audit(self,*rows,at="2026-11-08T20:30:00+09:00"):
        return {"schemaVersion":1,"generatedAt":at,"results":list(rows)}

    def test_known_url_gains_only_verified_deadline_not_eligibility(self):
        rows=[{"id":"old","url":URL,"source":SOURCE,
               "deadline":None,"title":"식약처 연구개발",
               "lastSeenAt":"2026-11-08T20:00:00+09:00",
               "eligibility":"자격 확인 필요"}]
        out,meta=merge_verified_deadlines(rows,self.audit(self.entry()),NOW)
        self.assertEqual(meta["updated"],1)
        self.assertEqual(len(out),1)
        self.assertEqual(out[0]["deadline"],"2026-12-07T11:00:00+09:00")
        self.assertEqual(out[0]["eligibility"],"자격 확인 필요")
        self.assertEqual(out[0]["sourceStatus"],"unknown")

    def test_expired_date_is_closed_without_fake_future_eligibility(self):
        out,meta=merge_verified_deadlines([],self.audit(
            self.entry(applicationDeadline="2026-10-13",
                       status="expired_confirmed")),NOW)
        self.assertEqual(meta["added"],1)
        self.assertEqual(out[0]["sourceStatus"],"closed")

    def test_open_date_current_source_conflict_not_overwritten(self):
        current=[{"url":URL,"deadline":"2026-12-10",
             "lastSeenAt":"2026-11-08T20:40:00+09:00"}]
        out,meta=merge_verified_deadlines(current,self.audit(self.entry()),NOW)
        self.assertEqual(meta["conflicts"],1)
        self.assertEqual(out[0]["deadline"],"2026-12-10")

    def test_unsupported_host_and_unknown_deadline_never_import(self):
        alien=self.entry(url="https://evil.example/board/view?menuId=MENU01484&linkId=48952358")
        unknown=self.entry(status="unknown_deadline",applicationDeadline=None)
        out,meta=merge_verified_deadlines([],self.audit(alien,unknown),NOW)
        self.assertEqual(out,[])
        self.assertEqual(meta["accepted"],0)
        self.assertFalse(safe_official_url(alien["url"],SOURCE))

    def test_stale_audit_cannot_rewrite_current_application_status(self):
        out,meta=merge_verified_deadlines([],self.audit(
            self.entry(),at="2026-11-01T10:00:00+09:00"),NOW)
        self.assertEqual(out,[])
        self.assertEqual(meta["skipped"],"stale_audit")

    def test_khis_verified_canonical_notice_accepted(self):
        url="https://www.khis.kr/board.es?act=view&bid=0009&list_no=2678&mid=a10304000000"
        self.assertTrue(safe_official_url(url,"한국보건의료정보원 실증·사업 공고"))
        self.assertFalse(safe_official_url(url.replace("bid=0009","bid=0001"),
             "한국보건의료정보원 실증·사업 공고"))

if __name__=="__main__":
    unittest.main()
