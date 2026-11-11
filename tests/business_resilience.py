"""Controlled outages of this project's local Redis/RabbitMQ; always restart dependencies."""
import json
from pathlib import Path
import subprocess
import time
from business_integration import BASE, account, call, expect

if not BASE.startswith(("http://127.0.0.1:","http://localhost:")):
    raise SystemExit("This outage test is restricted to the local Compose environment")
compose=["docker","compose","-f","compose.yaml","-f","compose.business.yaml"]

def command(*args):subprocess.run(compose+list(args),check=True)

def main():
    _,token=account()
    product=expect(201,call("POST","/products",{"name":"Resilience fixture","price":2.50,"unit":"item"},token),"create resilience product")
    path="/products/"+product["id"]
    hit=call("GET",path,token=token)
    assert hit[2].get("X-Cache")=="HIT",hit
    # Expire only our fixture's real Redis key; service default TTL stays unchanged.
    command("exec","-T","redis","sh","-c",'export REDISCLI_AUTH="$REDIS_PASSWORD"; redis-cli EXPIRE "$1" 1',"sh","products:id:"+product["id"])
    time.sleep(1.3)
    expired=call("GET",path,token=token)
    assert expired[0]==200 and expired[2].get("X-Cache")=="MISS",expired
    command("stop","redis")
    try:
        fallback=call("GET",path,token=token)
        assert fallback[0]==200 and fallback[1]["id"]==product["id"],fallback
    finally:command("start","redis")
    command("stop","rabbitmq")
    try:
        order=expect(201,call("POST","/orders",{"items":[{"idProduct":product["id"],"quantity":2}]},token),"order persists while broker unavailable")
        summary=expect(200,call("GET","/orders/events/summary",token=token),"outbox during real broker outage")
        assert summary["broker_connected"] is False and summary["user_outbox_pending"]>=1,summary
    finally:command("start","rabbitmq")
    for _ in range(90):
        notification=call("GET","/orders/"+order["id"]+"/notifications",token=token)
        if notification[0]==200 and notification[1]["status"]=="PROCESSED":break
        time.sleep(.5)
    assert notification[0]==200 and notification[1]["status"]=="PROCESSED",notification
    summary_after=expect(200,call("GET","/orders/events/summary",token=token),"outbox recovered")
    assert summary_after["broker_connected"] and summary_after["user_outbox_pending"]==0,summary_after
    expect(204,call("DELETE",path,token=token),"delete resilience fixture")
    report={"redis_expiration":"real fixture key expired with EXPIRE 1; default service TTL unchanged",
       "redis_down":"Product returned 200 from database","rabbitmq_down":"Order returned 201 and outbox remained pending",
       "rabbitmq_restarted":"Pending event processed and outbox cleared",
       "limits":"Controlled dependency outages do not prove crash safety between ACK and database commit."}
    Path("artifacts/business-resilience.json").write_text(json.dumps(report,indent=2))
    print("PASS: real Redis expiry/outage fallback and RabbitMQ outage/outbox recovery")

if __name__=="__main__":main()
