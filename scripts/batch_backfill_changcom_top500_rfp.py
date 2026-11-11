#!/usr/bin/env python3
"""One-shot, measurable G2B batch metadata + official document extraction.

A date-window download of public metadata is NOT an RFP document download.
Never claim all documents are read just because API pagination completed.
Preserve previous scan evidence and checkpoint each new result.

Run only with explicit --execute; otherwise no upstream HTTP occurs.
"""
import argparse
import collections
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime as dt
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
import urllib.error

from refresh_worklinks_rfp import (
    process, compact_coverage, compact_changcom_evidence,
    bounded_detail_snapshot, CLASSIFICATION_VERSION, HWPX_READER_VERSION,
    reusable_rfp_extraction
)

KST=dt.timezone(dt.timedelta(hours=9))
API='https://apis.data.go.kr/1230000/ad/BidPublicInfoService02/'
OPS=[
    ('ordinary','getBidPblancListInfoAtchFileInfo02'),
    ('eorder','getBidPblancListInfoEorderAtchFileInfo02'),
    ('detail','getBidPblancListInfoServc02')
]
PAGE_SIZE=999
WINDOWS=[('20261026','20261030'),('20261102','20261107'),('20261109','20261110')]
def load(p,default=None):
    path=Path(p)
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else default

def atomic_json(path,data):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.pending.'+str(os.getpid()))
    tmp.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    os.replace(tmp,path)

def key_for(b):
    return str(b.get('bidNo') or b.get('bidNtceNo') or '')+':'+str(b.get('order') or b.get('bidNtceOrd') or '0').zfill(3)

def close_of(b):
    try:
        when=dt.datetime.fromisoformat(str(b.get('closes') or '').replace('Z','+00:00'))
        return when if when.tzinfo else when.replace(tzinfo=KST)
    except ValueError:return None

def posted_date(con,notice):
    no,order=notice.split(':',1)
    row=con.execute("""SELECT payload FROM bid_notices WHERE kind='servc'
        AND bid_no=? AND printf('%03d',CAST(bid_ord AS INTEGER))=?
        ORDER BY last_seen DESC LIMIT 1""",(no,order)).fetchone()
    if not row: return None
    try: data=json.loads(row[0])
    except ValueError:return None
    raw=str(data.get('posted') or '')
    match=re.search(r'20\d{2}[-./]?\d{2}[-./]?\d{2}',raw)
    if not match:return None
    try:return dt.datetime.strptime(re.sub(r'\D','',match.group()),'%Y%m%d').date()
    except ValueError:return None

def select(data):
    now=dt.datetime.now(KST)
    action=load(data/'snapshots/changcom-actionable.json') or {}
    existing=load(data/'snapshots/rfp-coverage-index.json') or {}
    assert action.get('ok') is True and action.get('bizno')=='1308185973','WRONG_ACTIONABLE_SOURCE'
    ranked=[x for x in action.get('bids',[]) if
            x.get('deadlineState')!='unknown' and
            close_of(x) and close_of(x)-now>=dt.timedelta(hours=24)]
    top=ranked[:500]
    if len(top)!=500:raise RuntimeError('TOP500_SHORTLIST_UNAVAILABLE '+str(len(top)))
    covered=existing.get('byNotice') or {}
    target=[x for x in top if (covered.get(key_for(x)) or {}).get('status') in (None,'not_scanned')]
    con=sqlite3.connect('file:'+str(data/'bids.sqlite3')+'?mode=ro',uri=True)
    dated={}
    for item in target:
        ident=key_for(item)
        day=posted_date(con,ident)
        if not day:raise RuntimeError('MISSING_POSTED_DATE '+ident)
        ds=day.strftime('%Y%m%d')
        if not any(start<=ds<=end for start,end in WINDOWS):
            raise RuntimeError('DATE_OUTSIDE_VERIFIED_WINDOWS '+ident+' '+ds)
        dated[ident]=ds
    con.close()
    return top,target,dated

def secret(path):
    for line in Path(path).read_text().splitlines():
        if line.startswith('G2B_SERVICE_KEY='):
            k=line.split('=',1)[1].strip().strip('"').strip("'")
            if k:return k
    raise RuntimeError('G2B_SERVICE_KEY_MISSING')

