#!/usr/bin/env python3
"""No-network regression: original DRMONE bytes must not be mislabeled as corrupt ZIP."""
import io
import sys
import zipfile
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import refresh_worklinks_rfp as r

encrypted=bytes.fromhex('9b2044524d4f4e45')+b'  This Document is protected.'
assert r.detected_source_format('blueprint.xlsx',encrypted)=='drm_protected'
assert r.detected_source_format('request.hwpx',encrypted)=='drm_protected'

for name in ('blueprint.xlsx','request.hwpx'):
    try:
        r.extract(name,encrypted)
        raise AssertionError('DRM original must not be marked readable: '+name)
    except ValueError as error:
        assert str(error)=='drm_protected_original_requires_authorized_decryption'

with io.BytesIO() as stream:
    with zipfile.ZipFile(stream,'w') as archive:
        archive.writestr('request.hwpx',encrypted)
        archive.writestr('other.txt','Public notice text with staffing terms')
    real_zip=stream.getvalue()

assert zipfile.is_zipfile(io.BytesIO(real_zip))
try:
    r.extract('official-attachments.hwpx',real_zip)
    raise AssertionError('A DRM member must not be silently skipped')
except ValueError as error:
    assert str(error)=='drm_protected_original_requires_authorized_decryption'

assert r.classify_failure(ValueError('drm_protected_original_requires_authorized_decryption')) == 'drm_protected_original_requires_authorized_decryption'
print('RFP_VERIFIED_DRMONE_ORIGINAL_CLASSIFIED_WITHOUT_FALSE_SUCCESS=PASS')
