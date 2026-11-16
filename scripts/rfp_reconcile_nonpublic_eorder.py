#!/usr/bin/env python3
"""Fix specifically verified non-public e-order 422 references; no network calls.

Never remove a publicly listed attachment. The archived OFFICIAL e-order JSON
must explicitly label each failed reference '긴급발주사유서'. Every remaining
download must still have a fully SHA-256-verified binary in the ledger.
"""
import argparse
import datetime as dt
import json
import re
import sqlite3
import urllib.parse
import zlib

from rfp_call_ledger import CallLedger, cache_key

TARGETS=(
    'R26BK01789790:000','R26BK01804199:000',
    'R26BK01811838:000','R26BK01815325:000',
    'R26BK01821154:000','R26BK01823630:000',
)

def _loads(raw):
    value=json.loads(raw or '{}')
    if not isinstance(value,dict):raise ValueError('invalid_object')
    return value

def _canonical_key(row):
    return str(row.get('bidNtceNo') or '')+':'+str(row.get('bidNtceOrd') or '000').zfill(3)

def _official_sources(archive,need):
    """Read already archived JSON once; never call a live procurement endpoint."""
    labels={}
    for (blob,) in archive.execute(
            "SELECT payload FROM verified_cache WHERE media_type='json'"):
        try:payload=json.loads(zlib.decompress(blob))
        except (ValueError,TypeError,zlib.error):continue
        if not isinstance(payload,dict):continue
        for raw in payload.get('items') or []:
            if not isinstance(raw,dict):continue
            key=_canonical_key(raw)
            if key not in need:continue
            url=str(raw.get('atchFileUrl') or
                raw.get('atchFileInfoUrl') or raw.get('eorderAtchFileUrl') or
                raw.get('fileUrl') or raw.get('fileDownloadUrl') or '')
            if url not in need[key]:continue
            category=str(raw.get('eorderDocDivNm') or '').strip()
            name=str(raw.get('eorderAtchFileNm') or '')
            labels.setdefault((key,url),set()).add((category,name))
    return labels

def _source_eligible(key,meta,labels):
    docs=meta.get('attachments') or {}
    if docs.get('ok') is not True or docs.get('complete') is not True:
        raise ValueError(key+':incomplete_official_manifest')
    errors=meta.get('downloadErrorFiles') or []
    verified=meta.get('downloadVerifiedFiles') or []
    if not errors or not verified:
        raise ValueError(key+':missing_error_or_verified_originals')
    official_urls={}
    for item in docs.get('items') or []:
        if not isinstance(item,dict):raise ValueError(key+':malformed_manifest_item')
        url=str(item.get('url') or '')
        if url:official_urls[url]=item
    error_urls=set()
    for err in errors:
        if not isinstance(err,dict) or err.get('httpStatus')!=422:
            raise ValueError(key+':non_422_error_present')
        url=str(err.get('url') or '')
        item=official_urls.get(url)
        if (not item or item.get('source')!='eorder' or url in error_urls):
            raise ValueError(key+':error_not_single_eorder_source')
        found=labels.get((key,url),set())
        if (not found or any(category!='긴급발주사유서' or
                (name and name!=str(err.get('name') or ''))
                for category,name in found)):
            raise ValueError(key+':no_unambiguous_verified_internal_source:'+url[-35:])
        error_urls.add(url)
    verified_urls=set()
    for item in verified:
        if (not isinstance(item,dict) or not item.get('sha256') or
            not item.get('url') or item['url'] not in official_urls or
            item['url'] in verified_urls or item['url'] in error_urls):
            raise ValueError(key+':invalid_verified_original_receipt')
        verified_urls.add(item['url'])
    if set(official_urls)!=error_urls|verified_urls:
        raise ValueError(key+':manifest_and_saved_originals_do_not_match')
    excluded=[{**official_urls[url],'reason':'not_public_proposal_attachment',
               'documentCategory':'긴급발주사유서','httpStatus':422}
              for url in sorted(error_urls)]
    newdocs=dict(docs)
    newdocs['items']=[x for x in docs.get('items') or []
                      if str(x.get('url') or '') not in error_urls]
    newdocs['count']=len(newdocs['items'])
    newdocs['excludedNonPublicDocuments']=[
        *(docs.get('excludedNonPublicDocuments') or []),*excluded]
    updated=dict(meta,attachments=newdocs,
                 downloadExcludedNonPublicReferences=excluded)
    updated.pop('downloadErrorFiles',None)
    return updated,error_urls,verified

