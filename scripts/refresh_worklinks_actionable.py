#!/usr/bin/env python3
"""WorkLinks: actionable Changcom bid shortlist from the complete public G2B index.

This is a *basic industry and service-fit screening*, NEVER legal bid approval.
Unknown/ambiguous evidence is retained in review buckets, not called ineligible.
No model, third-party paid API, local production database access or secrets.
"""
import argparse
import datetime as dt
import json
import pathlib
import re
import urllib.parse
import urllib.request

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/'startup-support/changcom-actionable.json'
RFP=ROOT/'startup-support/rfp-coverage-index.json'
API='https://api-suaveforge.suaveforge.com:18458/api/g2b'
BIZNO='1308185973'
KST=dt.timezone(dt.timedelta(hours=9))
SVC_PRODUCT=re.compile(r'8111159901|8111189901|8111179901|8111239901|정보시스템(?:개발|유지관리)서비스',re.I)
CORE=re.compile(
    r'소프트웨어|S/?W|정보시스템|정보화|전산|웹(?:사이트|서비스|포털)?|홈페이지|'
    r'어플|응용프로그램|모바일|앱(?:개발)?|클라우드|플랫폼|데이터(?:베이스|플랫폼)?|'
    r'빅데이터|인공지능|AI|챗봇|API|OCR|전자(?:결재|문서|인사)|통합\s*(?:관리|운영|시스템)|IT서비스',re.I)
ACTION=re.compile(
    r'개발|구축|고도화|운영|유지\s*보수|유지\s*관리|기능\s*개선|'
    r'시스템\s*전환|서비스\s*고도화|위탁\s*운영|재구축|개편|리뉴얼|기술지원',re.I)
# These describe physical works / equipment / site surveys, not an SW delivery.
NON_CORE=re.compile(
    r'건축|토목|가스시설|전기공사|방수공사|도로공사|산업단지|하수관로|상수관로|'
    r'차집관로|하수처리|지하시설물\s*(?:DB|데이터베이스)|GIS\s*DB|영상감시\s*장치|'
    r'CCTV\s*(?:설치|조사)|측량|공간정보|기구,\s*전장|기계(?:설비|정비)|'
    r'장비(?:구매|정비|수리|유지)|서버\s*구매|PC\s*구매|관광|출장|'
    r'행사\s*(?:대행|운영)|교육\s*(?:운영|용역)|연수|설계\s*용역|'
    r'시제품\s*(?:제작|생산)|라이선스\s*(?:갱신|구매)|솔루션\s*구매',re.I)
SOFTWARE_GOODS=re.compile(
    r'(?:SW|S/W|소프트웨어|응용프로그램|앱|프로그램)\s*(?:신규\s*)?(?:개발|구축|고도화)'
    r'|(?:개발|고도화)\s*(?:용역|업무)',re.I)

def get_json(path):
    url=API+path
    request=urllib.request.Request(url,headers={
        'User-Agent':'WorkLinks-Changcom-Actionable-ReadOnly/1.0','Accept':'application/json'})
    with urllib.request.urlopen(request,timeout=35) as response:
        raw=response.read(3_500_000)
        if len(raw)>=3_500_000:raise ValueError('public_g2b_page_too_large')
    result=json.loads(raw)
    if not isinstance(result,dict) or result.get('ok') is not True:
        raise ValueError('public_g2b_response_not_complete')
    return result

def parse_close(value):
    value=str(value or '').strip()
    if not value:return None
    v=value.replace(' ','T')
    try:
        out=dt.datetime.fromisoformat(v.replace('Z','+00:00'))
        return out.replace(tzinfo=KST) if out.tzinfo is None else out.astimezone(KST)
    except ValueError:pass
    digits=re.sub(r'\D','',value)
    if len(digits)>=12:
        try:return dt.datetime.strptime(digits[:14] if len(digits)>=14 else digits[:12],
                          '%Y%m%d%H%M%S' if len(digits)>=14 else '%Y%m%d%H%M').replace(tzinfo=KST)
        except ValueError:pass
    return None

def canonical(row):
    number=str(row.get('bidNo') or '').strip()
    order=str(row.get('order') or '0').strip()
    if not re.fullmatch(r'(?:R\d{2}BK\d{8}|\d{11})',number):return None
    if not re.fullmatch(r'\d{1,3}',order):return None
    return number,order.zfill(3)

def all_indexed(fetch=get_json):
    """Fetch all pages; an interrupted API response must NOT publish a partial shortlist."""
    rows=[]
    totals=[]
    for offset in range(0,100000,500):
        data=fetch('/saved?sw=1&limit=500&offset='+str(offset))
        total=int(data.get('totalCount') or 0)
        values=data.get('items')
        if not isinstance(values,list):raise ValueError('missing_saved_items_page')
        totals.append(total)
        rows.extend(values)
        if offset+len(values)>=total:break
        if len(values)!=500:raise ValueError('short_saved_page_before_end')
    else:raise ValueError('saved_index_page_limit_reached')
    # Dynamic crawler may append a few rows mid-fetch. Never claim a perfect
    # full crawl if the API dataset moved while pages were being fetched.
    if not totals or not rows or len(rows)<min(totals)-500:
        raise ValueError('saved_index_incomplete')
    return rows, max(totals)

