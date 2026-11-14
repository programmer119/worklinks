#!/usr/bin/env python3
"""One-day, paginated, durable official attachment lists for many RFP notices.

All three document sources are acquired by PERIOD rather than by notice.
An incomplete page/source NEVER counts as a complete manifest. A single
request may populate dozens of separate notice download jobs.
"""
import datetime as dt
import json
import math
from pathlib import Path
import re
import sqlite3
import time
import urllib.parse

SOURCES=('ordinary','eorder','detail')
ROWS=1000
MAX_PAGES_PER_DAY_SOURCE=300
MAX_FETCH_PER_PASS=18
DAILY_LIMIT=180
HOURLY_LIMIT=36

class BulkManifestError(RuntimeError):
    pass

class BulkManifestQuota(BulkManifestError):
    pass

class BulkManifestPlanner:
    def __init__(self,queue,bids_db,fetch,pacer):
        self.queue=queue
        self.bids_db=Path(bids_db)
        self.fetch=fetch
        self.pacer=pacer

    def posted_days(self):
        """Only verified posted dates from saved SW service notices."""
        if not self.bids_db.is_file():return {}
        with sqlite3.connect('file:'+str(self.bids_db)+'?mode=ro',uri=True,timeout=12) as db:
            rows=db.execute('''SELECT bid_no,bid_ord,payload
                FROM bid_notices WHERE sw_candidate=1''').fetchall()
        desired=set(self.queue.unprepared_notices())
        result={}
        for no,order,payload in rows:
            key=str(no)+':'+str(order or '000').zfill(3)
            if key not in desired:continue
            try:notice=json.loads(payload)
            except (ValueError,TypeError):continue
            raw=str(notice.get('posted') or '')
            match=re.match(r'^(20\d\d)[-/]?(\d\d)[-/]?(\d\d)',raw)
            if not match:continue
            try:
                date=dt.date(*map(int,match.groups()))
            except ValueError:continue
            if date>dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date():
                continue
            result[key]=date.isoformat()
        return result

    def _cached_pages(self,day,source):
        with self.queue.connect() as db:
            rows=db.execute('''SELECT page,total_count,raw_count,items_json
                FROM rfp_bulk_pages WHERE day=? AND source=? ORDER BY page''',
                (day,source)).fetchall()
        if not rows:return None
        total=rows[0][1]
        # Some official operations silently return ten rows despite requesting
        # 1,000. The FIRST ACTUAL page, not the requested rows, controls the
        # page count. Never treat 10/151 as a one-page complete response.
        first=rows[0][2]
        effective=first if total>first else max(1,total)
        required=max(1,math.ceil(total/effective))
        if (required>MAX_PAGES_PER_DAY_SOURCE or len(rows)!=required or
                [row[0] for row in rows]!=list(range(1,required+1)) or
                any(row[1]!=total or row[2]!=min(effective,total-(row[0]-1)*effective)
                    for row in rows) or
                sum(row[2] for row in rows)!=total):
            return None
        out=[]
        seen_full_pages=set()
        for page,count,raw,data in rows:
            try:
                values=json.loads(data)
                if not isinstance(values,list):return None
            except (TypeError,ValueError):return None
            # If official API ignored 'page', repeated pages would otherwise
            # silently certify the wrong RFP attachments.
            if page<required and values:
                signature=json.dumps(values,ensure_ascii=False,sort_keys=True)
                if signature in seen_full_pages:return None
                seen_full_pages.add(signature)
            out.extend(values)
        return out

    def _pages_present(self,day,source):
        with self.queue.connect() as db:
            rows=db.execute('''SELECT page,total_count,raw_count
                FROM rfp_bulk_pages WHERE day=? AND source=? ORDER BY page''',
                (day,source)).fetchall()
        return rows

    def _reserve_api_call(self,source,day,page,cost=1):
        stamp=dt.datetime.now(dt.timezone.utc)
        hourly=(stamp-dt.timedelta(hours=1)).isoformat()
        midnight=stamp.replace(hour=0,minute=0,second=0,microsecond=0).isoformat()
        with self.queue.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            hour=db.execute("SELECT COUNT(*) FROM rfp_bulk_request_budget WHERE started_at>=?",
                            (hourly,)).fetchone()[0]
            daily=db.execute("SELECT COUNT(*) FROM rfp_bulk_request_budget WHERE started_at>=?",
                             (midnight,)).fetchone()[0]
            if hour+cost>HOURLY_LIMIT or daily+cost>DAILY_LIMIT:
                raise BulkManifestQuota('rfp_bulk_budget_hourly_or_daily')
            db.executemany('''INSERT INTO rfp_bulk_request_budget(started_at,source,day,page)
                VALUES(?,?,?,?)''',[(stamp.isoformat(),source,day,page)]*cost)
            # 3-day bounded history; avoid a forever-growing request ledger.
            db.execute("DELETE FROM rfp_bulk_request_budget WHERE started_at<?",
                       ((stamp-dt.timedelta(days=3)).isoformat(),))

    def _source_for_day(self,day,source,needed_keys,fetch_limit=None):
        cached=self._cached_pages(day,source)
        if cached is not None:return cached,0
        saved=self._pages_present(day,source)
        known_total=saved[0][1] if saved else None
        if known_total is not None and known_total<0:
            raise BulkManifestError('invalid_cached_batch_total')
        if saved and saved[0][0]==1:
            first_raw=saved[0][2]
            if known_total>0 and first_raw==0:
                raise BulkManifestError('invalid_cached_batch_first_page')
            effective=(first_raw if known_total>first_raw else max(1,known_total))
        else:
            effective=ROWS
        pages=max(1,math.ceil(known_total/effective)) if known_total is not None else 1
        if pages>MAX_PAGES_PER_DAY_SOURCE:
            raise BulkManifestError('batch_page_count_unprofitable')
        existing={row[0] for row in saved}
        fetched=0
        page=1
        while page<=pages:
            if page in existing:
                page+=1
                continue
            if fetched>=min(MAX_FETCH_PER_PASS,fetch_limit or MAX_FETCH_PER_PASS):
                return None,fetched
            self._reserve_api_call(source,day,page)
            self.pacer.acquire()
            compact=day.replace('-','')
            params={'source':source,'from':compact+'0000',
                    'to':compact+'2359','page':page,
                    'rows':ROWS if page==1 else effective}
            url='http://127.0.0.1:18192/api/g2b/rfp-attachment-batch?'+urllib.parse.urlencode(params)
            payload=self.fetch(url)
            if payload.get('ok') is not True:
                raise BulkManifestError('batch_proxy_incomplete:'+str(payload.get('error'))[:100])
            count=int(payload.get('totalCount',-1))
            raw=int(payload.get('rawCount',-1))
            if (count<0 or raw<0 or raw>ROWS or
                    (count and raw==0) or
                    int(payload.get('page',-1))!=page or
                    payload.get('source')!=source or
                    not isinstance(payload.get('items'),list)):
                raise BulkManifestError('batch_invalid_provider_pagination')
            if known_total is not None and count!=known_total:
                raise BulkManifestError('batch_total_changed_restart_window')
            if page==1:
                effective=raw if count>raw else max(1,count)
            elif raw!=min(effective,count-(page-1)*effective):
                raise BulkManifestError('batch_provider_page_size_changed')
            expected=max(1,math.ceil(count/effective))
            if expected>MAX_PAGES_PER_DAY_SOURCE:
                raise BulkManifestError('batch_page_count_unprofitable')
            known_total=count
            filtered=[]
            for item in payload['items']:
                if not isinstance(item,dict):
                    raise BulkManifestError('batch_invalid_attachment_item')
                filtered.append(item)  # retain all rows for newly discovered notices
            with self.queue.connect() as db:
                db.execute('''INSERT OR REPLACE INTO rfp_bulk_pages
                    (day,source,page,total_count,raw_count,items_json,saved_at)
                    VALUES(?,?,?,?,?,?,?)''',
                    (day,source,page,count,raw,
                     json.dumps(filtered,ensure_ascii=False,separators=(',',':')),
                     dt.datetime.now(dt.timezone.utc).isoformat()))
            fetched+=1
            pages=expected
            page+=1
        return self._cached_pages(day,source),fetched

    @staticmethod
    def _notice_meta(key,source_items):
        merged=[]
        all_detail=[]
        seen=set()
        general=0;eorder=0
        for source in SOURCES:
            for row in source_items[source]:
                if str(row.get('bidNo'))+':'+str(row.get('order'))!=key:
                    continue
                name=str(row.get('name') or '')[:160]
                url=str(row.get('url') or '')
                item={'name':name,'url':url,'source':row.get('source')}
                if source=='detail':all_detail.append(item)
                if url and url in seen:continue
                if url:seen.add(url)
                if name or url:merged.append(item)
                if source=='ordinary':general+=1
                if source=='eorder':eorder+=1
        return {'ok':True,'bidNo':key.split(':')[0],'order':key.split(':')[1],
            'region':{'ok':False,'complete':False,'error':'not_requested_for_rfp_download'},
            'attachments':{'ok':True,'complete':True,'count':len(merged),
                 'items':merged,'generalCount':general,'eorderCount':eorder,
                 'noticeDetailDocumentCount':len(all_detail),
                 'sourceCoverage':'all_three_official_paginated_date_sources'},
            'noticeDocuments':{'ok':True,'complete':True,'items':all_detail,
                               'count':len(all_detail),
                               'source':'official_paginated_notice_detail'},
            'manifestOrigin':'verified_full_day_batch'}

    def _single_for_day(self,day,keys):
        """Use only 3 exact metadata calls for each sparse or absent bid.

        An incomplete exact-source response is never stored. Reserve every
        potential official call before dispatch, even if it is cache-served.
        """
        made=0
        complete={}
        for key in sorted(keys)[:8]:
            if self.queue.bulk_manifest(key) is not None:continue
            bid,order=key.split(':',1)
            self._reserve_api_call('single',day,-1,cost=3)
            self.pacer.acquire()
            url=('http://127.0.0.1:18192/api/g2b/rfp-attachment-single?'+
                 urllib.parse.urlencode({'bidNo':bid,'order':order}))
            payload=self.fetch(url)
            made+=3  # Budget reservations; authoritative provider calls may use cache.
            docs=payload.get('attachments') or {}
            notice=payload.get('noticeDocuments') or {}
            if (payload.get('ok') is not True or
                    docs.get('ok') is not True or docs.get('complete') is not True or
                    notice.get('complete') is not True):
                raise BulkManifestError('exact_official_attachment_not_complete')
            complete[key]=payload
        return {'new':self.queue.save_bulk_manifests(complete),'day':day,
                'callsReserved':made,'mode':'sparse_exact_three_sources',
                'pending':len(self.queue.unprepared_notices())}

    def populate_one_day(self):
        """One dense day or up to 8 sparse notices per pass, source safe."""
        mapping=self.posted_days()
        missing_keys=set(self.queue.unprepared_notices())-set(mapping)
        if not mapping:
            if missing_keys:
                return self._single_for_day('unknown',missing_keys)
            return {'new':0,'missingPostedDate':0,'calls':0}
        groups={}
        for key,day in mapping.items():groups.setdefault(day,set()).add(key)
        # Drain dense days first: one batch serves the maximum number of bids.
        day=max(groups,key=lambda value:(len(groups[value]),value))
        keys=groups[day]
        # A sparse day's date query may be dozens of pages. Probe at most one
        # first page, then compare three complete batches to 3 per-bid calls.
        ordinary=self._pages_present(day,'ordinary')
        if not ordinary:
            _,made=self._source_for_day(day,'ordinary',keys,fetch_limit=1)
            return {'new':0,'day':day,'calls':made,'probed':True}
        if ordinary:
            total=ordinary[0][1]
            raw=ordinary[0][2]
            effective=(raw if total>raw else max(1,total))
            estimated=max(1,math.ceil(total/effective))*len(SOURCES)
            # Estimate the COMPLETE three-source batch cost against exact
            # calls even for a large backlog; process sparse fallbacks eight
            # at a time, never one giant burst.
            if estimated>len(keys)*len(SOURCES):
                return self._single_for_day(day,keys)
        sources={}
        calls=0
        for source in SOURCES:
            items,made=self._source_for_day(day,source,keys)
            calls+=made
            if items is None:
                return {'new':0,'day':day,'calls':calls,'partial':True}
            sources[source]=items
        seen_keys=set()
        for source,items in sources.items():
            for row in items:
                key=str(row.get('bidNo') or '')+':'+str(row.get('order') or '')
                if key in keys:seen_keys.add(key)
        # An entirely missing bid is not proof of "no attachment". Only an
        # exact three-source confirmation can mark an empty manifest complete.
        manifests={key:self._notice_meta(key,sources) for key in seen_keys}
        count=self.queue.save_bulk_manifests(manifests)
        missing=keys-seen_keys
        if missing:
            one=self._single_for_day(day,missing)
            return {'new':count+one['new'],'day':day,'calls':calls,
                    'exactCallsReserved':one['callsReserved'],
                    'missingExact':len(missing),'pending':one['pending']}
        return {'new':count,'day':day,'calls':calls,'sourceCounts':
                {src:len(items) for src,items in sources.items()},
                'pending':len(self.queue.unprepared_notices())}