def reconcile(queue_path,ledger_path,apply=False,targets=TARGETS):
    queue=sqlite3.connect(queue_path,timeout=45)
    archive=sqlite3.connect('file:'+ledger_path+'?mode=ro',uri=True,timeout=45)
    try:
        entries={}
        needed={}
        for key in targets:
            row=queue.execute("""SELECT download_status,scan_status,
                 metadata_json FROM rfp_dual_notices WHERE notice_key=?""",
                 (key,)).fetchone()
            if row is None:raise ValueError(key+':notice_not_in_queue')
            status,scan,raw=row
            if status=='ready' and scan in ('pending','retry','scanning','done'):
                print('NONPUBLIC_REFERENCE_ALREADY_RECONCILED',key,flush=True)
                continue
            if status!='error_confirmed' or scan not in ('pending','retry','done'):
                raise ValueError(key+':unexpected_queue_status:'+str((status,scan)))
            meta=_loads(raw)
            errors=meta.get('downloadErrorFiles') or []
            needed[key]={str(x.get('url') or '') for x in errors if isinstance(x,dict)}
            entries[key]=(raw,meta,scan)
        labels=_official_sources(archive,needed)
        prepared={}
        for key,(raw,meta,scan) in entries.items():
            updated,excluded,receipts=_source_eligible(key,meta,labels)
            # Re-read each compressed original and verify SHA against its receipt.
            for receipt in receipts:
                reqkey=cache_key('official_attachment',receipt['url'])
                row=archive.execute("""SELECT rowid,sha256 FROM verified_cache
                  WHERE media_type='bytes' AND request_key=? AND source_revision=''""",
                  (reqkey,)).fetchone()
                if not row or row[1]!=receipt['sha256']:
                    raise ValueError(key+':verified_original_missing_or_sha_disagrees')
                checked=CallLedger._verify_blob_stream(archive,row[0],row[1])
                if checked['bytes']!=receipt.get('bytes'):
                    raise ValueError(key+':verified_original_length_disagrees')
            bulk=queue.execute("""SELECT metadata_json FROM rfp_bulk_manifests
                  WHERE notice_key=?""",(key,)).fetchone()
            if bulk:
                oldbulk=_loads(bulk[0])
                oldbulk_attachments=oldbulk.get('attachments') or {}
                bulkurls={str(item.get('url') or '') for item in
                          oldbulk_attachments.get('items') or []
                          if isinstance(item,dict) and item.get('url')}
                if not excluded.issubset(bulkurls):
                    raise ValueError(key+':bulk_manifest_missing_official_refs')
                newbulk=dict(oldbulk,attachments={
                    **oldbulk_attachments,
                    'items':[item for item in oldbulk_attachments.get('items') or []
                        if item.get('url') not in excluded],
                    'count':len([item for item in oldbulk_attachments.get('items') or []
                        if item.get('url') not in excluded]),
                    'excludedNonPublicDocuments':[
                        *(oldbulk_attachments.get('excludedNonPublicDocuments') or []),
                        *updated['downloadExcludedNonPublicReferences']]})
                bulkchange=(bulk[0],json.dumps(newbulk,ensure_ascii=False,separators=(',',':')))
            else:bulkchange=None
            prepared[key]=(raw,updated,len(receipts),len(excluded),bulkchange,scan)
            print('NONPUBLIC_REFERENCE_VERIFIED',json.dumps({
                'noticeKey':key,'publicVerifiedFiles':len(receipts),
                'excludedInternal422':len(excluded),
                'excludedFileNames':[x['name'] for x in
                  updated['downloadExcludedNonPublicReferences']],
                'source':'verified_official_eorder_category',
                'bytesShaVerified':True},ensure_ascii=False),flush=True)
        if apply:
            queue.execute('BEGIN IMMEDIATE')
            now=dt.datetime.now(dt.timezone.utc).isoformat()
            for key,(old,meta,files,nexcluded,bulkchange,scan) in prepared.items():
                result=queue.execute("""UPDATE rfp_dual_notices
                    SET download_status='ready',scan_status=?, 
                        metadata_json=?,download_done=?,download_total=?,
                        download_retry_epoch=0,scan_retry_epoch=0,
                        last_error='',updated_at=?
                    WHERE notice_key=? AND download_status='error_confirmed'
                      AND metadata_json=? AND scan_status=?""",(
                    'done' if scan=='done' else 'pending',
                    json.dumps(meta,ensure_ascii=False,separators=(',',':')),
                    files,files,now,key,old,scan))
                if result.rowcount!=1:
                    raise ValueError(key+':queue_changed_during_reconciliation')
                if bulkchange:
                    result=queue.execute("""UPDATE rfp_bulk_manifests
                         SET metadata_json=?,saved_at=?
                         WHERE notice_key=? AND metadata_json=?""",(
                        bulkchange[1],now,key,bulkchange[0]))
                    if result.rowcount!=1:
                        raise ValueError(key+':bulk_manifest_changed_during_reconciliation')
            queue.commit()
        print('NONPUBLIC_EORDER_RECONCILE_FINISHED',json.dumps({
            'mode':'applied' if apply else 'dry_run',
            'notices':list(prepared),
            'verifiedPublicFiles':sum(row[2] for row in prepared.values()),
            'excludedInternal422':sum(row[3] for row in prepared.values())},
            ensure_ascii=False),flush=True)
        return len(prepared)
    finally:
        archive.close()
        queue.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--queue',default='/app/data/rfp-dual-queue.sqlite3')
    parser.add_argument('--ledger',default='/app/data/rfp-request-ledger.sqlite3')
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--notice-key',help='One exact official bid number and revision; avoids changing unrelated queue rows')
    args=parser.parse_args()
    if args.notice_key and not re.fullmatch(r'R[0-9]{2}BK[0-9]{8}:[0-9]{3}',args.notice_key):
        parser.error('--notice-key must use R00BK00000000:000 format')
    reconcile(args.queue,args.ledger,args.apply,
              targets=(args.notice_key,) if args.notice_key else TARGETS)
