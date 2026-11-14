#!/usr/bin/env python3
"""No-network regression: real parser reuses extracted source text and drains first-time bids."""
import datetime as dt
import hashlib
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import refresh_worklinks_rfp as m
from rfp_call_ledger import CallLedger

with tempfile.TemporaryDirectory() as folder:
    ledger=CallLedger(Path(folder)/'ledger.sqlite3')
    raw=b'local verified source from server123'
    extract_calls=[]
    def extract(name,content):
        extract_calls.append((name,hashlib.sha256(content).hexdigest()))
        return 'Qualification and staffing sample\nPM 2\uba85',{'sourceComplete':True}
    with patch.object(m,'active_rfp_ledger',return_value=ledger),\
         patch.object(m,'extract_with_source_status',side_effect=extract):
        first=m.extract_cached_text('requirements.hwp',raw)
        second=m.extract_cached_text('requirements.hwp',raw)
        assert first[2] is False and second[2] is True,(first,second)
        assert len(extract_calls)==1,extract_calls
        changed=m.extract_cached_text('requirements.hwp',raw+b' changed')
        assert changed[2] is False and len(extract_calls)==2
        different_format=m.extract_cached_text('requirements.pdf',raw)
        assert different_format[2] is False and len(extract_calls)==3
    def incomplete(name,content):
        return 'partial',{'sourceComplete':False}
    with patch.object(m,'active_rfp_ledger',return_value=ledger),\
         patch.object(m,'extract_with_source_status',side_effect=incomplete):
        incomplete_result=m.extract_cached_text('blank.pdf',b'other raw')
        assert incomplete_result[2] is False
        again=m.extract_cached_text('blank.pdf',b'other raw')
        assert again[2] is False  # incomplete text cannot be a reliable cache hit

now=dt.datetime.now(dt.timezone(dt.timedelta(hours=9)))
deadline=(now+dt.timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')
items=[
 {'bidNo':'R26BK01800001','order':'000','kind':'servc','closes':deadline},
 {'bidNo':'R26BK01800002','order':'000','kind':'servc','closes':deadline},
 {'bidNo':'R26BK01800003','order':'000','kind':'servc','closes':deadline}]
prior={'R26BK01800001:000':{'status':'text_extracted_requires_review',
      'classificationVersion':m.CLASSIFICATION_VERSION-1,'hwpxReaderVersion':m.HWPX_READER_VERSION,
      'checkedAt':'2026-11-13T00:00:00+00:00','files':[{'readable':True,'sourceSha256':'a'*64}],
      'readableDocumentCount':1}}
with patch.dict(os.environ,{'WORKLINKS_RFP_UPGRADE_ONLY':'1'}),\
     patch.object(m,'fetch_json',return_value={'ok':True,'totalCount':len(items),'items':items}):
    selected=m.discover(3,prior=prior,targets=set(),manifest_probe_out=[],priority=set())
    keys=[no+':'+ordn for no,ordn,_ in selected]
    assert keys==['R26BK01800001:000','R26BK01800002:000','R26BK01800003:000'],keys
print('RFP_SPEED_REGRESSION=PASS extraction-cache, hash-isolation, incomplete-not-cached, all-first-time-drain')
