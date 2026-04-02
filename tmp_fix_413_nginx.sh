#!/bin/bash
set -euo pipefail
CONF="/etc/nginx/conf.d/verifai.in.conf"
python3 - <<'PY'
from pathlib import Path
p = Path('/etc/nginx/conf.d/verifai.in.conf')
t = p.read_text()
if 'client_max_body_size' not in t:
    t = t.replace('server_name verifai.in;', 'server_name verifai.in;\n    client_max_body_size 200M;', 1)
    p.write_text(t)
print('client_max_body_size present:', 'client_max_body_size' in p.read_text())
PY
nginx -t
systemctl reload nginx
grep -n 'client_max_body_size\|server_name verifai.in' "$CONF"
