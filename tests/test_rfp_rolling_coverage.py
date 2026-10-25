#!/usr/bin/env python3
"""Regression: thousands of bids get fair, never-rejected RFP scan scheduling."""
import datetime as dt
import json
import pathlib
import runpy

root=pathlib.Path(__file__).resolve().parents[1]
module=runpy.run_path(str(root/'scripts/refresh_worklinks_rfp.py'),run_name='test_rolling')
discover=module['discover']
utc=dt.datetime.now(dt.timezone.utc)
today=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()
deadline=(today+dt.timedelta(days=4)).strftime('%Y%m%d')+'1400'
rows=[{'bidNo':'R26BK'+str(i).zfill(8),'order':'000',
       'kind':'servc','closes':deadline,
       'bidEligibility':{'requirements':[{'codes':['1468']}]}}
      for i in range(3450)]
calls=[]
def fake(url):
    from urllib.parse import parse_qs,urlsplit
    off=int(parse_qs(urlsplit(url).query)['offset'][0])
    calls.append(off)
    return {'ok':True,'totalCount':len(rows),'items':rows[off:off+500]}
discover.__globals__['fetch_json']=fake
first=discover(220,{})
assert len(first)==220,len(first)
assert calls==list(range(0,3500,500)),calls
recent={no+':'+order:{
 'checkedAt':utc.isoformat(),
 'classificationVersion':module['CLASSIFICATION_VERSION'],
 'hwpxReaderVersion':module['HWPX_READER_VERSION'],
 'reviewComplete':False,'files':[]} for no,order,_ in first}
calls.clear()
second=discover(220,recent)
assert len(second)==220,len(second)
assert set((n,o) for n,o,_ in first).isdisjoint((n,o) for n,o,_ in second)
assert len(calls)==7
# Partial scans, 403 errors, unknown times and after-deadline notices remain
# visible in the scan queue rather than being declared ineligible.
record={'checkedAt':utc.isoformat(),'classificationVersion':22,
        'status':'text_extracted_requires_review','files':[{
        'name':'공고문.hwpx','readable':True,
        'sourceSha256':'a'*64,'sourceTextScanComplete':True,
        'clauseCandidates':[{'sourceText':'업종코드 1468 필수','type':'industry_code'}]}]}
summary=module['compact_coverage'](record)
assert summary['status']=='text_extracted_requires_review'
assert summary['reviewComplete'] is False
assert summary['files'][0]['sourceSha256']=='a'*64
assert 'clauseCandidates' not in summary['files'][0]
assert summary['files'][0]['clauseCandidateCount']==1
# Regression: the publication must never create a 100 MB GitHub blob.
# Keep the newest, unabridged detail records; older ones remain indexed by
# their official source hashes and bounded, verifiable quotations.
bound=module['bounded_detail_snapshot']
records={
    'older:000':{'checkedAt':'2026-10-01T00:00:00+00:00','files':[
        {'sourceSha256':'a'*64,'clauseCandidates':[{'sourceText':'old '+('가'*1200)}]}]},
    'newer:000':{'checkedAt':'2026-10-25T00:00:00+00:00','files':[
        {'sourceSha256':'b'*64,'clauseCandidates':[{'sourceText':'new '+('나'*1200)}]}]},
}
selected,omitted=bound(records,max_records=240,max_bytes=10000)
assert omitted==1 and list(selected)==['newer:000'],(selected.keys(),omitted)
assert selected['newer:000']['files'][0]['clauseCandidates'][0]['sourceText'].endswith('나'*1200)
assert len(json.dumps({'byNotice':selected},ensure_ascii=False,indent=2).encode('utf-8'))<10000
assert records['older:000']['files'][0]['sourceSha256']=='a'*64
# Equal timestamp ordering is deterministic, and count cap remains independent
# of byte cap. The original source dict is never modified by this function.
many={f'k{i:04d}':{'checkedAt':'2026-10-25','files':[]} for i in range(300)}
kept,not_in_cache=bound(many,max_records=240,max_bytes=100000)
assert len(kept)==240 and not_in_cache==60
assert len(many)==300
print('WORKLINKS_RFP_GITHUB_BLOB_GUARD=PASS','selected',len(selected),'omitted',omitted)
# An extracted but not legally reviewed RFP is NOT a new download job
# after 24 hours. Cumulative scans are distinct from participation verdicts.
old_scan=(utc-dt.timedelta(days=15)).isoformat()
def scanned_record():
    return {'checkedAt':old_scan,'status':'text_extracted_requires_review',
            'classificationVersion':module['CLASSIFICATION_VERSION'],
            'hwpxReaderVersion':module['HWPX_READER_VERSION'],
            'reviewComplete':False,'readableDocumentCount':1,
            'unreadableDocumentCount':0,
            'files':[{'name':'official.hwpx','readable':True,
                      'sourceSha256':'d'*64,'sourceTextScanComplete':True}]}
