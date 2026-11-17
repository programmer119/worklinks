#!/usr/bin/env python3
"""Source-backed required/not-required decisions for two bid eligibility conditions.

These are *document requirements*, NOT claims that a particular bidder is
qualified. A positive needs an explicit mandatory clause. A negative needs
complete coverage of all original attachments (or a clearly explicit waiver).
Evaluation scores alone are not mandatory pre-bid experience credentials.
"""
import re

VERSION=1
MAX_TEXT_CHARS=6_000_000
MAX_EVIDENCE=12
P=re.compile(r'수행\s*실적|유사\s*(?:사업|용역|납품|구축)?\s*실적|실적\s*(?:증명|확인|자료|서류|기준|요건|조건|제출|평가|점수|배점)|(?:사업|계약|납품|용역|구축)\s*실적|실적\s*\d',re.I)
D=re.compile(r'직접\s*생산|세부\s*품명\s*번호|세부품명번호|직생\s*(?:확인|증명)',re.I)
EVAL=re.compile(r'평가|배점|가점|정량|정성|점수|평가표|제안서\s*평가|평점|심사\s*점수',re.I)
REQUIRED=re.compile(r'입찰\s*참가\s*(?:자격|조건|요건)|참가\s*자격|입찰\s*참여\s*조건|필수|반드시|소지\s*하여야|보유\s*하여야|제출\s*하여야|제출\s*해야|첨부\s*하여야|제출\s*필수|자격\s*요건|구비\s*하여야|보유\s*업체|보유한\s*자|미제출\s*시\s*(?:무효|제외)|실적\s*미달\s*시',re.I)
PROOF=re.compile(r'제출|첨부|소지|보유|필수|확인\s*증명서|실적\s*증명서|증빙\s*자료',re.I)
NUMERIC_PERF=re.compile(r'(?:(?:최근|직전)\s*\d+\s*년|(?<!\d)\d[\d,.]*\s*(?:억\s*원|백만\s*원|만원|건)\s*이상|실적.{0,18}(?:이상|보유|입증))',re.I)
NEGATIVE=re.compile(r'불필요|필요하지\s*않|요구하지\s*않|적용하지\s*않|제출하지\s*않|의무\s*없|면제|요구\s*없|실적\s*제한\s*없|직접\s*생산.{0,15}(?:대상\s*아님|해당\s*없)',re.I)
CONDITIONAL=re.compile(r'해당하는\s*경우|해당\s*시|필요\s*시|필요한\s*경우|요청\s*시|경우에\s*한해|제출\s*가능|선택\s*사항|예시|참고용|선정\s*후|낙찰자\s*선정\s*후|계약\s*체결\s*후',re.I)
EXPLICIT_WAIVER=re.compile(
    r'(?:실적|실적증명|수행실적|직접\s*생산|직접생산확인증명서).{0,55}'
    r'(?:불필요|필요하지\s*않|요구하지\s*않|적용하지\s*않|제출하지\s*않|의무\s*없|면제|요구\s*없|해당\s*없)'
    r'|(?:불필요|요구하지\s*않|의무\s*없|면제).{0,35}'
    r'(?:실적|직접\s*생산|세부\s*품명)',re.I)
DIRECT_CERT=re.compile(r'직접\s*생산\s*(?:확인\s*)?(?:증명서|확인서)|직접생산확인증명서',re.I)
PERF_CERT=re.compile(r'(?:수행|사업|납품|용역)?\s*실적\s*(?:확인서|증명서|증명|제출\s*서류)',re.I)


def _windows(text):
    lines=text.splitlines()
    for i,line in enumerate(lines):
        trimmed=' '.join(line.split())
        if not trimmed:
            continue
        # A 6 MB HWP paragraph must not drop a requirement after the first 270
        # characters. Overlapping bounded windows also cover wrapped PDF lines.
        if len(trimmed)>450:
            for off in range(0,len(trimmed),300):
                yield i+1,trimmed[max(0,off-100):off+450]
        else:
            left=' '.join(lines[max(0,i-1):i]).strip()
            right=' '.join(lines[i+1:i+2]).strip()
            if len(trimmed)<150 and len(left)<130 and len(right)<130:
                yield i+1,' '.join((left,trimmed,right)).strip()
            else:
                yield i+1,trimmed


def _classify(topic,window):
    pattern=P if topic=='performance' else D
    if not pattern.search(window):
        return None
    normalized=' '.join(window.split())[:450]
    if EXPLICIT_WAIVER.search(normalized):
        return 'waived'
    if CONDITIONAL.search(normalized):
        return 'ambiguous'
    is_eval=bool(EVAL.search(normalized))
    if topic=='performance':
        certain=bool(PERF_CERT.search(normalized) and PROOF.search(normalized) and REQUIRED.search(normalized))
        certain=certain or bool(P.search(normalized) and REQUIRED.search(normalized)
                                and NUMERIC_PERF.search(normalized))
        certain=certain or bool(P.search(normalized) and
                                re.search(r'실적.{0,45}(?:입찰\s*참가\s*자격|필수|제출\s*하여야)|'
                                          r'입찰\s*참가\s*(?:자격|조건).{0,80}실적',normalized,re.I))
    else:
        certain=bool(DIRECT_CERT.search(normalized) and
                     (REQUIRED.search(normalized) or PROOF.search(normalized)))
        certain=certain or bool(re.search(
            r'입찰\s*참가\s*(?:자격|요건|조건).{0,90}직접\s*생산|'
            r'직접\s*생산.{0,90}(?:입찰\s*참가\s*(?:자격|요건|조건)|필수|제출\s*하여야)',normalized,re.I))
    # Evaluation experience can earn points without being an admission gate.
    if is_eval and not re.search(
        r'입찰\s*참가\s*(?:자격|조건|요건)|미제출\s*시\s*(?:무효|제외)|필수\s*(?:실적|증빙)',normalized,re.I):
        return 'evaluation'
    if certain and not NEGATIVE.search(normalized):
        return 'required'
    return 'ambiguous'


