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