class Provider:
    def __init__(self,key):
        self.key=key
        self.calls=0
        self.failed=0
        self.rows=collections.Counter()
        self.pages={}
    def request(self,op,start,end,page):
        params={'serviceKey':self.key,'type':'json','pageNo':page,'numOfRows':PAGE_SIZE,
                'inqryDiv':1,'inqryBgnDt':start+'0000','inqryEndDt':end+'2359'}
        if op=='ordinary':params['bsnsDivCd']=5
        url=API+dict(OPS)[op]+'?'+urllib.parse.urlencode(params)
        error=None
        for attempt in range(3):
            self.calls+=1
            try:
                req=urllib.request.Request(url,headers={
                    'Accept':'application/json','User-Agent':'WorkLinks-Top500-Batch/20261111'})
                with urllib.request.urlopen(req,timeout=30) as response:
                    raw=response.read(20_000_000)
                    if len(raw)>=20_000_000:raise RuntimeError('RESPONSE_TOO_LARGE')
                root=json.loads(raw.decode('utf-8'))
                h=(root.get('response') or {}).get('header') or {}
                b=(root.get('response') or {}).get('body') or {}
                code=str(h.get('resultCode') or '')
                if code not in ('00','0'):
                    raise RuntimeError('PROVIDER_RESULT_CODE_'+code)
                total=int(b.get('totalCount') or 0)
                items=b.get('items') or []
                if isinstance(items,dict): items=items.get('item') or []
                if isinstance(items,dict): items=[items]
                if not isinstance(items,list):raise RuntimeError('UNEXPECTED_ITEMS_TYPE')
                if total>PAGE_SIZE*300:raise RuntimeError('PAGINATION_SIZE_GUARD')
                return total,items
            except (urllib.error.HTTPError,urllib.error.URLError,TimeoutError,RuntimeError,ValueError) as exc:
                error=exc
                typ=str(exc)
                if 'PROVIDER_RESULT_CODE_22' in typ or 'PROVIDER_RESULT_CODE_23' in typ:
                    break
                if isinstance(exc,urllib.error.HTTPError) and exc.code not in (429,500,502,503,504):
                    break
                if attempt<2:time.sleep(1.4*(attempt+1))
        self.failed+=1
        raise RuntimeError('OFFICIAL_BATCH_API_FAILED '+op+' '+start+'-'+end+
                           ' page='+str(page)+' '+type(error).__name__+':'+str(error)[:120])
    def gather(self,op,window,needed):
        start,end=window
        first_total,first=self.request(op,start,end,1)
        expected=math.ceil(first_total/PAGE_SIZE) if first_total else 0
        if first_total and len(first)==0:raise RuntimeError('EMPTY_FIRST_PAGE_NONZERO')
        got=0
        result=collections.defaultdict(list)
        def store(rows):
            nonlocal got
            got+=len(rows)
            for row in rows:
                if not isinstance(row,dict):continue
                identity=key_for(row)
                if identity in needed and start<=needed[identity]<=end:
                    result[identity].append(row)
        store(first)
        for page in range(2,expected+1):
            time.sleep(.32)
            total,rows=self.request(op,start,end,page)
            if total!=first_total:
                raise RuntimeError('PAGINATION_TOTAL_MOVED '+op+' '+start)
            if not rows:raise RuntimeError('EMPTY_INTERMEDIATE_PAGE '+op+' '+start)
            store(rows)
        if got!=first_total:
            raise RuntimeError('PAGINATION_ROW_COUNT_MISMATCH '+op+' '+start+
                               ' expected='+str(first_total)+' got='+str(got))
        self.pages[op+'_'+start]={'pages':max(1,expected),'totalRows':first_total,
                                   'targetNoticeHits':len(result)}
        self.rows[op]+=got
        print('BATCH_SOURCE_COMPLETE',op,start,end,'PAGES',max(1,expected),
              'ROWS',got,'TARGET_NOTICE_HITS',len(result),flush=True)
        return result

