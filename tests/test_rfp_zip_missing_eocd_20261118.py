#!/usr/bin/env python3
"""Safe exact 6-byte HWPX ZIP footer recovery. No source file is edited."""
import io
import pathlib
import sys
import zipfile
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
from refresh_worklinks_rfp import repair_truncated_zip_eocd,extract_with_source_status

def make_zip(content):
    bio=io.BytesIO()
    with zipfile.ZipFile(bio,'w',compression=zipfile.ZIP_DEFLATED) as arc:
        arc.writestr('mimetype','application/hwp+zip')
        arc.writestr('Contents/section0.xml',
            '<hp:document xmlns:hp="urn:hp"><hp:p><hp:t>'+content+
            '</hp:t></hp:p></hp:document>')
        arc.writestr('Contents/header.xml','<h:header xmlns:h="urn:header"/>')
    return bio.getvalue()

correct=make_zip('입찰참가자격은 서류 제출 조건을 준수하여야 한다.')
assert zipfile.is_zipfile(io.BytesIO(correct))
broken=correct[:-6]
assert broken.startswith(bytes.fromhex('504b0304'))
assert not zipfile.is_zipfile(io.BytesIO(broken))
fixed=repair_truncated_zip_eocd(broken)
assert fixed==correct,(len(fixed),len(correct))
assert zipfile.is_zipfile(io.BytesIO(fixed))
with zipfile.ZipFile(io.BytesIO(fixed)) as arc:
    assert arc.testzip() is None
    assert len(arc.infolist())==3
source,evidence=extract_with_source_status('규격서.hwpx',broken)
assert '입찰참가자격' in source
assert evidence['sourceComplete'] is True
assert evidence['verifiedTruncatedZipFooterRecoveries']==1
untouched,ev2=extract_with_source_status('규격서.hwpx',correct)
assert '입찰참가자격' in untouched
assert ev2['verifiedTruncatedZipFooterRecoveries']==0
for unsafe in (
    correct[:-7],correct[:-5],correct[:-22],
    b'PK'+b'x'*30,
    broken[:40]+bytes([broken[40]^255])+broken[41:],
    broken[:15]+bytes([broken[15]^255])+broken[16:]
):
    assert repair_truncated_zip_eocd(unsafe)==unsafe
    assert repair_truncated_zip_eocd(unsafe)!=correct
assert repair_truncated_zip_eocd(b'not a zip')==b'not a zip'
print('HWPX_CRC_VERIFIED_EXACT_SIX_BYTE_EOCD_RECOVERY_PASS')
