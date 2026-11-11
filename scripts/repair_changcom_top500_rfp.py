#!/usr/bin/env python3
"""Repair frozen G2B RFP batch without re-fetching already parsed documents."""
import argparse
import collections
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime as dt
from pathlib import Path
import urllib.parse

from batch_backfill_changcom_top500_rfp import load, atomic_json, merge_coverage
from refresh_worklinks_rfp import (
    BASE, fetch_json, process, CLASSIFICATION_VERSION, HWPX_READER_VERSION
)

STATE_NAME = 'rfp-top500-batch-state-20261111.json'
META_NAME = 'rfp-top500-batch-metadata-20261111.json'
REPORT_NAME = 'rfp-top500-repair-report-20261111.json'
RECHECK = {'no_official_attachment_metadata', 'metadata_not_confirmed',
           'metadata_fetch_failed', 'file_scan_failed'}


def readable(row):
    return sum(f.get('readable') is True for f in (row.get('files') or []))


def unreadable(row):
    return sum(f.get('readable') is not True for f in (row.get('files') or []))


def incomplete(row):
    if not isinstance(row, dict):
        return True
    if row.get('status') != 'text_extracted_requires_review':
        return True
    return (row.get('manifestComplete') is not True or not readable(row)
            or unreadable(row) > 0)


def attempts(history, key):
    prior = history.get(key) or {}
    if (prior.get('classificationVersion') != CLASSIFICATION_VERSION or
            prior.get('hwpxReaderVersion') != HWPX_READER_VERSION):
        return 0
    return max(0, int(prior.get('count') or 0))


