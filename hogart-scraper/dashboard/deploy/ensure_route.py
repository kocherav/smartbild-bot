"""Reconcile only this dashboard route through Caddy's local admin API."""
import json
import urllib.request
import urllib.error

BASE='http://127.0.0.1:2019'
IDENT='smartbild-deal-dashboard'
ROUTE={'@id':IDENT,'match':[{'host':['claude.smartbild.su'],'path':['/deal-dashboard','/deal-dashboard/*']}],
    'handle':[{'handler':'reverse_proxy','upstreams':[{'dial':'127.0.0.1:8096'}],
        'headers':{'request':{'set':{'X-Dashboard-IP':['{http.request.remote.host}']}}}}],'terminal':True}

def request(path, method='GET', body=None, etag=None):
    headers={'Content-Type':'application/json'}
    if etag:headers['If-Match']=etag
    req=urllib.request.Request(BASE+path,method=method,headers=headers,
        data=json.dumps(body).encode() if body is not None else None)
    with urllib.request.urlopen(req,timeout=10) as res:
        raw=res.read()
        return (json.loads(raw) if raw else None), res.headers.get('Etag')

def main():
    try:
        existing,_=request('/id/'+IDENT)
        if existing!=ROUTE:raise RuntimeError('Existing dashboard route differs; review before changing')
        return
    except urllib.error.HTTPError as exc:
        if exc.code!=404:raise
    servers,_=request('/config/apps/http/servers')
    names=[name for name,server in servers.items() if ':443' in server.get('listen',[]) and
        any('claude.smartbild.su' in match.get('host',[]) for route in server.get('routes',[]) for match in route.get('match',[]))]
    if len(names)!=1:raise RuntimeError('HTTPS host is not unambiguous')
    path='/config/apps/http/servers/'+names[0]+'/routes'
    routes,etag=request(path)
    if any(route.get('@id')==IDENT for route in routes):return
    request(path+'/0','PUT',ROUTE,etag)
    actual,_=request('/id/'+IDENT)
    if actual!=ROUTE:raise RuntimeError('Route verification failed')
    print('Dashboard HTTPS route installed; existing routes preserved')

if __name__=='__main__':main()
