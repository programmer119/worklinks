#!/usr/bin/env python3
"""Classify RFP retrieval gaps without asserting that an attachment does not exist."""
import importlib.util
from pathlib import Path
script=Path(__file__).resolve().parents[1]/'scripts/refresh_worklinks_rfp.py'
spec=importlib.util.spec_from_file_location('worklinks_rfp',script)
rfp=importlib.util.module_from_spec(spec)
spec.loader.exec_module(rfp)
orig_fetch=rfp.fetch_json
orig_download=rfp.download
try:
    def response(items,count=0,ok=True,complete=True,error=''):
        return {'attachments':{'ok':ok,'complete':complete,'items':items,
                'count':count,'error':error}}
    rfp.fetch_json=lambda _:response([],0)
    zero=rfp.process('R26BK12345678','000')
    assert zero['status']=='no_official_attachment_metadata'
    assert zero['reasonCode']=='eorder_api_zero__notice_detail_api_error'
    assert zero['reviewComplete'] is False
    rfp.fetch_json=lambda _:dict(response([],0),noticeDocuments={'ok':True,'complete':True,'items':[]})
    nofiles=rfp.process('R26BK12345678','000')
    assert nofiles['reasonCode']=='eorder_api_zero__notice_detail_zero_files'
    rfp.fetch_json=lambda _:dict(response([{'name':'RFP.hwp',
      'url':'https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/document.hwp'}],1),
      noticeDocuments={'ok':True,'complete':True,'items':[{'name':'RFP.hwp'}]})
    rfp.download=lambda _:b'not-a-hwp'
    detail=rfp.process('R26BK12345678','000')
    assert detail['files'][0]['errorCategory']=='invalid_hwp'
    rfp.fetch_json=lambda _:response([],None,False,False,'upstream_http_403')
    unauthorized=rfp.process('R26BK12345678','000')
    assert unauthorized['reasonCode']=='metadata_api_error'
    assert unauthorized['sourceError']=='upstream_http_403'
    rfp.fetch_json=lambda _:response([{'name':'제안서.docx',
         'url':'https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/invalid.docx'}],1)
    unsupported=rfp.process('R26BK12345678','000')
    assert unsupported['status']=='text_unavailable'
    assert unsupported['files'][0]['errorCategory']=='file_extract_failure' # non-ZIP test fixture
    assert rfp.legal_file({'name':'제안서.docx','url':'https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/a.docx'})
    rfp.fetch_json=lambda _:response([{'name':'제안서.hwp',
         'url':'https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/downloadRfpFile.do'}],1)
    rfp.download=lambda _:b'not-a-hwp'
    invalid=rfp.process('R26BK12345678','000')
    assert invalid['files'][0]['errorCategory']=='invalid_hwp'
    assert invalid['reviewComplete'] is False
finally:
    rfp.fetch_json=orig_fetch
    rfp.download=orig_download
# Pagination, already-checked suppression, urgency and 1468 matching priority.
orig_discovery=rfp.fetch_json
try:
    fake_date=rfp.dt.datetime.now(rfp.dt.timezone(rfp.dt.timedelta(hours=9))).date()
    deadline=fake_date.strftime('%Y%m%d')+'1700'
    rows=[
      {'bidNo':'R26BK12345601','order':'000','kind':'servc','closes':deadline,
       'bidEligibility':{'requirements':[{'codes':['1468']}]}},
      {'bidNo':'R26BK12345602','order':'000','kind':'servc','closes':deadline},
      {'bidNo':'R26BK12345603','order':'000','kind':'thng','closes':deadline},
    ]
    calls=[]
    def pages(url):
        calls.append(url)
        if 'offset=0' in url:
            return {'ok':True,'totalCount':503,'items':rows+[
               {'bidNo':'bad','order':'000','closes':deadline} for _ in range(497)]}
        if 'offset=500' in url:
            return {'ok':True,'totalCount':503,'items':[
             {'bidNo':'R26BK12345604','order':'000','kind':'servc','closes':deadline,
              'bidEligibility':{'requirements':[{'codes':['1426']}]}}
             for _ in range(3)]}
        raise AssertionError(url)
    rfp.fetch_json=pages
    prior={'R26BK12345601:000':{'classificationVersion':rfp.CLASSIFICATION_VERSION,'checkedAt':
       rfp.dt.datetime.now(rfp.dt.timezone.utc).isoformat(),'reviewComplete':False}}
    result=rfp.discover(10,prior)
    assert len(calls)==2,'discovery must request the next 500 notice page'
    assert result[0][0]=='R26BK12345604',('new matching 1426 registration should be prioritized; observed '+repr(result[:5]))
    assert all(v[0]!='R26BK01756420' for v in result),'historical fixture must not enter live notices'
    assert all(v[0]!='R26BK12345601' for v in result)
finally:
    rfp.fetch_json=orig_discovery

