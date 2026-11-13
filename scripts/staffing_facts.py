#!/usr/bin/env python3
"""Source-backed staffing facts. Headcount, work effort and recommendations stay separate.

No number is treated as a person unless its source explicitly states people.
The staff-plan requirement does not imply a specified or mandatory headcount.
"""
import re
from decimal import Decimal, InvalidOperation

ROLE_RE=re.compile(
    r'(?P<role>IT\s*PM|응용\s*SW\s*개발자|UI\s*/\s*UX\s*(?:디자이너|개발자))'
    r'\s+(?:평균|협의)\s+'
    r'(?P<months>\d{1,3}(?:\.\d+)?)\s+'
    r'(?P<rate>0(?:\.\d+)?|1(?:\.0+)?)'
    r'(?:\s+0(?:\.0+)?)?\s*$', re.I
)
TOTAL_RE=re.compile(r'총\s*투입공수.{0,50}?(?P<total>\d{1,3}(?:\.\d+)?)\s*$', re.I)
RECOMMENDED_RE=re.compile(
    r'(?:상주\s*인력|상주인력|투입\s*인력|투입인력)'
    r'.{0,45}?(?:월\s*평균|월평균)?\s*'
    r'(?P<count>[1-9]\d?)\s*명\s*이상.{0,25}(?:유지\s*)?권고', re.I
)
PLAN_MUST_RE=re.compile(
    r'투입(?:될|되는)?\s*(?:인원|인력)\s*(?:현황|구성).{0,30}(?:제시하여야|제시해야)|'
    r'투입\s*인력.{0,25}(?:구성|조직\s*체계).{0,20}(?:제시|제출)|'
    r'본\s*사업.{0,22}인력\s*구성.{0,30}제시|'
    r'유지관리\s*인력\s*요구사항.{0,30}(?:준수하여야|준수해야)', re.I
)
GENERIC_FILE_RE=re.compile(
    r'행안부\s*예규|행정안전부\s*예규|지방자치단체\s*입찰시\s*낙찰자\s*결정기준|'
    r'입찰\s*및\s*계약집행기준|입찰유의서.{0,90}계약일반조건', re.I
)
_RELATED_ROLE_NAMES=[
    ('사업관리자(PM)',re.compile(r'사업관리자\s*\n\s*\(PM\)')),
    ('사업수행관리자(PL)',re.compile(r'사업수행관리자\s*\n\s*\(PL\)')),
    ('인공지능·빅데이터 분야 전문가',re.compile(r'인공지능\s*및\s*\n\s*빅데이터\s*분야\s*\n\s*전문가')),
    ('포털SW 기능개선',re.compile(r'포털\s*SW\s*기능개선')),
    ('인프라관리',re.compile(r'인프라관리\s*\n\s*상용\s*SW')),
]

def extract_staffing_facts(text, filename, source_url=''):
    """Return bounded facts with explicit provenance, without guessing headcount."""
    if GENERIC_FILE_RE.search(str(filename or '')):
        return []
    lines=str(text or '').splitlines()
    evidence=[]
    def put(kind, lineno, source, **details):
        quote=' '.join(str(source).split())[:240]
        if not quote:return
        item={'kind':kind,'sourceFile':str(filename or '')[:140],
              'sourceLine':lineno,'sourceText':quote}
        if str(source_url).startswith('https://www.g2b.go.kr/'):
            item['sourceUrl']=source_url
        item.update(details)
        if item not in evidence:evidence.append(item)
    workload=[]
    for i,line in enumerate(lines):
        s=' '.join(line.split())
        if not s:continue
        m=ROLE_RE.search(s)
        if m and ('공내역서' in str(filename) or
                  ('투입공수' in text[:2000] and '평균임금' in text[:2000])):
            try:
                months=Decimal(m.group('months'))
                rate=Decimal(m.group('rate'))
                if not (Decimal('0')<=rate<=1 and Decimal('0')<months<=36):
                    continue
                mm=(months*rate).quantize(Decimal('.001'))
                role=' '.join(m.group('role').split())
                onsite=bool(re.search(r'상주\s*인력',s[:m.start()]))
                workload.append(mm)
                put('workload_role',i+1,s,role=role,
                    durationMonths=float(months),allocationRate=float(rate),
                    manMonths=float(mm),onsite=onsite,
                    headcount=None)
            except (InvalidOperation,ValueError):
                pass
        m=TOTAL_RE.search(s)
        if m and workload and ('공내역서' in str(filename) or '투입공수' in text[:2000]):
            value=Decimal(m.group('total'))
            summation=sum(workload,Decimal('0'))
            if abs(value-summation)<=Decimal('.001'):
                put('workload_total',i+1,s,
                    manMonths=float(value.quantize(Decimal('.001'))),
                    verifiedRoleCount=len(workload))
        r=RECOMMENDED_RE.search(s)
        if r and not re.search(r'예시|산정\s*사례|평가\s*배점',s):
            put('headcount_recommended',i+1,s,
                count=int(r.group('count')),
                minimum=True,mandatory=False,
                onsite=bool(re.search('상주',s)))
        if (PLAN_MUST_RE.search(s) and
                not re.search(r'평가\s*배점|점수|산정\s*예시',s)):
            put('staffing_plan_required',i+1,s,
                headcount=None,mandatory=True)
        if len(evidence)>=35:break
    # A source-labelled role does NOT carry a numeric headcount. These
    # definitions are not a table of committed staff numbers.
    if 'MHR-002' in text and '사업수행 인력투입 요건' in text:
        for role,pattern in _RELATED_ROLE_NAMES:
            m=pattern.search(text)
            if not m:continue
            index=text.count('\n',0,m.start())+1
            put('role_unspecified',index,m.group(0),role=role,
                headcount=None,mandatory=False)
    return evidence[:35]
