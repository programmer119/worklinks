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
NOTICE_REVIEWS=ROOT/'startup-support/changcom-bid-review.json'
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


def load_official_award_cache(fetch=get_json):
    """Official historic participation counts, indexed by exact old bid notice.

    Never infer a competitor count from a missing cache row, zero, or an
    unrelated award. The recurring_projects worker independently verifies
    comparable agency + title before its history may be used.
    """
    try:
        first=fetch('/award-cache?limit=200&offset=0')
        if not first.get('installed'):return {}
        total=int(first.get('totalCount') or 0)
        if total<0 or total>10000:return {}
        rows=list(first.get('records') or [])
        for offset in range(200,total,200):
            page=fetch('/award-cache?limit=200&offset='+str(offset))
            if page.get('ok') is not True or page.get('installed') is not True:
                return {}
            rows.extend(page.get('records') or [])
        found={}
        for row in rows:
            if not isinstance(row,dict):continue
            no=str(row.get('bidNo') or '')
            count=row.get('count')
            if not re.fullmatch(r'(?:R\d{2}BK\d{8}|\d{11})',no):continue
            try:num=int(count)
            except (ValueError,TypeError):continue
            if not 1<=num<=1000000:continue
            found[no]={'participants':num,'winner':str(row.get('winner') or ''),
                       'awardAmount':row.get('amount'),
                       'awardRate':row.get('rate'),
                       'verifiedAt':str(row.get('verifiedAt') or '')}
        return found
    except (ValueError,OSError,KeyError,TypeError,RuntimeError,TimeoutError):
        return {}

def comparable_competition(row,awards):
    """Past matched bids only: not present-day odds or a guaranteed low bid."""
    history=row.get('repeatHistory')
    if not isinstance(history,list):return []
    results=[]
    for past in history:
        if not isinstance(past,dict) or past.get('verified') is not True:continue
        no=str(past.get('bidNo') or '')
        if no not in awards:continue
        year=past.get('year')
        try:past_year=int(year)
        except (ValueError,TypeError):continue
        if not 2022<=past_year<=2026:continue
        item=awards[no]
        results.append({'pastBidNo':no,'year':past_year,'pastTitle':str(past.get('title') or ''),
                        'participants':item['participants'],'winner':item['winner'],
                        'awardAmount':item['awardAmount'],'awardRate':item['awardRate'],
                        'verifiedAt':item['verifiedAt'],
                        'source':'나라장터 과거 낙찰정보·유사 공고번호 대조'})
    return results[:3]

def load_verified_reviews(path=NOTICE_REVIEWS):
    """Human-checked notice-source observations. Never imply legal approval."""
    try:
        data=json.loads(path.read_text(encoding='utf-8'))
        by=data.get('byNotice') if isinstance(data,dict) else None
        return by if isinstance(by,dict) else {}
    except (OSError,ValueError,TypeError):
        return {}

def notice_review(key,record,company):
    """Validate any geographic mismatch against current complete official registry."""
    if not isinstance(record,dict) or record.get('bidNo')+':'+str(record.get('order'))!=key:
        return {}
    output=dict(record)
    rawstate=record.get('state')
    if rawstate=='explicit_mandatory_region_mismatch':
        city=str((record.get('mandatory') or {}).get('regionCity') or '')
        firm=company.get('company') if isinstance(company.get('company'),dict) else {}
        address=str(firm.get('regionName') or '')+' '+str(firm.get('address') or '')
        if not (company.get('complete') is True and city and address.strip()):
            output['state']='regional_eligibility_unverified'
        elif city in address:
            output['state']='regional_eligibility_recheck'
        else:
            output['state']='explicit_mandatory_region_mismatch'
            output['officialRegistryCity']=str(firm.get('regionName') or '')
    output['finalEligibilityCertified']=False
    return output

def latest_revisions(rows):
    dedup={}
    for row in rows:
        ident=canonical(row)
        if ident is None:continue
        no,order=ident
        if no not in dedup or int(order)>int(dedup[no]['_order']):
            dedup[no]={**row,'_order':order}
    return list(dedup.values())

