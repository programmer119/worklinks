#!/usr/bin/env python3
"""HWP5 ColumnSet failure falls back to all sections, without trusting PrvText."""
import io,json,sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import refresh_worklinks_rfp as r
import repair_open_rfp_cached_attachments as repair

ctl=b''.join(n.to_bytes(2,'little') for n in
              (0x0010,0x6364,0x7365,0,0,0,0,0x0010))
encoded='입찰'.encode('utf-16-le')+ctl+'참가자격: 개발자 2명'.encode('utf-16-le')
assert r.decode_hwp_paragraph_bytes(encoded)=='입찰참가자격: 개발자 2명'

class FakeOle:
    def __init__(self,raw):pass
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def listdir(self):return [['FileHeader'],['BodyText','Section0'],['BodyText','Section1']]
class FakeOleModule:
    OleFileIO=FakeOle

payload=' '.join('%02x'%v for v in encoded)
def fake_run(cmd,**kwargs):
    if cmd[0]=='hwp5txt':
        return SimpleNamespace(returncode=1,stdout=b'',
                               stderr=b'AssertionError: ColumnSet')
    if cmd[0]=='hwp5proc' and cmd[1]=='records':
        return SimpleNamespace(returncode=0,
            stdout=json.dumps([{'tagid':66,'payload':['00']},
                              {'tagid':67,'payload':[payload]}]).encode(),
            stderr=b'')
    raise AssertionError('no other subprocess is permitted '+repr(cmd))

with patch.dict(sys.modules,{'olefile':FakeOleModule()}),\
     patch.object(r.subprocess,'run',side_effect=fake_run):
    hwp=bytes.fromhex('D0CF11E0A1B11AE1')+b'\x00'*120
    text,evidence=r.extract_with_source_status('proposal.hwp',hwp)
    assert text.count('입찰참가자격: 개발자 2명')==2,text
    assert evidence['sourceComplete'] is True
    assert evidence['extractionMethod']=='hwp_record_fallback',evidence

# An incomplete section must never be declared completely parsed.
def failed_section(cmd,**kwargs):
    if cmd[0]=='hwp5proc':
        return SimpleNamespace(returncode=1,stdout=b'',stderr=b'broken')
    return fake_run(cmd,**kwargs)
with patch.dict(sys.modules,{'olefile':FakeOleModule()}),\
     patch.object(r.subprocess,'run',side_effect=failed_section):
    try:
        r.extract_with_source_status('proposal.hwp',hwp)
        raise AssertionError('broken HWP section must be rejected')
    except ValueError as exc:
        assert str(exc)=='hwp_record_fallback_failed',str(exc)

# A government-provided HML ending in a half-written tag is incomplete source,
# not a supported document that may be silently counted as fully reviewed.
try:
    r.extract('notice.hml',
      b'<?xml version="1.0"?><HWPML><BODY><CHAR>Test</CHAR></BODY><COM')
    raise AssertionError('malformed source must not pass')
except ValueError as exc:
    assert str(exc)=='hml_xml_truncated',str(exc)

assert repair.READER_ATTEMPT_VERSION.endswith('v15-20261116')
print('RFP_HWP5_RECORD_FALLBACK_AND_TRUNCATED_HML=PASS')
