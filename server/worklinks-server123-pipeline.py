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
SHORTLIST_PERIOD = max(10800, int(os.environ.get('G2B_SHORTLIST_PERIOD', 10800)))
AWARD_FALLBACK_PERIOD = max(14400, int(os.environ.get('G2B_OPEN_AWARD_PERIOD', 14400)))
RFP_LIMIT = max(1, min(8, int(os.environ.get('G2B_RFP_BATCH', 8))))
RFP_REPAIR_PERIOD = max(3600, int(os.environ.get('G2B_RFP_REPAIR_PERIOD', 3600)))
RFP_REPAIR_LIMIT = max(1, min(120, int(os.environ.get('G2B_RFP_REPAIR_LIMIT', 48))))
READ_FILES = (
    'changcom-actionable.json',
    'g2b-award-fields-open.json',
    'rfp-clauses.json',
    'rfp-coverage-index.json',
    'changcom-bid-review.json',
    'sme-cert-snapshot.json',
    'direct-production-snapshot.json',
    'official-awards-snapshot.json',
    'audits/changcom-rfp-backfill-60-20261110.json',
    'audits/changcom-priority-rfp-recovery-20261111.json'
)
PUBLISHED = {
    'rfp': ('rfp-clauses.json', 'rfp-coverage-index.json'),
    'rfpRepair': ('rfp-clauses.json', 'rfp-coverage-index.json',
                  'rfp-top500-batch-state-20261111.json',
                  'rfp-top500-batch-metadata-20261111.json',
                  'rfp-top500-repair-report-20261111.json'),
    'actionable': ('changcom-actionable.json',),
    'awardFallback': ('g2b-award-fields-open.json',)
}
TIMEOUT = {'rfp': 2100, 'rfpRepair': 2100, 'actionable': 540, 'awardFallback': 540}


def log(*values):
    print(dt.datetime.now(dt.timezone.utc).isoformat(), *values, flush=True)


def read_state():
    try:
        result = json.loads(STATE.read_text(encoding='utf-8'))
        return result if isinstance(result, dict) else {}
    except (OSError, ValueError):
        return {}


def publish_atomic(src, destination):
    """Prepare gzip and JSON files before replace, never publish partial bytes."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.with_name('.' + destination.name + '.next')
    gzpath = Path(str(destination) + '.gz')
    gzstaging = gzpath.with_name('.' + gzpath.name + '.next')
    try:
        with src.open('rb') as inp, staging.open('wb') as out, gzip.open(gzstaging, 'wb', compresslevel=6) as zipped:
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
        if kind in ('rfp','rfpRepair') and path.name in ('rfp-clauses.json','rfp-coverage-index.json'):
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


def stage_workspace(path):
    root = path / 'worklinks'
    (root / 'scripts').mkdir(parents=True)
    for name in ('refresh_worklinks_rfp.py', 'refresh_worklinks_actionable.py',
                 'refresh_worklinks_open_award_fallback.py',
                 'batch_backfill_changcom_top500_rfp.py',
                 'repair_changcom_top500_rfp.py'):
        shutil.copy2(SCRIPTS / name, root / 'scripts' / name)
    for name in READ_FILES:
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
            shutil.copy2(source, dest)
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


def run_once(kind, runner=None):
    """Run one job in an isolated writable workspace, atomic publish on success."""
    if kind not in PUBLISHED:
        raise ValueError('unknown_pipeline_kind')
    with tempfile.TemporaryDirectory(prefix='worklinks-pipeline-', dir=str(DATA)) as tmp:
        root = stage_workspace(Path(tmp))
        env = dict(os.environ, WORKLINKS_G2B_API=SOURCE_API)
        if kind == 'rfp':
            command = [sys.executable, str(root / 'scripts' / 'refresh_worklinks_rfp.py'),
                       '--limit', str(RFP_LIMIT)]
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
        outputs = [root / ('snapshots' if kind == 'rfpRepair' else 'startup-support') / name
                   for name in PUBLISHED[kind]]
        quality_guard(kind, outputs)
        for result in outputs:
            publish_atomic(result, SEEDS / result.name)
        log('PIPELINE_PUBLISHED', kind,
            'outputs', ','.join(result.name for result in outputs))
    return True


def iteration(current=None, runner=None):
    now = float(time.time() if current is None else current)
    state = read_state()
    # Persistent timestamps, not sleep-only, protect against restart loops.
    jobs = (('actionable', SHORTLIST_PERIOD), ('awardFallback', AWARD_FALLBACK_PERIOD),
            ('rfp', RFP_PERIOD), ('rfpRepair', RFP_REPAIR_PERIOD))
    for kind, period in jobs:
        previous = float((state.get(kind) or {}).get('attemptEpoch') or 0)
        if now - previous < period:
            continue
        entry = {'attemptEpoch': now, 'status': 'started'}
        state[kind] = entry
        publish_state(state)
        try:
            run_once(kind, runner=runner)
            entry.update(status='ok', successEpoch=time.time())
        except Exception as error:
            entry.update(status='failed', error=type(error).__name__ + ': ' + str(error)[:180])
            log('PIPELINE_JOB_RETRY_NEXT_CYCLE', kind, entry['error'])
        state[kind] = entry
        publish_state(state)
    return state


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
        if not (SCRIPTS / 'refresh_worklinks_actionable.py').is_file():
            raise RuntimeError('pipeline_scripts_missing')
        state = read_state()
        state['rfpRepairPreflight'] = repair_preflight()
        publish_state(state)
        log('PIPELINE_REPAIR_PREFLIGHT', state['rfpRepairPreflight'])
        log('PIPELINE_SERVER123_STARTED', 'rfpPeriod', RFP_PERIOD,
            'shortlistPeriod', SHORTLIST_PERIOD, 'openAwardPeriod', AWARD_FALLBACK_PERIOD,
            'rfpLimit', RFP_LIMIT, 'rfpRepairLimit', RFP_REPAIR_LIMIT)
        while True:
            iteration()
            time.sleep(90)


if __name__ == '__main__':
    sys.exit(main())
