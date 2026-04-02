import json
import urllib.request
import urllib.parse
import urllib.error

BASE = 'http://127.0.0.1:8000'
USER = 'sudhir'
PASS = 'Dhoom*2690'


def post_json(path, payload, token=None):
    data = json.dumps(payload).encode('utf-8')
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method='POST')
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.status, json.loads(resp.read().decode('utf-8', errors='ignore') or '{}')


def post_no_body(path, token=None):
    headers = {}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(BASE + path, data=b'', headers=headers, method='POST')
    with urllib.request.urlopen(req, timeout=600) as resp:
        return resp.status, json.loads(resp.read().decode('utf-8', errors='ignore') or '{}')

try:
    s, login = post_json('/api/v1/auth/login', {'username': USER, 'password': PASS})
    token = str(login.get('access_token') or '')
    print('login_status', s)
    print('login_role', ((login.get('user') or {}).get('role') if isinstance(login.get('user'), dict) else ''))

    s1, lbl = post_no_body('/api/v1/checklist/ml/labels-from-alignment?overwrite=true', token=token)
    print('labels_status', s1)
    print('labels_response', json.dumps(lbl, ensure_ascii=False))

    s2, tr = post_no_body('/api/v1/checklist/ml/train', token=token)
    print('train_status', s2)
    print('train_response', json.dumps(tr, ensure_ascii=False))
except urllib.error.HTTPError as e:
    body = e.read().decode('utf-8', errors='ignore')
    print('http_error', e.code)
    print(body)
    raise
except Exception as e:
    print('error', str(e))
    raise
