import json
import ssl
import urllib.parse
import urllib.request

base_url = 'https://teamrightworks.in/QC/sync_to_verifai.php'
key = 'sync_dL1EuYoMu1wbtoZP7WisGdC3eKqbLHT5'
limit = 200
offset = 0
batch = 0
summary = {
    'batches': 0,
    'selected': 0,
    'success': 0,
    'failed': 0,
}

ctx = ssl.create_default_context()

while True:
    batch += 1
    params = {
        'key': key,
        'mode': 'bulk',
        'status': 'all',
        'limit': str(limit),
        'offset': str(offset),
    }
    url = base_url + '?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={'User-Agent': 'verifai-sync-runner/1.0'})
    with urllib.request.urlopen(req, context=ctx, timeout=180) as resp:
        body = resp.read().decode('utf-8', errors='replace')
    data = json.loads(body)

    selected = int(data.get('total_selected') or 0)
    success = int(data.get('success') or 0)
    failed = int(data.get('failed') or 0)

    summary['batches'] += 1
    summary['selected'] += selected
    summary['success'] += success
    summary['failed'] += failed

    print(f"batch={batch} offset={offset} selected={selected} success={success} failed={failed}")

    if selected == 0:
        break

    offset += limit
    if selected < limit:
        break

print('FINAL_SUMMARY=' + json.dumps(summary, ensure_ascii=False))
