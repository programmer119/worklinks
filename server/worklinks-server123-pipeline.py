#!/usr/bin/env python3
"""Server123's sole scheduler for Changcom shortlist and official RFP extraction.

No GitHub Actions schedules, no git push, and no new ports.
All outputs are served read-only by the existing G2B API from data/snapshots.
Existing GitHub snapshots are seed/fallback and are never deleted by this worker.
"""
import datetime as dt
import fcntl
import gzip
import collections
import json
import re
import sqlite3
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import tempfile
import time

DATA = Path(os.environ.get('G2B_PIPELINE_DATA', '/app/data'))
SEEDS = DATA / 'snapshots'
SCRIPTS = Path(os.environ.get('G2B_PIPELINE_SCRIPTS', '/app/scripts'))
STATE = DATA / 'pipeline-scheduler-state.json'
SOURCE_API = os.environ.get('WORKLINKS_G2B_API', 'http://127.0.0.1:18192/api/g2b')
RFP_PERIOD = max(3600, int(os.environ.get('G2B_RFP_PERIOD', 3600)))
# Recheck/failed-job cooldown only. Successful triggered batches continue immediately.
RFP_UPGRADE_PERIOD = max(300, int(os.environ.get('G2B_RFP_UPGRADE_PERIOD', 600)))
RFP_UPGRADE_LIMIT = max(1, min(8, int(os.environ.get('G2B_RFP_UPGRADE_BATCH', 8))))
RFP_DRAIN_ALGORITHM_VERSION = 'full-management-cohort-reconcile-v6-20261115'
SHORTLIST_PERIOD = max(10800, int(os.environ.get('G2B_SHORTLIST_PERIOD', 10800)))
AWARD_FALLBACK_PERIOD = max(14400, int(os.environ.get('G2B_OPEN_AWARD_PERIOD', 14400)))
RFP_LIMIT = max(1, min(8, int(os.environ.get('G2B_RFP_BATCH', 8))))
RFP_REPAIR_PERIOD = max(3600, int(os.environ.get('G2B_RFP_REPAIR_PERIOD', 3600)))
RFP_REPAIR_LIMIT = max(1, min(120, int(os.environ.get('G2B_RFP_REPAIR_LIMIT', 48))))
# Local OCR repair uses only stored source URLs, no government metadata API calls.
RFP_OPEN_OCR_PERIOD = max(900, int(os.environ.get('G2B_RFP_OPEN_OCR_PERIOD', 900)))
# During continuous stage-3 scanning, interleave one small local-only OCR repair
# after every four successfully published scan batches instead of starving it.
RFP_OCR_SCAN_BATCH_INTERVAL = 4
# When download-ready work is on scan-retry cooldown, OCR repair is independent
# of upstream file requests and must continue using saved verified originals.
RFP_OCR_IDLE_PERIOD = 120
RFP_OPEN_READER_VERSION='pdf25-blank-hwpx-embedded-image-v7'
# Enqueue one bounded official RFP pass after staffing-role parser upgrades.
RFP_STAFFING_READER_VERSION='v7-form-scope-and-two-live-notice-rescan-20261113'
# Explicit short-lived recovery selection; candidates rotate out once fully scanned.
RFP_STAFFING_PRIORITY_KEYS='R26BK01811303:000,R26BK01805618:000,R26BK01807134:000,R26BK01783957:000,R26BK01818412:000,R26BK01797739:000,R26BK01810885:000,R26BK01803834:000'
RFP_OPEN_OCR_LIMIT = max(1, min(35, int(os.environ.get('G2B_RFP_OPEN_OCR_LIMIT', 20))))
QUALIFICATION_PERIOD = max(3600, int(os.environ.get('G2B_QUALIFICATION_PERIOD', 3600)))
QUALIFICATION_BATCH = max(1, min(300, int(os.environ.get('G2B_QUALIFICATION_BATCH', 120))))
READ_FILES = (
    'changcom-actionable.json',
    'g2b-award-fields-open.json',
    'rfp-clauses.json',
    'rfp-coverage-index.json',
    'qualification-review.json',
    'changcom-bid-review.json',
    'sme-cert-snapshot.json',
    'direct-production-snapshot.json',
    'official-awards-snapshot.json',
    'audits/changcom-rfp-backfill-60-20261110.json',
    'audits/changcom-priority-rfp-recovery-20261111.json'
)
PUBLISHED = {
    'rfp': ('rfp-clauses.json', 'rfp-coverage-index.json'),
    'rfpUpgrade': ('rfp-clauses.json', 'rfp-coverage-index.json'),
    'rfpOpenRepair': ('rfp-coverage-index.json',),
    'rfpRepair': ('rfp-clauses.json', 'rfp-coverage-index.json',
                  'rfp-top500-batch-state-20261111.json',
                  'rfp-top500-batch-metadata-20261111.json',
                  'rfp-top500-repair-report-20261111.json'),
    'qualification': ('qualification-review.json',),
    'actionable': ('changcom-actionable.json',),
    'awardFallback': ('g2b-award-fields-open.json',)
}
TIMEOUT = {'rfpUpgrade': 2100, 'rfp': 2100, 'rfpRepair': 2100, 'rfpOpenRepair': 1200, 'qualification': 750, 'actionable': 540, 'awardFallback': 540}


def log(*values):
    print(dt.datetime.now(dt.timezone.utc).isoformat(), *values, flush=True)


def scan_failure_diagnosis(row, versions):
    """Explain failed stage-3 gates using already published evidence, not
    another source request. Does not classify or extract document contents.
    """
    data=row if isinstance(row,dict) else {}
    status=str(data.get('status') or 'missing')
    files=[f for f in (data.get('files') or []) if isinstance(f,dict)]
    readable=[f for f in files if f.get('readable') is True
              and f.get('staffingScopeExcluded') is not True]
    file_failures=collections.Counter(str(f.get('errorCategory') or '')
              for f in files if f.get('readable') is not True
              and f.get('errorCategory')
              and f.get('staffingScopeExcluded') is not True
              and f.get('skippedDuplicateFormat') is not True)
    common=file_failures.most_common(1)[0][0] if file_failures else ''
    if status!='text_extracted_requires_review':
        gate='scan_extraction_'+status
    elif data.get('manifestComplete') is not True:
        gate='scan_manifest_incomplete'
    elif not readable:
        gate='scan_no_readable_source'
    elif any(f.get('sourceTextScanComplete') is not True for f in readable):
        gate='scan_source_incomplete'
    elif any(f.get('qualificationScanTruncated') is True for f in readable):
        gate='scan_qualification_truncated'
    elif data.get('staffingRoleScanComplete') is not True:
        gate='scan_staffing_incomplete'
    elif any(f.get('staffingRoleScanTruncated') is True for f in readable):
        gate='scan_staffing_truncated'
    elif any(int(f.get('staffingRoleScanVersion') or 0)<
             int(versions.get('staffingRoleScanVersion') or 0) for f in readable):
        gate='scan_staffing_version_old'
    else:
        gate='scan_validation_incomplete'
    return (gate+(':'+common if common else ''))[:140]


