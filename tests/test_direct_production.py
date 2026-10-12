#!/usr/bin/env python3
import runpy
p=runpy.run_path('/app/api.py',run_name='test_run')
items=p['prod_normalize']([{'업체명':'창컴정보통신(주)','사업자번호':'130-81-85973','세부품목':'정보시스템개발서비스','유효기간 시작일':'20260201','유효기간 종료일':'2027.02.01'}],'1308185973')
assert len(items)==1
assert items[0]['product']=='정보시스템개발서비스'
assert items[0]['validFrom']=='2026-02-01'
assert items[0]['validTo']=='2027-02-01'
try:p['prod_normalize']([{'사업자번호':'1234567890','세부품목':'기타'}],'1308185973')
except p['ApiError'] as ex:assert ex.msg=='production_filter_mismatch'
else:raise AssertionError('Should reject other company records')
print('DIRECT_PRODUCTION_PREFLIGHT=PASS')
