#!/usr/bin/env python3
"""Incrementally extract LIMITED qualification excerpts from public G2B RFPs.
Never classify final bid eligibility from a keyword or omit review of attachments.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import nullcontext
import datetime as dt
import hashlib
import io
import json
import os
import shutil
import sqlite3
import threading
from pathlib import Path
import re
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
import zipfile
try:
    from rfp_call_ledger import CallLedger, cache_key
except ModuleNotFoundError as exc:
    if exc.name!='rfp_call_ledger':raise
    # importlib.spec_from_file_location/runpy do not put the source
    # directory on sys.path, although this script's sibling is present.
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parent))
    from rfp_call_ledger import CallLedger, cache_key

_LEDGER_LOCK=threading.Lock()
_NOTICE_CONTEXT=threading.local()
_NOTICE_DEADLINES={}
_DOCUMENT_SCAN=threading.local()
_LEDGER_INSTANCE=None
_LEDGER_PATH=None

RFP_TEXT_CACHE_VERSION=1

def extract_cached_text(name, raw):
    """Verified, content-addressed extracted text. Reclassify without rereading HWP/OCR.

    Cache identity includes the exact binary hash and extractor revision. A
    successful source extraction is cached; incomplete OCR/errors are not.
    No official metadata or attachment HTTP request is made by this function.
    """
    ledger=active_rfp_ledger()
    digest=hashlib.sha256(raw).hexdigest()
    key=cache_key('rfp_extracted_text',RFP_TEXT_CACHE_VERSION,HWPX_READER_VERSION,
                  Path(name).suffix.lower(),digest)
    if ledger is not None:
        cached=ledger.get_json(key,source_revision='reader-'+str(RFP_TEXT_CACHE_VERSION))
        if (isinstance(cached,dict) and isinstance(cached.get('text'),str)
                and isinstance(cached.get('evidence'),dict)
                and cached['evidence'].get('sourceComplete') is True):
            return cached['text'],cached['evidence'],True
    text,evidence=extract_with_source_status(name,raw)
    if ledger is not None and evidence.get('sourceComplete') is True:
        ledger.save_json(key,{'text':text,'evidence':evidence},
                         source_revision='reader-'+str(RFP_TEXT_CACHE_VERSION),
                         max_bytes=16_000_000)
    return text,evidence,False

def active_rfp_ledger():
    """Only server123 opts in; local no-network regression remains isolated."""
    global _LEDGER_INSTANCE, _LEDGER_PATH
    path=os.environ.get('WORKLINKS_RFP_LEDGER_DB')
    if not path:return None
    if path!=_LEDGER_PATH:
        with _LEDGER_LOCK:
            if path!=_LEDGER_PATH:
                _LEDGER_INSTANCE=CallLedger(path)
                _LEDGER_PATH=path
    return _LEDGER_INSTANCE

BASE=os.environ.get('WORKLINKS_G2B_API','https://api-suaveforge.suaveforge.com:18458/api/g2b').rstrip('/')+'/'
ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'startup-support/rfp-clauses.json'
COVERAGE_DEST=ROOT/'startup-support/rfp-coverage-index.json'
CHANGCOM_SOURCE=ROOT/'startup-support/changcom-actionable.json'
CHANGCOM_EVIDENCE_DEST=ROOT/'startup-support/changcom-rfp-evidence.json'
CHANGCOM_BACKFILL60=ROOT/'startup-support/audits/changcom-rfp-backfill-60-20261110.json'
CHANGCOM_URGENT_RECOVERY=ROOT/'startup-support/audits/changcom-priority-rfp-recovery-20261111.json'
MAX_FILE=24_000_000
# OCR is local-only and bounded to prevent runaway attachment processing.
MAX_PDF_OCR_PAGES=24
MAX_PDF_OCR_PIXELS=12_000_000
PDF_OCR_TARGET_DPI=300
MAX_DOCUMENTS=24
# Per-member AND total XML caps are needed for safe HWPX decompression.
# 3MB per member was rejecting real official documents before text extraction.
MAX_HWPX_XML_MEMBER=28_000_000
MAX_HWPX_XML_TOTAL=90_000_000
HWPX_READER_VERSION=3
PARTNER_VERIFIED_CODES={'1426','1468','1469','1470'}
TEXT_FORMATS=('.hwp','.hwpx','.pdf','.docx','.xlsx','.pptx','.zip','.png','.jpg','.jpeg','.bmp','.tif','.tiff','.webp')
CLASSIFICATION_VERSION=23
EXTRA_QUALIFICATION_ANCHORS=re.compile(
    r'입찰\s*참가\s*(?:자격|요건|등록|가능|할\s*수)|참가\s*자격|업종\s*코드|소프트웨어사업자|직접\s*생산|'
    r'중소기업\s*확인|중소기업자|중소기업\s*(?:만|에\s*한정|이어야|이하)|'
    r'(?<!중)소기업|소상공인|지역\s*제한|본점\s*소재|'
    r'수행\s*실적|실적\s*증명|재직\s*증명|4대\s*보험|사대보험|공동\s*수급|분담\s*이행|'
    r'하도급|기술\s*인력|상주\s*(?:인력|기술자|개발자)|(?:중급|고급|초급|특급)\s*(?:이상\s*)?(?:기술자|개발자)|[0-9]+(?:\.[0-9]+)?\s*(?:MM|M/M|맨먼스)|등록\s*업체|정보통신공사업|제안\s*자격|'
    r'조세\s*포탈|제\s*8조의\s*2|특별법인|입찰보증금|'
    r'입찰참가자격등록증상|입찰참가자격의\s*판단기준일|입찰업체\s*서약서', re.I)

# Priority is derived from *all* live indexed bids. No pinned notice IDs.
SIGNALS={
 '입찰참가자격':r'입찰\s*참가\s*자격|참가\s*자격',
 '직접생산':r'직접\s*생산|세부품명번호',
 '중소기업':r'중소기업\s*확인|소기업|소상공인',
 '수행실적':r'수행\s*실적|유사\s*용역\s*실적|실적\s*증명',
 '기술인력':r'투입\s*인력|기술\s*인력|상주\s*인력|자격증|재직\s*증명|4대\s*보험|맨먼스|\bMM\b|현장\s*상주|중급\s*기술자',
 '지역제한':r'지역\s*제한|본점\s*소재|소재지',
 '공동수급':r'공동\s*수급|분담\s*이행|하도급'
}
AGENTS={'User-Agent':'WorkLinks-RFP-ReadOnly/1.0','Accept':'application/json'}
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,request,fp,code,msg,headers,newurl):
        raise ValueError('redirect_forbidden')

OPENER=urllib.request.build_opener(NoRedirect)
def fetch_json(url):
    # Every physical proxy request is logged; cache reuse is handled by the
    # verified per-notice snapshot/ledger, never by pretending HTTP was called.
    request=urllib.request.Request(url,headers=AGENTS)
    ledger=active_rfp_ledger()
    parts=urllib.parse.urlsplit(url)
    query=dict(urllib.parse.parse_qsl(parts.query))
    safe_query=[(k,v) for k,v in query.items()
                if k.lower() not in ('servicekey','apikey','token','key')]
    notice_key=(str(query['bidNo'])+':'+str(query.get('order') or '0').zfill(3)
                if query.get('bidNo') and 'bid-evidence' in parts.path else None)
    reqkey=cache_key('proxy',parts.path,sorted(safe_query))
    for attempt in range(4):
        try:
            with OPENER.open(request,timeout=24) as r:
                data=r.read(2_000_000)
                status=getattr(r,'status',200)
                if len(data)>=2_000_000:raise ValueError('oversize_json')
                parsed=json.loads(data.decode('utf-8'))
            if ledger:
                ledger.record('proxy_http',reqkey,'http_ok',http_status=status,
                              notice_key=notice_key,
                              response_sha256=hashlib.sha256(data).hexdigest())
            return parsed
        except (urllib.error.HTTPError,TimeoutError,ConnectionError,
                urllib.error.URLError,ValueError,UnicodeError) as ex:
            if ledger:
                ledger.record('proxy_http',reqkey,'http_failed',
                              notice_key=notice_key,
                              http_status=getattr(ex,'code',None),
                              error_class=type(ex).__name__)
            if isinstance(ex,urllib.error.HTTPError):
                retry=ex.code in (429,500,502,503,504)
            else:
                retry=isinstance(ex,(TimeoutError,ConnectionError,urllib.error.URLError))
            if not retry or attempt==3:raise
        time.sleep(min(8,1.5*(2**attempt)))
def needs_hwpx_reader_retry(record):
    if (record or {}).get('hwpxReaderVersion',0)>=HWPX_READER_VERSION:
        return False
    return any(f.get('errorCategory')=='large_xml_section' and
               (Path(f.get('name') or '').suffix.lower() in ('.hwpx',''))
               for f in (record or {}).get('files') or [])

def staffing_general_annex_file(name):
    """General legal-procedure packets, never a project staffing specification."""
    label=str(name or '')
    return bool(
        re.search(r'입찰\s*유의서.{0,90}계약\s*일반\s*조건.{0,90}(?:특수\s*조건|적격\s*심사)',label,re.I)
        and label.lower().endswith('.zip'))



def staffing_ancillary_form_without_extractable_text(file):
    """Exclude only known blank submission forms from the *staffing* scan.

    A blank application/pledge form is not an RFP personnel specification.
    Its extraction failure remains visible in general document coverage.
    Never exempt an unreadable proposal, technical appendix, or unknown form.
    """
    if not isinstance(file, dict) or file.get('readable') is True:
        return False
    if str(file.get('errorCategory') or '') != 'no_searchable_text':
        return False
    name=Path(str(file.get('name') or '')).name.strip()
    return bool(re.fullmatch(
        r'(?:입찰\s*참가\s*신청서|서약서\s*[\(\[]\s*서식\s*[\)\]])\.(?:hwp|hwpx|pdf)',
        name, re.I))


def staffing_effective_file_complete(file, files):
    """An expressly skipped, same-stem official HWP uses the scanned PDF instead.

    This does NOT assert that the HWP binary was examined or byte-identical.
    The cited PDF, verified by SHA in the SAME manifest, is the effective source.
    """
    if not isinstance(file, dict):return False
    if staffing_ancillary_form_without_extractable_text(file):return True
    # Generic nationwide contract-law archives are outside the project-specific
    # staffing scope; preserve their separate qualification extraction failure.
    if (staffing_general_annex_file(file.get('name')) or
            staffing_source_is_general_example(file.get('name'))):return True
    if (file.get('readable') is True and
            file.get('sourceTextScanComplete') is True and
            int(file.get('staffingRoleScanVersion') or 0)>=STAFFING_ROLE_SCAN_VERSION and
            int(file.get('staffingFactScanVersion') or 0)>=STAFFING_FACT_SCAN_VERSION and
            file.get('staffingRoleScanTruncated') is not True):
        return True
    return (file.get('skippedDuplicateFormat') is True and
            file.get('readable') is not True and
            hwp_covered_by_staffing_verified_pdf(file, files))


def hwp_covered_by_staffing_verified_pdf(file, files):
    pdf=verified_pdf_companion(file, files)
    return bool(pdf and file.get('alternatePdfEvidence')==pdf.get('name')
        and file.get('alternatePdfSourceSha256')==pdf.get('sourceSha256')
        and int(pdf.get('staffingRoleScanVersion') or 0)>=STAFFING_ROLE_SCAN_VERSION
        and pdf.get('staffingRoleScanTruncated') is not True)


def staffing_source_is_general_example(filename, quote=''):
    """Legal templates and score examples are not project staffing demands."""
    name=str(filename or '')
    source=str(quote or '')
    if re.search(r'(?:행안부\s*예규|행정안전부\s*예규|지방자치단체\s*입찰시\s*낙찰자\s*결정기준|입찰\s*및\s*계약집행기준)',name,re.I):
        return True
    if re.search(r'(?:산정\s*예시|산정\s*사례|평가\s*예시|배점\s*예시)',source):
        return True
    return False


def staffing_scan_pending(record):
    """A prior qualification scan is not proof that roles/headcounts were scanned.

    Return True only for reusable, readable attachments missing current staffing
    provenance. An invalid/missing record is handled by ordinary RFP discovery.
    """
    if not isinstance(record,dict) or record.get('status')!='text_extracted_requires_review':
        return False
    files=[f for f in record.get('files') or [] if isinstance(f,dict)]
    if not files:return False
    if (record.get('staffingRoleScanComplete') is True and
            all(staffing_effective_file_complete(f,files) for f in files)):
        return False
    return any(f.get('readable') is True and
               (int(f.get('staffingRoleScanVersion') or 0)<STAFFING_ROLE_SCAN_VERSION
                or int(f.get('staffingFactScanVersion') or 0)<STAFFING_FACT_SCAN_VERSION
                or f.get('staffingRoleScanTruncated') is True)
               for f in files)


def reusable_rfp_extraction(record):
    """Reuse a sourced RFP scan; legal qualification review is a separate gate.

    A new official notice order has a different key. Explicit parser-version
    upgrades and failed/unreadable scans remain eligible for another attempt.
    """
    if not isinstance(record,dict):return False
    if record.get('status')!='text_extracted_requires_review':return False
    if record.get('manifestChangePending'):return False
    if record.get('classificationVersion')!=CLASSIFICATION_VERSION:return False
    if needs_hwpx_reader_retry(record):return False
    if int(record.get('readableDocumentCount') or 0)<1:return False
    return any(f.get('readable') is True and f.get('sourceSha256')
               for f in (record.get('files') or []) if isinstance(f,dict))

def partial_retry_due(record,utc=None):
    """Retry only transient missing files / incomplete official manifests.

    A PDF image, unsupported HWP or oversized file will not become readable
    merely by repeating the same API request. Successful partial documents
    remain available; no legal-completeness claim follows from this retry.
    """
    if not isinstance(record,dict) or record.get('status')!='text_extracted_requires_review':
        return False
    if int(record.get('partialRetryCount') or 0)>=2:
        return False
    failures=[str(f.get('errorCategory') or '') for f in
              (record.get('files') or []) if isinstance(f,dict)
              and f.get('readable') is not True]
    retryable=any(v in ('file_download_connection_error',
                        'file_download_http_429','file_download_http_500',
                        'file_download_http_502','file_download_http_503',
                        'file_download_http_504') for v in failures)
    retryable=retryable or record.get('manifestComplete') is False
    if not retryable:return False
    last=str(record.get('checkedAt') or '')
    if not last:return True
    try:
        when=dt.datetime.fromisoformat(last.replace('Z','+00:00'))
        now=utc or dt.datetime.now(dt.timezone.utc)
        return when.tzinfo is None or now-when>=dt.timedelta(hours=24)
    except (ValueError,TypeError):
        return True

# Only attachment METADATA is periodically compared. Unchanged documents
# never need to be downloaded. Same-order binary changes with identical
# metadata cannot be proven without a separate, explicit hash audit.
MAX_MANIFEST_PROBES_PER_RUN=2
MANIFEST_PROBE_INTERVAL=dt.timedelta(hours=36)


def official_manifest_signature(data):
    docs=(data or {}).get('attachments') or {}
    notice=(data or {}).get('noticeDocuments') or {}
    # Partial/failed sources do not establish that an attachment was removed.
    if not (docs.get('ok') and docs.get('complete') and
            notice.get('ok') and notice.get('complete') and
            docs.get('eorderCount') is not None):
        return None
    items=docs.get('items') or []
    if not isinstance(items,list):return None
    normalized=sorted(
        (str(f.get('name') or '').strip(),str(f.get('url') or '').strip(),
         str(f.get('source') or '').strip(),
         str(f.get('officialNoticeField') or '').strip())
        for f in items if isinstance(f,dict))
    payload=json.dumps(normalized,ensure_ascii=False,separators=(',',':'))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def manifest_probe_due(record,now):
    if not reusable_rfp_extraction(record):return False
    # A failed/incomplete metadata probe must rotate out for 36 hours too;
    # otherwise the same eight legacy records monopolize every hourly run.
    last=(record.get('manifestCheckedAt') or
          (record.get('checkedAt') if record.get('manifestSignature') else ''))
    if not last:return True
    try:
        checked=dt.datetime.fromisoformat(str(last).replace('Z','+00:00'))
        return not checked.tzinfo or now-checked>=MANIFEST_PROBE_INTERVAL
    except (ValueError,TypeError):
        return True


def inspect_manifest_probe(data,existing,checked_at):
    sig=official_manifest_signature(data)
    if not sig:
        return {'manifestCheckedAt':checked_at,
                'lastManifestProbeStatus':'metadata_incomplete'},'incomplete'
    previous=str((existing or {}).get('manifestSignature') or '')
    result={'manifestCheckedAt':checked_at,'lastManifestProbeStatus':'complete'}
    if previous and previous!=sig:
        result.update(manifestChangePending=True,manifestPendingSignature=sig)
        return result,'changed'
    if not previous:
        old_files=[str(f.get('name') or '').strip() for f in
                   (existing or {}).get('files') or [] if isinstance(f,dict)]
        new_files=[str(f.get('name') or '').strip() for f in
                   (data.get('attachments') or {}).get('items') or [] if isinstance(f,dict)]
        expected=(existing or {}).get('attachmentManifestCount')
        if (expected is not None and expected==len(old_files) and
                sorted(old_files)!=sorted(new_files)):
            result.update(manifestChangePending=True,
                          manifestPendingSignature=sig,
                          manifestBaselineUnverified=True)
            return result,'legacy_list_changed'
        # Old scans had no manifest digest: establish a baseline. This cannot
        # prove that an earlier binary revision has not occurred.
        result.update(manifestSignature=sig,manifestBaselineUnverified=True,
                      manifestChangePending=False)
        return result,'baseline'
    result.update(manifestSignature=sig,manifestChangePending=False)
    return result,'unchanged'


def datestr(raw):
    m=re.search(r'(20\d{2})[-./]?(\d{2})[-./]?(\d{2})',str(raw or ''))
    return m.group(1)+m.group(2)+m.group(3) if m else ''
def changcom_targets(path=CHANGCOM_SOURCE):
    """All live candidates; no hardcoded bid numbers."""
    try:
        doc=json.loads(path.read_text(encoding='utf-8'))
        if not doc.get('ok') or doc.get('bizno')!='1308185973':return set()
        return {str(x.get('bidNo'))+':'+str(x.get('order') or '0').zfill(3)
                for x in doc.get('bids',[]) if x.get('deadlineState') in ('open','unknown')}
    except (OSError,ValueError,TypeError,AttributeError):
        return set()

def pending_changcom_backfill(path=CHANGCOM_BACKFILL60):
    """Persisted 60-notice audit from the original 200-notice snapshot.

    This is only a scan priority queue; every item remains unverified until the
    official attached document is downloaded and its text successfully read.
    """
    try:
        obj=json.loads(path.read_text(encoding='utf-8'))
        items=obj.get('items') or []
        if obj.get('originalUnscannedCount')!=60 or len(items)!=60:
            raise ValueError('invalid_backfill_target_count')
        found=set()
        for entry in items:
            key=str(entry.get('bidId') or '')
            if not re.fullmatch(r'R\d{2}BK\d{8}:\d{3}',key):
                raise ValueError('invalid_backfill_bid_id')
            found.add(key)
        if len(found)!=60:raise ValueError('duplicate_backfill_bid_id')
        return found
    except (OSError,ValueError,TypeError,AttributeError) as error:
        print('CHANGCOM_BACKFILL_QUEUE_UNAVAILABLE',type(error).__name__,
              str(error)[:100],flush=True)
        return set()


def pending_urgent_recovery(path=CHANGCOM_URGENT_RECOVERY):
    """Data-driven, user-requested RFP recovery queue, never a legal preference."""
    try:
        obj=json.loads(path.read_text(encoding='utf-8'))
        if obj.get('schemaVersion')!=1:return set()
        ids=[str(item.get('bidId') or '') for item in obj.get('items') or []]
        if not ids or len(ids)!=len(set(ids)) or any(
                not re.fullmatch(r'R\d{2}BK\d{8}:\d{3}',key) for key in ids):
            raise ValueError('invalid_urgent_queue')
        return set(ids)
    except (OSError,ValueError,TypeError,AttributeError) as ex:
        print('RFP_URGENT_QUEUE_UNAVAILABLE',type(ex).__name__,flush=True)
        return set()

def iter_saved_sw_pages():
    """Use the already-mounted local SQLite, not 18 proxy HTTP pages per batch.

    The same bid_notices + license-cache rows back /saved?sw=1. The database
    is opened read-only; no government requests or snapshot mutations occur.
    """
    local_db=ROOT/'bids.sqlite3'
    if local_db.is_file():
        try:
            with sqlite3.connect('file:'+str(local_db)+'?mode=ro',
                                 uri=True,timeout=15) as db:
                db.execute('PRAGMA busy_timeout=15000')
                try:
                    query=("SELECT b.payload,q.payload FROM bid_notices b "
                           "LEFT JOIN bid_license_cache q ON b.bid_no=q.bid_no "
                           "AND q.bid_ord=printf('%03d',CAST(b.bid_ord AS INTEGER)) "
                           "WHERE b.sw_candidate=1 ORDER BY b.last_seen DESC "
                           "LIMIT ? OFFSET ?")
                    db.execute("SELECT 1 FROM bid_license_cache LIMIT 1")
                except sqlite3.OperationalError:
                    query=("SELECT b.payload,NULL FROM bid_notices b "
                           "WHERE b.sw_candidate=1 ORDER BY b.last_seen DESC "
                           "LIMIT ? OFFSET ?")
                offset=0
                while True:
                    values=db.execute(query,(500,offset)).fetchall()
                    if not values:break
                    rows=[]
                    for payload,qual in values:
                        try:item=json.loads(payload)
                        except (TypeError,ValueError):continue
                        if isinstance(item,dict):
                            if qual:
                                try:item['bidEligibility']=json.loads(qual)
                                except (TypeError,ValueError):pass
                            rows.append(item)
                    yield rows
                    offset+=len(values)
                    if len(values)<500:break
                print('RFP_SAVED_DISCOVERY_LOCAL_SQLITE',offset,flush=True)
                return
        except sqlite3.Error as error:
            print('RFP_LOCAL_SQLITE_FALLBACK',type(error).__name__,flush=True)
    for offset in range(0,100000,500):
        data=fetch_json(BASE+'saved?sw=1&limit=500&offset='+str(offset))
        if not data.get('ok'):
            raise RuntimeError('RFP_DISCOVER_SERVER_ERROR '+str(data.get('error') or 'unknown'))
        rows=data.get('items') or []
        if not rows:break
        yield rows
        if offset+len(rows)>=int(data.get('totalCount') or 0):break
    else:
        print('RFP_DISCOVER_PAGINATION_LIMIT_REACHED','offset_limit',100000)


def discover(limit,prior=None,targets=None,manifest_probe_out=None,priority=None):
    """Visit ALL indexed SW bids; retain past scan timestamps to rotate fairly.

    The file snapshot only contains recent detailed snippets, while the
    coverage index records previously scanned official documents. Neither is
    a final bidder qualification. Expired or unclassified bids are NOT
    classified as ineligible merely because they are lower scan priority.
    """
    prior=prior or {}
    targets=changcom_targets() if targets is None else targets
    backfill=pending_changcom_backfill()
    urgent=pending_urgent_recovery()
    priority=priority or set()
    # Bounded, opt-in migration of OLD successful parses ahead of new scans.
    # This is a ranking hint, never evidence that a missing document is readable.
    prefer_legacy=os.environ.get('WORKLINKS_RFP_PREFER_LEGACY_SCAN')=='1'
    upgrade_only=os.environ.get('WORKLINKS_RFP_UPGRADE_ONLY')=='1'
    reader_fingerprint=':'.join(str(n) for n in
        (CLASSIFICATION_VERSION,HWPX_READER_VERSION,
         STAFFING_ROLE_SCAN_VERSION,STAFFING_FACT_SCAN_VERSION))
    seen={}
    tz=dt.timezone(dt.timedelta(hours=9))
    today=dt.datetime.now(tz).date()
    utc=dt.datetime.now(dt.timezone.utc)
    try:
        for rows in iter_saved_sw_pages():
            for item in rows:
                no=str(item.get('bidNo') or '')
                if not re.fullmatch(r'(?:R\d{2}BK\d{8}|\d{11})',no):continue
                order=str(item.get('order') or '0').zfill(3)
                end=datestr(item.get('closes'))
                date=dt.datetime.strptime(end,'%Y%m%d').date() if end else None
                key=no+':'+order
                cached=prior.get(key) or {}
                retry=needs_hwpx_reader_retry(cached)
                # A past legal review never exempts the source from a newer parser.
                if cached.get('reviewComplete') is True and not upgrade_only:continue
                partially_retryable=partial_retry_due(cached,utc)
                if (reusable_rfp_extraction(cached) and not partially_retryable
                        and not staffing_scan_pending(cached)):
                    if (manifest_probe_out is not None and date and date>=today and
                            manifest_probe_due(cached,utc)):
                        last=str(cached.get('manifestCheckedAt') or cached.get('checkedAt') or '')
                        rank=(0 if key in targets else 1,
                              0 if not cached.get('manifestSignature') else 1,
                              last,date,key)
                        manifest_probe_out.append((rank,no,order))
                    continue
                if (key not in priority and cached.get('classificationVersion')==CLASSIFICATION_VERSION and not retry
                        and not cached.get('manifestChangePending') and
                        not staffing_scan_pending(cached)):
                    try:
                        checked=dt.datetime.fromisoformat(str(cached.get('checkedAt','')).replace('Z','+00:00'))
                        if checked.tzinfo and (utc-checked).total_seconds()<24*3600:
                            continue
                    except (ValueError,TypeError):pass
                qual=item.get('bidEligibility') or {}
                matching=any(PARTNER_VERIFIED_CODES.intersection(
                                 str(v) for v in (row.get('codes') or []))
                             for row in (qual.get('requirements') or [])
                             if isinstance(row,dict))
                # Requested 60 missing RFPs outrank generic live bids, without
                # bypassing cached-source reuse, quota limits or retry cooldown.
                # Urgent, unreviewed and official-license-matched bids first.
                # Do not confuse a lack of matching metadata with a rejection.
                temporal=0 if date and date>=today else 1 if date is None else 2
                novel=0 if not cached or cached.get('manifestChangePending') else 1
                staff_missing=staffing_scan_pending(cached)
                legacy_outdated=(cached.get('status')=='text_extracted_requires_review' and
                                 (int(cached.get('classificationVersion') or 0)<CLASSIFICATION_VERSION or
                                  int(cached.get('hwpxReaderVersion') or 0)<HWPX_READER_VERSION or
                                  staff_missing))
                if upgrade_only:
                    # One continuous queue: legacy upgrades first, then the
                    # first-time open SW bids. Do not abandon thousands of
                    # unscanned bids just because the version queue drained.
                    # Unknown electronic close is not evidence the bid expired.
                    if temporal==2:continue
                    is_first_scan=not cached or cached.get('status') in ('not_scanned','unscanned')
                    retry_failed=bool(cached) and cached.get('status') not in (
                        'text_extracted_requires_review','not_scanned','unscanned')
                    if not (legacy_outdated or is_first_scan or retry_failed):continue
                    # Do not retry a known broken source on every batch.
                    last_attempt=str(cached.get('lastAttemptAt') or '')
                    if (last_attempt and
                            cached.get('lastAttemptReaderFingerprint')==reader_fingerprint and
                            not cached.get('manifestChangePending')):
                        try:
                            when=dt.datetime.fromisoformat(last_attempt.replace('Z','+00:00'))
                            if when.tzinfo and utc-when<dt.timedelta(hours=24):continue
                        except (ValueError,TypeError):pass
                    lane=(3 if temporal==1 else 0 if legacy_outdated else 1 if is_first_scan else 2)
                    seen[key]=((lane,0 if key in targets else 1,
                                str(cached.get('lastAttemptAt') or cached.get('checkedAt') or ''),
                                key),no,order,date.isoformat() if date else '')
                    continue
                rank=(-3 if key in priority and temporal==0 else
                      -2 if prefer_legacy and legacy_outdated and key in targets and temporal==0 else
                      -2 if key in urgent and key in targets and temporal==0 else
                      -1 if staff_missing and key in targets and temporal==0 else
                      -1 if key in backfill and temporal==0 else
                      -1 if partially_retryable and key in targets and temporal==0 else
                      0 if key in targets and temporal==0 else 1 if temporal==0 else
                      2 if key in targets else 3,
                      novel,0 if retry else 1,
                      0 if matching else 1,
                      date if date is not None and date>=today else today+dt.timedelta(days=3650),
                      0 if item.get('kind')=='servc' else 1,key)
                seen[key]=(rank,no,order,date.isoformat() if date else '')
    except Exception as error:
        print('SAVED_NOTICE_DISCOVERY_UNAVAILABLE',type(error).__name__,str(error)[:140])
    # Old parser versions still get retried after all currently open/unread
    # notices; they never displace an urgent live bidder's first source scan.
    for key,cached in prior.items():
        if upgrade_only:break
        if not isinstance(cached,dict):continue
        if cached.get('classificationVersion')==CLASSIFICATION_VERSION and not needs_hwpx_reader_retry(cached):
            continue
        m=re.fullmatch(r'(R\d{2}BK\d{8}|\d{11}):(\d{3})',key)
        if not m or key in seen:continue
        no,order=m.groups()
        rank=(4,1,0 if needs_hwpx_reader_retry(cached) else 1,1,
              today+dt.timedelta(days=3650),1,key)
        seen[key]=(rank,no,order,'')
    sorted_rows=sorted(seen.values(),key=lambda row:row[0])
    if upgrade_only and limit>=3:
        # Fairness for non-electronic tenders; no expired confirmed bid enters.
        no_close=[row for row in sorted_rows if row[0][0]==3]
        known=[row for row in sorted_rows if row[0][0]!=3]
        selected=known[:limit-1]+no_close[:1] if no_close and len(known)>=limit else sorted_rows[:limit]
        return [(no,order,date) for _,no,order,date in selected]
    return [(no,order,date) for _,no,order,date in sorted_rows[:limit]]

def legal_file(item):
    url=str(item.get('url') or '')
    u=urllib.parse.urlsplit(url)
    if u.scheme!='https' or u.hostname!='www.g2b.go.kr' or u.port not in (None,443):
        return None
    if not u.path.startswith('/pn/pnp/pnpe/UntyAtchFile/'):
        return None
    name=str(item.get('name') or '')[:160]
    lower=name.lower()
    return name,url
class OfficialAttachmentReferenceMissing(ValueError):
    """An official download URL is listed but the server denies its file ID."""


def official_missing_reference(error):
    """True only for a verified 422 JSON response from G2B."""
    if not isinstance(error, urllib.error.HTTPError) or error.code != 422:
        return False
    try:
        body=error.read(2048)
        data=json.loads(body.decode('utf-8','replace'))
        return (isinstance(data,dict) and data.get('ErrorCode')==-1
                and data.get('ErrorMsg')=='파일이 존재하지 않습니다.')
    except (OSError,ValueError,UnicodeError):
        return False


def _ocr_pdf_page(raw,index):
    """Render one image-only page and OCR with installed local Korean Tesseract."""
    if not shutil.which('tesseract'):
        raise ValueError('pdf_ocr_engine_unavailable')
    try:
        import pymupdf
    except ImportError as exc:
        raise ValueError('pdf_ocr_renderer_unavailable') from exc
    with pymupdf.open(stream=raw,filetype='pdf') as document:
        page=document.load_page(index)
        zoom=min(PDF_OCR_TARGET_DPI/72.0,
                 (MAX_PDF_OCR_PIXELS/max(1.0,page.rect.width*page.rect.height))**.5)
        pix=page.get_pixmap(matrix=pymupdf.Matrix(zoom,zoom),alpha=False)
        if pix.width*pix.height>MAX_PDF_OCR_PIXELS:
            raise ValueError('pdf_ocr_page_too_large')
        png=pix.tobytes('png')
    result=subprocess.run(
        ['tesseract','stdin','stdout','-l','kor+eng','--psm','3',
         '--dpi',str(max(72,int(72*zoom)))],
        input=png,capture_output=True,timeout=22,check=False)
    if result.returncode:
        raise ValueError('pdf_ocr_engine_failed')
    return result.stdout.decode('utf-8','replace')


def _extract_image_with_audit(raw):
    """OCR a bounded, real raster image; fail closed on unreadable text."""
    from PIL import Image,ImageOps,ImageFile
    Image.MAX_IMAGE_PIXELS=12_000_000
    ImageFile.LOAD_TRUNCATED_IMAGES=False
    with Image.open(io.BytesIO(raw)) as source:
        if source.width*source.height>12_000_000:
            raise ValueError('image_ocr_page_too_large')
        image=ImageOps.exif_transpose(source)
        image=image.convert('RGB')
        if min(image.size)<1150:
            scale=min(2.5,1150/max(1,min(image.size)),
                (12_000_000/max(1,image.width*image.height))**.5)
            if scale>1.0:
                image=image.resize((int(image.width*scale),int(image.height*scale)))
        out=io.BytesIO()
        image.save(out,format='PNG')
    run=subprocess.run(['tesseract','stdin','stdout','-l','kor+eng',
                        '--psm','3','--dpi','300'],input=out.getvalue(),
                        capture_output=True,timeout=28,check=False)
    if run.returncode:
        raise ValueError('image_ocr_engine_failed')
    text=run.stdout.decode('utf-8','replace')
    if sum(c.isalnum() for c in text)<12:
        raise ValueError('image_ocr_incomplete')
    return text


def _extract_pdf_with_audit(raw):
    """Keep readable native pages; OCR only pages lacking native text."""
    from pypdf import PdfReader
    document=PdfReader(io.BytesIO(raw))
    if len(document.pages)>450:raise ValueError('pdf_over_page_limit')
    parts=[];missing=[];attempted=[];recovered=[];untouched_blanks=[]
    for i,page in enumerate(document.pages):
        try:
            natural=page.extract_text() or ''
        except Exception:
            natural=''
        if natural.strip():
            parts.append(natural)
            continue
        has_content=page.get_contents() is not None
        try:
            has_images=bool(page.images)
        except Exception:
            has_images=True
        if not has_content and not has_images:
            untouched_blanks.append(i+1)
            continue
        if len(attempted)>=MAX_PDF_OCR_PAGES:
            missing.append(i+1)
            continue
        # Bulk index/eligibility scan must never block its 8-notice batch on
        # multi-page Tesseract. Preserve the unresolved pages for the isolated
        # cached attachment OCR-repair job, which runs with this flag OFF.
        if os.environ.get('WORKLINKS_RFP_DEFER_OCR')=='1':
            missing.append(i+1)
            continue
        attempted.append(i+1)
        try:
            value=_ocr_pdf_page(raw,i)
        except (ValueError,subprocess.TimeoutExpired):
            missing.append(i+1)
            continue
        # A short recognition artifact must not clear legal evidence.
        if sum(c.isalnum() for c in value)<12:
            missing.append(i+1)
            continue
        parts.append(value)
        recovered.append(i+1)
    text='\n'.join(parts)
    info={'pdfPages':len(document.pages),'ocrAttemptedPages':len(attempted),
          'ocrRecoveredPages':len(recovered),'unresolvedPages':missing[:30],
          'genuinelyBlankPages':len(untouched_blanks),
          'sourceComplete':not missing,
          'extractionMethod':'pdf_native_ocr' if attempted else 'pdf_native'}
    if not text.strip():
        raise ValueError('pdf_ocr_incomplete' if missing else 'no_searchable_text')
    return text,info


def extract_with_source_status(name,raw):
    """Record mixed PDF/OCR provenance including PDFs nested in a ZIP."""
    previous=getattr(_DOCUMENT_SCAN,'pdf',None)
    _DOCUMENT_SCAN.pdf=[]
    try:
        data=extract(name,raw)
        pdf_stats=list(_DOCUMENT_SCAN.pdf)
        complete=all(x.get('sourceComplete') is True for x in pdf_stats)
        return data,{'sourceComplete':complete,'pdfFiles':len(pdf_stats),
                     'pdfPages':sum(x['pdfPages'] for x in pdf_stats),
                     'ocrAttemptedPages':sum(x['ocrAttemptedPages'] for x in pdf_stats),
                     'ocrRecoveredPages':sum(x['ocrRecoveredPages'] for x in pdf_stats),
                     'unresolvedPages':sum(len(x['unresolvedPages']) for x in pdf_stats),
                     'extractionMethod':'pdf_native_ocr' if
                        any(x['ocrAttemptedPages'] for x in pdf_stats)
                        else 'native'}
    finally:
        if previous is None:
            try:del _DOCUMENT_SCAN.pdf
            except AttributeError:pass
        else:_DOCUMENT_SCAN.pdf=previous


def classify_failure(error):
    if isinstance(error,OfficialAttachmentReferenceMissing):
        return 'official_attachment_reference_missing_422'
    if isinstance(error,urllib.error.HTTPError):
        return 'file_download_http_'+str(error.code)
    if isinstance(error,(TimeoutError,ConnectionError,urllib.error.URLError)):
        return 'file_download_connection_error'
    detail=str(error)
    known=('large_file','invalid_hwp','hwp5txt_failed','archive_many_xml_files',
           'pdf_over_100_pages','pdf_over_page_limit','pdf_unreadable_page','no_searchable_text','unsupported_format',
           'redirect_forbidden','oversize_json','egg_archive_requires_converter',
           'nested_archive_requires_review','unknown_archive_member_requires_review',
           'archive_no_searchable_documents','unsafe_archive_path','large_xml_section',
            'image_ocr_incomplete','image_ocr_page_too_large','image_ocr_engine_failed',
            'pdf_ocr_incomplete','pdf_ocr_engine_unavailable','pdf_ocr_renderer_unavailable')
    return next((v for v in known if v in detail),'file_extract_failure')


def invalid_file_reason(item):
    url=str(item.get('url') or '')
    if not url:return 'download_url_missing'
    u=urllib.parse.urlsplit(url)
    if u.scheme!='https' or u.hostname!='www.g2b.go.kr' or u.port not in (None,443):
        return 'not_approved_official_host'
    if not u.path.startswith('/pn/pnp/pnpe/UntyAtchFile/'):
        return 'unsupported_download_path'
    name=str(item.get('name') or '')
    return 'unrecognized_file_error'



class DownloadPrefetch:
    """Separate bounded attachment downloader for four independent scan threads.

    At most eight file GETs run at once. A limited two-file lookahead per
    notice bounds memory while download and text extraction overlap. The
    official-source ledger retains verified compressed bytes after parsing.
    """

    def __init__(self,max_workers=8):
        self.workers=max(1,min(8,int(max_workers)))
        self.executor=ThreadPoolExecutor(max_workers=self.workers,
                                         thread_name_prefix='rfp-download')
        self.lock=threading.Lock()
        self.pace_lock=threading.Lock()
        self.next_start=0.0
        self.inflight={}
        self.submitted=0
        self.coalesced=0
        self.network_attempts=0

    def __enter__(self):return self

    def __exit__(self,*exc):
        self.executor.shutdown(wait=True)

    def acquire(self):
        """Limit starts to <=4 official file requests/s even with eight threads."""
        with self.pace_lock:
            now=time.monotonic()
            start=max(now,self.next_start)
            self.next_start=start+0.25
            self.network_attempts+=1
        delay=start-now
        if delay>0:time.sleep(delay)

    def submit(self,notice_key,closes_on,url):
        with self.lock:
            ongoing=self.inflight.get(url)
            if ongoing is not None and not ongoing.done():
                self.coalesced+=1
                return ongoing
            future=self.executor.submit(
                _download_for_notice,notice_key,closes_on,url,self)
            self.inflight[url]=future
            self.submitted+=1
            return future

    def release(self,url,future):
        with self.lock:
            if self.inflight.get(url) is future and future.done():
                del self.inflight[url]

    def stats(self):
        with self.lock:
            return {'workers':self.workers,'submitted':self.submitted,
                    'coalesced':self.coalesced,
                    'networkAttempts':self.network_attempts}


def _download_for_notice(notice_key,closes_on,url,prefetch):
    _NOTICE_CONTEXT.notice_key=notice_key
    _NOTICE_CONTEXT.closes_on=closes_on
    started=time.perf_counter()
    try:
        raw=download(url,rate_gate=prefetch)
        return raw,time.perf_counter()-started
    finally:
        _NOTICE_CONTEXT.notice_key=None
        _NOTICE_CONTEXT.closes_on=''


def _eligible_prefetch_positions(manifest,processing_order,reusable):
    """Never prefetch a possible same-stem HWP before checking its PDF.

    A failed PDF's HWP is downloaded on demand through the SAME pool.
    Already-successful staffing parses and deferred OCR are never fetched.
    """
    pdf_stems={
        _document_stem(str(item.get('name') or ''))
        for item in manifest
        if isinstance(item,dict) and
           str(item.get('name') or '').lower().endswith('.pdf') and
           legal_file(item) is not None
    }
    result=[]
    for position in processing_order:
        item=manifest[position]
        public=legal_file(item)
        if not public:continue
        name,url=public
        if (name.lower().endswith(('.hwp','.hwpx')) and
                _document_stem(name) in pdf_stems):
            continue
        retained=reusable.get((name,url))
        if (retained and
                int(retained.get('staffingRoleScanVersion') or 0)>=STAFFING_ROLE_SCAN_VERSION and
                int(retained.get('staffingFactScanVersion') or 0)>=STAFFING_FACT_SCAN_VERSION and
                retained.get('staffingRoleScanTruncated') is not True):
            continue
        if (os.environ.get('WORKLINKS_RFP_DEFER_OCR')=='1' and
                name.lower().endswith(('.png','.jpg','.jpeg','.bmp','.tif','.tiff','.webp'))):
            continue
        result.append(position)
    return result


def download(url,*,rate_gate=None,progress=None):
    # Persist small official binaries even if text extraction later fails.
    # A parser-only retry can then reuse the exact bytes without an HTTP call.
    ledger=active_rfp_ledger()
    reqkey=cache_key('official_attachment',url)
    notice_key=getattr(_NOTICE_CONTEXT,'notice_key',None)
    if ledger and not os.environ.get('WORKLINKS_RFP_FORCE_REDOWNLOAD'):
        reusable=ledger.get_bytes(reqkey)
        if reusable is not None:
            if progress:progress(len(reusable),len(reusable),True)
            ledger.link_attachment(reqkey,notice_key,getattr(_NOTICE_CONTEXT,'closes_on',''))
            ledger.record('attachment_reuse',reqkey,'verified_bytes_reused',
                          notice_key=notice_key,
                          response_sha256=hashlib.sha256(reusable).hexdigest())
            return reusable
    if os.environ.get('WORKLINKS_RFP_DUAL_SCAN_ONLY')=='1':
        # The scan lane never makes a network request. Missing archives go
        # back to the independent download lane for verification/recovery.
        from rfp_dual_queue import RfpDualQueue
        key=getattr(_NOTICE_CONTEXT,'notice_key',None)
        if key:
            RfpDualQueue(os.environ['WORKLINKS_RFP_DUAL_QUEUE_DB']).mark_download_missing(key)
        raise RuntimeError('queued_original_missing')
    request=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Referer':'https://www.g2b.go.kr/'})
    for attempt in range(3):
        if rate_gate is not None:rate_gate.acquire()
        try:
            with OPENER.open(request,timeout=35) as r:
                status=getattr(r,'status',200)
                size=int(r.headers.get('Content-Length') or '0')
                if size>MAX_FILE:raise ValueError('large_file')
                chunks=[]
                received=0
                last_report=0.0
                if progress:progress(0,size,False)
                while True:
                    block=r.read(min(256*1024,MAX_FILE+1-received))
                    if not block:break
                    chunks.append(block)
                    received+=len(block)
                    if received>MAX_FILE:raise ValueError('large_file')
                    now_tick=time.monotonic()
                    if progress and (now_tick-last_report>=0.4 or (size and received>=size)):
                        progress(received,size,False)
                        last_report=now_tick
                raw=b''.join(chunks)
                if progress:progress(received,size or received,True)
            if ledger:
                ledger.record('attachment_http',reqkey,'http_ok',http_status=status,
                              notice_key=notice_key,
                              response_sha256=hashlib.sha256(raw).hexdigest(),
                              detail='bytes='+str(len(raw)))
                ledger.save_bytes(reqkey,raw,notice_key=notice_key,
                                  closes_on=getattr(_NOTICE_CONTEXT,'closes_on',''))
            return raw
        except (urllib.error.HTTPError,TimeoutError,ConnectionError,
                urllib.error.URLError,ValueError) as ex:
            if ledger:
                ledger.record('attachment_http',reqkey,'http_failed',
                              notice_key=notice_key,
                              http_status=getattr(ex,'code',None),
                              error_class=type(ex).__name__)
            if isinstance(ex,urllib.error.HTTPError):
                if official_missing_reference(ex):
                    raise OfficialAttachmentReferenceMissing(
                        'official_attachment_reference_missing_422') from ex
                retry=ex.code in (429,500,502,503,504)
            else:
                retry=isinstance(ex,(TimeoutError,ConnectionError,urllib.error.URLError))
            if not retry or attempt==2:raise
        time.sleep(1.5*(attempt+1))
def _document_stem(name):
    # Only a matching filename stem inside the SAME official attachment
    # manifest can stand in for a failed HWP; never fuzzy-match similar titles.
    return re.sub(r'[\W_]+','',Path(str(name or '')).stem.lower())


def verified_pdf_companion(hwp,files):
    """Return fully scanned same-stem PDF, otherwise None."""
    name=str(hwp.get('name') or '')
    if not name.lower().endswith(('.hwp','.hwpx')):return None
    stem=_document_stem(name)
    if not stem:return None
    for candidate in files:
        if candidate is hwp or not isinstance(candidate,dict):continue
        label=str(candidate.get('name') or '')
        if (label.lower().endswith('.pdf') and
            _document_stem(label)==stem and
            candidate.get('readable') is True and
            candidate.get('sourceTextScanComplete') is True and
            candidate.get('qualificationScanTruncated') is not True and
            candidate.get('sourceSha256')):
            return candidate
    return None


def hwp_covered_by_verified_pdf(hwp,files):
    """PDF-first selection, not a claim the HWP binary was read."""
    return verified_pdf_companion(hwp,files) is not None


def annotate_official_pdf_siblings(files):
    """Use a successfully scanned same-title PDF as alternate official evidence.

    Never claim the HWP itself was read or that two formats are byte-identical.
    The PDF's own clause citations remain the authoritative extracted source.
    """
    updated=0
    for f in files:
        if not isinstance(f,dict):continue
        if f.get('readable') is True and f.get('sourceTextScanComplete') is True:
            continue
        other=verified_pdf_companion(f,files)
        if not other:continue
        if f.get('alternatePdfEvidence')!=other.get('name'):
            updated+=1
        f['alternatePdfEvidence']=other['name']
        f['alternatePdfSourceSha256']=other['sourceSha256']
        f['alternatePdfEvidenceMode']='same_basename_not_proven_identical'
        f['skippedDuplicateFormat']=True
        # Do not retain a misleading failed HWP status when its same-title
        # PDF is selected. The raw HWP remains explicitly *unread*.
        f.pop('errorCategory',None)
        f.pop('error',None)
    return updated


def extract(name,raw):
    # G2B sometimes supplies an OLE HWP named .hwpx or a ZIP of several
    # PDFs named .pdf. Choose the reader from bytes, NOT the filename.
    n=name.lower()
    if raw.startswith(b'%PDF-'):
        n='.pdf'
    elif raw.startswith(bytes.fromhex('D0CF11E0A1B11AE1')):
        n='.hwp'
    elif raw.startswith(b'PK\x03\x04'):
        # Identify Office XML formats by internal paths. Otherwise this is
        # an ordinary attachment archive, regardless of its .pdf/.hwp name.
        with zipfile.ZipFile(io.BytesIO(raw)) as probe:
            members=set(probe.namelist())
        if 'word/document.xml' in members:
            n='.docx'
        elif 'xl/workbook.xml' in members or any(
                m.startswith('xl/worksheets/') and m.endswith('.xml')
                for m in members):
            n='.xlsx'
        elif 'ppt/presentation.xml' in members or any(
                m.startswith('ppt/slides/') and m.endswith('.xml')
                for m in members):
            n='.pptx'
        elif any(p.startswith('Contents/') and p.endswith('.xml') for p in members):
            n='.hwpx'
        else:
            n='.zip'
    elif not n.endswith(TEXT_FORMATS):
        raise ValueError('unsupported_format')
    # Verify actual magic and dimensions with Pillow before processing images.
    if n.endswith(('.png','.jpg','.jpeg','.bmp','.tif','.tiff','.webp')):
        return _extract_image_with_audit(raw)
    if n.endswith('.egg'):
        raise ValueError('egg_archive_requires_converter')
    if n.endswith('.zip'):
        parts=[]
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members=archive.infolist()
            if len(members)>250 or sum(m.file_size for m in members)>45_000_000:
                raise ValueError('archive_many_xml_files')
            for entry in members:
                if entry.is_dir():continue
                inner=entry.filename
                if inner.startswith('/') or '..' in Path(inner).parts:
                    raise ValueError('unsafe_archive_path')
                suffix=Path(inner).suffix.lower()
                if suffix in {'.pdf','.hwp','.hwpx','.docx','.xlsx','.pptx',
                              '.png','.jpg','.jpeg','.bmp','.webp','.tif','.tiff'}:
                    if entry.file_size>MAX_FILE:raise ValueError('large_file')
                    value=extract(Path(inner).name,archive.read(entry))
                    if not value.strip():raise ValueError('no_searchable_text')
                    parts.append('FILE '+inner+'\n'+value)
                elif suffix=='.zip':
                    # One additional nested ZIP level only; each archive
                    # still has strict member, expanded-size and path limits.
                    depth=getattr(_DOCUMENT_SCAN,'zip_depth',0)
                    if depth>=1:raise ValueError('nested_archive_requires_review')
                    if entry.file_size>MAX_FILE:raise ValueError('large_file')
                    _DOCUMENT_SCAN.zip_depth=depth+1
                    try:
                        value=extract(Path(inner).name,archive.read(entry))
                    finally:_DOCUMENT_SCAN.zip_depth=depth
                    if not value.strip():raise ValueError('no_searchable_text')
                    parts.append('FILE '+inner+'\n'+value)
                elif suffix in {'.egg','.7z','.rar'}:
                    raise ValueError('nested_archive_requires_review')
                elif suffix in {'.txt','.csv'}:
                    if entry.file_size>MAX_FILE:raise ValueError('large_file')
                    data=archive.read(entry)
                    parts.append('FILE '+inner+'\n'+data.decode('utf-8','replace'))
                elif suffix not in {'.png','.jpg','.jpeg','.gif','.bmp','.webp','.xml',
                                     '.rels','.DS_Store','.md'}:
                    raise ValueError('unknown_archive_member_requires_review')
        if not parts:raise ValueError('archive_no_searchable_documents')
        return '\n'.join(parts)
    if n.endswith(('.docx','.xlsx','.pptx')):
        # OOXML text is accessible without external dependencies. Only bounded
        # declared members are read, so decompression bombs cannot exhaust CI.
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names=archive.namelist()
            if len(names)>1000:raise ValueError('archive_many_xml_files')
            total=sum(archive.getinfo(m).file_size for m in names)
            if total>45_000_000:raise ValueError('large_xml_section')
            pieces=[]
            shared=[]
            if n.endswith('.xlsx') and 'xl/sharedStrings.xml' in names:
                info=archive.getinfo('xl/sharedStrings.xml')
                if info.file_size>10_000_000:raise ValueError('large_xml_section')
                tree=ET.fromstring(archive.read('xl/sharedStrings.xml'))
                for si in tree.iter():
                    if si.tag.rsplit('}',1)[-1]=='si':
                        shared.append(''.join((z.text or '') for z in si.iter()
                                              if z.tag.rsplit('}',1)[-1]=='t'))
            if n.endswith('.docx'):
                chosen=[m for m in names if m=='word/document.xml' or
                        re.fullmatch(r'word/(?:header|footer)\d+\.xml',m)]
            elif n.endswith('.xlsx'):
                chosen=[m for m in names if re.fullmatch(r'xl/worksheets/sheet\d+\.xml',m)]
            else:
                chosen=[m for m in names if re.fullmatch(r'ppt/slides/slide\d+\.xml',m)]
            if len(chosen)>150:raise ValueError('archive_many_xml_files')
            for member in chosen:
                info=archive.getinfo(member)
                if info.file_size>6_000_000:raise ValueError('large_xml_section')
                tree=ET.fromstring(archive.read(member))
                if n.endswith('.xlsx'):
                    for row in tree.iter():
                        if row.tag.rsplit('}',1)[-1]!='row':continue
                        cells=[]
                        for cell in row:
                            if cell.tag.rsplit('}',1)[-1]!='c':continue
                            v=next((z.text or '' for z in cell.iter()
                                    if z.tag.rsplit('}',1)[-1]=='v'),'')
                            if cell.get('t')=='s' and v.isdigit() and int(v)<len(shared):
                                v=shared[int(v)]
                            elif cell.get('t')=='inlineStr':
                                v=''.join(z.text or '' for z in cell.iter()
                                          if z.tag.rsplit('}',1)[-1]=='t')
                            if v.strip():cells.append(v.strip())
                        if cells:pieces.append(' '.join(cells))
                else:
                    for paragraph in tree.iter():
                        if paragraph.tag.rsplit('}',1)[-1]!='p':continue
                        value=''.join(z.text or '' for z in paragraph.iter()
                                      if z.tag.rsplit('}',1)[-1]=='t')
                        if value.strip():pieces.append(value.strip())
            return '\n'.join(pieces)
    if n.endswith('.hwp'):
        if not raw.startswith(bytes.fromhex('D0CF11E0A1B11AE1')):raise ValueError('invalid_hwp')
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'source.hwp'
            p.write_bytes(raw)
            r=subprocess.run(['hwp5txt',str(p)],capture_output=True,timeout=38)
            if r.returncode:raise ValueError('hwp5txt_failed')
            return r.stdout.decode('utf-8','replace')
    if n.endswith('.hwpx'):
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            data=[]
            members=[x for x in archive.namelist() if x.startswith('Contents/') and x.endswith('.xml')]
            # No silent XML member or paragraph truncation: it would hide
            # eligibility clauses in a document reported as readable.
            if len(members)>80:raise ValueError('archive_many_xml_files')
            sizes=[archive.getinfo(member).file_size for member in members]
            if any(n>MAX_HWPX_XML_MEMBER for n in sizes) or sum(sizes)>MAX_HWPX_XML_TOTAL:
                raise ValueError('large_xml_section')
            for member in members:
                tree=ET.fromstring(archive.read(member))
                # HWPX uses hp:p paragraphs containing hp:t spans. Joining all
                # text spans into one line hid qualification clauses completely.
                paragraphs=[]
                for p in tree.iter():
                    if p.tag.rsplit('}',1)[-1]!='p':continue
                    segments=[t.text or '' for t in p.iter() if t.tag.rsplit('}',1)[-1]=='t']
                    value=''.join(segments).strip()
                    if value:paragraphs.append(value)
                if not paragraphs:
                    paragraphs=[''.join(x.text or '' for x in tree.iter()
                                if x.tag.rsplit('}',1)[-1]=='t')]
                data.extend(paragraphs)
            return '\n'.join(data)
    if n.endswith('.pdf'):
        text,details=_extract_pdf_with_audit(raw)
        attached=getattr(_DOCUMENT_SCAN,'pdf',None)
        if attached is not None:attached.append(details)
        return text
    raise ValueError('unsupported_format')
def parse_clauses(text):
    text=re.sub(r'[\u200b\ufeff\x00]','',text)
    text=text[:350_000]
    triggers={name:len(re.findall(rx,text,re.I)) for name,rx in SIGNALS.items()}
    snippets=[]
    lines=re.split(r'\n+',text)
    seen=set()
    for raw in lines:
        line=' '.join(raw.split())
        if not 14<=len(line)<=1800:continue
        match=next((k for k,rx in SIGNALS.items() if re.search(rx,line,re.I)),None)
        if not match:continue
        clean=line[:190]
        if clean in seen:continue
        seen.add(clean)
        snippets.append({'topic':match,'text':clean})
        if len(snippets)>=16:break
    return triggers,snippets

# A separate, source-grounded staffing scan. Qualification snippets alone miss
# tables such as "직무 / 등급 / 인원" and wrapped DOCX/PDF/HWPX rows.
STAFFING_ROLE_SCAN_VERSION=4
# Independent of staffing role extraction: do not trigger fresh government API
# calls merely because the presentation of source-backed conditions improved.
STAFFING_FACT_SCAN_VERSION=2
STAFFING_ROLE_TEXT_LIMIT=350_000
try:
    from staffing_facts import extract_staffing_facts
except ModuleNotFoundError as exc:
    if exc.name!='staffing_facts':raise
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parent))
    from staffing_facts import extract_staffing_facts
_STAFF_ROLE=re.compile(
    r'(?<![가-힣A-Za-z0-9])(?:사업\s*책임자|총괄\s*책임자|프로젝트\s*관리자|'
    r'프로젝트\s*리더|PM\b|PL\b|DBA\b|QA\b|'
    r'프론트\s*엔드\s*개발자|백\s*엔드\s*개발자|웹\s*개발자|'
    r'소프트웨어\s*개발자|시스템\s*개발자|개발자|'
    r'시스템\s*운영자|운영\s*인력|운영자|유지\s*보수\s*인력|'
    r'시스템\s*엔지니어|기술\s*지원\s*인력|기술자|'
    r'정보\s*보안\s*담당자|보안\s*담당자|데이터\s*분석가|'
    r'AI\s*전문가|인공\s*지능\s*전문가|포털\s*개발|'
    r'인프라|개발|품질\s*관리자|테스터|디자이너|퍼블리셔)'
    r'(?![가-힣A-Za-z0-9])', re.I)
_STAFF_HEADER=re.compile(
    r'(?:인원|인력|투입\s*인원|인원\s*수|인원\s*계획)'
    r'.{0,45}(?:직무|역할|직종|등급|구분|분야)|'
    r'(?:직무|역할|직종|등급|구분|분야).{0,45}'
    r'(?:인원|인력|투입\s*인원|인원\s*수)', re.I)
_STAFF_COUNT=re.compile(r'(?<!\d)([1-9]\d?)\s*(?:명|인)(?![가-힣A-Za-z])')
_STAFF_TABLE_COUNT=re.compile(
    r'(?<!\d)([1-9]\d?)(?!\d|\s*(?:MM|M/M|년|개월|일|건|회|원|%|호))', re.I)
_STAFF_GRADE=re.compile(r'(?<![가-힣])(?:특급|고급|중급|초급)(?![가-힣])')
_STAFF_MM=re.compile(r'(?<!\d)(\d{1,3}(?:\.\d{1,2})?)\s*(?:MM|M/M|맨먼스)\b', re.I)

def staffing_role_is_grounded(row):
    """Reject score, annex and years-of-experience numbers disguised as people."""
    quote=' '.join(str(row.get('sourceText') or '').split())
    if staffing_source_is_general_example(row.get('sourceFile'), quote):return False
    role=' '.join(str(row.get('role') or '').split())
    count=int(row.get('count') or 0)
    if not role or not quote or not 1<=count<=99:return False
    if (re.search(r'평가\s*항목|평가\s*기준|배\s*점|점수|점\s*이상|산술한\s*수치',quote)
            and ('|' in quote or role=='기술자')):
        return False
    match=re.search(re.escape(role)+r'(.{0,52}?)'+str(count)+
        r'\s*(?:명|인)(?=\s|$|[.,()·:;]|이상|이하|투입|상주)',quote,re.I)
    if match:
        middle=match.group(1)
        if re.search(r'전담\s*유지\s*보수|별도의?\s*담당자|기타\s*인력|부문별\s*대표자',middle):
            return False
        return len(middle)<=32 or bool(re.search(r'최소|이상|투입|필요|배치',middle))
    if re.fullmatch(re.escape(role)+r'\s+(?:특급|고급|중급|초급)\s+'+str(count),quote):
        return True
    if (len(quote)>110 or quote.count('|')<2 or
            re.search(r'경력|별지|서식|항목|번호|평가|점|년',quote)):
        return False
    cells=[cell.strip() for cell in quote.split('|')]
    return (len(cells)==3 and role in cells[0] and
            re.search(r'특급|고급|중급|초급',cells[1]) is not None and
            re.fullmatch(r'[1-9]\d?',cells[2]) is not None and
            int(cells[2])==count)

def extract_staffing_roles(text, filename, source_url='', excerpt_only=False):
    """Extract explicit role/count pairs, including line-wrapped staffing tables.

    No automatic summing of different roles, grades, documents, or alternative
    staffing plans. An unsupported number is never assumed to be a headcount.
    """
    if staffing_source_is_general_example(filename) or staffing_general_annex_file(filename):return []
    text=str(text or '')[:STAFFING_ROLE_TEXT_LIMIT]
    lines=[' '.join(part.split())[:550] for part in text.splitlines()]
    result=[]
    seen=set()
    header_at=-1000
    def parse(fragment, lineno, table=False):
        matches=list(_STAFF_ROLE.finditer(fragment))
        if not matches:return
        for n,match in enumerate(matches):
            end=matches[n+1].start() if n+1<len(matches) else len(fragment)
            span=fragment[match.start():end][:130]
            tail=fragment[match.end():end][:100]
            counted=_STAFF_COUNT.search(tail)
            if not counted and table and len(span)<110:
                counted=_STAFF_TABLE_COUNT.search(tail)
            if not counted:continue
            count=int(counted.group(1))
            if count<1 or count>99:continue
            role=' '.join(match.group(0).split())
            grade=(_STAFF_GRADE.search(span) or _STAFF_GRADE.search(fragment[max(0,match.start()-12):match.start()]))
            grade=grade.group(0) if grade else ''
            onsite=('비상주' if re.search(r'비\s*상주',span) else
                    '상주' if re.search(r'(?<!비)\s*상주',span) else '')
            mm=_STAFF_MM.search(span)
            kind='minimum' if re.search(r'(?:최소|이상|적어도)\s*$|'
                                        r'(?<!미)\s*이상|(?:최소|이상).{0,10}'+re.escape(counted.group(0)),span) else 'specified'
            key=(role.lower(),grade,count,onsite,kind)
            if key in seen:continue
            seen.add(key)
            result.append({'role':role,'grade':grade,'count':count,
                           'countKind':kind,'onsite':onsite,
                           'manMonths':float(mm.group(1)) if mm else None,
                           'sourceFile':str(filename or '')[:140],
                           'sourceUrl':source_url if str(source_url).startswith('https://www.g2b.go.kr/') else '',
                           'sourceLine':lineno,'sourceText':fragment[:240],
                           'scope':'excerpt' if excerpt_only else 'document'})
            if len(result)>=20:return
    for idx,line in enumerate(lines):
        if idx>=STAFFING_ROLE_TEXT_LIMIT//2 or len(result)>=20:break
        if _STAFF_HEADER.search(line):header_at=idx
        if not _STAFF_ROLE.search(line):continue
        table=idx-header_at<=18
        before=len(result)
        parse(line,idx+1,table)
        if len(result)>before or not table:continue
        # DOCX/HWPX table cells and PDF extraction can emit role, grade, count
        # as separate short lines. Never span across another role or heading.
        parts=[line]
        for extra in lines[idx+1:idx+4]:
            if len(extra)>38 or _STAFF_ROLE.search(extra) or _STAFF_HEADER.search(extra):
                break
            parts.append(extra)
            combined=' | '.join(parts)
            previous=len(result)
            parse(combined,idx+1,True)
            if len(result)>previous:break
    return [row for row in result if staffing_role_is_grounded(row)]

def staffing_from_saved_excerpts(file):
    """Best-effort recovery from stored 270-char quotes; NOT a full text scan."""
    if not isinstance(file,dict):return []
    clauses=file.get('clauseCandidates') or []
    output=[]
    seen=set()
    for clause in clauses:
        if not isinstance(clause,dict):continue
        text=str(clause.get('sourceText') or '')
        if not _STAFF_ROLE.search(text):continue
        for item in extract_staffing_roles(text,file.get('name') or
                                          clause.get('sourceFile') or '',
                                          file.get('sourceUrl') or '',True):
            key=(item['role'].lower(),item['grade'],item['count'],item['onsite'])
            if key not in seen and len(output)<20:
                seen.add(key);output.append(item)
    return output

def extract_rule_candidates(text,filename):
    """Capture cited clauses without silently truncating long HWPX paragraphs.

    Candidates are evidence, not an authoritative exhaustive list. Adjacent PDF
    wrapped lines are included to retain their registration/certificate verbs.
    """
    raw_lines=[' '.join(line.split()) for line in re.split(r'\n+',text[:350_000])]
    rules={
      'industry_code':r'업종\s*코드|업종코드|업종으로\s*입찰|소프트웨어사업자|학술.?연구용역|정보통신공사업',
      'direct_production':r'직접\s*생산|세부\s*품명\s*번호|공간정보\s*DB\s*구축',
      'sme_certificate':r'소기업[\s․·/-]*소상공인\s*확인서|소기업.{0,150}소상공인.{0,60}확인서|중소기업\s*확인서|소기업\s*확인서|소기업.?소상공인.*소지|중소기업자\s*만|소기업\s*만|소상공인\s*만|중소기업자.{0,22}입찰',
      'staff_proof':(
          # Onsite is a worksite mode, not a bidder staffing-date requirement.
          # Preserve these clauses for the dedicated onsite/offsite UI judgment.
          r'상주\s*(?:근무|배치|운영|유지관리)|현장\s*상주|'
          r'(?:발주기관|발주처|수요기관|기관\s*내).{0,35}(?:상시\s*근무|상주\s*근무)|'
          r'(?:상시\s*근무|상주\s*근무).{0,35}(?:발주기관|발주처|수요기관)|'
          r'재직.{0,12}경력|경력.{0,12}학력|자격.?증명서|투입\s*인력|'
          r'(?:상주|전담|현장\s*배치).{0,35}(?:인력|개발자|기술자|\d+\s*(?:명|인))|'
          r'(?:인력|개발자|기술자|\d+\s*(?:명|인)).{0,35}(?:상주|전담|현장\s*배치)|'
          r'(?:중급|고급|초급|특급).{0,24}(?:기술자|개발자|기술인력)|'
          r'(?:경력|개발경험).{0,15}\d+\s*년|'
          r'\d+(?:\.\d+)?\s*(?:MM|M/M|맨먼스|[Mm]an[- ]?[Mm]onth)|'
          r'(?:입찰\s*공고일|입찰\s*마감일|제안서\s*제출일).{0,100}(?:재직|소속|4대\s*보험)|'
          r'(?:재직|소속|4대\s*보험).{0,100}(?:입찰\s*공고일|입찰\s*마감일|제안서\s*제출일)|'
          r'재직\s*증명서|4대\s*보험|사대보험|낙찰\s*후.{0,40}(?:채용|인력)|'
          r'착수\s*(?:일|전).{0,30}(?:인력|채용|확보)'),
      'performance_proof':r'실적\s*증명|수행\s*실적|유사\s*용역\s*실적',
      'region_restriction':r'지역\s*제한|본점\s*소재|주된\s*영업소|소재지',
      'joint_participation':r'공동\s*수급|분담\s*이행|하도급',
      'legal_exclusion':r'제\s*8조의\s*2|조세\s*포탈|유죄판결이\s*확정된|입찰에\s*참여할\s*수\s*없|입찰\s*참가\s*자격\s*제한\s*기간\s*중|입찰\s*참가\s*자격\s*제한을?\s*받은\s*자',
      'bid_security':r'입찰보증금|입찰공고일\s*이전\s*1년\s*이내.{0,130}입찰참가자격',
      'registration_identity':r'입찰\s*참가\s*자격\s*등록\s*(?:사항|증|정보|규정|장소)|경쟁\s*입찰\s*참가\s*자격\s*등록증|상호\s*또는\s*대표자\s*변경신고|변경\s*전\s*상호|변경\s*등록(?:하여야|하지|하고|을)|등록\s*정보.{0,65}(?:상호|대표자)',
      'eligibility_cutoff':r'입찰참가자격의\s*판단기준일|마감일.{0,90}참가자격을\s*갖추지\s*않은',
      'submission_required':r'입찰업체\s*서약서|입찰참가자격\s*확인을\s*위한\s*제출서류|입찰\s*참가\s*자격\s*입증\s*서류|입찰\s*참가\s*등록하고\s*규격서에\s*따라\s*납품\s*가능한\s*업체|규정에\s*의한\s*참가자격을\s*갖추고|(?:경쟁\s*입찰\s*)?참가\s*자격을?\s*(?:갖춘|구비한|갖추어야)|입찰\s*참가\s*자격\s*등록\s*마감일시',
      'special_legal_entity':r'특별법인'
    }
    # PDF extraction may drop article digits and split the SME eligibility
    # sentence across lines. Capture the fragment as *unreviewed evidence*;
    # do not infer that the bidder satisfies the certificate requirement.
    if filename.lower().endswith('.pdf'):
        rules['sme_certificate'] += (
            r'|중소기업기본법\s*제?\s*\d*\s*조|소기업자\s*또는\s*소상')
    out=[];seen=set()
    for index,line in enumerate(raw_lines):
        if len(line)<12 and not re.search(
            r"공동\s*수급.{0,4}(?:불허|금지|불가)|하도급.{0,4}(?:불허|금지|불가)",line):
            continue
        # Only nonqualification guidance may be skipped. The same test is
        # used by the coverage auditor, so this cannot silently clear an
        # unmatched mandatory licence, registration or certificate line.
        if nonqualification_context(line):
            continue
        # Prefer one extracted paragraph; for visually wrapped PDF lines include
        # the following short line, never the entire neighbouring section.
        if len(line)>270:
            # A 271-800 character official paragraph was previously truncated
            # to the first 270 characters, silently dropping later conditions.
            windows=[line[i:i+270] for i in range(0,len(line),220)]
        else:
            windows=[line]
        if len(line)<100 and index+1<len(raw_lines):
            next_line=raw_lines[index+1]
            if 0<len(next_line)<=170:windows.append((line+' '+next_line)[:270])
        if len(line)<100 and index>0:
            prev=raw_lines[index-1]
            if 0<len(prev)<=170:windows.append((prev+' '+line)[:270])
        # PDF line wrapping may place the legal citation two lines before
        # the actual bidder requirement. Keep one continuous cited 270-char
        # window; do not reclassify by shared keywords alone.
        if filename.lower().endswith('.pdf') and len(line)<140:
            neighbors=raw_lines[max(0,index-2):min(len(raw_lines),index+3)]
            if all(len(v)<=175 for v in neighbors):
                joined=' '.join(neighbors)
                windows.extend(joined[i:i+270] for i in range(0,len(joined),220))
        for window in windows:
            for topic,rx in rules.items():
                if not re.search(rx,window,re.I):continue
                if topic=='industry_code':
                    codes=re.findall(r'(?<!\d)\d{4}(?!\d)',window)
                    codes=[c for c in codes if not c.startswith('20')]
                elif topic=='direct_production':
                    codes=re.findall(r'(?<!\d)\d{10}(?!\d)',window)
                else:codes=[]
                phrase=window[:270]
                key=(topic,phrase)
                if key in seen:continue
                seen.add(key)
                out.append({'type':topic,'codes':codes[:6],'sourceFile':filename[:160],
                   'sourceText':phrase,'reviewStatus':'unreviewed',
                   'explicitMust':bool(re.search(
                    r'반드시|필수|입찰참가자격|소지하여야|제출하여야|등록한\s*자|소지한\s*(?:자|업체)|등록을?\s*필한\s*업체|업체이어야',phrase)),
                   'documentRequiresManualFullReview':True})
    return out


def clearly_nonqualification_guidance(line):
    """Skip narrow, unmistakable bidder *instructions*, not actual credentials.

    Never discard a paragraph that also states a concrete registration,
    certificate, location, qualification threshold or current exclusion.
    """
    concrete = re.search(
        r'업종\s*코드|(?<!\d)\d{10}(?!\d)|직접\s*생산\s*(?:확인|증명)|'
        r'(?:중소|소)기업\s*(?:자\s*)?확인서|소상공인\s*확인서|'
        r'본점\s*소재|주된\s*영업소|지역\s*제한|'
        r'조세\s*포탈|입찰\s*참가\s*자격\s*제한\s*기간\s*중|'
        r'(?:(?:실적|인력|경력)\s*\d+\s*(?:년|명|건|원|억)\s*이상)|'
        r'(?:소지|등록)한\s*(?:자|업체)\s*만\s*(?:참가|입찰)', line)
    if concrete:
        return False
    # Read-the-documents instruction; "반드시" modifies "확인 바랍니다".
    if re.search(r'(?:투찰|입찰)\s*업체.{0,45}입찰\s*참가\s*자격.{0,90}'
                 r'(?:확인\s*(?:하(?:시기|여|도록)?|바랍니다|요망)|숙지\s*바랍니다)', line):
        return True
    # Presentation-only attendee IDs, employment evidence and ID cards are
    # not prerequisites for the bidder firm. They can be required on the day
    # of presentation, so retain these in ordinary extracted text.
    if (re.search(r'제안(?:서)?\s*발표|발표자|발표\s*참석|참석\s*인원|'
                  r'참석\s*입찰\s*참가자|참석자\s*전원', line) and
            re.search(r'재직\s*증명|신분증|4대\s*보험|가입\s*증명', line) and
            not re.search(r'입찰\s*참가\s*자격.{0,45}(?:경력|인력|재직)|'
                          r'입찰\s*참가.{0,40}(?:직원|기술자)\s*\d+\s*명\s*이상', line)):
        return True
    # Score/bonus table rows do not automatically become minimum eligibility.
    if (re.search(r'배점|가점|평가\s*점수|점수\s*배분|평가\s*항목|'
                  r'실적\s*점수|\d+\s*점\s*만점', line) and
            re.search(r'실적|경력|기술\s*인력|재직\s*증명', line) and
            not re.search(r'입찰\s*참가\s*자격.{0,65}(?:실적|경력|인력)|'
                          r'(?:실적|인력|경력).{0,30}(?:필수\s*(?:조건|자격)|'
                          r'이상\s*보유.{0,20}(?:입찰|참가))', line)):
        return True
    # A warning about a *possible future* sanction is not an indication of
    # the bidder's present suspension or a separate mandatory certificate.
    if (re.search(r'서약\s*내용.{0,45}허위.{0,110}'
                  r'(?:입찰\s*참가\s*자격.{0,9}제한|제재|계약\s*해[제지])', line) and
            not re.search(r'현재|이미|제재\s*기간\s*중|조세\s*포탈', line)):
        return True
    return False


def nonqualification_context(line):
    """Ignore only unambiguous headings/administration/evaluation context.
    Explicit bidder requirements, prohibitions and regional restrictions
    always need a cited candidate and interpretation."""
    if clearly_nonqualification_guidance(line):
        return True
    # A qualification heading stating that rules follow is not itself an
    # additional condition; each subsequent actual condition is still scanned.
    if re.fullmatch(
        r"\s*(?:\d+[.]\s*)?(?:(?:견적|입찰)\s*제출\s*)?"
        r"(?:입찰\s*)?참가\s*자격\s*[(]?\s*(?:아래|다음)\s*조건을?\s*모두\s*충족하여야\s*함\s*[)]?\s*", line):
        return True
    # A standalone continuation of the official call-center responsibility
    # warning is not an independent bidder credential.
    if re.fullmatch(r"입찰\s*참가자에게\s*있습니다\.?\s*", line):
        return True
    if re.fullmatch(
        r"\s*(?:(?:\d+(?:[.\-]\d+)*|[가-힣])[\.\)]?\s*)?"
        r"(?:입찰\s*참가\s*자격|참가\s*자격|입찰참가자격)\s*[:：.]?\s*",line):
        return True
    # A post-negotiation document request is not a pre-bid licence.
    # Only ignore this narrow, documented PDF-wrapped instruction.
    if (re.search(r"협상대상자에게\s*필요한\s*서류\s*제출을?\s*요", line) and
            not re.search(r"업종\s*코드|직접\s*생산|확인서를?\s*소지", line)):
        return True
    # Electronic bidding call-centre responsibility (PDF wrapped).
    if (re.search(r"장애발생.{0,100}문의하지\s*않아.{0,100}책임은\s*입찰\s*참가자", line) and
            not re.search(r"업종\s*코드|직접\s*생산|입찰참가자격등록", line)):
        return True
    # Only documented non-credential contexts are safe to ignore.
    if re.search(r"신용평가등급.{0,100}(?:배점|평가)|창업기업.{0,90}(?:배점|점수)|"
                 r"중소기업협동조합.{0,90}신용평가등급",line):
        if not re.search(r"소기업.{0,20}(?:확인서|소지하여야)|직접\s*생산.{0,20}확인",line):
            return True
    if re.search(r"조달\s*콜센터.{0,140}(?:문의|책임)|전산장비.{0,80}(?:투찰|등록)|"
                 r"보안각서.{0,70}열람|제안내용.{0,50}추가\s*자료",line):
        return True
    if re.search(r"누출|유출|담합|금품|향응|청렴|근로자\s*권리|"
                 r"계약의\s*주요조건을\s*위반|불공정행위|퇴직자",line) and re.search(
                 r"입찰\s*참가\s*자격\s*제한|입찰참가자격제한|부정당업자",line):
        if not re.search(r"입찰공고일\s*이전\s*1년|조세\s*포탈|"
                         r"제\s*8조의\s*2|입찰\s*참가\s*자격.{0,40}(?:현행|현재)\s*제한",line):
            return True
    if re.search(r"계약이\s*해지.{0,110}입찰참가자격\s*제한|"
                 r"입찰.{0,40}취소되거나.{0,100}부정당업자",line):
        return True
    if re.search(r"^\s*주\s*\d+\).*재직증명서",line):
        return True
    # An already incurred suspension is not the same as a possible sanction
    # for future conduct. These precise variants are from the audited RFP.
    if re.search(r"(?:유출|누출).{0,180}입찰참가자격을\s*제한",line):
        return True
    if re.search(r"입찰자\s*또는\s*낙찰자가.{0,160}제76조.{0,160}"
                 r"입찰참가자격을\s*제한할\s*수",line):
        return True
    if re.search(r"이를\s*위반한\s*사실.{0,260}"
                 r"입찰참가자격제한.{0,55}처분을\s*받을\s*수",line):
        return True
    if re.search(r"부정당업자.{0,28}입찰참가자격제한처분을\s*받을\s*수|"
                 r"법령에\s*따라\s*부정당업자로\s*입찰참가자격\s*제한처분을\s*받을\s*수",line):
        return True
    # Administrative instructions and future penalties are not *new* bidder
    # certificates. Guard against their containing actual codes or conditions.
    if re.search(r"(?:낙찰자|계약상대자).{0,140}"
                 r"(?:계약불이행|계약해지|보증금|직접생산\s*확인기준|"
                 r"입찰참가자격\s*제한|부정당업자\s*제재)",line):
        if not re.search(r"등록\s*(?:하여야|한\s*자)|소지한\s*(?:자|업체)|"
                         r"자격을\s*갖춘\s*자",line):
            return True
    if re.search(r"조달청.{0,25}입찰참가자격\s*등록.{0,12}안내|"
                 r"경쟁입찰참가자격\s*등록은?\s*수시|"
                 r"입찰\s*참가\s*시.{0,80}(?:전산장비|투찰이\s*곤란)|"
                 r"협상대상자.{0,50}서류\s*제출.{0,25}요구할\s*수",line):
        if not re.search(r"(?:업종코드|세부품명번호|직접생산확인증명서|"
                         r"소기업.{0,8}확인서|주된\s*영업소|지역제한)",line):
            return True
    if re.fullmatch(r"\s*(?:[①-⑳]|[\d\-]+[\.\)]?)?\s*"
                    r"(?:기타\s*서류)?\s*\(?입찰\s*참가\s*자격\s*확인\s*서류\)?",line):
        return True
    # A section heading announcing subsequent bidder requirements is not
    # itself a credential. Scan the following lines for actual requirements.
    if re.search(r'(?:입찰|견적)\s*(?:제출\s*)?참가\s*자격', line) and (
            re.search(r'(?:아래|다음|각\s*호).{0,70}(?:조건|요건|자격)', line)
            or re.fullmatch(
                r'\s*(?:\d+[\.\)]?\s*)?(?:입찰|견적)\s*(?:제출\s*)?'
                r'참가\s*자격\s*[:：]?\s*', line)):
        if not re.search(
                r'업종\s*코드|\b\d{10}\b|직접\s*생산|소기업|소상공인|'
                r'본점\s*소재|주된\s*영업소|지역\s*제한|'
                r'등록한\s*(?:자|업체)|소지한\s*(?:자|업체)', line):
            return True
    # These are administrative notices, not new bidder-specific entry gates.
    # Keep any sentence with a concrete licence, certificate or restriction.
    real_condition = re.search(
        r'업종\s*코드|\b\d{10}\b|직접\s*생산|소기업|소상공인|'
        r'본점\s*소재|주된\s*영업소|지역\s*제한|'
        r'입찰참가자격의\s*판단기준일|변경\s*등록하여야', line)
    if not real_condition:
        if re.search(r'(?:콜\s*센터|1588-0800).{0,120}(?:문의|책임)|'
                     r'(?:문의하지\s*않아|숙지하지\s*못).{0,90}(?:책임|부담)|'
                     r'(?:책임|비용)은?\s*입찰\s*참가자(?:에게|의)', line):
            return True
        if re.search(r'(?:제안서|제안내용|제안사).{0,75}(?:추가자료|추가제안|'
                     r'평가결과|비용\s*부담|반환하지)|'
                     r'입찰\s*참가자.{0,60}(?:추첨|추가자료)|'
                     r'입찰\s*참가\s*(?:업체|순).{0,60}(?:제안서|발표|평가)', line):
            return True
        if re.search(r'(?:부정|위조|변조|허위).{0,110}'
                     r'(?:입찰\s*참가\s*자격\s*제한|공모참가자격\s*제한)|'
                     r'(?:계약\s*해지|계약불이행|이행하지\s*않).{0,110}'
                     r'입찰\s*참가\s*자격\s*제한',line):
            if not re.search(r'현재|이미|제재\s*기간\s*중|'
                             r'입찰\s*참가\s*자격\s*제한을?\s*받은\s*자',line):
                return True
    if re.fullmatch(r'\s*(?:[IVXⅣⅤⅥ\d.\s]+[.]?\s*)?'
                    r'(?:수의\s*견적\s*제출\s*)?참가\s*자격\s*(?:\d{1,3})?\s*',line):
        return True
    if re.search(r'참가\s*자격\s*등록\s*장소\s*:\s*조달청\s*(?:고객|정부)',line):
        return True
    strong=bool(re.search(# A call-centre number such as 1588-0800 is not a four-digit G2B industry code.
        r"(?<![\d-])\d{4}(?![\d-])|(?<!\d)\d{10}(?!\d)|"
        r"직접\s*생산|소기업\s*확인|중소기업\s*확인|"
        r"지역\s*제한|본점\s*소재|주된\s*영업소",line))
    if strong:return False
    if re.search(r'입찰.{0,30}등록하고.{0,70}(?:납품|수행)\s*가능한\s*업체|규격서.{0,35}납품\s*가능',line):
        return False
    if re.fullmatch(r'\s*(?:입찰\s*참가\s*신청서|입찰\s*참가\s*서류|입찰\s*유의사항)\s*',line):
        return True
    if re.search(r"제안서|평가\s*(?:항목|기준|점수|배점|표)|붙임|별지|서식|양식",line):
        if re.search(r"수행\s*실적|실적\s*증명|투입\s*인력|재직\s*증명|공동\s*수급",line):
            if not re.search(r"(?:입찰\s*참가|참가\s*자격).{0,45}(?:필수|실적|경력|인력)|"
                             r"(?:실적|인력).{0,35}(?:이상|입찰\s*참가\s*자격)",line):
                return True
    if re.search(r"나라장터|전자\s*입찰|조달청\s*이용|입찰참가자격등록규정",line):
        if not re.search(r"소지한\s*(?:업체|자)|등록(?:하여야|을?\s*필한)|"
                         r"(?:입찰\s*참가\s*자격).{0,45}(?:갖춘|있어야)",line):
            return True
    if re.search(r"계약\s*체결\s*후|낙찰\s*후|착수\s*후",line):
        # Do not discard post-award hiring/deployment deadlines.
        if re.search(r"인력|채용|개발자|기술자|재직|소속|상주|전담|확보|충원",line):
            return False
        return not re.search(r"입찰\s*참가\s*자격.{0,40}(?:있어야|필수)",line)
    return False


def audit_qualification_scan(text, candidates, include_missing=False):
    """Count every eligibility-looking paragraph, not only extracted snippets.

    This is *coverage evidence*, not proof that a bidder satisfies the text.
    Unrecognized qualification wording must prevent automatic full review.
    """
    lines=[' '.join(line.split()) for line in re.split(r'\n+',text)]
    source=[str(x.get('sourceText') or '') for x in candidates]
    # Long paragraphs are split into overlapping evidence windows. Comparing
    # the entire paragraph to one window falsely reports coverage missing.
    normalized_sources=[re.sub(r"\s+","",s) for s in source]
    anchor_lines=[line for line in lines if EXTRA_QUALIFICATION_ANCHORS.search(line)]
    missing=[]
    missing_full=[]
    for line in anchor_lines:
        if nonqualification_context(line):
            continue
        # Require each eligibility-looking local span in the original to
        # be covered by a cited candidate, not just a shared keyword.
        anchored=[]
        for anchor in EXTRA_QUALIFICATION_ANCHORS.finditer(line):
            a=max(0,anchor.start()-25)
            b=min(len(line),anchor.end()+45)
            span=re.sub(r"\s+","",line[a:b])
            key=re.sub(r"\s+","",anchor.group())
            if span:anchored.append((key,span))
        # Source excerpts have 50-character overlaps; a qualification
        # anchor can straddle an excerpt boundary. Require *every* short
        # context fragment to be attested by some cited excerpt, including
        # the anchor itself. Keyword-only matches cannot prove coverage.
        def cited(key,span):
            if not any(key in evidence for evidence in normalized_sources):
                return False
            if len(span)<=32:
                pieces=[span]
            else:
                pieces=[span[i:i+32] for i in range(0,len(span)-31,20)]
                pieces.append(span[-32:])
            return all(any(piece in evidence for evidence in normalized_sources)
                       for piece in pieces)
        matched=bool(anchored) and all(cited(key,span) for key,span in anchored)
        if not matched:
            missing.append(line[:180])
            if include_missing:missing_full.append(line)
    complete=(len(text)<=350_000 and not missing)
    result={'sourceTextScanComplete':complete,
            'qualificationAnchorCount':len(anchor_lines),
            'unmatchedQualificationAnchorCount':len(missing),
            'unmatchedAnchorSamples':missing[:30]}
    if include_missing:result['_uncitedLines']=missing_full
    return result


def preserve_unclassified_qualification(text, filename, candidates):
    """Preserve every uncited eligibility-looking phrase without declaring it met.

    This closes an extraction evidence gap, NOT an eligibility gate. Unknown
    legal or bidder conditions are retained verbatim and force manual review.
    """
    before=audit_qualification_scan(text,candidates,include_missing=True)
    missing=before.pop('_uncitedLines')
    extras=[];seen=set()
    for line in missing:
        if nonqualification_context(line):continue
        for match in EXTRA_QUALIFICATION_ANCHORS.finditer(line):
            # The citation auditor requires 25 characters before and 45
            # after every anchor. Preserve a wider contiguous excerpt.
            start=max(0,match.start()-35)
            end=min(len(line),match.end()+55)
            quote=line[start:end]
            if not quote or quote in seen:continue
            seen.add(quote)
            extras.append({'type':'unclassified_qualification','codes':[],
                           'sourceFile':filename[:160],'sourceText':quote,
                           'reviewStatus':'unreviewed','explicitMust':False,
                           'documentRequiresManualFullReview':True})
    candidates.extend(extras)
    after=audit_qualification_scan(text,candidates)
    after['unclassifiedQualificationCount']=len(extras)
    after['preSupplementUnmatchedCount']=before['unmatchedQualificationAnchorCount']
    return after

def normalize_extracted_text(content):
    """Treat embedded NUL separators as whitespace before extracting qualifications."""
    return content.replace('\x00', ' ')



def preflight_rfp_metadata(unscanned, fetcher=None, sample_size=4):
    """Distinguish daily quota from brief bursts before downloading RFPs."""
    fetcher=fetch_json if fetcher is None else fetcher
    staged={}
    valid=0
    for no,ordn in unscanned[:sample_size]:
        url=BASE+'bid-evidence?'+urllib.parse.urlencode({'bidNo':no,'order':ordn})
        try:
            for attempt in range(2):
                data=fetcher(url)
                attachments=data.get('attachments') or {}
                notice=data.get('noticeDocuments') or {}
                errors=[str(attachments.get('error') or ''),
                        str(notice.get('error') or ''),str(data.get('error') or '')]
                daily=any('LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR' in e or
                          'upstream_result_22' in e for e in errors)
                cached_daily=any(e=='upstream_temporarily_rate_limited_daily_quota'
                                 for e in errors)
                transient=any('upstream_temporarily_rate_limited' in e or
                              'upstream_http_429' in e or
                              'PER_SECOND_EXCEEDS_ERROR' in e or
                              'upstream_result_23' in e for e in errors)
                if daily:
                    print('RFP_UPSTREAM_ORIGINAL_DAILY_LIMIT',no+':'+ordn,
                          'ORIGIN',','.join(x for x in errors if x)[:180],flush=True)
                    raise RuntimeError('RFP_UPSTREAM_DAILY_QUOTA_PREFLIGHT')
                if cached_daily:
                    # The proxy's cached flag is NOT a fresh original provider
                    # response and cannot establish account-wide quota usage.
                    print('RFP_PROXY_CACHED_DAILY_COOLDOWN_UNVERIFIED',no+':'+ordn,
                          flush=True)
                    raise RuntimeError('RFP_PROXY_CACHED_DAILY_COOLDOWN_PREFLIGHT')
                # Legacy unsuffixed cooldown cannot establish the provider's
                # category. Preserve fail-safe behavior in old deployments.
                if 'upstream_temporarily_rate_limited' in errors:
                    print('RFP_UPSTREAM_LEGACY_COOLDOWN',no+':'+ordn,flush=True)
                    raise RuntimeError('RFP_UPSTREAM_RATE_LIMITED_PREFLIGHT')
                if transient and attempt==0:
                    print('RFP_UPSTREAM_SHORT_LIMIT_RETRY',no+':'+ordn,flush=True)
                    time.sleep(6)
                    continue
                if transient:
                    raise RuntimeError('RFP_UPSTREAM_TRANSIENT_LIMIT_PREFLIGHT')
                break
            valid+=int(attachments.get('ok') is True and
                       attachments.get('complete') is True)
            staged[(no,ordn)]=data
        except RuntimeError as err:
            if str(err).startswith('RFP_UPSTREAM_'):
                raise
            staged[(no,ordn)]={'attachments':{
                'ok':False,'complete':False,'error':'preflight_RuntimeError'}}
        except Exception as err:
            reason=('http_'+str(err.code) if isinstance(err,urllib.error.HTTPError)
                    else type(err).__name__)
            staged[(no,ordn)]={'attachments':{
                'ok':False,'complete':False,'error':'preflight_'+reason}}
    print('RFP_METADATA_PREFLIGHT','TESTED',len(staged),
          'COMPLETE',valid,'UPSTREAM_UNAVAILABLE',len(staged)-valid,flush=True)
    if staged and not valid:
        raise RuntimeError('RFP_UPSTREAM_METADATA_UNAVAILABLE_PREFLIGHT')
    return staged

def process(no,ordn,metadata=None,previous=None,prefetch=None):
    if (os.environ.get('WORKLINKS_RFP_DUAL_SCAN_ONLY')=='1'
            and metadata is None):
        # A durable ready/scan record MUST include verified bulk metadata.
        # Missing metadata is not permission to fetch bid-evidence by notice.
        return {'status':'metadata_not_confirmed',
                'reasonCode':'dual_queue_bulk_manifest_missing',
                'reviewComplete':False,'files':[]}
    phase={'downloadSeconds':0.0,'downloadQueueWaitSeconds':0.0,'extractSeconds':0.0,
           'analysisSeconds':0.0,'textCacheHits':0,'filesProcessed':0,
           'deferredImageFiles':0}
    data=(metadata if metadata is not None else fetch_json(
        BASE+'bid-evidence?'+urllib.parse.urlencode({'bidNo':no,'order':ordn})))
    docs=data.get('attachments') or {}
    if not docs.get('ok') or not docs.get('complete'):
        return {'status':'metadata_not_confirmed','reasonCode':'metadata_api_error' if not docs.get('ok') else 'metadata_page_incomplete',
                'sourceError':str(docs.get('error') or '')[:120],
                'count':docs.get('count'),'source':'나라장터 e발주 첨부파일 API'}
    if not docs.get('items'):
        notice=data.get('noticeDocuments') or {}
        ecount=docs.get('eorderCount')
        detail_status='notice_detail_'+('api_error' if not notice.get('ok') else
           'zero_files' if notice.get('complete') else 'partial_response')
        return {'status':'no_official_attachment_metadata',
                'reasonCode':'eorder_api_zero__'+detail_status,
                'source':'나라장터 e발주 + 공식 입찰공고 상세',
                'count':0,'eorderCount':ecount,'noticeDetailDocumentCount':0,
                'noticeDetailError':notice.get('error') or '',
                'files':[],'reviewComplete':False,
                'contractPerformanceVerified':False}
    saved=[]
    # Reuse the EXACT successfully parsed attachment when a retry is needed
    # only for another failed file or a newly added file. Never download all
    # previous successes again just because one sibling attachment failed.
    reusable={}
    if (isinstance(previous,dict) and
            previous.get('classificationVersion')==CLASSIFICATION_VERSION and
            previous.get('hwpxReaderVersion')==HWPX_READER_VERSION):
        for old_file in previous.get('files') or []:
            if (isinstance(old_file,dict) and
                    old_file.get('readable') is True and
                    old_file.get('sourceSha256') and
                    old_file.get('sourceUrl')):
                reusable[(old_file.get('name'),old_file.get('sourceUrl'))]=old_file
    manifest=docs.get('items') or []
    primary_manifest=manifest[:MAX_DOCUMENTS]
    # Process PDF first, even when the official list puts HWP first.
    # Restore official ordering in saved source evidence afterwards.
    processing_order=sorted(range(len(primary_manifest)),
        key=lambda i: 0 if str(primary_manifest[i].get('name') or '').lower().endswith('.pdf') else 1)
    saved_slots={}
    queued={}
    prefetch_positions=iter(_eligible_prefetch_positions(
        primary_manifest,processing_order,reusable)) if prefetch is not None else iter(())
    notice_key=no+':'+ordn
    close_date=_NOTICE_DEADLINES.get(notice_key,'')
    def refill():
        if prefetch is None:return
        while len(queued)<2:
            try:position=next(prefetch_positions)
            except StopIteration:break
            name,url=legal_file(primary_manifest[position])
            queued[position]=prefetch.submit(notice_key,close_date,url)
    refill()
    for position in processing_order:
        item=primary_manifest[position]
        public=legal_file(item)
        if not public:
            saved_slots[position]={'name':str(item.get('name') or '')[:160],'readable':False,
                          'errorCategory':invalid_file_reason(item)}
            continue
        name,url=public
        # Same filename stem + verified PDF in this notice: use PDF only.
        # Do not download the duplicate HWP and never mark it readable.
        companion=verified_pdf_companion({'name':name},list(saved_slots.values()))
        if companion:
            saved_slots[position]={
                'name':name,'sourceUrl':url,'readable':False,
                'sourceTextScanComplete':False,
                'skippedDuplicateFormat':True,
                'alternatePdfEvidence':companion['name'],
                'alternatePdfSourceSha256':companion['sourceSha256'],
                'alternatePdfEvidenceMode':'same_basename_not_proven_identical'}
            continue
        retained=reusable.get((name,url))
        # Qualification text can be reused ONLY if its separate staffing-table
        # pass was completed as well. Older read-only qualification scans must
        # reparse this official file (cached bytes if present, otherwise download).
        if (retained and
                int(retained.get('staffingRoleScanVersion') or 0)>=STAFFING_ROLE_SCAN_VERSION and
                int(retained.get('staffingFactScanVersion') or 0)>=STAFFING_FACT_SCAN_VERSION and
                retained.get('staffingRoleScanTruncated') is not True):
            saved_slots[position]=dict(retained)
            continue
        record={'name':name,'sourceUrl':url,'readable':False}
        if (os.environ.get('WORKLINKS_RFP_DEFER_OCR')=='1' and
                name.lower().endswith(('.png','.jpg','.jpeg','.bmp','.tif','.tiff','.webp'))):
            record.update(errorCategory='ocr_deferred_to_repair',
                          sourceTextScanComplete=False,ocrDeferred=True)
            phase['deferredImageFiles']+=1
            saved_slots[position]=record
            continue
        try:
            # Measure file work separately from page retrieval, metadata and
            # whole-index JSON publication; worker threads may overlap.
            phase['filesProcessed']+=1
            if prefetch is not None:
                future=queued.pop(position,None)
                if future is None:
                    # Fallback HWP after an unsuccessful same-stem PDF remains
                    # in the bounded downloader, never in the scan thread.
                    future=prefetch.submit(notice_key,close_date,url)
                waited=time.perf_counter()
                try:
                    raw,download_seconds=future.result()
                finally:
                    prefetch.release(url,future)
                    phase['downloadQueueWaitSeconds']+=time.perf_counter()-waited
                phase['downloadSeconds']+=download_seconds
                # Start fetching the next official file before parsing bytes.
                refill()
                # A coalesced source may belong to several notices: retain
                # every notice's deadline, not just the first downloader.
                ledger=active_rfp_ledger()
                if ledger is not None:
                    ledger.link_attachment(cache_key('official_attachment',url),
                                           notice_key,close_date)
            else:
                timer=time.perf_counter()
                try:
                    _NOTICE_CONTEXT.notice_key=notice_key
                    _NOTICE_CONTEXT.closes_on=close_date
                    raw=download(url)
                finally:
                    _NOTICE_CONTEXT.notice_key=None
                    _NOTICE_CONTEXT.closes_on=''
                    phase['downloadSeconds']+=time.perf_counter()-timer
            timer=time.perf_counter()
            try:
                extracted,source_evidence,text_cache_hit=extract_cached_text(name,raw)
            finally:
                phase['extractSeconds']+=time.perf_counter()-timer
            phase['textCacheHits']+=int(text_cache_hit)
            content=normalize_extracted_text(extracted)
            timer=time.perf_counter()
            if len(content.strip())<(30 if name.lower().endswith(('.xlsx','.pptx','.png','.jpg','.jpeg','.webp')) else 100):
                raise ValueError('no_searchable_text')
            triggers,snippets=parse_clauses(content)
            candidate_rules=extract_rule_candidates(content,name)
            staffing_roles=extract_staffing_roles(content,name,url)
            staffing_facts=extract_staffing_facts(content,name,url)
            scan=preserve_unclassified_qualification(content,name,candidate_rules)
            phase['analysisSeconds']+=time.perf_counter()-timer
            record.update({'readable':True,'textChars':len(content),
                           **scan,
                           'sourceTextScanComplete':scan.get('sourceTextScanComplete') is True and
                                                    source_evidence['sourceComplete'],
                           'extractionEvidence':source_evidence,
                           'sourceSha256':hashlib.sha256(raw).hexdigest(),
                           'textSha256':hashlib.sha256(content.encode('utf-8')).hexdigest(),
                           'extractedTextCacheHit':text_cache_hit,
                           'qualificationScanTruncated':len(content)>350_000,
                           'clauseCandidatesTruncated':False,
                           'staffingRoleScanVersion':STAFFING_ROLE_SCAN_VERSION,
                           'staffingFactScanVersion':STAFFING_FACT_SCAN_VERSION,
                           'staffingRoleScanTruncated':len(content)>STAFFING_ROLE_TEXT_LIMIT,
                           'staffingRoles':staffing_roles,
                           'staffingFacts':staffing_facts,
                           'topics':triggers,'snippets':snippets,
                           'clauseCandidates':candidate_rules,
                           'fullReviewPending':True})
        except Exception as ex:
            record['errorCategory']=classify_failure(ex)
            record['error']=type(ex).__name__+': '+str(ex)[:90]
        saved_slots[position]=record
    saved=[saved_slots[i] for i in range(len(primary_manifest))]
    annotate_official_pdf_siblings(saved)
    for item in manifest[MAX_DOCUMENTS:]:
        saved.append({'name':str(item.get('name') or '')[:160], 'readable':False,
                      'errorCategory':'manifest_documents_over_limit'})
    readable=any(x.get('readable') for x in saved)
    notice=data.get('noticeDocuments') or {}
    return {'status':'text_extracted_requires_review' if readable else 'text_unavailable',
            'reasonCode':'readable_text_requires_full_review' if readable else
                         'download_or_format_failure',
            'source':'나라장터 e발주 + 입찰공고 상세',
            'count':docs.get('count'),'eorderCount':docs.get('eorderCount'),
            'noticeDetailDocumentCount':docs.get('noticeDetailDocumentCount'),
            'noticeDetailError':notice.get('error') or '',
            'attachmentManifestCount':len(manifest),
            'manifestComplete':docs.get('complete') is True and
                               notice.get('ok') is True and notice.get('complete') is True,
            'readableDocumentCount':sum(int(f.get('readable') is True) for f in saved),
            'unreadableDocumentCount':sum(int(f.get('readable') is not True) for f in saved),
            'files':saved,
            'reviewComplete':False,'requiredConditionsComplete':False,
            'contractPerformanceVerified':False,
            'manifestSignature':official_manifest_signature(data),
            'manifestCheckedAt':dt.datetime.now(dt.timezone.utc).isoformat(),
            'manifestChangePending':False,'_stageTimings':phase}

def staffing_summary(item):
    """Bounded, per-notice role evidence in the cumulative lightweight index."""
    files=(item or {}).get('files') or []
    seen=set()
    rows=[]
    for f in files:
        if not isinstance(f,dict):continue
        sources=f.get('staffingRoles')
        if not isinstance(sources,list):
            sources=staffing_from_saved_excerpts(f)
        for row in sources:
            if not isinstance(row,dict):continue
            count=row.get('count')
            try:count=int(count)
            except (TypeError,ValueError):continue
            if not 1<=count<=99:continue
            role=str(row.get('role') or '').strip()
            if not _STAFF_ROLE.fullmatch(role):continue
            if staffing_source_is_general_example(
                    row.get('sourceFile') or f.get('name'),
                    row.get('sourceText')):continue
            grade=str(row.get('grade') or '')[:12]
            onsite=str(row.get('onsite') or '')[:12]
            signature=(role.lower(),grade,count,onsite,
                       str(row.get('countKind') or 'specified'))
            if signature in seen:continue
            seen.add(signature)
            output={
              'role':role,'grade':grade,'count':count,
              'countKind':str(row.get('countKind') or 'specified')[:12],
              'onsite':onsite,
              'manMonths':row.get('manMonths'),
              'sourceFile':str(row.get('sourceFile') or f.get('name') or '')[:140],
              'sourceLine':int(row.get('sourceLine') or 0),
              'sourceText':str(row.get('sourceText') or '')[:240],
              'scope':str(row.get('scope') or 'excerpt')[:12]}
            url=str(row.get('sourceUrl') or '')
            if url.startswith('https://www.g2b.go.kr/'):
                output['sourceUrl']=url
            rows.append(output)
            if len(rows)>=24:return rows
    return rows

def staffing_fact_summary(item):
    """Bounded source-provenanced workload/recommendation/role facts."""
    result=[]
    seen=set()
    supported={'workload_role','workload_total','headcount_recommended',
               'staffing_plan_required','role_unspecified','staffing_requirement'}
    for f in (item or {}).get('files') or []:
        if not isinstance(f,dict):continue
        if staffing_source_is_general_example(f.get('name')):continue
        for fact in f.get('staffingFacts') or []:
            if not isinstance(fact,dict) or fact.get('kind') not in supported:continue
            source=str(fact.get('sourceText') or '').strip()[:240]
            role=str(fact.get('role') or '').strip()[:80]
            if not source or not str(fact.get('sourceFile') or f.get('name') or '').strip():
                continue
            signature=(fact['kind'],role,str(fact.get('count')),str(fact.get('manMonths')),
                       str(fact.get('allocationRate')),str(fact.get('requirementType')),source)
            if signature in seen:continue
            seen.add(signature)
            clean={'kind':fact['kind'],'role':role,'sourceText':source,
                   'sourceFile':str(fact.get('sourceFile') or f.get('name'))[:140],
                   'sourceLine':int(fact.get('sourceLine') or 0)}
            for key in ('count','minimum','mandatory','onsite','headcount',
                        'manMonths','durationMonths','allocationRate','verifiedRoleCount',
                        'requirementType','label'):
                if key in fact:clean[key]=fact[key]
            url=str(fact.get('sourceUrl') or '')
            if url.startswith('https://www.g2b.go.kr/'):
                clean['sourceUrl']=url
            result.append(clean)
            if len(result)>=35:return result
    return result


def backfill_cached_staffing(records, max_files=24):
    """Reparse verified local attachment bytes only; NEVER make an HTTP call.

    Old detailed records without stored full text may retain quote-only
    staffing evidence, explicitly marked scope='excerpt'. The persisted ledger
    is optional; a missing binary is not a reason to download it again.
    """
    ledger=active_rfp_ledger()
    parsed=0
    for key,notice in sorted(records.items(),key=lambda entry:
                             str((entry[1] or {}).get('checkedAt') or ''),
                             reverse=True):
        if not isinstance(notice,dict):continue
        for f in notice.get('files') or []:
            if not isinstance(f,dict) or f.get('readable') is not True:continue
            if (int(f.get('staffingRoleScanVersion') or 0)>=STAFFING_ROLE_SCAN_VERSION and
                    int(f.get('staffingFactScanVersion') or 0)>=STAFFING_FACT_SCAN_VERSION):
                continue
            name=str(f.get('name') or '')
            url=str(f.get('sourceUrl') or '')
            raw=None
            if (ledger and parsed<max_files and
                    url.startswith('https://www.g2b.go.kr/') and
                    f.get('sourceSha256')):
                raw=ledger.get_bytes(cache_key('official_attachment',url),
                                     max_age_seconds=7*24*3600)
                if raw and hashlib.sha256(raw).hexdigest()!=f['sourceSha256']:
                    raw=None
            if raw:
                try:
                    extracted,evidence,_=extract_cached_text(name,raw)
                    content=normalize_extracted_text(extracted)
                    if not evidence.get('sourceComplete'):
                        raise ValueError('cached_source_scan_incomplete')
                    f['staffingRoles']=extract_staffing_roles(content,name,url)
                    f['staffingFacts']=extract_staffing_facts(content,name,url)
                    f['staffingRoleScanVersion']=STAFFING_ROLE_SCAN_VERSION
                    f['staffingFactScanVersion']=STAFFING_FACT_SCAN_VERSION
                    f['staffingRoleScanTruncated']=len(content)>STAFFING_ROLE_TEXT_LIMIT
                    parsed+=1
                except Exception:
                    # The original successful RFP qualification scan remains valid.
                    f['staffingRoles']=staffing_from_saved_excerpts(f)
            elif 'staffingRoles' not in f:
                f['staffingRoles']=staffing_from_saved_excerpts(f)
    return parsed

def compact_coverage(item):
    """Keep cross-run scan provenance for every bid, not capped at 240.

    Compact index is a *scan inventory*, not a license grant, a verified RFP
    comparison, nor proof that missing attachments never existed.
    """
    compact={
        'status':item.get('status') or 'unknown',
        'checkedAt':item.get('checkedAt') or '',
        'classificationVersion':item.get('classificationVersion',0),
        'hwpxReaderVersion':item.get('hwpxReaderVersion',0),
        'partialRetryCount':item.get('partialRetryCount',0),
        'reviewComplete':False,
        'attachmentManifestCount':item.get('attachmentManifestCount'),
        'manifestComplete':item.get('manifestComplete'),
        'readableDocumentCount':item.get('readableDocumentCount',0),
        'unreadableDocumentCount':item.get('unreadableDocumentCount',0),
        'files':[{
            'name':str(f.get('name') or '')[:160],
            'readable':f.get('readable') is True,
            'sourceSha256':str(f.get('sourceSha256') or '')[:64],
            'alternatePdfEvidence':str(f.get('alternatePdfEvidence') or '')[:160],
            'alternatePdfSourceSha256':str(f.get('alternatePdfSourceSha256') or '')[:64],
            'alternatePdfEvidenceMode':str(f.get('alternatePdfEvidenceMode') or '')[:50],
            'skippedDuplicateFormat':f.get('skippedDuplicateFormat') is True,
            'extractionEvidence':f.get('extractionEvidence') or {},
            'errorCategory':str(f.get('errorCategory') or '')[:60],
            'sourceTextScanComplete':f.get('sourceTextScanComplete') is True,
            'staffingRoleScanVersion':int(f.get('staffingRoleScanVersion') or 0),
            'staffingFactScanVersion':int(f.get('staffingFactScanVersion') or 0),
            'staffingScopeExcluded':bool(
                staffing_ancillary_form_without_extractable_text(f) or
                staffing_general_annex_file(f.get('name')) or
                staffing_source_is_general_example(f.get('name'))),
            'staffingScopeReason':(
                '입찰신청·서약 제출용 서식의 텍스트 미추출 (인력 판독 범위에서만 제외, 전체 문서 오류 유지)'
                if staffing_ancillary_form_without_extractable_text(f) else
                '공통 입찰·계약 규정 또는 일반 낙찰기준 (사업별 인원요건 아님)'
                if staffing_general_annex_file(f.get('name')) or
                   staffing_source_is_general_example(f.get('name')) else ''),
            'staffingRoleScanTruncated':f.get('staffingRoleScanTruncated') is True,
            'qualificationScanTruncated':f.get('qualificationScanTruncated') is True,
            'unmatchedQualificationAnchorCount':f.get('unmatchedQualificationAnchorCount',0),
            'clauseCandidateCount':len(f.get('clauseCandidates') or [])
        } for f in (item.get('files') or [])[:MAX_DOCUMENTS]]
    }
    compact['staffingRoles']=staffing_summary(item)
    compact['staffingFacts']=staffing_fact_summary(item)
    compact['staffingRoleScanComplete']=bool(
        item.get('manifestComplete') is True and compact['files'] and
        all(staffing_effective_file_complete(f,item.get('files') or [])
            for f in (item.get('files') or [])))
    for field in ('manifestSignature','manifestCheckedAt',
                  'manifestChangePending','manifestPendingSignature',
                  'manifestBaselineUnverified'):
        if item.get(field) is not None:
            compact[field]=item[field]
    return compact


def compact_changcom_evidence(item):
    """Bounded official source excerpts, never a verified qualification."""
    types=('industry_code','direct_production','sme_certificate','region_restriction',
           'joint_participation','performance_proof','staff_proof','eligibility_cutoff',
           'registration_identity','unclassified_qualification','legal_exclusion',
           'submission_required','bid_security')
    excerpts={t:[] for t in types}
    links=[]
    seen=set()
    for file in item.get('files') or []:
        if not isinstance(file,dict) or not file.get('readable'):continue
        url=str(file.get('sourceUrl') or '')
        if not url.startswith('https://www.g2b.go.kr/'):continue
        name=str(file.get('name') or '공식 첨부자료')[:100]
        if url not in [x['url'] for x in links] and len(links)<6:
            links.append({'name':name,'url':url})
        for clause in file.get('clauseCandidates') or []:
            if not isinstance(clause,dict):continue
            typ=str(clause.get('type') or '')
            if typ not in excerpts or len(excerpts[typ])>=3:continue
            quote=' '.join(str(clause.get('sourceText') or '').split())[:320]
            if not quote or (typ,quote) in seen:continue
            seen.add((typ,quote))
            codes=[str(c) for c in (clause.get('codes') or [])
                   if re.fullmatch(r'\d{4}|\d{10}',str(c))]
            excerpts[typ].append({'text':quote,'codes':codes,
                'sourceFile':name,'url':url,'interpretation':'manual_review_required'})
    return {
        'status':item.get('status') or 'not_scanned',
        'checkedAt':item.get('checkedAt') or '',
        'readableDocumentCount':item.get('readableDocumentCount',0),
        'unreadableDocumentCount':item.get('unreadableDocumentCount',0),
        'manifestComplete':item.get('manifestComplete') is True,
        'reviewComplete':False,'eligibilityVerified':False,
        'files':links,'clauseCandidates':{k:v for k,v in excerpts.items() if v}
    }


# GitHub rejects blobs over 100 MB. The detailed 240-notice view is a
# rolling cache; durable source hashes and bounded official excerpts are kept
# separately in rfp-coverage-index.json for ALL previously scanned notices.
MAX_PUBLISHED_RFP_BYTES=85_000_000


def bounded_detail_snapshot(records, max_records=240, max_bytes=MAX_PUBLISHED_RFP_BYTES):
    """Prioritize latest scans without silently exceeding the GitHub blob limit.

    Do not shorten individual quotations or claim that discarded cache entries
    were unscanned. The cumulative evidence index is written independently.
    """
    # Successful official excerpts outrank failed metadata-only refreshes.
    # Otherwise one G2B outage replaces the complete rolling 240-document
    # evidence cache with 240 zero-document error records.
    ordered=sorted(records.items(), key=lambda pair: (
        int(isinstance(pair[1],dict) and
            pair[1].get('status')=='text_extracted_requires_review' and
            any(isinstance(f,dict) and f.get('readable') and f.get('sourceSha256')
                for f in pair[1].get('files') or [])),
        str((pair[1] if isinstance(pair[1],dict) else {}).get('checkedAt') or '')),
        reverse=True)
    selected={}
    omitted=[]
    used=4096  # JSON wrapper and metadata headroom
    for key,item in ordered:
        encoded=json.dumps(item,ensure_ascii=False,separators=(',',':'))
        # Exact compact JSON payload plus a conservative per-key margin.
        estimated=len(encoded.encode('utf-8'))+len(json.dumps(key,ensure_ascii=False).encode('utf-8'))+4
        if len(selected)>=max_records or used+estimated>max_bytes:
            omitted.append(key)
            continue
        selected[key]=item
        used+=estimated
    if not selected and records:
        raise ValueError('RFP_DETAIL_RECORD_EXCEEDS_SAFE_BUDGET')
    print('RFP_DETAIL_SNAPSHOT_BOUNDED','STORED',len(selected),
          'OMITTED_FROM_ROLLING_CACHE',len(omitted),
          'BYTE_BUDGET',max_bytes,flush=True)
    return selected,len(omitted)


def publish_notice_checkpoint(notice_key, result, fingerprint):
    """Durably record ONE finished notice as soon as its future completes.

    This small SQLite checkpoint is independent of the 8-notice JSON snapshot.
    It includes only compact, source-linked evidence and never declares an
    incomplete source or unreadable file to be fully verified.
    """
    path=os.environ.get('WORKLINKS_RFP_NOTICE_PROGRESS_DB')
    if not path:return False
    if not re.fullmatch(r'(?:R\d{2}BK\d{8}|\d{11}):\d{3}',notice_key):
        raise ValueError('invalid_checkpoint_notice_key')
    record=compact_coverage(result)
    checked=str(result.get('checkedAt') or '')
    if not checked or not record.get('status'):
        raise ValueError('invalid_checkpoint_source_provenance')
    record['lastAttemptAt']=checked
    record['lastAttemptReaderFingerprint']=fingerprint
    value=json.dumps(record,ensure_ascii=False,separators=(',',':'))
    with sqlite3.connect(path,timeout=12) as db:
        db.execute('PRAGMA busy_timeout=12000')
        db.execute('''CREATE TABLE IF NOT EXISTS rfp_notice_checkpoints(
            notice_key TEXT PRIMARY KEY,
            checked_at TEXT NOT NULL,
            evidence_json TEXT NOT NULL)''')
        db.execute('''INSERT INTO rfp_notice_checkpoints(notice_key,checked_at,evidence_json)
            VALUES(?,?,?) ON CONFLICT(notice_key) DO UPDATE SET
            checked_at=excluded.checked_at,evidence_json=excluded.evidence_json
            WHERE excluded.checked_at>=rfp_notice_checkpoints.checked_at''',
            (notice_key,checked,value))
    print('RFP_NOTICE_CHECKPOINT',notice_key,checked,record['status'],flush=True)
    return True


def main():
    # Measure the actual production wall-clock phases per scheduled batch.
    # Final summary is emitted AFTER snapshot save so the parent worker's
    # last-15-lines log captures it without relying on speculative ratios.
    stage_clock=time.perf_counter()
    stage_seconds={}
    def stage_done(label):
        nonlocal stage_clock
        now_clock=time.perf_counter()
        stage_seconds[label]=round(now_clock-stage_clock,4)
        stage_clock=now_clock
    parser=argparse.ArgumentParser()
    parser.add_argument('--limit',type=int,default=14)
    args=parser.parse_args()
    limit=max(1,min(args.limit,240))
    now=dt.datetime.now(dt.timezone.utc)
    old={}
    if DEST.exists():
        try:old=json.loads(DEST.read_text()).get('byNotice',{})
        except (ValueError,OSError):pass
    prior_index={}
    if COVERAGE_DEST.exists():
        try:prior_index=json.loads(COVERAGE_DEST.read_text()).get('byNotice',{})
        except (ValueError,OSError):pass
    # The detailed snapshot wins for equal keys; the index preserves ALL
    # previously scanned keys and prevents a repeat 240-bid treadmill.
    prior={**old,**prior_index}
    targets=changcom_targets()
    manifest_probes=[]
    # One-time operator-selected RFP jobs; no hardcoded ranking of named
    # agencies and no re-download once the requested scan is complete.
    priority={k for k in os.environ.get('WORKLINKS_RFP_ROLE_PRIORITY_KEYS','').split(',')
              if re.fullmatch(r'R\d{2}BK\d{8}:\d{3}',k)}
    dual_scan=os.environ.get('WORKLINKS_RFP_DUAL_SCAN_ONLY')=='1'
    dual_queue=None
    selected_metadata={}
    if dual_scan:
        from rfp_dual_queue import RfpDualQueue
        dual_queue=RfpDualQueue(os.environ['WORKLINKS_RFP_DUAL_QUEUE_DB'])
        dual_queue.recover_stale_scans()
        claims=dual_queue.claim_ready(limit)
        selected=[(key.split(':')[0],key.split(':')[1],closes)
                  for key,closes,_ in claims]
        selected_metadata={key:metadata for key,_,metadata in claims}
        print('RFP_DUAL_SCAN_READY',len(selected),flush=True)
        if not selected:
            print('RFP_DUAL_SCAN_NO_READY',flush=True)
            return
    else:
        selected=discover(limit,prior,targets=targets,manifest_probe_out=manifest_probes,
                          priority=priority)
    # RFP archive retention follows the official closing date, not scan date.
    _NOTICE_DEADLINES.clear()
    _NOTICE_DEADLINES.update({no+':'+order:date for no,order,date in selected if date})
    stage_done('load_and_discover')
    if os.environ.get('WORKLINKS_RFP_UPGRADE_ONLY')=='1':
        print('RFP_UPGRADE_SELECT_COUNT',len(selected),flush=True)
    if os.environ.get('WORKLINKS_RFP_REQUIRE_EXACT_PRIORITY')=='1':
        selected_keys={no+':'+ordn for no,ordn,_ in selected}
        if not priority or selected_keys!=priority or len(selected)!=len(priority):
            print('RFP_EXACT_PRIORITY_SELECTION_FAILED',
                  'expected',sorted(priority),'selected',sorted(selected_keys),flush=True)
            raise SystemExit('RFP_EXACT_PRIORITY_SELECTION_FAILED')
        print('RFP_EXACT_PRIORITY_SELECTED',sorted(selected_keys),flush=True)
    results=dict(old)
    selected_keys={no+':'+order for no,order,_ in selected}
    reader_fingerprint=':'.join(str(n) for n in
        (CLASSIFICATION_VERSION,HWPX_READER_VERSION,
         STAFFING_ROLE_SCAN_VERSION,STAFFING_FACT_SCAN_VERSION))
    # Parse already-stored binaries first; an older record is never re-downloaded
    # just to populate the staffing column.
    # Never hold up each 8-notice live batch to reparse up to 96 OLD
    # attachments. Selected notices are handled by process() itself.
    # An explicit maintenance run may still opt into bounded backfill.
    backfill_limit=max(0,min(96,int(os.environ.get('WORKLINKS_RFP_STAFFING_BACKFILL_FILES','0'))))
    cached_staffing_upgrades=(backfill_cached_staffing(results,max_files=backfill_limit)
                             if backfill_limit else 0)
    if cached_staffing_upgrades:
        print('RFP_CACHED_STAFFING_REPARSED',cached_staffing_upgrades,flush=True)
    stage_done('cached_backfill')
    # Preserve historical evidence while normalizing old ambiguous "unavailable"
    # entries with explicit zero-row API evidence. This is NOT proof that no RFP exists.
    for key,prior in results.items():
        if (prior.get('status')=='text_unavailable' and prior.get('count')==0
                and not prior.get('files')):
            prior['status']='no_eorder_files'
            prior['reasonCode']='eorder_api_returned_zero'
            prior['classificationVersion']=2
    success=0
    failed_refresh={}
    scan_validity={}
    uncached=[]
    if dual_scan:
        uncached=[(no,ordn) for no,ordn,_ in selected]
    for no,ordn,_ in ([] if dual_scan else selected):
        key=no+':'+ordn
        cached=old.get(key)
        cached_source=prior_index.get(key) or cached
        if (not (prior_index.get(key) or {}).get('manifestChangePending') and
                not partial_retry_due(cached_source,now) and
                (reusable_rfp_extraction(cached) or reusable_rfp_extraction(prior_index.get(key))) and
                not staffing_scan_pending(cached_source)):
            print('RFP_REUSE_PREVIOUS_EXTRACTION',key)
            continue
        # A confirmed manifest change is more important than the old 6-hour
        # detail-cache TTL. The previous detail must not block its refresh.
        if cached and not (prior_index.get(key) or {}).get('manifestChangePending'):
            try:
                checked=dt.datetime.fromisoformat(cached.get('checkedAt','').replace('Z','+00:00'))
                if (cached.get('classificationVersion')==CLASSIFICATION_VERSION and
                        not needs_hwpx_reader_retry(cached) and not staffing_scan_pending(cached_source) and
                        checked.tzinfo and (now-checked).total_seconds()<6*3600):
                    print('RFP_CACHE_HIT',key)
                    continue
            except (ValueError,TypeError):pass
        uncached.append((no,ordn))
    # Scan concurrency and download concurrency are independent: four
    # notice parsers consume completed raw bytes from eight download workers.
    preloaded=selected_metadata if dual_scan else preflight_rfp_metadata(uncached)
    stage_done('preflight_metadata')
    file_phase_totals={'downloadSeconds':0.0,'downloadQueueWaitSeconds':0.0,
                       'extractSeconds':0.0,'analysisSeconds':0.0,
                       'textCacheHits':0,'filesProcessed':0,'deferredImageFiles':0}
    download_workers=max(1,min(8,int(os.environ.get(
        'WORKLINKS_RFP_DOWNLOAD_CONCURRENCY','8'))))
    with (nullcontext(None) if dual_scan else DownloadPrefetch(max_workers=download_workers)) as prefetch:
      with ThreadPoolExecutor(max_workers=4) as pool:
        tasks={pool.submit(process,no,ordn,preloaded.get((no,ordn)),
                           old.get(no+':'+ordn) or prior_index.get(no+':'+ordn),
                           prefetch):
               (no,ordn) for no,ordn in uncached}
        for future in as_completed(tasks):
            no,ordn=tasks[future]
            key=no+':'+ordn
            try:
                data=future.result()
                scan_validity[key]=data.get('status')=='text_extracted_requires_review'
                profile=data.pop('_stageTimings',None)
                if profile:
                    for name,value in profile.items():
                        file_phase_totals[name]+=value
                # Record the real per-notice completion time, not the common
                # batch start timestamp shared by all eight notices.
                data['checkedAt']=dt.datetime.now(dt.timezone.utc).isoformat()
                data['classificationVersion']=CLASSIFICATION_VERSION
                data['hwpxReaderVersion']=HWPX_READER_VERSION
                previous=prior_index.get(key) or old.get(key) or {}
                if partial_retry_due(previous,now):
                    data['partialRetryCount']=int(previous.get('partialRetryCount') or 0)+1
                if (reusable_rfp_extraction(old.get(key)) and
                        data['status']!='text_extracted_requires_review'):
                    results[key]=old[key]
                    failed_refresh[key]=data['status']
                    print('RFP_PRIOR_DETAIL_PRESERVED',key,data['status'],flush=True)
                else:
                    results[key]=data
                # Progress becomes visible and durable immediately for THIS
                # notice, even while other futures remain in flight.
                try:
                    publish_notice_checkpoint(key,results[key],reader_fingerprint)
                except (OSError,sqlite3.Error,ValueError) as checkpoint_error:
                    # Never discard a successfully parsed RFP because the
                    # supplementary live-progress DB was temporarily locked.
                    print('RFP_NOTICE_CHECKPOINT_FAILED',key,
                          type(checkpoint_error).__name__,flush=True)
                print('RFP_SCAN',key,data['status'],'FILES',len(data.get('files',[])),flush=True)
                success+=int(data['status']=='text_extracted_requires_review')
            except Exception as e:
                scan_validity[key]=False
                reason=('metadata_http_'+str(e.code) if isinstance(e,urllib.error.HTTPError)
                        else classify_failure(e))
                failed={'status':'metadata_fetch_failed','reasonCode':reason,
                              'source':'나라장터 e발주 첨부파일 API',
                              'sourceError':type(e).__name__+': '+str(e)[:100],
                              'files':[],'reviewComplete':False,
                              'contractPerformanceVerified':False,
                              'checkedAt':now.isoformat(),'classificationVersion':CLASSIFICATION_VERSION,
                              'hwpxReaderVersion':HWPX_READER_VERSION}
                if reusable_rfp_extraction(old.get(key)):
                    results[key]=old[key]
                    failed_refresh[key]='metadata_fetch_failed'
                else:
                    results[key]=failed
                try:
                    publish_notice_checkpoint(key,results[key],reader_fingerprint)
                except (OSError,sqlite3.Error,ValueError) as checkpoint_error:
                    # Never discard a successfully parsed RFP because the
                    # supplementary live-progress DB was temporarily locked.
                    print('RFP_NOTICE_CHECKPOINT_FAILED',key,
                          type(checkpoint_error).__name__,flush=True)
                print('RFP_SCAN_ERROR',key,reason,flush=True)
      prefetch_stats=prefetch.stats() if prefetch is not None else {'workers':0,'submitted':0,'coalesced':0,'networkAttempts':0}
    if not dual_scan:print('RFP_DOWNLOAD_PIPELINE',json.dumps(prefetch_stats,separators=(',',':')),flush=True)
    stage_done('process_notices')
    if not results:raise SystemExit('NO_RFP_RESULT')
    details,omitted=bounded_detail_snapshot(results)
    output={'ok':True,'generatedAt':now.isoformat(),'scope':'공식 공고첨부 텍스트 발췌·키워드 근거(비최종판정)',
            'reviewComplete':False,'detailOmittedFromRollingCache':omitted,
            'byNotice':details}
    DEST.write_text(json.dumps(output,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    stage_done('write_detail_json')
    if DEST.stat().st_size>MAX_PUBLISHED_RFP_BYTES:
        raise SystemExit('RFP_DETAIL_SNAPSHOT_FILE_TOO_LARGE')
    coverage=dict(prior_index)
    # Legacy cumulative rows can retain cited staffing snippets even if their
    # large rolling detail is no longer available. Do not mark the scan complete.
    for key,legacy in coverage.items():
        if not isinstance(legacy,dict) or legacy.get('staffingRoles'):continue
        references=((legacy.get('changcomClauseEvidence') or {})
                    .get('clauseCandidates') or {}).get('staff_proof') or []
        saved=[]
        for ref in references:
            if not isinstance(ref,dict):continue
            quoted={'name':ref.get('sourceFile') or '',
                    'sourceUrl':ref.get('url') or '',
                    'clauseCandidates':[{'sourceText':ref.get('text') or ''}]}
            saved.extend(staffing_from_saved_excerpts(quoted))
        if saved:legacy['staffingRoles']=saved[:24]
        legacy.setdefault('staffingRoleScanComplete',False)
    for key,item in results.items():
        if not isinstance(item,dict):continue
        update=compact_coverage(item)
        prev=coverage.get(key) or {}
        if (not update.get('staffingRoles') and prev.get('staffingRoles') and
                item.get('status')!='text_extracted_requires_review'):
            update['staffingRoles']=prev['staffingRoles']
            update['staffingRoleScanComplete']=False
        if key in selected_keys:
            update['lastAttemptAt']=now.isoformat()
            update['lastAttemptReaderFingerprint']=reader_fingerprint
        elif prev.get('lastAttemptAt'):
            update['lastAttemptAt']=prev['lastAttemptAt']
            if prev.get('lastAttemptReaderFingerprint'):
                update['lastAttemptReaderFingerprint']=prev['lastAttemptReaderFingerprint']
        if key in failed_refresh:
            update['lastAttemptStatus']=failed_refresh[key]
        # Retain the last authenticated manifest and pending-change flag if a
        # fresh download failed or the current metadata endpoints were partial.
        # Probe timestamps are newer than the cached detail's extraction
        # timestamp. Never roll back a completed metadata check on the next run.
        if (str(prev.get('manifestCheckedAt') or '') >
                str(update.get('manifestCheckedAt') or '')):
            update['manifestCheckedAt']=prev['manifestCheckedAt']
        if prev.get('manifestSignature') and not update.get('manifestSignature'):
            update['manifestSignature']=prev['manifestSignature']
        if prev.get('manifestBaselineUnverified') and not update.get('manifestBaselineUnverified'):
            update['manifestBaselineUnverified']=True
        if prev.get('lastManifestProbeStatus') and not update.get('lastManifestProbeStatus'):
            update['lastManifestProbeStatus']=prev['lastManifestProbeStatus']
        # An old, previously successful DETAIL does not prove a subsequently
        # detected manifest change was handled. Clear pending ONLY after a
        # newer, successful scan of the exact changed attachment identity.
        refreshed=(prev.get('manifestChangePending') and
                   item.get('status')=='text_extracted_requires_review' and
                   item.get('manifestSignature')==prev.get('manifestPendingSignature') and
                   str(item.get('checkedAt') or '')>str(prev.get('manifestCheckedAt') or ''))
        if prev.get('manifestChangePending') and not refreshed:
            update['manifestChangePending']=True
            if prev.get('manifestPendingSignature'):
                update['manifestPendingSignature']=prev['manifestPendingSignature']
        elif refreshed:
            update['manifestChangePending']=False
            update.pop('manifestPendingSignature',None)
        # Add bounded primary-source excerpts to the already published cumulative
        # index, rather than the rolling 240-document detail snapshot.
        if key in targets and item.get('status')=='text_extracted_requires_review':
            update['changcomClauseEvidence']=compact_changcom_evidence(item)
        elif prev.get('changcomClauseEvidence'):
            update['changcomClauseEvidence']=prev['changcomClauseEvidence']
        if str(update.get('checkedAt') or '')>=str(prev.get('checkedAt') or ''):
            if (prev.get('status')=='text_extracted_requires_review' and
                    update.get('status')!='text_extracted_requires_review'):
                update['lastAttemptStatus']=update['status']
                update['status']=prev['status']
                if prev.get('files'):
                    update['files']=prev['files']
            coverage[key]=update
    # When an old file already passed the role parser, update only the derived
    # completion/role summary. No additional file downloads or government calls.
    # The revision also drops previously misidentified general scoring examples.
    for key,item in coverage.items():
        if not isinstance(item,dict):continue
        files=item.get('files') or []
        if not files:continue
        for f in files:
            if staffing_ancillary_form_without_extractable_text(f):
                f['staffingScopeExcluded']=True
                f['staffingScopeReason']=(
                    '입찰신청·서약 제출용 서식의 텍스트 미추출 '
                    '(인력 판독 범위에서만 제외, 전체 문서 오류 유지)')
        complete=(item.get('manifestComplete') is True and
                  all(staffing_effective_file_complete(f,files) for f in files))
        if item.get('staffingRoleScanComplete') is not complete:
            item['staffingRoleScanComplete']=complete
        rows=item.get('staffingRoles') or []
        filtered=[row for row in rows if not staffing_source_is_general_example(
            row.get('sourceFile') if isinstance(row,dict) else '',
            row.get('sourceText') if isinstance(row,dict) else '')]
        if len(filtered)!=len(rows):item['staffingRoles']=filtered

    # Re-probe only a small rotating batch of already-extracted, open bids.
    # The metadata fetch does not download any PDF/HWPX bytes.
    for _,no,ordn in sorted(manifest_probes,key=lambda x:x[0])[:MAX_MANIFEST_PROBES_PER_RUN]:
        key=no+':'+ordn
        previous=coverage.get(key) or prior.get(key) or {}
        try:
            meta=fetch_json(BASE+'bid-evidence?'+urllib.parse.urlencode(
                {'bidNo':no,'order':ordn}))
            fields,verdict=inspect_manifest_probe(meta,previous,now.isoformat())
        except Exception as error:
            fields={'manifestCheckedAt':now.isoformat(),
                    'lastManifestProbeStatus':'fetch_failed'}
            verdict='fetch_failed_'+type(error).__name__
        coverage[key]={**previous,**fields}
        print('RFP_MANIFEST_PROBE',key,verdict,flush=True)
    cumulative={'ok':True,'generatedAt':now.isoformat(),
       'scope':'누적 공식 RFP 다운로드·텍스트 스캔 이력(적격 판정 아님)',
       'reviewComplete':False,'scannedNoticeCount':len(coverage),
       'byNotice':coverage}
    COVERAGE_DEST.write_text(json.dumps(cumulative,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    if dual_scan:
        # The parent worker commits final queue statuses only AFTER publishing
        # both validated RFP snapshots, so a crash cannot lose scan evidence.
        scan_outcomes=[{'key':no+':'+ordn,
                        'ok':scan_validity.get(no+':'+ordn) is True}
                       for no,ordn in uncached]
        print('RFP_DUAL_SCAN_RESULT',json.dumps(scan_outcomes,separators=(',',':')),flush=True)
    stage_done('rebuild_and_write_coverage')
    print('RFP_SNAPSHOT_READY','DETAIL_RECORDS',len(output['byNotice']),
          'CUMULATIVE_SCANNED',len(coverage),'NEW_READABLE',success)
    print('RFP_BATCH_TIMING',json.dumps({
        'selected':len(selected),'actualProcess':len(uncached),
        'existingBackfill':cached_staffing_upgrades,
        'filePhaseTotals':{k:round(v,4) if isinstance(v,float) else v
                           for k,v in file_phase_totals.items()},
        'phaseSeconds':stage_seconds,
        'totalSeconds':round(sum(stage_seconds.values()),4)},
        separators=(',',':')),flush=True)
if __name__=='__main__':main()