def active_codes(company):
    if company.get('found') is not True or company.get('complete') is not True:
        raise ValueError('company_official_registry_unavailable')
    # The company API may contain a code without a known current status.
    # Treat that as unknown, not as a valid license or a definite absence.
    current=set()
    uncertain=set()
    for record in company.get('industries') or []:
        code=str(record.get('code') or '').strip()
        status=str(record.get('status') or '').strip()
        if not re.fullmatch(r'\d{4}',code):continue
        if status=='정상':current.add(code)
        elif not status:uncertain.add(code)
    if not current:raise ValueError('company_active_industry_registry_empty')
    return current,uncertain

def scope(row):
    title=str(row.get('title') or '')
    kind=str(row.get('kind') or '')
    subject=str(row.get('purchsObjPrdctList') or '')
    if kind=='servc':
        if NON_CORE.search(title):return 'other_or_specialist'
        if (CORE.search(title) and ACTION.search(title)) or SVC_PRODUCT.search(subject):
            return 'software_service'
        return 'scope_review'
    if kind=='thng' and not NON_CORE.search(title) and SOFTWARE_GOODS.search(title):
        return 'software_goods_review'
    return 'other_or_specialist'

def industry_evidence(row,registered,uncertain):
    bid=row.get('bidEligibility')
    if not isinstance(bid,dict) or bid.get('ok') is not True or bid.get('complete') is not True:
        return ('official_license_unavailable',[],[],[],[])
    rules=bid.get('requirements')
    if not isinstance(rules,list):
        return ('official_license_unavailable',[],[],[],[])
    codes=[]
    unknown_rule=False
    for rule in rules:
        if not isinstance(rule,dict):unknown_rule=True;continue
        items=rule.get('codes')
        if not isinstance(items,list):unknown_rule=True;continue
        if not items:unknown_rule=True
        codes.extend(str(code) for code in items if re.fullmatch(r'\d{4}',str(code)))
    codes=list(dict.fromkeys(codes))
    known=[code for code in codes if code in registered]
    unclear=[code for code in codes if code in uncertain]
    not_registered=[code for code in codes if code not in registered and code not in uncertain]
    if not rules:return ('no_license_restriction_detected',codes,known,unclear,not_registered)
    if unknown_rule or not codes:return ('official_license_ambiguous',codes,known,unclear,not_registered)
    if not_registered or unclear:
        # The official grouping might use OR, exceptions or subcontractors.
        # This only flags a conflict; it is NOT a legal disqualification.
        return ('industry_rule_conflict_review',codes,known,unclear,not_registered)
    return ('published_industry_codes_match',codes,known,unclear,not_registered)

def extract_rfp_index(path=RFP):
    if not path.exists():return {}
    try:
        d=json.loads(path.read_text(encoding='utf-8'))
        return d.get('byNotice') if isinstance(d.get('byNotice'),dict) else {}
    except (OSError,ValueError):return {}

def latest_revisions(rows):
    dedup={}
    for row in rows:
        ident=canonical(row)
        if ident is None:continue
        no,order=ident
        if no not in dedup or int(order)>int(dedup[no]['_order']):
            dedup[no]={**row,'_order':order}
    return list(dedup.values())

