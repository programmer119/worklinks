#!/usr/bin/env python3
"""Server123's sole scheduler for Changcom shortlist and official RFP extraction.

No GitHub Actions schedules, no git push, and no new ports.
All outputs are served read-only by the existing G2B API from data/snapshots.
Existing GitHub snapshots are seed/fallback and are never deleted by this worker.
"""
import datetime as dt
import fcntl
import gzip
import json
import re
import sqlite3
import os
from pathlib import Path
import shutil
import subprocess
import sys
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
RFP_DRAIN_ALGORITHM_VERSION = 'per-notice-live-progress-v4-20261114'
SHORTLIST_PERIOD = max(10800, int(os.environ.get('G2B_SHORTLIST_PERIOD', 10800)))
AWARD_FALLBACK_PERIOD = max(14400, int(os.environ.get('G2B_OPEN_AWARD_PERIOD', 14400)))
RFP_LIMIT = max(1, min(8, int(os.environ.get('G2B_RFP_BATCH', 8))))
RFP_REPAIR_PERIOD = max(3600, int(os.environ.get('G2B_RFP_REPAIR_PERIOD', 3600)))
RFP_REPAIR_LIMIT = max(1, min(120, int(os.environ.get('G2B_RFP_REPAIR_LIMIT', 48))))
# Local OCR repair uses only stored source URLs, no government metadata API calls.
RFP_OPEN_OCR_PERIOD = max(900, int(os.environ.get('G2B_RFP_OPEN_OCR_PERIOD', 900)))
RFP_OPEN_READER_VERSION='pdf24-image-zip-hwpx-v3'
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
                 'rfp_call_ledger.py'):
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
        if kind=='rfpUpgrade' and 'RFP_UPGRADE_SELECT_COUNT 0' in (completed.stdout or ''):
            if ('SAVED_NOTICE_DISCOVERY_UNAVAILABLE' in (completed.stdout or '') or
                    'RFP_DISCOVER_SERVER_ERROR' in (completed.stdout or '')):
                raise RuntimeError('upgrade_discovery_unavailable')
            log('PIPELINE_RFP_UPGRADE_QUEUE_DRAINED')
            return False
        outputs = [root / ('snapshots' if kind in ('rfpRepair','rfpOpenRepair') else 'startup-support') / name
                   for name in PUBLISHED[kind]]
        quality_guard(kind, outputs)
        for result in outputs:
            publish_atomic(result, SEEDS / result.name)
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
        # Scanner and repair jobs share a single serial scheduler. Never let
        # 100s+ OCR/repair jobs stop the successful first-time scan queue.
        # Paused/empty drains may safely run repairs while scanning is idle.
        if kind in ('rfpOpenRepair','rfpRepair') and state.get('rfpUpgradeActive') is True:
            drain_status=str((state.get('rfpUpgrade') or {}).get('status') or '')
            if drain_status in ('started','ok','parser_versions_upgraded','drain_algorithm_upgraded'):
                continue
            if kind=='rfpOpenRepair' and drain_status!='no_eligible_now':
                completed=int(state.get('rfpUpgradeBatchesCompleted') or 0)
                previous_repair=int(state.get('rfpOpenRepairUpgradeBatch') or 0)
                if completed-previous_repair<12:continue
        if kind=='rfpUpgrade':
            if state.get('rfpUpgradeActive') is not True:continue
            # A successful batch never waits for the clock. A failed batch or
            # temporarily empty eligible queue respects its persisted retry time.
            if now < float(prior.get('retryAfterEpoch') or 0):continue
        else:
            previous=float(prior.get('attemptEpoch') or 0)
            if now - previous < period:continue
        entry = {'attemptEpoch': now, 'status': 'started'}
        state[kind] = entry
        publish_state(state)
        try:
            more=run_once(kind, runner=runner,
                _single=(kind=='rfpOpenRepair' and state.get('rfpUpgradeActive') is True))
            finished=time.time()
            if kind=='rfpUpgrade':
                state['rfpUpgradeBatchesCompleted']=int(state.get('rfpUpgradeBatchesCompleted') or 0)+(1 if more is not False else 0)
                if more is False:
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



def prune_rfp_archive():
    """Periodic bounded cleanup of source binaries, independent from RFP scans.

    Deadline metadata comes from the same local saved-notice inventory used by
    the scanner; unknown deadlines get a bounded age-based fallback in ledger.
    """
    sys.path.insert(0,str(SCRIPTS))
    from rfp_call_ledger import CallLedger
    db_path=DATA/'bids.sqlite3'
    deadlines={}
    if db_path.is_file():
        with sqlite3.connect('file:'+str(db_path)+'?mode=ro',
                             uri=True,timeout=15) as db:
            for (payload,) in db.execute(
                    "SELECT payload FROM bid_notices WHERE sw_candidate=1"):
                try:notice=json.loads(payload)
                except (TypeError,ValueError):continue
                no=str(notice.get('bidNo') or '')
                ordinal=str(notice.get('order') or '0').zfill(3)
                raw=str(notice.get('closes') or '')
                match=re.search(r'(20\d{2})[-./]?(\d{2})[-./]?(\d{2})',raw)
                if not match:continue
                try:date=dt.date(*(int(x) for x in match.groups()))
                except ValueError:continue
                key=no+':'+ordinal
                if key not in deadlines or date>deadlines[key]:
                    deadlines[key]=date
    grace=int(os.environ.get('WORKLINKS_RFP_ARCHIVE_GRACE_DAYS','7'))
    unknown=int(os.environ.get('WORKLINKS_RFP_ARCHIVE_UNKNOWN_DAYS','30'))
    ledger=CallLedger(DATA/'rfp-request-ledger.sqlite3')
    report=ledger.prune_expired(
        deadlines,grace_days=grace,unknown_days=unknown)
    log('RFP_ARCHIVE_RETENTION',json.dumps(
        {'mappedNoticeDeadlines':len(deadlines),'graceDays':grace,
         'unknownDays':unknown,**report},separators=(',',':')))
    return report


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
        last_archive_cleanup=0.0
        while True:
            state=iteration()
            if time.monotonic()-last_archive_cleanup>=3600:
                try:prune_rfp_archive()
                except (OSError,sqlite3.Error,ValueError) as error:
                    log('RFP_ARCHIVE_RETENTION_FAILED',type(error).__name__)
                last_archive_cleanup=time.monotonic()
            drain=state.get('rfpUpgrade') or {}
            # Continuous scan while candidates exist. Keep ordinary scheduled
            # jobs fair (one bounded RFP batch per loop) and never spin while
            # the upstream service is rate-limited or no items are eligible.
            time.sleep(1 if (state.get('rfpUpgradeActive') is True and
                              drain.get('status')=='ok') else
                       15 if state.get('rfpUpgradeActive') is True else 90)


if __name__ == '__main__':
    sys.exit(main())
