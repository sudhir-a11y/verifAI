import json
import urllib.request
import urllib.error

BASE = 'http://127.0.0.1:8000'

def post_json(url, payload):
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.status, resp.read().decode('utf-8', errors='ignore')

def get_json(url, token):
    req = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + token}, method='GET')
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.status, resp.read().decode('utf-8', errors='ignore')

try:
    status, body = post_json(BASE + '/api/v1/auth/login', {'username': 'sudhir', 'password': 'Dhoom*2690'})
    print('login_status', status)
    data = json.loads(body)
    token = str(data.get('access_token') or '')
    status2, body2 = get_json(BASE + '/api/v1/user-tools/dashboard-overview', token)
    print('dashboard_status', status2)
    payload = json.loads(body2)
    day = payload.get('day_wise_completed') or []
    assignee = payload.get('assignee_wise') or []
    print('day_count', len(day))
    print('assignee_count', len(assignee))
    print('day_head', json.dumps(day[:5]))
except urllib.error.HTTPError as e:
    print('http_error', e.code)
    print(e.read().decode('utf-8', errors='ignore'))
    raise
except Exception as e:
    print('error', str(e))
    raise
