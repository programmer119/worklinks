#!/usr/bin/env python3
"""Read-only authoritative open-SW cohort + evidence validity for queue reconciliation.

This intentionally matches server/g2b-proxy.py's rfp_progress_from_rows and
rfp_stage_checks. No public procurement request or download is made here.
"""
import datetime as dt
import json
import re
import sqlite3
from pathlib import Path

KST=dt.timezone(dt.timedelta(hours=9))
VERSIONS=('classificationVersion','staffingRoleScanVersion',
          'staffingFactScanVersion','hwpxReaderVersion')


# UI history is a separate, source-backed record, NOT a statement that
# the current parser revision passed. It is bounded to one prior success per
# notice; failed rechecks must not erase the last successful thumbnail.
THUMBNAIL_FIELDS=('name','readable','sourceSha256','alternatePdfEvidence',
    'alternatePdfSourceSha256','skippedDuplicateFormat',
    'sourceTextScanComplete','qualificationScanTruncated',
    'staffingRoleScanVersion','staffingFactScanVersion',
    'staffingRoleScanTruncated','staffingScopeExcluded')


def same_thumbnail_original(a,b):
    """Do not reuse an old verdict across changed official source identities."""
    if not isinstance(a,dict) or not isinstance(b,dict):
        return False
    if a.get('manifestChangePending') or b.get('manifestChangePending'):
        return False
    left=[v for v in (a.get('files') or []) if isinstance(v,dict)]
    right=[v for v in (b.get('files') or []) if isinstance(v,dict)]
    if not left or len(left)!=len(right):
        return False
    if [str(f.get('name') or '') for f in left]!=[
            str(f.get('name') or '') for f in right]:
        return False
    sig_a=str(a.get('manifestSignature') or '')
    sig_b=str(b.get('manifestSignature') or '')
    if sig_a or sig_b:
        if not sig_a or sig_a!=sig_b:
            return False
    else:
        # No signed manifest: only exact hashes for ALL original files.
        for x,y in zip(left,right):
            hx=str(x.get('sourceSha256') or x.get('alternatePdfSourceSha256') or '')
            hy=str(y.get('sourceSha256') or y.get('alternatePdfSourceSha256') or '')
            if len(hx)!=64 or hx!=hy:
                return False
    # Even a matching URL/name manifest cannot override a known byte mismatch.
    for x,y in zip(left,right):
        hx=str(x.get('sourceSha256') or '')
        hy=str(y.get('sourceSha256') or '')
        if hx and hy and hx!=hy:
            return False
    return True


def completed_thumbnail_source(row):
    """A proven 4-insurance/onsite/staffing negative needs full source coverage.

    If any applicable source was unresolved, retain only individually cited
    positives through the regular evidence index; do not make up negatives.
    """
    if not isinstance(row,dict) or row.get('status')!='text_extracted_requires_review':
        return False
    if row.get('manifestComplete') is not True or (
            row.get('staffingRoleScanComplete') is not True):
        return False
    files=[f for f in (row.get('files') or []) if isinstance(f,dict)]
    if not files:
        return False
    usable=0
    for f in files:
        if f.get('staffingScopeExcluded') is True:
            continue
        if f.get('readable') is True:
            if (f.get('sourceTextScanComplete') is not True or
                    f.get('qualificationScanTruncated') is True or
                    f.get('staffingRoleScanTruncated') is True or
                    int(f.get('staffingRoleScanVersion') or 0)<=0 or
                    int(f.get('staffingFactScanVersion') or 0)<=0):
                return False
            usable+=1
            continue
        if f.get('skippedDuplicateFormat') is True and (
                f.get('alternatePdfEvidence') and
                len(str(f.get('alternatePdfSourceSha256') or ''))==64):
            matching=next((other for other in files
                if other.get('name')==f.get('alternatePdfEvidence') and
                other.get('readable') is True and
                other.get('sourceTextScanComplete') is True and
                other.get('sourceSha256')==f.get('alternatePdfSourceSha256')),None)
            if matching:
                continue
        return False
    return usable>0


