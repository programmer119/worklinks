#!/usr/bin/env python3
"""Repair frozen G2B RFP batch without re-fetching already parsed documents."""
import argparse
import collections
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime as dt
from pathlib import Path
import urllib.parse

from batch_backfill_changcom_top500_rfp import load, atomic_json, merge_coverage, key_for, close_of
from rfp_call_ledger import CallLedger, cache_key, ledger_path
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
            or unreadable(row) > 0 or
            any(f.get('readable') is True and
                (f.get('sourceTextScanComplete') is False or
                 f.get('qualificationScanTruncated') is True)
                for f in (row.get('files') or [])))


def attempts(history, key):
    prior = history.get(key) or {}
    if (prior.get('classificationVersion') != CLASSIFICATION_VERSION or
            prior.get('hwpxReaderVersion') != HWPX_READER_VERSION):
        return 0
    return max(0, int(prior.get('count') or 0))


def frozen_targets(snap, state):
    """Identify the actual 500 notices, never silently replace moved shortlist members.

    The first backfill saved only the 334 missing scans and did not persist
    the original 500 keys. Recover from the on-server ranked shortlist only
    when every previously scanned key still belongs to its top 500.
    """
    original = state.get('scans') or {}
    saved = state.get('frozenNoticeKeys')
    if saved is not None:
        if (not isinstance(saved, list) or len(saved) != 500 or
                len(set(saved)) != 500 or not set(original).issubset(saved)):
            raise RuntimeError('FROZEN_500_CHECKPOINT_INVALID')
        return saved, 'saved_frozen_keys', []

    action = load(snap.parent / 'startup-support' / 'changcom-actionable.json')
    if not (isinstance(action, dict) and action.get('ok') is True and
            action.get('bizno') == '1308185973' and
            isinstance(action.get('bids'), list)):
        raise RuntimeError('FROZEN_500_SHORTLIST_SOURCE_UNAVAILABLE')
    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=9)))
    eligible = [item for item in action['bids']
                if item.get('deadlineState') != 'unknown' and close_of(item)
                and close_of(item) - now >= dt.timedelta(hours=24)]
    keys = [key_for(item) for item in eligible[:500]]
    if len(keys) != 500 or len(set(keys)) != 500:
        raise RuntimeError('FROZEN_500_SHORTLIST_NOT_UNIQUE_OR_SHORT')
    # The original one-shot batch persisted only the 334 new scans and no
    # immutable original 500-key cohort. A later shortlist can legitimately
    # change. Preserve ALL those records in a separate archive and explicitly
    # label this as a new current top-500 cohort (never call it original).
    missing_from_shortlist = sorted(set(original) - set(keys))
    return (keys, 'current_ranked_top500_after_unfrozen_initial_batch',
            missing_from_shortlist)


def bootstrap_scans(snap, keys, existing):
    """Reuse the full rolling detail, then the compact cumulative evidence."""
    archive = load(snap / 'rfp-coverage-index.json') or {}
    detail = load(snap / 'rfp-clauses.json') or {}
    compact = archive.get('byNotice') or {}
    full = detail.get('byNotice') or {}
    scans = dict(existing)
    from_detail = from_index = unknown = 0
    for key in keys:
        if key in scans:
            continue
        if isinstance(full.get(key), dict):
            scans[key] = full[key]
            from_detail += 1
        elif isinstance(compact.get(key), dict):
            scans[key] = compact[key]
            from_index += 1
        else:
            scans[key] = {'status': 'not_scanned', 'manifestComplete': False,
                          'files': [], 'reviewComplete': False}
            unknown += 1
    return scans, {'fromFullArchive': from_detail,
                   'fromCoverageIndex': from_index,
                   'notPreviouslyScanned': unknown}


def metadata_confirmed(row):
    if not isinstance(row,dict):
        return False
    attachment=row.get('attachments') or {}
    notice=row.get('noticeDocuments') or {}
    return (attachment.get('ok') is True and
            attachment.get('complete') is True and
            notice.get('ok') is True and
            notice.get('complete') is True)


