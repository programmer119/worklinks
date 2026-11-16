#!/usr/bin/env python3
"""Repair previously attempted live RFP attachments, using saved metadata ONLY.

Scope: WorkLinks SW notices whose bid closes more than 24h from run start.
No G2B bid/attachment metadata API is invoked. Only official attachment GETs
whose URLs were already saved, with the verified binary cache checked first.
Never reread successfully extracted siblings; never claim bidder qualification.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime as dt
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import urllib.parse
import zlib

import refresh_worklinks_rfp as rfp
from rfp_call_ledger import cache_key

KST=dt.timezone(dt.timedelta(hours=9))
REPAIR_VERSION='signature-reader-20261112'
READER_ATTEMPT_VERSION='framed-isolated-extract-v19-hwp-record-unicode-pdf750-20261117'
NESTED_ZIP_READER_VERSION='two-nested-levels-cumulative-250mb-v1'
PARTIAL_DRM_ZIP_READER_VERSION='complete-nonprotected-members-strict-drm-v1'
SPARSE_COVER_READER_VERSION='sha-psm6-11-and-source-title-20261117'
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


def false_hwpml_v13_success(file):
    """v13 mistakenly used the HTML parser on standalone HWPML .hwpx,
    incorporating embedded BINDATA as qualification text. Repair exact
    provenance even if the prior record was marked source complete.
    """
    return (file.get('detectedFormat')=='hwpml_xml'
        and file.get('lastReaderAttemptVersion')=='pdf25-blank-hwpml-psm611-v13-20261116')


def failed_files(scan):
    files=scan.get('files') or []
    # Do not download or retry an HWP that a fully read, same-name official
    # PDF already covers. Keep the HWP binary explicitly unread.
    return [f for f in files if isinstance(f,dict)
       and not rfp.hwp_covered_by_verified_pdf(f,files)
       and (false_hwpml_v13_success(f)
            or f.get('readable') is not True or f.get('sourceTextScanComplete') is not True
            or f.get('qualificationScanTruncated') is True
            or int(f.get('unmatchedQualificationAnchorCount') or 0)>0)]


def repair_file_priority(f):
    """Prioritize reader-fixable, already downloaded files over repeated HWP failures."""
    category=str(f.get('errorCategory') or '')
    suffix=Path(str(f.get('name') or '')).suffix.lower()
    # Repair parser output framing for sources whose child emitted diagnostics
    # alongside JSON; these errors are often not failures of the source bytes.
    if category in ('isolated_extraction_worker_reply_invalid',
                    'isolated_extraction_worker_failed'):
        return -4
    # Image-only HWPX members in two verified nine-document ZIP notices used
    # to make the entire archive no_searchable_text. Reader v7 recognizes
    # BinData/BMP OCR: recheck these saved ZIPs promptly, without any GET.
    if category=='no_searchable_text' and suffix=='.zip':
        return -3
    if category=='hwpx_image_ocr_deferred_to_repair':
        return -3
    # Reader v6 solves a verified pyhwp ColumnSet failure by decoding every
    # native HWP5 text record. Retry these proven new-reader fixes before OCR.
    if category=='hwp5txt_failed':
        return -2 if suffix in ('.xls','.xlsx') else -1
    if f.get('readable') is True and (f.get('qualificationScanTruncated') is True
                                     or f.get('staffingRoleScanTruncated') is True):
        return -1
    if category in ('pdf_ocr_incomplete','ocr_deferred_to_repair',
                    'image_ocr_incomplete','pdf_unreadable_page'):
        return 0
    if suffix in ('.xls','.hml','.html','.htm'):
        return 1
    if category=='no_searchable_text':
        return 2
    if category in ('hwp5txt_failed','invalid_hwp',
                    'source_extraction_timeout_deferred','pdf_over_page_limit'):
        return 5
    if f.get('readable') is True and (f.get('sourceTextScanComplete') is not True
                                     or f.get('qualificationScanTruncated') is True):
        return 4
    return 3


def choose_repair_batch(candidates,limit,max_files,per_notice_cap=3,minimum_old_ocr=0,minimum_format_fixes=0):
    """Complete easily recoverable notices first, then longer OCR documents.

    Keep reader-category priority, while avoiding a 91-page incomplete PDF
    occupying one of only four slots ahead of a nearly finished 26-page PDF.
    Legacy six-column input is retained for no-network compatibility tests.
    """
    chosen=[]
    used=0
    def priority(item):
        # item[6]: (additional non-retryable broken files, unfinished files,
        #             estimated OCR pages). The lowest unfinished work first.
        score=item[6] if len(item)>6 else (0,1,0)
        # Finishing a whole notice outranks the reader class of a single
        # file: 1 remaining PDF should not wait behind a notice with 2+
        # incomplete HWP/ZIP companions. Within equal completion distance,
        # preserve the established safer reader-category priority.
        return (score[0],score[1],item[0],score[2],item[1],item[2])
    ordered=sorted(candidates,key=priority)
    # Each small production batch reserves capacity for legacy OCR records that
    # have NEVER had a run with the deployed reader. Otherwise completion-first
    # ranking can repeatedly starve two/three-file notices behind short PDFs.
    old=[item for item in ordered if len(item)>7 and item[7] is True]
    reserved=old[:max(0,int(minimum_old_ocr))]
    reserved_ids={id(item) for item in reserved}
    # Legacy HWP, XML, HTML-XLS and ZIP format mismatches must not be
    # starved behind OCR. Reserve a real third file slot for those originals.
    formats=[item for item in ordered if len(item)>8 and item[8] is True
             and item[7] is not True and id(item) not in reserved_ids]
    for item in formats[:max(0,int(minimum_format_fixes))]:
        reserved.append(item)
        reserved_ids.add(id(item))
    ordered=reserved+[item for item in ordered if id(item) not in reserved_ids]
    for item in ordered:
        _priority,deadline,key,metadata,source,nfiles=item[:6]
        if len(chosen)>=limit or used>=max_files:break
        allowance=min(max(1,int(per_notice_cap)),nfiles,max_files-used)
        if allowance<=0:continue
        chosen.append((key,deadline,metadata,source,allowance))
        used+=allowance
    return chosen,used


def repair_completion_score(scan,pending):
    """Prioritize bids whose remaining verified files can actually finish."""
    incomplete=failed_files(scan)
    unrepairable=max(0,len(incomplete)-len(pending))
    pages=0
    for item in pending:
        info=item.get('extractionEvidence') or {}
        deferred=info.get('ocrBatchDeferredPages')
        failed=info.get('ocrFailedPages')
        if deferred is not None or failed is not None:
            pages+=max(1,int(deferred or 0)+int(failed or 0))
        elif info.get('pdfPages') is not None:
            pages+=max(1,int(info.get('pdfPages') or 0)-
                int(info.get('ocrRecoveredPages') or 0))
        else:
            pages+=8
    return (unrepairable,len(incomplete),pages)


def reader_retry_files(scan):
    """Resume OCR progress and one bounded retry for transient child failures.

    Stable unreadable bytes never create a forever-retrying OCR queue.
    """
    selected=[]
    transient={'isolated_extraction_worker_reply_invalid',
               'isolated_extraction_worker_failed',
               'source_extraction_timeout_deferred',
               'file_extract_failure'}
    for f in failed_files(scan):
        evidence=f.get('extractionEvidence') or {}
        if (f.get('errorCategory')=='pdf_ocr_incomplete'
                and f.get('lastSparseCoverAttemptVersion')!=SPARSE_COVER_READER_VERSION
                and int(evidence.get('ocrBatchDeferredPages') or 0)==0
                and 0<int(evidence.get('ocrFailedPages') or 0)<=2
                and 0<int(evidence.get('pdfPages') or 0)<=80):
            selected.append(f)
            continue
        if (f.get('errorCategory')=='drm_protected_original_requires_authorized_decryption'
                and f.get('lastPartialDrmZipAttemptVersion')!=PARTIAL_DRM_ZIP_READER_VERSION):
            selected.append(f)
            continue
        if (f.get('errorCategory')=='nested_archive_requires_review' and
                f.get('lastNestedZipAttemptVersion')!=NESTED_ZIP_READER_VERSION):
            selected.append(f)
            continue
        if f.get('lastReaderAttemptVersion')!=READER_ATTEMPT_VERSION:
            selected.append(f)
            continue
        if (str(f.get('errorCategory') or '') in transient
                and int(f.get('lastReaderTransientRetryCount') or 0)<1):
            try:
                stamp=dt.datetime.fromisoformat(
                    str(f.get('lastReaderAttemptAt') or '').replace('Z','+00:00'))
                aged=(dt.datetime.now(dt.timezone.utc)-stamp).total_seconds()
            except (ValueError,TypeError,OverflowError):
                aged=300
            if aged>=120:
                selected.append(f)
                continue
        evidence=f.get('extractionEvidence') or {}
        if (str(f.get('errorCategory') or '')=='pdf_ocr_incomplete'
                and int(evidence.get('ocrBatchDeferredPages') or 0)>0
                and ((int(evidence.get('ocrRecoveredPages') or 0)-
                      int(evidence.get('ocrRestoredPages') or 0))>0
                     or int(evidence.get('ocrNewFailedPages') or 0)>0)):
            # A genuinely new failed-page receipt is progress in a long PDF:
            # it is cached with a retry cooldown and the NEXT pass can reach
            # previously deferred pages. Do not count it as successfully read.
            # If neither a new success nor a new recorded failure exists,
            # leave the document incomplete without spinning forever.
            selected.append(f)
    return selected


def legacy_pdf_ocr_failure(file):
    """A PDF OCR source that has not run under the current repair reader."""
    return (str(file.get('errorCategory') or '')=='pdf_ocr_incomplete'
            and str(file.get('lastReaderAttemptVersion') or '')!=READER_ATTEMPT_VERSION)


FORMAT_REPAIR_ERRORS=frozenset((
    'invalid_hwp','file_extract_failure','invalid_legacy_xls',
    'unknown_archive_member_requires_review','large_xml_section',
    'archive_many_xml_files','hancom_cell_converter_required'))


def legacy_format_failure(file):
    return (str(file.get('errorCategory') or '') in FORMAT_REPAIR_ERRORS
            and str(file.get('lastReaderAttemptVersion') or '')!=READER_ATTEMPT_VERSION)


def ordered_retry_files(scan,prioritize_legacy_pdf_ocr=False,prioritize_format=False):
    """Reserve an actual file within the notice, not merely its notice ID."""
    pending=reader_retry_files(scan)
    if prioritize_format:
        return sorted(pending,key=lambda f:(
            0 if legacy_format_failure(f) else 1,repair_file_priority(f)))
    if prioritize_legacy_pdf_ocr:
        return sorted(pending,key=lambda f:(
            0 if legacy_pdf_ocr_failure(f) else 1,repair_file_priority(f)))
    return sorted(pending,key=repair_file_priority)


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


class VerifiedOriginalMissing(RuntimeError):
    """Second-stage verified original or its stored bytes are unavailable."""


def verified_download_queue(path):
    """Only notices completed by the independent downloader are scan-eligible."""
    if not path.is_file():
        return {}
    try:
        with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True,timeout=12) as db:
            rows=db.execute("""SELECT notice_key,download_total,download_done,metadata_json
                FROM rfp_dual_notices WHERE download_status='ready'""").fetchall()
    except (sqlite3.Error,OSError):
        return {}
    ready={}
    for key,total,done,payload in rows:
        try:
            meta=json.loads(payload)
            if not isinstance(meta,dict):
                continue
            receipts=meta.get('downloadVerifiedFiles')
            if (not isinstance(receipts,list) or not receipts or
                    len(receipts)!=total or done!=total or
                    any(not isinstance(f,dict) or
                        not f.get('url') or not f.get('sha256') or
                        len(str(f['sha256']))!=64 for f in receipts)):
                continue
        except (TypeError,ValueError,AttributeError):
            continue
        ready[key]=meta
    return ready


def fetch_verified_raw(source,ledgerpath,expected_sha):
    """Read ONLY the downloader's SHA-verified bytes. No network fallback."""
    url=source.get('url') or ''
    if not rfp.legal_file(source):
        raise ValueError('unapproved_official_file_url')
    if not isinstance(expected_sha,str) or len(expected_sha)!=64:
        raise VerifiedOriginalMissing('download_receipt_sha_missing')
    key=cache_key('official_attachment',url)
    if not ledgerpath.is_file():
        raise VerifiedOriginalMissing('verified_original_ledger_missing')
    with sqlite3.connect('file:'+str(ledgerpath)+'?mode=ro',uri=True,timeout=15) as conn:
        row=conn.execute("SELECT payload,sha256 FROM verified_cache WHERE request_key=? AND media_type='bytes'",
                         (key,)).fetchone()
    if row is None or row[1]!=expected_sha:
        raise VerifiedOriginalMissing('verified_original_not_in_downloader_cache')
    try:
        raw=zlib.decompress(row[0])
    except (zlib.error,TypeError) as exc:
        raise VerifiedOriginalMissing('verified_original_corrupt') from exc
    if len(raw)>rfp.MAX_FILE or hashlib.sha256(raw).hexdigest()!=expected_sha:
        raise VerifiedOriginalMissing('verified_original_hash_mismatch')
    return raw,'verified_cache'