def last_success_thumbnail(row):
    """Return bounded, nonrecursive, evidenced historical source or None."""
    if not completed_thumbnail_source(row):
        return None
    fields=('status','checkedAt','classificationVersion','hwpxReaderVersion',
            'manifestSignature','manifestComplete','staffingRoleScanComplete',
            'manifestChangePending')
    saved={k:row.get(k) for k in fields if row.get(k) is not None}
    saved['files']=[{k:f.get(k) for k in THUMBNAIL_FIELDS if k in f}
                    for f in row.get('files') or [] if isinstance(f,dict)][:24]
    saved['staffingRoles']=(row.get('staffingRoles') or [])[:24]
    saved['staffingFacts']=(row.get('staffingFacts') or [])[:35]
    # Preserve only official quoted requirements used by the three badges.
    snippets=[]
    for entry in row.get('thumbnailClauses') or []:
        if isinstance(entry,dict) and entry.get('text'):
            snippets.append({k:str(entry.get(k) or '')[:330]
                for k in ('type','text','sourceFile')})
        if len(snippets)>=14:break
    for typ,items in ((row.get('changcomClauseEvidence') or {}).get(
            'clauseCandidates') or {}).items():
        for item in items if isinstance(items,list) else []:
            if isinstance(item,dict) and item.get('text') and len(snippets)<14:
                snippets.append({'type':str(typ)[:40],
                    'text':str(item['text'])[:330],
                    'sourceFile':str(item.get('sourceFile') or '')[:140]})
    saved['thumbnailClauses']=snippets
    return saved


def preserve_last_success_thumbnail(candidate,previous):
    """Carry one old verified snapshot only across unchanged originals."""
    if not isinstance(candidate,dict) or not isinstance(previous,dict):
        return candidate
    if completed_thumbnail_source(candidate):
        candidate.pop('lastSuccessfulThumbnail',None)
        return candidate
    archived=previous.get('lastSuccessfulThumbnail')
    snapshot=(archived if isinstance(archived,dict) and
              completed_thumbnail_source(archived) else
              last_success_thumbnail(previous))
    if snapshot and same_thumbnail_original(candidate,snapshot):
        candidate['lastSuccessfulThumbnail']=snapshot
    else:
        candidate.pop('lastSuccessfulThumbnail',None)
    return candidate

def deadline_kst(value):
    match=re.search(r'(20\d{2})[-./]?(\d{2})[-./]?(\d{2})(?:[T\s]*(\d{1,2}):?(\d{2}))?',
                    str(value or '').strip())
    if not match:return None
    try:
        return dt.datetime(int(match[1]),int(match[2]),int(match[3]),
            int(match[4]) if match[4] is not None else 23,
            int(match[5]) if match[5] is not None else 59,tzinfo=KST)
    except ValueError:return None

def latest_complete(row,versions):
    if not isinstance(row,dict) or row.get('status')!='text_extracted_requires_review':
        return False
    files=[f for f in row.get('files') or [] if isinstance(f,dict)]
    # A successfully scanned sibling does not make a failed OCR PDF complete.
    # In particular, keep an old-reader OCR failure eligible for recovery.
    ocr_failed={'pdf_ocr_incomplete','ocr_deferred_to_repair',
                'pdf_unreadable_page','image_ocr_incomplete',
                'hwpx_image_ocr_deferred_to_repair'}
    if any(str(f.get('errorCategory') or '') in ocr_failed
           and f.get('readable') is not True
           and f.get('staffingScopeExcluded') is not True for f in files):
        return False
    readable=[f for f in files if f.get('readable') is True and
              f.get('staffingScopeExcluded') is not True]
    classification=(bool(readable) and row.get('manifestComplete') is True and
         int(row.get('classificationVersion') or 0)>=versions['classificationVersion'] and
         all(f.get('sourceTextScanComplete') is True and
             f.get('qualificationScanTruncated') is not True for f in readable))
    roles=(row.get('staffingRoleScanComplete') is True and bool(readable) and
         all(f.get('sourceTextScanComplete') is True and
             int(f.get('staffingRoleScanVersion') or 0)>=versions['staffingRoleScanVersion'] and
             f.get('staffingRoleScanTruncated') is not True for f in readable))
    facts=(bool(readable) and row.get('staffingRoleScanComplete') is True and
         all(f.get('sourceTextScanComplete') is True and
             int(f.get('staffingFactScanVersion') or 0)>=versions['staffingFactScanVersion']
             for f in readable))
    hwpx=[f for f in readable if str(f.get('name') or '').lower().endswith('.hwpx')]
    hwpx_valid=not hwpx or (
        all(f.get('sourceTextScanComplete') is True for f in hwpx) and
        int(row.get('hwpxReaderVersion') or 0)>=versions['hwpxReaderVersion'])
    return bool(classification and roles and facts and hwpx_valid)

