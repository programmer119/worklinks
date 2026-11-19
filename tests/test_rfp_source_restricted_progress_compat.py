#!/usr/bin/env python3
"""Protected originals remain separate from active scan work, including v1 tabs."""
import ast
import datetime
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
src = (root / 'server/g2b-proxy.py').read_text(encoding='utf-8')
parsed = ast.parse(src)
function = next(x for x in parsed.body
                if isinstance(x, ast.FunctionDef) and x.name == 'rfp_progress_from_rows')
now = datetime.datetime(2026, 11, 19, tzinfo=datetime.timezone(datetime.timedelta(hours=9)))
deadline = now + datetime.timedelta(days=5)

def checks(row, latest):
    ok = isinstance(row, dict) and row.get('done') is True
    return {'classification': ok, 'roles': ok, 'facts': ok, 'hwpx': None}

env = {
    'datetime': datetime, 'json': json, 're': re,
    'rfp_deadline_kst': lambda value: deadline,
    'rfp_stage_checks': checks,
}
exec(compile(ast.Module(body=[function], type_ignores=[]),
             'rfp_progress_from_rows', 'exec'), env)
progress = env['rfp_progress_from_rows']
versions = {'classificationVersion': 25, 'staffingRoleScanVersion': 4,
            'staffingFactScanVersion': 2, 'hwpxReaderVersion': 3,
            'ocrReaderVersion': 'v20'}
rows = [(key, '000', json.dumps({'closes': '2026-11-25'}))
        for key in ('FINISHED', 'RESTRICTED', 'EMPTY', 'PENDING')]
def row(done):
    return {'status': 'text_extracted_requires_review',
            'classificationVersion': 25, 'hwpxReaderVersion': 3,
            'files': [], 'done': done}
index = {'FINISHED:000': row(True), 'PENDING:000': row(False)}
report = progress(rows, index, versions, asof=now, include_scope=True,
                  excluded_keys={'EMPTY:000'},
                  restricted_keys={'RESTRICTED:000'})
counts = report['counts']
assert counts['total'] == 4, counts
assert counts['eligible'] == 2, counts
assert counts['completed'] == 1 and counts['remaining'] == 1, counts
assert counts['excluded'] == 2, counts
assert counts['excludedNoAttachments'] == 1, counts
assert counts['sourceRestricted'] == 1, counts
assert counts['total'] == counts['eligible'] + counts['excluded'], counts
assert counts['excluded'] == counts['excludedNoAttachments'] + counts['sourceRestricted']
assert report['stages']['roles']['total'] == 2
managed, completed = report['_cohortKeys']
assert managed == {key + ':000' for key in ('FINISHED','RESTRICTED','EMPTY','PENDING')}
assert completed == {'FINISHED:000'}
print('RFP_SOURCE_RESTRICTED_V1_COMPAT=PASS')
