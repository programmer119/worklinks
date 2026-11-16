#!/usr/bin/env python3
"""Prioritize repairable originals without starving notices with large manifests."""
import datetime as dt
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import repair_open_rfp_cached_attachments as repair

pdf={'name':'support.pdf','errorCategory':'pdf_ocr_incomplete','readable':False}
ole={'name':'bill.xls','errorCategory':'hwp5txt_failed','readable':False}
plain={'name':'contract.hwp','errorCategory':'no_searchable_text','readable':False}
hard={'name':'legacy.hwp','errorCategory':'hwp5txt_failed','readable':False}
huge={'name':'contract.pdf','errorCategory':'source_extraction_timeout_deferred','readable':False}
assert repair.repair_file_priority(hard)<repair.repair_file_priority(pdf)
assert repair.repair_file_priority(ole)<repair.repair_file_priority(hard)
assert repair.repair_file_priority(plain)<repair.repair_file_priority(huge)
zip_images={'name':'입찰공고자료(26G056-H).zip','errorCategory':'no_searchable_text','readable':False}
assert repair.repair_file_priority(zip_images)<repair.repair_file_priority(ole)
deferred={'name':'영향평가.hwpx','errorCategory':'hwpx_image_ocr_deferred_to_repair','readable':False}
assert repair.repair_file_priority(deferred)<repair.repair_file_priority(pdf)
long_rfp={'name':'제안요청서.hwpx','readable':True,
          'qualificationScanTruncated':True,'sourceTextScanComplete':False}
assert repair.repair_file_priority(long_rfp)<repair.repair_file_priority(pdf)

now=dt.datetime.now(dt.timezone.utc)
candidates=[
    (repair.repair_file_priority(hard),now,'R26BK00000001:000',{},'verified_download_queue',15),
    (repair.repair_file_priority(pdf),now+dt.timedelta(hours=1),'R26BK00000002:000',{},'verified_download_queue',1),
    (repair.repair_file_priority(ole),now+dt.timedelta(hours=2),'R26BK00000003:000',{},'verified_download_queue',10),
]
chosen,used=repair.choose_repair_batch(candidates,limit=3,max_files=8)
assert [x[0] for x in chosen]==[
    'R26BK00000003:000','R26BK00000001:000','R26BK00000002:000'
],chosen
assert used==7,used  # 3 HWP + 1 OCR + 3 XLS; large manifests remain eligible
assert [x[-1] for x in chosen]==[3,3,1],chosen
assert repair.choose_repair_batch(candidates,limit=2,max_files=3)[1]==3
assert repair.choose_repair_batch(candidates,limit=3,max_files=1)[1]==1
# Production OCR batches have three file slots: reserve two for
# never-attempted current reader failures and spend at most one per notice.
# Preserve a third slot for normal completion-first repairs.
legacy_a=(0,now,'legacy-A',{},'verified_download_queue',3,(0,3,45),True)
legacy_b=(0,now+dt.timedelta(hours=1),'legacy-B',{},'verified_download_queue',2,(0,2,16),True)
normal=(0,now,'completed-soon',{},'verified_download_queue',1,(0,1,1),False)
fair,fair_files=repair.choose_repair_batch([normal,legacy_a,legacy_b],
    limit=3,max_files=3,per_notice_cap=1,minimum_old_ocr=2)
assert [r[0] for r in fair]==['legacy-B','legacy-A','completed-soon'],fair
assert [r[-1] for r in fair]==[1,1,1] and fair_files==3,(fair,fair_files)
# A two-file legacy record cannot monopolize all three worker slots.
fair2,slots=repair.choose_repair_batch([legacy_a,normal],2,3,
    per_notice_cap=1,minimum_old_ocr=2)
assert [r[0] for r in fair2]==['legacy-A','completed-soon']
assert slots==2
# Reserved legacy-PDF OCR capacity must actually process the PDF OCR file
# rather than a higher-ranked failing ZIP or HWP attached to the same notice.
mixed={'files':[
    {'name':'standard-terms.zip','errorCategory':'no_searchable_text',
     'readable':False},
    {'name':'scanned-contract.pdf','errorCategory':'pdf_ocr_incomplete',
     'lastReaderAttemptVersion':'','readable':False},
    {'name':'unreadable-record.hwp','errorCategory':'invalid_hwp',
     'readable':False}
]}
default=repair.ordered_retry_files(mixed)
prioritized=repair.ordered_retry_files(mixed,prioritize_legacy_pdf_ocr=True)
assert default[0]['name']=='standard-terms.zip',default
assert prioritized[0]['name']=='scanned-contract.pdf',prioritized
assert repair.legacy_pdf_ocr_failure(prioritized[0])
assert not repair.legacy_pdf_ocr_failure({
    **prioritized[0],'lastReaderAttemptVersion':repair.READER_ATTEMPT_VERSION})
print('RFP_RESERVED_PDF_OCR_SLOT_SELECTS_ACTUAL_PDF_ERROR=PASS')

# While 26 official HWP filenames actually contained XML or ZIP, all three
# repair slots were reserved for PDF OCR. Reserve one per batch for format bugs.
format_failed={'name':'terms.hwp','errorCategory':'invalid_hwp','readable':False,
               'lastReaderAttemptVersion':'pdf25-blank-hwpml-strict-v14-20261116'}
assert repair.legacy_format_failure(format_failed)
mixed={'files':[
    {'name':'old-pdf.pdf','errorCategory':'pdf_ocr_incomplete','readable':False,
     'lastReaderAttemptVersion':''},format_failed]}
assert repair.ordered_retry_files(mixed,prioritize_format=True)[0]['name']=='terms.hwp'
format_item=(5,now,'format-source',{},'verified_download_queue',2,(0,2,12),False,True)
normal_item=(1,now,'normal',{},'verified_download_queue',1,(0,1,1),False,False)
selected,used=repair.choose_repair_batch([
    legacy_b+ (False,),legacy_a+(False,),format_item,normal_item],
    limit=3,max_files=3,per_notice_cap=1,
    minimum_old_ocr=2,minimum_format_fixes=1)
assert [x[0] for x in selected]==['legacy-B','legacy-A','format-source'],selected
assert used==3
print('RFP_OCR_PRIORITY_AND_LARGE_MANIFEST_FILE_BUDGET=PASS')
