#!/usr/bin/env python3
"""One-shot read-only WORKLINK diagnostic. Never print or persist API keys/URLs.

Compare the existing bid-service key and separately configured operating key
against the two registered G2B early-stage services. Four bounded requests.
No modifications to live crawler/DB or service-specific quotas.
"""
import datetime as dt
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

NOW=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime('%Y%m%d')
SERVICES={
    'plan':('https://apis.data.go.kr/1230000/ao/OrderPlanSttusService',
            'getOrderPlanSttusListServc'),
    'prespec':('https://apis.data.go.kr/1230000/ao/HrcspSsstndrdInfoService',
               'getPublicPrcureThngInfoServc'),
}
KEY_SOURCES={
    'existing_bid':('/run/secrets/g2b.env','G2B_SERVICE_KEY'),
    'operating_standard':('/run/secrets/g2b-standard.env','G2B_STANDARD_SERVICE_KEY')
}
ERROR_LABELS=(
    'SERVICE_ACCESS_DENIED_ERROR','SERVICE_KEY_IS_NOT_REGISTERED_ERROR',
    'PERMISSION_DENIED','SERVICE_KEY_IS_NULL','INVALID_REQUEST_PARAMETER_ERROR',
    'NO_OPENAPI_SERVICE_ERROR','LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR',
    'LIMITED_NUMBER_OF_SERVICE_REQUESTS_PER_SECOND_EXCEEDS_ERROR',
    'BLACKLIST_IP_ACCESS_ERROR','DEADLINE_HAS_EXPIRED_ERROR',
    'INVALID_KEY','ACCESS_DENIED','AUTH_ERROR',
)

def read_secret(filepath, variable):
    if not os.path.isfile(filepath):return None
    with open(filepath,encoding='utf-8') as fh:
        for line in fh:
            if line.startswith(variable+'='):
                raw=line.split('=',1)[1].strip().strip('"').strip("'")
                return raw or None
    return None

def code_only(body):
    # Response text may contain request echo / URL; never output it.
    txt=body[:16384].decode('utf-8','replace')
    for mark in ERROR_LABELS:
        if mark.lower() in txt.lower():return mark
    try:
        info=json.loads(txt)
        h=info.get('response',{}).get('header',{})
        result=str(h.get('resultCode') or info.get('resultCode') or '')
        return 'official_code_'+result if re.fullmatch(r'[0-9A-Za-z_-]{1,32}',result) else 'body_unclassified'
    except (ValueError,TypeError,AttributeError):pass
    try:
        root=ET.fromstring(txt)
        for name in ('returnReasonCode','resultCode','code'):
            val=root.findtext('.//'+name)
            if val and re.fullmatch(r'[0-9A-Za-z_-]{1,32}',val):return 'official_code_'+val
    except ET.ParseError:pass
    return 'body_unclassified'

def probe(stage,key):
    base,method=SERVICES[stage]
    args={'serviceKey':key,'type':'json','pageNo':'1','numOfRows':'1',
          'inqryDiv':'1','inqryBgnDt':NOW+'0000','inqryEndDt':NOW+'2359'}
    if stage=='plan':
        args.update({'orderBgnYm':NOW[:6],'orderEndYm':NOW[:6]})
    request_url=base+'/'+method+'?'+urllib.parse.urlencode(args)
    request=urllib.request.Request(request_url,headers={
        'Accept':'application/json','User-Agent':'WorkLinksKeyDiagnostic/1.0'})
    try:
        with urllib.request.urlopen(request,timeout=15) as resp:
            payload=resp.read(16384)
            return {'http':int(resp.getcode() or 200),'result':code_only(payload)}
    except urllib.error.HTTPError as exc:
        try:body=exc.read(16384)
        except OSError:body=b''
        return {'http':int(exc.code),'result':code_only(body)}
    except (urllib.error.URLError,TimeoutError,OSError):
        return {'http':0,'result':'connection_failed'}

def main():
    keys={tag:read_secret(*source) for tag,source in KEY_SOURCES.items()}
    results={'marker':'G2B_PREBID_AUTH_DIAG_V1',
             'key_sources_present':{k:bool(v) for k,v in keys.items()},
             'keys_identical':bool(keys['existing_bid'] and
                                   keys['existing_bid']==keys['operating_standard']),
             'probes':[]}
    for source,key in keys.items():
        if not key:continue
        for stage in SERVICES:
            results['probes'].append(dict(source=source,stage=stage,**probe(stage,key)))
    print(json.dumps(results,ensure_ascii=False,separators=(',',':')),flush=True)
    # A denied key should not make the diagnostic workflow look like a deploy failure.
    return results

if __name__=='__main__':main()
