#!/usr/bin/env python3
"""Factual RFP worker telemetry. Never calls upstream APIs or starts jobs."""
import json
import os
import sqlite3
import threading
import time
from pathlib import Path

def database_path():
    return os.environ.get('WORKLINKS_RFP_DUAL_QUEUE_DB') or str(Path(os.environ.get('G2B_PIPELINE_DATA','/app/data'))/'rfp-dual-queue.sqlite3')

_SCHEMA_LOCK=threading.Lock()
_SCHEMA_READY=set()

def connect(path=None):
    target=str(path or database_path())
    db=sqlite3.connect(target,timeout=3)
    db.execute('PRAGMA busy_timeout=3000')
    if target not in _SCHEMA_READY:
        with _SCHEMA_LOCK:
            if target not in _SCHEMA_READY:
                db.execute('''CREATE TABLE IF NOT EXISTS rfp_live_events(
                    lane TEXT NOT NULL, notice_key TEXT NOT NULL, file_key TEXT NOT NULL,
                    file_name TEXT NOT NULL DEFAULT '',phase TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,bytes_done INTEGER NOT NULL DEFAULT 0,
                    bytes_total INTEGER NOT NULL DEFAULT 0,files_done INTEGER NOT NULL DEFAULT 0,
                    files_total INTEGER NOT NULL DEFAULT 0,retry_epoch REAL NOT NULL DEFAULT 0,
                    error_text TEXT NOT NULL DEFAULT '',updated_epoch REAL NOT NULL,
                    started_epoch REAL NOT NULL DEFAULT 0,
                    byte_progress_epoch REAL NOT NULL DEFAULT 0,
                    PRIMARY KEY(lane,notice_key,file_key))''')
                db.execute('''CREATE TABLE IF NOT EXISTS rfp_live_workers(
                    lane TEXT PRIMARY KEY,status TEXT NOT NULL,error_text TEXT NOT NULL DEFAULT '',
                    retry_epoch REAL NOT NULL DEFAULT 0,updated_epoch REAL NOT NULL)''')
                # Existing server123 DB is preserved; these columns are additive.
                columns={row[1] for row in db.execute('PRAGMA table_info(rfp_live_events)')}
                for name in ('started_epoch','byte_progress_epoch'):
                    if name not in columns:
                        db.execute('ALTER TABLE rfp_live_events ADD COLUMN '+name+
                                   ' REAL NOT NULL DEFAULT 0')
                db.commit()
                _SCHEMA_READY.add(target)
    return db

def record(lane,notice_key,file_key='',file_name='',phase='',status='working',
           bytes_done=0,bytes_total=0,files_done=0,files_total=0,retry_epoch=0,error=''):
    if lane not in ('manifest','download','scan'):return
    now=time.time()
    with connect() as db:
        db.execute('''INSERT INTO rfp_live_events(
            lane,notice_key,file_key,file_name,phase,status,bytes_done,bytes_total,
            files_done,files_total,retry_epoch,error_text,updated_epoch,
            started_epoch,byte_progress_epoch)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(lane,notice_key,file_key) DO UPDATE SET
            file_name=excluded.file_name,phase=excluded.phase,status=excluded.status,
            bytes_done=excluded.bytes_done,bytes_total=excluded.bytes_total,
            files_done=excluded.files_done,files_total=excluded.files_total,
            retry_epoch=excluded.retry_epoch,error_text=excluded.error_text,
            updated_epoch=excluded.updated_epoch,
            started_epoch=CASE
                WHEN excluded.status='working' AND rfp_live_events.status='working'
                    AND rfp_live_events.started_epoch>0
                THEN rfp_live_events.started_epoch
                ELSE excluded.started_epoch END,
            byte_progress_epoch=CASE
                WHEN excluded.bytes_done>rfp_live_events.bytes_done
                  OR (excluded.status='working' AND rfp_live_events.status<>'working')
                  OR excluded.bytes_done<rfp_live_events.bytes_done
                THEN excluded.updated_epoch
                ELSE rfp_live_events.byte_progress_epoch END''',
            (lane,str(notice_key)[:100],str(file_key)[:80],str(file_name)[:180],
             str(phase)[:80],str(status)[:24],max(0,int(bytes_done or 0)),
             max(0,int(bytes_total or 0)),max(0,int(files_done or 0)),
             max(0,int(files_total or 0)),float(retry_epoch or 0),str(error)[:180],
             now,now,now))
        if lane=='scan':
            # The parent scheduler is blocked while the child scanner runs.
            # Refresh scan worker heartbeat from actual file-level evidence;
            # a previous 'waiting_for_download' must not remain on screen.
            db.execute("""INSERT INTO rfp_live_workers(
                lane,status,error_text,retry_epoch,updated_epoch)
                VALUES('scan','running','',0,?)
                ON CONFLICT(lane) DO UPDATE SET status='running',
                    error_text='',retry_epoch=0,updated_epoch=excluded.updated_epoch""",
                (now,))

