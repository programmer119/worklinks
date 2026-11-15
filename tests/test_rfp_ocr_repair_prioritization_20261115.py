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
assert repair.repair_file_priority(pdf)<repair.repair_file_priority(hard)
assert repair.repair_file_priority(ole)<repair.repair_file_priority(hard)
assert repair.repair_file_priority(plain)<repair.repair_file_priority(huge)

now=dt.datetime.now(dt.timezone.utc)
candidates=[
    (repair.repair_file_priority(hard),now,'R26BK00000001:000',{},'verified_download_queue',15),
    (repair.repair_file_priority(pdf),now+dt.timedelta(hours=1),'R26BK00000002:000',{},'verified_download_queue',1),
    (repair.repair_file_priority(ole),now+dt.timedelta(hours=2),'R26BK00000003:000',{},'verified_download_queue',10),
]
chosen,used=repair.choose_repair_batch(candidates,limit=3,max_files=8)
assert [x[0] for x in chosen]==[
    'R26BK00000002:000','R26BK00000003:000','R26BK00000001:000'
],chosen
assert used==7,used  # 1 OCR + 3 XLS + 3 HWP (not blocked by 10/15 members)
assert [x[-1] for x in chosen]==[1,3,3],chosen
assert repair.choose_repair_batch(candidates,limit=2,max_files=3)[1]==3
assert repair.choose_repair_batch(candidates,limit=3,max_files=1)[1]==1
print('RFP_OCR_PRIORITY_AND_LARGE_MANIFEST_FILE_BUDGET=PASS')
