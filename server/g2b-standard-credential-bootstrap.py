#!/usr/bin/env python3
"""One-time secure installation of the separate G2B public-data standard-service key.

Key comes ONLY from stdin (never argv, env, repository file, or logs).
Do not change the existing A02 service key. Requires 3 successful upstream checks
before writing the new credential in its own root-restricted secret file.
"""
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

EXPECTED_KEY_SHA256 = "45b84afe183091bda2e74a0d968e0b4f3fff39011daee29776699883fd33e36b"
BASE = "https://apis.data.go.kr/1230000/ao/PubDataOpnStdService/"
DEST = "/secrets/g2b-standard.env"
TESTS = (
    ("B1", "getDataSetOpnStdBidPblancInfo", {"pageNo": 1, "numOfRows": 1}),
    ("B2", "getDataSetOpnStdScsbidInfo", {"pageNo": 1, "numOfRows": 1, "bsnsDivCd": "5", "opengBgnDt": "20261101", "opengEndDt": "20261110"}),
    ("B3", "getDataSetOpnStdCntrctInfo", {"pageNo": 1, "numOfRows": 1}),
)

def call(label, operation, params, key):
    url = BASE + operation + "?" + urllib.parse.urlencode({**params, "serviceKey": key, "type": "json"})
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "WorkLinksG2BStandardBootstrap/1.0"})
    output = {"endpoint": label, "calls": 1}
    try:
        with urllib.request.urlopen(req, timeout=22) as r:
            output["http"] = r.status
            raw = r.read(500000)
    except urllib.error.HTTPError as e:
        output["http"] = e.code
        raw = e.read(30000)
    except (OSError, TimeoutError) as e:
        output["error_type"] = type(e).__name__
        return False, output
    try:
        data = json.loads(raw.decode("utf-8"))
        response = data.get("response") or {}
        header = response.get("header") or {}
        gateway = (data.get("OpenAPI_ServiceResponse") or {}).get("cmmMsgHeader") or {}
        output["result_code"] = str(header.get("resultCode") or "")
        output["response_root_keys"] = list(data.keys())[:6]
        output["result_message"] = str(header.get("resultMsg") or "")[:80]
        output["gateway_code"] = gateway.get("returnReasonCode")
        body = response.get("body") or {}
        output["total_count"] = body.get("totalCount")
        items = body.get("items") or []
        output["received"] = len(items) if isinstance(items, list) else None
    except (ValueError, UnicodeError, AttributeError, TypeError):
        output["format_error"] = True
    return output.get("http") == 200 and output.get("result_code") in ("00", "0"), output

def main():
    key = sys.stdin.buffer.read(4096).strip().decode("ascii")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", key):
        raise SystemExit("INVALID_KEY_FORMAT")
    if hashlib.sha256(key.encode()).hexdigest() != EXPECTED_KEY_SHA256:
        raise SystemExit("KEY_FINGERPRINT_MISMATCH")
    results = []
    for label, operation, params in TESTS:
        good, result = call(label, operation, params, key)
        print("B_STANDARD_LIVE_CHECK " + json.dumps(result, ensure_ascii=False), flush=True)
        results.append(good)
    if not all(results):
        print("B_STANDARD_KEY_NOT_INSTALLED", flush=True)
        return 2
    if os.path.exists(DEST):
        with open(DEST, encoding="utf-8") as fd:
            old = fd.read().strip()
        if old != "G2B_STANDARD_SERVICE_KEY=" + key:
            raise SystemExit("DIFFERENT_B_STANDARD_KEY_ALREADY_PRESENT")
        print("B_STANDARD_KEY_ALREADY_CORRECT", flush=True)
        return 0
    fd = os.open(DEST, os.O_CREAT | os.O_WRONLY | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("G2B_STANDARD_SERVICE_KEY=" + key + "\n")
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        try:
            os.unlink(DEST)
        except OSError:
            pass
        raise
    print("B_STANDARD_KEY_INSTALLED_SEPARATELY=YES", flush=True)
    print("A02_KEY_UNCHANGED=YES", flush=True)
    print("SECRET_VALUES_PRINTED=NO", flush=True)
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, UnicodeError, AttributeError, OSError):
        print("B_STANDARD_BOOTSTRAP_FAILED", flush=True)
        sys.exit(3)