all_done={row['bidNo']+':'+row['order']:scanned_record() for row in rows}
calls.clear()
assert discover(220,all_done)==[], 'old successful RFP downloads must not repeat'
assert len(calls)==7,calls
# Transient failures and parser upgrades remain legitimate, bounded retries.
bad_key=rows[0]['bidNo']+':000'
version_key=rows[1]['bidNo']+':000'
retry=dict(all_done)
retry[bad_key]={**scanned_record(),'status':'metadata_fetch_failed'}
retry[version_key]={**scanned_record(),
                    'classificationVersion':module['CLASSIFICATION_VERSION']-1}
candidate=discover(5,retry)
assert {(n,o) for n,o,_ in candidate} == {
    (rows[0]['bidNo'],'000'),(rows[1]['bidNo'],'000')},candidate
# A published correction order is a NEW document identity, not a repeat.
original=rows[2]
rows[2]={**original,'order':'001'}
corrected=discover(5,all_done)
assert corrected==[(original['bidNo'],'001',deadline[:4]+'-'+deadline[4:6]+'-'+deadline[6:8])],corrected
rows[2]=original
print('WORKLINKS_RFP_SUCCESS_REUSE=PASS','historical',len(all_done),'retry',len(candidate))

# A successful RFP keeps its official source hash but has a separately
# monitored manifest digest. Metadata checks do not download document bytes.
manifest=module['official_manifest_signature']
inspect=module['inspect_manifest_probe']
def metadata(*names,complete=True):
    items=[{'name':name,'url':'https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/'+name}
           for name in names]
    return {'attachments':{'ok':True,'complete':complete,
                           'eorderCount':len(items),'items':items},
            'noticeDocuments':{'ok':True,'complete':complete,'items':[]}}
alpha=metadata('A.pdf','B.hwpx')
reverse=metadata('B.hwpx','A.pdf')
modified=metadata('A.pdf','C.hwpx')
sig=manifest(alpha)
assert sig and sig==manifest(reverse) and sig!=manifest(modified)
assert manifest(metadata('A.pdf',complete=False)) is None
existing={**scanned_record(),'manifestSignature':sig,
          'manifestCheckedAt':(utc-dt.timedelta(days=3)).isoformat()}
steady,verdict=inspect(reverse,existing,utc.isoformat())
assert verdict=='unchanged' and not steady['manifestChangePending']
changed,verdict=inspect(modified,existing,utc.isoformat())
assert verdict=='changed' and changed['manifestChangePending']
assert changed['manifestPendingSignature']!=sig and 'manifestSignature' not in changed
assert not module['reusable_rfp_extraction']({**existing,**changed})
legacy,verdict=inspect(alpha,scanned_record(),utc.isoformat())
assert verdict=='baseline' and legacy['manifestBaselineUnverified']
incomplete,verdict=inspect(metadata('B.hwpx',complete=False),existing,utc.isoformat())
assert verdict=='incomplete' and incomplete['lastManifestProbeStatus']=='metadata_incomplete'
assert not module['manifest_probe_due'](
    {**scanned_record(),'manifestCheckedAt':utc.isoformat()},utc)
assert module['manifest_probe_due'](
    {**scanned_record(),'manifestCheckedAt':(utc-dt.timedelta(days=3)).isoformat()},utc)
pending_record={**scanned_record(),'checkedAt':utc.isoformat(),
                'manifestChangePending':True,'manifestSignature':'d'*64}
pending_key=rows[4]['bidNo']+':000'
pending_jobs=discover(1,{pending_key:pending_record},targets={pending_key})
assert pending_jobs and pending_jobs[0][:2]==(rows[4]['bidNo'],'000'),pending_jobs
probe_candidates=[]
discover(5, {rows[0]['bidNo']+':000':existing},manifest_probe_out=probe_candidates)
assert any(x[1]==rows[0]['bidNo'] for x in probe_candidates),probe_candidates[:2]
print('WORKLINKS_RFP_MANIFEST_CHECK=PASS','metadata_probe_only',True)
print('WORKLINKS_RFP_ROLLING_CORPUS=PASS','total',len(rows),'batch',220,'cumulative_archive',True)
