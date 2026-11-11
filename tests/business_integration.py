"""Real six-service acceptance through Gateway, including external FX, Redis and RabbitMQ."""
from decimal import Decimal, ROUND_HALF_UP
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request
import uuid

BASE=os.environ.get("BASE_URL","http://127.0.0.1:8080")
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
checks=[]

def call(method,path,body=None,token=None,headers=None):
    hdr={"Content-Type":"application/json",**(headers or {})}
    if token:hdr["Authorization"]="Bearer "+token
    req=urllib.request.Request(BASE+path,data=json.dumps(body).encode() if body is not None else None,headers=hdr,method=method)
    try:response=opener.open(req,timeout=25)
    except urllib.error.HTTPError as err:response=err
    with response:
        raw=response.read()
        try:data=json.loads(raw)
        except ValueError:data=raw.decode()
        return response.status,data,dict(response.headers)

def expect(status,result,label):
    assert result[0]==status,(label,"expected",status,"got",result[0],result[1])
    checks.append(label)
    return result[1]

def money(value):return Decimal(str(value)).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP)

def account():
    credentials={"email":f"integration-{uuid.uuid4().hex}@example.com","password":"integration-Password123!"}
    obj=expect(201,call("POST","/accounts",{"name":"Integration",**credentials}),"account registration")
    for _ in range(90):
        result=call("POST","/auth/login",credentials)
        if result[0]==200:break
        time.sleep(.5)
    session=expect(200,result,"Java login")
    return obj,session["access_token"]

def main():
    first,a=account();second,b=account()
    for route in ("/products","/orders","/exchanges/USD/BRL"):
        expect(401,call("GET",route),"missing token rejected "+route)
        expect(401,call("GET",route,token="invalid.jwt.token"),"invalid token rejected "+route)
    p1=expect(201,call("POST","/products",{"name":"Integration Tomato","price":10.12,"unit":"kg"},a),"create product 1")
    p2=expect(201,call("POST","/products",{"name":"Integration Cheese","price":.62,"unit":"slice"},a),"create product 2")
    product_path="/products/"+p1["id"]
    found=expect(200,call("GET",product_path,token=a),"read product")
    assert found==p1
    cached=call("GET",product_path,token=a)
    expect(200,cached,"cached product")
    assert cached[2].get("X-Cache")=="HIT",cached[2]
    bypass=call("GET",product_path,token=a,headers={"X-Cache-Control":"no-cache"})
    expect(200,bypass,"cache bypass through Go gateway")
    assert bypass[2].get("X-Cache")=="BYPASS",bypass[2]
    stats=expect(200,call("GET","/products/cache/stats",token=a),"real Redis connection")
    assert stats["redis_connected"] is True and stats["hits"]>=1 and stats["bypasses"]>=1,stats
    collection=expect(200,call("GET","/products",token=a),"list products")
    assert {p1["id"],p2["id"]}.issubset({p["id"] for p in collection})
    bad={"items":[{"idProduct":str(uuid.uuid4()),"quantity":1}]}
    expect(400,call("POST","/orders",bad,a),"nonexistent product rejected by Order")
    created=expect(201,call("POST","/orders",{"items":[{"idProduct":p1["id"],"quantity":2},{"idProduct":p2["id"],"quantity":10}]},a),"create order using real Product")
    assert money(created["total"])==Decimal("26.44"),created
    order_path="/orders/"+created["id"]
    listed=expect(200,call("GET","/orders",token=a),"list own orders")
    assert created["id"] in {o["id"] for o in listed}
    assert expect(200,call("GET","/orders",token=b),"other account list isolation")==[]
    expect(404,call("GET",order_path,token=b),"other account detail isolation")
    expect(404,call("GET",order_path,token=b,headers={"X-Account-ID":first["id"]}),"forged identity rejected across business services")
    usd=expect(200,call("GET",order_path,token=a),"USD detail")
    assert usd["currency"]=="USD" and money(usd["total"])==Decimal("26.44")
    quote_result=call("GET","/exchanges/USD/BRL",token=a)
    quote=expect(200,quote_result,"external exchange provider")
    assert quote["id-account"]==first["id"] and quote["sell"]>0 and quote["buy"]>0 and quote["date"],quote
    source=quote_result[2].get("X-Exchange-Source","")
    assert source.startswith(("awesomeapi","open-er-api")),source
    converted=expect(200,call("GET",order_path+"?currency=BRL",token=a),"Order calls real Exchange")
    expected=sum((money(Decimal(str(item["total"]))*Decimal(str(quote["sell"]))) for item in usd["items"]),Decimal("0.00"))
    assert converted["currency"]=="BRL" and money(converted["total"])==expected,(converted,quote,expected)
    assert expect(200,call("GET",order_path,token=a),"USD unchanged after conversion")==usd
    expect(422,call("GET",order_path+"?currency=XYZ",token=a),"unsupported currency in Order")
    expect(422,call("GET","/exchanges/USD/XYZ",token=a),"unsupported currency in Exchange")
    for _ in range(60):
        notification=expect(200,call("GET",order_path+"/notifications",token=a),"notification poll")
        if notification["status"]=="PROCESSED":break
        time.sleep(.25)
    assert notification["status"]=="PROCESSED",notification
    replay=expect(200,call("POST",order_path+"/events/replay",token=a),"real RabbitMQ duplicate replay")
    for _ in range(30):
        notification=expect(200,call("GET",order_path+"/notifications",token=a),"idempotency poll")
        if notification.get("notification",{}).get("duplicate_deliveries",0)>=1:break
        time.sleep(.25)
    assert notification["notification"]["duplicate_deliveries"]>=1,notification
    summary=expect(200,call("GET","/orders/events/summary",token=a),"real broker connection")
    assert summary["broker_connected"] and summary["user_notifications_processed"]==1,summary
    expect(404,call("POST","/orders/events/consumer",{"enabled":False},a),"global demo control disabled")
    expect(404,call("GET",order_path+"/notifications",token=b),"notification ownership")
    expect(204,call("DELETE",product_path,token=a),"delete product")
    expect(404,call("GET",product_path,token=a),"cache invalidation after deletion")
    remaining=expect(200,call("GET","/products",token=a),"collection invalidation")
    assert p1["id"] not in {p["id"] for p in remaining}
    assert expect(200,call("GET",order_path,token=a),"historical order survives product deletion")==usd
    expect(204,call("DELETE","/products/"+p2["id"],token=a),"fixture cleanup")
    report={"utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"base_url":BASE,"passed":checks,
      "usd_total":26.44,"brl_total":float(expected),"exchange_source":source,"quote":{k:quote[k] for k in ("sell","buy","date")},
      "redis_real":True,"rabbitmq_real":True,"mocks":False,
      "limits":"This run does not prove crash-safe broker acknowledgement or concurrent cache invalidation."}
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/business-integration.json").write_text(json.dumps(report,indent=2))
    print(f"PASS: {len(checks)} checks across all six real services; external FX={source}; USD=26.44 BRL={expected}")

if __name__=="__main__":main()
