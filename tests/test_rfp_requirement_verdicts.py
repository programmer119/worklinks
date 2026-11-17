#!/usr/bin/env python3
"""No-network tests for bid requirement decisions from full official document text."""
import pathlib
import sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
from rfp_requirement_verdicts import scan_file,summarize_notice,VERSION

def original(text,name='입찰공고문.pdf',sha='a'*64):
    return dict(name=name,readable=True,sourceTextScanComplete=True,
                qualificationScanTruncated=False,sourceSha256=sha,
                requirementScanVersion=VERSION,
                requirementVerdicts=scan_file(text,name,'https://www.g2b.go.kr/official.pdf'))

necessary=original('입찰참가자격: 최근 3년간 유사 용역 수행실적 1억원 이상 보유하여야 한다.\n'
                   '입찰 참가시 실적증명서를 제출하여야 한다.')
assert necessary['requirementVerdicts']['performance']['status']=='required'
assert necessary['requirementVerdicts']['directProduction']['status']=='not_required'
assert necessary['requirementVerdicts']['performance']['evidence'][0]['sourceFile']=='입찰공고문.pdf'
direct=original('입찰 참가 자격은 세부품명번호 1234567890에 해당하는 '
                '직접생산확인증명서를 소지하고 제출하여야 한다.',
                name='제안요청서.hwpx',sha='b'*64)
assert direct['requirementVerdicts']['directProduction']['status']=='required'
evaluation=original('정량평가항목: 유사사업 수행실적 평가(배점 10점).')
assert evaluation['requirementVerdicts']['performance']['status']=='not_required'
assert evaluation['requirementVerdicts']['performance']['hasEvaluation'] is True
absent=original('소프트웨어 사업자 신고 업체에 한하여 참가할 수 있다.')
assert absent['requirementVerdicts']['performance']['status']=='not_required'
assert absent['requirementVerdicts']['directProduction']['status']=='not_required'
uncertain=original('직접생산확인증명서 제출은 필요한 경우에만 요청한다.')
assert uncertain['requirementVerdicts']['directProduction']['status']=='review'
negated=original('입찰 시 수행실적증명서 제출은 불필요하다.\n직접생산확인증명서 제출 불필요.')
assert negated['requirementVerdicts']['performance']['status']=='not_required'
assert negated['requirementVerdicts']['directProduction']['status']=='not_required'
contradict=original('입찰참가자격: 수행실적 2억원 이상을 보유하여야 한다.\n'
                    '수행실적 제출은 불필요하다.')
assert contradict['requirementVerdicts']['performance']['status']=='review'
files=[necessary,direct,evaluation,absent]
done=summarize_notice(files,True)
assert done['complete'] is True
assert done['verdicts']['performance']['status']=='required'
assert done['verdicts']['directProduction']['status']=='required'
assert len(done['verdicts']['performance']['evidence'])>0
negative=summarize_notice([absent,evaluation],True)
assert negative['complete'] is True
assert negative['verdicts']['performance']['status']=='not_required'
assert negative['verdicts']['performance']['hasEvaluation'] is True
unreadable={'name':'보안내역.xlsx','readable':False,
            'errorCategory':'drm_protected_original_requires_authorized_decryption'}
partial=summarize_notice([absent,unreadable],True)
assert partial['complete'] is False
assert partial['verdicts']['performance']['status']=='review'
assert partial['verdicts']['directProduction']['status']=='review'
positive_even_partial=summarize_notice([direct,unreadable],True)
assert positive_even_partial['complete'] is False
assert positive_even_partial['verdicts']['directProduction']['status']=='required'
assert summarize_notice([absent],False)['verdicts']['performance']['status']=='review'
assert summarize_notice([dict(absent,qualificationScanTruncated=True)],True)['complete'] is False
assert summarize_notice([dict(absent,requirementScanVersion=0)],True)['complete'] is False
pdf=original('참가자격은 소프트웨어사업자 등록증을 제출한다.',
             name='공고서.pdf',sha='c'*64)
hwp={'name':'공고서.hwpx','readable':False,'sourceTextScanComplete':False,
     'skippedDuplicateFormat':True,'alternatePdfEvidence':'공고서.pdf',
     'alternatePdfSourceSha256':'c'*64}
same=summarize_notice([hwp,pdf],True)
assert same['complete'] is True
assert same['verdicts']['performance']['status']=='not_required'
assert summarize_notice([dict(hwp,alternatePdfSourceSha256='d'*64),pdf],True)['complete'] is False
assert summarize_notice([dict(hwp,skippedDuplicateFormat=False),pdf],True)['complete'] is False
# Do not infer negatives when the scan exceeded the scanner's full-text bound.
huge='가'*6_000_002
too_big=scan_file(huge,'연속문서.hwpx')
assert too_big['performance']['status']=='review'
# Evaluator-only score wording must not become mandatory participation proof.
assert scan_file('제안서 정량 평가: 수행실적 증명서 제출 시 가점 5점.',
                 '평가표.hwp')['performance']['status']!='required'
# A numerical threshold with genuine admission terms is mandatory.
assert scan_file('참가자격: 최근 3년간 수행실적 5억원 이상 보유한 업체',
                 '공고문.hwp')['performance']['status']=='required'
print('RFP_PERFORMANCE_DIRECT_PRODUCTION_FULL_SOURCE_VERDICTS_PASS')
