#!/usr/bin/env python3
"""Exact original-200 audit from bounded official G2B RFP excerpts.
This does NOT mark a bidder legally qualified, nor infer absent restrictions.
"""
import csv
import datetime as dt
import json
from collections import Counter
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
AUDIT=ROOT/'startup-support/audits'
ORIG=AUDIT/'changcom-200-screening-20261110.csv'
PERSON=AUDIT/'changcom-200-personnel-blockers-20261110.csv'
INDEX=ROOT/'startup-support/rfp-coverage-index.json'
OUT=AUDIT/'changcom-200-official-evidence-20261111.csv'
REPORT=AUDIT/'changcom-200-official-evidence-20261111.md'

def load_rows(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))

def norm(text):
    return ' '.join(str(text or '').split())

def link_for(key):
    no,ordn=key.split(':')
    return 'https://www.g2b.go.kr/link/PNPE027_01/single/?bidPbancNo='+no+'&bidPbancOrd='+ordn

def source_clauses(record):
    evidence=record.get('changcomClauseEvidence') or {}
    rules=evidence.get('clauseCandidates') or {}
    clauses=[]
    for typ,arr in rules.items():
        for item in arr or []:
            if not isinstance(item,dict):continue
            clauses.append({
                'type':typ,
                'text':norm(item.get('text'))[:320],
                'url':str(item.get('url') or '')[:600],
                'sourceFile':str(item.get('sourceFile') or '')[:150]})
    return clauses

PATTERNS={
    '하도급불허_문구':re.compile(r'하도급\s*(?:계약)?\s*(?:을|은)?\s*(?:불허|불가|금지)|하도급.{0,10}허용하지\s*않',re.I),
    '하도급승인_문구':re.compile(r'하도급.{0,15}(?:사전\s*승인|허용|가능|계획서)',re.I),
    '사전재직_문구':re.compile(r'공고(?:일|일자).{0,55}(?:재직|소속)|(?:재직|소속).{0,55}공고(?:일|일자)|[136]\s*개월.{0,15}(?:재직|근무)',re.I),
    '상주_문구':re.compile(r'(?:전담\s*)?상주.{0,24}(?:인력|기술자|개발자|필수|의무)|(?:인력|기술자|개발자).{0,24}상주',re.I),
    '전원정규직_문구':re.compile(r'(?:투입인력|수행인력|핵심인력|전원).{0,30}(?:정규직|입찰자\s*소속)|(?:정규직|입찰자\s*소속).{0,25}(?:인력|개발자)',re.I),
    '실적증빙_문구':re.compile(r'수행\s*실적|유사\s*사업\s*실적|실적\s*증명|실적\s*요건',re.I),
    '공동수급_문구':re.compile(r'공동\s*(?:수급|이행|계약)|분담\s*이행',re.I),
    '직생_문구':re.compile(r'직접\s*생산|8111\d{6}',re.I),
}
SEVERE=['하도급불허_문구','사전재직_문구','전원정규직_문구','상주_문구']
FIELDS=['원본순위','공고번호','공고명','마감(KST)','예산(원)','누적추출상태','공식첨부수','텍스트판독첨부','미판독첨부','공식원문발췌수','외부개발자기존판정','재직/하도급위험_발췌탐지','탐지신호','주요원문발췌(맥락은원본확인)','공식파일링크','공고링크','검증상태']

