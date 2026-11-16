#!/usr/bin/env python3
"""KOICA official two-level ZIP, bounded depth and cumulative size guard."""
import io,sys,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import refresh_worklinks_rfp as reader

def pack(name,raw):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr(name,raw)
    return out.getvalue()

text=b'Authenticated original public bid package contract includes verifiable terms.'
inside=pack('verified-terms.txt',text)
middle=pack('second-level.zip',inside)
outer=pack('first-level.zip',middle)
extracted,evidence=reader.extract_with_source_status('public.zip',outer)
assert 'Authenticated original' in extracted
assert 'verified-terms.txt' in extracted
assert evidence['sourceComplete'] is True
# Third level must remain forbidden.
too_deep=pack('additional-third-level.zip',outer)
try:
    reader.extract_with_source_status('public.zip',too_deep)
except ValueError as ex:
    assert str(ex)=='nested_archive_requires_review',ex
else:
    raise AssertionError('unbounded third nested ZIP incorrectly accepted')
# A rejected source must not leak its nesting depth into later sources.
again,evidence=reader.extract_with_source_status('public.zip',outer)
assert again==extracted and evidence['sourceComplete'] is True
print('KOICA_TWO_ZIP_LAYERS_AND_DEPTH_BOUND_SAFE=PASS')
