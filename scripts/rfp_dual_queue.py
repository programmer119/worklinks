#!/usr/bin/env python3
"""Durable, independent download and scan queues for the full live RFP backlog.

The download worker never waits for a scan; the scanner claims only ready notices.
A changed reader fingerprint resets scanning but keeps verified archived originals.
"""
import datetime as dt
import json
import os
from pathlib import Path
import sqlite3
import time

KST=dt.timezone(dt.timedelta(hours=9))
SCHEMA_VERSION=1

def now_utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()

class RfpDualQueue:
    def __init__(self,path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('''CREATE TABLE IF NOT EXISTS rfp_dual_notices(
                notice_key TEXT PRIMARY KEY,
                closes_on TEXT NOT NULL DEFAULT '',
                reader_fingerprint TEXT NOT NULL,
                download_status TEXT NOT NULL DEFAULT 'pending',
                scan_status TEXT NOT NULL DEFAULT 'pending',
                metadata_json TEXT NOT NULL DEFAULT '',
                download_total INTEGER NOT NULL DEFAULT 0,
                download_done INTEGER NOT NULL DEFAULT 0,
                download_attempts INTEGER NOT NULL DEFAULT 0,
                download_retry_epoch REAL NOT NULL DEFAULT 0,
                scan_retry_epoch REAL NOT NULL DEFAULT 0,
                last_error TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            )''')
            db.execute('''CREATE INDEX IF NOT EXISTS dual_queue_fetch
                ON rfp_dual_notices(download_status,download_retry_epoch)''')
            db.execute('''CREATE INDEX IF NOT EXISTS dual_queue_scan
                ON rfp_dual_notices(scan_status,download_status,scan_retry_epoch)''')

    def connect(self):
        db=sqlite3.connect(str(self.path),timeout=12)
        db.execute('PRAGMA busy_timeout=12000')
        return db

    def enqueue(self,notices,fingerprint):
        """Idempotent. 64-small-row transactions avoid blocking scan writes."""
        added=0
        entries=list(notices)
        for offset in range(0,len(entries),64):
            with self.connect() as db:
                for no,order,closes in entries[offset:offset+64]:
                    key=str(no)+':'+str(order).zfill(3)
                    val=str(closes or '')
                    cur=db.execute('SELECT reader_fingerprint FROM rfp_dual_notices WHERE notice_key=?',(key,)).fetchone()
                    if cur is None:
                        db.execute('''INSERT INTO rfp_dual_notices(
                            notice_key,closes_on,reader_fingerprint,updated_at)
                            VALUES(?,?,?,?)''',(key,val,fingerprint,now_utc()))
                        added+=1
                    elif cur[0]!=fingerprint:
                        db.execute('''UPDATE rfp_dual_notices
                            SET reader_fingerprint=?,scan_status='pending',scan_retry_epoch=0,
                                closes_on=?,updated_at=? WHERE notice_key=?''',
                            (fingerprint,val,now_utc(),key))
                    elif val:
                        db.execute('''UPDATE rfp_dual_notices SET closes_on=?
                            WHERE notice_key=? AND closes_on<>?''',(val,key,val))
        return added

    def retire_expired(self,today=None):
        """Retire past-close notices. Raw originals are retained/pruned elsewhere."""
        day=today or dt.datetime.now(KST).date()
        with self.connect() as db:
            return db.execute(
                "DELETE FROM rfp_dual_notices WHERE closes_on<>'' AND closes_on<?",
                (day.isoformat(),)).rowcount

    def reset_stale(self):
        """Safe only at process start; a lost worker can be resumed from raw bytes."""
        with self.connect() as db:
            db.execute("UPDATE rfp_dual_notices SET download_status='pending' WHERE download_status='fetching'")
            db.execute("UPDATE rfp_dual_notices SET scan_status='pending' WHERE scan_status='scanning'")

    def claim_download(self):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('''SELECT notice_key,closes_on FROM rfp_dual_notices
                WHERE download_status IN ('pending','retry')
                AND download_retry_epoch<=?
                ORDER BY download_retry_epoch,updated_at,notice_key LIMIT 1''',
                (time.time(),)).fetchone()
            if row:
                db.execute('''UPDATE rfp_dual_notices SET download_status='fetching',
                    download_attempts=download_attempts+1,updated_at=?
                    WHERE notice_key=?''',(now_utc(),row[0]))
            return row

    def downloaded(self,key,metadata,done,total):
        payload=json.dumps(metadata,ensure_ascii=False,separators=(',',':'))
        with self.connect() as db:
            db.execute('''UPDATE rfp_dual_notices
                SET download_status='ready',metadata_json=?,download_done=?,download_total=?,
                    download_retry_epoch=0,last_error='',updated_at=?
                WHERE notice_key=? AND download_status='fetching' ''',
                (payload,int(done),int(total),now_utc(),key))

    def download_failed(self,key,reason,retry_seconds=180):
        with self.connect() as db:
            db.execute('''UPDATE rfp_dual_notices SET download_status='retry',
                download_retry_epoch=?,last_error=?,updated_at=?
                WHERE notice_key=? AND download_status='fetching' ''',
                (time.time()+retry_seconds,str(reason)[:140],now_utc(),key))

    def claim_ready(self,limit):
        """Claim completed downloads only, never ask an official endpoint."""
        claimed=[]
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            rows=db.execute('''SELECT notice_key,closes_on,metadata_json
                FROM rfp_dual_notices WHERE download_status='ready'
                AND scan_status IN ('pending','retry') AND scan_retry_epoch<=?
                ORDER BY updated_at,notice_key LIMIT ?''',
                (time.time(),int(limit))).fetchall()
            for key,closes,metadata in rows:
                try:obj=json.loads(metadata)
                except (ValueError,TypeError):continue
                if not isinstance(obj,dict):continue
                db.execute('''UPDATE rfp_dual_notices SET scan_status='scanning',updated_at=?
                    WHERE notice_key=?''',(now_utc(),key))
                claimed.append((key,closes,obj))
        return claimed

    def scan_finished(self,key,success,reason=''):
        with self.connect() as db:
            db.execute('''UPDATE rfp_dual_notices
                SET scan_status=?,scan_retry_epoch=?,last_error=?,updated_at=?
                WHERE notice_key=? AND scan_status='scanning' ''',
                ('done' if success else 'retry',
                 0 if success else time.time()+3600,
                 '' if success else str(reason)[:140],now_utc(),key))

    def mark_download_missing(self,key):
        with self.connect() as db:
            db.execute('''UPDATE rfp_dual_notices SET download_status='pending',
                scan_status='pending',download_retry_epoch=0,scan_retry_epoch=0,
                last_error='cached_original_missing',updated_at=?
                WHERE notice_key=?''',(now_utc(),key))

    def recover_stale_scans(self,seconds=2400):
        cutoff=(dt.datetime.now(dt.timezone.utc)-
                dt.timedelta(seconds=seconds)).isoformat()
        with self.connect() as db:
            return db.execute('''UPDATE rfp_dual_notices SET scan_status='pending'
                WHERE scan_status='scanning' AND updated_at<?''',(cutoff,)).rowcount

    def scan_release(self,keys):
        with self.connect() as db:
            db.executemany('''UPDATE rfp_dual_notices SET scan_status='pending'
                WHERE notice_key=? AND scan_status='scanning' ''',
                [(key,) for key in keys])

    def stats(self):
        with self.connect() as db:
            rows=db.execute('''SELECT download_status,scan_status,COUNT(*)
                FROM rfp_dual_notices GROUP BY download_status,scan_status''').fetchall()
        total=sum(n for _,_,n in rows)
        downloaded=sum(n for download,_,n in rows if download=='ready')
        scan_done=sum(n for _,scan,n in rows if scan=='done')
        # "retry" is retriable, not a fabricated completed action.
        return {'available':True,'total':total,
                'download':{'total':total,'done':downloaded,
                            'active':sum(n for download,_,n in rows if download=='fetching'),
                            'failed':sum(n for download,_,n in rows if download=='retry')},
                'scan':{'total':total,'done':scan_done,
                        'active':sum(n for _,scan,n in rows if scan=='scanning'),
                        'failed':sum(n for _,scan,n in rows if scan=='retry')}}

    @staticmethod
    def read_stats(path):
        if not Path(path).is_file():
            return {'available':False}
        with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True,timeout=2) as db:
            rows=db.execute('''SELECT download_status,scan_status,COUNT(*)
                FROM rfp_dual_notices GROUP BY download_status,scan_status''').fetchall()
        total=sum(n for _,_,n in rows)
        return {'available':True,'total':total,
                'download':{'total':total,
                            'done':sum(n for a,_,n in rows if a=='ready'),
                            'active':sum(n for a,_,n in rows if a=='fetching'),
                            'failed':sum(n for a,_,n in rows if a=='retry')},
                'scan':{'total':total,
                        'done':sum(n for _,b,n in rows if b=='done'),
                        'active':sum(n for _,b,n in rows if b=='scanning'),
                        'failed':sum(n for _,b,n in rows if b=='retry')}}
