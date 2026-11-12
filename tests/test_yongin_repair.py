#!/usr/bin/env python3
"""No-network exact-two-file repair: preserves three good files and source evidence."""
import gzip,hashlib,importlib.util,json,sys,tempfile
from pathlib import Path
from unittest.mock import patch

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'scripts'))
spec=importlib.util.spec_from_file_location('one_off_yongin',root/'scripts/repair_yongin_signature_files_once.py')
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

names=list(mod.FILES)
assert len(names)==2
raws={name:source['magic']+b'-fake official binary-'+bytes([i])
      for i,(name,source) in enumerate(mod.FILES.items())}
for name in names:
    mod.FILES[name]['shaPrefix']=hashlib.sha256(raws[name]).hexdigest()[:20]
docs=[{'name':names[0],'readable':False,'errorCategory':'file_extract_failure'},
      {'name':'already-success-1.pdf','readable':True,'sourceTextScanComplete':True,
       'sourceSha256':'a'*64},
      {'name':'already-success-2.xlsx','readable':True,'sourceTextScanComplete':True,
       'sourceSha256':'b'*64},
      {'name':'already-success-3.hwpx','readable':True,'sourceTextScanComplete':True,
       'sourceSha256':'c'*64},
      {'name':names[1],'readable':False,'errorCategory':'file_extract_failure'}]
with tempfile.TemporaryDirectory() as tmp:
    p=Path(tmp)/'snapshots'
    p.mkdir()
    path=p/'rfp-coverage-index.json'
    record={'status':'text_extracted_requires_review',
            'manifestComplete':True,'readableDocumentCount':3,
            'unreadableDocumentCount':2,'reviewComplete':False,'files':docs,
            'changcomClauseEvidence':{'files':[],
               'clauseCandidates':{'industry_code':[{'text':'소프트웨어사업자 1468 등록',
                                                    'sourceFile':'existing.pdf'}]}}}
    path.write_text(json.dumps({'ok':True,'byNotice':{mod.NOTICE:record}}),encoding='utf-8')
    def fake_download(url):
        for name,src in mod.FILES.items():
            if src['url']==url:return raws[name]
        raise AssertionError('downloaded unexpected URL')
    original={d['name']:d['sourceSha256'] for d in docs if d['readable']}
    text=('입찰 참가 자격 소프트웨어사업자 1468 등록 필수.\n'
          '4대보험 가입확인서 제출은 입찰마감일 전까지 필요하다.\n'
          '사업수행자는 공동수급 조건을 확인하여야 한다.\n')*5
    with patch.object(mod,'download',side_effect=fake_download) as dl, \
         patch.object(mod,'extract',return_value=text):
        mod.repair(tmp)
        assert dl.call_count==2,dl.call_count
        mod.repair(tmp)
        assert dl.call_count==2,'no re-download after repaired'
    new=json.loads(path.read_text(encoding='utf-8'))
    saved=new['byNotice'][mod.NOTICE]
    assert len(saved['files'])==5
    assert saved['readableDocumentCount']==5 and saved['unreadableDocumentCount']==0
    assert all(f['readable'] and f['sourceTextScanComplete'] for f in saved['files'])
    assert all(next(f for f in saved['files'] if f['name']==name)['sourceSha256']==sha
               for name,sha in original.items())
    assert saved['reviewComplete'] is False
    assert saved['changcomClauseEvidence']['clauseCandidates']['industry_code']
    assert gzip.decompress(Path(str(path)+'.gz').read_bytes())==path.read_bytes()
print('YONGIN_TWO_FILE_REPAIR_NO_REDOWNLOAD_REGRESSION=PASS')
