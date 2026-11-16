#!/usr/bin/env python3
"""Durable, independent download and scan queues for the full live RFP backlog.

The download worker never waits for a scan; the scanner claims only ready notices.
A changed reader fingerprint resets scanning but keeps verified archived originals.
"""
import datetime as dt
from contextlib import contextmanager
import json
import hashlib
import os
from pathlib import Path
import sqlite3
import time

KST=dt.timezone(dt.timedelta(hours=9))
SCHEMA_VERSION=1

def now_utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()

# Repeat detection uses only durable scan evidence, never a wall-clock stamp.
# OCR repair or a newer parser can change this fingerprint and reopen work.
def scan_evidence_signature(evidence):
    row=evidence if isinstance(evidence,dict) else {}
    fields=('status','manifestComplete','classificationVersion',
            'staffingRoleScanComplete','hwpxReaderVersion')
    file_fields=('name','sourceSha256','readable','sourceTextScanComplete',
                 'staffingRoleScanVersion','staffingFactScanVersion',
                 'staffingRoleScanTruncated','qualificationScanTruncated',
                 'skippedDuplicateFormat','alternatePdfSourceSha256',
                 'staffingScopeExcluded','errorCategory')
    compact={'notice':{k:row.get(k) for k in fields},
             'files':[{k:f.get(k) for k in file_fields}
                      for f in (row.get('files') or []) if isinstance(f,dict)]}
    return hashlib.sha256(json.dumps(compact,sort_keys=True,
                  ensure_ascii=False,separators=(',',':')).encode('utf-8')).hexdigest()

