#!/usr/bin/env python3
"""No-network regression: persisted supplemental G2B API facts, with unknown != none."""
import json
import os
import pathlib
import runpy
import tempfile

root=pathlib.Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='worklinks-extra-') as d:
    os.environ['G2B_DB_PATH']=str(pathlib.Path(d)/'bids.sqlite3')
    mod=runpy.run_path(str(root/'server/g2b-proxy.py'),run_name='supplemental_unit_test')
    g=mod['bid_extra_query'].__globals__
    original=g['request_api']
    calls=[]
    no='R26BK01807134'
    def provider(base,operation,params):
        calls.append(operation)
        assert base.endswith('BidPublicInfoService02'),base
        assert params.get('bidNtceNo')==no
        assert params.get('bidNtceOrd')=='000'
        if operation=='getBidPblancListInfoServcPurchsObjPrdct02':
            return {'items':[{'bidNtceNo':no,'bidNtceOrd':'000',
                              'prdctClsfcNo':'8111189901','qty':'1'},
                             {'bidNtceNo':'R26BK00000001','prdctClsfcNo':'invalid'}],
                    'totalCount':2}
        if operation=='getBidPblancJntcontrctDutyRgnListInfo02':
            return {'items':[], 'totalCount':0}
        if operation=='getBidPblancIncntvRgnListInfo02':
            raise mod['ApiError']('upstream_http_403_SERVICE_ACCESS_DENIED_ERROR')
        raise AssertionError(operation)
    g['request_api']=provider
    try:
        result=mod['bid_extra_query'](no,'000')
        assert not result['complete'] and not result['ok']
        assert set(result['sources'])=={'serviceProducts','mandatoryJointRegion','regionalIncentives'}
        products=result['sources']['serviceProducts']
        assert products['ok'] and products['complete']
        assert len(products['items'])==1 and products['items'][0]['prdctClsfcNo']=='8111189901'
        region=result['sources']['mandatoryJointRegion']
        assert region['ok'] and region['complete'] and region['totalCount']==0
        denied=result['sources']['regionalIncentives']
        assert not denied['ok'] and denied['error'].startswith('upstream_http_403')
        assert len(calls)==3,calls
        again=mod['bid_extra_query'](no,'000')
        assert again['cached'] is True and len(calls)==3
        # UI reads saved bids only; even supplementary data cannot trigger G2B.
        mod['persist_bids']([{'kind':'servc','bidNo':no,'order':'0',
             'title':'정보시스템 기능 개선','closes':'2026-12-01'}])
        listing=mod['query_saved_bids'](50,0,True)
        assert listing['items'][0]['supplementalBidFacts']['sources']['serviceProducts']['ok']
        assert listing['items'][0]['supplementalBidFacts']['complete'] is False
        assert len(calls)==3,'saved listing triggered provider requests'
        print('WORKLINKS_SUPPLEMENTAL_SQLITE_CACHE=PASS',len(calls))
    finally:
        g['request_api']=original
