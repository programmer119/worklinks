#!/usr/bin/env python3
"""Source-backed cleanup: remove obsolete parser errors from confirmed successes."""
import argparse
import gzip
import json
import os
from pathlib import Path
import shutil
import tempfile

def atom(path,raw):
    fd,name=tempfile.mkstemp(prefix='.'+path.name+'.',suffix='.tmp',dir=str(path.parent))
    try:
        with os.fdopen(fd,'wb') as f:
            f.write(raw);f.flush();os.fsync(f.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)

def run(root):
    file=Path(root)/'snapshots'/'rfp-coverage-index.json'
    data=json.loads(file.read_text(encoding='utf-8'))
    rows=data.get('byNotice')
    assert data.get('ok') is True and isinstance(rows,dict) and len(rows)>100, 'RFP_SNAPSHOT_INVALID'
    total=0;examples=[];files=0
    for key,obj in rows.items():
        if not isinstance(obj,dict):continue
        for f in obj.get('files') or []:
            if not isinstance(f,dict):continue
            files+=1
            if (f.get('readable') is True and
                f.get('sourceTextScanComplete') is True and
                isinstance(f.get('sourceSha256'),str) and
                len(f['sourceSha256'])==64):
                old=f.get('errorCategory') or f.get('error')
                if old:
                    total+=1
                    if len(examples)<15:
                        examples.append({'bid':key,'name':f.get('name'),
                                         'oldError':f.get('errorCategory') or ''})
                    for field in ('errorCategory','error','lastHttpStatus'):
                        f.pop(field,None)
    if total:
        backup=Path(str(file)+'.pre-ocr-error-cleanup')
        if not backup.exists():shutil.copy2(file,backup)
        raw=(json.dumps(data,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
        atom(file,raw)
        atom(Path(str(file)+'.gz'),gzip.compress(raw,compresslevel=5,mtime=0))
    print('RFP_CONFIRMED_SUCCESS_ERROR_CLEANUP '+json.dumps({
       'indexedNotices':len(rows),'filesReviewed':files,
       'staleErrorsRemoved':total,'examples':examples,
       'noGovernmentAPICalls':True},ensure_ascii=False),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--data-dir',required=True)
    args=p.parse_args()
    run(args.data_dir)