def build(rows,total_count,company,now=None,rfp=None):
    now=now or dt.datetime.now(KST)
    if now.tzinfo is None:now=now.replace(tzinfo=KST)
    registered,uncertain=active_codes(company)
    rfp=rfp or {}
    selected=latest_revisions(rows)
    groups={'open':0,'expired':0,'deadline_unknown':0,'openService':0,
        'softwareService':0,'publishedIndustryAligned':0,'servicePendingReview':0,
        'serviceCodeConflict':0,'otherOrSpecialist':0,'softwareGoodsReview':0}
    bids=[]
    for row in selected:
        end=parse_close(row.get('closes'))
        if end is None:
            groups['deadline_unknown']+=1
            continue
        if end<=now:
            groups['expired']+=1
            continue
        groups['open']+=1
        if row.get('kind')=='servc':groups['openService']+=1
        purpose=scope(row)
        if purpose=='other_or_specialist':
            groups['otherOrSpecialist']+=1
            continue
        if purpose=='scope_review':
            groups['otherOrSpecialist']+=1
            continue
        if purpose=='software_goods_review':groups['softwareGoodsReview']+=1
        if purpose=='software_service':groups['softwareService']+=1
        screening,codes,matched,unclear,missing=industry_evidence(row,registered,uncertain)
        if purpose=='software_service':
            if screening=='published_industry_codes_match':
                groups['publishedIndustryAligned']+=1
            else:
                groups['servicePendingReview']+=1
                if screening=='industry_rule_conflict_review':
                    groups['serviceCodeConflict']+=1
        no,order=canonical(row)
        key=no+':'+order
        source=rfp.get(key) if isinstance(rfp.get(key),dict) else {}
        scanned=source.get('status')=='text_extracted_requires_review'
        hours=(end-now).total_seconds()/3600
        days=int((hours+23.999)//24)
        subject=str(row.get('purchsObjPrdctList') or '')
        has_svc=bool(SVC_PRODUCT.search(subject))
        budget=str(row.get('budget') or '').strip()
        price=int(re.sub(r'\D','',budget) or 0)
        score=(100 if screening=='published_industry_codes_match' else
               50 if screening=='no_license_restriction_detected' else
               25 if screening=='official_license_unavailable' else
               15 if screening=='official_license_ambiguous' else 0)
        score+=20 if has_svc else 0
        score+=10 if 48<=hours<=14*24 else 0
        score+=8 if scanned else 0
        score+=5 if 0<price<=300_000_000 else 0
        if hours<24:score-=12
        if price>=3_000_000_000:score-=12
        if purpose=='software_goods_review':score-=30
        bids.append({
            'bidNo':no,'order':order,'title':str(row.get('title') or ''),
            'org':str(row.get('org') or row.get('agency') or ''),
            'closes':end.isoformat(timespec='minutes'),
            'hoursLeft':round(hours,1),'daysLeft':days,
            'budget':budget,'kind':str(row.get('kind') or ''),
            'scope':purpose,'screening':screening,'requiredCodes':codes,
            'registeredCodesMatched':matched,'codesUnknownStatus':unclear,
            'codesNotInCurrentRegistry':missing,
            'industryCheckedAt':str((row.get('bidEligibility') or {}).get('checkedAt') or ''),
            'rfpTextScanned':scanned,
            'rfpScanStatus':str(source.get('status') or 'not_scanned'),
            'rfpCheckedAt':str(source.get('checkedAt') or ''),
            'sourceUrl':('https://www.g2b.go.kr/link/PNPE027_01/single/?'+
                         urllib.parse.urlencode({'bidPbancNo':no,'bidPbancOrd':order})),
            'priorityScore':score,
            'eligibilityVerified':False,
            'needsFullNoticeReview':True
        })
    order={'published_industry_codes_match':0,
           'no_license_restriction_detected':1,
           'official_license_ambiguous':2,
           'official_license_unavailable':3,
           'industry_rule_conflict_review':4}
    bids.sort(key=lambda x:(0 if x['scope']=='software_service' else 1,
        order.get(x['screening'],5),-x['priorityScore'],x['closes'],x['bidNo']))
    observed=len(rows)
    return {
        'ok':True,'generatedAt':now.isoformat(timespec='seconds'),
        'company':str((company.get('company') or {}).get('name') or '창컴정보통신 주식회사')
                  if isinstance(company.get('company'),dict) else str(company.get('company') or ''),
        'bizno':BIZNO,'companyRegistryCheckedAt':company.get('checkedAt'),
        'activeIndustryCodes':sorted(registered),'industryStatusUncertainCodes':sorted(uncertain),
        'officialSource':API+'/saved?sw=1',
        'counts':{'indexedSWTotal':total_count,'indexRowsFetched':observed,
                  'latestRevisions':len(selected),**groups},
        'statusDefinition':{
            'published_industry_codes_match':'공식 면허제한 API 등록코드와 업체 정상등록코드 일치 · 기타 참가조건 미확정',
            'no_license_restriction_detected':'면허제한 API 0건 · 원문 추가조건 확인 필요',
            'official_license_unavailable':'면허제한 API 미수집/오류 · 적격·부적격 아님',
            'official_license_ambiguous':'제한 업종 관계·코드 미확정 · 원문 확인',
            'industry_rule_conflict_review':'현 등록업종 외 코드 포함 · 원문 AND/OR·예외 확인 전 제외 금지'},
        'limitations':'기본 등록업종·SW 업무분야만 대조. 직접생산·기업규모·지역·경력·실적·RFP 원문·정정공고 추가조건은 개별 확인. 적격 확정·낙찰 확률 아님.',
        'bids':bids
    }

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default=str(OUT))
    args=parser.parse_args()
    rows,count=all_indexed()
    company=get_json('/company?bizno='+BIZNO)
    snapshot=build(rows,count,company,rfp=extract_rfp_index())
    c=snapshot['counts']
    if c['indexedSWTotal']<100 or c['softwareService']<1:
        raise SystemExit('LIVE_G2B_DATA_NOT_CREDIBLE_REFUSING_EMPTY_OUTPUT')
    path=pathlib.Path(args.output)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(snapshot,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
    print('WORKLINKS_ACTIONABLE_CORPUS',json.dumps(c,ensure_ascii=False))
    print('WORKLINKS_PRIORITIZED_TOP',json.dumps([
       {'no':b['bidNo'],'title':b['title'],'screening':b['screening'],
        'daysLeft':b['daysLeft']} for b in snapshot['bids'][:12]],ensure_ascii=False))
if __name__=='__main__':
    main()
