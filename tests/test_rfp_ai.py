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
assert a["fullDocumentAudit"]["complete"] is False
assert "official_attachment_manifest_incomplete" in a["fullDocumentAudit"]["blockers"]
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
 "mandatory","context_only","context_only","prohibited","mandatory"]
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
# Consortium templates, proposal scoring and broken PDF-line duplicates
# must never be counted as additional missing bidder credentials.
conditional=[
 {"index":0,"type":"joint_participation",
  "sourceText":"※ 공동수급인 경우 구성원별 별지 제5호 서식 각자 작성"},
 {"index":1,"type":"joint_participation",
  "sourceText":"공동수급체는 5개 이하로 구성하여야 하고 지분율은 10% 이상"},
 {"index":2,"type":"staff_proof",
  "sourceText":"투입인력 PC 소프트웨어 설치에 소요되는 일체의 경비는 본 사업에 포함"},
 {"index":3,"type":"performance_proof",
  "sourceText":"[붙임 4호 서식] 사업실적증명서"},
 {"index":4,"type":"industry_code","codes":["1468"],
  "sourceText":"소프트웨어사업자(컴퓨터관련서비스사업 업종코드 1468)로 입찰참가 등록 되어 있어야 합니다."},
 {"index":5,"type":"industry_code","codes":["1468"],
  "sourceText":"소프트웨어사업자(컴퓨터관련서비스사업 업종코드 1468)로 입찰참가"},
 {"index":6,"type":"direct_production","codes":["8111159901"],
  "sourceText":"직접생산확인증명서(정보시스템개발서비스 8111159901)를 소지한 업체"},
 {"index":7,"type":"direct_production","codes":["9999999999"],
  "sourceText":"직접생산확인증명서(알 수 없는 품목 9999999999)"},
]
r=m.rule_based_interpret(conditional)["items"]
assert [x["classification"] for x in r[:5]]==[
 "context_only","context_only","context_only","context_only","mandatory"]
assert r[5]["classification"]=="context_only"
assert r[6]["classification"]=="mandatory"
assert r[7]["classification"]=="unknown", "unmatched production item must remain unresolved"

# Automated machine review may complete only when every official file, quote,
# hash and bidder-condition classification can be reconciled.
import hashlib
good_text="소프트웨어사업자 1468 업종코드 등록한 업체"
sha=hashlib.sha256(good_text.encode()).hexdigest()
valid={"status":"text_extracted_requires_review","manifestComplete":True,
 "attachmentManifestCount":1,"files":[{"name":"입찰공고문.hwp","readable":True,
 "sourceSha256":sha,"textSha256":sha,"sourceTextScanComplete":True,
 "unmatchedQualificationAnchorCount":0,"clauseCandidates":[
 {"type":"industry_code","codes":["1468"],"sourceFile":"입찰공고문.hwp",
  "sourceText":good_text}]}]}
v=m.process_one("R26BK01700001:000",valid,None,lambda c:m.rule_based_interpret(c))
assert v["fullDocumentAudit"]["complete"] is True
assert v["reviewComplete"] is True and v["automaticEligibilityApproved"] is False
missing=dict(valid,files=[dict(valid["files"][0],sourceTextScanComplete=False)])
assert m.process_one("R26BK01700002:000",missing,None,
 lambda c:m.rule_based_interpret(c))["reviewComplete"] is False
# The interpreter must not silently drop clause 121 onward.
# Fully extracted files and fully interpreted clauses should remain auditable
# even when a notice contains more than 120 unique cited paragraphs.
large_notice=dict(valid,files=[dict(valid["files"][0],clauseCandidates=[
 {"type":"industry_code","codes":["1468"],"sourceFile":"입찰공고문.hwp",
  "sourceText":good_text+" 제"+str(i)+"항"} for i in range(135)
])])
assert len(m.source_candidates(large_notice))==135
large_result=m.process_one("R26BK01700003:000",large_notice,None,
 lambda c:m.rule_based_interpret(c))