class RfpDualQueue:
    def __init__(self,path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('''CREATE TABLE IF NOT EXISTS rfp_dual_notices(
                notice_key TEXT PRIMARY KEY,
                closes_on TEXT NOT NULL DEFAULT '',
                reader_fingerprint TEXT NOT NULL,
                download_status TEXT NOT NULL DEFAULT 'pending',
                scan_status TEXT NOT NULL DEFAULT 'pending',
                metadata_json TEXT NOT NULL DEFAULT '',
                download_total INTEGER NOT NULL DEFAULT 0,
                download_done INTEGER NOT NULL DEFAULT 0,
                download_attempts INTEGER NOT NULL DEFAULT 0,
                download_retry_epoch REAL NOT NULL DEFAULT 0,
                scan_retry_epoch REAL NOT NULL DEFAULT 0,
                scan_repeat_count INTEGER NOT NULL DEFAULT 0,
                scan_failure_signature TEXT NOT NULL DEFAULT '',
                last_error TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            )''')
            cols={row[1] for row in db.execute('PRAGMA table_info(rfp_dual_notices)')}
            if 'scan_repeat_count' not in cols:
                db.execute("ALTER TABLE rfp_dual_notices ADD COLUMN scan_repeat_count INTEGER NOT NULL DEFAULT 0")
            if 'scan_failure_signature' not in cols:
                db.execute("ALTER TABLE rfp_dual_notices ADD COLUMN scan_failure_signature TEXT NOT NULL DEFAULT ''")
            db.execute('''CREATE INDEX IF NOT EXISTS dual_queue_fetch
                ON rfp_dual_notices(download_status,download_retry_epoch)''')
            db.execute('''CREATE TABLE IF NOT EXISTS rfp_bulk_manifests(
                notice_key TEXT PRIMARY KEY,
                metadata_json TEXT NOT NULL,
                sources TEXT NOT NULL,
                saved_at TEXT NOT NULL
            )''')
            db.execute('''CREATE TABLE IF NOT EXISTS rfp_bulk_pages(
                day TEXT NOT NULL, source TEXT NOT NULL, page INTEGER NOT NULL,
                total_count INTEGER NOT NULL, raw_count INTEGER NOT NULL,
                items_json TEXT NOT NULL, saved_at TEXT NOT NULL,
                requested_rows INTEGER NOT NULL DEFAULT 1000,
                PRIMARY KEY(day,source,page)
            )''')
            cols={row[1] for row in db.execute('PRAGMA table_info(rfp_bulk_pages)')}
            if 'requested_rows' not in cols:
                db.execute('ALTER TABLE rfp_bulk_pages ADD COLUMN requested_rows INTEGER NOT NULL DEFAULT 1000')
            db.execute('''CREATE TABLE IF NOT EXISTS rfp_bulk_unmatched(
                notice_key TEXT PRIMARY KEY, retry_epoch REAL NOT NULL,
                reason TEXT NOT NULL DEFAULT ''
            )''')
            db.execute('''CREATE TABLE IF NOT EXISTS rfp_bulk_request_budget(
                started_at TEXT NOT NULL, source TEXT NOT NULL, day TEXT NOT NULL,
                page INTEGER NOT NULL
            )''')
            db.execute('''CREATE INDEX IF NOT EXISTS rfp_bulk_request_started
                ON rfp_bulk_request_budget(started_at)''')
            db.execute('''CREATE INDEX IF NOT EXISTS dual_queue_scan
                ON rfp_dual_notices(scan_status,download_status,scan_retry_epoch)''')

    @contextmanager
    def connect(self):
        db=sqlite3.connect(str(self.path),timeout=12)
        db.execute('PRAGMA busy_timeout=12000')
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def enqueue(self,notices,fingerprint):
        """Idempotent. 64-small-row transactions avoid blocking scan writes."""
        added=0
        entries=list(notices)
        for offset in range(0,len(entries),64):
            with self.connect() as db:
                for no,order,closes in entries[offset:offset+64]:
                    key=str(no)+':'+str(order).zfill(3)
                    val=str(closes or '')
                    cur=db.execute('SELECT reader_fingerprint FROM rfp_dual_notices WHERE notice_key=?',(key,)).fetchone()
                    if cur is None:
                        db.execute('''INSERT INTO rfp_dual_notices(
                            notice_key,closes_on,reader_fingerprint,updated_at)
                            VALUES(?,?,?,?)''',(key,val,fingerprint,now_utc()))
                        added+=1
                    elif cur[0]!=fingerprint:
                        db.execute('''UPDATE rfp_dual_notices
                            SET reader_fingerprint=?,scan_status='pending',scan_retry_epoch=0,
                                scan_repeat_count=0,scan_failure_signature='',
                                closes_on=?,updated_at=? WHERE notice_key=?''',
                            (fingerprint,val,now_utc(),key))
                    elif val:
                        db.execute('''UPDATE rfp_dual_notices SET closes_on=?
                            WHERE notice_key=? AND closes_on<>?''',(val,key,val))
        return added

    def reconcile_management(self,managed,latest_valid,fingerprint):
        """Idempotently restore the real known-deadline cohort.

        A validated historical scan requires no new download. An old queue
        'done' is NEVER proof of current-version RFP completeness. Preserve
        verified binaries, metadata, retries, and independent unknown-date work.
        """
        valid=set(latest_valid)
        if not isinstance(managed,dict) or not valid.issubset(managed):
            raise ValueError('invalid_management_cohort')
        if not isinstance(fingerprint,str) or not fingerprint:
            raise ValueError('invalid_reader_fingerprint')
        with self.connect() as db:
            old={key:(download,scan,version,closes)
                for key,download,scan,version,closes in db.execute('''
                    SELECT notice_key,download_status,scan_status,
                    reader_fingerprint,closes_on FROM rfp_dual_notices''')}
        tally={'managed':len(managed),'latestValid':len(valid),
               'missingAdded':0,'previouslyValidAdded':0,
               'obsoleteDoneRequeued':0,'verifiedEmptyBlocked':0,
               'completedEvidenceReconciled':0,
               'outsideScopePreserved':len(set(old)-set(managed))}
        entries=sorted(managed.items())
        for offset in range(0,len(entries),64):
            with self.connect() as db:
                for key,closes in entries[offset:offset+64]:
                    present=old.get(key)
                    is_valid=key in valid
                    if present is None:
                        status='evidence_complete' if is_valid else 'pending'
                        scan='done' if is_valid else 'pending'
                        db.execute('''INSERT OR IGNORE INTO rfp_dual_notices(
                            notice_key,closes_on,reader_fingerprint,download_status,
                            scan_status,updated_at) VALUES(?,?,?,?,?,?)''',
                            (key,closes,fingerprint,status,scan,now_utc()))
                        if is_valid:tally['previouslyValidAdded']+=1
                        else:tally['missingAdded']+=1
                        continue
                    download,scan,version,old_close=present
                    # Do not change an active downloader or scanner claim.
                    if download=='fetching' or scan=='scanning':
                        continue
                    new_download=download
                    new_scan=scan
                    retry_reset=False
                    if is_valid:
                        if download in ('pending','retry','evidence_complete'):
                            new_download='evidence_complete'
                        if scan!='done':
                            new_scan='done'
                            retry_reset=True
                            tally['completedEvidenceReconciled']+=1
                    elif download=='evidence_complete':
                        # A previously valid index was invalidated by a new
                        # parser/manifest. Obtain/reuse real originals again.
                        new_download='pending'
                        new_scan='pending'
                        retry_reset=True
                        tally['obsoleteDoneRequeued']+=1
                    elif scan in ('done','skipped'):
                        if download=='ready':
                            new_scan='pending'
                            retry_reset=True
                            tally['obsoleteDoneRequeued']+=1
                        elif download=='no_attachments':
                            # Officially complete empty manifest; cannot scan
                            # a nonexistent original and must never lie "done".
                            tally['verifiedEmptyBlocked']+=1
                        elif download=='error_confirmed':
                            # Permanent verified HTTP 422 can reopen only on
                            # an actual official attachment reference change.
                            new_scan='pending'
                            retry_reset=True
                        else:
                            new_scan='pending'
                            retry_reset=True
                    if (new_download,new_scan,version,old_close)!=(
                            download,scan,fingerprint,closes):
                        db.execute('''UPDATE rfp_dual_notices
                            SET download_status=?,scan_status=?,
                                reader_fingerprint=?,closes_on=?,
                                scan_retry_epoch=CASE WHEN ? THEN 0
                                    ELSE scan_retry_epoch END,
                                download_retry_epoch=CASE WHEN ?='evidence_complete'
                                    THEN 0 ELSE download_retry_epoch END,
                                updated_at=?
                            WHERE notice_key=? AND download_status<> 'fetching'
                              AND scan_status<> 'scanning' ''',
                            (new_download,new_scan,fingerprint,closes,
                             int(retry_reset),new_download,now_utc(),key))
                    # A reader version change invalidates the previous retry signature.
                    if version!=fingerprint:
                        db.execute("""UPDATE rfp_dual_notices
                            SET scan_repeat_count=0,scan_failure_signature=''
                            WHERE notice_key=? AND scan_status!='scanning'""",(key,))
                    if is_valid:
                        # The evidence is now complete. Old generic error text
                        # is not allowed to survive a successful reconciliation.
                        db.execute("""UPDATE rfp_dual_notices
                            SET last_error='',scan_retry_epoch=0,
                                scan_repeat_count=0,scan_failure_signature=''
                            WHERE notice_key=? AND scan_status='done'
                            AND (last_error<>'' OR scan_retry_epoch<>0
                                 OR scan_repeat_count<>0 OR scan_failure_signature<>'')""",
                            (key,))
        return tally

    def retire_expired(self,today=None):
        """Retire past-close notices. Raw originals are retained/pruned elsewhere."""
        day=today or dt.datetime.now(KST).date()
        with self.connect() as db:
            return db.execute(
                "DELETE FROM rfp_dual_notices WHERE closes_on<>'' AND closes_on<?",
                (day.isoformat(),)).rowcount

    def retire_superseded(self,latest):
        """Retire previous ordinals, officially canceled or no-longer-SW bids."""
        if not latest:return 0
        with self.connect() as db:
            rows=db.execute('SELECT notice_key FROM rfp_dual_notices').fetchall()
        stale=[]
        for (key,) in rows:
            try:no,ordinal=key.rsplit(':',1);number=int(ordinal)
            except (ValueError,TypeError):continue
            current=latest.get(no)
            if current is None:continue
            if (number<int(current['order']) or current['cancelled'] or
                    not current['sw']):
                stale.append((key,))
        for start in range(0,len(stale),64):
            with self.connect() as db:
                chunk=stale[start:start+64]
                db.executemany('DELETE FROM rfp_dual_notices WHERE notice_key=?',chunk)
                db.executemany('DELETE FROM rfp_bulk_manifests WHERE notice_key=?',chunk)
                db.executemany('DELETE FROM rfp_bulk_unmatched WHERE notice_key=?',chunk)
        return len(stale)

    def reset_stale(self):
        """Safe only at process start; a lost worker can be resumed from raw bytes."""
        with self.connect() as db:
            db.execute("UPDATE rfp_dual_notices SET download_status='pending' WHERE download_status='fetching'")
            # Scanner claims are recovered on their own timeout, not on downloader restart.

    def release_old_official_missing_retries(self):
        """One-time migration: recheck old 24h HTTP 422 retries with terminal handling."""
        with self.connect() as db:
            return db.execute('''UPDATE rfp_dual_notices
                SET download_status='pending',download_retry_epoch=0,
                    last_error='official_missing_reference_verify_once',
                    updated_at=?
                WHERE download_status='retry' AND
                    last_error LIKE '%official_attachment_reference_missing_422%' ''',
                (now_utc(),)).rowcount

    def release_old_metadata_quota_retries(self):
        """A verified bulk manifest supersedes stale per-notice metadata quota failures.

        Only release errors from the old official-metadata reader. Binary HTTPS
        failures and their existing backoff remain untouched.
        """
        with self.connect() as db:
            return db.execute('''UPDATE rfp_dual_notices
                SET download_retry_epoch=0,
                    last_error='metadata_quota_recovered_by_verified_bulk_manifest'
                WHERE download_status='retry'
                  AND last_error LIKE '%upstream_temporarily_rate_limited_daily_quota%'
                  AND EXISTS (SELECT 1 FROM rfp_bulk_manifests m
                              WHERE m.notice_key=rfp_dual_notices.notice_key)
            ''').rowcount

    def claim_download(self,ready_manifest=False):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('''SELECT notice_key,closes_on FROM rfp_dual_notices
                WHERE download_status IN ('pending','retry')
                AND download_retry_epoch<=?
                AND (?=0 OR EXISTS(SELECT 1 FROM rfp_bulk_manifests
                    WHERE rfp_bulk_manifests.notice_key=rfp_dual_notices.notice_key))
                ORDER BY CASE WHEN last_error='cached_original_missing' THEN 0 ELSE 1 END,
                         download_retry_epoch,updated_at,notice_key LIMIT 1''',
                (time.time(),int(ready_manifest))).fetchone()
            if row:
                db.execute('''UPDATE rfp_dual_notices SET download_status='fetching',
                    download_attempts=download_attempts+1,updated_at=?
                    WHERE notice_key=?''',(now_utc(),row[0]))
            return row

    def save_bulk_manifests(self,records):
        # Publish a complete three-source manifest atomically, never partial.
        if not records:return 0
        with self.connect() as db:
            # Confirmed errors are terminal only for the present official file references.
            # A genuinely changed official manifest reopens just that notice.
            for key,metadata in records.items():
                row=db.execute('''SELECT metadata_json FROM rfp_dual_notices
                    WHERE notice_key=? AND download_status='error_confirmed' ''',
                    (key,)).fetchone()
                if row is None:continue
                try:previous=json.loads(row[0] or '{}')
                except (ValueError,TypeError):previous={}
                def references(doc):
                    items=((doc.get('attachments') or {}).get('items') or [])
                    return sorted((str(x.get('name') or ''),str(x.get('url') or ''))
                                  for x in items if isinstance(x,dict))
                if references(previous)!=references(metadata):
                    db.execute('''UPDATE rfp_dual_notices
                        SET download_status='pending',scan_status='pending',
                        download_retry_epoch=0,scan_retry_epoch=0,
                        metadata_json='',download_done=0,download_total=0,
                        last_error='official_attachment_references_changed',
                        updated_at=? WHERE notice_key=? AND
                        download_status='error_confirmed' ''',(now_utc(),key))
            db.executemany('''INSERT INTO rfp_bulk_manifests(
                notice_key,metadata_json,sources,saved_at)
                VALUES (?,?,?,?) ON CONFLICT(notice_key) DO UPDATE SET
                metadata_json=excluded.metadata_json,
                sources=excluded.sources,saved_at=excluded.saved_at''',
                [(key,json.dumps(metadata,ensure_ascii=False,separators=(',',':')),
                  'ordinary,eorder,detail',now_utc()) for key,metadata in records.items()])
            db.executemany('DELETE FROM rfp_bulk_unmatched WHERE notice_key=?',
                           [(key,) for key in records])
        return len(records)

    def bulk_manifest(self,key):
        with self.connect() as db:
            row=db.execute('''SELECT metadata_json FROM rfp_bulk_manifests
                WHERE notice_key=?''',(key,)).fetchone()
        return json.loads(row[0]) if row else None

    def unprepared_notices(self,eligible_only=False):
        """Deferred unmatched notices remain incomplete, not silently finished."""
        with self.connect() as db:
            return [x[0] for x in db.execute('''SELECT notice_key FROM rfp_dual_notices
                WHERE download_status IN ('pending','retry')
                AND NOT EXISTS(SELECT 1 FROM rfp_bulk_manifests
                    WHERE rfp_bulk_manifests.notice_key=rfp_dual_notices.notice_key)
                AND (?=0 OR NOT EXISTS(SELECT 1 FROM rfp_bulk_unmatched
                    WHERE rfp_bulk_unmatched.notice_key=rfp_dual_notices.notice_key
                      AND retry_epoch>?))''',(int(eligible_only),time.time()))]

    def defer_bulk_unmatched(self,keys,seconds,reason):
        if not keys:return
        with self.connect() as db:
            db.executemany('''INSERT INTO rfp_bulk_unmatched(notice_key,retry_epoch,reason)
                VALUES(?,?,?) ON CONFLICT(notice_key) DO UPDATE SET
                retry_epoch=excluded.retry_epoch,reason=excluded.reason''',
                [(key,time.time()+seconds,str(reason)[:120]) for key in keys])

    def no_attachments(self,key,metadata):
        """All official manifest sources checked: no files to download or scan."""
        attachments=metadata.get('attachments') or {}
        notices=metadata.get('noticeDocuments') or {}
        if not (attachments.get('ok') is True and attachments.get('complete') is True
                and notices.get('ok') is True and notices.get('complete') is True
                and not attachments.get('items')):
            raise ValueError('no_attachments_requires_verified_empty_manifest')
        with self.connect() as db:
            db.execute('''UPDATE rfp_dual_notices
                SET download_status='no_attachments',scan_status='skipped',
                    metadata_json=?,download_done=0,download_total=0,
                    download_retry_epoch=0,scan_retry_epoch=0,last_error='',
                    updated_at=?
                WHERE notice_key=? AND download_status='fetching' ''',
                (json.dumps(metadata,ensure_ascii=False,separators=(',',':')),
                 now_utc(),key))

    def reconcile_legacy_ready(self):
        """Move legacy unverified ready rows back to downloader, or skip empty
        official manifests. Only unprocessed rows; completed scans untouched.
        """
        repaired=0
        skipped=0
        with self.connect() as db:
            rows=db.execute("""SELECT notice_key,metadata_json
                FROM rfp_dual_notices WHERE download_status='ready'
                AND scan_status IN ('pending','retry')""").fetchall()
            for key,raw in rows:
                try: meta=json.loads(raw)
                except (ValueError,TypeError):meta={}
                verified=meta.get('downloadVerifiedFiles') if isinstance(meta,dict) else None
                if isinstance(verified,list) and verified and all(
                    isinstance(f,dict) and f.get('url') and f.get('sha256')
                    for f in verified):
                    continue
                attachments=(meta.get('attachments') or {}) if isinstance(meta,dict) else {}
                notice=(meta.get('noticeDocuments') or {}) if isinstance(meta,dict) else {}
                if (attachments.get('ok') is True and attachments.get('complete') is True
                        and notice.get('ok') is True and notice.get('complete') is True
                        and not attachments.get('items')):
                    db.execute("""UPDATE rfp_dual_notices SET
                        download_status='no_attachments',scan_status='skipped',
                        download_done=0,download_total=0,
                        download_retry_epoch=0,scan_retry_epoch=0,last_error='',
                        updated_at=? WHERE notice_key=?""",(now_utc(),key))
                    skipped+=1
                else:
                    db.execute("""UPDATE rfp_dual_notices SET
                        download_status='pending',scan_status='pending',
                        download_done=0,download_total=0,
                        download_retry_epoch=0,scan_retry_epoch=0,
                        last_error='legacy_download_receipt_missing',
                        updated_at=? WHERE notice_key=?""",(now_utc(),key))
                    repaired+=1
        return {'requeuedForVerifiedDownload':repaired,'verifiedEmptyManifestsSkipped':skipped}

    def downloaded(self,key,metadata,done,total):
        originals=metadata.get('downloadVerifiedFiles')
        if (not isinstance(originals,list) or not originals or
                done!=total or len(originals)!=total or
                any(not isinstance(f,dict) or not f.get('url') or
                    not f.get('sha256') for f in originals)):
            raise ValueError('downloaded_requires_verified_file_receipts')
        payload=json.dumps(metadata,ensure_ascii=False,separators=(',',':'))
        with self.connect() as db:
            db.execute('''UPDATE rfp_dual_notices
                SET download_status='ready',metadata_json=?,download_done=?,download_total=?,
                    download_retry_epoch=0,last_error='',updated_at=?
                WHERE notice_key=? AND download_status='fetching' ''',
                (payload,int(done),int(total),now_utc(),key))

    def download_unavailable(self,key,metadata,verified_files,error_files):
        """Terminal official 422: retain verified originals; never mark missing as saved.

        The notice does NOT enter the scanner's ready queue. New official
        attachment references can reopen it through save_bulk_manifests.
        """
        if not error_files or any(
            not isinstance(item,dict) or item.get('httpStatus')!=422 or
            not item.get('url') for item in error_files):
            raise ValueError('terminal_error_requires_verified_official_422')
        if any(not isinstance(item,dict) or
               not item.get('sha256') or not item.get('url')
               for item in verified_files):
            raise ValueError('terminal_error_verified_receipts_invalid')
        data=dict(metadata,downloadVerifiedFiles=verified_files,
                  downloadErrorFiles=error_files)
        with self.connect() as db:
            db.execute('''UPDATE rfp_dual_notices SET
                download_status='error_confirmed',scan_status='pending',
                metadata_json=?,download_done=?,download_total=?,
                download_retry_epoch=0,scan_retry_epoch=0,
                last_error='official_attachment_reference_missing_422',
                updated_at=?
                WHERE notice_key=? AND download_status='fetching' ''',
                (json.dumps(data,ensure_ascii=False,separators=(',',':')),
                 len(verified_files),len(verified_files)+len(error_files),
                 now_utc(),key))

    def download_failed(self,key,reason,retry_seconds=180):
        with self.connect() as db:
            db.execute('''UPDATE rfp_dual_notices SET download_status='retry',
                download_retry_epoch=?,last_error=?,updated_at=?
                WHERE notice_key=? AND download_status='fetching' ''',
                (time.time()+retry_seconds,str(reason)[:140],now_utc(),key))

    def claim_ready(self,limit):
        """Claim completed downloads only, never ask an official endpoint."""
        claimed=[]
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            rows=db.execute('''SELECT notice_key,closes_on,metadata_json
                FROM rfp_dual_notices WHERE download_status='ready'
                AND scan_status IN ('pending','retry') AND scan_retry_epoch<=?
                ORDER BY updated_at,notice_key LIMIT ?''',
                (time.time(),int(limit))).fetchall()
            for key,closes,metadata in rows:
                try:obj=json.loads(metadata)
                except (ValueError,TypeError):continue
                if not isinstance(obj,dict):continue
                db.execute('''UPDATE rfp_dual_notices SET scan_status='scanning',updated_at=?
                    WHERE notice_key=?''',(now_utc(),key))
                claimed.append((key,closes,obj))
        return claimed

    def scan_finished(self,key,success,reason='',signature=''):
        """Persist a real failure reason; do not endlessly rescan unchanged bytes.

        First failed scan rechecks once after five minutes. A second identical
        failure is held until the evidence signature or parser version changes.
        A held failure stays retry/incomplete, never becomes a fake success.
        """
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            previous=db.execute('''SELECT scan_failure_signature,scan_repeat_count
                FROM rfp_dual_notices
                WHERE notice_key=? AND scan_status='scanning' ''',(key,)).fetchone()
            if previous is None:return False
            sig=str(signature or '')[:64] if not success else ''
            repeats=(int(previous[1] or 0)+1 if sig and sig==previous[0] else 1)
            # Without a durable signature, never assume the failure is identical.
            retry_epoch=(0 if success else
                2147483647 if sig and repeats>=2 else time.time()+300)
            db.execute('''UPDATE rfp_dual_notices SET
                scan_status=?,scan_retry_epoch=?,last_error=?,
                scan_repeat_count=?,scan_failure_signature=?,updated_at=?
                WHERE notice_key=? AND scan_status='scanning' ''',
                ('done' if success else 'retry',retry_epoch,
                 '' if success else str(reason or 'scan_failure_unclassified')[:140],
                 0 if success else repeats,sig,now_utc(),key))
            return True

    def reopen_changed_scan_evidence(self,evidence):
        """Resume held failures only after their stored scan evidence changes."""
        if not isinstance(evidence,dict):return 0
        recovered=0
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            rows=db.execute('''SELECT notice_key,scan_failure_signature
                FROM rfp_dual_notices WHERE scan_status='retry'
                AND download_status='ready'
                AND scan_failure_signature<>'' AND scan_retry_epoch>?''',
                (time.time(),)).fetchall()
            for key,sig in rows:
                row=evidence.get(key)
                if not isinstance(row,dict):continue
                if scan_evidence_signature(row)==sig:continue
                db.execute('''UPDATE rfp_dual_notices
                    SET scan_retry_epoch=0,scan_repeat_count=0,
                        scan_failure_signature='',updated_at=?
                    WHERE notice_key=? AND scan_status='retry'
                    AND scan_failure_signature=?''',
                    (now_utc(),key,sig))
                recovered+=1
        return recovered

    def mark_download_missing(self,key):
        with self.connect() as db:
            db.execute('''UPDATE rfp_dual_notices SET download_status='pending',
                scan_status='pending',download_retry_epoch=0,scan_retry_epoch=0,
                scan_repeat_count=0,scan_failure_signature='',
                last_error='cached_original_missing',updated_at=?
                WHERE notice_key=?''',(now_utc(),key))

    def recover_stale_scans(self,seconds=2400):
        cutoff=(dt.datetime.now(dt.timezone.utc)-
                dt.timedelta(seconds=seconds)).isoformat()
        with self.connect() as db:
            return db.execute('''UPDATE rfp_dual_notices SET scan_status='pending'
                WHERE scan_status='scanning' AND updated_at<?''',(cutoff,)).rowcount

    def scan_release(self,keys):
        with self.connect() as db:
            db.executemany('''UPDATE rfp_dual_notices SET scan_status='pending'
                WHERE notice_key=? AND scan_status='scanning' ''',
                [(key,) for key in keys])

    def ready_count(self):
        with self.connect() as db:
            return db.execute('''SELECT COUNT(*) FROM rfp_dual_notices
                WHERE download_status='ready' AND scan_status IN ('pending','retry')
                AND scan_retry_epoch<=?''',(time.time(),)).fetchone()[0]

    def stats(self):
        with self.connect() as db:
            rows=db.execute('''SELECT download_status,scan_status,COUNT(*)
                FROM rfp_dual_notices GROUP BY download_status,scan_status''').fetchall()
        total=sum(n for _,_,n in rows)
        downloaded=sum(n for download,_,n in rows if download in ('ready','no_attachments'))
        scan_done=sum(n for _,scan,n in rows if scan in ('done','skipped'))
        skipped=sum(n for _,scan,n in rows if scan=='skipped')
        # "retry" is retriable, not a fabricated completed action.
        confirmed=sum(n for download,_,n in rows if download=='error_confirmed')
        return {'available':True,'total':total,
                'download':{'total':total,'done':downloaded,
                            'processed':downloaded+confirmed,'errors':confirmed,
                            'active':sum(n for download,_,n in rows if download=='fetching'),
                            'failed':sum(n for download,_,n in rows if download=='retry')},
                'scan':{'total':total,'done':scan_done,'skipped':skipped,
                        'active':sum(n for _,scan,n in rows if scan=='scanning'),
                        'failed':sum(n for _,scan,n in rows if scan=='retry')}}

    @staticmethod
    def read_stats(path):
        if not Path(path).is_file():
            return {'available':False}
        with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True,timeout=2) as db:
            rows=db.execute('''SELECT download_status,scan_status,COUNT(*)
                FROM rfp_dual_notices GROUP BY download_status,scan_status''').fetchall()
        total=sum(n for _,_,n in rows)
        return {'available':True,'total':total,
                'download':{'total':total,
                            'done':sum(n for a,_,n in rows if a in ('ready','no_attachments')),
                            'processed':sum(n for a,_,n in rows if a in ('ready','no_attachments','error_confirmed')),
                            'errors':sum(n for a,_,n in rows if a=='error_confirmed'),
                            'active':sum(n for a,_,n in rows if a=='fetching'),
                            'failed':sum(n for a,_,n in rows if a=='retry')},
                'scan':{'total':total,
                        'done':sum(n for _,b,n in rows if b in ('done','skipped')),
                        'skipped':sum(n for _,b,n in rows if b=='skipped'),
                        'active':sum(n for _,b,n in rows if b=='scanning'),
                        'failed':sum(n for _,b,n in rows if b=='retry')}}
