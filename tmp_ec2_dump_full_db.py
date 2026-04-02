from __future__ import annotations

import os
import subprocess
from datetime import datetime
from pathlib import Path


def read_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in path.read_text(encoding='utf-8', errors='ignore').splitlines():
        line = raw.strip().replace('\r', '')
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        out[k.strip()] = v.strip()
    return out


def main() -> int:
    root = Path('/home/ec2-user/qc-python')
    env_map = read_env(root / '.env')
    host = env_map.get('PG_HOST', '127.0.0.1')
    port = env_map.get('PG_PORT', '5432')
    user = env_map.get('PG_USER', 'postgres')
    password = env_map.get('PG_PASSWORD', '')
    database = env_map.get('PG_DATABASE', 'postgres')

    ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    out_path = root / 'artifacts' / f'ec2_full_{ts}.dump'
    out_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        'pg_dump',
        '-h', host,
        '-p', str(port),
        '-U', user,
        '-d', database,
        '-Fc',
        '--no-owner',
        '--no-privileges',
        '-f', str(out_path),
    ]
    env = os.environ.copy()
    env['PGPASSWORD'] = password

    proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if proc.returncode != 0:
        print('ERROR=pg_dump_failed')
        print(proc.stdout.strip())
        print(proc.stderr.strip())
        return proc.returncode

    print(f'DUMP_PATH={out_path}')
    print(f'DUMP_SIZE={out_path.stat().st_size}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
