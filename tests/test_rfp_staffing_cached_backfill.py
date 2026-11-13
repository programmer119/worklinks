#!/usr/bin/env python3
"""No-network integration fixture for the real cached staffing backfill runner."""
import hashlib
import json
from pathlib import Path
import runpy
import sqlite3
import tempfile
import zlib

root=Path(__file__).resolve().parents[1]
m=runpy.run_path(str(root/'scripts/backfill_worklinks_staffing_cached.py'),
                 run_name='rfp_staffing_backfill_fixture')
run=m['run']
global_vars=run.__globals__
old_reader=global_vars['extract_with_source_status']
raw=b'locally-verified-rfp-source'
sha=hashlib.sha256(raw).hexdigest()
key='R26BK01807134:000'
with tempfile.TemporaryDirectory() as tmp:
    base=Path(tmp)
    index=base/'rfp-coverage-index.json'
    detail=base/'rfp-clauses.json'
    ledger=base/'ledger.sqlite3'
    patch=base/'patch.json'
    report=base/'report.json'
    index.write_text(json.dumps({'ok':True,'generatedAt':'test',
      'byNotice':{key:{'status':'text_extracted_requires_review',
        'manifestComplete':True,'staffingRoleScanComplete':True,  # Staffing roles done; new condition facts missing.
        'files':[{'name':'투입인력계획서.pdf','staffingRoleScanVersion':4,
          'staffingFactScanVersion':0,
          'readable':True,'sourceSha256':sha,
          'sourceTextScanComplete':True}]}}},ensure_ascii=False))
    detail.write_text(json.dumps({'ok':True,'byNotice':{key:{'files':[
        {'name':'투입인력계획서.pdf','sourceSha256':sha,
         'sourceUrl':'https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/test'}]}}}))
    with sqlite3.connect(ledger) as db:
        db.execute('CREATE TABLE verified_cache (sha256 TEXT,media_type TEXT,payload BLOB)')
        db.execute('INSERT INTO verified_cache VALUES (?,?,?)',
                   (sha,'bytes',zlib.compress(raw)))
    calls=[]
    def local_reader(name,content):
        calls.append((name,content))
        assert content==raw
        return '투입인력 계획\n직무 | 등급 | 투입인원\nPM | 고급 | 1\n개발자 | 중급 | 2',{'sourceComplete':True}
    global_vars['extract_with_source_status']=local_reader
    try:
        output=run(index,detail,ledger,patch,report,max_files=5,max_seconds=30)
    finally:
        global_vars['extract_with_source_status']=old_reader
    result=json.loads(patch.read_text())
    change=result['updates'][key]
    assert output['officialFileDownloads']==0 and output['governmentApiCalls']==0,output
    assert output['filesReparsed']==1 and output['noticePatches']==1,output
    assert change['staffingRoleScanComplete'] is True,change
    assert {(r['role'],r['count']) for r in change['staffingRoles']}=={('PM',1),('개발자',2)},change
    assert all(r['sourceFile']=='투입인력계획서.pdf' and r['sourceText']
               for r in change['staffingRoles']),change
    assert len(calls)==1,calls
    assert change['staffingFactScanVersions']=={'0':2},change
    # Once the SHA-matched cached file has been published as fact-version 2,
    # the next incremental pass MUST skip it without re-reading any bytes.
    done=json.loads(index.read_text())
    done['byNotice'][key]['files'][0]['staffingFactScanVersion']=2
    index.write_text(json.dumps(done))
    calls.clear()
    after=run(index,detail,ledger,patch,report,max_files=5,max_seconds=30)
    assert after['filesReparsed']==0 and after['governmentApiCalls']==0,after
    assert not calls,calls
print('CACHED_RFP_STAFFING_REPARSE_OFFLINE_FIXTURE=PASS')
