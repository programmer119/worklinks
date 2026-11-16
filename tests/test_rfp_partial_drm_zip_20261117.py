#!/usr/bin/env python3
"""A DRMONE sibling must not prevent reading genuine plaintext ZIP entries."""
import io
import sys
import zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import refresh_worklinks_rfp as source
import repair_open_rfp_cached_attachments as repair

buf=io.BytesIO()
with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:
    z.writestr('verified-public-conditions.txt',
      '소프트웨어사업자 등록이 필요한 입찰 공고문이며 중급 개발자 2명 필요')
    z.writestr('secret-member.hwpx',bytes.fromhex('9b2044524d4f4e45')+b'drm_original')
    z.writestr('another-public-note.txt','4대보험 자료를 제출해야 합니다')
raw=buf.getvalue()
text,ev=source.extract_with_source_status('download.pdf',raw)
assert ev['sourceComplete'] is False
assert ev['protectedMemberCount']==1
assert ev['protectedArchiveMembers']==['secret-member.hwpx']
assert '중급 개발자 2명' in text and '4대보험' in text
# No success may leak into the verified full scan from these partial bytes.
damaged={'files':[{'name':'download.pdf','errorCategory':
    'drm_protected_original_requires_authorized_decryption',
    'lastReaderAttemptVersion':repair.READER_ATTEMPT_VERSION,
    'readable':False,'sourceTextScanComplete':False}]}
assert len(repair.reader_retry_files(damaged))==1
damaged['files'][0]['lastPartialDrmZipAttemptVersion']=repair.PARTIAL_DRM_ZIP_READER_VERSION
assert not repair.reader_retry_files(damaged)
# Entire DRM-only attachment remains unreadable.
try:
    source.extract_with_source_status('original.xlsx',
        bytes.fromhex('9b2044524d4f4e45')+b'protected original')
except ValueError as e:
    assert str(e)=='drm_protected_original_requires_authorized_decryption'
else:
    raise AssertionError('DRMONE raw original incorrectly decrypted')
# Whole bundle of only DRM files is also not full source.
protected=io.BytesIO()
with zipfile.ZipFile(protected,'w') as z:
    z.writestr('only.hwpx',bytes.fromhex('9b2044524d4f4e45')+b'x')
try:
    source.extract_with_source_status('container.zip',protected.getvalue())
except ValueError as e:
    assert str(e)=='drm_protected_original_requires_authorized_decryption'
else:
    raise AssertionError('DRM-only ZIP incorrectly accepted')
print('NONDRM_SIBLINGS_EXTRACTED_AND_DRM_MEMBER_STRICTLY_INCOMPLETE=PASS')