def normalize(meta,day,now):
    ordinary=meta['ordinary']
    eorder=meta['eorder']
    detail=meta['detail']
    docs=[];seen=set()
    def add(name,url,source):
        url=str(url or '').strip()
        name=str(name or '')[:160]
        if not name and not url:return
        if url and url in seen:return
        if url:seen.add(url)
        docs.append({'name':name,'url':url,'source':source})
    for row in ordinary:
        add(row.get('atchFileNm') or row.get('fileNm'),
            row.get('atchFileUrl') or row.get('fileUrl'),'notice_attachment_api')
    for row in eorder:
        add(row.get('atchFileNm') or row.get('eorderAtchFileNm'),
            row.get('atchFileUrl') or row.get('eorderAtchFileUrl'),'eorder')
    for row in detail:
        for i in range(1,11):
            add(row.get('ntceSpecFileNm'+str(i)),
                row.get('ntceSpecDocUrl'+str(i)),'notice_detail')
    # A successful page scan establishes that no more rows exist in that date
    # window; a missing notice detail cannot establish this specific bid's
    # attachments are absent, hence no negative finding without a matched row.
    anchored=bool(detail or ordinary or eorder)
    confirmed=anchored
    return {'ok':confirmed,'attachments':{
      'ok':confirmed,'complete':confirmed,'count':len(docs),
      'items':docs,'generalCount':len(ordinary),
      'eorderCount':len(eorder),
      'noticeDetailDocumentCount':len(detail),
      'error':'' if confirmed else 'notice_not_present_in_complete_date_window'},
      'noticeDocuments':{
       'ok':bool(detail),'complete':bool(detail),
       'noticeRows':len(detail),'items':[],
       'error':'' if detail else 'notice_detail_row_absent_in_date_window'},
      'checkedAt':now,'source':'batch_window_official_a02',
      'windowDate':day}

