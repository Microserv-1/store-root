"""Bounded authenticated business load; validates responses and records per-route metrics."""
import argparse
import collections
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--base-url',default='http://127.0.0.1:8080')
    parser.add_argument('--scenario',choices=['products','orders','exchange','business'],default='business')
    parser.add_argument('--users',type=int,default=2)
    parser.add_argument('--duration',type=int,default=30)
    parser.add_argument('--pause-ms',type=int,default=100)
    parser.add_argument('--max-orders-per-user',type=int,default=20)
    parser.add_argument('--cache',choices=['enabled','bypass'],default='enabled')
    parser.add_argument('--output',default='artifacts/business-load.json')
    parser.add_argument('--context',help='Optional explicit cluster context to capture replica/HPA/CPU/memory snapshots')
    parser.add_argument('--allow-internal-http',action='store_true')
    args=parser.parse_args()
    if not 1<=args.users<=50 or not 1<=args.duration<=3600 or not 1<=args.max_orders_per_user<=500 or args.pause_ms<0:
        parser.error('Invalid bounds: users 1..50, seconds 1..3600, max orders per user 1..500, pause >=0')
    url=urllib.parse.urlsplit(args.base_url)
    if url.scheme not in ['http','https'] or url.username or url.password or url.query or url.fragment:
        parser.error('Use a plain HTTP(S) base URL without credentials, query or fragment')
    if url.scheme=='http' and url.hostname not in ['127.0.0.1','localhost'] and not args.allow_internal_http:
        parser.error('Use HTTPS externally or explicitly allow an internal cluster HTTP endpoint')
    base=args.base_url.rstrip('/')
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    rows=[];mutex=threading.Lock();run_id=uuid.uuid4().hex
    cache_headers={'X-Cache-Control':'no-cache'} if args.cache=='bypass' else {}

    def request(method,path,token=None,payload=None,label=None,expected=200,validate=None,headers=None):
        hdr={'Content-Type':'application/json',**(headers or {})}
        if token:hdr['Authorization']='Bearer '+token
        req=urllib.request.Request(base+path,data=json.dumps(payload).encode() if payload is not None else None,headers=hdr,method=method)
        begin=time.monotonic();status=0;success=False;problem=None;body=None;cache=None
        try:
            try:response=opener.open(req,timeout=15)
            except urllib.error.HTTPError as exc:response=exc
            with response:
                status=response.status;raw=response.read();cache=response.headers.get('X-Cache')
                body=json.loads(raw) if raw else None
                success=status==expected and (validate(body) if validate else True)
                if not success:problem='UnexpectedStatusOrPayload'
        except (OSError,ValueError,KeyError,TypeError) as exc:problem=type(exc).__name__
        duration=(time.monotonic()-begin)*1000
        if label:
            with mutex:rows.append((label,status,duration,success,problem,cache))
        elif not success:
            raise RuntimeError('Fixture/cleanup request failed: '+method+' '+path+' ('+str(status)+')')
        return body

    def snapshot():
        if not args.context:return None
        result={}
        for label,command in [('resources',['get','deployments,hpa,pods','-o','json']),('utilization',['top','pods'])]:
            process=subprocess.run(['kubectl','--context',args.context,'-n','store',*command],capture_output=True,text=True)
            result[label]={'exit_code':process.returncode,'output':process.stdout if process.returncode==0 else 'Unavailable'}
        return result

    credentials=[]
    for index in range(args.users):
        account={'email':f'load-{run_id}-{index}@example.com','password':'load-business-Password123!'}
        request('POST','/accounts',payload={'name':'Load fixture',**account},expected=201)
        session=request('POST','/auth/login',payload=account)
        credentials.append(session['access_token'])
    product=request('POST','/products',credentials[0],{'name':'Load '+run_id,'price':3.25,'unit':'item'},expected=201)
    product_id=product['id'];product_path='/products/'+product_id
    request('GET',product_path,credentials[0])
    before=snapshot();started=time.monotonic();deadline=started+args.duration

    def worker(token):
        orders=[];cursor=0
        while time.monotonic()<deadline:
            if args.scenario in ['products','business']:
                request('GET',product_path,token,label='GET product',headers=cache_headers,
                        validate=lambda data:data['id']==product_id and Decimal(str(data['price']))==Decimal('3.25'))
                request('GET','/products',token,label='GET products',headers=cache_headers,
                        validate=lambda data:any(p['id']==product_id for p in data))
            if args.scenario in ['orders','business']:
                if len(orders)<args.max_orders_per_user:
                    order=request('POST','/orders',token,{'items':[{'idProduct':product_id,'quantity':1}]},
                                  label='POST order',expected=201,validate=lambda data:Decimal(str(data['total']))==Decimal('3.25'))
                    if order and 'id' in order:orders.append(order['id'])
                if orders:
                    path='/orders/'+orders[cursor%len(orders)];cursor+=1
                    request('GET',path,token,label='GET order USD',
                            validate=lambda data:data['currency']=='USD' and Decimal(str(data['total']))==Decimal('3.25'))
                    request('GET',path+'?currency=BRL',token,label='GET order BRL',
                            validate=lambda data:data['currency']=='BRL' and Decimal(str(data['total']))>0)
            if args.scenario in ['exchange','business']:
                request('GET','/exchanges/USD/BRL',token,label='GET exchange',
                        validate=lambda data:data['sell']>0 and data['buy']>0 and bool(data['id-account']))
            if args.pause_ms:time.sleep(args.pause_ms/1000)

    try:
        with ThreadPoolExecutor(max_workers=args.users) as pool:list(pool.map(worker,credentials))
    finally:
        # This API has no order/account DELETE: use a dedicated test database for prolonged runs.
        request('DELETE',product_path,credentials[0],expected=204)
    elapsed=time.monotonic()-started

    def metrics(data):
        samples=sorted(r[2] for r in data)
        def percentile(p):return samples[int((len(samples)-1)*p)] if samples else None
        return {'requests':len(data),'requests_per_second':round(len(data)/elapsed,3),
                'latency_ms':{'p50':percentile(.5),'p95':percentile(.95),'p99':percentile(.99)},
                'error_ratio':sum(not r[3] for r in data)/max(1,len(data)),
                'status_counts':dict(collections.Counter(str(r[1]) for r in data)),
                'problems':dict(collections.Counter(r[4] for r in data if r[4])),
                'cache_headers':dict(collections.Counter(r[5] for r in data if r[5]))}
    commits={name:subprocess.check_output(['git','-C','api/'+name,'rev-parse','HEAD'],text=True).strip()
             for name in ['account','auth','gateway','product','order','exchange']}
    result={'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'base_url':base,'scenario':args.scenario,
            'users':args.users,'requested_duration_s':args.duration,'actual_duration_s':round(elapsed,3),
            'model':'closed-loop; pause after each business iteration','pause_ms':args.pause_ms,'cache':args.cache,
            'max_orders_created':args.users*args.max_orders_per_user,'commits':commits,
            'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'overall':metrics(rows),'operations':{op:metrics([r for r in rows if r[0]==op]) for op in sorted({r[0] for r in rows})},
            'cluster_before':before,'cluster_after':snapshot(),
            'limits':'Short local runs do not prove EKS performance or an SLA. Accounts/orders remain as test data; only the product fixture is removed.'}
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'scenario':args.scenario,'users':args.users,**result['overall']},indent=2))
    if not rows or result['overall']['error_ratio']>0:raise SystemExit(1)


if __name__=='__main__':main()
