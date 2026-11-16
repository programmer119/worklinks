#!/usr/bin/env python3
"""Read-only forensic OCR verification on exactly the 61 PDF OCR failures at 01:19 UTC.
Reads only saved SHA-verified originals; never writes production databases or snapshots.
"""
import argparse
from collections import Counter, defaultdict
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import repair_open_rfp_cached_attachments as repair
import refresh_worklinks_rfp as reader

parser=argparse.ArgumentParser()
parser.add_argument('--data',default='/data')
parser.add_argument('--baseline',default='/baseline/diagnostics/rfp-rescan-live-20261116.json')
parser.add_argument('--output',default='/output/pdf_ocr_original_61.json')
parser.add_argument('--probe-only',action='store_true')
parser.add_argument('--max-ocr-files',type=int,default=61)
parser.add_argument('--max-passes',type=int,default=5)
args=parser.parse_args()
root=Path(args.data)
baseline=json.loads(Path(args.baseline).read_text(encoding='utf8'))
original=[(r['noticeKey'], f['name']) for r in baseline['problemNotices']
          for f in r.get('files',[]) if f.get('errorCategory')=='pdf_ocr_incomplete']
if len(original)!=61:
    raise SystemExit('ABORT_EXPECTED_EXACT_ORIGINAL_61_GOT_'+str(len(original)))
index=repair.read_json(root/'snapshots/rfp-coverage-index.json').get('byNotice') or {}
queue=repair.verified_download_queue(root/'rfp-dual-queue.sqlite3')
ledger=root/'rfp-request-ledger.sqlite3'
if not ledger.is_file():raise SystemExit('MISSING_VERIFIED_LEDGER')
result={'startedAt':dt.datetime.now(dt.timezone.utc).isoformat(),
        'scope':'original_61_file_identity_exact','readOnlyProduction':True,
        'original61':len(original),'readerVersion':repair.READER_ATTEMPT_VERSION,
        'probeOnly':args.probe_only,'files':[]}
out=Path(args.output)
out.parent.mkdir(exist_ok=True,parents=True)
def publish():
    result['checkedAt']=dt.datetime.now(dt.timezone.utc).isoformat()
    result['categories']=dict(Counter(r['status'] for r in result['files']))
    result['processed']=len(result['files'])
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print('PDF_ORIGINAL61_PROGRESS',json.dumps({
        'processed':len(result['files']),'of':61,'categories':result['categories']},
        ensure_ascii=False),flush=True)
selected=0
for notice,name in original:
    entry={'notice':notice,'name':name,'status':'not_started'}
    result['files'].append(entry)
    started=time.monotonic()
    try:
        scan=index.get(notice)
        if not isinstance(scan,dict):raise ValueError('current_notice_missing_from_snapshot')
        live=[x for x in scan.get('files',[]) if str(x.get('name') or '')==name]
        if not live:raise ValueError('current_file_missing_from_snapshot')
        f=live[0]
        entry['currentError']=str(f.get('errorCategory') or '')
        entry['currentReadComplete']=bool(f.get('readable') is True and
                                          f.get('sourceTextScanComplete') is True)
        entry['lastReaderAttemptVersion']=str(f.get('lastReaderAttemptVersion') or '')
        metadata=queue.get(notice)
        if not metadata:raise ValueError('no_verified_completed_download_for_notice')
        if not repair.metadata_valid(metadata,scan):
            raise ValueError('manifest_scan_mismatch')
        mapped=defaultdict(list)
        for item in metadata['attachments']['items']:
            mapped[str(item.get('name') or '')].append(item)
        paired=[]
        for current in scan.get('files',[]):
            matches=mapped[str(current.get('name') or '')]
            if not matches:raise ValueError('manifest_file_pair_mismatch')
            item=matches.pop(0)
            if str(current.get('name') or '')==name:paired.append(item)
        item=paired[0]
        receipt=next((v for v in metadata.get('downloadVerifiedFiles',[])
                      if v.get('url')==item['url']),None)
        if not receipt:raise ValueError('missing_verified_download_receipt')
        raw,origin=repair.fetch_verified_raw(item,ledger,str(receipt['sha256']))
        entry['byteCount']=len(raw)
        entry['format']=reader.detected_source_format(name,raw)
        entry['verifiedSha256']=hashlib.sha256(raw).hexdigest()
        entry['hasVerifiedOriginal']=True
        if args.probe_only or selected>=args.max_ocr_files:
            entry['status']='verified_original_available_not_ocr_tested'
        else:
            selected+=1
            before=None
            for trial in range(1,args.max_passes+1):
                try:
                    text,evidence,cached=reader.extract_cached_text(name,raw)
                    evidence=evidence or {}
                    diag={
                        'pass':trial,'complete':evidence.get('sourceComplete'),
                        'pdfPages':evidence.get('pdfPages'),
                        'ocrAttemptedPages':evidence.get('ocrAttemptedPages'),
                        'ocrRecoveredPages':evidence.get('ocrRecoveredPages'),
                        'ocrRestoredPages':evidence.get('ocrRestoredPages'),
                        'ocrBatchDeferredPages':evidence.get('ocrBatchDeferredPages'),
                        'ocrFailedPages':evidence.get('ocrFailedPages'),
                        'unresolvedPages':evidence.get('unresolvedPages'),
                        'sources':[{'name':p.get('sourceFile'),'pages':p.get('pdfPages'),
                           'unresolved':p.get('unresolvedPages'),
                           'failed':p.get('ocrFailureDetails')} for p in
                             (evidence.get('pdfSources') or [])[:5]],
                        'textAlnum':sum(c.isalnum() for c in text)
                    }
                    entry.setdefault('passes',[]).append(diag)
                    if evidence.get('sourceComplete') is True and sum(c.isalnum() for c in text)>=12:
                        entry['status']='ocr_extract_success'
                        break
                    signature=(diag['ocrAttemptedPages'],diag['ocrRestoredPages'],
                               diag['ocrRecoveredPages'],diag['ocrBatchDeferredPages'],
                               diag['ocrFailedPages'],str(diag['unresolvedPages']))
                    if signature==before:
                        entry['status']='ocr_no_progress'
                        break
                    before=signature
                except Exception as exc:
                    entry['status']='ocr_exception'
                    entry['error']=type(exc).__name__+': '+str(exc)[:220]
                    break
            if entry['status']=='not_started':entry['status']='ocr_still_incomplete_after_bounded_retries'
    except Exception as exc:
        entry['status']='missing_or_invalid_original'
        entry['error']=type(exc).__name__+': '+str(exc)[:220]
    finally:
        entry['durationSeconds']=round(time.monotonic()-started,2)
        print('PDF_ORIGINAL61_FILE',json.dumps({
            'notice':notice,'file':name,'status':entry['status'],
            'duration':entry['durationSeconds'],
            'error':entry.get('error'),'lastPass':(entry.get('passes') or [{}])[-1]},
            ensure_ascii=False),flush=True)
        publish()
print('PDF_ORIGINAL61_VERIFICATION_DONE',json.dumps(result['categories'],ensure_ascii=False),flush=True)
