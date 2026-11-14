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
ROWS=999
MAX_PAGES_PER_DAY_SOURCE=500
MAX_FETCH_PER_PASS=18
DAILY_LIMIT=180
# Old 36/hour self-throttle left 1,585 notices without lists while the
# official A02 proxy circuit breaker was inactive. Period calls already
# have paced starts (0.8s) and a separate rolling daily budget, so do
# not impose an unsupported additional 36/hour starvation window.
HOURLY_LIMIT=DAILY_LIMIT

class BulkManifestError(RuntimeError):
    pass

class BulkManifestQuota(BulkManifestError):
    def __init__(self,message,retry_after_seconds=60):
        super().__init__(message)
        self.retry_after_seconds=max(1,int(retry_after_seconds))

class BulkManifestPlanner:
    def __init__(self,queue,bids_db,fetch,pacer,allow_exceptions=True):
        self.queue=queue
        self.bids_db=Path(bids_db)
        self.fetch=fetch
        self.pacer=pacer
        self.allow_exceptions=allow_exceptions

    def posted_days(self):
        """Only verified posted dates from saved SW service notices."""
        if not self.bids_db.is_file():return {}
        with sqlite3.connect('file:'+str(self.bids_db)+'?mode=ro',uri=True,timeout=12) as db:
            rows=db.execute('''SELECT bid_no,bid_ord,payload
                FROM bid_notices WHERE sw_candidate=1''').fetchall()
        desired=set(self.queue.unprepared_notices(eligible_only=True))
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

    @staticmethod
    def _required_pages(total,first_count):
        # A 1000-row request returned 10 rows; use 999 and retain defensive pagination.
        # The first page's actual size, never the requested size, controls
        # pagination. Incomplete/empty first pages must fail closed.
        if total<0 or first_count<0 or (total>0 and first_count==0):
            raise BulkManifestError('batch_invalid_first_page_size')
        return max(1,math.ceil(total/first_count)) if total else 1

    def _cached_pages(self,day,source):
        with self.queue.connect() as db:
            rows=db.execute('''SELECT page,total_count,raw_count,items_json
                FROM rfp_bulk_pages WHERE day=? AND source=? ORDER BY page''',
                (day,source)).fetchall()
        if not rows:return None
        total=rows[0][1]
        if rows[0][0]!=1:return None
        try:required=self._required_pages(total,rows[0][2])
        except BulkManifestError:return None
        effective=rows[0][2]
        if (required>MAX_PAGES_PER_DAY_SOURCE or len(rows)!=required or
                [row[0] for row in rows]!=list(range(1,required+1)) or
                any(row[1]!=total or not 0<=row[2]<=ROWS for row in rows) or
                any(row[2]!=min(effective,max(0,total-i*effective))
                    for i,row in enumerate(rows)) or
                sum(row[2] for row in rows)!=total):
            return None
        return [record for row in rows for record in json.loads(row[3])]

    def _pages_present(self,day,source):
        with self.queue.connect() as db:
            rows=db.execute('''SELECT page,total_count,raw_count,requested_rows
                FROM rfp_bulk_pages WHERE day=? AND source=? ORDER BY page''',
                (day,source)).fetchall()
        return rows

    def _reserve_api_call(self,source,day,page):
        stamp=dt.datetime.now(dt.timezone.utc)
        hourly=(stamp-dt.timedelta(hours=1)).isoformat()
        midnight=stamp.replace(hour=0,minute=0,second=0,microsecond=0).isoformat()
        with self.queue.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            hour=db.execute("SELECT COUNT(*) FROM rfp_bulk_request_budget WHERE started_at>=?",
                            (hourly,)).fetchone()[0]
            daily=db.execute("SELECT COUNT(*) FROM rfp_bulk_request_budget WHERE started_at>=?",
                             (midnight,)).fetchone()[0]
            if hour>=HOURLY_LIMIT or daily>=DAILY_LIMIT:
                # Resume exactly as the saved rolling-hour / UTC-day budgets
                # release requests, rather than blindly sleeping another hour.
                retry_at=stamp
                if hour>=HOURLY_LIMIT:
                    oldest=db.execute('''SELECT MIN(started_at)
                        FROM rfp_bulk_request_budget WHERE started_at>=?''',
                        (hourly,)).fetchone()[0]
                    if oldest:
                        retry_at=max(retry_at,
                            dt.datetime.fromisoformat(oldest)+dt.timedelta(hours=1,seconds=2))
                if daily>=DAILY_LIMIT:
                    retry_at=max(retry_at,
                        stamp.replace(hour=0,minute=0,second=0,microsecond=0)+
                        dt.timedelta(days=1,seconds=2))
                wait=math.ceil((retry_at-stamp).total_seconds())
                raise BulkManifestQuota('rfp_bulk_budget_hourly_or_daily',
                                         retry_after_seconds=wait)
            db.execute('''INSERT INTO rfp_bulk_request_budget(started_at,source,day,page)
                VALUES(?,?,?,?)''',(stamp.isoformat(),source,day,page))
            # 3-day bounded history; avoid a forever-growing request ledger.
            db.execute("DELETE FROM rfp_bulk_request_budget WHERE started_at<?",
                       ((stamp-dt.timedelta(days=3)).isoformat(),))

    def _source_for_day(self,day,source,needed_keys):
        cached=self._cached_pages(day,source)
        if cached is not None:return cached,0
        saved=self._pages_present(day,source)
        if saved and any(row[3]!=ROWS for row in saved):
            # Only incomplete caches reach here; complete caches were reused.
            # Never continue a 10-row first page with 999-row page offsets.
            with self.queue.connect() as db:
                db.execute('DELETE FROM rfp_bulk_pages WHERE day=? AND source=?',
                           (day,source))
            saved=[]
        known_total=saved[0][1] if saved else None
        if known_total is not None and known_total<0:
            raise BulkManifestError('invalid_cached_batch_total')
        effective=saved[0][2] if saved and saved[0][0]==1 else None
        if saved and effective is None:
            raise BulkManifestError('batch_missing_first_page')
        pages=(self._required_pages(known_total,effective)
               if known_total is not None else 1)
        if pages>MAX_PAGES_PER_DAY_SOURCE:
            raise BulkManifestError('batch_page_count_unprofitable')
        existing={row[0] for row in saved}
        fetched=0
        page=1
        while page<=pages:
            if page in existing:
                page+=1
                continue
            if fetched>=MAX_FETCH_PER_PASS:
                return None,fetched
            self._reserve_api_call(source,day,page)
            self.pacer.acquire()
            compact=day.replace('-','')
            params={'source':source,'from':compact+'0000',
                    'to':compact+'2359','page':page,'rows':ROWS}
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
            if effective is None:
                if page!=1:raise BulkManifestError('batch_first_page_not_fetched')
                effective=raw
            expected=self._required_pages(count,effective)
            if raw!=min(effective,max(0,count-(page-1)*effective)):
                raise BulkManifestError('batch_unexpected_effective_page_size')
            if expected>MAX_PAGES_PER_DAY_SOURCE:
                raise BulkManifestError('batch_page_count_unprofitable')
            if known_total is not None and count!=known_total:
                raise BulkManifestError('batch_total_changed_restart_window')
            known_total=count
            filtered=[]
            for item in payload['items']:
                if not isinstance(item,dict):
                    raise BulkManifestError('batch_invalid_attachment_item')
                filtered.append(item)  # retain all rows for newly discovered notices
            with self.queue.connect() as db:
                db.execute('''INSERT OR REPLACE INTO rfp_bulk_pages
                    (day,source,page,total_count,raw_count,items_json,saved_at,requested_rows)
                    VALUES(?,?,?,?,?,?,?,?)''',
                    (day,source,page,count,raw,
                     json.dumps(filtered,ensure_ascii=False,separators=(',',':')),
                     dt.datetime.now(dt.timezone.utc).isoformat(),ROWS))
            fetched+=1
            pages=expected
            page+=1
        return self._cached_pages(day,source),fetched

    def _exception_one(self,key,day):
        """Maximum one exceptional notice per pass, maximum two per UTC day.

        Normal traffic remains three shared date listings. A three-operation
        exception is used only after a complete batch misses the notice.
        """
        if not self.allow_exceptions:return None,0
        stamp=dt.datetime.now(dt.timezone.utc)
        midnight=stamp.replace(hour=0,minute=0,second=0,microsecond=0).isoformat()
        with self.queue.connect() as db:
            used=db.execute("""SELECT COUNT(*) FROM rfp_bulk_request_budget
                WHERE started_at>=? AND source LIKE 'exception_%'""",
                (midnight,)).fetchone()[0]
        if used>=6:return None,0
        # Reserve the cost of ALL THREE official operations, not one proxy call.
        for src in SOURCES:self._reserve_api_call('exception_'+src,day,0)
        self.pacer.acquire()
        bid,order=key.split(':',1)
        params=urllib.parse.urlencode({'bidNo':bid,'order':order})
        payload=self.fetch('http://127.0.0.1:18192/api/g2b/rfp-attachment-exception?'+params)
        attachments=payload.get('attachments') or {}
        documents=payload.get('noticeDocuments') or {}
        if (attachments.get('ok') is not True or
                attachments.get('complete') is not True or
                documents.get('complete') is not True):
            return None,3
        payload['manifestOrigin']='verified_missing_date_batch_exception'
        return payload,3

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
                if source=='detail' and (name or url):all_detail.append(item)
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

    def populate_one_day(self):
        """At most one day per pass; never touch the actual file-download queue."""
        mapping=self.posted_days()
        if not mapping:return {'new':0,'missingPostedDate':len(self.queue.unprepared_notices()),'calls':0}
        groups={}
        for key,day in mapping.items():groups.setdefault(day,set()).add(key)
        day=sorted(groups,reverse=True)[0]
        keys=groups[day]
        sources={}
        calls=0
        for source in SOURCES:
            items,made=self._source_for_day(day,source,keys)
            calls+=made
            if items is None:
                return {'new':0,'day':day,'calls':calls,'partial':True}
            sources[source]=items
        # A full-date response can legitimately contain no attachment files,
        # but it cannot establish that an entirely absent notice was checked.
        # Avoid a per-notice fallback storm: hold unmatched notices for a
        # later bounded exception pass; never publish an invented empty list.
        present={key:False for key in keys}
        for items in sources.values():
            for item in items:
                key=str(item.get('bidNo'))+':'+str(item.get('order'))
                if key in present:present[key]=True
        verified={key for key,found in present.items() if found}
        missing=sorted(keys-verified)
        manifests={key:self._notice_meta(key,sources) for key in verified}
        exception_calls=0
        if missing:
            # One notice at most; never fan out a per-notice API storm.
            try:
                recovered,exception_calls=self._exception_one(missing[0],day)
            except BulkManifestQuota:
                recovered=None
            if recovered is not None:
                manifests[missing[0]]=recovered
                missing=missing[1:]
        count=self.queue.save_bulk_manifests(manifests)
        calls+=exception_calls
        if missing:
            # Retry on another planning window rather than hammer the same day.
            self.queue.defer_bulk_unmatched(missing,3600,'not_present_in_complete_date_batch')
        return {'new':count,'day':day,'calls':calls,'unmatched':len(missing),
                'sourceCounts':{src:len(items) for src,items in sources.items()},
                'pending':len(self.queue.unprepared_notices())}
