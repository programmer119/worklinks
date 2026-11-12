#!/usr/bin/env python3
"""Repair previously attempted live RFP attachments, using saved metadata ONLY.

Scope: WorkLinks SW notices whose bid closes more than 24h from run start.
No G2B bid/attachment metadata API is invoked. Only official attachment GETs
whose URLs were already saved, with the verified binary cache checked first.
Never reread successfully extracted siblings; never claim bidder qualification.
"""
import argparse
from collections import Counter
import datetime as dt
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import urllib.parse
import zlib

import refresh_worklinks_rfp as rfp
from rfp_call_ledger import cache_key

KST=dt.timezone(dt.timedelta(hours=9))
REPAIR_VERSION='signature-reader-20261112'
READER_ATTEMPT_VERSION='pdf-ocr-kor-20261112-v1'
ERRORS=('metadata_missing','manifest_mismatch','url_missing','unrecognized_error',
        'attachment_unavailable','still_scan_incomplete','changed_while_repairing')


def read_json(file):
    try:return json.loads(Path(file).read_text(encoding='utf-8'))
    except (OSError,ValueError):return {}


def write_atomic(path,content):
    path=Path(path)
    fd,temp=tempfile.mkstemp(prefix=path.name+'.pending.',dir=str(path.parent))
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)


def close_time(row):
    raw=str(row.get('closes') or '')
    try:
        value=dt.datetime.fromisoformat(raw.replace('Z','+00:00'))
        return value if value.tzinfo else value.replace(tzinfo=KST)
    except (ValueError,TypeError):return None


def open_candidates(data_dir,now):
    cutoff=now+dt.timedelta(hours=24)
    db=Path(data_dir)/'bids.sqlite3'
    with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True,timeout=15) as conn:
        rows=conn.execute('SELECT bid_no,bid_ord,payload FROM bid_notices WHERE sw_candidate=1').fetchall()
    found={}
    for no,order,payload in rows:
        try:body=json.loads(payload)
        except (ValueError,TypeError):continue
        end=close_time(body)
        if end is None or end.astimezone(dt.timezone.utc)<=cutoff:continue
        key=str(no)+':'+str(order or '0').zfill(3)
        if key not in found or end<found[key]:
            found[key]=end
    return sorted(found.items(),key=lambda row:(row[1],row[0]))


def failed_files(scan):
    return [f for f in scan.get('files') or [] if isinstance(f,dict)
       and (f.get('readable') is not True or f.get('sourceTextScanComplete') is not True
            or f.get('qualificationScanTruncated') is True
            or int(f.get('unmatchedQualificationAnchorCount') or 0)>0)]


def reader_retry_files(scan):
    return [f for f in failed_files(scan)
            if f.get('lastReaderAttemptVersion')!=READER_ATTEMPT_VERSION]


def metadata_valid(metadata,scan):
    if not isinstance(metadata,dict):return False
    doc=metadata.get('attachments') or {}
    notice=metadata.get('noticeDocuments') or {}
    if not (doc.get('ok') is True and doc.get('complete') is True and
            notice.get('ok') is True and notice.get('complete') is True):return False
    manifest=doc.get('items') or []
    if not isinstance(manifest,list) or not manifest:return False
    prev=scan.get('files') or []
    # Compare exact file labels and multiplicity, never just filename matches.
    if (len(manifest)!=len(prev) or
        Counter(str(f.get('name') or '') for f in manifest)!=
        Counter(str(f.get('name') or '') for f in prev)):
        return False
    return True


def cached_metadata(dbpath,key):
    # Read verified historical response only. Never invoke metadata endpoints.
    if not dbpath.exists():return None
    request_key=cache_key('bid_evidence',key)
    with sqlite3.connect('file:'+str(dbpath)+'?mode=ro',uri=True,timeout=15) as conn:
        item=conn.execute("SELECT payload,sha256 FROM verified_cache WHERE request_key=? AND media_type='json'",
                          (request_key,)).fetchone()
    if not item:return None
    try:
        raw=zlib.decompress(item[0])
        if hashlib.sha256(raw).hexdigest()!=item[1]:return None
        return json.loads(raw.decode('utf-8'))
    except (ValueError,zlib.error,UnicodeError):return None