def sync_scan_retry_activity(queue, key):
    """Make file-level live retry clocks match the committed queue policy.

    The extractor may have emitted its previous one-hour estimate before the
    parent acknowledged the scan. Never show that stale timer to operators.
    """
    try:
        with queue.connect() as db:
            row=db.execute('''SELECT scan_status,scan_retry_epoch,last_error
                FROM rfp_dual_notices WHERE notice_key=?''',(key,)).fetchone()
            if not row:return
            if row[0]=='done':
                # Retire stale file-level retry events instead of claiming
                # that an earlier unreadable file was successfully parsed.
                db.execute('''DELETE FROM rfp_live_events WHERE lane='scan'
                    AND notice_key=? AND file_key<>'' AND status='retry' ''',(key,))
                db.execute('''UPDATE rfp_live_events
                    SET status='done',phase='최신 판독 완료',error_text='',
                        retry_epoch=0,updated_epoch=?
                    WHERE lane='scan' AND notice_key=? AND file_key='' ''',
                    (time.time(),key))
            elif row[0]=='retry':
                held=float(row[1] or 0)>=2147483647
                actual_epoch=0 if held else float(row[1] or 0)
                title=('동일 오류 반복 · 판독 자료 또는 판독기 변경 필요' if held
                       else '검증 미완료 · 예약된 재판독')
                db.execute('''UPDATE rfp_live_events
                    SET retry_epoch=?,error_text=?,
                        phase=CASE WHEN file_key='' THEN ? ELSE phase END,
                        updated_epoch=?
                    WHERE lane='scan' AND notice_key=? AND status='retry' ''',
                    (actual_epoch,str(row[2] or '')[:180],title,time.time(),key))
    except sqlite3.OperationalError:
        # Deterministic queue state remains authoritative even when the
        # optional live-activity table has not been initialized yet.
        pass


def deployed_rfp_reader_versions():
    """Read the version constants from the scanner actually installed on server123."""
    source=(SCRIPTS/'refresh_worklinks_rfp.py').read_text(encoding='utf-8')
    names={'CLASSIFICATION_VERSION':'classificationVersion',
           'STAFFING_ROLE_SCAN_VERSION':'staffingRoleScanVersion',
           'STAFFING_FACT_SCAN_VERSION':'staffingFactScanVersion',
           'HWPX_READER_VERSION':'hwpxReaderVersion'}
    result={}
    for variable,field in names.items():
        candidates=[line.split('=',1)[1].strip() for line in source.splitlines()
                    if '=' in line and line.split('=',1)[0].strip()==variable]
        if len(candidates)!=1 or not candidates[0].isdigit():
            raise RuntimeError('deployed_rfp_parser_version_missing_'+variable)
        result[field]=int(candidates[0])
    return result


def read_state():
    try:
        result=json.loads(STATE.read_text(encoding='utf-8'))
        return result if isinstance(result,dict) else {}
    except (OSError,ValueError):
        return {}


def rfp_coverage_complete(row, versions):
    """Only a full current-version, source-backed scan can protect old evidence."""
    if not isinstance(row,dict) or row.get('status')!='text_extracted_requires_review':
        return False
    if row.get('manifestComplete') is not True or row.get('staffingRoleScanComplete') is not True:
        return False
    files=[f for f in row.get('files') or [] if isinstance(f,dict) and
           f.get('readable') is True and f.get('staffingScopeExcluded') is not True]
    if not files or int(row.get('classificationVersion') or 0)<int(versions.get('classificationVersion') or 999):
        return False
    for f in files:
        if f.get('sourceTextScanComplete') is not True or f.get('qualificationScanTruncated') is True:
            return False
        if f.get('staffingRoleScanTruncated') is True:
            return False
        if int(f.get('staffingRoleScanVersion') or 0)<int(versions.get('staffingRoleScanVersion') or 999):
            return False
        if int(f.get('staffingFactScanVersion') or 0)<int(versions.get('staffingFactScanVersion') or 999):
            return False
    hwpx=any(str(f.get('name') or '').lower().endswith('.hwpx') for f in files)
    return not hwpx or int(row.get('hwpxReaderVersion') or 0)>=int(versions.get('hwpxReaderVersion') or 999)


def rfp_same_verified_manifest(left,right):
    """Do not protect an older scan when a changed official manifest is known."""
    if not isinstance(left,dict) or not isinstance(right,dict):
        return False
    if left.get('manifestChangePending') or right.get('manifestChangePending'):
        return False
    a=str(left.get('manifestSignature') or '')
    b=str(right.get('manifestSignature') or '')
    if a or b:
        return bool(a and b and a==b)
    x=[f for f in left.get('files') or [] if isinstance(f,dict)]
    y=[f for f in right.get('files') or [] if isinstance(f,dict)]
    if not x or len(x)!=len(y):
        return False
    if [f.get('name') for f in x]!=[f.get('name') for f in y]:
        return False
    for old,new in zip(x,y):
        old_sha=str(old.get('sourceSha256') or '')
        new_sha=str(new.get('sourceSha256') or '')
        if old_sha and new_sha and old_sha!=new_sha:
            return False
    return True


def rfp_prefer_evidence(candidate,previous,versions):
    if not isinstance(previous,dict):
        return candidate
    if not isinstance(candidate,dict):
        return previous
    if rfp_same_verified_manifest(candidate,previous):
        candidate_ok=rfp_coverage_complete(candidate,versions)
        previous_ok=rfp_coverage_complete(previous,versions)
        if previous_ok and not candidate_ok:
            return previous
        if candidate_ok and not previous_ok:
            return candidate
    return (candidate if str(candidate.get('checkedAt') or '')>=
            str(previous.get('checkedAt') or '') else previous)


def merge_rfp_coverage_before_publish(stage):
    """Rebase an isolated scan on today's live index and per-notice checkpoints.

    A long OCR batch must never erase a shorter repair already published while
    it was running. A valid complete scan of unchanged originals cannot become
    incomplete just because fast stage-3 defers OCR.
    """
    source=json.loads(stage.read_text(encoding='utf-8'))
    if source.get('ok') is not True or not isinstance(source.get('byNotice'),dict):
        raise ValueError('invalid_staged_rfp_coverage')
    versions_path=SEEDS/'rfp-scanner-versions.json'
    try:
        versions=json.loads(versions_path.read_text(encoding='utf-8'))['latest']
    except (OSError,ValueError,KeyError,TypeError):
        versions={}
    rows=dict(source['byNotice'])
    live=SEEDS/'rfp-coverage-index.json'
    if live.is_file():
        prior=json.loads(live.read_text(encoding='utf-8'))
        if prior.get('ok') is not True or not isinstance(prior.get('byNotice'),dict):
            raise ValueError('invalid_live_rfp_coverage')
        for key,record in prior['byNotice'].items():
            rows[key]=rfp_prefer_evidence(rows.get(key),record,versions)
    progress=DATA/'rfp-notice-progress.sqlite3'
    protected=0
    if progress.is_file():
        with sqlite3.connect('file:'+str(progress)+'?mode=ro',uri=True,timeout=12) as db:
            checkpoints=db.execute(
                'SELECT notice_key,checked_at,evidence_json FROM rfp_notice_checkpoints').fetchall()
        for key,checked,raw in checkpoints:
            try:record=json.loads(raw)
            except (ValueError,TypeError):continue
            if not isinstance(record,dict) or str(record.get('checkedAt') or '')!=str(checked):
                continue
            selected=rfp_prefer_evidence(record,rows.get(key),versions)
            if selected is record:
                protected+=1
            rows[key]=selected
    source['byNotice']=rows
    stage.write_text(json.dumps(source,ensure_ascii=False,separators=(',',':'))+'\n',
                     encoding='utf-8')
    log('RFP_COVERAGE_REBASED',json.dumps({
        'notices':len(rows),'checkpointsPreferred':protected},separators=(',',':')))
    return rows


