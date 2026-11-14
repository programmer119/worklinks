#!/usr/bin/env python3
"""No-network verification: eight download workers independent from scan workers."""
import hashlib
import os
from pathlib import Path
import sys
import threading
import time
from unittest import mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import refresh_worklinks_rfp as r

# Scheduler must accept eight independent raw downloads and globally pace
# official file request starts. Simulate artificial network to measure workers.
busy=0
maximum=0
observed=set()
lock=threading.Lock()
def simulated_download(url,*,rate_gate=None):
    global busy,maximum
    assert rate_gate is not None
    rate_gate.acquire()
    with lock:
        busy+=1
        maximum=max(maximum,busy)
        observed.add(url)
    time.sleep(.12)
    with lock:busy-=1
    return ('original:'+url).encode()

with mock.patch.object(r,'download',side_effect=simulated_download):
    with r.DownloadPrefetch(max_workers=8) as prefetch:
        assert prefetch.workers==8
        urls=['https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/f'+str(i) for i in range(8)]
        jobs=[prefetch.submit('R26BK01800001:000','2026-11-20',url) for url in urls]
        copied=prefetch.submit('R26BK01800002:000','2026-11-21',urls[0])
        assert copied is jobs[0], 'same URL must share one in-flight request'
        results=[f.result() for f in jobs]
        assert len(observed)==8,observed
        assert all(d==('original:'+u).encode() for (d,_),u in zip(results,urls))
        assert prefetch.stats()['workers']==8
        assert prefetch.stats()['coalesced']==1
        assert prefetch.stats()['networkAttempts']==8
        assert maximum<=8
        for u,f in zip(urls,jobs):prefetch.release(u,f)

# The ordinary 4-scanner pool is separate from the download queue. Under
# different download latencies, all eight requests still start.
assert maximum>=2,maximum

# A PDF must be parsed before its HWP companion is even downloaded. If PDF
# fails, fallback HWP will use the same download pool on demand.
manifest=[
  {'name':'requirements.hwp','url':'https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/hwp'},
  {'name':'requirements.pdf','url':'https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/pdf'},
  {'name':'other.hwp','url':'https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/other'},
  {'name':'saved.pdf','url':'https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/saved'},
]
positions=r._eligible_prefetch_positions(manifest,[1,3,0,2],{
    ('saved.pdf',manifest[3]['url']):{
      'staffingRoleScanVersion':r.STAFFING_ROLE_SCAN_VERSION,
      'staffingFactScanVersion':r.STAFFING_FACT_SCAN_VERSION,
      'staffingRoleScanTruncated':False}})
assert positions==[1,2],positions
print('RFP_DOWNLOAD_8_INDEPENDENT_WORKERS=PASS',
      {'unique':len(observed),'coalesced':1,'maximumParallel':maximum,
       'officialStartsPerSecond':4,'pdfFirst':True},flush=True)
