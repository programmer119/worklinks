#!/usr/bin/env python3
"""No-network server123 cached JSON / gzip / CORS snapshot endpoint regression."""
import gzip
import importlib.util
import io
import json
from pathlib import Path
import tempfile

source=Path(__file__).resolve().parents[1]/'server'/'g2b-proxy.py'
spec=importlib.util.spec_from_file_location('g2b_snapshot_api',str(source))
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
with tempfile.TemporaryDirectory() as d:
    module.SNAPSHOT_ROOT=d
    source=Path(d)/'changcom-actionable.json'
    content=b'{"ok":true,"bids":[]}'
    source.write_bytes(content)
    with gzip.open(str(source)+'.gz','wb') as gz:
        gz.write(content)
    class HandlerHarness(module.Handler):
        def __init__(self,headers):
            self.headers=headers
            self.calls=[]
            self.wfile=io.BytesIO()
        def send_response(self,status,*args):
            self.calls.append(('status',status))
        def send_header(self,key,value):
            self.calls.append((key,value))
        def end_headers(self):pass
    no_upstream=[]
    module.request_api=lambda *a,**kw:no_upstream.append(1)
    h=HandlerHarness({'Accept-Encoding':'gzip',
                      'Origin':'https://worklinks.suaveforge.com'})
    h.reply_snapshot('changcom-actionable')
    assert ('status',200) in h.calls,h.calls
    assert ('Content-Encoding','gzip') in h.calls,h.calls
    assert ('Access-Control-Allow-Origin','https://worklinks.suaveforge.com') in h.calls
    assert gzip.decompress(h.wfile.getvalue())==content
    h2=HandlerHarness({'Accept-Encoding':'identity'})
    h2.reply_snapshot('changcom-actionable')
    assert h2.wfile.getvalue()==content
    assert ('Content-Encoding','gzip') not in h2.calls
    h3=HandlerHarness({})
    h3.reply_snapshot('../secrets/g2b.env')
    assert ('status',400) in h3.calls
    h4=HandlerHarness({})
    h4.reply_snapshot('rfp-clauses')
    assert ('status',404) in h4.calls
    assert not no_upstream, 'cached snapshot call cannot query any government API'
print('WORKLINKS_SERVER123_LOCAL_GZIP_SNAPSHOT_API=PASS')
