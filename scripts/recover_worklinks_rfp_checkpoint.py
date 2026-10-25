#!/usr/bin/env python3
"""Recover a same-repository RFP scan checkpoint after a failed GitHub push."""
import json
from pathlib import Path
import sys
import zipfile

from refresh_worklinks_rfp import bounded_detail_snapshot, MAX_PUBLISHED_RFP_BYTES

ROOT = Path(__file__).resolve().parents[1]
DETAIL = ROOT / 'startup-support/rfp-clauses.json'
INDEX = ROOT / 'startup-support/rfp-coverage-index.json'


def newer_evidence(old, incoming):
    if not isinstance(old, dict):
        return incoming
    if not isinstance(incoming, dict):
        return old
    if (old.get('status') == 'text_extracted_requires_review'
            and incoming.get('status') != 'text_extracted_requires_review'):
        return old
    if str(old.get('checkedAt') or '') > str(incoming.get('checkedAt') or ''):
        return old
    return incoming


def combine(current, checkpoint, cumulative=False):
    existing = dict(current.get('byNotice') or {})
    changed = 0
    for key, item in (checkpoint.get('byNotice') or {}).items():
        if not isinstance(item, dict):
            continue
        prev = existing.get(key) or {}
        chosen = dict(newer_evidence(prev, item))
        if cumulative and prev:
            # An old scan's metadata timestamp can equal a NEW checkpoint's
            # source timestamp. Preserve the newest separately probed manifest,
            # especially a pending same-order attachment correction.
            previous_probe=str(prev.get('manifestCheckedAt') or '')
            incoming_probe=str(chosen.get('manifestCheckedAt') or '')
            if previous_probe > incoming_probe:
                for field in ('manifestSignature','manifestCheckedAt',
                              'manifestChangePending','manifestPendingSignature',
                              'manifestBaselineUnverified','lastManifestProbeStatus'):
                    if field in prev:
                        chosen[field]=prev[field]
                    else:
                        chosen.pop(field,None)
        if cumulative and prev.get('changcomClauseEvidence') and not chosen.get('changcomClauseEvidence'):
            chosen = {**chosen, 'changcomClauseEvidence': prev['changcomClauseEvidence']}
        if cumulative and chosen.get('status') == 'text_extracted_requires_review' and not chosen.get('files') and prev.get('files'):
            chosen = {**chosen, 'files': prev['files']}
        if chosen != prev:
            changed += 1
        existing[key] = chosen
    return existing, changed


def archive_documents(filename):
    with zipfile.ZipFile(filename) as archive:
        entries = archive.namelist()
        result = {}
        for basename, limit in [('rfp-clauses.json', 90_000_000),
                                ('rfp-coverage-index.json', 95_000_000)]:
            matches = [name for name in entries if name.rsplit('/', 1)[-1] == basename]
            if len(matches) != 1 or archive.getinfo(matches[0]).file_size > limit:
                raise ValueError('invalid_rfp_checkpoint_' + basename)
            with archive.open(matches[0]) as source:
                document = json.load(source)
            if document.get('ok') is not True or not isinstance(document.get('byNotice'), dict):
                raise ValueError('invalid_checkpoint_schema_' + basename)
            result[basename] = document
        return result


def recover(archive_path, detail_path=DETAIL, index_path=INDEX):
    checkpoint = archive_documents(archive_path)
    current_detail = json.loads(detail_path.read_text(encoding='utf-8'))
    current_index = json.loads(index_path.read_text(encoding='utf-8'))
    detail, detail_new = combine(current_detail, checkpoint['rfp-clauses.json'])
    index, index_new = combine(current_index, checkpoint['rfp-coverage-index.json'], cumulative=True)
    selected, omitted = bounded_detail_snapshot(detail)
    next_detail = {**current_detail, 'byNotice': selected,
                   'detailOmittedFromRollingCache': omitted}
    next_index = {**current_index, 'byNotice': index, 'scannedNoticeCount': len(index)}
    detail_text = json.dumps(next_detail, ensure_ascii=False, separators=(',', ':')) + '\n'
    index_text = json.dumps(next_index, ensure_ascii=False, indent=2) + '\n'
    if len(detail_text.encode('utf-8')) > MAX_PUBLISHED_RFP_BYTES:
        raise ValueError('checkpoint_detail_exceeds_safe_limit')
    if len(index_text.encode('utf-8')) >= 100_000_000:
        raise ValueError('checkpoint_index_exceeds_github_limit')
    json.loads(detail_text)
    json.loads(index_text)
    detail_path.write_text(detail_text, encoding='utf-8')
    index_path.write_text(index_text, encoding='utf-8')
    print('RFP_CHECKPOINT_RECOVERED',
          'DETAIL_UPDATED', detail_new, 'INDEX_UPDATED', index_new,
          'CUMULATIVE_SCANNED', len(index), 'OMITTED_FROM_ROLLING_CACHE', omitted,
          flush=True)
    return detail_new, index_new


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('usage: recover_worklinks_rfp_checkpoint.py <zip>')
    recover(sys.argv[1])
