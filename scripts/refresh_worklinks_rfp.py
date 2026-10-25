#!/usr/bin/env python3
"""Incrementally extract LIMITED qualification excerpts from public G2B RFPs.
Never classify final bid eligibility from a keyword or omit review of attachments.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime as dt
import hashlib
import io
import json
import os
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

BASE='https://api-suaveforge.suaveforge.com:18458/api/g2b/'
ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'startup-support/rfp-clauses.json'
COVERAGE_DEST=ROOT/'startup-support/rfp-coverage-index.json'
CHANGCOM_SOURCE=ROOT/'startup-support/changcom-actionable.json'
CHANGCOM_EVIDENCE_DEST=ROOT/'startup-support/changcom-rfp-evidence.json'
MAX_FILE=12_000_000
MAX_DOCUMENTS=24
# Per-member AND total XML caps are needed for safe HWPX decompression.
# 3MB per member was rejecting real official documents before text extraction.
MAX_HWPX_XML_MEMBER=10_000_000
MAX_HWPX_XML_TOTAL=45_000_000
HWPX_READER_VERSION=2
PARTNER_VERIFIED_CODES={'1426','1468','1469','1470'}
TEXT_FORMATS=('.hwp','.hwpx','.pdf','.docx','.xlsx','.pptx','.zip')
CLASSIFICATION_VERSION=22
EXTRA_QUALIFICATION_ANCHORS=re.compile(
    r'입찰\s*참가\s*(?:자격|요건|등록|가능|할\s*수)|참가\s*자격|업종\s*코드|소프트웨어사업자|직접\s*생산|'
    r'중소기업\s*확인|중소기업자|중소기업\s*(?:만|에\s*한정|이어야|이하)|'
    r'(?<!중)소기업|소상공인|지역\s*제한|본점\s*소재|'
    r'수행\s*실적|실적\s*증명|재직\s*증명|공동\s*수급|분담\s*이행|'
    r'하도급|기술\s*인력|등록\s*업체|정보통신공사업|제안\s*자격|'
    r'조세\s*포탈|제\s*8조의\s*2|특별법인|입찰보증금|'
    r'입찰참가자격등록증상|입찰참가자격의\s*판단기준일|입찰업체\s*서약서', re.I)

# Priority is derived from *all* live indexed bids. No pinned notice IDs.
SIGNALS={
 '입찰참가자격':r'입찰\s*참가\s*자격|참가\s*자격',
 '직접생산':r'직접\s*생산|세부품명번호',
 '중소기업':r'중소기업\s*확인|소기업|소상공인',
 '수행실적':r'수행\s*실적|유사\s*용역\s*실적|실적\s*증명',
 '기술인력':r'투입\s*인력|기술\s*인력|상주\s*인력|자격증',
 '지역제한':r'지역\s*제한|본점\s*소재|소재지',
 '공동수급':r'공동\s*수급|분담\s*이행|하도급'
}
AGENTS={'User-Agent':'WorkLinks-RFP-ReadOnly/1.0','Accept':'application/json'}
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,request,fp,code,msg,headers,newurl):
        raise ValueError('redirect_forbidden')

OPENER=urllib.request.build_opener(NoRedirect)
def fetch_json(url):
    # The evidence API occasionally responds 503 during parallel scans. Retry
    # only transient transport failures; never reinterpret a failed fetch as
    # confirmation that a tender has no official attachments.
    request=urllib.request.Request(url,headers=AGENTS)
    for attempt in range(4):
        try:
            with OPENER.open(request,timeout=24) as r:
                data=r.read(2_000_000)
                if len(data)>=2_000_000:raise ValueError('oversize_json')
                return json.loads(data.decode('utf-8'))
        except urllib.error.HTTPError as ex:
            if ex.code not in (429,500,502,503,504) or attempt==3:raise
        except (TimeoutError,ConnectionError,urllib.error.URLError):
            if attempt==3:raise
        time.sleep(min(8,1.5*(2**attempt)))
def needs_hwpx_reader_retry(record):
    if (record or {}).get('hwpxReaderVersion',0)>=HWPX_READER_VERSION:
        return False
    return any(f.get('errorCategory')=='large_xml_section' and
               (Path(f.get('name') or '').suffix.lower() in ('.hwpx',''))
               for f in (record or {}).get('files') or [])

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

# Only attachment METADATA is periodically compared. Unchanged documents
# never need to be downloaded. Same-order binary changes with identical
# metadata cannot be proven without a separate, explicit hash audit.
MAX_MANIFEST_PROBES_PER_RUN=8
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
    if not record.get('manifestSignature'):return True
    try:
        checked=dt.datetime.fromisoformat(
            str(record.get('manifestCheckedAt') or record.get('checkedAt') or '').replace('Z','+00:00'))
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

def discover(limit,prior=None,targets=None,manifest_probe_out=None):
    """Visit ALL indexed SW bids; retain past scan timestamps to rotate fairly.

    The file snapshot only contains recent detailed snippets, while the
    coverage index records previously scanned official documents. Neither is
    a final bidder qualification. Expired or unclassified bids are NOT
    classified as ineligible merely because they are lower scan priority.
    """
    prior=prior or {}
    targets=changcom_targets() if targets is None else targets
    seen={}
    tz=dt.timezone(dt.timedelta(hours=9))
    today=dt.datetime.now(tz).date()
    utc=dt.datetime.now(dt.timezone.utc)
    try:
        for offset in range(0,100000,500):
            data=fetch_json(BASE+'saved?sw=1&limit=500&offset='+str(offset))
            if not data.get('ok'):
                print('RFP_DISCOVER_SERVER_ERROR',data.get('error','unknown'))
                break
            total=int(data.get('totalCount') or 0)
            rows=data.get('items') or []
            for item in rows:
                no=str(item.get('bidNo') or '')
                if not re.fullmatch(r'(?:R\d{2}BK\d{8}|\d{11})',no):continue
                order=str(item.get('order') or '0').zfill(3)
                end=datestr(item.get('closes'))
                date=dt.datetime.strptime(end,'%Y%m%d').date() if end else None
                key=no+':'+order
                cached=prior.get(key) or {}
                retry=needs_hwpx_reader_retry(cached)
                if cached.get('reviewComplete') is True:continue
                if reusable_rfp_extraction(cached):
                    if (manifest_probe_out is not None and date and date>=today and
                            manifest_probe_due(cached,utc)):
                        last=str(cached.get('manifestCheckedAt') or cached.get('checkedAt') or '')
                        rank=(0 if key in targets else 1,
                              0 if not cached.get('manifestSignature') else 1,
                              last,date,key)
                        manifest_probe_out.append((rank,no,order))
                    continue
                if (cached.get('classificationVersion')==CLASSIFICATION_VERSION and not retry
                        and not cached.get('manifestChangePending')):
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
                # Urgent, unreviewed and official-license-matched bids first.
                # Do not confuse a lack of matching metadata with a rejection.
                temporal=0 if date and date>=today else 1 if date is None else 2
                novel=0 if not cached or cached.get('manifestChangePending') else 1
                rank=(0 if key in targets and temporal==0 else 1 if temporal==0 else
                      2 if key in targets else 3,
                      novel,0 if retry else 1,
                      0 if matching else 1,
                      date if date is not None and date>=today else today+dt.timedelta(days=3650),
                      0 if item.get('kind')=='servc' else 1,key)
                seen[key]=(rank,no,order,date.isoformat() if date else '')
            if not rows or offset+len(rows)>=total:break
        else:
            print('RFP_DISCOVER_PAGINATION_LIMIT_REACHED','offset_limit',100000)
    except Exception as error:
        print('SAVED_NOTICE_DISCOVERY_UNAVAILABLE',type(error).__name__,str(error)[:140])
    # Old parser versions still get retried after all currently open/unread
    # notices; they never displace an urgent live bidder's first source scan.
    for key,cached in prior.items():
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
def classify_failure(error):
    if isinstance(error,urllib.error.HTTPError):
        return 'file_download_http_'+str(error.code)
    if isinstance(error,(TimeoutError,ConnectionError,urllib.error.URLError)):
        return 'file_download_connection_error'
    detail=str(error)
    known=('large_file','invalid_hwp','hwp5txt_failed','archive_many_xml_files',
           'pdf_over_100_pages','pdf_over_page_limit','pdf_unreadable_page','no_searchable_text','unsupported_format',
           'redirect_forbidden','oversize_json','egg_archive_requires_converter',
           'nested_archive_requires_review','unknown_archive_member_requires_review',
           'archive_no_searchable_documents','unsafe_archive_path','large_xml_section')
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


def download(url):
    request=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Referer':'https://www.g2b.go.kr/'})
    for attempt in range(3):
        try:
            with OPENER.open(request,timeout=35) as r:
                size=int(r.headers.get('Content-Length') or '0')
                if size>MAX_FILE:raise ValueError('large_file')
                raw=r.read(MAX_FILE+1)
                if len(raw)>MAX_FILE:raise ValueError('large_file')
                return raw
        except urllib.error.HTTPError as ex:
            if ex.code not in (429,500,502,503,504) or attempt==2:raise
        except (TimeoutError,ConnectionError,urllib.error.URLError):
            if attempt==2:raise
        time.sleep(1.5*(attempt+1))
def extract(name,raw):
    n=name.lower()
    # Official downloads occasionally have no extension; inspect bounded
    # file signatures instead of falsely treating them as unreadable.
    if not n.endswith(TEXT_FORMATS):
        if raw.startswith(b'%PDF-'):n+='.pdf'
        elif raw.startswith(bytes.fromhex('D0CF11E0A1B11AE1')):n+='.hwp'
        elif raw.startswith(b'PK\x03\x04'):
            with zipfile.ZipFile(io.BytesIO(raw)) as probe:
                members=set(probe.namelist())
            n+=('.docx' if 'word/document.xml' in members else
                '.xlsx' if 'xl/workbook.xml' in members else
                '.pptx' if 'ppt/presentation.xml' in members else
                '.hwpx' if any(x.startswith('Contents/') and x.endswith('.xml') for x in members)
                else '.zip')
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
                if suffix in {'.pdf','.hwp','.hwpx','.docx','.xlsx','.pptx'}:
                    if entry.file_size>MAX_FILE:raise ValueError('large_file')
                    value=extract(Path(inner).name,archive.read(entry))
                    if not value.strip():raise ValueError('no_searchable_text')
                    parts.append('FILE '+inner+'\n'+value)
                elif suffix in {'.zip','.egg','.7z','.rar'}:
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
        from pypdf import PdfReader
        pdf=PdfReader(io.BytesIO(raw))
        if len(pdf.pages)>220:raise ValueError('pdf_over_page_limit')
        pages=[page.extract_text() or '' for page in pdf.pages]
        if any(not p.strip() for p in pages):raise ValueError('pdf_unreadable_page')
        return '\n'.join(pages)
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
      'staff_proof':r'재직.{0,12}경력|경력.{0,12}학력|자격.?증명서|투입\s*인력',
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


def process(no,ordn):
    data=fetch_json(BASE+'bid-evidence?'+urllib.parse.urlencode({'bidNo':no,'order':ordn}))
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
    manifest=docs.get('items') or []
    for item in manifest[:MAX_DOCUMENTS]:
        public=legal_file(item)
        if not public:
            saved.append({'name':str(item.get('name') or '')[:160],'readable':False,
                          'errorCategory':invalid_file_reason(item)})
            continue
        name,url=public
        record={'name':name,'sourceUrl':url,'readable':False}
        try:
            raw=download(url)
            content=normalize_extracted_text(extract(name,raw))
            if len(content.strip())<(30 if name.lower().endswith(('.xlsx','.pptx')) else 100):
                raise ValueError('no_searchable_text')
            triggers,snippets=parse_clauses(content)
            candidate_rules=extract_rule_candidates(content,name)
            scan=preserve_unclassified_qualification(content,name,candidate_rules)
            record.update({'readable':True,'textChars':len(content),
                           **scan,
                           'sourceSha256':hashlib.sha256(raw).hexdigest(),
                           'textSha256':hashlib.sha256(content.encode('utf-8')).hexdigest(),
                           'qualificationScanTruncated':len(content)>350_000,
                           'clauseCandidatesTruncated':False,
                           'topics':triggers,'snippets':snippets,
                           'clauseCandidates':candidate_rules,
                           'fullReviewPending':True})
        except Exception as ex:
            record['errorCategory']=classify_failure(ex)
            record['error']=type(ex).__name__+': '+str(ex)[:90]
        saved.append(record)
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
            'manifestChangePending':False}
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
        'reviewComplete':False,
        'attachmentManifestCount':item.get('attachmentManifestCount'),
        'readableDocumentCount':item.get('readableDocumentCount',0),
        'unreadableDocumentCount':item.get('unreadableDocumentCount',0),
        'files':[{
            'name':str(f.get('name') or '')[:160],
            'readable':f.get('readable') is True,
            'sourceSha256':str(f.get('sourceSha256') or '')[:64],
            'errorCategory':str(f.get('errorCategory') or '')[:60],
            'sourceTextScanComplete':f.get('sourceTextScanComplete') is True,
            'unmatchedQualificationAnchorCount':f.get('unmatchedQualificationAnchorCount',0),
            'clauseCandidateCount':len(f.get('clauseCandidates') or [])
        } for f in (item.get('files') or [])[:MAX_DOCUMENTS]]
    }
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
    ordered=sorted(records.items(), key=lambda pair: str(
        (pair[1] if isinstance(pair[1],dict) else {}).get('checkedAt') or ''),
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


def main():
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
    selected=discover(limit,prior,targets=targets,manifest_probe_out=manifest_probes)
    results=dict(old)
    # Preserve historical evidence while normalizing old ambiguous "unavailable"
    # entries with explicit zero-row API evidence. This is NOT proof that no RFP exists.
    for key,prior in results.items():
        if (prior.get('status')=='text_unavailable' and prior.get('count')==0
                and not prior.get('files')):
            prior['status']='no_eorder_files'
            prior['reasonCode']='eorder_api_returned_zero'
            prior['classificationVersion']=2
    success=0
    uncached=[]
    for no,ordn,_ in selected:
        key=no+':'+ordn
        cached=old.get(key)
        if (not (prior_index.get(key) or {}).get('manifestChangePending') and
                (reusable_rfp_extraction(cached) or reusable_rfp_extraction(prior_index.get(key)))):
            print('RFP_REUSE_PREVIOUS_EXTRACTION',key)
            continue
        if cached:
            try:
                checked=dt.datetime.fromisoformat(cached.get('checkedAt','').replace('Z','+00:00'))
                if (cached.get('classificationVersion')==CLASSIFICATION_VERSION and
                        not needs_hwpx_reader_retry(cached) and checked.tzinfo and
                        (now-checked).total_seconds()<6*3600):
                    print('RFP_CACHE_HIT',key)
                    continue
            except (ValueError,TypeError):pass
        uncached.append((no,ordn))
    # Official requests are bounded; four independent notices run concurrently
    # so one unavailable PDF does not starve the entire 16-minute job.
    with ThreadPoolExecutor(max_workers=4) as pool:
        tasks={pool.submit(process,no,ordn):(no,ordn) for no,ordn in uncached}
        for future in as_completed(tasks):
            no,ordn=tasks[future]
            key=no+':'+ordn
            try:
                data=future.result()
                data['checkedAt']=now.isoformat()
                data['classificationVersion']=CLASSIFICATION_VERSION
                data['hwpxReaderVersion']=HWPX_READER_VERSION
                results[key]=data
                print('RFP_SCAN',key,data['status'],'FILES',len(data.get('files',[])),flush=True)
                success+=int(data['status']=='text_extracted_requires_review')
            except Exception as e:
                reason=('metadata_http_'+str(e.code) if isinstance(e,urllib.error.HTTPError)
                        else classify_failure(e))
                results[key]={'status':'metadata_fetch_failed','reasonCode':reason,
                              'source':'나라장터 e발주 첨부파일 API',
                              'sourceError':type(e).__name__+': '+str(e)[:100],
                              'files':[],'reviewComplete':False,
                              'contractPerformanceVerified':False,
                              'checkedAt':now.isoformat(),'classificationVersion':CLASSIFICATION_VERSION,
                              'hwpxReaderVersion':HWPX_READER_VERSION}
                print('RFP_SCAN_ERROR',key,reason,flush=True)
    if not results:raise SystemExit('NO_RFP_RESULT')
    details,omitted=bounded_detail_snapshot(results)
    output={'ok':True,'generatedAt':now.isoformat(),'scope':'공식 공고첨부 텍스트 발췌·키워드 근거(비최종판정)',
            'reviewComplete':False,'detailOmittedFromRollingCache':omitted,
            'byNotice':details}
    DEST.write_text(json.dumps(output,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    if DEST.stat().st_size>MAX_PUBLISHED_RFP_BYTES:
        raise SystemExit('RFP_DETAIL_SNAPSHOT_FILE_TOO_LARGE')
    coverage=dict(prior_index)
    for key,item in results.items():
        if not isinstance(item,dict):continue
        update=compact_coverage(item)
        prev=coverage.get(key) or {}
        # Retain the last authenticated manifest and pending-change flag if a
        # fresh download failed or the current metadata endpoints were partial.
        if prev.get('manifestSignature') and not update.get('manifestSignature'):
            update['manifestSignature']=prev['manifestSignature']
        if prev.get('manifestCheckedAt') and not update.get('manifestCheckedAt'):
            update['manifestCheckedAt']=prev['manifestCheckedAt']
        if prev.get('manifestChangePending') and not (
                item.get('status')=='text_extracted_requires_review' and
                item.get('manifestSignature')):
            update['manifestChangePending']=True
            if prev.get('manifestPendingSignature'):
                update['manifestPendingSignature']=prev['manifestPendingSignature']
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
    COVERAGE_DEST.write_text(json.dumps(cumulative,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('RFP_SNAPSHOT_READY','DETAIL_RECORDS',len(output['byNotice']),
          'CUMULATIVE_SCANNED',len(coverage),'NEW_READABLE',success)
if __name__=='__main__':main()