def process_one(key,scan,meta,ledger,file_limit=None,prioritize_legacy_pdf_ocr=False,prioritize_format=False):
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
    # Examine all notice siblings together. The single-file wrapper here
    # previously lost the verified PDF companion and retried covered HWP.
    pending=ordered_retry_files(scan,prioritize_legacy_pdf_ocr,prioritize_format)
    if file_limit is not None:
        pending=pending[:max(0,int(file_limit))]
    receipts={f['url']:f for f in meta.get('downloadVerifiedFiles') or []
              if isinstance(f,dict) and f.get('url') and f.get('sha256')}
    for f in scan['files']:
        if f not in pending:continue
        previous_version=str(f.get('lastReaderAttemptVersion') or '')
        if f.get('errorCategory')=='pdf_ocr_incomplete':
            f['lastSparseCoverAttemptVersion']=SPARSE_COVER_READER_VERSION
        if f.get('errorCategory')=='nested_archive_requires_review':
            f['lastNestedZipAttemptVersion']=NESTED_ZIP_READER_VERSION
        if f.get('errorCategory')=='drm_protected_original_requires_authorized_decryption':
            f['lastPartialDrmZipAttemptVersion']=PARTIAL_DRM_ZIP_READER_VERSION
        if previous_version==READER_ATTEMPT_VERSION:
            f['lastReaderTransientRetryCount']=int(f.get('lastReaderTransientRetryCount') or 0)+1
        else:
            f['lastReaderTransientRetryCount']=0
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
            receipt=receipts.get(item['url'])
            if receipt is None:
                raise VerifiedOriginalMissing('file_not_in_completed_download_receipt')
            raw,origin=fetch_verified_raw(item,ledger,str(receipt['sha256']))
            f['detectedFormat']=rfp.detected_source_format(label,raw)
            extract_started=time.perf_counter()
            extracted,evidence,_=rfp.extract_cached_text(label,raw)
            extract_elapsed=round(time.perf_counter()-extract_started,3)
            # Source-linked, text-free operational profile: this distinguishes
            # page rasterization/Tesseract from PDF parsing and cache overhead.
            if int(evidence.get('ocrAttemptedPages') or 0)>0:
                print('OPEN_RFP_OCR_PHASE_PROFILE',json.dumps({
                    'notice':key,'file':label[:100],
                    'pdfPages':evidence.get('pdfPages'),
                    'pdfFiles':evidence.get('pdfFiles'),
                    'ocrNewPages':evidence.get('ocrAttemptedPages'),
                    'ocrRestoredPages':evidence.get('ocrRestoredPages'),
                    'extractWallSeconds':extract_elapsed,
                    'pdfOpenSeconds':evidence.get('ocrPdfOpenSeconds'),
                    'pdfTotalSeconds':evidence.get('ocrPdfTotalSeconds'),
                    'nativeTextSeconds':evidence.get('ocrNativeTextSeconds'),
                    'nativeMuPdfAcceptedFiles':evidence.get('ocrNativeMuPdfAcceptedFiles'),
                    'nativeMuPdfVerifiedPages':evidence.get('ocrNativeMuPdfVerifiedPages'),
                    'nativeMuPdfValidationSeconds':evidence.get('ocrNativeMuPdfValidationSeconds'),
                    'nativeMuPdfTextSeconds':evidence.get('ocrNativeMuPdfTextSeconds'),
                    'nativeMuPdfTextPages':evidence.get('ocrNativeMuPdfTextPages'),
                    'nativeMuPdfFallbackPages':evidence.get('ocrNativeMuPdfFallbackPages'),
                    'nativeFastProbeSeconds':evidence.get('ocrNativeFastProbeSeconds'),
                    'nativeFastProbePages':evidence.get('ocrNativeFastProbePages'),
                    'nativeFastSkippedPages':evidence.get('ocrNativeFastSkippedPages'),
                    'nativeFastFallbacks':evidence.get('ocrNativeFastFallbacks'),
                    'imageCheckSeconds':evidence.get('ocrImageCheckSeconds'),
                    'renderSeconds':evidence.get('ocrRenderSeconds'),
                    'tesseractSeconds':evidence.get('ocrTesseractSeconds'),
                    'receiptWriteSeconds':evidence.get('ocrReceiptWriteSeconds'),
                    'extractOutsidePdfSeconds':round(max(0,extract_elapsed-float(evidence.get('ocrPdfTotalSeconds') or 0)),3),
                    'extractFormatTimes':evidence.get('extractFormatTimes') or {},
                    'ocrRegionProbe':[probe for pdf in evidence.get('pdfSources',[]) if isinstance(pdf,dict)
                        for probe in pdf.get('ocrRegionProbe',[]) if isinstance(probe,dict)][:4],
                    'sourceComplete':evidence.get('sourceComplete')},
                    ensure_ascii=False,separators=(',',':')),flush=True)
            text=rfp.normalize_extracted_text(extracted)
            if not evidence['sourceComplete']:
                f['extractionEvidence']=evidence
                f['partialTextChars']=len(text)
                if int(evidence.get('protectedMemberCount') or 0)>0:
                    f['errorCategory']='drm_protected_original_requires_authorized_decryption'
                    f['error']='protected member(s) remain in verified archive; readable siblings extracted separately'
                    counts['partial_drm_archive']+=1
                else:
                    f['errorCategory']='pdf_ocr_incomplete'
                    f['error']='pdf_ocr_incomplete: unresolved PDF pages in source'
                    counts['pdf_ocr_incomplete']+=1
                continue
            if sum(ch.isalnum() for ch in text)<12:
                raise ValueError('no_searchable_text')
            triggers,snippets=rfp.parse_clauses(text)
            clauses=rfp.extract_rule_candidates(text,label)
            roles=rfp.extract_staffing_roles(text,label,item['url'])
            facts=rfp.extract_staffing_facts(text,label,item['url'])
            audit=rfp.preserve_unclassified_qualification(text,label,clauses)
            if len(text)>rfp.RFP_QUALIFICATION_TEXT_LIMIT or audit.get('sourceTextScanComplete') is not True:
                f['errorCategory']='source_scan_incomplete'
                f['error']='source_scan_incomplete: document exceeds clause coverage or anchors remain unmatched'
                f['partialTextChars']=len(text)
                f['extractionEvidence']=evidence
                counts['still_scan_incomplete']+=1
                continue
            digest=hashlib.sha256(raw).hexdigest()
            f.update({'readable':True,'sourceSha256':digest,
                      'sourceTextScanComplete':True,'qualificationScanTruncated':False,
                      'unmatchedQualificationAnchorCount':0,
                      'clauseCandidateCount':len(clauses),
                      'textChars':len(text),'sourceUrl':item['url'],
                      'extractionEvidence':evidence,
                      'staffingRoles':roles,'staffingFacts':facts,
                      'staffingRoleScanVersion':rfp.STAFFING_ROLE_SCAN_VERSION,
                      'staffingFactScanVersion':rfp.STAFFING_FACT_SCAN_VERSION,
                      'staffingRoleScanTruncated':len(text)>rfp.STAFFING_ROLE_TEXT_LIMIT})
            f.pop('errorCategory',None)
            f.pop('error',None)
            latest.append({'name':label,'sourceUrl':item['url'],
                           'readable':True,'clauseCandidates':clauses})
            counts['file_repaired']+=1
            counts['cache_hit']+=1
        except VerifiedOriginalMissing:
            # Missing originals belong to the downloader, never the parser.
            raise
        except Exception as exc:
            classification=rfp.classify_failure(exc)
            f['errorCategory']=classification
            f['error']=type(exc).__name__+': '+str(exc)[:165]
            if classification=='official_attachment_reference_missing_422':
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
    # Correct the cumulative notice status when a SHA-verified reparse has
    # recovered readable source. Never leave a successful PDF/HWPX repair
    # labeled text_unavailable; legal conditions still require later review.
    if (rec['readableDocumentCount']>0 and
        rec.get('manifestComplete') is True and
        rec.get('status') in ('text_unavailable','download_not_verified',
                              'text_extracted_requires_review')):
        rec['status']='text_extracted_requires_review'
        rec['reasonCode']='readable_text_requires_full_review'
    rec['checkedAt']=now
    rec['classificationVersion']=rfp.CLASSIFICATION_VERSION
    rec['signatureReaderRepair']=REPAIR_VERSION
    rec['reviewComplete']=False
    rec['requiredConditionsComplete']=False
    rec['staffingRoles']=rfp.staffing_summary(rec)
    rec['staffingFacts']=rfp.staffing_fact_summary(rec)
    rec['staffingRoleScanComplete']=bool(rec.get('manifestComplete') is True and
        all(rfp.staffing_effective_file_complete(f,fs) for f in fs))
    if additions:update_evidence(rec,additions,now)