assert large_result["interpretedCount"]==135
assert large_result["sourceTruncated"] is False
assert large_result["reviewComplete"] is True
assert len(large_result["requirements"])==135
# Never fabricate a matching company qualification from a model statement.
assert all(x["sourceVerified"] and not x["documentFullyReviewed"] for x in a["requirements"])
# Persisted artifacts must not contain a copy of the GitHub auth token.
with tempfile.TemporaryDirectory() as tmp:
 target=Path(tmp)/"ai-qualification.json"
 target.write_text(json.dumps({"byNotice":{"R26BK01756420:000":a}},ensure_ascii=False))
 assert "GITHUB_TOKEN" not in target.read_text()
print("WORKLINKS_RFP_AI_SOURCE_VALIDATION=PASS")

# Regression: general procurement guidance and consortium evaluation are not
# additional bidder credentials. Explicit mandatory/region rules remain.
context_samples=[
 {"index":0,"type":"industry_code","sourceText":"입찰 참가 자격"},
 {"index":1,"type":"industry_code","sourceText":"나라장터 전자입찰 이용자는 입찰참가자격등록규정에 따라 이용자 등록을 합니다"},
 {"index":2,"type":"joint_participation","sourceText":"공동수급체 평가점수는 지분율에 따라 계산한다"},
 {"index":3,"type":"performance_proof","sourceText":"제안서 평가용 수행실적 증명서 별지 2호 서식"},
 {"index":4,"type":"region_restriction","sourceText":"2.2. 지역제한(제주특별자치도) 대상 용역입니다."},
 {"index":5,"type":"joint_participation","sourceText":"공동수급 불허 단독 참가"},
 {"index":6,"type":"performance_proof","sourceText":"입찰참가자격으로 최근 3년 수행실적증명서를 제출하여야 한다"},
 {"index":7,"type":"industry_code","codes":["1468"],"sourceText":"소프트웨어사업자 업종코드 1468 등록을 필한 업체"}]
expected=["context_only","context_only","context_only","context_only",
          "mandatory","prohibited","mandatory","mandatory"]
actual=[x["classification"] for x in m.rule_based_interpret(context_samples)["items"]]
assert actual==expected,(actual,expected)

# Extractor coverage must not consider nonqualification headings, bidder
# portal instructions or score templates as a missing company qualification.
import io
import zipfile
rfp_path=Path(__file__).resolve().parents[1]/"scripts/refresh_worklinks_rfp.py"
rfp_spec=importlib.util.spec_from_file_location("worklinks_rfp_extractor",rfp_path)
rfp=importlib.util.module_from_spec(rfp_spec)
rfp_spec.loader.exec_module(rfp)
text_fixture=(
 "1. 입찰 참가 자격\n"
 "소프트웨어사업자 업종코드 1468 등록한 업체\n"
 "직접생산확인증명서 정보시스템유지관리서비스(8111189901)를 소지한 업체\n"
 "제안서 평가용 수행실적 별지 제3호 서식\n"
 "공동수급체 평가점수는 구성원별 지분율로 계산한다\n"
 "나라장터 전자입찰 이용 안내\n"
 "공동수급 불허\n"
)
rules=rfp.extract_rule_candidates(text_fixture,"입찰공고문.pdf")
scan=rfp.audit_qualification_scan(text_fixture,rules)
assert scan["sourceTextScanComplete"] is True,scan
assert any(x["type"]=="industry_code" for x in rules)
assert any(x["type"]=="direct_production" and "8111189901" in x["codes"] for x in rules)
assert any(x["type"]=="joint_participation" and "불허" in x["sourceText"] for x in rules)
missing_text=text_fixture+"\n기술인력 5명 이상 입찰자격으로 요구함"
failure=rfp.audit_qualification_scan(missing_text,rules)
assert failure["sourceTextScanComplete"] is False,failure
assert failure["unmatchedQualificationAnchorCount"]>0
region_text="지역 제한(제주특별자치도) 대상 용역입니다."
region_rules=rfp.extract_rule_candidates(region_text,"입찰공고문.pdf")
assert any(q["type"]=="region_restriction" for q in region_rules)
assert m.rule_based_interpret([dict(q,index=i) for i,q in enumerate(region_rules)])["items"][0]["classification"]=="mandatory"

# Nested official ZIP contents must actually be read; do not mark a ZIP as
# reviewed by its manifest alone or allow an unreadable executable to vanish.
def zip_bytes(members):
    b=io.BytesIO()
    with zipfile.ZipFile(b,"w") as z:
        for name,value in members.items():z.writestr(name,value)
    return b.getvalue()