def main():
    base=load_rows(ORIG)
    staff=load_rows(PERSON)
    if len(base)!=200 or len(staff)!=200:raise RuntimeError('original_200_missing')
    staff_by={r['공고번호']:r for r in staff}
    ids=[r['공고번호'] for r in base]
    if len(set(ids))!=200 or set(staff_by)!=set(ids):raise RuntimeError('original_200_membership_changed')
    cumulative=json.loads(INDEX.read_text(encoding='utf-8'))
    coverage=cumulative.get('byNotice') or {}
    result=[]
    for pos,src in enumerate(base,1):
        key=src['공고번호']
        if int(src['순위'])!=pos:raise RuntimeError('original_order_changed_'+key)
        info=coverage.get(key) or {}
        clauses=source_clauses(info)
        existing=staff_by[key]
        snippets=[norm(src.get('자료확인근거구절(발췌)'))]
        snippets+=[norm(existing.get('발췌 인사요건'))]
        snippets+=[c['text'] for c in clauses]
        snippets=[s for s in snippets if s]
        tags=[]
        matched=[]
        for name,pattern in PATTERNS.items():
            hits=[s for s in snippets if pattern.search(s)]
            if hits:
                tags.append(name)
                if name in SEVERE:matched.extend(hits[:2])
        orig_person=existing.get('개인참여 판정') or ''
        if orig_person in ('현 방식 직접 참여 불가 위험','역할·고용형태 변경 필요'):
            tags.append('기존인력위험심사')
        file_count=info.get('attachmentManifestCount')
        readable=int(info.get('readableDocumentCount') or 0)
        unreadable=int(info.get('unreadableDocumentCount') or 0)
        summary=' | '.join(matched[:3])[:900]
        urls=[c['url'] for c in clauses if c['url']]
        urls=list(dict.fromkeys(urls))
        result.append({
            '원본순위':pos,'공고번호':key,'공고명':src['공고명'],
            '마감(KST)':src['투찰마감(KST)'],'예산(원)':src['배정예산(원)'],
            '누적추출상태':info.get('status') or '증빙누락',
            '공식첨부수':file_count if file_count is not None else '',
            '텍스트판독첨부':readable,'미판독첨부':unreadable,
            '공식원문발췌수':len(clauses),
            '외부개발자기존판정':orig_person,
            '재직/하도급위험_발췌탐지': '발췌 문구 확인 필요' if any(k in tags for k in SEVERE) else '명시적 문구 미검출(없음 뜻 아님)',
            '탐지신호':'; '.join(sorted(set(tags))),
            '주요원문발췌(맥락은원본확인)':summary,
            '공식파일링크': ' ; '.join(urls[:3]) or src.get('대표 첨부 원문') or '',
            '공고링크':link_for(key),'검증상태':'텍스트기반 사전검토만 완료 / 최종 적격 미확정'
        })
    with OUT.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(result)
    stats=Counter(r['누적추출상태'] for r in result)
    unread=sum(int(r['미판독첨부'] or 0)>0 for r in result)
    legal_zero=sum(r['검증상태']!='텍스트기반 사전검토만 완료 / 최종 적격 미확정' for r in result)
    by_tag=Counter()
    for r in result:
        for tag in filter(None,r['탐지신호'].split('; ')):
            by_tag[tag]+=1
    # Put potentially surprising conflicts first, rather than assuming
    # "no signal" means the notice is restriction-free.
    needs=[r for r in result if any(x in r['탐지신호'] for x in ('하도급불허_문구','사전재직_문구','전원정규직_문구'))]
    md=[
        '# 창컴 원본 200건: 공식 RFP 발췌 기반 물리적 제약 재점검',
        '',
        '**고정 대상:** 2026-11-10 최초 200개 공고번호와 순위 변경 없음.',
        '**검토 범위:** 누적 추출 인덱스에 저장된 공식 첨부 발췌·기존 인력 조사. 법적 최종심사 아님.',
        '',
        f'- 총 {len(result)}건, 원문 추출 성공 상태 {stats.get("text_extracted_requires_review",0)}건, 기타 상태 {len(result)-stats.get("text_extracted_requires_review",0)}건.',
        f'- 미판독 첨부가 1개 이상 확인된 공고 {unread}건 (원문 전문을 전부 검토했다고 볼 수 없음).',
        '- **최종 투찰 적격 확인 0건.** 키워드 미검출을 제약 부재로 판정하지 않음.',
        '',
        '## 제한·자격 관련 발췌 검출 건수 (중복 포함)',
        '',
        '| 검출 항목 | 건수 |',
        '|---|---:|',
    ]
    md.extend(f'| {k} | {v} |' for k,v in sorted(by_tag.items()))
    md.extend([
        '',
        '## 충돌 문구가 검출된 대표 공고 (원문 필수 대조)',
        '',
        '| 원본순위 | 공고 | 검출 | 인력 조사 |',
        '|---:|---|---|---|',
    ])
    for item in needs[:35]:
        md.append(f'| {item["원본순위"]} | [{item["공고번호"]}]({item["공고링크"]}) | {item["탐지신호"].replace("|","/")} | {item["외부개발자기존판정"]} |')
    md.extend([
        '',
        '## 창컴 협의에 적용할 판정 원칙',
        '',
        '- 공고일 이전 재직 요구가 PM에만 해당한다면 창컴 기존 PM 대체 가능성 검토.',
        '- 개발자 본인의 사전 재직 의무와 제출 대리인의 재직서류를 혼동하지 않음.',
        '- 하도급 불허 문구는 실제 허용범위와 원도급 직접 수행 의무를 확인하기 전 외부개발 구조 위험으로 취급.',
        '- 부속서/정정공고 중 아직 읽히지 않은 첨부가 있으면 안전한 공고라고 결론내리지 않음.',
        '- 사업성은 실제 제안인력·일정·기술스택·실적·이익을 따로 검토해야 함.',
        '',
        '[원본 200건 공식 근거 CSV](https://github.com/programmer119/worklinks/blob/main/startup-support/audits/changcom-200-official-evidence-20261111.csv)',
        '[창컴 1차 협의안](https://github.com/programmer119/worklinks/blob/main/startup-support/audits/changcom-partner-consultation-20261111.md)',
        ''
    ])
    REPORT.write_text('\n'.join(md),encoding='utf-8')
    print('CHANGCOM_ORIGINAL_200_SOURCE_AUDIT',json.dumps({
        'count':len(result),'statuses':dict(stats),'unreadableNotices':unread,
        'sourceExcerptNotices':sum(r['공식원문발췌수']>0 for r in result),
        'alertNoticeCount':len(needs),'signals':dict(by_tag)},ensure_ascii=False))
if __name__=='__main__':
    main()