def metadata_for(key,scan,stored,ledgerpath,archive=None):
    # A detected source-manifest revision must never use historical file URLs.
    if scan.get('manifestChangePending') is True:
        return None,'manifest_changed'
    metadata=stored.get(key)
    if metadata_valid(metadata,scan):return metadata,'saved_metadata'
    prior=cached_metadata(ledgerpath,key)
    if metadata_valid(prior,scan):return prior,'verified_ledger'
    # Old full extraction records retain sourceUrl even when the compact
    # cumulative index strips it. Recover from those URLs without an A02 call.
    for source,origin in archive or []:
        rec=source.get(key)
        if not isinstance(rec,dict) or rec.get('manifestComplete') is not True:
            continue
        files=rec.get('files') or []
        if (len(files)!=len(scan.get('files') or []) or
            [str(f.get('name') or '') for f in files]!=
            [str(f.get('name') or '') for f in scan.get('files') or []]):
            continue
        if any(not rfp.legal_file({'name':f.get('name'),'url':f.get('sourceUrl')})
               for f in files if f.get('readable') is not True or
               f.get('sourceTextScanComplete') is not True):
            continue
        recovered={'attachments':{'ok':True,'complete':True,
                    'items':[{'name':f.get('name') or '',
                              'url':f.get('sourceUrl') or ''}
                             for f in files]},
                   'noticeDocuments':{'ok':True,'complete':True},
                   '_source':'previously_verified_full_rfp_scan'}
        if metadata_valid(recovered,scan):
            return recovered,origin
    return None,'metadata_missing'


def fetch_verified_raw(source,ledgerpath):
    """Use local verified bytes when available; else one *attachment* GET."""
    url=source['url']
    legal=rfp.legal_file(source)
    if not legal:raise ValueError('unapproved_official_file_url')
    key=cache_key('official_attachment',url)
    if ledgerpath.exists():
        with sqlite3.connect('file:'+str(ledgerpath)+'?mode=ro',uri=True,timeout=15) as conn:
            row=conn.execute("SELECT payload,sha256 FROM verified_cache WHERE request_key=? AND media_type='bytes'",
                              (key,)).fetchone()
        if row:
            try:
                raw=zlib.decompress(row[0])
                if (len(raw)<=rfp.MAX_FILE and hashlib.sha256(raw).hexdigest()==row[1]):
                    return raw,'verified_cache'
            except (zlib.error,TypeError):pass
    # Does NOT use bid-evidence, A02, or any public data API.
    req=rfp.urllib.request.Request(url,headers={
        'User-Agent':'Mozilla/5.0','Referer':'https://www.g2b.go.kr/'})
    try:
        with rfp.OPENER.open(req,timeout=35) as response:
            if int(response.headers.get('Content-Length') or 0)>rfp.MAX_FILE:
                raise ValueError('large_file')
            raw=response.read(rfp.MAX_FILE+1)
            if len(raw)>rfp.MAX_FILE:raise ValueError('large_file')
            if getattr(response,'status',200)!=200:
                raise ValueError('unexpected_http_status')
    except rfp.urllib.error.HTTPError as ex:
        if rfp.official_missing_reference(ex):
            raise rfp.OfficialAttachmentReferenceMissing(
                'official_attachment_reference_missing_422') from ex
        raise
    return raw,'official_attachment_GET'