def run(data_dir, execute=False, limit=48, workers=5, max_attempts=3):
    snap = Path(data_dir) / 'snapshots'
    state_path, meta_path = snap / STATE_NAME, snap / META_NAME
    state, meta = load(state_path), load(meta_path)
    if not (isinstance(state, dict) and state.get('ok') is True and
            isinstance(state.get('scans'), dict) and
            isinstance(meta, dict) and meta.get('ok') is True and
            isinstance(meta.get('byNotice'), dict)):
        raise RuntimeError('BATCH_REPAIR_SOURCE_CHECKPOINT_UNAVAILABLE')
    scans = dict(state['scans'])
    by_notice = dict(meta['byNotice'])
    history = dict(state.get('repairAttempts') or {})
    pending = [key for key, row in scans.items() if incomplete(row)]
    selected = [key for key in pending if attempts(history, key) < max_attempts][:limit]
    print('RFP_REPAIR_PLAN FROZEN', len(scans), 'INCOMPLETE', len(pending),
          'QUEUED', len(selected), flush=True)
    if not execute:
        return {'ok': True, 'dryRun': True, 'frozen': len(scans),
                'incomplete': len(pending), 'queued': selected}
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat()
    repaired = {}

    def repair(key):
        old = scans.get(key) or {}
        source = by_notice.get(key)
        live = None
        if old.get('status') in RECHECK or not isinstance(source, dict):
            no, order = key.rsplit(':', 1)
            live = fetch_json(BASE + 'bid-evidence?' +
                              urllib.parse.urlencode({'bidNo': no, 'order': order}))
            fields = live.get('attachments') or {}
            if fields.get('ok') is not True or fields.get('complete') is not True:
                raise RuntimeError('OFFICIAL_METADATA_RECHECK_UNCONFIRMED')
            source = live
        if not isinstance(source, dict):
            raise RuntimeError('BATCH_REPAIR_METADATA_MISSING')
        no, order = key.rsplit(':', 1)
        new = process(no, order, metadata=source, previous=old)
        if not isinstance(new, dict):
            raise RuntimeError('BATCH_REPAIR_INVALID_RESULT')
        new.update(checkedAt=timestamp, classificationVersion=CLASSIFICATION_VERSION,
                   hwpxReaderVersion=HWPX_READER_VERSION, reviewComplete=False)
        if readable(new) < readable(old):
            return old, live, 'prior_readable_preserved'
        return new, live, 'processed'

    with ThreadPoolExecutor(max_workers=max(1, min(8, workers))) as pool:
        jobs = {pool.submit(repair, key): key for key in selected}
        for job in as_completed(jobs):
            key = jobs[job]
            old = scans.get(key) or {}
            try:
                fresh, live, outcome = job.result()
                if live is not None:
                    by_notice[key] = live
                if fresh is not old:
                    scans[key] = fresh
                    repaired[key] = fresh
                print('RFP_REPAIR_RESULT', key, outcome, 'NEW_READABLE',
                      max(0, readable(fresh) - readable(old)),
                      'UNREADABLE', unreadable(fresh), flush=True)
            except Exception as error:
                outcome = 'retry_failed_' + type(error).__name__
                print('RFP_REPAIR_FAILED', key, outcome, str(error)[:100], flush=True)
            history[key] = {'count': attempts(history, key) + 1,
                            'classificationVersion': CLASSIFICATION_VERSION,
                            'hwpxReaderVersion': HWPX_READER_VERSION,
                            'lastAttemptAt': timestamp, 'lastOutcome': outcome}

    state.update(ok=True, generatedAt=timestamp, scans=scans, repairAttempts=history)
    meta.update(ok=True, byNotice=by_notice, lastRepairMetadataCheckAt=timestamp)
    still_pending = [key for key, row in scans.items() if incomplete(row)]
    blocked = [key for key in still_pending if attempts(history, key) >= max_attempts]
    statuses = collections.Counter(str(row.get('status') or 'unknown')
                                   for row in scans.values())
    errors = collections.Counter(
        str(f.get('errorCategory') or 'unclassified')
        for row in scans.values() for f in (row.get('files') or [])
        if f.get('readable') is not True)
    report = {
        'ok': True, 'generatedAt': timestamp,
        'scope': 'frozen_batch_document_repair',
        'completedDocumentReview': False, 'finalEligibilityVerified': False,
        'targetSavedScans': len(scans), 'repairAttemptedThisRun': len(selected),
        'updatedScanResults': len(repaired),
        'incompleteNoticeCount': len(still_pending),
        'stillEligibleForRetry': len(still_pending) - len(blocked),
        'attemptLimitReached': len(blocked),
        'officialNoAttachmentCount': statuses.get('no_official_attachment_metadata', 0),
        'readableDocumentCount': sum(readable(row) for row in scans.values()),
        'unreadableDocumentCount': sum(unreadable(row) for row in scans.values()),
        'sourceTextScanIncompleteNoticeCount': sum(any(
            f.get('readable') is True and (
                f.get('sourceTextScanComplete') is False or
                f.get('qualificationScanTruncated') is True)
            for f in (row.get('files') or [])) for row in scans.values()),
        'statuses': dict(statuses), 'failureCategories': dict(errors),
        'unresolvedNoticeKeys': still_pending,
        'warning': 'Metadata/parsed text does not prove legal bidder eligibility.'
    }
    # Scheduler operates on isolated snapshots and publishes all outputs
    # only after quality checks. A failed retry cannot regress the index.
    if repaired:
        merge_coverage(Path(data_dir), repaired, timestamp)
    atomic_json(state_path, state)
    atomic_json(meta_path, meta)
    atomic_json(snap / REPORT_NAME, report)
    print('RFP_REPAIR_SUMMARY ATTEMPTED', len(selected),
          'UNRESOLVED', len(still_pending), flush=True)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', default='/data')
    parser.add_argument('--limit', type=int, default=48)
    parser.add_argument('--workers', type=int, default=5)
    parser.add_argument('--max-attempts', type=int, default=3)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args(argv)
    return run(args.data_dir, args.execute, max(1, min(args.limit, 120)),
               args.workers, max(1, min(args.max_attempts, 6)))


if __name__ == '__main__':
    main()
