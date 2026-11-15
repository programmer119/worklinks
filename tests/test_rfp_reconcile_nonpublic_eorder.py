#!/usr/bin/env python3
"""Offline proof: internal eorder 422 is not a public missing original."""
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from rfp_call_ledger import CallLedger,cache_key
from rfp_dual_queue import RfpDualQueue
from rfp_reconcile_nonpublic_eorder import reconcile,_source_eligible

base='https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/'
good=base+'downloadRfpFile.do?rfpNo=R26DH00060272&rfpOrd=000&rfpUntyAtchFileNo=21'
bad=base+'downloadRfpFile.do?rfpNo=R26DH00060272&rfpOrd=000&rfpUntyAtchFileNo=1'
key='R26BK01789790:000'
with tempfile.TemporaryDirectory() as root:
    folder=Path(root)
    q=RfpDualQueue(folder/'rfp-dual-queue.sqlite3')
    q.enqueue([('R26BK01789790','000','2099-12-31')],'v1')
    meta={'attachments':{'ok':True,'complete':True,'items':[
          {'name':'긴급입찰사유서.pdf','url':good,'source':'eorder'},
          {'name':'(붙임3) 긴급입찰사유서.pdf','url':bad,'source':'eorder'}]},
          'noticeDocuments':{'ok':True,'complete':True,'items':[]}}
    q.save_bulk_manifests({key:meta})
    claim=q.claim_download(ready_manifest=True)
    assert claim[0]==key,claim
    ledger_path=folder/'rfp-request-ledger.sqlite3'
    with patch.dict(os.environ,{'WORKLINKS_RFP_DISK_RESERVE_MB':'32',
                                'WORKLINKS_RFP_LEDGER_MAX_MB':'128'}):
        archive=CallLedger(ledger_path)
        saved_hash=archive.save_bytes(cache_key('official_attachment',good),
                b'%PDF-1.4 publicly posted original',notice_key=key,
                closes_on='2099-12-31')
        assert saved_hash is not None
        receipt=archive.verified_bytes_info(cache_key('official_attachment',good))
        assert receipt and receipt['sha256']==saved_hash
        archive.save_json(cache_key('test_source',key),{'items':[{
            'bidNtceNo':'R26BK01789790','bidNtceOrd':'000',
            'atchFileUrl':bad,'eorderAtchFileNm':'(붙임3) 긴급입찰사유서.pdf',
            'eorderDocDivNm':'긴급발주사유서'}]})
    q.download_unavailable(key,meta,[{'name':'긴급입찰사유서.pdf',
        'url':good,'bytes':receipt['bytes'],'sha256':receipt['sha256']}],
        [{'name':'(붙임3) 긴급입찰사유서.pdf','url':bad,'httpStatus':422,
          'reason':'official_attachment_reference_missing_422'}])
    assert q.stats()['download']['errors']==1
    assert reconcile(str(q.path),str(ledger_path),apply=False,targets=(key,))==1
    assert q.stats()['download']['errors']==1,'dry run changed production-like DB'
    assert reconcile(str(q.path),str(ledger_path),apply=True,targets=(key,))==1
    assert q.stats()['download']['errors']==0
    assert q.stats()['download']['done']==1
    ready=q.claim_ready(10)
    assert len(ready)==1 and ready[0][0]==key,ready
    result=ready[0][2]
    assert len(result['downloadVerifiedFiles'])==1
    assert [x['url'] for x in result['attachments']['items']]==[good]
    assert result['attachments']['excludedNonPublicDocuments'][0]['url']==bad
    assert not result.get('downloadErrorFiles')
    assert q.bulk_manifest(key)['attachments']['count']==1
    assert reconcile(str(q.path),str(ledger_path),apply=True,targets=(key,))==0
    q.scan_release([key])

# A failed public RFP is never silently dropped without explicit official
# source-category evidence, even if it also returns HTTP 422.
fake={'attachments':{'ok':True,'complete':True,'items':[
 {'name':'public.pdf','url':good,'source':'eorder'},
 {'name':'missing.pdf','url':bad,'source':'eorder'}]},
 'downloadErrorFiles':[{'name':'missing.pdf','url':bad,'httpStatus':422}],
 'downloadVerifiedFiles':[{'name':'public.pdf','url':good,'sha256':'a'*64,'bytes':10}]}
try:
    _source_eligible(key,fake,{(key,bad):{('제안요청서','missing.pdf')}})
except ValueError as err:
    assert 'no_unambiguous_verified_internal_source' in str(err)
else:raise AssertionError('public missing RFP wrongly suppressed')
print('RFP_NONPUBLIC_EORDER_422_VERIFIED_RECONCILIATION=PASS')
