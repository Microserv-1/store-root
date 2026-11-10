"""Functional & resilience proof of Gargalo B2: RabbitMQ Asynchronous Messaging in Order Service."""
import argparse
import json
import os
from pathlib import Path
import statistics
import time
import urllib.error
import urllib.request
import uuid

parser = argparse.ArgumentParser()
parser.add_argument("--base-url", default=os.environ.get("BASE_URL", "http://127.0.0.1:8080"))
parser.add_argument("--batch-size", type=int, default=12)
parser.add_argument("--output", default="artifacts/messaging-bottleneck.json")
args = parser.parse_args()

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def request(method, path, payload=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        args.base_url + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers=headers,
        method=method,
    )
    try:
        resp = opener.open(req, timeout=15)
    except urllib.error.HTTPError as err:
        resp = err
    with resp:
        raw = resp.read()
        return resp.status, json.loads(raw) if raw else None


def main():
    email = f"mq-bench-{uuid.uuid4().hex[:8]}@example.com"
    password = "mq-Password123!"
    status, _ = request("POST", "/accounts", {"name": "MQ Bench", "email": email, "password": password})
    assert status == 201
    status, session = request("POST", "/auth/login", {"email": email, "password": password})
    assert status == 200
    token = session["access_token"]

    status, product = request(
        "POST",
        "/products",
        {"name": f"Async Item {uuid.uuid4().hex[:6]}", "price": 45.0, "unit": "unit"},
        token=token,
    )
    assert status == 201

    # 1. Pause consumer to simulate downstream notification worker outage
    status, paused_state = request("POST", "/orders/events/consumer", {"enabled": False}, token=token)
    assert status == 200 and paused_state["consumer_active"] is False

    created_order_ids = []
    post_latencies_ms = []
    try:
        for _ in range(args.batch_size):
            t0 = time.monotonic()
            status, order = request(
                "POST",
                "/orders",
                {"items": [{"idProduct": product["id"], "quantity": 1}]},
                token=token,
            )
            dt = (time.monotonic() - t0) * 1000.0
            assert status == 201, (status, order)
            created_order_ids.append(order["id"])
            post_latencies_ms.append(dt)

        _, summary_while_paused = request("GET", "/orders/events/summary", token=token)
        # While consumer is paused, HTTP POST /orders succeeded immediately and messages are queued in RabbitMQ
        _, notif_while_paused = request("GET", f"/orders/{created_order_ids[0]}/notifications", token=token)
        assert notif_while_paused["status"] == "PENDING"
    finally:
        # 2. Resume consumer and measure catch-up processing
        resume_t0 = time.monotonic()
        status, resumed_state = request("POST", "/orders/events/consumer", {"enabled": True}, token=token)
        assert status == 200 and resumed_state["consumer_active"] is True

    # Wait until all batch orders have their notification processed
    deadline = time.monotonic() + 20.0
    processed_orders = 0
    while time.monotonic() < deadline:
        processed_orders = 0
        for oid in created_order_ids:
            st, body = request("GET", f"/orders/{oid}/notifications", token=token)
            if st == 200 and body and body.get("status") == "PROCESSED":
                processed_orders += 1
        if processed_orders == len(created_order_ids):
            break
        time.sleep(0.2)
    catchup_duration_ms = (time.monotonic() - resume_t0) * 1000.0
    assert processed_orders == len(created_order_ids), (processed_orders, len(created_order_ids))

    # 3. Replay first order's event twice to prove idempotency (no duplicate notification rows)
    target_order_id = created_order_ids[0]
    for _ in range(2):
        st, rep = request("POST", f"/orders/{target_order_id}/events/replay", token=token)
        assert st == 200 and rep["status"] == "PROCESSED"

    st, target_notif = request("GET", f"/orders/{target_order_id}/notifications", token=token)
    assert st == 200 and target_notif["status"] == "PROCESSED"
    assert target_notif["notification"]["duplicate_deliveries"] >= 2

    _, summary_after = request("GET", "/orders/events/summary", token=token)
    assert summary_after["user_orders_total"] == len(created_order_ids)
    assert summary_after["user_notifications_processed"] == len(created_order_ids)

    report = {
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "bottleneck": "B2 - RabbitMQ Asynchronous Order Event Processing & Idempotent Consumer",
        "base_url": args.base_url,
        "resilience_and_decoupling": {
            "orders_created_while_consumer_paused": len(created_order_ids),
            "post_order_latency_while_paused_ms": {
                "avg": round(statistics.mean(post_latencies_ms), 3),
                "max": round(max(post_latencies_ms), 3),
            },
            "first_order_status_while_paused": notif_while_paused["status"],
            "queue_depth_while_paused": summary_while_paused["queue_depth"],
            "orders_caught_up_after_resume": processed_orders,
            "catchup_duration_ms": round(catchup_duration_ms, 2),
        },
        "idempotency_verification": {
            "order_id": target_order_id,
            "unique_notifications_for_user": summary_after["user_notifications_processed"],
            "duplicate_deliveries_skipped": target_notif["notification"]["duplicate_deliveries"],
        },
        "summary_after_catchup_and_replay": summary_after,
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