def build(rows,total_count,company,now=None,rfp=None,awards=None,reviews=None):
    now=now or dt.datetime.now(KST)
    if now.tzinfo is None:now=now.replace(tzinfo=KST)
    registered,uncertain=active_codes(company)
    rfp=rfp or {}
    awards=awards or {}
    reviews=reviews or {}
    selected=latest_revisions(rows)
    groups={'open':0,'expired':0,'deadline_unknown':0,'openService':0,
        'softwareService':0,'publishedIndustryAligned':0,'servicePendingReview':0,
        'serviceCodeConflict':0,'otherOrSpecialist':0,'softwareGoodsReview':0,
        'unknownDeadlineRelevant':0}
    bids=[]
    for row in selected:
        end=parse_close(row.get('closes'))
        deadline_unknown=end is None
        if deadline_unknown:
            groups['deadline_unknown']+=1
        elif end<=now:
            groups['expired']+=1
            continue
        else:
            groups['open']+=1
            if row.get('kind')=='servc':groups['openService']+=1
        purpose=scope(row)
        if purpose=='other_or_specialist':
            groups['otherOrSpecialist']+=1
            continue
        if purpose=='scope_review':
            groups['otherOrSpecialist']+=1
            continue
        if deadline_unknown:
            groups['unknownDeadlineRelevant']+=1
        else:
            if purpose=='software_goods_review':groups['softwareGoodsReview']+=1
            if purpose=='software_service':groups['softwareService']+=1
        screening,codes,matched,unclear,missing=industry_evidence(row,registered,uncertain)
        if purpose=='software_service' and not deadline_unknown:
            if screening=='published_industry_codes_match':
                groups['publishedIndustryAligned']+=1
            else:
                groups['servicePendingReview']+=1
                if screening=='industry_rule_conflict_review':
                    groups['serviceCodeConflict']+=1
        no,order=canonical(row)
        key=no+':'+order
        human=notice_review(key,reviews.get(key),company)
        source=rfp.get(key) if isinstance(rfp.get(key),dict) else {}
        evidence=source.get('changcomClauseEvidence')
        if not isinstance(evidence,dict):evidence={}
        clauses=evidence.get('clauseCandidates')
        if not isinstance(clauses,dict):clauses={}
        cited_types={str(t):len(v) for t,v in clauses.items() if isinstance(v,list)}
        cited_documents=evidence.get('files') if isinstance(evidence.get('files'),list) else []
        historical=comparable_competition(row,awards)
        scanned=source.get('status')=='text_extracted_requires_review'
        hours=(end-now).total_seconds()/3600 if end is not None else None
        days=int((hours+23.999)//24) if hours is not None else None
        subject=str(row.get('purchsObjPrdctList') or '')
        has_svc=bool(SVC_PRODUCT.search(subject))
        budget=str(row.get('budget') or '').strip()
        price=int(re.sub(r'\D','',budget) or 0)
        score=(100 if screening=='published_industry_codes_match' else
               50 if screening=='no_license_restriction_detected' else
               25 if screening=='official_license_unavailable' else
               15 if screening=='official_license_ambiguous' else 0)
        score+=20 if has_svc else 0
        score+=10 if hours is not None and 48<=hours<=14*24 else 0
        score+=8 if scanned else 0
        score+=5 if 0<price<=300_000_000 else 0
        # Practical contract value is distinct from minimum legal registration.
        # Never delete a candidate based on these commercial-fit indicators.
        title=str(row.get('title') or '')
        if re.search(r'운용장비|보존.?복원.*장비|장비.*유지|마을방송|'
                     r'정보통신시설|CCTV|스마트기기',title,re.I):
            score-=35
        elif re.search(r'ISMP|ISP|정보화전략|컨설팅|전략.*수립',title,re.I):
            score-=16
        elif re.search(r'유지\s*관리|유지\s*보수|유지\s*운영|'
                       r'시스템.*운영|홈페이지.*관리',title,re.I):
            score+=16
        elif re.search(r'개발|고도화|기능\s*개선|재구축|'
                       r'데이터\s*이관|연계',title,re.I):
            score+=12
        if 50_000_000<=price<=300_000_000:score+=12
        elif price>1_000_000_000:score-=22
        if hours is not None and hours<24:score-=18
        if deadline_unknown:score-=60
        if price>=3_000_000_000:score-=12
        if purpose=='software_goods_review':score-=30
        bids.append({
            'bidNo':no,'order':order,'title':str(row.get('title') or ''),
            'org':str(row.get('org') or row.get('agency') or ''),
            'closes':end.isoformat(timespec='minutes') if end is not None else None,
            'deadlineState':'unknown' if deadline_unknown else 'open',
            'hoursLeft':round(hours,1) if hours is not None else None,'daysLeft':days,
            'budget':budget,'kind':str(row.get('kind') or ''),
            'scope':purpose,'screening':screening,'requiredCodes':codes,
            'registeredCodesMatched':matched,'codesUnknownStatus':unclear,
            'codesNotInCurrentRegistry':missing,
            'industryCheckedAt':str((row.get('bidEligibility') or {}).get('checkedAt') or ''),
            'rfpTextScanned':scanned,
            'rfpScanStatus':str(source.get('status') or 'not_scanned'),
            'rfpCheckedAt':str(source.get('checkedAt') or ''),
            'officialClauseEvidence':evidence,
            'originalRequirementTypes':cited_types,
            'originalSourceDocumentCount':len(cited_documents),
            'historicalCompetition':historical,'reviewedNotice':human,
            'precheckedMandatoryClauses':bool(human),
            'confirmedRegionalMismatch':human.get('state')=='explicit_mandatory_region_mismatch',
            'competitionVerified':bool(historical),'costVerified':False,
            'personnelAndScopeVerified':False,'proposalReady':False,
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
    bids.sort(key=lambda x:(2 if x['deadlineState']=='unknown' else
        0 if x['scope']=='software_service' else 1,
        order.get(x['screening'],5),-x['priorityScore'],x['closes'] or '9999',x['bidNo']))
    observed=len(rows)
    tracked=len(bids)
    progress={
        'reviewTarget':tracked,
        'precheckedNoticeRequirements':sum(x['precheckedMandatoryClauses'] for x in bids),
        'explicitMandatoryMismatch':sum(x['confirmedRegionalMismatch'] for x in bids),
        'industryBasicMatched':sum(x['screening']=='published_industry_codes_match'
                                   for x in bids),
        'rfpTextScanned':sum(x['rfpTextScanned'] for x in bids),
        'citableRfpExtracts':sum(bool(x['originalRequirementTypes']) for x in bids),
        'fullLegalEligibilityVerified':sum(x['eligibilityVerified'] for x in bids),
        'executionFeasibilityVerified':sum(x['personnelAndScopeVerified'] for x in bids),
        'historicalCompetitionVerified':sum(x['competitionVerified'] for x in bids),
        'costProfitabilityVerified':sum(x['costVerified'] for x in bids),
        'proposalReadyVerified':sum(x['proposalReady'] for x in bids)
    }
    return {
        'ok':True,'generatedAt':now.isoformat(timespec='seconds'),
        'company':str((company.get('company') or {}).get('name') or '창컴정보통신 주식회사')
                  if isinstance(company.get('company'),dict) else str(company.get('company') or ''),
        'bizno':BIZNO,'companyRegistryCheckedAt':company.get('checkedAt'),
        'activeIndustryCodes':sorted(registered),'industryStatusUncertainCodes':sorted(uncertain),
        'officialSource':API+'/saved?sw=1','verificationProgress':progress,
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
    snapshot=build(rows,count,company,rfp=extract_rfp_index(),
                   awards=load_official_award_cache(),reviews=load_verified_reviews())
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