def publish_verified_repair_checkpoints(keys):
    """Advance only genuinely complete repaired evidence, never a partial error.

    The same authoritative SQLite checkpoint is read by the public API and the
    scan queue reconciler; writing only a JSON snapshot is not durable.
    """
    if not keys:return 0
    source=json.loads((SEEDS/'rfp-coverage-index.json').read_text(encoding='utf-8'))
    rows=source['byNotice']
    versions=json.loads((SEEDS/'rfp-scanner-versions.json').read_text(encoding='utf-8'))['latest']
    dbpath=DATA/'rfp-notice-progress.sqlite3'
    published=0
    with sqlite3.connect(str(dbpath),timeout=15) as db:
        db.execute('PRAGMA busy_timeout=15000')
        db.execute('''CREATE TABLE IF NOT EXISTS rfp_notice_checkpoints(
            notice_key TEXT PRIMARY KEY,checked_at TEXT NOT NULL,evidence_json TEXT NOT NULL)''')
        for key in keys:
            row=rows.get(key)
            if not rfp_coverage_complete(row,versions):
                continue
            checked=str(row.get('checkedAt') or '')
            if not checked:continue
            previous=db.execute(
                'SELECT checked_at,evidence_json FROM rfp_notice_checkpoints WHERE notice_key=?',(key,)
            ).fetchone()
            if previous:
                try:prior=json.loads(previous[1])
                except (TypeError,ValueError):prior={}
                if rfp_prefer_evidence(row,prior,versions) is not row:
                    continue
            payload=json.dumps(row,ensure_ascii=False,separators=(',',':'))
            db.execute('''INSERT INTO rfp_notice_checkpoints(notice_key,checked_at,evidence_json)
                VALUES(?,?,?) ON CONFLICT(notice_key) DO UPDATE SET
                checked_at=excluded.checked_at,evidence_json=excluded.evidence_json
                WHERE excluded.checked_at>=rfp_notice_checkpoints.checked_at''',
                (key,checked,payload))
            published+=1
    log('RFP_OCR_VERIFIED_CHECKPOINTS',published,'of',len(keys))
    return published