sample='''- 소프트웨어사업자(컴퓨터관련서비스사업)[업종코드 : 1468] 업종으로 반드시 등록한 자
- 직접생산확인증명서(세부품명: 정보시스템유지관리서비스, 세부품명번호 : 8111189901)를 소지한 자
- 제안서에는 투입인력 재직·경력·학력·자격증명서 서류 원본 또는 사본을 첨부하여야 함
- 공동수급 금지. 단독입찰만 허용
''';
c=rfp.extract_rule_candidates(sample,'공식 제안요청서.hwp')
assert any(x['type']=='industry_code' and '1468' in x['codes'] for x in c)
assert any(x['type']=='direct_production' and '8111189901' in x['codes'] for x in c)
assert any(x['type']=='staff_proof' and x['reviewStatus']=='unreviewed' for x in c)
assert all(x['documentRequiresManualFullReview'] for x in c)
# Real HWPX paragraphs must stay split; a one-line 15k XML string used to yield
# zero candidates because of the former line-length filter.
import io,zipfile
test_xml=('<root xmlns:hp="urn:hp">'+
 '<hp:p><hp:t>등록해야 하는 입찰참가자격으로 소프트웨어사업자 업종코드 1468</hp:t></hp:p>'+
 '<hp:p><hp:t>직접생산확인증명서 정보시스템개발서비스 8111159901 소지한 업체</hp:t></hp:p>'+
 '</root>').encode()
mem=io.BytesIO()
with zipfile.ZipFile(mem,'w') as archive:
 archive.writestr('Contents/section0.xml',test_xml)
split=rfp.extract('sample.hwpx',mem.getvalue())
assert '\n' in split and '1468' in split and '8111159901' in split
assert len(rfp.extract_rule_candidates(split,'sample.hwpx'))>=2
checked=rfp.audit_qualification_scan(split,rfp.extract_rule_candidates(split,'sample.hwpx'))
assert checked['sourceTextScanComplete'],checked
missed=rfp.audit_qualification_scan(
 '사업자는 입찰참가자격이 있어야 한다\n자본금 10억 이상으로 제한',
 [{'sourceText':'사업자는 입찰참가자격이 있어야 한다'}])
assert missed['sourceTextScanComplete'] is True or missed['unmatchedQualificationAnchorCount']==0
# Unknown criteria must not be marked complete when an eligible-phrase anchor is unaccounted.
unknown=rfp.audit_qualification_scan(
 '소프트웨어사업자 1468 등록한 자\n직접생산확인증명서 8111159901 소지한 업체',
 [{'sourceText':'소프트웨어사업자 1468 등록한 자'}])
assert unknown['sourceTextScanComplete'] is False
assert unknown['unmatchedQualificationAnchorCount']==1
# Reconciled PDF-wrapped evidence must not look like an unexamined rule.
wrapped='입찰 참가 자격\n소프트웨어사업자 1468 등록한 업체\n○ 공동수급 불허'
wrapped_rules=rfp.extract_rule_candidates(wrapped,'공고서.pdf')
assert any(q['type']=='joint_participation' for q in wrapped_rules)
wrapped_scan=rfp.audit_qualification_scan(wrapped,wrapped_rules)
assert wrapped_scan['unmatchedQualificationAnchorCount']==0,wrapped_scan
# A substantive clause not in the extracted citation set still blocks review.
uncovered=rfp.audit_qualification_scan('직접생산확인증명서 8111159901 소지한 업체',
 [{'sourceText':'소프트웨어사업자 1468 등록한 업체'}])
assert uncovered['unmatchedQualificationAnchorCount']==1

# All manifest documents are represented, even if the bounded downloader is
# unable to extract an unsupported attachment.
try:
 rfp.fetch_json=lambda _:dict(response([{'name':'RFP.pdf','url':'https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/a.pdf'},
    {'name':'견적.xlsx','url':'https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/a.xlsx'}],2),
    noticeDocuments={'ok':True,'complete':True,'items':[]})
 rfp.download=lambda _:b'not-a-pdf'
 coverage=rfp.process('R26BK12345678','000')
 assert len(coverage['files'])==2 and coverage['unreadableDocumentCount']==2
 assert coverage['reviewComplete'] is False and coverage['requiredConditionsComplete'] is False
finally:
 rfp.fetch_json=orig_fetch
 rfp.download=orig_download

# Verify official OOXML text extraction, including numeric sheet cell codes.
import io,zipfile
def office_xml(name,member,xml,extra=None):
 m=io.BytesIO()
 with zipfile.ZipFile(m,'w') as z:
  z.writestr(member,xml)
  for k,v in (extra or {}).items():z.writestr(k,v)
 return rfp.extract(name,m.getvalue())
doc=office_xml('notice.docx','word/document.xml',
 '<w:document xmlns:w="urn:w"><w:body><w:p><w:r><w:t>입찰참가자격 업종코드 1468 등록한 사업자</w:t></w:r></w:p></w:body></w:document>')
assert '1468' in doc and '\n' not in doc
sheet=office_xml('conditions.xlsx','xl/worksheets/sheet1.xml',
 '<worksheet><sheetData><row><c t="s"><v>0</v></c><c><v>8111189901</v></c></row></sheetData></worksheet>',
 {'xl/sharedStrings.xml':'<sst><si><t>직접생산확인증명서 정보시스템유지관리서비스</t></si></sst>'})
assert '직접생산확인증명서 정보시스템유지관리서비스 8111189901' in sheet
slide=office_xml('requirements.pptx','ppt/slides/slide1.xml',
 '<p:sld xmlns:p="urn:p" xmlns:a="urn:a"><a:p><a:r><a:t>중소기업확인서 소지 필수</a:t></a:r></a:p></p:sld>')
assert '중소기업확인서 소지 필수' in slide

print('WORKLINKS_RFP_FAILURE_CLASSIFICATION=PASS')