def scan_file(text,filename,source_url=''):
    """Full extracted source, versioned. Never infer success from an excerpt."""
    text=str(text or '')
    trimmed=text[:MAX_TEXT_CHARS]
    found={'performance':[],'directProduction':[]}
    overflow={'performance':False,'directProduction':False}
    seen={'performance':set(),'directProduction':set()}
    for number,window in _windows(trimmed):
        for topic in found:
            kind=_classify(topic,window)
            if kind is None:
                continue
            quote=' '.join(window.split()).strip()[:300]
            key=(kind,quote)
            if key in seen[topic]:
                continue
            seen[topic].add(key)
            if len(found[topic])>=MAX_EVIDENCE:
                overflow[topic]=True
                continue
            found[topic].append({
                'kind':kind,'sourceFile':str(filename)[:160],
                'sourceUrl':str(source_url)[:400],
                'sourceLine':number,'sourceText':quote})
    out={}
    for topic in found:
        kinds={f['kind'] for f in found[topic]}
        if len(text)>MAX_TEXT_CHARS or overflow[topic]:
            status='review'
        elif 'required' in kinds and 'waived' in kinds:
            status='review'  # conflicting clauses
        elif 'required' in kinds:
            status='required'
        elif 'ambiguous' in kinds:
            status='review'
        else:
            status='not_required'  # fully read source; may be evaluation-only
        out[topic]={
            'status':status,'evidence':found[topic],
            'hasEvaluation':('evaluation' in kinds),
            'reason':('source_text_truncated_or_evidence_overflow'
                      if len(text)>MAX_TEXT_CHARS or overflow[topic]
                      else 'conflicting_required_and_waived' if status=='review'
                      and 'required' in kinds and 'waived' in kinds
                      else 'explicit_required' if status=='required'
                      else 'ambiguous_qualification_wording' if status=='review'
                      else 'explicit_waiver' if 'waived' in kinds
                      else 'evaluation_only_not_bid_qualification' if 'evaluation' in kinds
                      else 'no_mandatory_clause_in_full_source')
        }
    return out


def summarize_notice(files,manifest_complete):
    """One notice verdict; conservative with unread originals or old versions."""
    files=[f for f in files if isinstance(f,dict)]
    def pdf_substitute(f):
        if (f.get('skippedDuplicateFormat') is not True
                or not f.get('alternatePdfEvidence') or
                len(str(f.get('alternatePdfSourceSha256') or ''))!=64):
            return False
        return any(o.get('name')==f['alternatePdfEvidence'] and
                   o.get('sourceSha256')==f['alternatePdfSourceSha256'] and
                   o.get('readable') is True and
                   o.get('sourceTextScanComplete') is True and
                   int(o.get('requirementScanVersion') or 0)>=VERSION
                   for o in files)
    usable=[f for f in files if not pdf_substitute(f)]
    complete=bool(files and manifest_complete is True and all(
        f.get('readable') is True and f.get('sourceTextScanComplete') is True
        and f.get('qualificationScanTruncated') is not True
        and int(f.get('requirementScanVersion') or 0)>=VERSION
        and isinstance(f.get('requirementVerdicts'),dict)
        for f in usable))
    result={}
    for topic in ('performance','directProduction'):
        evidence=[]
        statuses=[]
        evaluation=False
        for f in usable:
            d=(f.get('requirementVerdicts') or {}).get(topic) or {}
            statuses.append(d.get('status','review'))
            evaluation=evaluation or d.get('hasEvaluation') is True
            for item in d.get('evidence') or []:
                if len(evidence)<MAX_EVIDENCE:
                    evidence.append(item)
        if 'required' in statuses and 'not_required' in statuses:
            # Ordinary absence in another file is not contradictory to a
            # positive in this source. Explicit waivers require human review.
            explicit_waiver=any(
                item.get('kind')=='waived' for item in evidence)
        else:
            explicit_waiver=any(item.get('kind')=='waived' for item in evidence)
        if 'required' in statuses and explicit_waiver:
            verdict='review'
        elif 'required' in statuses:
            verdict='required'
        elif not complete or 'review' in statuses:
            verdict='review'
        else:
            verdict='not_required'
        result[topic]={
            'status':verdict,'scanVersion':VERSION,
            'evidence':evidence,'hasEvaluation':evaluation,
            'sourceComplete':complete,
            'reason':('explicit_required' if verdict=='required'
                      else 'conflicting_official_clauses' if verdict=='review' and
                      explicit_waiver and 'required' in statuses
                      else 'source_unreadable_or_unscanned' if not complete
                      else 'ambiguous_source_clause' if verdict=='review'
                      else 'full_official_attachments_no_mandatory_clause')}
    return {'version':VERSION,'complete':complete,'verdicts':result}