def publish_atomic(src, destination):
    """Prepare gzip and JSON files before replace, never publish partial bytes."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.with_name('.' + destination.name + '.next')
    gzpath = Path(str(destination) + '.gz')
    gzstaging = gzpath.with_name('.' + gzpath.name + '.next')
    try:
        with src.open('rb') as inp, staging.open('wb') as out, gzip.open(gzstaging, 'wb', compresslevel=1) as zipped:
            while True:
                chunk = inp.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                zipped.write(chunk)
        os.replace(staging, destination)
        os.replace(gzstaging, gzpath)
    finally:
        for path in (staging, gzstaging):
            try: path.unlink()
            except FileNotFoundError: pass


def publish_state(state):
    staging = STATE.with_suffix('.json.tmp')
    staging.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(staging, STATE)


def quality_guard(kind, outputs):
    """Prevent interrupted scans from replacing source-backed historical evidence."""
    for path in outputs:
        content = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(content, dict) or content.get('ok') is not True:
            raise ValueError('pipeline_incomplete_json_' + path.name)
        if kind in ('rfp','rfpUpgrade','rfpRepair','rfpOpenRepair') and path.name in ('rfp-clauses.json','rfp-coverage-index.json'):
            history = content.get('byNotice')
            if not isinstance(history, dict):
                raise ValueError('pipeline_missing_rfp_byNotice')
            priorpath = SEEDS / path.name
            if priorpath.is_file():
                prior = json.loads(priorpath.read_text(encoding='utf-8'))
                old_history = prior.get('byNotice') or {}
                # Every prior notice key must remain in the cumulative archive.
                if path.name == 'rfp-coverage-index.json' and not set(old_history).issubset(history):
                    raise ValueError('pipeline_rfp_archived_notice_regression')
        if kind == 'qualification':
            if (content.get('schemaVersion') != 1 or
                    not isinstance(content.get('byNotice'),dict) or
                    content.get('mode') != 'rule_based' or
                    any(v.get('automaticEligibilityApproved') is not False
                        for v in content['byNotice'].values())):
                raise ValueError('pipeline_invalid_qualification_summary')
            priorpath=SEEDS / path.name
            if priorpath.is_file():
                prior=json.loads(priorpath.read_text(encoding='utf-8'))
                if not set(prior.get('byNotice') or {}).issubset(content['byNotice']):
                    raise ValueError('pipeline_qualification_history_regression')
        if kind == 'actionable':
            bids=content.get('bids')
            counts=content.get('counts') or {}
            if content.get('bizno') != '1308185973' or not isinstance(bids,list):
                raise ValueError('pipeline_invalid_changcom_identity')
            if int(counts.get('indexedSWTotal') or 0) < 100 or int(counts.get('softwareService') or 0)<1:
                raise ValueError('pipeline_suspect_shortlist_size')
            if not bids or len(bids) < int(counts.get('softwareService') or 0):
                raise ValueError('pipeline_partial_or_empty_changcom_bids')
        if kind == 'awardFallback':
            indexed=content.get('byNotice')
            if (not isinstance(indexed,dict) or
                    int(content.get('totalSavedSw') or 0)<100 or
                    content.get('count')!=len(indexed)):
                raise ValueError('pipeline_bad_award_fallback')
    return True


def stage_workspace(path,minimal=False):
    root = path / 'worklinks'
    (root / 'scripts').mkdir(parents=True)
    for name in ('refresh_worklinks_rfp.py', 'staffing_facts.py', 'analyze_worklinks_rfp_ai.py', 'refresh_worklinks_actionable.py',
                 'refresh_worklinks_open_award_fallback.py',
                 'batch_backfill_changcom_top500_rfp.py',
                 'repair_changcom_top500_rfp.py',
                 'repair_open_rfp_cached_attachments.py',
                 'rfp_call_ledger.py','rfp_dual_queue.py','rfp_management_reconcile.py','rfp_live_activity.py','rfp_bulk_manifests.py'):
        shutil.copy2(SCRIPTS / name, root / 'scripts' / name)
    for name in (() if minimal else READ_FILES):
        source = SEEDS / name
        if source.is_file():
            dest = root / 'startup-support' / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
    for name in ('rfp-clauses.json', 'rfp-coverage-index.json',
                 'rfp-top500-batch-state-20261111.json',
                 'rfp-top500-batch-metadata-20261111.json'):
        source = SEEDS / name
        if source.is_file():
            dest = root / 'snapshots' / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            if minimal and name != 'rfp-coverage-index.json':
                # Only the coverage index is modified by OCR repair. Large
                # full-text archives stay linked read-only, not copied.
                dest.symlink_to(source)
            else:
                shutil.copy2(source, dest)
    # Read-only live databases, with all output written to isolated snapshot stage.
    for name in ('bids.sqlite3','rfp-request-ledger.sqlite3'):
        source = DATA / name
        if source.exists():
            (root / name).symlink_to(source)
    return root


def repair_preflight():
    """Read-only on-server source diagnosis; no G2B requests or writes to RFP data."""
    result = {'checkedAt': dt.datetime.now(dt.timezone.utc).isoformat()}
    required = ('rfp-top500-batch-state-20261111.json',
                'rfp-top500-batch-metadata-20261111.json',
                'changcom-actionable.json',
                'rfp-coverage-index.json')
    result['checkpointFiles'] = {name: (SEEDS / name).is_file() for name in required}
    try:
        with tempfile.TemporaryDirectory(prefix='worklinks-rfp-preflight-', dir=str(DATA)) as temp:
            root = stage_workspace(Path(temp))
            cmd = [sys.executable,
                   str(root / 'scripts' / 'repair_changcom_top500_rfp.py'),
                   '--data-dir', str(root)]
            completed = subprocess.run(cmd, cwd=str(root),
                                       capture_output=True, text=True, timeout=150,
                                       env=dict(os.environ, WORKLINKS_G2B_API=SOURCE_API))
            if completed.returncode:
                lines = (completed.stderr or completed.stdout or '').strip().splitlines()
                return dict(result, status='failed',
                            failureReason=(lines[-1][:220] if lines else 'unknown_exit'),
                            exitCode=completed.returncode)
            lines = (completed.stdout or '').strip().splitlines()
            return dict(result, status='ok', summary=(lines[-1][:800] if lines else ''),
                        exitCode=completed.returncode)
    except Exception as exc:
        return dict(result, status='failed',
                    failureReason=type(exc).__name__ + ': ' + str(exc)[:180])


def run_once(kind, runner=None, _single=False):
    """Run one job in an isolated writable workspace, atomic publish on success."""
    dual_enabled=(os.environ.get('WORKLINKS_RFP_DUAL_QUEUE')=='1')
    if dual_enabled and kind in ('rfp','rfpRepair'):
        # Fail closed even if this function is invoked directly, bypassing
        # the outer scheduler's skip branch.
        raise RuntimeError('legacy_single_bid_metadata_job_disabled_in_dual_queue')
    if kind=='rfpUpgrade' and dual_enabled and runner is None:
        # Waiting on original downloads must NOT create an expensive 80MB
        # staged scan workspace, nor report the full backlog as complete.
        sys.path.insert(0,str(SCRIPTS))
        from rfp_dual_queue import RfpDualQueue
        q=RfpDualQueue(DATA/'rfp-dual-queue.sqlite3')
        q.reconcile_legacy_ready()
        q.recover_stale_scans()
        if q.ready_count()==0:
            counters=q.stats()
            if counters['total'] and counters['scan']['done']==counters['total']:
                return False
            log('RFP_DUAL_WAIT_ORIGINALS',
                counters['download']['done'],counters['download']['total'],
                counters['scan']['done'],counters['scan']['total'])
            return 'download_wait'
    if kind not in PUBLISHED:
        raise ValueError('unknown_pipeline_kind')
    if kind == 'rfpOpenRepair' and runner is None and not _single:
        # Publish every small batch independently. A later slow OCR file
        # cannot erase the already verified, completed repair batches.
        for batch in range(7):
            more=run_once(kind,runner=None,_single=True)
            log('PIPELINE_RFP_OCR_BATCH_COMMITTED',batch+1,'more',bool(more))
            if not more:break
        return True
    with tempfile.TemporaryDirectory(prefix='worklinks-pipeline-', dir=str(DATA)) as tmp:
        root = stage_workspace(Path(tmp),minimal=(kind=='rfpOpenRepair'))
        env = dict(os.environ, WORKLINKS_G2B_API=SOURCE_API,
                   WORKLINKS_RFP_ROLE_PRIORITY_KEYS=RFP_STAFFING_PRIORITY_KEYS,
                   WORKLINKS_RFP_LEDGER_DB=str(DATA/'rfp-request-ledger.sqlite3'),
                   WORKLINKS_RFP_NOTICE_PROGRESS_DB=str(DATA/'rfp-notice-progress.sqlite3'))
        if kind in ('rfpUpgrade','rfpOpenRepair'):
            # Both stage-3 readers use the actual persistent stage-2 queue;
            # the isolated repair workspace does not contain this SQLite DB.
            env['WORKLINKS_RFP_DUAL_QUEUE_DB']=str(DATA/'rfp-dual-queue.sqlite3')
        if kind=='rfpUpgrade' and dual_enabled:
            env['WORKLINKS_RFP_DUAL_SCAN_ONLY']='1'
        if kind=='rfpUpgrade' and dual_enabled:
            # Limit each source extractor, not just the entire eight-notice batch.
            env['WORKLINKS_RFP_EXTRACT_TIMEOUT_SECONDS']='12'
        elif kind=='rfpOpenRepair':
            # Slow full-fidelity OCR gets its own generous but finite budget.
            env['WORKLINKS_RFP_EXTRACT_TIMEOUT_SECONDS']='90'
        if kind in ('rfp','rfpUpgrade'):
            # OCR repair remains full-fidelity, but the bulk scanner never
            # holds every other notice behind multi-page Tesseract.
            env['WORKLINKS_RFP_DEFER_OCR']='1'
        if kind == 'rfp':
            command = [sys.executable, str(root / 'scripts' / 'refresh_worklinks_rfp.py'),
                       '--limit', str(RFP_LIMIT)]
        elif kind == 'rfpUpgrade':
            env['WORKLINKS_RFP_UPGRADE_ONLY']='1'
            env['WORKLINKS_RFP_ROLE_PRIORITY_KEYS']=''
            command = [sys.executable, str(root / 'scripts' / 'refresh_worklinks_rfp.py'),
                       '--limit', str(RFP_UPGRADE_LIMIT)]
        elif kind == 'qualification':
            command = [sys.executable, str(root / 'scripts' / 'analyze_worklinks_rfp_ai.py'),
                       '--input', str(root / 'startup-support' / 'rfp-clauses.json'),
                       '--summary', str(root / 'startup-support' / 'qualification-review.json'),
                       '--summary-only', '--rule-based', '--limit', str(QUALIFICATION_BATCH)]
        elif kind == 'rfpOpenRepair':
            command = [sys.executable, str(root / 'scripts' / 'repair_open_rfp_cached_attachments.py'),
                       '--data-dir', str(root), '--limit', str(min(4,RFP_OPEN_OCR_LIMIT)),
                       '--max-files', str(min(8,RFP_OPEN_OCR_LIMIT * 2)), '--execute']
        elif kind == 'rfpRepair':
            command = [sys.executable, str(root / 'scripts' / 'repair_changcom_top500_rfp.py'),
                       '--data-dir', str(root), '--limit', str(RFP_REPAIR_LIMIT), '--execute']
        elif kind == 'awardFallback':
            command = [sys.executable, str(root / 'scripts' / 'refresh_worklinks_open_award_fallback.py')]
        else:
            command = [sys.executable, str(root / 'scripts' / 'refresh_worklinks_actionable.py')]
        if runner is None:
            runner = subprocess.run
        completed = runner(command, cwd=str(root), env=env,
                           capture_output=True, text=True, timeout=TIMEOUT[kind])
        for line in (completed.stdout or '').splitlines()[-15:]:
            log('PIPELINE_LOG', kind, line[:400])
        if completed.returncode != 0:
            log('PIPELINE_FAILED', kind, 'exit', completed.returncode,
                'tail', (completed.stderr or '')[-300:].replace('\n', ' '))
            details = (completed.stderr or completed.stdout or '').strip().splitlines()
            reason = details[-1][:130] if details else 'missing_child_diagnostics'
            raise RuntimeError('pipeline_' + kind + '_failed: ' + reason)
        if kind=='rfpUpgrade' and dual_enabled and 'RFP_DUAL_SCAN_NO_READY' in (completed.stdout or ''):
            return 'download_wait'
        if kind=='rfpUpgrade' and 'RFP_UPGRADE_SELECT_COUNT 0' in (completed.stdout or ''):
            if ('SAVED_NOTICE_DISCOVERY_UNAVAILABLE' in (completed.stdout or '') or
                    'RFP_DISCOVER_SERVER_ERROR' in (completed.stdout or '')):
                raise RuntimeError('upgrade_discovery_unavailable')
            log('PIPELINE_RFP_UPGRADE_QUEUE_DRAINED')
            return False
        outputs = [root / ('snapshots' if kind in ('rfpRepair','rfpOpenRepair') else 'startup-support') / name
                   for name in PUBLISHED[kind]]
        repaired_keys=[]
        for result in outputs:
            if result.name!='rfp-coverage-index.json':continue
            if kind=='rfpOpenRepair':
                staged=json.loads(result.read_text(encoding='utf-8')).get('byNotice') or {}
                earlier=json.loads((SEEDS/'rfp-coverage-index.json').read_text(encoding='utf-8')).get('byNotice') or {}
                repaired_keys=[key for key,item in staged.items() if isinstance(item,dict) and
                    str(item.get('checkedAt') or '')>str((earlier.get(key) or {}).get('checkedAt') or '')]
            merge_rfp_coverage_before_publish(result)
        quality_guard(kind, outputs)
        for result in outputs:
            publish_atomic(result, SEEDS / result.name)
        if kind=='rfpOpenRepair' and repaired_keys:
            publish_verified_repair_checkpoints(repaired_keys)
        if kind=='rfpUpgrade' and dual_enabled:
            # Mark scans finished ONLY after both validated archives are
            # durably published. An interrupted publish is always retryable.
            from rfp_dual_queue import RfpDualQueue, scan_evidence_signature
            from rfp_management_reconcile import read_evidence
            queue=RfpDualQueue(DATA/'rfp-dual-queue.sqlite3')
            authoritative_versions,authoritative_evidence=read_evidence(DATA)
            published=json.loads((SEEDS/'rfp-coverage-index.json').read_text('utf-8'))
            saved=published.get('byNotice') or {}
            versions=None
            for line in (completed.stdout or '').splitlines():
                if not line.startswith('RFP_DUAL_SCAN_RESULT '):continue
                records=json.loads(line.split(' ',1)[1])
                for record in records:
                    key=str(record.get('key') or '')
                    if re.fullmatch(r'(?:R\d{2}BK\d{8}|\d{11}):\d{3}',key):
                        if record.get('redownload') is True:
                            queue.mark_download_missing(key)
                        else:
                            # Current scan checkpoint may already contain a later
                            # verified OCR repair of these exact files.
                            verified=authoritative_evidence.get(key) or {}
                            versions=authoritative_versions
                            ok=bool(record.get('ok')) or rfp_coverage_complete(verified,versions)
                            row=verified if ok else (saved.get(key) or {})
                            if not ok and versions is None:
                                versions=deployed_rfp_reader_versions()
                            reason='' if ok else scan_failure_diagnosis(row,versions)
                            committed=queue.scan_finished(key,ok,reason,
                                                scan_evidence_signature(row) if not ok else '')
                            if committed:sync_scan_retry_activity(queue,key)
                            if not ok:
                                log('RFP_SCAN_RETRY_CAUSE',key,reason)
        if kind=='rfpOpenRepair' and dual_enabled:
            # A published OCR repair may complete a previously failed notice.
            # Reconcile now, not only on the independent 10-minute discovery.
            from rfp_dual_queue import RfpDualQueue
            from rfp_management_reconcile import read_evidence, management_scope
            queue=RfpDualQueue(DATA/'rfp-dual-queue.sqlite3')
            versions,evidence=read_evidence(DATA)
            reopened=queue.reopen_changed_scan_evidence(evidence)
            managed,valid=management_scope(DATA)
            fingerprint=':'.join(str(versions[k]) for k in
                ('classificationVersion','hwpxReaderVersion',
                 'staffingRoleScanVersion','staffingFactScanVersion'))
            tally=queue.reconcile_management(managed,valid,fingerprint)
            log('RFP_SCAN_POST_REPAIR_RECONCILED',
                json.dumps({'newEvidenceReopened':reopened,
                   'validCompleted':tally['completedEvidenceReconciled']},
                   separators=(',',':')))
        log('PIPELINE_PUBLISHED', kind,
            'outputs', ','.join(result.name for result in outputs))
        if kind=='rfpOpenRepair' and _single:
            # Dry-run plan is source-derived and no upstream bid-metadata API
            # was called; stop cycles when no repairable notice is left.
            for line in (completed.stdout or '').splitlines():
                if line.startswith('OPEN_RFP_CACHED_REPAIR_PLAN '):
                    try:
                        plan=json.loads(line.split(' ',1)[1])
                        return int(plan.get('selectedNotices') or 0)>0
                    except ValueError:
                        break
    return True


def iteration(current=None, runner=None):
    now = float(time.time() if current is None else current)
    state = read_state()
    # Periodic tasks remain scheduled. Triggered RFP drain continues as soon
    # as the previous successful batch atomically publishes its checkpoint.
    jobs = (('rfp', RFP_PERIOD), ('rfpUpgrade', RFP_UPGRADE_PERIOD), ('actionable', SHORTLIST_PERIOD),
            ('awardFallback', AWARD_FALLBACK_PERIOD),
            ('rfpOpenRepair', RFP_OPEN_OCR_PERIOD), ('rfpRepair', RFP_REPAIR_PERIOD),
            ('qualification', QUALIFICATION_PERIOD))
    for kind, period in jobs:
        prior = state.get(kind) or {}
        # The scanner and OCR repair share a serial snapshot publisher.
        # A bounded cached-original OCR pass is fair after four scan batches,
        # even while the normal scan queue remains continuously active.
        if (os.environ.get('WORKLINKS_RFP_DUAL_QUEUE')=='1'
                and kind in ('rfp','rfpRepair')):
            # Legacy RFP and frozen top500 repair use bid-evidence per notice.
            # The split queue + period-batched manifest replaces those paths.
            # Keep cached-file OCR repair, which uses zero upstream metadata calls.
            continue
        ocr_due_to_batches=False
        ocr_due_idle=False
        if kind in ('rfpOpenRepair','rfpRepair') and state.get('rfpUpgradeActive') is True:
            # Legacy top500 repair is excluded from the independent scan lane.
            if kind=='rfpRepair':
                continue
            drain_status=str((state.get('rfpUpgrade') or {}).get('status') or '')
            if drain_status=='started':
                continue
            completed=int(state.get('rfpUpgradeBatchesCompleted') or 0)
            previous_repair=int(state.get('rfpOpenRepairUpgradeBatch') or 0)
            ocr_due_to_batches=(completed-previous_repair>=RFP_OCR_SCAN_BATCH_INTERVAL)
            last_attempt=float(prior.get('attemptEpoch') or 0)
            ocr_due_idle=(drain_status in ('waiting_for_download','no_eligible_now','failed')
                          and now-last_attempt>=RFP_OCR_IDLE_PERIOD)
            # One local-only repair slice between scan batches, or every two
            # minutes while the main scan is blocked on retry/eligibility.
            if not (ocr_due_to_batches or ocr_due_idle):
                continue
        if kind=='rfpUpgrade':
            if state.get('rfpUpgradeActive') is not True:continue
            # A successful batch never waits for the clock. A failed batch or
            # temporarily empty eligible queue respects its persisted retry time.
            if now < float(prior.get('retryAfterEpoch') or 0):continue
        else:
            previous=float(prior.get('attemptEpoch') or 0)
            if now - previous < period and not (ocr_due_to_batches or ocr_due_idle):continue
        entry = {'attemptEpoch': now, 'status': 'started'}
        state[kind] = entry
        publish_state(state)
        try:
            more=run_once(kind, runner=runner,
                _single=(kind=='rfpOpenRepair' and state.get('rfpUpgradeActive') is True))
            finished=time.time()
            if kind=='rfpUpgrade':
                state['rfpUpgradeBatchesCompleted']=int(state.get('rfpUpgradeBatchesCompleted') or 0)+(1 if more is True else 0)
                if more=='download_wait':
                    entry.update(status='waiting_for_download',successEpoch=finished,
                                 retryAfterEpoch=finished+5)
                    log('PIPELINE_RFP_WAIT_DOWNLOADER',5,'seconds')
                elif more is False:
                    # No eligible item *now* does not mean the 2k+ remaining
                    # notices are complete: some may need official-file retry.
                    entry.update(status='no_eligible_now',successEpoch=finished,
                                 retryAfterEpoch=finished+RFP_UPGRADE_PERIOD)
                    log('PIPELINE_RFP_NO_ELIGIBLE_NOW_RECHECK',RFP_UPGRADE_PERIOD)
                else:
                    entry.update(status='ok',successEpoch=finished)
                    log('PIPELINE_RFP_CONTINUE_NEXT_BATCH',state['rfpUpgradeBatchesCompleted'])
            else:
                entry.update(status='ok',successEpoch=finished)
        except Exception as error:
            message=type(error).__name__ + ': ' + str(error)[:180]
            entry.update(status='failed', error=message)
            if kind=='rfpUpgrade':
                streak=int(prior.get('failureStreak') or 0)+1
                upper=message.upper()
                # Do not overload government endpoints when quotas or a
                # transient outage have been explicitly observed.
                delay=(21600 if 'DAILY_QUOTA' in upper or 'DAILY_COOLDOWN' in upper
                       else 300 if 'RATE_LIMIT' in upper or 'TRANSIENT_LIMIT' in upper
                       else min(3600,60*2**min(streak,5)))
                entry.update(failureStreak=streak,retryAfterEpoch=time.time()+delay)
                log('PIPELINE_RFP_DRAIN_BACKOFF',delay,'seconds',message)
            log('PIPELINE_JOB_RETRY_NEXT_CYCLE', kind, entry['error'])
        if kind=='rfpOpenRepair' and state.get('rfpUpgradeActive') is True:
            state['rfpOpenRepairUpgradeBatch']=int(state.get('rfpUpgradeBatchesCompleted') or 0)
        state[kind] = entry
        publish_state(state)
    return state



def prune_rfp_archive(*,compact=True):
    """Periodic bounded cleanup of source binaries, independent from RFP scans.

    Deadline metadata comes from the same local saved-notice inventory used by
    the scanner; unknown deadlines get a bounded age-based fallback in ledger.
    """
    sys.path.insert(0,str(SCRIPTS))
    from rfp_call_ledger import CallLedger
    db_path=DATA/'bids.sqlite3'
    deadlines={}
    latest_by_no={}
    if db_path.is_file():
        with sqlite3.connect('file:'+str(db_path)+'?mode=ro',
                             uri=True,timeout=15) as db:
            columns={x[1] for x in db.execute('PRAGMA table_info(bid_notices)')}
            query=("SELECT bid_no,bid_ord,payload FROM bid_notices"
                   if {'bid_no','bid_ord'}.issubset(columns)
                   else "SELECT NULL,NULL,payload FROM bid_notices")
            for bid_no,bid_ord,payload in db.execute(query):
                try:notice=json.loads(payload)
                except (TypeError,ValueError):continue
                no=str(bid_no or notice.get('bidNo') or '')
                ordinal=str(bid_ord or notice.get('order') or '0').zfill(3)
                status=str(notice.get('noticeKind') or notice.get('state') or '')
                number=int(ordinal)
                if no not in latest_by_no or number>latest_by_no[no][0]:
                    latest_by_no[no]=(number,bool(re.search('취소|철회|폐기',status)))
                raw=str(notice.get('closes') or '')
                match=re.search(r'(20\d{2})[-./]?(\d{2})[-./]?(\d{2})',raw)
                if not match:continue
                try:date=dt.date(*(int(x) for x in match.groups()))
                except ValueError:continue
                key=no+':'+ordinal
                if key not in deadlines or date>deadlines[key]:
                    deadlines[key]=date
    grace=int(os.environ.get('WORKLINKS_RFP_ARCHIVE_GRACE_DAYS','0'))
    unknown=int(os.environ.get('WORKLINKS_RFP_ARCHIVE_UNKNOWN_DAYS','30'))
    ledger=CallLedger(DATA/'rfp-request-ledger.sqlite3')
    cancelled={no for no,(ordinal,is_cancelled) in latest_by_no.items()
               if is_cancelled}
    report=ledger.prune_expired(
        deadlines,grace_days=grace,unknown_days=unknown,compact=compact,
        cancelled_notice_numbers=cancelled)
    log('RFP_ARCHIVE_RETENTION',json.dumps(
        {'mappedNoticeDeadlines':len(deadlines),'cancelledNumbers':len(cancelled),
         'graceDays':grace,'unknownDays':unknown,**report},separators=(',',':')))
    return report



def ensure_independent_downloader(current):
    """Keep one separate long-lived download PROCESS alive through scan cycles."""
    enabled=(os.environ.get('WORKLINKS_RFP_DUAL_QUEUE')=='1' and
             current.get('rfpUpgradeActive') is True)
    if not enabled:return None
    source=SCRIPTS/'rfp_download_worker.py'
    if not source.is_file():raise RuntimeError('rfp_download_worker_missing')
    global _RFP_DOWNLOAD_PROCESS,_RFP_DOWNLOAD_LAST_LAUNCH
    if _RFP_DOWNLOAD_PROCESS is not None and _RFP_DOWNLOAD_PROCESS.poll() is None:
        return _RFP_DOWNLOAD_PROCESS.pid
    if time.monotonic()-_RFP_DOWNLOAD_LAST_LAUNCH<10:return None
    env=dict(os.environ,WORKLINKS_G2B_API=SOURCE_API,
             G2B_PIPELINE_DATA=str(DATA),G2B_PIPELINE_SCRIPTS=str(SCRIPTS),
             WORKLINKS_RFP_UPGRADE_ONLY='1',WORKLINKS_RFP_DEFER_OCR='1',
             WORKLINKS_RFP_LEDGER_DB=str(DATA/'rfp-request-ledger.sqlite3'),
             WORKLINKS_RFP_DOWNLOAD_CONCURRENCY='8',
             WORKLINKS_RFP_BATCH_MANIFESTS='1')
    logpath=DATA/'rfp-download-worker.log'
    if logpath.is_file() and logpath.stat().st_size>8*1048576:
        os.replace(logpath,DATA/'rfp-download-worker.previous.log')
    with logpath.open('a') as stream:
        _RFP_DOWNLOAD_PROCESS=subprocess.Popen(
            [sys.executable,'-u',str(source)],
            cwd=str(DATA),env=env,stdout=stream,stderr=subprocess.STDOUT)
    _RFP_DOWNLOAD_LAST_LAUNCH=time.monotonic()
    log('RFP_DOWNLOAD_PROCESS_STARTED','pid',_RFP_DOWNLOAD_PROCESS.pid)
    return _RFP_DOWNLOAD_PROCESS.pid

_RFP_DOWNLOAD_PROCESS=None
_RFP_DOWNLOAD_LAST_LAUNCH=-100

def supervise_independent_downloader(stop=None):
    """Reap and restart the downloader even when a scanner iteration blocks.

    Scanner work can occupy iteration() for many minutes. The downloader must
    have its own independent supervision loop, not wait for the scan loop.
    Only this thread owns downloader process creation.
    """
    while stop is None or not stop.is_set():
        try:
            ensure_independent_downloader(read_state())
        except (OSError,RuntimeError,ValueError) as error:
            log('RFP_DOWNLOADER_SUPERVISOR_RETRY',
                type(error).__name__,str(error)[:180])
        if stop is None:
            time.sleep(5)
        elif stop.wait(5):
            break


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    SEEDS.mkdir(parents=True, exist_ok=True)
    lock_path = DATA / 'pipeline-scheduler.lock'
    with lock_path.open('a') as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log('PIPELINE_LOCK_HELD_EXIT')
            return 1
        if os.environ.get('WORKLINKS_RFP_DUAL_QUEUE')=='1':
            # A restarted exclusive scheduler has no surviving owned scanner.
            # Reclaim interrupted scans immediately rather than trapping
            # downloaded originals in 'scanning' for the 40-minute stale TTL.
            sys.path.insert(0,str(SCRIPTS))
            from rfp_dual_queue import RfpDualQueue
            reclaimed=RfpDualQueue(DATA/'rfp-dual-queue.sqlite3').recover_stale_scans(seconds=0)
            if reclaimed:
                log('RFP_RECLAIM_INTERRUPTED_SCANS_AFTER_RESTART',reclaimed)
        # Exclusive lock means no other pipeline owner can be using these
        # temporary scan workspaces. Remove crash/deploy leftovers (often
        # hundreds of MB) before retrying interrupted work.
        for abandoned in DATA.glob('worklinks-pipeline-*'):
            if abandoned.is_symlink() or not abandoned.is_dir():
                continue
            if time.time()-abandoned.stat().st_mtime < 180:
                continue
            try:
                shutil.rmtree(abandoned)
                log('PIPELINE_INTERRUPTED_STAGE_REMOVED',abandoned.name)
            except OSError as exc:
                log('PIPELINE_INTERRUPTED_STAGE_CLEANUP_FAILED',
                    abandoned.name,type(exc).__name__)
        if not (SCRIPTS / 'refresh_worklinks_actionable.py').is_file():
            raise RuntimeError('pipeline_scripts_missing')
        state = read_state()
        # Deployed parser versions, not front-end page visits, trigger an
        # independent bounded upgrade queue with durable progress.
        current_versions=deployed_rfp_reader_versions()
        previous_versions=state.get('rfpDeployedReaderVersions')
        manifest={'ok':True,'schemaVersion':1,'latest':current_versions,
                  'generatedAt':dt.datetime.now(dt.timezone.utc).isoformat()}
        manifest_path=SEEDS/'rfp-scanner-versions.json'
        if previous_versions!=current_versions or not manifest_path.is_file():
            with tempfile.TemporaryDirectory(prefix='rfp-reader-versions-',dir=str(DATA)) as temp:
                staged=Path(temp)/'rfp-scanner-versions.json'
                staged.write_text(json.dumps(manifest,ensure_ascii=False)+'\n',encoding='utf-8')
                publish_atomic(staged,manifest_path)
            state['rfpDeployedReaderVersions']=current_versions
            state['rfpUpgradeActive']=True
            state['rfpUpgrade']={'status':'parser_versions_upgraded','attemptEpoch':0}
            state['rfp']={'status':'parser_versions_upgraded','attemptEpoch':0}
            log('PIPELINE_PARSER_UPGRADE_QUEUE_CREATED',current_versions)
        # A source-only queue change does not alter parser field versions.
        # Discard an old "no eligible" cooldown on this deploy so the
        # newly supported first-time SW backlog starts draining immediately.
        if state.get('rfpDrainAlgorithmVersion')!=RFP_DRAIN_ALGORITHM_VERSION:
            state['rfpDrainAlgorithmVersion']=RFP_DRAIN_ALGORITHM_VERSION
            state['rfpUpgradeActive']=True
            state['rfpUpgrade']={'status':'drain_algorithm_upgraded','attemptEpoch':0,
                                 'retryAfterEpoch':0,'failureStreak':0}
            log('PIPELINE_RFP_DRAIN_ALGORITHM_ACTIVATED',RFP_DRAIN_ALGORITHM_VERSION)
        state['rfpUpgradePeriodSeconds']=RFP_UPGRADE_PERIOD
        state['rfpRegularPeriodSeconds']=RFP_PERIOD
        # A "started" entry from disk can only belong to a process that
        # terminated before publishing its result; this worker owns the
        # exclusive scheduler lock. Re-run immediately, never treat it as
        # a successful cooldown after a restart/deployment.
        for kind in PUBLISHED:
            entry=state.get(kind) or {}
            if entry.get('status')=='started':
                state[kind]={'status':'interrupted_retry_on_restart',
                             'attemptEpoch':0,
                             'interruptedAttemptEpoch':entry.get('attemptEpoch')}
                log('PIPELINE_INTERRUPTED_JOB_RETRY_IMMEDIATE',kind)
        # Each new OCR reader version gets one immediate on-server repair pass.
        # The file-level version gate prevents repeat downloads afterwards.
        if state.get('rfpOpenReaderVersion') != RFP_OPEN_READER_VERSION:
            state['rfpOpenReaderVersion'] = RFP_OPEN_READER_VERSION
            state['rfpOpenRepair'] = {'status':'reader_version_changed_run_now',
                                      'attemptEpoch':0}
        if state.get('rfpStaffingReaderVersion') != RFP_STAFFING_READER_VERSION:
            # Keep existing completed/partial RFP evidence, but have the
            # scheduler perform exactly one bounded pass with the new role
            # parser immediately after deployment. This uses normal quota
            # preflight and the existing exclusive worker lock.
            state['rfpStaffingReaderVersion'] = RFP_STAFFING_READER_VERSION
            state['rfp'] = {'status':'staffing_parser_upgrade_run_now',
                            'attemptEpoch':0}
            log('PIPELINE_STAFFING_ROLE_UPGRADE_RESCAN_ENQUEUED',
                RFP_STAFFING_READER_VERSION)
        # A previous attempt may have failed because the new parser module was
        # absent from staged workspaces. Now that it is deployed, retry this
        # bounded RFP batch immediately instead of retaining the hourly cooldown.
        failed_rfp=state.get('rfp') or {}
        if (failed_rfp.get('status')=='failed' and
                "No module named 'staffing_facts'" in str(failed_rfp.get('error') or '') and
                (SCRIPTS / 'staffing_facts.py').is_file()):
            state['rfp']={'status':'retry_after_staffing_module_restored',
                          'attemptEpoch':0,
                          'previousFailure':str(failed_rfp.get('error') or '')[:180]}
            log('PIPELINE_STAFFING_MODULE_RESTORED_RETRY_NOW')
        state['rfpRepairPreflight'] = repair_preflight()
        # After a new worker deployment, retry one previously failed repair
        # immediately ONLY when a fresh read-only preflight succeeds.
        if (state['rfpRepairPreflight'].get('status') == 'ok' and
                (state.get('rfpRepair') or {}).get('status') == 'failed'):
            state['rfpRepairRetryAfterDeploy'] = {
                'requestedAt': dt.datetime.now(dt.timezone.utc).isoformat(),
                'previousFailure': (state.get('rfpRepair') or {}).get('error', '')
            }
            state['rfpRepair'] = {'status': 'retry_after_verified_preflight',
                                  'attemptEpoch': 0}
        publish_state(state)
        log('PIPELINE_REPAIR_PREFLIGHT', state['rfpRepairPreflight'])
        log('PIPELINE_SERVER123_STARTED', 'rfpPeriod', RFP_PERIOD,
            'rfpUpgradePeriod', RFP_UPGRADE_PERIOD, 'rfpUpgradeLimit', RFP_UPGRADE_LIMIT,
            'shortlistPeriod', SHORTLIST_PERIOD, 'openAwardPeriod', AWARD_FALLBACK_PERIOD,
            'rfpLimit', RFP_LIMIT, 'rfpRepairLimit', RFP_REPAIR_LIMIT,
            'rfpOpenOcrLimit', RFP_OPEN_OCR_LIMIT,
             'qualificationBatch', QUALIFICATION_BATCH)
        # Downloader supervision must not depend on slow stage-3 scans.
        downloader_watchdog=threading.Thread(
            target=supervise_independent_downloader,
            name='rfp-independent-downloader-supervisor',daemon=True)
        downloader_watchdog.start()
        log('RFP_INDEPENDENT_DOWNLOADER_SUPERVISOR_STARTED')
        last_archive_cleanup=0.0
        archive_cleanup_thread=None
        def safe_archive_cleanup(compact):
            try:prune_rfp_archive(compact=compact)
            except Exception as error:
                log('RFP_ARCHIVE_RETENTION_FAILED',type(error).__name__)
        while True:
            state=iteration()
            # Keep scan health visible independently of the downloader.
            try:
                sys.path.insert(0,str(SCRIPTS))
                import rfp_live_activity as live_trace
                scan=(state.get('rfpUpgrade') or {})
                retry=float(scan.get('retryAfterEpoch') or 0)
                if scan.get('status')=='failed' or (retry and retry>time.time()):
                    live_trace.worker('scan','retry',str(scan.get('error') or scan.get('status') or ''),retry)
                else:live_trace.worker('scan','running')
            except (ImportError,OSError,ValueError):pass
            # Archive maintenance is never allowed to block the continuous
            # scanner; only one bounded cleanup job may run at a time.
            if (time.monotonic()-last_archive_cleanup>=3600 and
                    (archive_cleanup_thread is None or
                     not archive_cleanup_thread.is_alive())):
                drain_status=str((state.get('rfpUpgrade') or {}).get('status') or '')
                drain_busy=bool(state.get('rfpUpgradeActive') and drain_status=='ok')
                archive_cleanup_thread=threading.Thread(
                    target=safe_archive_cleanup,args=(not drain_busy,),
                    name='rfp-archive-retention',daemon=True)
                archive_cleanup_thread.start()
                last_archive_cleanup=time.monotonic()
            drain=state.get('rfpUpgrade') or {}
            # Continuous scan while candidates exist. Keep ordinary scheduled
            # jobs fair (one bounded RFP batch per loop) and never spin while
            # the upstream service is rate-limited or no items are eligible.
            time.sleep(1 if (state.get('rfpUpgradeActive') is True and
                              drain.get('status') in ('ok','waiting_for_download')) else
                       15 if state.get('rfpUpgradeActive') is True else 90)


if __name__ == '__main__':
    sys.exit(main())