def run(data_dir, execute=False, limit=48, workers=5, max_attempts=3):
    snap = Path(data_dir) / 'snapshots'
    state_path, meta_path = snap / STATE_NAME, snap / META_NAME
    state, meta = load(state_path), load(meta_path)
    if not (isinstance(state, dict) and state.get('ok') is True and
            isinstance(state.get('scans'), dict) and
            isinstance(meta, dict) and meta.get('ok') is True and
            isinstance(meta.get('byNotice'), dict)):
        raise RuntimeError('BATCH_REPAIR_SOURCE_CHECKPOINT_UNAVAILABLE')
    keys, identity_source, outdated_keys = frozen_targets(snap, state)
    previous_scans = state['scans']
    archived = dict(state.get('archivedOutOfScopeScans') or {})
    for key in outdated_keys:
        archived.setdefault(key, previous_scans[key])
    frozen_set = set(keys)
    current_scans = {key: row for key, row in previous_scans.items()
                     if key in frozen_set}
    scans, recovered = bootstrap_scans(snap, keys, current_scans)
    by_notice = dict(meta['byNotice'])
    history = dict(state.get('repairAttempts') or {})
    pending = [key for key in keys if incomplete(scans.get(key))]
    selected = [key for key in pending if attempts(history, key) < max_attempts][:limit]
    print('RFP_REPAIR_PLAN FROZEN', len(keys), 'SCAN_ROWS', len(scans),
          'RECOVERED', recovered, 'IDENTITY', identity_source,
          'ARCHIVED_OUT_OF_SCOPE', len(outdated_keys),
          'INCOMPLETE', len(pending),
          'QUEUED', len(selected), flush=True)
    if not execute:
        return {'ok': True, 'dryRun': True, 'frozen': len(keys),
                'recovered': recovered, 'identitySource': identity_source,
                'archivedOutOfScope': len(outdated_keys),
                'incomplete': len(pending), 'queued': selected}
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat()
    # This SQLite database is persistent outside isolated snapshots on server123.
    # Creating it is deliberately delayed until --execute (dry-run is read-only).
    ledger=CallLedger(ledger_path(data_dir))
    repaired = {}

    def repair(key):
        old = scans.get(key) or {}
        source = by_notice.get(key)
        live = None
        request_key=cache_key('bid_evidence',key)
        if metadata_confirmed(source):
            # Persist previously retrieved official metadata, without
            # claiming a historical upstream HTTP attempt took place now.
            if ledger.get_json(request_key) is None:
                ledger.save_json(request_key,source)
            ledger.record('notice_metadata',request_key,'existing_verified_reused',
                          notice_key=key)
        else:
            # A prior verified response can survive a snapshot interruption.
            cached=ledger.get_json(request_key,max_age_seconds=36*3600)
            if metadata_confirmed(cached):
                source=cached
                ledger.record('notice_metadata',request_key,'verified_cache_reused',
                              notice_key=key)
            else:
                no, order = key.rsplit(':', 1)
                live = fetch_json(BASE + 'bid-evidence?' +
                                  urllib.parse.urlencode({'bidNo': no, 'order': order}))
                if not metadata_confirmed(live):
                    ledger.record('notice_metadata',request_key,'metadata_unconfirmed',
                                  notice_key=key)
                    raise RuntimeError('OFFICIAL_METADATA_RECHECK_UNCONFIRMED')
                ledger.save_json(request_key,live)
                ledger.record('notice_metadata',request_key,'fresh_metadata_verified',
                              notice_key=key)
                source=live
        if not metadata_confirmed(source):
            raise RuntimeError('BATCH_REPAIR_METADATA_MISSING_OR_PARTIAL')
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
            ledger.record('repair_attempt',cache_key('repair',key),outcome,
                          notice_key=key,
                          detail='readable='+str(readable(scans.get(key) or {}))+
                                 ';unreadable='+str(unreadable(scans.get(key) or {})))
            history[key] = {'count': attempts(history, key) + 1,
                            'classificationVersion': CLASSIFICATION_VERSION,
                            'hwpxReaderVersion': HWPX_READER_VERSION,
                            'lastAttemptAt': timestamp, 'lastOutcome': outcome}

    state.update(ok=True, generatedAt=timestamp, scans=scans,
                 frozenNoticeKeys=keys, frozenIdentitySource=identity_source,
                 archivedOutOfScopeScans=archived,
                 repairAttempts=history)
    meta.update(ok=True, byNotice=by_notice, lastRepairMetadataCheckAt=timestamp)
    still_pending = [key for key in keys if incomplete(scans.get(key))]
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
        'targetSavedScans': len(scans), 'frozenTargetCount': len(keys),
        'frozenIdentitySource': identity_source, 'recoveredExisting': recovered,
        'archivedOutOfScopeCount': len(archived),
        'repairAttemptedThisRun': len(selected),
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
        'requestLedger': ledger.stats(),
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
