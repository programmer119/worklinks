#!/usr/bin/env python3
"""Official G2B one-file URLs must NOT read sibling files from their ZIP wrapper."""
import io,runpy,zipfile
from pathlib import Path

src=runpy.run_path(str(Path(__file__).resolve().parents[1]/'scripts/refresh_worklinks_rfp.py'),
                   run_name='test_official_zip_member_identity')
extract=src['extract_with_source_status']

def package(files):
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name,raw in files:z.writestr(name,raw)
    return stream.getvalue()

def xlsx():
    return package([
        ('xl/workbook.xml',b'<workbook/>'),
        ('xl/worksheets/sheet1.xml',
         '<worksheet><sheetData><row r="1"><c t="inlineStr"><is><t>RFP SOURCE IDENTIFIED</t></is></c></row></sheetData></worksheet>'.encode())
    ])

drm=b'\x9b DRMONE' + b'not-authorized'
same_name='2027\ub144 \uac70\uc81c\uc2dc \uc0b0\ucd9c\ub0b4\uc5ed\uc11c v4.xlsx'
bundle=package([(same_name,xlsx()),('other-technical.pdf',drm)])
text,evidence=extract(same_name,bundle)
assert 'RFP SOURCE IDENTIFIED' in text,text
assert evidence['sourceComplete'] is True,evidence
assert evidence['pdfFiles']==0,evidence

doc=package([('requested.txt',b'THIS IS THE EXPECTED DOCUMENT'),('secret.hwpx',drm)])
text,evidence=extract('requested.txt',doc)
assert text=='THIS IS THE EXPECTED DOCUMENT',(text,evidence)

for wrong in ('missing.txt','secret.txt'):
    try:extract(wrong,doc)
    except ValueError as err:
        assert 'official_bundle_requested_member_missing' in str(err),err
    else:raise AssertionError('unrelated ZIP sibling was scanned as requested source')

ambiguous=package([('a/official.txt',b'aa'),('b/official.txt',b'bb')])
try:extract('official.txt',ambiguous)
except ValueError as err:
    assert 'official_bundle_requested_member_ambiguous' in str(err),err
else:raise AssertionError('ambiguous archive identity accepted')

# An explicitly named ZIP is intentionally a multi-document bundle.
zip_src=package([('one.txt',b'FIRST FORM SOURCE VALID'),('two.txt',b'SECOND FORM SOURCE VALID')])
text,details=extract('official-bundle.zip',zip_src)
assert 'FIRST FORM' in text and 'SECOND FORM' in text
assert details['sourceComplete'] is True
# A failed member must report its exact ZIP entry, not a generic ZIP OCR error.
unreadable=package([('good.txt',b'NORMAL RELEVANT TEXT'),('unsupported.cell',b'not-convertible')])
partial,evidence=extract('technical-bundle.zip',unreadable)
assert 'NORMAL RELEVANT TEXT' in partial,partial
assert evidence['sourceComplete'] is False,evidence
assert evidence['archiveFailedMemberCount']==1,evidence
assert evidence['archiveFailedMembers'][0]['name']=='unsupported.cell',evidence
assert evidence['archiveFailedMembers'][0]['errorCategory']=='hancom_cell_converter_required',evidence
assert not evidence['protectedMemberCount'],evidence

nested=package([('inner.zip',package([('unsupported.cell',b'not-convertible')]))])
try:extract('nested-technical-bundle.zip',nested)
except ValueError as err:
    assert 'zip_member=inner.zip' in str(err),err
    assert 'zip_member=unsupported.cell' in str(err),err
else:raise AssertionError('nested ZIP member failure had no provenance')

print('OFFICIAL_ZIP_MEMBER_IDENTITY_PASS')
