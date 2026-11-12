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
        compressed=zlib.compress(raw,level=6)
        with self._connect() as conn:
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

    def save_bytes(self,key,raw,*,source_revision='',max_bytes=2_000_000):
        if len(raw)>max_bytes:
            self.record('cache',key,'payload_above_cache_limit',
                        detail='bytes='+str(len(raw)))
            return None
        return self._store(key,'bytes',raw,source_revision=source_revision)

    def stats(self):
        with self._connect() as conn:
            counts=dict(conn.execute('''SELECT kind || ':' || outcome,COUNT(*)
                FROM call_events GROUP BY kind,outcome''').fetchall())
            cached=conn.execute('SELECT COUNT(*) FROM verified_cache').fetchone()[0]
            total=conn.execute('SELECT COUNT(*) FROM call_events').fetchone()[0]
        return {'events':total,'cachedResponses':cached,'counts':counts}