def worker(lane,status,error='',retry_epoch=0):
    if lane not in ('manifest','download','scan'):return
    with connect() as db:
        db.execute('''INSERT INTO rfp_live_workers(lane,status,error_text,retry_epoch,updated_epoch)
          VALUES(?,?,?,?,?) ON CONFLICT(lane) DO UPDATE SET
          status=excluded.status,error_text=excluded.error_text,
          retry_epoch=excluded.retry_epoch,updated_epoch=excluded.updated_epoch''',
          (lane,str(status)[:32],str(error)[:180],float(retry_epoch or 0),time.time()))


def recover_interrupted_downloads():
    """Release orphaned file activity on downloader subprocess restart.

    The durable notice queue is reset separately by RfpDualQueue.reset_stale;
    archived verified originals remain intact and are reused.
    """
    with connect() as db:
        now=time.time()
        return db.execute('''UPDATE rfp_live_events
            SET status='retry',phase='다운로드 프로세스 재시작 · 복구',
                retry_epoch=?,error_text='worker_restart_reclaim',
                updated_epoch=? WHERE lane='download' AND file_key<>''
                AND status='working' ''',(now,now)).rowcount

def stalled_downloads(notice_keys,idle_seconds=180,path=None,min_updated_epoch=0):
    """Observe only this process's currently claimed files; no API requests.

    The separate download parent can relaunch a non-responsive subprocess
    after a verified, long *no-byte-progress* period. Duration alone is not
    treated as failure while bytes keep arriving.
    """
    keys=list(dict.fromkeys(str(key) for key in notice_keys if key))
    if not keys:return []
    target=str(path or database_path())
    if not os.path.isfile(target):return []
    try:
        with sqlite3.connect('file:'+target+'?mode=ro',uri=True,timeout=2) as db:
            cols={row[1] for row in db.execute('PRAGMA table_info(rfp_live_events)')}
            if 'byte_progress_epoch' not in cols:return []
            values=','.join('?' for _ in keys)
            rows=db.execute('''SELECT notice_key,file_key,file_name,
                    byte_progress_epoch,updated_epoch FROM rfp_live_events
                WHERE lane='download' AND file_key<>'' AND status='working'
                  AND phase='전송 중' AND updated_epoch>=? AND notice_key IN ('''+values+''')''',
                [float(min_updated_epoch or 0),*keys]).fetchall()
        now=time.time()
        return [{'noticeKey':key,'fileKey':fk,'fileName':name,
                 'idleSeconds':int(now-(advanced or updated))}
                for key,fk,name,advanced,updated in rows
                if now-(advanced or updated)>idle_seconds]
    except (sqlite3.Error,OSError):return []

def snapshot(path=None,limit=12):
    target=path or database_path()
    if not os.path.isfile(target):return {'available':False}
    now=time.time()
    try:
        with sqlite3.connect('file:'+str(target)+'?mode=ro',uri=True,timeout=2) as db:
            # Older live DBs are valid but have no activity tables.
            tables={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'rfp_live_events' not in tables:return {'available':False}
            entries=db.execute('''SELECT lane,notice_key,file_key,file_name,phase,status,
                bytes_done,bytes_total,files_done,files_total,retry_epoch,error_text,updated_epoch,
                started_epoch,byte_progress_epoch FROM rfp_live_events
                WHERE (status NOT IN ('done','skipped') OR updated_epoch>?)
                ORDER BY CASE WHEN status='working' THEN 0 WHEN status='retry' THEN 1 ELSE 2 END,
                    updated_epoch DESC LIMIT ?''',(now-120,int(limit))).fetchall()
            workers=db.execute('''SELECT lane,status,error_text,retry_epoch,updated_epoch
                FROM rfp_live_workers''').fetchall() if 'rfp_live_workers' in tables else []
            columns=('lane','noticeKey','fileKey','fileName','phase','status','bytesDone',
                     'bytesTotal','filesDone','filesTotal','retryEpoch','error','updatedEpoch',
                     'startedEpoch','byteProgressEpoch')
            return {'available':True,'asOfEpoch':now,
                    'items':[dict(zip(columns,row)) for row in entries],
                    'workers':{lane:{'status':status,'error':err,'retryEpoch':retry,
                                     'updatedEpoch':updated,
                                     'stale':now-updated>90} for lane,status,err,retry,updated in workers}}
    except (sqlite3.Error,OSError):
        return {'available':False}

# Telemetry is observational: a transient SQLite lock must never stop production
# downloads or scans. Persistent loss is visible as stale worker activity.
def _nonfatal(fn):
    def wrapped(*args,**kwargs):
        try:return fn(*args,**kwargs)
        except (sqlite3.Error,OSError):return None
    return wrapped

record=_nonfatal(record)
worker=_nonfatal(worker)

recover_interrupted_downloads=_nonfatal(recover_interrupted_downloads)
