#!/usr/bin/env python3
"""Factual RFP worker telemetry. Never calls upstream APIs or starts jobs."""
import json
import os
import sqlite3
import time
from pathlib import Path

def database_path():
    return os.environ.get('WORKLINKS_RFP_DUAL_QUEUE_DB') or str(Path(os.environ.get('G2B_PIPELINE_DATA','/app/data'))/'rfp-dual-queue.sqlite3')

def connect(path=None):
    db=sqlite3.connect(str(path or database_path()),timeout=3)
    db.execute('PRAGMA busy_timeout=3000')
    db.execute('''CREATE TABLE IF NOT EXISTS rfp_live_events(
        lane TEXT NOT NULL, notice_key TEXT NOT NULL, file_key TEXT NOT NULL,
        file_name TEXT NOT NULL DEFAULT '',phase TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL,bytes_done INTEGER NOT NULL DEFAULT 0,
        bytes_total INTEGER NOT NULL DEFAULT 0,files_done INTEGER NOT NULL DEFAULT 0,
        files_total INTEGER NOT NULL DEFAULT 0,retry_epoch REAL NOT NULL DEFAULT 0,
        error_text TEXT NOT NULL DEFAULT '',updated_epoch REAL NOT NULL,
        PRIMARY KEY(lane,notice_key,file_key))''')
    db.execute('''CREATE TABLE IF NOT EXISTS rfp_live_workers(
        lane TEXT PRIMARY KEY,status TEXT NOT NULL,error_text TEXT NOT NULL DEFAULT '',
        retry_epoch REAL NOT NULL DEFAULT 0,updated_epoch REAL NOT NULL)''')
    return db

def record(lane,notice_key,file_key='',file_name='',phase='',status='working',
           bytes_done=0,bytes_total=0,files_done=0,files_total=0,retry_epoch=0,error=''):
    if lane not in ('manifest','download','scan'):return
    with connect() as db:
        db.execute('''INSERT INTO rfp_live_events(
            lane,notice_key,file_key,file_name,phase,status,bytes_done,bytes_total,
            files_done,files_total,retry_epoch,error_text,updated_epoch)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(lane,notice_key,file_key) DO UPDATE SET
            file_name=excluded.file_name,phase=excluded.phase,status=excluded.status,
            bytes_done=excluded.bytes_done,bytes_total=excluded.bytes_total,
            files_done=excluded.files_done,files_total=excluded.files_total,
            retry_epoch=excluded.retry_epoch,error_text=excluded.error_text,
            updated_epoch=excluded.updated_epoch''',
            (lane,str(notice_key)[:100],str(file_key)[:80],str(file_name)[:180],
             str(phase)[:80],str(status)[:24],max(0,int(bytes_done or 0)),
             max(0,int(bytes_total or 0)),max(0,int(files_done or 0)),
             max(0,int(files_total or 0)),float(retry_epoch or 0),str(error)[:180],
             time.time()))

def worker(lane,status,error='',retry_epoch=0):
    if lane not in ('manifest','download','scan'):return
    with connect() as db:
        db.execute('''INSERT INTO rfp_live_workers(lane,status,error_text,retry_epoch,updated_epoch)
          VALUES(?,?,?,?,?) ON CONFLICT(lane) DO UPDATE SET
          status=excluded.status,error_text=excluded.error_text,
          retry_epoch=excluded.retry_epoch,updated_epoch=excluded.updated_epoch''',
          (lane,str(status)[:32],str(error)[:180],float(retry_epoch or 0),time.time()))

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
                bytes_done,bytes_total,files_done,files_total,retry_epoch,error_text,updated_epoch
                FROM rfp_live_events
                WHERE (status NOT IN ('done','skipped') OR updated_epoch>?)
                ORDER BY CASE WHEN status='working' THEN 0 WHEN status='retry' THEN 1 ELSE 2 END,
                    updated_epoch DESC LIMIT ?''',(now-120,int(limit))).fetchall()
            workers=db.execute('''SELECT lane,status,error_text,retry_epoch,updated_epoch
                FROM rfp_live_workers''').fetchall() if 'rfp_live_workers' in tables else []
            columns=('lane','noticeKey','fileKey','fileName','phase','status','bytesDone',
                     'bytesTotal','filesDone','filesTotal','retryEpoch','error','updatedEpoch')
            return {'available':True,'asOfEpoch':now,
                    'items':[dict(zip(columns,row)) for row in entries],
                    'workers':{lane:{'status':status,'error':err,'retryEpoch':retry,
                                     'updatedEpoch':updated,
                                     'stale':now-updated>90} for lane,status,err,retry,updated in workers}}
    except (sqlite3.Error,OSError):
        return {'available':False}
