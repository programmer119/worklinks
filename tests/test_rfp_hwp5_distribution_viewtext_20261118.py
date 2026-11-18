#!/usr/bin/env python3
"""HWP distribution copies are decoded from real ViewText, never PrvText."""
import io,json,sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import refresh_worklinks_rfp as reader

hangul='계약 서약서 입찰 기준 및 제출 서류 확인'
encoded=hangul.encode('utf-16-le')
payload=' '.join(f'{b:02x}' for b in encoded)
commands=[]
flags=5
class FakeOle:
    def __init__(self,source):pass
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def listdir(self):
        return [['FileHeader'],['BodyText','Section0'],['ViewText','Section0']]
    def openstream(self,name):
        assert name=='FileHeader'
        sig=b'HWP Document File'
        return io.BytesIO(sig+b'\x00'*(36-len(sig))+flags.to_bytes(4,'little'))
class FakeOleModule:
    OleFileIO=FakeOle

def fake_run(cmd,**kwargs):
    commands.append(cmd)
    assert cmd[:3]==['hwp5proc','records','--json']
    return SimpleNamespace(returncode=0,stdout=json.dumps([
        {'tagid':66,'payload':['00']},
        {'tagid':67,'payload':[payload]}
    ]).encode(),stderr=b'')

with patch.dict(sys.modules,{'olefile':FakeOleModule()}),patch.object(reader.subprocess,'run',side_effect=fake_run):
    assert hangul in reader.extract_hwp_record_paragraphs(b'TRUSTED_TEST_SOURCE')
    assert commands[-1][-1]=='ViewText/Section0',commands[-1]
    flags=1
    assert hangul in reader.extract_hwp_record_paragraphs(b'TRUSTED_TEST_SOURCE')
    assert commands[-1][-1]=='BodyText/Section0'
    flags=7
    before=len(commands)
    try:reader.extract_hwp_record_paragraphs(b'TRUSTED_TEST_SOURCE')
    except ValueError as exc:
        assert str(exc)=='hwp_record_fallback_protected'
    else:raise AssertionError('password file was accepted')
    assert len(commands)==before
print('HWP_DISTRIBUTED_VIEWTEXT_AND_NORMAL_BODYTEXT_NO_FAKED_SUCCESS=PASS')
