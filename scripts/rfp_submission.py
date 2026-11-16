#!/usr/bin/env python3
"""Source-cited tender submission deliverables; never infer requirements from filenames.

This is deliberately separate from bidder eligibility and staffing. A mention of
a document in an evaluation table is NOT evidence that it must be submitted.
"""
import re

VERSION = 1
TEXT_LIMIT = 1_000_000
MAX_FILE_ITEMS = 28
MAX_NOTICE_ITEMS = 24
STAGES = {'bid', 'presentation', 'post_award', 'unknown'}

DOCS = (
    ('정성 PDF', r'정성(?:적)?\s*(?:평가\s*)?(?:제안서|PDF)|제안서\s*[(\[]\s*정성'),
    ('정량 PDF', r'정량(?:적)?\s*(?:평가\s*)?(?:제안서|PDF)|제안서\s*[(\[]\s*정량'),
    ('발표자료', r'발표\s*자료|제안\s*발표\s*(?:자료|PPT)|프레젠테이션\s*자료'),
    ('제안서', r'(?<!요청)제안\s*서(?!\s*(?:요청|서식\s*작성))'),
    ('입찰신청서', r'입찰\s*(?:참가\s*)?신청서'),
    ('가격제안서', r'가격\s*제안서|가격\s*입찰서'),
    ('견적서', r'견적\s*서'),
    ('서약서', r'서약\s*서'),
    ('확약서', r'확약\s*서'),
    ('실적증명서', r'(?:수행\s*)?실적\s*증명서'),
    ('재직증명서', r'재직\s*증명서'),
    ('사업자등록증', r'사업자\s*등록증'),
    ('인감증명서', r'인감\s*증명서'),
)
SUBMISSION_CONTEXT = re.compile(r'제출|구비\s*서류|첨부\s*(?:하|서류)|접수\s*서류|송부|준비\s*서류')
HEADING = re.compile(r'제출\s*(?:서류|자료|문서|물|목록)|입찰\s*참가\s*(?:신청|등록)\s*서류|구비\s*서류')
NEW_SECTION = re.compile(r'^\s*(?:[0-9IVXivx]+[.)]\s*)?(?:사업\s*개요|과업\s*(?:내용|범위)|평가\s*(?:항목|기준|방법)|선정\s*방법|참가\s*자격|계약\s*(?:조건|체결))\s*[:：]?$')
NEGATIVE = re.compile(r'제출\s*(?:불필요|면제|하지\s*않|할\s*필요\s*없)|(?:제출|구비)\s*대상\s*아님|제출\s*하지\s*말')
OPTIONAL = re.compile(r'선택\s*사항|해당\s*(?:시|하는\s*경우)|필요\s*시|별도\s*(?:요청|안내)|제출\s*가능')
POST_AWARD = re.compile(r'낙찰\s*(?:자|후)|계약\s*(?:체결\s*)?(?:후|시)|계약\s*상대자|우선\s*협상\s*대상자|선정\s*(?:후|업체)')
PRESENTATION = re.compile(r'발표\s*(?:평가|심사|당일)\s*(?:시|당일|까지)?|발표\s*당일|PT\s*평가\s*시')
BID = re.compile(r'입찰\s*(?:시|전|마감|접수|참가|등록)|제안서\s*제출|입찰서\s*제출|접수\s*(?:마감|시)|마감\s*(?:시|전|까지)')
COPY_COUNT = re.compile(r'(?:원본|사본)?\s*([0-9]{1,3})\s*부')

def _stage(text, inherited='unknown'):
    if POST_AWARD.search(text):
        return 'post_award'
    if PRESENTATION.search(text):
        return 'presentation'
    if BID.search(text):
        return 'bid'
    return inherited

def extract_submission_items(text, source_file):
    """Extract document labels only from explicit or scoped submission statements."""
    if not isinstance(text, str):
        return [], False
    complete = len(text) <= TEXT_LIMIT
    lines = text[:TEXT_LIMIT].splitlines()
    found = {}
    section_left = 0
    section_stage = 'unknown'
    for line_no, raw in enumerate(lines, 1):
        line = ' '.join(raw.split())
        if not line:
            if section_left:
                section_left -= 1
            continue
        if HEADING.search(line):
            section_left = 16
            section_stage = _stage(line, 'bid')
        elif NEW_SECTION.fullmatch(line):
            section_left = 0
        explicit = bool(SUBMISSION_CONTEXT.search(line))
        scoped = section_left > 0
        if section_left:
            section_left -= 1
        if not (explicit or scoped) or NEGATIVE.search(line):
            continue
        stage = _stage(line, section_stage if scoped else 'unknown')
        contextual = not explicit or bool(OPTIONAL.search(line))
        matches = []
        for label, rx in DOCS:
            for m in re.finditer(rx, line, re.I):
                matches.append((m.start(), label, m.end()))
                break
        annex = re.search(r'별지\s*(?:제?\s*)?([0-9]{1,2})(?:\s*[~～-]\s*(?:제?\s*)?([0-9]{1,2}))?', line)
        if annex:
            last = annex.group(2)
            matches.append((annex.start(),
                            '별지 ' + annex.group(1) + (('~' + last) if last else ''),
                            annex.end()))
        if any(m[1] in ('정성 PDF', '정량 PDF') for m in matches):
            matches = [m for m in matches if m[1] != '제안서']
        if any(m[1] == '가격제안서' for m in matches):
            matches = [m for m in matches if m[1] != '제안서']
        for start, label, end in sorted(matches):
            tail = line[end:end + 24]
            count_match = COPY_COUNT.search(tail)
            quantity = (str(int(count_match.group(1))) + '부') if count_match else ''
            display = label + (' ' + quantity if quantity else '')
            if label == '발표자료' and '발표평가' in line and not explicit and not scoped:
                continue
            key = (label, stage)
            item = {'label': display[:44], 'stage': stage,
                    'confidence': 'review' if contextual else 'source',
                    'sourceFile': str(source_file or '')[:160],
                    'sourceLine': line_no, 'sourceText': line[:260]}
            prev = found.get(key)
            if prev is None or (item['confidence'] == 'source' and
                                prev['confidence'] != 'source') or (
                                quantity and not re.search(r'\d+부$', prev['label'])):
                found[key] = item
            if len(found) >= MAX_FILE_ITEMS:
                return list(found.values()), False
    return list(found.values()), complete

def submission_summary(notice):
    """Bounded durable evidence; no notice-wide completeness claim from partial files."""
    files = [f for f in (notice.get('files') or []) if isinstance(f, dict)]
    selected = {}
    for file in files:
        if file.get('readable') is not True:
            continue
        for item in (file.get('submissionItems') or []):
            if not isinstance(item, dict):
                continue
            label = str(item.get('label') or '').strip()
            stage = item.get('stage')
            if not label or stage not in STAGES:
                continue
            key = (re.sub(r'\s+\d+부$', '', label), stage)
            current = selected.get(key)
            if current is None or (item.get('confidence') == 'source'
                                   and current.get('confidence') != 'source'):
                selected[key] = item
            if len(selected) >= MAX_NOTICE_ITEMS:
                break
    return [{'label': str(v.get('label') or '')[:44],
             'stage': v['stage'],
             'confidence': ('source' if v.get('confidence') == 'source' else 'review'),
             'sourceFile': str(v.get('sourceFile') or '')[:160],
             'sourceLine': int(v.get('sourceLine') or 0),
             'sourceText': str(v.get('sourceText') or '')[:260]}
            for v in selected.values()][:MAX_NOTICE_ITEMS]
