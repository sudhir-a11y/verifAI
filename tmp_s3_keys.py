from app.services.storage_service import _s3_client
from app.core.config import settings

client = _s3_client()
bucket = settings.s3_bucket
resp = client.list_objects_v2(Bucket=bucket, MaxKeys=50)
print('bucket', bucket, 'key_count_returned', resp.get('KeyCount'))
for obj in resp.get('Contents', []):
    print(obj.get('Key'))