docx=zip_bytes({"word/document.xml":
    '<w:document xmlns:w="urn:test"><w:body><w:p><w:r><w:t>입찰참가자격 업종코드 1468 등록</w:t></w:r></w:p></w:body></w:document>'})
archive=zip_bytes({"공고문.docx":docx})
assert "업종코드 1468" in rfp.extract("공고첨부.zip",archive)
assert "업종코드 1468" in rfp.extract("첨부명없음",docx)
try:
    rfp.extract("공고첨부.zip",zip_bytes({"unexpected.exe":b"not a document"}))
    raise AssertionError("unparsed archive member was silently ignored")
except ValueError as ex:
    assert "requires_review" in str(ex)
print("WORKLINKS_RFP_COVERAGE_AND_ARCHIVE=PASS")

# Explicit small-business-only bids and official local restrictions are bidder
# prerequisites; generic evaluation documents and post-award subcontract
# administration are not.
adversarial=[
 {"index":0,"type":"sme_certificate","sourceText":"※ 중소기업자만 입찰참가 가능"},
 {"index":1,"type":"region_restriction","sourceText":"참여지역(입찰참가자의 본점 소재)을 서울특별시 또는 경기도로 제한"},
 {"index":2,"type":"region_restriction","sourceText":"지역 제한은 두지 아니함"},
 {"index":3,"type":"joint_participation","sourceText":"하도급계약 승인을 신청하는 경우 하도급 계약승인 신청서 제출"},
 {"index":4,"type":"joint_participation","sourceText":"공동수급체 구성원별 평가점수는 지분율로 계산"},
 {"index":5,"type":"industry_code","sourceText":"대기업 및 중견기업인 소프트웨어사업자는 본 입찰에 참여할 수 없음"},
 {"index":6,"type":"joint_participation","sourceText":"공동수급체 전원 입찰참가자격을 구비하여야 한다"}
]
states=[v["classification"] for v in m.rule_based_interpret(adversarial)["items"]]
assert states==["mandatory","mandatory","context_only","context_only",
                "context_only","prohibited","context_only"],states
assert any(c["type"]=="sme_certificate" for c in rfp.extract_rule_candidates(
    "※ 중소기업자만 입찰참가 가능","입찰공고문.hwp"))




# Fully quoted bidder certificate must remain mandatory, while later
# conditional certificate paperwork and future contract penalties are context.
postaward=[
 {"index":0,"type":"sme_certificate","sourceText":
  "입찰참가자격으로 소기업 소상공인확인서를 소지한 업체"},
 {"index":1,"type":"sme_certificate","sourceText":
  "소기업·소상공인확인서 신청을 증빙할 수 있는 서류 1부"},
 {"index":2,"type":"direct_production","sourceText":
  "계약상대자가 직접생산 확인기준을 위반한 사실을 확인한 경우 계약해지"},
 {"index":3,"type":"staff_proof","sourceText":
  "주4) 상기내용을 증명할 수 있는 재직·경력·학력·자격증명서 서류 제출"},
 {"index":4,"type":"joint_participation","sourceText":"11. 하도급에 관한 사항"},
 {"index":5,"type":"joint_participation","sourceText":
  "하도급거래 공정화에 관한 법률 시행절차 안내"}
]
presult=m.rule_based_interpret(postaward)["items"]
assert [x["classification"] for x in presult]==[
    "mandatory","context_only","context_only","context_only","context_only","context_only"],presult
# Unknown certificate paperwork without a cited mandatory certificate clause
# stays unknown; do not invent a complete eligibility audit.
unanchored=m.rule_based_interpret(postaward[1:2])["items"]
assert unanchored[0]["classification"]=="unknown",unanchored


# Corrupted PDF fragments may be reconciled only against a *full* cited
# matching requirement. Never merge a different required production product.
fragmented=[
 {"index":0,"type":"direct_production","codes":["8111189901"],
  "sourceText":"직접생산확인증명서 세부품명 정보시스템유지관리서비스 세부품명번호 8111189901 소지한 업체"},
 {"index":1,"type":"direct_production","codes":[],
  "sourceText":"직접생산확인증명서 세부품명 정보시스템유지관리서비스 세부품명번호 자리"},
 {"index":2,"type":"direct_production","codes":[],
  "sourceText":"직접생산확인증명서 세부품명 인터넷지원개발서비스 세부품명번호 자리"},
 {"index":3,"type":"sme_certificate","codes":[],
  "sourceText":"소기업 소상공인확인서 신청을 증빙할 수 있는 서류 부"},
 {"index":4,"type":"sme_certificate","codes":[],
  "sourceText":"입찰참가 자격으로 소기업 소상공인확인서를 소지한 업체"}
]
fclasses=[x["classification"] for x in m.rule_based_interpret(fragmented)["items"]]
assert fclasses==["mandatory","context_only","unknown","context_only","mandatory"],fclasses


