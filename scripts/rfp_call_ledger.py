#!/usr/bin/env python3
"""Durable, secret-free RFP request ledger and verified response cache on server123.

Only records actually observed after installation; historical totals remain historical.
A 'cache_hit' is never counted as a fresh upstream HTTP call.
"""
import datetime as dt
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import zlib


def utcnow():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def cache_key(*parts):
    """Opaque, bounded identity; never put serviceKey or full signed URLs in SQLite."""
    data=json.dumps(parts,ensure_ascii=False,separators=(',',':'))
    return hashlib.sha256(data.encode('utf-8')).hexdigest()


def ledger_path(data_dir=None):
    explicit=os.environ.get('WORKLINKS_RFP_LEDGER_DB')
    if explicit:
        return Path(explicit)
    return Path(data_dir or '/data') / 'rfp-request-ledger.sqlite3'


class CallLedger:
    def __init__(self, path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self._connect() as conn:
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('''CREATE TABLE IF NOT EXISTS call_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                occurred_at TEXT NOT NULL,
                kind TEXT NOT NULL,
                request_key TEXT NOT NULL,
                notice_key TEXT,
                outcome TEXT NOT NULL,
                http_status INTEGER,
                response_sha256 TEXT,
                error_class TEXT,
                detail TEXT
            )''')
            conn.execute('''CREATE INDEX IF NOT EXISTS call_events_key_id
                            ON call_events(request_key,id)''')
            conn.execute('''CREATE TABLE IF NOT EXISTS attachment_refs (
                request_key TEXT NOT NULL,
                notice_key TEXT NOT NULL,
                closes_on TEXT NOT NULL DEFAULT '',
                PRIMARY KEY(request_key,notice_key)
            )''')
            conn.execute('''CREATE INDEX IF NOT EXISTS attachment_refs_notice
                            ON attachment_refs(notice_key)''')
            conn.execute('''CREATE TABLE IF NOT EXISTS ledger_meta (
                key TEXT PRIMARY KEY, value TEXT NOT NULL
            )''')
            conn.execute('''CREATE TABLE IF NOT EXISTS verified_cache (
                request_key TEXT PRIMARY KEY,
                stored_at TEXT NOT NULL,
                media_type TEXT NOT NULL,
                payload BLOB NOT NULL,
                sha256 TEXT NOT NULL,
                source_revision TEXT NOT NULL DEFAULT ''
            )''')

    @contextmanager
    def _connect(self):
        conn=sqlite3.connect(str(self.path),timeout=30)
        conn.execute('PRAGMA busy_timeout=30000')
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def record(self,kind,request_key,outcome,*,notice_key=None,
               http_status=None,response_sha256=None,error_class=None,detail=None):
        # Caller passes a canonical opaque request id, never a serviceKey.
        if not isinstance(request_key,str) or len(request_key)>120:
            raise ValueError('RFP_LEDGER_INVALID_KEY')
        if detail is not None and len(str(detail))>180:
            detail=str(detail)[:180]
        with self._connect() as conn:
            conn.execute('''INSERT INTO call_events
                (occurred_at,kind,request_key,notice_key,outcome,http_status,
                 response_sha256,error_class,detail) VALUES (?,?,?,?,?,?,?,?,?)''',
                (utcnow(),kind,request_key,notice_key,outcome,http_status,
                 response_sha256,error_class,detail))

    def _read(self,key,media_type,*,max_age_seconds=None,source_revision=''):
        with self._connect() as conn:
            row=conn.execute('''SELECT stored_at,payload,sha256,source_revision
                FROM verified_cache WHERE request_key=? AND media_type=?''',
                (key,media_type)).fetchone()
        if row is None:return None
        stored_at,payload,expected,revision=row
        if source_revision != revision:return None
        if max_age_seconds is not None:
            try:
                age=(dt.datetime.now(dt.timezone.utc) -
                     dt.datetime.fromisoformat(stored_at)).total_seconds()
            except ValueError:return None
            if age<0 or age>max_age_seconds:return None
        try:
            data=zlib.decompress(payload)
        except (zlib.error,TypeError):
            self.record('cache',key,'corrupt_cache',error_class='invalid_compression')
            return None
        if hashlib.sha256(data).hexdigest()!=expected:
            self.record('cache',key,'corrupt_cache',error_class='sha256_mismatch')
            return None
        if media_type=='json':
            try:value=json.loads(data.decode('utf-8'))
            except (UnicodeError,ValueError):
                self.record('cache',key,'corrupt_cache',error_class='invalid_json')
                return None
        else:value=data
        self.record('cache',key,'cache_hit',response_sha256=expected)
        return value

    def get_json(self,key,*,max_age_seconds=None,source_revision=''):
        return self._read(key,'json',max_age_seconds=max_age_seconds,
                          source_revision=source_revision)

    def get_bytes(self,key,*,max_age_seconds=None,source_revision=''):
        return self._read(key,'bytes',max_age_seconds=max_age_seconds,
                          source_revision=source_revision)

    def _store(self,key,media_type,raw,*,source_revision=''):
        signature=hashlib.sha256(raw).hexdigest()
        compressed=zlib.compress(raw,level=4)
        max_disk,reserve=self._limits()
        with self._connect() as conn:
            # Serialize quota checks across concurrent notice workers.
            conn.execute('BEGIN IMMEDIATE')
            existing=conn.execute('SELECT length(payload) FROM verified_cache WHERE request_key=?',
                                  (key,)).fetchone()
            current_size=(self.path.stat().st_size if self.path.exists() else 0)
            wal=Path(str(self.path)+'-wal')
            if wal.is_file():current_size+=wal.stat().st_size
            # Budget limits physical SQLite/WAL growth, not only raw file size.
            # Replacements are allowed when the DB is full, if no page growth
            # is needed. Admission never evicts a live notice's archived bytes.
            growth=max(0,len(compressed)-(int(existing[0]) if existing else 0))
            if (current_size+growth+8*1048576>max_disk or
                shutil.disk_usage(self.path.parent).free<reserve+max(growth*2,1048576)):
                conn.execute('''INSERT INTO call_events
                    (occurred_at,kind,request_key,outcome,detail)
                    VALUES(?,?,?,?,?)''',
                    (utcnow(),'cache',key,'storage_quota_skip',
                     'compressed_bytes='+str(len(compressed))))
                return None
            conn.execute('''INSERT INTO verified_cache
                (request_key,stored_at,media_type,payload,sha256,source_revision)
                VALUES (?,?,?,?,?,?) ON CONFLICT(request_key) DO UPDATE SET
                  stored_at=excluded.stored_at,media_type=excluded.media_type,
                  payload=excluded.payload,sha256=excluded.sha256,
                  source_revision=excluded.source_revision''',
                (key,utcnow(),media_type,compressed,signature,source_revision))
            conn.execute('''INSERT INTO call_events
                (occurred_at,kind,request_key,outcome,response_sha256)
                VALUES (?,?,?,?,?)''',(utcnow(),'cache',key,'verified_response_saved',signature))
        return signature

    def save_json(self,key,payload,*,source_revision='',max_bytes=20_000_000):
        raw=json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode('utf-8')
        if len(raw)>max_bytes:
            self.record('cache',key,'payload_above_cache_limit',
                        detail='bytes='+str(len(raw)))
            return None
        return self._store(key,'json',raw,source_revision=source_revision)

    def save_bytes(self,key,raw,*,source_revision='',max_bytes=24_000_000,
                   notice_key=None,closes_on=''):
        if len(raw)>max_bytes:
            self.record('cache',key,'payload_above_cache_limit',
                        detail='bytes='+str(len(raw)))
            return None
        result=self._store(key,'bytes',raw,source_revision=source_revision)
        if result and notice_key:self.link_attachment(key,notice_key,closes_on)
        return result


    @staticmethod
    def _close_date(value):
        raw=str(value or '').strip()
        try:
            return dt.date.fromisoformat(raw[:10]) if len(raw)>=10 else dt.date.fromisoformat(raw)
        except (ValueError,TypeError):
            return None

    def link_attachment(self, key, notice_key, closes_on=''):
        """Reference an exact archived binary from a notice (no download)."""
        if not notice_key:return
        date=self._close_date(closes_on)
        with self._connect() as db:
            db.execute('''INSERT INTO attachment_refs(request_key,notice_key,closes_on)
                VALUES(?,?,?) ON CONFLICT(request_key,notice_key) DO UPDATE SET
                closes_on=CASE WHEN excluded.closes_on<>'' THEN excluded.closes_on
                               ELSE attachment_refs.closes_on END''',
                (key,str(notice_key)[:48],date.isoformat() if date else ''))

    @staticmethod
    def _limits():
        def number(name,default,minimum,maximum):
            try:val=int(os.environ.get(name,str(default)))
            except ValueError:val=default
            return min(max(val,minimum),maximum)
        return (number('WORKLINKS_RFP_LEDGER_MAX_MB',4096,256,16384)*1048576,
                number('WORKLINKS_RFP_DISK_RESERVE_MB',5120,512,32768)*1048576)

    def prune_expired(self, deadline_by_notice=None, *, today=None, grace_days=7,
                      unknown_days=30, json_days=30, event_days=60,
                      compact=True):
        """Delete only expired/orphan archived bytes; retain any live notice ref.

        Legacy archives are linked to their notice from historical HTTP events.
        Unknown-deadline archives expire after a bounded fallback lifetime.
        Nothing here touches original RFP scan evidence or API snapshot files.
        """
        deadlines=deadline_by_notice or {}
        today=today or dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()
        if isinstance(today,dt.datetime):today=today.date()
        grace=max(0,int(grace_days))
        unknown=max(1,int(unknown_days))
        now_utc=dt.datetime.now(dt.timezone.utc)
        cutoff_json=(now_utc-dt.timedelta(days=max(1,int(json_days)))).isoformat()
        cutoff_events=(now_utc-dt.timedelta(days=max(1,int(event_days)))).isoformat()
        archived_deleted=0
        json_deleted=0
        events_deleted=0
        deleted_payload_bytes=0
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute("SELECT 1 FROM ledger_meta WHERE key='legacy_refs_migrated'").fetchone():
                db.execute('''INSERT OR IGNORE INTO attachment_refs(request_key,notice_key,closes_on)
                    SELECT DISTINCT e.request_key,e.notice_key,''
                    FROM call_events e INNER JOIN verified_cache c
                       ON c.request_key=e.request_key AND c.media_type='bytes'
                    WHERE e.kind IN ('attachment_http','attachment_reuse')
                      AND e.notice_key IS NOT NULL AND e.notice_key<>'' ''')
                db.execute("INSERT INTO ledger_meta(key,value) VALUES('legacy_refs_migrated',?)",
                           (utcnow(),))
            # Notice metadata can be corrected after an archive was saved.
            for notice,close in deadlines.items():
                date=self._close_date(close)
                if date:
                    db.execute('UPDATE attachment_refs SET closes_on=? WHERE notice_key=?',
                               (date.isoformat(),notice))
            refs={}
            for key,notice,close in db.execute(
                    'SELECT request_key,notice_key,closes_on FROM attachment_refs'):
                refs.setdefault(key,[]).append((notice,close))
            to_remove=[]
            for key,stamp,payload_size in db.execute(
                    "SELECT request_key,stored_at,length(payload) FROM verified_cache WHERE media_type='bytes'"):
                try:created=dt.datetime.fromisoformat(stamp).date()
                except (TypeError,ValueError):created=today
                keep=False
                candidates=refs.get(key,[])
                if not candidates:
                    keep=(today-created).days<unknown
                else:
                    for notice,stored_close in candidates:
                        date=self._close_date(deadlines.get(notice) or stored_close)
                        if date:
                            if today<=date+dt.timedelta(days=grace):
                                keep=True
                                break
                        elif (today-created).days<unknown:
                            keep=True
                            break
                if not keep:to_remove.append((key,int(payload_size or 0)))
            for key,size in to_remove:
                db.execute("DELETE FROM verified_cache WHERE request_key=? AND media_type='bytes'",
                           (key,))
                db.execute("DELETE FROM attachment_refs WHERE request_key=?",(key,))
                archived_deleted+=1
                deleted_payload_bytes+=size
            json_deleted=db.execute(
                "DELETE FROM verified_cache WHERE media_type='json' AND stored_at < ?",
                (cutoff_json,)).rowcount
            events_deleted=db.execute(
                "DELETE FROM call_events WHERE occurred_at < ?",(cutoff_events,)).rowcount
            remaining=db.execute(
                "SELECT COUNT(*),COALESCE(SUM(length(payload)),0) FROM verified_cache WHERE media_type='bytes'"
            ).fetchone()
        # SQLite deletion may leave reusable free pages. Compact safely when
        # enough disk space exists; otherwise preserve data and retry later.
        file_before=self.path.stat().st_size if self.path.exists() else 0
        reclaimed=0
        try:
            with sqlite3.connect(str(self.path),timeout=1) as db:
                db.execute('PRAGMA busy_timeout=1000')
                if compact:db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
                free_pages=db.execute('PRAGMA freelist_count').fetchone()[0]
                page_size=db.execute('PRAGMA page_size').fetchone()[0]
                reclaimable=free_pages*page_size
                incremental=db.execute('PRAGMA auto_vacuum').fetchone()[0]==2
                if compact and reclaimable>=32*1048576:
                    if incremental:
                        db.execute('PRAGMA incremental_vacuum')
                    elif (shutil.disk_usage(self.path.parent).free >=
                          file_before*2+512*1048576):
                        db.execute('VACUUM')
            reclaimed=max(0,file_before-self.path.stat().st_size)
        except (sqlite3.Error,OSError):
            pass  # Cannot block active reader or cause disk pressure.
        return {'attachmentsDeleted':archived_deleted,
                'deletedCompressedBytes':deleted_payload_bytes,
                'jsonDeleted':json_deleted,'eventsDeleted':events_deleted,
                'attachmentsRemaining':remaining[0],
                'compressedBytesRemaining':remaining[1],
                'fileBytesReclaimed':reclaimed}

    def stats(self):
        with self._connect() as conn:
            counts=dict(conn.execute('''SELECT kind || ':' || outcome,COUNT(*)
                FROM call_events GROUP BY kind,outcome''').fetchall())
            cached=conn.execute('SELECT COUNT(*) FROM verified_cache').fetchone()[0]
            total=conn.execute('SELECT COUNT(*) FROM call_events').fetchone()[0]
        return {'events':total,'cachedResponses':cached,'counts':counts}
