#!/usr/bin/env python3
"""Offline regression for A02/B123 using one protected operating key file."""
import os
from pathlib import Path
import runpy
import tempfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as work:
    a=Path(work)/'g2b.env'
    b=Path(work)/'g2b-standard.env'
    a.write_text('G2B_SERVICE_KEY=legacy-key-do-not-use-for-A02\n',encoding='utf-8')
    b.write_text('G2B_STANDARD_SERVICE_KEY=approved-operating-test-key\n',encoding='utf-8')
    env={
        'G2B_SECRET_PATH':str(a),
        'G2B_OPERATING_KEY_PATH':str(b),
        'G2B_SERVICE_KEY':'legacy-env-override-must-not-win-A02'
    }
    with patch.dict(os.environ,env):
        proxy=runpy.run_path(str(ROOT/'server'/'g2b-proxy.py'),
                             run_name='shared_g2b_key_test')
        crawler=runpy.run_path(str(ROOT/'server'/'g2b-full-crawler.py'),
                               run_name='shared_g2b_crawler_test')
        assert proxy['get_a02_key']()=='approved-operating-test-key'
        assert proxy['get_key']()=='legacy-env-override-must-not-win-A02'
        assert crawler['secret']()=='approved-operating-test-key'
        # Missing/invalid operating key MUST NOT silently fall back to old A02.
        b.write_text('UNRELATED_CONFIG=value\n',encoding='utf-8')
        assert proxy['get_a02_key']()==''
        try:
            crawler['secret']()
        except RuntimeError as exc:
            assert str(exc)=='g2b_operating_key_missing'
        else:
            raise AssertionError('crawler fell back to old key')
    for name in ('deploy-g2b-api-only.sh','deploy-g2b-crawler-only.sh'):
        deploy=(ROOT/'server'/name).read_text(encoding='utf-8')
        assert '-e G2B_OPERATING_KEY_PATH=/run/secrets/g2b-standard.env' in deploy
        assert '-v "$OPERATING_SECRET:/run/secrets/g2b-standard.env:ro"' in deploy
        assert 'g2b-standard.env' in deploy
print('A02_B123_SINGLE_OPERATING_KEY_FAIL_CLOSED_NO_NETWORK=PASS',flush=True)
