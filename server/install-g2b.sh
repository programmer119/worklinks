#!/usr/bin/env bash
# WorkLinks G2B API proxy installer (server123/CentOS 7, Node 18+).
# Run from a trusted interactive root shell. Secret is never on the CLI or GitHub.
set -euo pipefail
if [[ "$(id -u)" != "0" ]]; then echo "ERROR: run as root"; exit 1; fi
for c in node curl systemctl; do command -v "$c" >/dev/null 2>&1 || { echo "Missing: $c"; exit 1; }; done
node_major="$(node -p 'parseInt(process.versions.node.split(".")[0],10)')"
if (( node_major < 18 )); then echo "ERROR: Node 18+ required"; exit 1; fi
if ! id -u worklinks >/dev/null 2>&1; then
  useradd --system --no-create-home --shell /sbin/nologin worklinks
fi
install -d -o root -g root -m 0755 /home/worklinks
install -d -o root -g root -m 0755 /home/worklinks/g2b
install -d -o worklinks -g worklinks -m 0700 /home/worklinks/secrets
curl -fsSL --max-time 30 "https://raw.githubusercontent.com/programmer119/worklinks/main/server/g2b-proxy.mjs" -o /home/worklinks/g2b/g2b-proxy.mjs.tmp
node --check /home/worklinks/g2b/g2b-proxy.mjs.tmp
install -o root -g root -m 0644 /home/worklinks/g2b/g2b-proxy.mjs.tmp /home/worklinks/g2b/g2b-proxy.mjs
rm -f /home/worklinks/g2b/g2b-proxy.mjs.tmp
secret_path="/home/worklinks/secrets/g2b.env"
if [[ ! -s "$secret_path" ]]; then
  if [[ ! -t 0 ]]; then echo "ERROR: interactive terminal required for first key setup"; exit 1; fi
  read -r -s -p "Enter G2B service key (hidden): " g2bkey
  echo
  if [[ -z "$g2bkey" || "$g2bkey" =~ [[:space:]] ]]; then
    echo "ERROR: invalid key"; unset g2bkey; exit 1
  fi
  (umask 077; printf 'G2B_SERVICE_KEY=%s\n' "$g2bkey" > "$secret_path")
  unset g2bkey
fi
chown worklinks:worklinks "$secret_path"
chmod 0600 "$secret_path"
node_bin="$(command -v node)"
cat >/etc/systemd/system/worklinks-g2b.service <<EOF
[Unit]
Description=WorkLinks G2B Procurement API Proxy
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=worklinks
Group=worklinks
WorkingDirectory=/home/worklinks/g2b
ExecStart=$node_bin /home/worklinks/g2b/g2b-proxy.mjs
Environment=PORT=18191
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
echo "LOCAL STATUS (no secret printed)"
curl -fsS --max-time 8 http://127.0.0.1:18191/api/g2b/status
echo
echo "LIVE PROCUREMENT API TEST (returns count only)"
today="$(TZ=Asia/Seoul date +%Y%m%d)"
curl -fsS --max-time 18 "http://127.0.0.1:18191/api/g2b/bids?kind=servc&from=$today&to=$today&page=1&rows=5" \
 | node -e 'let s="";process.stdin.on("data",x=>s+=x);process.stdin.on("end",()=>{let j=JSON.parse(s);console.log(JSON.stringify({ok:j.ok,totalCount:j.totalCount,returned:j.items?.length,error:j.error||null}));if(!j.ok)process.exitCode=1})'
echo
echo "DONE: http://127.0.0.1:18191 (local only)"
echo "Next: Cloudflare Tunnel hostname api-worklinks.suaveforge.com => http://localhost:18191"
echo "Keep TCP/18191 closed externally."
