#!/usr/bin/env python3
"""No-network regressions for WorkLinks automatic, source-cited RFP AI analysis."""
import importlib.util
import json
import tempfile
from pathlib import Path

src=Path(__file__).resolve().parents[1]/"scripts/analyze_worklinks_rfp_ai.py"
spec=importlib.util.spec_from_file_location("worklinks_rfp_ai",src)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
notice={"files":[{"name":"공식 제안요청서.hwp","readable":True,"clauseCandidates":[
 {"type":"industry_code","codes":["1468"],"sourceFile":"공식 제안요청서.hwp",
  "sourceText":"소프트웨어사업자 컴퓨터관련서비스사업 업종코드 1468 등록하여야 한다"},
 {"type":"direct_production","codes":["8111189901"],"sourceFile":"공식 제안요청서.hwp",
  "sourceText":"직접생산확인증명서 정보시스템유지관리서비스 세부품명 8111189901 소지"},
 {"type":"joint_participation","codes":[],"sourceFile":"공식 제안요청서.hwp",
  "sourceText":"본 사업에 대한 공동수급은 불가하며 단독으로 참가해야 한다"},
 {"type":"industry_code","codes":["1468"],"sourceFile":"공식 제안요청서.hwp",
  "sourceText":"소프트웨어사업자 컴퓨터관련서비스사업 업종코드 1468 등록하여야 한다"}
]}],"reviewComplete":False}
c=m.source_candidates(notice)
assert len(c)==3
assert c[0]["codes"]==["1468"]
assert c[1]["codes"]==["8111189901"]
def mock(rows):
 return {"items":[{"index":i,"classification":"mandatory" if i!=2 else "prohibited",
     "relation":"all" if i!=2 else "not_allowed","reason":"원문에 명시된 입찰 조건"} for i in range(len(rows))]}
a=m.process_one("R26BK01756420:000",notice,None,mock)
assert a["analysisStatus"]=="classified" and a["interpretedCount"]==3
assert a["reviewComplete"] is False and a["automaticEligibilityApproved"] is False
assert a["requirements"][0]["sourceText"]==c[0]["sourceText"]
assert a["requirements"][1]["codes"]==["8111189901"]
assert m.process_one("R26BK01756420:000",notice,a,mock) is None
for wrong in [
 {"items":[{"index":0,"classification":"mandatory","relation":"all","reason":"x"}]},
 {"items":[{"index":0,"classification":"ready","relation":"all","reason":"x"}]},
 {"items":[{"index":0,"classification":"mandatory","relation":"all","reason":"x"} for _ in range(3)]},
 {"items":[{"index":100,"classification":"mandatory","relation":"all","reason":"x"}]},
 {"items":[{"index":0,"classification":"mandatory","relation":"not_allowed","reason":"x"}]}
]:
 try:
  m.validate_inference(wrong,c)
  raise AssertionError("model output accepted without complete source validation")
 except ValueError:pass
# Exclude proposal/delivery language from bidder prerequisites in rule-only mode.
samples=[
 {"index":0,"type":"industry_code","sourceText":"입찰참가자격으로 소프트웨어사업자 업종코드 1468 등록하여야 한다"},
 {"index":1,"type":"staff_proof","sourceText":"계약체결 후 사업 수행 중 투입인력 배치계획을 제출하여야 한다"},
 {"index":2,"type":"performance_proof","sourceText":"정보시스템의 과거 수행실적 통계 조회 기능 개선"},
 {"index":3,"type":"joint_participation","sourceText":"공동수급 불가하며 단독 참가"},
 {"index":4,"type":"performance_proof","sourceText":"입찰참가자격으로 유사용역 실적증명서를 제출하여야 한다"}
]
classified=m.rule_based_interpret(samples)["items"]
assert [q["classification"] for q in classified]==[
 "mandatory","context_only","unknown","prohibited","mandatory"]
# Real official phrasing: "소지한 업체" and "등록을 필한 업체" must be
# recognized; no requirement may be fabricated from a mere service mention.
realistic=[
 {"index":0,"type":"direct_production","sourceText":"규정에 의한 직접 생산 확인 증명서[공간정보 DB 구축 서비스(8115169901)]를 소지한 업체"},
 {"index":1,"type":"sme_certificate","sourceText":"규정에 따라 발급된 소기업 소상공인 확인서를 소지한 업체"},
 {"index":2,"type":"industry_code","sourceText":"소프트웨어사업자(컴퓨터관련서비스사업, 업종코드: 1468) 면허 등록을 필한 업체이어야 합니다"},
 {"index":3,"type":"region_restriction","sourceText":"2.2. 지역제한(제주특별자치도) 대상 용역입니다."},
 {"index":4,"type":"joint_participation","sourceText":"공동수급 및 하도급을 일체 허용하지 않음"}
]
assert [x["classification"] for x in m.rule_based_interpret(realistic)["items"]]==[
 "mandatory","mandatory","mandatory","mandatory","prohibited"]
# Never fabricate a matching company qualification from a model statement.
assert all(x["sourceVerified"] and not x["documentFullyReviewed"] for x in a["requirements"])
# Persisted artifacts must not contain a copy of the GitHub auth token.
with tempfile.TemporaryDirectory() as tmp:
 target=Path(tmp)/"ai-qualification.json"
 target.write_text(json.dumps({"byNotice":{"R26BK01756420:000":a}},ensure_ascii=False))
 assert "GITHUB_TOKEN" not in target.read_text()
print("WORKLINKS_RFP_AI_SOURCE_VALIDATION=PASS")