def process_one(key,scan,meta,ledger):
    """No successful file is downloaded, parsed, or overwritten."""
    manifest=meta['attachments']['items']
    byname={}
    for item in manifest:byname.setdefault(str(item.get('name') or ''),[]).append(item)
    paired={}
    for f in scan['files']:
        label=str(f.get('name') or '')
        paired[id(f)]=byname[label].pop(0)
    latest=[]
    counts=Counter()
    counts['alternate_pdf_evidence']+=rfp.annotate_official_pdf_siblings(scan['files'])
    for f in scan['files']:
        if f not in reader_retry_files({'files':[f]}):continue
        f['lastReaderAttemptVersion']=READER_ATTEMPT_VERSION
        f['lastReaderAttemptAt']=dt.datetime.now(dt.timezone.utc).isoformat()
        counts['reader_attempt_recorded']+=1
        label=str(f.get('name') or '')
        item=paired[id(f)]
        if f.get('alternatePdfEvidence') and str(f.get('errorCategory') or '') in (
                'file_extract_failure','no_searchable_text','hwp5txt_failed',
                'invalid_hwp','pdf_ocr_incomplete'):
            counts['same_title_official_pdf_reused']+=1
            continue
        if not rfp.legal_file(item):
            counts['invalid_official_url']+=1
            continue
        try:
            raw,origin=fetch_verified_raw(item,ledger)
            extracted,evidence=rfp.extract_with_source_status(label,raw)
            text=rfp.normalize_extracted_text(extracted)
            if not evidence['sourceComplete']:
                f['extractionEvidence']=evidence
                f['partialTextChars']=len(text)
                f['errorCategory']='pdf_ocr_incomplete'
                counts['pdf_ocr_incomplete']+=1
                continue
            if len(text.strip())<(30 if label.lower().endswith(('.xlsx','.pptx')) else 100):
                raise ValueError('no_searchable_text')
            triggers,snippets=rfp.parse_clauses(text)
            clauses=rfp.extract_rule_candidates(text,label)
            audit=rfp.preserve_unclassified_qualification(text,label,clauses)
            if len(text)>350000 or audit.get('sourceTextScanComplete') is not True:
                counts['still_scan_incomplete']+=1
                continue
            digest=hashlib.sha256(raw).hexdigest()
            f.update({'readable':True,'sourceSha256':digest,
                      'sourceTextScanComplete':True,'qualificationScanTruncated':False,
                      'unmatchedQualificationAnchorCount':0,
                      'clauseCandidateCount':len(clauses),
                      'textChars':len(text),'sourceUrl':item['url'],
                      'extractionEvidence':evidence})
            f.pop('errorCategory',None)
            f.pop('error',None)
            latest.append({'name':label,'sourceUrl':item['url'],
                           'readable':True,'clauseCandidates':clauses})
            counts['file_repaired']+=1
            counts['cache_hit' if origin=='verified_cache' else 'official_file_GET']+=1
        except Exception as exc:
            classification=rfp.classify_failure(exc)
            if classification=='official_attachment_reference_missing_422':
                f['errorCategory']=classification
                f['lastHttpStatus']=422
                counts['official_attachment_reference_missing_422']+=1
            counts['file_error_'+type(exc).__name__]+=1
            print('OPEN_RFP_FILE_FAILED',key,json.dumps({
                'filename':label,'error':type(exc).__name__,
                'classification':classification,'detail':str(exc)[:145]},
                ensure_ascii=False),flush=True)
    counts['alternate_pdf_evidence']+=rfp.annotate_official_pdf_siblings(scan['files'])
    return latest,counts


def update_evidence(rec,additions,now):
    existing=rec.get('changcomClauseEvidence') or {}
    new=rfp.compact_changcom_evidence({'status':'text_extracted_requires_review',
        'checkedAt':now,'files':additions,'readableDocumentCount':0})
    prior=existing.get('clauseCandidates') or {}
    combined={k:list(v) for k,v in prior.items() if isinstance(v,list)}
    for kind,items in new.get('clauseCandidates',{}).items():
        all_items=items+combined.get(kind,[])
        seen=set();kept=[]
        for obj in all_items:
            identity=(obj.get('sourceFile'),obj.get('text'))
            if identity not in seen:
                seen.add(identity);kept.append(obj)
        if kind=='staff_proof':
            def weight(v):
                t=str(v.get('text') or '')
                return (int(bool(rfp.re.search('4\\s*대\\s*보험|사대보험',t))),
                        int(bool(rfp.re.search('상주|현장\\s*근무',t))))
            kept=sorted(kept,key=weight,reverse=True)
        combined[kind]=kept[:6]
    byurl={x.get('url'):x for x in existing.get('files') or [] if x.get('url')}
    for x in new.get('files') or []:
        if x.get('url'):byurl[x['url']]=x
    existing.update({'status':rec.get('status'),'checkedAt':now,
       'readableDocumentCount':rec.get('readableDocumentCount'),
       'unreadableDocumentCount':rec.get('unreadableDocumentCount'),
       'manifestComplete':rec.get('manifestComplete') is True,
       'reviewComplete':False,'eligibilityVerified':False,
       'clauseCandidates':combined,'files':list(byurl.values())[:20]})
    rec['changcomClauseEvidence']=existing


