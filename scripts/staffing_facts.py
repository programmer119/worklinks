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
# These are narrow, source-quoted WORKFORCE conditions, not inferred headcounts.
# Scan every readable official RFP; avoid hardcoding tender identifiers.
STAFF_REQUIREMENT_PATTERNS=(
    ('workplace', '근무조건 협의',
     re.compile(r'발주처와.{0,48}투입\s*인력\s*근무\s*조건.{0,24}협의(?:가\s*필요|\s*필요|하여야|해야)',re.I)),
    ('expertise','FP 산정 전문가 포함',
     re.compile(r'기능\s*점수.{0,36}산정\s*가능\s*전문가.{0,22}포함',re.I)),
    ('onsite','상주인력 근무·휴가 조건',
     re.compile(r'상주\s*인력.{0,28}휴가.{0,38}(?:사전\s*승인|승인\s*받)',re.I)),
    ('pm','PM 경력·참여율 조건',
     re.compile(r'(?:사업\s*총괄\s*인력\s*\(\s*PM\s*\)|\bPM\b).{0,125}?[1-9]\d?\s*년\s*이상.{0,145}?[1-9]\d?\s*%\s*이상',re.I)),
    ('proof','건강보험 자격득실확인서 등 재직 증빙',
     re.compile(r'(?:재직\s*증명\s*서류|재직\s*증명|참여\s*인력).{0,115}?건강\s*보험\s*자격\s*득실\s*확인서',re.I)),
    ('proof','참여인력 재직·경력 증빙',
     re.compile(r'참여\s*인력.{0,95}?재직\s*증명서.{0,35}(?:첨부|제출)',re.I)),
    ('workforce','공고일 현재 참여인력 자사 소속',
     re.compile(r'참여\s*인력.{0,48}입찰\s*공고\s*일\s*현재.{0,85}(?:자사\s*인력|소속)',re.I)),
    ('plan','투입인력 현황·업무분장 제시',
     re.compile(r'투입(?:될|되는)?\s*인원\s*현황.{0,45}(?:제시|제출).{0,75}업무\s*분장',re.I)),
)


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
    # Keep one requirement per source/document and kind. Large HWPX files often
    # repeat the same clause in both flattened and table-extracted text.
    seen_requirements=set()
    for i,line in enumerate(lines):
        s=' '.join(line.split())
        if not s or len(evidence)>=33:continue
        if re.search(r'산정\s*예시|평가\s*배점|배점\s*예시',s):continue
        for requirement_type,label,pattern in STAFF_REQUIREMENT_PATTERNS:
            key=(requirement_type,label)
            if key in seen_requirements:continue
            match=pattern.search(s)
            if not match:continue
            # Center the actual matched clause, not the beginning of an HWPX
            # line that can contain several flattened table cells.
            left=max(0,match.start()-42)
            right=min(len(s),max(match.end()+52,left+160))
            quote=s[left:right]
            if match.group(0) not in quote:continue
            put('staffing_requirement',i+1,quote,requirementType=requirement_type,
                label=label,headcount=None)
            seen_requirements.add(key)
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