def reconcile_old_verified_source_status(coverage_path,ready_downloads,open_keys,now):
    """Clear historical notice-level text_unavailable after verified OCR repair.

    Does not reparse, download, set legal review complete, or trust an
    unattested index file: each successful file's saved SHA must appear in
    its stage-2 receipt for the same named official attachment.
    """
    doc=read_json(coverage_path)
    rows=doc.get('byNotice') or {}
    fixed=[]
    for key in open_keys:
        record=rows.get(key)
        if not isinstance(record,dict) or record.get('status')!='text_unavailable':
            continue
        meta=ready_downloads.get(key)
        if not meta or not metadata_valid(meta,record):
            continue
        hashes_by_name={}
        receipts={x.get('url'):x.get('sha256')
                  for x in (meta.get('downloadVerifiedFiles') or [])
                  if isinstance(x,dict) and x.get('url') and x.get('sha256')}
        for item in (meta.get('attachments') or {}).get('items') or []:
            if not isinstance(item,dict):
                continue
            url=item.get('url')
            if url in receipts:
                hashes_by_name.setdefault(str(item.get('name') or ''),set()).add(receipts[url])
        restored=any(
            f.get('readable') is True and
            f.get('sourceTextScanComplete') is True and
            f.get('sourceSha256') in hashes_by_name.get(str(f.get('name') or ''),set())
            for f in (record.get('files') or [])
            if isinstance(f,dict))
        if not restored:
            continue
        update_counts(record,now,[])
        fixed.append(key)
    if fixed:
        doc['generatedAt']=now
        raw=(json.dumps(doc,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
        write_atomic(coverage_path,raw)
        write_atomic(Path(str(coverage_path)+'.gz'),
                     gzip.compress(raw,compresslevel=5,mtime=0))
        print('OPEN_RFP_STALE_REPAIRED_STATUS_RECONCILED',json.dumps({
            'count':len(fixed),'notices':sorted(fixed)[:30],
            'stage2ShaReceiptRequired':True,'legalReviewUnchanged':True},
            ensure_ascii=False),flush=True)
    return len(fixed)


def merge_verified_repair_attempt(live,entry):
    """Publish every attempted reader result while protecting newer successful scans.

    Prior logic only copied 422/PDF-incomplete errors. An XLS failure could
    remain labeled 'hwp5txt_failed' even after a new XLS reader had run.
    """
    if entry.get('lastReaderAttemptVersion')!=READER_ATTEMPT_VERSION:
        return False
    if (live.get('readable') is True and
            live.get('sourceTextScanComplete') is True and
            not false_hwpml_v13_success(live)):
        return False
    complete=(entry.get('readable') is True and
              entry.get('sourceTextScanComplete') is True and
              bool(entry.get('sourceSha256')))
    if complete:
        live.update(entry)
        for field in ('errorCategory','error','lastHttpStatus'):
            live.pop(field,None)
    else:
        # An incomplete source never becomes a success just because an OCR
        # engine was attempted. Preserve the actual reader result for triage.
        for field in ('errorCategory','error','lastHttpStatus','extractionEvidence',
                      'partialTextChars','detectedFormat','textChars',
                      'lastReaderAttemptVersion','lastReaderAttemptAt',
                      'lastNestedZipAttemptVersion','lastPartialDrmZipAttemptVersion',
                      'lastSparseCoverAttemptVersion'):
            if field in entry:live[field]=entry[field]
        if entry.get('errorCategory')!='official_attachment_reference_missing_422':
            live.pop('lastHttpStatus',None)
    for field in ('alternatePdfEvidence','alternatePdfSourceSha256',
                  'alternatePdfEvidenceMode'):
        if entry.get(field):live[field]=entry[field]
    return complete


def current_verified_download_metadata(queue_path,key):
    """Read only the selected notice, not all 3,000+ downloader receipts."""
    if not queue_path.is_file():return None
    with sqlite3.connect('file:'+str(queue_path)+'?mode=ro',
                         uri=True,timeout=12) as db:
        record=db.execute('''SELECT download_total,download_done,metadata_json
            FROM rfp_dual_notices WHERE notice_key=? AND download_status='ready' ''',
            (key,)).fetchone()
    if record is None:return None
    total,done,payload=record
    try:
        meta=json.loads(payload)
        receipts=meta.get('downloadVerifiedFiles') or []
        if (not isinstance(meta,dict) or done!=total or
                total!=len(receipts) or
                any(not isinstance(x,dict) or len(str(x.get('sha256') or ''))!=64
                    for x in receipts)):
            return None
        return meta
    except (ValueError,TypeError,AttributeError):
        return None


def verified_complete_for_early_checkpoint(record,metadata):
    """Never claim the full notice done without live SHA-verified originals."""
    if record.get('manifestChangePending') is True or not metadata_valid(metadata,record):
        return False
    from rfp_management_reconcile import latest_complete
    versions={'classificationVersion':rfp.CLASSIFICATION_VERSION,
              'staffingRoleScanVersion':rfp.STAFFING_ROLE_SCAN_VERSION,
              'staffingFactScanVersion':rfp.STAFFING_FACT_SCAN_VERSION,
              'hwpxReaderVersion':rfp.HWPX_READER_VERSION}
    if not latest_complete(rfp.compact_coverage(record),versions):
        return False
    receipts={x.get('url'):x.get('sha256')
              for x in metadata.get('downloadVerifiedFiles') or []
              if isinstance(x,dict)}
    sources={}
    for item in metadata['attachments']['items']:
        sources.setdefault(str(item.get('name') or ''),[]).append(item)
    for f in record.get('files') or []:
        label=str(f.get('name') or '')
        candidates=sources.get(label) or []
        if not candidates:return False
        original=candidates.pop(0)
        if f.get('readable') is True:
            sha=str(f.get('sourceSha256') or '')
            if not sha or sha!=receipts.get(original.get('url')):
                return False
    return True


def source_verified_current_repair_rows(root,snapshot_rows):
    """Use the newest authoritative scan evidence for repair, not an older
    successful snapshot shadowed by a later OCR-failure checkpoint.

    Never merge records from a changed official manifest. A failing new
    extraction is kept incomplete; an old successful record cannot be made
    'newly successful' by a mere timestamp bump.
    """
    from rfp_management_reconcile import read_evidence, same_thumbnail_original
    _versions,authoritative=read_evidence(root)
    rows=dict(snapshot_rows)
    for key,previous in snapshot_rows.items():
        latest=authoritative.get(key)
        if (not isinstance(previous,dict) or not isinstance(latest,dict)
                or str(latest.get('checkedAt') or '')<=
                   str(previous.get('checkedAt') or '')):
            continue
        if same_thumbnail_original(previous,latest):
            rows[key]=latest
    return rows


def run(data_dir,limit,execute=False,max_files=400,workers=1,
        per_notice_cap=3,minimum_old_ocr=0,minimum_format_fixes=0,
        only_notices=None):
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
    # The scheduler runs repair in an isolated temporary workspace.
    # Resolve the live stage-2 queue from the explicitly supplied server path.
    queue_path=Path(os.environ.get('WORKLINKS_RFP_DUAL_QUEUE_DB') or
                    root/'rfp-dual-queue.sqlite3')
    ready_downloads=verified_download_queue(queue_path)
    entries=source_verified_current_repair_rows(
        root,read_json(coverage_path).get('byNotice') or {})
    now=dt.datetime.now(dt.timezone.utc)
    open_rows=open_candidates(root,now)
    if only_notices is not None:
        allowed=set(only_notices)
        open_rows=[item for item in open_rows if item[0] in allowed]
    candidates=[];categories=Counter();selected_file_count=0
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
        # Snapshot metadata and file URLs are NEVER scanning eligibility.
        meta=ready_downloads.get(key)
        if not meta:
            categories['waiting_for_verified_download']+=1;continue
        if not metadata_valid(meta,scan):
            categories['download_manifest_mismatch']+=1;continue
        src='verified_download_queue'
        categories['ready']+=1
        old_ocr=any(legacy_pdf_ocr_failure(f) for f in broken)
        old_format=any(legacy_format_failure(f) for f in broken)
        candidates.append((min(repair_file_priority(f) for f in broken),
                           ends,key,meta,src,len(broken),
                           repair_completion_score(scan,broken),old_ocr,old_format))
    selected,selected_file_count=choose_repair_batch(candidates,limit,max_files,
        per_notice_cap=per_notice_cap,minimum_old_ocr=minimum_old_ocr,
        minimum_format_fixes=minimum_format_fixes)
    legacy_pdf_keys={item[2] for item in candidates if item[7] is True}
    legacy_format_keys={item[2] for item in candidates if item[8] is True and item[7] is not True}
    print('OPEN_RFP_CACHED_REPAIR_PLAN',json.dumps({
      'cutoffUTC':(now+dt.timedelta(hours=24)).isoformat(),
      'counts':dict(categories),'selectedNotices':len(selected),
      'selectedProblemFiles':selected_file_count,
      'legacyReadyCandidates':sum(item[7] is True for item in candidates),
      'legacyFormatReadyCandidates':sum(item[8] is True for item in candidates),
      'legacySelectedNotices':sum(any(item[2]==chosen[0] and item[7] is True
                                 for item in candidates) for chosen in selected),
      'legacyFormatSelectedNotices':sum(chosen[0] in legacy_format_keys for chosen in selected),
      'selectedIds':[chosen[0] for chosen in selected],
      'filesPerNoticeCap':max(1,int(per_notice_cap)),
      'noGovernmentMetadataAPICalls':True,
      'noGovernmentAttachmentGETs':True},ensure_ascii=False),flush=True)
    if not execute:return {'plan':dict(categories),'selected':len(selected)}
    lock=open(root/'rfp-open-repair.lock','a+')
    fcntl.flock(lock,fcntl.LOCK_EX)
    results={};tally=Counter();pending={}

    def flush_pending():
        if not pending:return
        # Rebase every patch on the latest index so other notices are preserved.
        latest_doc=read_json(coverage_path)
        current_rows=latest_doc.get('byNotice') or {}
        current_views=source_verified_current_repair_rows(root,current_rows)
        timestamp=dt.datetime.now(dt.timezone.utc).isoformat()
        applied={}
        for key,(work,additions) in pending.items():
            current=current_views.get(key)
            if not isinstance(current,dict):
                tally['changed_while_repairing']+=1;continue
            live_files=current.get('files') or []
            fixed_files=work.get('files') or []
            if (len(live_files)!=len(fixed_files) or
                [str(f.get('name') or '') for f in live_files]!=
                [str(f.get('name') or '') for f in fixed_files]):
                tally['changed_while_repairing']+=1;continue
            for i,entry in enumerate(fixed_files):
                merge_verified_repair_attempt(live_files[i],entry)
            update_counts(current,timestamp,additions)
            # Publish the newest verified checkpoint plus this attempt, never
            # an obsolete all-readable snapshot that hides later PDF errors.
            current_rows[key]=current
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
        clock=time.perf_counter()
        reconciled=reconcile_old_verified_source_status(
            coverage_path,ready_downloads,
            {key for key,_deadline in open_rows},
            dt.datetime.now(dt.timezone.utc).isoformat())
        if not selected:
            return {'result':'no_eligible_verified_download',
                    'reconciledOldStatus':reconciled}
        # The snapshot belongs to this isolated stage; concurrent threads only
        # read it. The downloader's current SHA receipt is checked per notice.
        latest_index=source_verified_current_repair_rows(
            root,read_json(coverage_path).get('byNotice') or {})
        tasks=[]
        for key,deadline,meta,src,file_limit in selected:
            if deadline.astimezone(dt.timezone.utc)<=dt.datetime.now(dt.timezone.utc)+dt.timedelta(hours=24):
                tally['skipped_deadline']+=1;continue
            current=latest_index.get(key)
            if not isinstance(current,dict) or not metadata_valid(meta,current):
                tally['changed_while_repairing']+=1;continue
            if not reader_retry_files(current):continue
            fresh=current_verified_download_metadata(queue_path,key)
            if not fresh or fresh.get('downloadVerifiedFiles')!=meta.get('downloadVerifiedFiles'):
                tally['download_receipt_changed']+=1;continue
            tasks.append((key,meta,file_limit,current,key in legacy_pdf_keys,key in legacy_format_keys))
        print('OPEN_RFP_PARALLEL_WORKERS',json.dumps({
            'workers':min(max(1,int(workers)),3,len(tasks)) if tasks else 0,
            'selectedFiles':sum(x[2] for x in tasks),
            'noticeCount':len(tasks)},separators=(',',':')),flush=True)
        def extract_task(item):
            key,meta,file_limit,current,prefer_pdf,prefer_format=item
            work=json.loads(json.dumps(current,ensure_ascii=False))
            begun=time.perf_counter()
            recovered,counters=process_one(
                key,work,meta,ledger,file_limit=file_limit,
                prioritize_legacy_pdf_ocr=prefer_pdf,prioritize_format=prefer_format)
            return work,recovered,counters,time.perf_counter()-begun

        # OCR itself runs in up to three independent subprocesses, via separate
        # worker threads. Python-side reader provenance is thread-local, and
        # each SHA/page OCR SQLite connection is private to its worker.
        # Publication, downloader state changes, and queue reconciliation
        # stay single-writer on the parent thread.
        worker_count=min(max(1,int(workers)),3,len(tasks)) if tasks else 1
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures={executor.submit(extract_task,item):item for item in tasks}
            for future in as_completed(futures):
                key,meta,file_limit,current,prefer_pdf,prefer_format=futures[future]
                try:
                    work,additions,counters,elapsed=future.result()
                except VerifiedOriginalMissing as exc:
                    from rfp_dual_queue import RfpDualQueue
                    RfpDualQueue(queue_path).mark_download_missing(key)
                    tally['returned_to_downloader']+=1
                    print('OPEN_RFP_RETURNED_TO_DOWNLOADER',key,str(exc)[:100],flush=True)
                    continue
                except Exception as exc:
                    tally['reader_worker_failed']+=1
                    print('OPEN_RFP_WORKER_FAILURE',key,
                          type(exc).__name__,str(exc)[:150],flush=True)
                    continue
                # Do not mark an old official original successful if a later
                # stage-2 download replaced the selected SHA while OCR ran.
                fresh=current_verified_download_metadata(queue_path,key)
                if not fresh or fresh.get('downloadVerifiedFiles')!=meta.get('downloadVerifiedFiles'):
                    tally['download_receipt_changed']+=1
                    continue
                tally.update(counters)
                should_publish=(bool(additions) or any(
                    counters.get(k) for k in (
                      'official_attachment_reference_missing_422',
                      'pdf_ocr_incomplete','alternate_pdf_evidence',
                      'reader_attempt_recorded')))
                if not should_publish:continue
                pending[key]=(work,additions)
                # A newly completed full notice becomes authoritative NOW,
                # via its small per-notice SQLite checkpoint. This does not
                # rewrite the entire RFP JSON or wait for slow sibling workers.
                updated=json.loads(json.dumps(current,ensure_ascii=False))
                for live,entry in zip(updated.get('files') or [],work.get('files') or []):
                    merge_verified_repair_attempt(live,entry)
                checked=dt.datetime.now(dt.timezone.utc).isoformat()
                update_counts(updated,checked,additions)
                early=False
                if verified_complete_for_early_checkpoint(updated,fresh):
                    fingerprint=':'.join(str(v) for v in (
                        rfp.CLASSIFICATION_VERSION,rfp.HWPX_READER_VERSION,
                        rfp.STAFFING_ROLE_SCAN_VERSION,rfp.STAFFING_FACT_SCAN_VERSION))
                    try:
                        early=bool(rfp.publish_notice_checkpoint(
                            key,updated,fingerprint))
                    except (sqlite3.Error,OSError,ValueError) as exc:
                        tally['checkpoint_failed']+=1
                        print('OPEN_RFP_CHECKPOINT_RETRY_AT_BATCH_END',
                              key,type(exc).__name__,flush=True)
                tally['early_verified_checkpoint']+=int(early)
                tally['worker_completed']+=1
                print('OPEN_RFP_PARALLEL_FILE_FINISHED',json.dumps({
                    'notice':key,'seconds':round(elapsed,2),
                    'filesRepaired':len(additions),'checkpointSaved':early,
                    'parallelism':worker_count},separators=(',',':')),flush=True)
        # Full cumulative JSON + gzip are written just ONCE per batch.
        # The final server publisher will rebase on newer live/checkpoint
        # evidence before atomically replacing any public snapshot.
        flush_pending()
        print('OPEN_RFP_CACHED_REPAIR_RESULT',json.dumps({
          'noticesUpdated':len(results),'counters':dict(tally),
          'parallelism':worker_count,'seconds':round(time.perf_counter()-clock,2),
          'remainingWithoutSavedMetadata':categories['metadata_missing'],
          'noGovernmentMetadataAPICalls':True,
          'noGovernmentAttachmentGETs':True},ensure_ascii=False),flush=True)
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
    p.add_argument('--only-notice',action='append',dest='only_notices',
                   help='Repair only specified official notice key; may repeat')
    p.add_argument('--workers',type=int,default=1,
                   help='parallel OCR workers; maximum 3 to protect server123')
    p.add_argument('--per-notice-file-cap',type=int,default=3)
    p.add_argument('--minimum-old-ocr',type=int,default=0)
    p.add_argument('--minimum-format-fixes',type=int,default=0)
    args=p.parse_args()
    run(args.data_dir,max(1,min(args.limit,300)),args.execute,
        max(1,min(args.max_files,600)),max(1,min(args.workers,3)),
        per_notice_cap=max(1,min(args.per_notice_file_cap,3)),
        minimum_old_ocr=max(0,min(args.minimum_old_ocr,3)),
        minimum_format_fixes=max(0,min(args.minimum_format_fixes,3)),
        only_notices=set(args.only_notices) if args.only_notices else None)
