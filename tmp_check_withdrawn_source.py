import requests
from app.core.config import settings

url = settings.teamrightworks_sync_trigger_url
key = settings.teamrightworks_sync_trigger_key
params = {'key': key, 'mode': 'bulk', 'status': 'withdrawn', 'limit': 5, 'offset': 0}
print('url', url)
resp = requests.get(url, params=params, timeout=60)
print('status', resp.status_code)
print('text_head', resp.text[:500])
try:
    data = resp.json()
    print('json_keys', list(data.keys())[:20])
    print('total_selected', data.get('total_selected'), 'success', data.get('success'), 'failed', data.get('failed'))
except Exception as e:
    print('json_error', e)