def update_counts(rec,now,additions):
    fs=rec['files']
    rec['readableDocumentCount']=sum(f.get('readable') is True for f in fs)
    rec['unreadableDocumentCount']=len(fs)-rec['readableDocumentCount']
    rec['checkedAt']=now
    rec['classificationVersion']=rfp.CLASSIFICATION_VERSION
    rec['signatureReaderRepair']=REPAIR_VERSION
    rec['reviewComplete']=False
    rec['requiredConditionsComplete']=False
    if additions:update_evidence(rec,additions,now)


def run(data_dir,limit,execute=False,max_files=400):
    root=Path(data_dir)
    snap=root/'snapshots'
    coverage_path=snap/'rfp-coverage-index.json'
    meta_doc=read_json(snap/'rfp-top500-batch-metadata-20261111.json')
    stored=meta_doc.get('byNotice') or {}
    detail=read_json(snap/'rfp-clauses.json').get('byNotice') or {}
    batch=read_json(snap/'rfp-top500-batch-state-20261111.json')
    older=batch.get('scans') or {}
    archived=batch.get('archivedOutOfScopeScans') or {}
    known_full=[(detail,'rolling_full_scan'),(older,'prior_batch_scan'),
                (archived,'archived_batch_scan')]
    ledger=root/'rfp-request-ledger.sqlite3'
    entries=read_json(coverage_path).get('byNotice') or {}
    now=dt.datetime.now(dt.timezone.utc)
    open_rows=open_candidates(root,now)
    selected=[];categories=Counter();selected_file_count=0
    for key,ends in open_rows:
        scan=entries.get(key)
        if not isinstance(scan,dict):
            categories['not_scanned']+=1;continue
        if not scan.get('files'):
            categories['without_scannable_files']+=1;continue
        broken=failed_files(scan)
        if not broken:
            categories['all_readable']+=1;continue
        categories['partial']+=1
        broken=reader_retry_files(scan)
        if not broken:
            categories['already_attempted_this_reader_version']+=1
            continue
        meta,src=metadata_for(key,scan,stored,ledger,known_full)
        if not meta:
            categories['metadata_missing']+=1;continue
        categories['ready']+=1
        if len(selected)<limit and selected_file_count+len(broken)<=max_files:
            selected.append((key,ends,meta,src))
            selected_file_count+=len(broken)
    print('OPEN_RFP_CACHED_REPAIR_PLAN',json.dumps({
      'cutoffUTC':(now+dt.timedelta(hours=24)).isoformat(),
      'counts':dict(categories),'selectedNotices':len(selected),
      'selectedProblemFiles':selected_file_count,
      'noGovernmentMetadataAPICalls':True},ensure_ascii=False),flush=True)
    if not execute:return {'plan':dict(categories),'selected':len(selected)}
    if not selected:return {'result':'no_eligible_cached_metadata'}
    lock=open(root/'rfp-open-repair.lock','a+')
    fcntl.flock(lock,fcntl.LOCK_EX)
    results={};tally=Counter();pending={}

    def flush_pending():
        if not pending:return
        # Rebase every patch on the latest index so other notices are preserved.
        latest_doc=read_json(coverage_path)
        current_rows=latest_doc.get('byNotice') or {}
        timestamp=dt.datetime.now(dt.timezone.utc).isoformat()
        applied={}
        for key,(work,additions) in pending.items():
            current=current_rows.get(key)
            if not isinstance(current,dict):
                tally['changed_while_repairing']+=1;continue
            live_files=current.get('files') or []
            fixed_files=work.get('files') or []
            if (len(live_files)!=len(fixed_files) or
                [str(f.get('name') or '') for f in live_files]!=
                [str(f.get('name') or '') for f in fixed_files]):
                tally['changed_while_repairing']+=1;continue
            for i,entry in enumerate(fixed_files):
                live=live_files[i]
                if (entry.get('readable') is True and
                      entry.get('sourceTextScanComplete') is True and
                      entry.get('sourceSha256') and
                      (live.get('readable') is not True or
                       live.get('sourceTextScanComplete') is not True)):
                    live.update(entry)
                    # dict.update does not delete a formerly failed file's
                    # error key. A new verified success must remove it.
                    live.pop('errorCategory',None)
                    live.pop('error',None)
                    live.pop('lastHttpStatus',None)
                elif entry.get('errorCategory') in (
                       'official_attachment_reference_missing_422','pdf_ocr_incomplete'):
                    for field in ('errorCategory','lastHttpStatus','extractionEvidence',
                                  'partialTextChars'):
                        if field in entry:live[field]=entry[field]
                if live.get('readable') is not True or live.get('sourceTextScanComplete') is not True:
                    for field in ('lastReaderAttemptVersion','lastReaderAttemptAt'):
                        if entry.get(field):live[field]=entry[field]
                for field in ('alternatePdfEvidence','alternatePdfSourceSha256',
                              'alternatePdfEvidenceMode'):
                    if entry.get(field):live[field]=entry[field]
            update_counts(current,timestamp,additions)
            applied[key]={'readable':current['readableDocumentCount'],
                          'total':len(live_files),'repaired':len(additions)}
        if applied:
            latest_doc['generatedAt']=timestamp
            raw=(json.dumps(latest_doc,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
            write_atomic(coverage_path,raw)
            write_atomic(Path(str(coverage_path)+'.gz'),gzip.compress(raw,compresslevel=5,mtime=0))
            results.update(applied)
            tally['notices_updated']+=len(applied)
            print('OPEN_RFP_CACHED_REPAIR_COMMITTED',json.dumps({
                  'notices':len(applied),'totalUpdated':len(results),
                  'filesRepaired':tally['file_repaired'],
                  'allReadableNotices':sum(v['readable']==v['total'] for v in applied.values())},
                  ensure_ascii=False),flush=True)
        pending.clear()

    try:
        for key,deadline,meta,src in selected:
            if deadline.astimezone(dt.timezone.utc)<=dt.datetime.now(dt.timezone.utc)+dt.timedelta(hours=24):
                tally['skipped_deadline']+=1;continue
            # Do not use stale input to overwrite a reclassified manifest.
            latest=read_json(coverage_path).get('byNotice',{}).get(key)
            if not isinstance(latest,dict) or not metadata_valid(meta,latest):
                tally['changed_while_repairing']+=1;continue
            if not reader_retry_files(latest):continue
            work=json.loads(json.dumps(latest,ensure_ascii=False))
            additions,counters=process_one(key,work,meta,ledger)
            tally.update(counters)
            if not additions and not any(counters.get(k) for k in (
                 'official_attachment_reference_missing_422','pdf_ocr_incomplete',
                 'alternate_pdf_evidence','reader_attempt_recorded')):continue
            pending[key]=(work,additions)
            if len(pending)>=8:flush_pending()
        flush_pending()
        print('OPEN_RFP_CACHED_REPAIR_RESULT',json.dumps({
          'noticesUpdated':len(results),'counters':dict(tally),
          'remainingWithoutSavedMetadata':categories['metadata_missing'],
          'noGovernmentMetadataAPICalls':True},ensure_ascii=False),flush=True)
        return results
    finally:
        fcntl.flock(lock,fcntl.LOCK_UN)
        lock.close()


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--data-dir',default='/app/data')
    p.add_argument('--limit',type=int,default=60)
    p.add_argument('--max-files',type=int,default=150)
    p.add_argument('--execute',action='store_true')
    args=p.parse_args()
    run(args.data_dir,max(1,min(args.limit,300)),args.execute,
        max(1,min(args.max_files,600)))
