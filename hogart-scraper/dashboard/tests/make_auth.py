"""Create short-lived signed test data locally without printing credentials."""
import hashlib,hmac,json,sys,time,urllib.parse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
token,allowed=server.credentials()
def signed(uid):
    fields={'auth_date':str(int(time.time())),'user':json.dumps({'id':uid}),'query_id':'dashboard-e2e'}
    secret=hmac.new(b'WebAppData',token.encode(),hashlib.sha256).digest()
    fields['hash']=hmac.new(secret,'\n'.join(f'{k}={v}' for k,v in sorted(fields.items())).encode(),hashlib.sha256).hexdigest()
    return urllib.parse.urlencode(fields)
p=Path('/tmp/deal-dashboard-test-auth.json')
p.write_text(json.dumps({'valid':signed(next(iter(allowed))),'other':signed(1)}));p.chmod(0o600)
