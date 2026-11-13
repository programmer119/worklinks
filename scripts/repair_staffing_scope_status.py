#!/usr/bin/env python3
"""Correct two verified RFP staffing *coverage flags*, not their original file errors.

Use only on server123's existing SHA-verified cumulative RFP index. No government
calls, attachment downloads or claim of bidder eligibility are made.
"""
import argparse
import datetime as dt
import gzip
import json
import os
from pathlib import Path
import tempfile
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from refresh_worklinks_rfp import (
    staffing_effective_file_complete,
    staffing_ancillary_form_without_extractable_text,
)

TARGETS=('R26BK01811303:000','R26BK01805618:000')
NOTE='제출용 단문 서식 텍스트 미추출 · 인력조건 판독 범위에서만 제외 (원본 실패 기록 보존)'

def apply(index_path,execute=False):
    path=Path(index_path)
    old_stat=path.stat()
    source=json.loads(path.read_text(encoding='utf-8'))
    assert source.get('ok') is True and isinstance(source.get('byNotice'),dict)
    notices=source['byNotice']
    assert len(notices)>100, 'unexpectedly small live RFP coverage archive'
    original_keys=set(notices)
    report=[]
    changed=False
    for key in TARGETS:
        item=notices.get(key)
        assert isinstance(item,dict), 'target notice absent: '+key
        files=item.get('files')
        assert isinstance(files,list) and len(files)>0, 'missing source files: '+key
        assert item.get('manifestComplete') is True, 'manifest not completed: '+key
        assert item.get('status')=='text_extracted_requires_review'
        excluded=[]
        for file in files:
            if staffing_ancillary_form_without_extractable_text(file):
                excluded.append(file.get('name'))
                if file.get('staffingScopeExcluded') is not True:
                    file['staffingScopeExcluded']=True
                    file['staffingScopeReason']=NOTE
                    changed=True
        assert len(excluded)==1, 'expected one precisely identified blank form: '+key
        checks=[staffing_effective_file_complete(file,files) for file in files]
        assert all(checks), 'incomplete core RFP staffing scan: '+key+' '+repr(checks)
        assert any(f.get('readable') is True and
            int(f.get('staffingRoleScanVersion') or 0)>=4
            for f in files), 'core scanner provenance absent: '+key
        before=item.get('staffingRoleScanComplete')
        if before is not True:
            item['staffingRoleScanComplete']=True
            item['staffingCoverageCorrectedAt']=dt.datetime.now(dt.timezone.utc).isoformat()
            changed=True
        report.append({'id':key,'beforeComplete':before,'afterComplete':True,
            'files':len(files),'excludedForms':excluded,'fileErrorsPreserved':{
                f['name']:f.get('errorCategory') for f in files if f.get('errorCategory')}})
    assert set(notices)==original_keys, 'archive keys changed'
    print('STAFFING_SOURCE_SCOPE_RECALC',json.dumps(report,ensure_ascii=False),flush=True)
    if not execute:
        print('STAFFING_SCOPE_PREFLIGHT=PASS_NO_WRITE',flush=True)
        return report
    if not changed:
        print('STAFFING_SCOPE_ALREADY_CORRECT=PASS',flush=True)
        return report
    # Do not silently clobber a concurrently published new RFP index.
    data=(json.dumps(source,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    assert len(data)<100_000_000, 'index size exceeds schema guard'
    parent=path.parent
    fd,json_tmp=tempfile.mkstemp(prefix='.staffing-two-',suffix='.json',dir=parent)
    gz_tmp=json_tmp+'.gz'
    try:
        with os.fdopen(fd,'wb') as out:
            out.write(data);out.flush();os.fsync(out.fileno())
        with gzip.open(gz_tmp,'wb',compresslevel=6) as zipped:
            zipped.write(data)
        current=path.stat()
        assert (current.st_size,current.st_mtime_ns)==(old_stat.st_size,old_stat.st_mtime_ns), \
            'index changed by another job; refusing stale overwrite'
        os.replace(json_tmp,path)
        os.replace(gz_tmp,Path(str(path)+'.gz'))
    finally:
        for stale in (json_tmp,gz_tmp):
            try:os.unlink(stale)
            except FileNotFoundError:pass
    now=json.loads(path.read_text(encoding='utf-8'))
    assert set(now['byNotice'])==original_keys
    assert all(now['byNotice'][key]['staffingRoleScanComplete'] is True for key in TARGETS)
    print('STAFFING_TWO_NOTICE_SOURCE_SCOPED_PUBLISHED=PASS',flush=True)
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--index',required=True,type=Path)
    p.add_argument('--execute',action='store_true')
    a=p.parse_args()
    apply(a.index,a.execute)
