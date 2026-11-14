#!/usr/bin/env python3
"""WorkLinks RFP live metrics: file bytes, independent lanes, retry, stall."""
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import rfp_live_activity as activity

with tempfile.TemporaryDirectory() as temp:
    path=str(Path(temp)/'live.sqlite3')
    os.environ['WORKLINKS_RFP_DUAL_QUEUE_DB']=path
    assert activity.snapshot()['available'] is False
    activity.worker('manifest','retry','provider quota',time.time()+3600)
    activity.worker('download','running')
    activity.worker('scan','running')
    activity.record('manifest','2026-11-14',phase='official detail',status='working',
                    files_done=2,files_total=3)
    activity.record('download','R26BK00000001:000',file_key='f1',
                    file_name='사업제안요청서.pdf',phase='전송 중',
                    bytes_done=524288,bytes_total=2097152,files_done=0,files_total=3)
    activity.record('scan','R26BK00000002:000',file_key='f2',
                    file_name='인력조건.hwp',phase='텍스트 추출',status='working')
    activity.record('download','R26BK00000003:000',phase='다운로드 실패',
                    status='retry',retry_epoch=time.time()+300,error='upstream_http_503')
    snapshot=activity.snapshot()
    assert snapshot['available'] and len(snapshot['items'])==4,snapshot
    workers=snapshot['workers']
    assert workers['manifest']['status']=='retry'
    assert workers['manifest']['retryEpoch']>time.time()+3500
    files=[row for row in snapshot['items'] if row['fileName']=='사업제안요청서.pdf']
    assert len(files)==1 and files[0]['bytesDone']==524288
    assert files[0]['bytesTotal']==2097152
    assert files[0]['filesTotal']==3
    error=[row for row in snapshot['items'] if row['status']=='retry']
    assert len(error)==1 and error[0]['retryEpoch']>time.time()+250
    activity.record('download','R26BK00000001:000',file_key='f1',
                    file_name='사업제안요청서.pdf',phase='저장 완료',
                    status='done',bytes_done=2097152,bytes_total=2097152)
    assert any(item['status']=='done' for item in activity.snapshot()['items'])
    # A lock on telemetry may not crash the actual workers.
    original=activity.connect
    def fail_connect(*args,**kwargs):
        raise OSError('telemetry unavailable')
    activity.connect=fail_connect
    assert activity.record('scan','abc') is None
    assert activity.worker('scan','running') is None
    activity.connect=original
print('WORKLINKS_RFP_LIVE_TELEMETRY=PASS')
