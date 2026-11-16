#!/usr/bin/env python3
"""Regression: native PDF surrogate cannot crash child; raw HWP5 BodyText valid."""
import io
import json
import struct
import subprocess
import sys
import types
import zlib
from pathlib import Path
from unittest.mock import patch

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'scripts'))
import refresh_worklinks_rfp as reader

# Native MuPDF may emit a lone surrogate: the child must write parseable,
# UTF-8-safe framed JSON even if the native source's text is anomalous.
with __import__('tempfile').TemporaryDirectory() as folder:
    Path(folder,'refresh_worklinks_rfp.py').write_text(
        "def extract_with_source_status(name,raw):\n"
        "    return 'abc '+chr(0xd9f1)+' Korean contract eligibility',"
        "{'sourceComplete':True}\n")
    p=subprocess.run([sys.executable,'-c',reader._RFP_EXTRACT_CHILD_PROGRAM,
                      folder,'verified.zip'],input=b'compressed',
                     capture_output=True,timeout=15)
    assert p.returncode==0,(p.stderr,p.stdout[:200])
    text,ev=reader.decode_extraction_child_result(p.stdout)
    assert '\\ud9f1' in text and ev['unmappedUnicodeSurrogateEscapes'] is True
    text.encode('utf-8')

# HWP5 compressed OLE BodyText records: 10-bit tag, 10-bit level, 12-bit
# payload length. HWP_PARA_TEXT=67, section is raw-deflate when compressed.
def pack(tag,payload):
    assert len(payload)<4095
    return struct.pack('<I',tag+(len(payload)<<20))+payload

section=pack(66,b'\0\0')+pack(67,'공고문에는 중급 개발자 2명 투입'.encode('utf-16-le'))
section+=pack(67,'4대보험 가입증명 제출 필요'.encode('utf-16-le'))
compressed=zlib.compress(section)[2:-4]
header=bytearray(256)
header[:len(b'HWP Document File')]=b'HWP Document File'
struct.pack_into('<I',header,36,1)

class FakeOLE:
    def __init__(self,blob):self.blob=blob
    def __enter__(self):return self
    def __exit__(self,*a):return False
    def exists(self,name):return name in ('FileHeader','BodyText/Section0')
    def openstream(self,name):
        return io.BytesIO(bytes(header) if name=='FileHeader' else compressed)

with patch.dict(sys.modules,{'olefile':types.SimpleNamespace(OleFileIO=FakeOLE)}):
    content=reader.decode_hwp_bodytext_records_from_ole(
        b'verified HWP5 bytes',['BodyText/Section0'])
    assert '중급 개발자 2명' in content and '4대보험' in content,content
    invalid=compressed[:-6]
    # A truncated record stream must never produce falsely full coverage.
    class BrokenOLE(FakeOLE):
        def openstream(self,name):
            return io.BytesIO(bytes(header) if name=='FileHeader' else invalid)
    with patch.dict(sys.modules,{'olefile':types.SimpleNamespace(OleFileIO=BrokenOLE)}):
        try:reader.decode_hwp_bodytext_records_from_ole(b'x',['BodyText/Section0'])
        except ValueError:pass
        else:raise AssertionError('truncated HWP5 stream accepted as valid')
    class ProtectedOLE(FakeOLE):
        def openstream(self,name):
            h=bytearray(header)
            struct.pack_into('<I',h,36,0b10)
            return io.BytesIO(bytes(h) if name=='FileHeader' else compressed)
    with patch.dict(sys.modules,{'olefile':types.SimpleNamespace(OleFileIO=ProtectedOLE)}):
        try:reader.decode_hwp_bodytext_records_from_ole(b'x',['BodyText/Section0'])
        except ValueError as e:assert str(e)=='hwp_record_fallback_protected'
        else:raise AssertionError('protected HWP should require authorized reader')
print('HWP5_COMPRESSED_ALL_RECORDS_AND_SURROGATE_SAFE_FRAMED_JSON=PASS')