def merge_coverage(data,scans,now):
    index_path=data/'snapshots/rfp-coverage-index.json'
    detail_path=data/'snapshots/rfp-clauses.json'
    current=load(index_path) or {'ok':True,'byNotice':{}}
    by=dict(current.get('byNotice') or {})
    for key,item in scans.items():
        previous=by.get(key) or {}
        if previous.get('status')=='text_extracted_requires_review' and (
            item.get('status')!='text_extracted_requires_review'):
            continue
        if str(previous.get('checkedAt') or '')>str(item.get('checkedAt') or ''):
            continue
        compact=compact_coverage(item)
        if item.get('status')=='text_extracted_requires_review':
            compact['changcomClauseEvidence']=compact_changcom_evidence(item)
        elif previous.get('changcomClauseEvidence'):
            compact['changcomClauseEvidence']=previous['changcomClauseEvidence']
        by[key]=compact
    current.update({'ok':True,'generatedAt':now,'reviewComplete':False,
                   'scannedNoticeCount':len(by),'byNotice':by})
    atomic_json(index_path,current)
    # Existing detailed text is a 240-notice rolling view; full scans in a
    # distinct batch detail checkpoint cannot be lost when rolling drops them.
    prior=load(detail_path) or {'ok':True,'byNotice':{}}
    combined=dict(prior.get('byNotice') or {})
    for key,item in scans.items():
        old=combined.get(key) or {}
        if old.get('status')=='text_extracted_requires_review' and (
            item.get('status')!='text_extracted_requires_review'):
            continue
        combined[key]=item
    bounded,omitted=bounded_detail_snapshot(combined)
    prior.update({'ok':True,'generatedAt':now,
                  'reviewComplete':False,'detailOmittedFromRollingCache':omitted,
                  'byNotice':bounded})
    atomic_json(detail_path,prior)
    return len(by),len(bounded),omitted

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data-dir',default='/data')
    parser.add_argument('--secret',default='/run/secrets/g2b.env')
    parser.add_argument('--workers',type=int,default=5)
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    data=Path(args.data_dir)
    top,target,dated=select(data)
    print('TARGET_FROZEN',json.dumps({
       'asOfKST':dt.datetime.now(KST).isoformat(timespec='seconds'),
       'top500':len(top),'newlyMissing':len(target),
       'first':key_for(top[0]),'last':key_for(top[-1])},separators=(',',':')),flush=True)
    if not args.execute:return
    now=dt.datetime.now(dt.timezone.utc).isoformat()
    state_path=data/'snapshots/rfp-top500-batch-state-20261111.json'
    existing=load(state_path) or {}
    saved_scans=existing.get('scans') or {}
    remaining=[b for b in target if not reusable_rfp_extraction(saved_scans.get(key_for(b)))]
    needed={key_for(b):dated[key_for(b)] for b in remaining}
    provider=Provider(secret(args.secret))
    grouped={key:{k:[] for k,_ in OPS} for key in needed}
    for op,_ in OPS:
        for window in WINDOWS:
            subset={key:date for key,date in needed.items() if window[0]<=date<=window[1]}
            if not subset:continue
            hits=provider.gather(op,window,subset)
            for key,rows in hits.items():
                grouped[key][op].extend(rows)
            time.sleep(.45)
    metadata={}
    by_source=collections.Counter()
    for key,group in grouped.items():
        for op,rows in group.items():
            if rows:by_source[op]+=1
        metadata[key]=normalize(group,dated[key],now)
    print('BATCH_METADATA_FINISHED',json.dumps({
       'officialCalls':provider.calls,'failedCalls':provider.failed,
       'totalPages':provider.pages,'targets':len(needed),
       'targetNoticeHitsBySource':dict(by_source),
       'withAnyOfficialRow':sum(int(v['ok']) for v in metadata.values()),
       'withDocumentUrls':sum(int(bool(v['attachments']['items'])) for v in metadata.values())
    },ensure_ascii=False,separators=(',',':')),flush=True)
    atomic_json(data/'snapshots/rfp-top500-batch-metadata-20261111.json',{
       'ok':True,'generatedAt':now,'officialCalls':provider.calls,
       'sourcePages':provider.pages,'targets':list(needed),'byNotice':metadata})
    # Never rescan an authenticated prior full extraction. Failure and no-URL
    # cases remain visibly distinguishable from an actual parsed RFP.
    scans=dict(saved_scans)
    checkpoint=0
    max_workers=max(1,min(8,args.workers))
    def analyze(key):
        meta=metadata[key]
        if not meta.get('ok'):
            return {'status':'metadata_not_confirmed',
                    'reasonCode':'batch_window_no_matching_notice_row','files':[],
                    'reviewComplete':False,'readableDocumentCount':0,'unreadableDocumentCount':0}
        if not meta['noticeDocuments']['ok']:
            # The notice has attachment rows, but no match in notice-detail:
            # don't report complete manifest or official absence.
            return {'status':'metadata_not_confirmed',
                    'reasonCode':'batch_notice_detail_unmatched','files':[],
                    'reviewComplete':False,'readableDocumentCount':0,
                    'unreadableDocumentCount':0}
        no,ordn=key.split(':')
        return process(no,ordn,metadata=meta,previous=saved_scans.get(key))
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures={pool.submit(analyze,key):key for key in needed}
        for future in as_completed(futures):
            key=futures[future]
            try:item=future.result()
            except Exception as e:
                item={'status':'file_scan_failed','reasonCode':type(e).__name__,
                      'sourceError':str(e)[:140],'files':[],'reviewComplete':False}
            item['checkedAt']=dt.datetime.now(dt.timezone.utc).isoformat()
            item['classificationVersion']=CLASSIFICATION_VERSION
            item['hwpxReaderVersion']=HWPX_READER_VERSION
            scans[key]=item
            checkpoint+=1
            if checkpoint%15==0:
                atomic_json(state_path,{
                   'ok':True,'generatedAt':dt.datetime.now(dt.timezone.utc).isoformat(),
                   'scans':scans,'metadataCalls':provider.calls,
                   'metadataPages':provider.pages})
                print('BATCH_EXTRACTION_CHECKPOINT','FINISHED',checkpoint,
                      'TOTAL',len(needed),flush=True)
    finished_at=dt.datetime.now(dt.timezone.utc).isoformat()
    atomic_json(state_path,{'ok':True,'generatedAt':finished_at,
                 'metadataCalls':provider.calls,'metadataPages':provider.pages,
                 'scans':scans})
    total_index,detail_count,omitted=merge_coverage(data,scans,finished_at)
    statuses=collections.Counter(str(scans[key].get('status')) for key in needed)
    readable=sum(int(scans[key].get('readableDocumentCount') or 0) for key in needed)
    failures=collections.Counter(
       f.get('errorCategory') or 'unknown'
       for key in needed for f in scans[key].get('files') or []
       if f.get('readable') is not True)
    report={'ok':True,'asOfKST':dt.datetime.now(KST).isoformat(timespec='seconds'),
       'top500':len(top),'targetMissingAtStart':len(target),
       'targetScannedThisRun':len(needed),'officialMetadataApiCalls':provider.calls,
       'providerFailures':provider.failed,'sourcePages':provider.pages,
       'targetNoticeHitsBySource':dict(by_source),
       'statuses':dict(statuses),'readableDocuments':readable,
       'unreadableCategories':dict(failures),
       'totalCoverageIndex':total_index,'rollingDetailCount':detail_count,
       'rollingDetailOmitted':omitted,
       'limitation':'Attachment API metadata and extracted excerpts are not a final legal eligibility review.'}
    atomic_json(data/'snapshots/rfp-top500-batch-report-20261111.json',report)
    print('TOP500_BATCH_REPORT='+json.dumps(report,ensure_ascii=False,separators=(',',':')),flush=True)

if __name__=='__main__':main()