def read_evidence(data_dir):
    data=Path(data_dir)
    versions_json=json.loads((data/'snapshots/rfp-scanner-versions.json').read_text('utf-8'))
    if versions_json.get('ok') is not True or versions_json.get('schemaVersion')!=1:
        raise ValueError('authoritative_reader_versions_not_verified')
    versions=versions_json.get('latest') or {}
    if any(not isinstance(versions.get(k),int) or versions[k]<=0 for k in VERSIONS):
        raise ValueError('authoritative_reader_versions_invalid')
    source=json.loads((data/'snapshots/rfp-coverage-index.json').read_text('utf-8'))
    if source.get('ok') is not True or not isinstance(source.get('byNotice'),dict):
        raise ValueError('authoritative_scan_index_unavailable')
    evidence=dict(source['byNotice'])
    checkpoints=data/'rfp-notice-progress.sqlite3'
    if checkpoints.exists():
        with sqlite3.connect('file:'+str(checkpoints)+'?mode=ro',uri=True,timeout=5) as db:
            rows=db.execute('''SELECT notice_key,checked_at,evidence_json
                 FROM rfp_notice_checkpoints ORDER BY checked_at DESC LIMIT 12000''').fetchall()
        for key,checked,raw in rows:
            if not isinstance(key,str) or not re.match(
                    r'^(?:R\d{2}BK\d{8}|\d{11}):\d{3}$',key):
                continue
            try:row=json.loads(raw)
            except (ValueError,TypeError):continue
            if not isinstance(row,dict) or str(row.get('checkedAt') or '')!=str(checked):
                continue
            if str((evidence.get(key) or {}).get('checkedAt') or '')>=checked:
                continue
            evidence[key]=row
    return versions,evidence

def management_scope(data_dir,now=None):
    """Return ({key: ISO close-date}, latest-valid-keys), same as API's known-deadline cohort.

    Explicitly excludes past/cancelled and unknown-deadline entries; unknown
    dates remain in their existing independent queue and are NOT deleted here.
    """
    data=Path(data_dir)
    now=now or dt.datetime.now(KST)
    if now.tzinfo is None:raise ValueError('timezone_aware_clock_required')
    versions,evidence=read_evidence(data)
    with sqlite3.connect('file:'+str(data/'bids.sqlite3')+'?mode=ro',uri=True,timeout=10) as db:
        rows=db.execute('''SELECT b.bid_no,b.bid_ord,b.payload FROM bid_notices b
            WHERE b.sw_candidate=1 AND NOT EXISTS (
            SELECT 1 FROM bid_notices newer WHERE newer.bid_no=b.bid_no
            AND CAST(newer.bid_ord AS INTEGER)>CAST(b.bid_ord AS INTEGER))
            ORDER BY b.last_seen DESC''').fetchall()
    latest={}
    for no,ordinal,payload in rows:
        try:number=int(ordinal or 0)
        except (ValueError,TypeError):continue
        if no not in latest or number>latest[no][0]:
            latest[no]=(number,no,ordinal,payload)
    managed={}
    valid=set()
    for _,no,ordinal,payload in latest.values():
        key=str(no or '')+':'+str(ordinal or '000').zfill(3)
        try:item=json.loads(payload) if isinstance(payload,str) else payload
        except (ValueError,TypeError):continue
        if not isinstance(item,dict):continue
        if re.search('취소|철회|폐기',str(item.get('noticeKind') or item.get('state') or '')):
            continue
        closes=deadline_kst(item.get('closes'))
        # Same 24-hour actionable deadline as the public progress and
        # verified-original OCR repair; expired/near-close is out of scope.
        if closes is None or closes<=now+dt.timedelta(hours=24):continue
        managed[key]=closes.date().isoformat()
        if latest_complete(evidence.get(key),versions):valid.add(key)
    return managed,valid
