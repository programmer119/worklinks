#!/usr/bin/env bash
# WorkLinks G2B installer for CentOS 7 default Python 2.7: no Node, pip or extra packages.
# Run as root in an interactive terminal. Service key is not stored in GitHub/CLI args.
set -euo pipefail
if [[ "$(id -u)" != "0" ]]; then echo "ERROR: root required"; exit 1; fi
for cmd in curl systemctl; do command -v "$cmd" >/dev/null 2>&1 || { echo "ERROR: missing $cmd"; exit 1; }; done
if command -v python2 >/dev/null 2>&1; then PYTHON_BIN="$(command -v python2)";
elif command -v python >/dev/null 2>&1; then PYTHON_BIN="$(command -v python)";
elif command -v python3 >/dev/null 2>&1; then PYTHON_BIN="$(command -v python3)";
else echo 'ERROR: Python not found'; exit 1; fi

"$PYTHON_BIN" - <<'PY'
import sys
if sys.version_info < (2,7): raise SystemExit('Python 2.7+ required')
PY

if ! id -u worklinks >/dev/null 2>&1; then
  useradd --system --no-create-home --shell /sbin/nologin worklinks
fi
install -d -o root -g root -m 0755 /home/worklinks/g2b
install -d -o worklinks -g worklinks -m 0700 /home/worklinks/g2b/secrets

src='https://raw.githubusercontent.com/programmer119/worklinks/main/server/g2b-proxy.py'
curl -fsSL --max-time 30 "$src" -o /home/worklinks/g2b/g2b-proxy.py.tmp
"$PYTHON_BIN" -m py_compile /home/worklinks/g2b/g2b-proxy.py.tmp
install -o root -g root -m 0644 /home/worklinks/g2b/g2b-proxy.py.tmp /home/worklinks/g2b/g2b-proxy.py
rm -f /home/worklinks/g2b/g2b-proxy.py.tmp

secret_path='/home/worklinks/g2b/secrets/g2b.env'
if [[ ! -s "$secret_path" ]]; then
  if [[ ! -t 0 ]]; then echo 'ERROR: interactive terminal required for key'; exit 1; fi
  read -r -s -p '나라장터 일반 인증키 입력 (표시되지 않음): ' key
  echo
  if [[ -z "$key" || "$key" =~ [[:space:]] ]]; then echo 'ERROR: invalid key'; unset key; exit 1; fi
  (umask 077; printf 'G2B_SERVICE_KEY=%s\n' "$key" > "$secret_path")
  unset key
fi
chown worklinks:worklinks "$secret_path"
chmod 0600 "$secret_path"

cat >/etc/systemd/system/worklinks-g2b.service <<EOF
[Unit]
Description=WorkLinks G2B Procurement Proxy (Python)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=worklinks
Group=worklinks
WorkingDirectory=/home/worklinks/g2b
ExecStart=$PYTHON_BIN /home/worklinks/g2b/g2b-proxy.py
Environment=PORT=18191
Environment=G2B_SECRET_PATH=/home/worklinks/g2b/secrets/g2b.env
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable worklinks-g2b.service >/dev/null
systemctl restart worklinks-g2b.service
sleep 2
echo 'STATUS (key hidden):'
curl -fsS --max-time 8 http://127.0.0.1:18191/api/g2b/status
echo
echo 'LIVE G2B API SMOKE TEST (only counts):'
today="$(TZ=Asia/Seoul date +%Y%m%d)"
curl -fsS --max-time 19 "http://127.0.0.1:18191/api/g2b/bids?kind=servc&from=$today&to=$today&page=1&rows=5" \
  | "$PYTHON_BIN" -c 'import sys,json; j=json.load(sys.stdin); print("ok=%s total=%s returned=%s error=%s" % (j.get("ok"),j.get("totalCount"),len(j.get("items",[])),j.get("error")));sys.exit(0 if j.get("ok") else 1)'
echo 'LOCAL: http://127.0.0.1:18191'
echo 'HTTPS: Cloudflare Tunnel api-worklinks.suaveforge.com -> http://localhost:18191'
echo 'Keep port 18191 closed externally.'