# Regression for the actual cause: 18-item classification slices hid the full
# HWP requirement from a later broken PDF quote. The deterministic classifier
# must use all official citations before declaring that a late fragment is
# an unidentified company obligation.
cross_doc=[{
 "type":"direct_production","codes":["8111189901"],
 "sourceFile":"입찰공고문.hwp",
 "sourceText":"직접생산확인증명서 세부품명 정보시스템유지관리서비스 8111189901 소지한 업체"
}]
cross_doc += [{
 "type":"joint_participation","sourceFile":"제안요청서.hwp",
 "sourceText":"공동수급체 구성원별 평가점수는 지분율에 따라 계산함 "+str(i)
} for i in range(24)]
cross_doc += [{
 "type":"direct_production","codes":[],
 "sourceFile":"입찰공고문_변환본.pdf",
 "sourceText":"직접생산확인증명서 세부품명 정보시스템유지관리서비스 세부품명번호 자리"
}]
cross_notice=dict(valid,files=[dict(valid["files"][0],clauseCandidates=cross_doc)])
cross_interpret=m.process_one("R26BK01756420:000",cross_notice,None,
                             m.rule_based_interpret,mode="rule_based")
assert cross_interpret["totalSourceCandidates"]==26
assert cross_interpret["interpretedCount"]==26
assert cross_interpret["requirements"][0]["classification"]=="mandatory"
assert cross_interpret["requirements"][-1]["classification"]=="context_only",cross_interpret["requirements"][-1]
assert cross_interpret["sourceTruncated"] is False
# Without the matching full official clause, a clipped certificate cannot be
# marked covered just because the category name is familiar.
clipped_only=dict(valid,files=[dict(valid["files"][0],clauseCandidates=cross_doc[1:])])
missing_anchor=m.process_one("R26BK01756420:001",clipped_only,None,
                             m.rule_based_interpret,mode="rule_based")
assert missing_anchor["requirements"][-1]["classification"]=="unknown"
assert missing_anchor["reviewComplete"] is False

# Real HWP conditions and PDF fragments must remain distinct.
g4_security_law=[
 {"index":0,"type":"bid_security","sourceFile":"입찰공고 원본.hwp",
  "sourceText":"8-1. 입찰보증금의 납부: 입찰보증금을 납부 하여야 합니다."},
 {"index":1,"type":"bid_security","sourceFile":"입찰공고 원본.hwp",
  "sourceText":"8-1. 입찰보증금의 납부"},
 {"index":2,"type":"bid_security","sourceFile":"입찰공고 원본.hwp",
  "sourceText":"2) 입찰공고일 이전 1년 이내에 제76조 사유로 입찰참가자격 제한을 받은 자"},
 {"index":3,"type":"bid_security","sourceFile":"입찰공고 변환본.pdf",
  "sourceText":"입찰공고일 이전 년 이내에 제 조 사유로 입찰참가자격 제한을 받은 자"},
 {"index":4,"type":"legal_exclusion","sourceFile":"입찰공고 원본.hwp",
  "sourceText":"조세포탈 등을 한 자로서 유죄판결이 확정된 날부터 2년이 지나지 아니한 자는 입찰에 참여 할 수 없습니다."},
 {"index":5,"type":"legal_exclusion","sourceFile":"입찰공고 변환본.pdf",
  "sourceText":"조세포탈 등을 한 자 로서 유죄판결이 확정된 날부터"}
]
g4_result=m.rule_based_interpret(g4_security_law)["items"]
assert [v["classification"] for v in g4_result]==[
 "mandatory","context_only","mandatory","context_only","prohibited","context_only"],g4_result
assert m.rule_based_interpret([g4_security_law[-1]])["items"][0]["classification"]=="unknown"
