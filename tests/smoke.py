"""Black-box acceptance of all 6 microservices (Account, Auth, Gateway, Product, Order, Exchange)."""
from decimal import Decimal, ROUND_HALF_UP
import json
import os
import time
import urllib.error
import urllib.request
import uuid

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:8080")
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def call_with_headers(method, path, payload=None, token=None, headers=None):
    hdrs = {"Content-Type": "application/json", **(headers or {})}
    if token:
        hdrs["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers=hdrs,
        method=method,
    )
    try:
        result = opener.open(req, timeout=15)
    except urllib.error.HTTPError as err:
        result = err
    raw = result.read()
    try:
        data = json.loads(raw) if raw else None
    except ValueError:
        data = raw.decode()
    resp_headers = {k.lower(): v for k, v in result.headers.items()}
    return result.status, data, resp_headers


def call(method, path, payload=None, token=None, headers=None):
    status, data, _ = call_with_headers(method, path, payload=payload, token=token, headers=headers)
    return status, data


def wait_for_notification(order_id, token, timeout_s=15):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        status, body = call("GET", f"/orders/{order_id}/notifications", token=token)
        if status == 200 and isinstance(body, dict) and body.get("status") == "PROCESSED" and body.get("notification"):
            return body
        time.sleep(0.25)
    raise AssertionError(f"Notification for order {order_id} not processed within {timeout_s}s")


def main():
    for _ in range(60):
        try:
            if call("GET", "/health-check")[0] == 200:
                break
        except OSError:
            pass
        time.sleep(1)

    # --- 1. Identity & Auth (Pessoa A) ---
    email = f"acceptance-{uuid.uuid4().hex}@example.com"
    password = "local-test-Password123!"
    status, account = call("POST", "/accounts", {"name": "Acceptance", "email": email, "password": password})
    assert status == 201, (status, account)
    assert "password" not in account
    assert call("POST", "/accounts", {"name": "Duplicate", "email": email.upper(), "password": password})[0] == 409

    for _ in range(60):
        status, session = call("POST", "/auth/login", {"email": email, "password": password})
        if status == 200:
            break
        time.sleep(1)
    assert status == 200, (status, session)
    token = session["access_token"]
    assert call("GET", "/accounts/me", token=token) == (200, account)
    assert call("GET", "/auth/me", token=token) == (200, {"id-account": account["id"]})
    assert call("GET", "/accounts/me")[0] == 401
    assert call("GET", "/accounts/me", headers={"X-Account-ID": account["id"]})[0] == 401
    assert call("GET", "/accounts/me", token=token[:-5] + "xxxxx")[0] == 401
    assert call("POST", "/auth/login", {"email": email, "password": "wrong-password"})[0] == 401
    assert call("POST", "/auth/login", {})[0] == 400
    assert call("POST", "/internal/credentials/verify", {"email": email, "password": password})[0] == 404

    second = {"name": "Second", "email": f"second-{uuid.uuid4().hex}@example.com", "password": password}
    status, account2 = call("POST", "/accounts", second)
    assert status == 201
    status, session2 = call("POST", "/auth/login", {"email": second["email"], "password": password})
    assert status == 200
    token2 = session2["access_token"]
    status, me = call("GET", "/accounts/me", token=token2, headers={"X-Account-ID": account["id"]})
    assert status == 200 and me["id"] == account2["id"] != account["id"]

    # --- 2. Product Service + Redis Cache (Pessoa B) ---
    assert call("GET", "/products")[0] == 401
    unique_tag = uuid.uuid4().hex[:8]
    status, prod1 = call(
        "POST",
        "/products",
        {"name": f"Cloud Server {unique_tag}", "price": 120.50, "unit": "month"},
        token=token,
    )
    assert status == 201, (status, prod1)
    status, prod2 = call(
        "POST",
        "/products",
        {"name": f"Managed Redis {unique_tag}", "price": 39.25, "unit": "month"},
        token=token,
    )
    assert status == 201, (status, prod2)

    status, fetched2, hdrs2 = call_with_headers("GET", f"/products/{prod1['id']}", token=token)
    assert status == 200 and fetched2["id"] == prod1["id"]
    assert hdrs2.get("x-cache") == "HIT", hdrs2

    # Search filter (?name=): first call MISS, second call HIT
    status, filtered, fhdr1 = call_with_headers("GET", f"/products?name={unique_tag}", token=token)
    assert status == 200 and len(filtered) == 2 and fhdr1.get("x-cache") == "MISS", (status, fhdr1)
    status, filtered2, fhdr2 = call_with_headers("GET", f"/products?name={unique_tag}", token=token)
    assert status == 200 and len(filtered2) == 2 and fhdr2.get("x-cache") == "HIT", (status, fhdr2)

    # Delete a temporary product and confirm 204 -> 404 and cache invalidation
    status, temp_prod = call(
        "POST",
        "/products",
        {"name": f"Temp Product {unique_tag}", "price": 10.0, "unit": "unit"},
        token=token,
    )
    assert status == 201
    assert call("GET", f"/products/{temp_prod['id']}", token=token)[0] == 200
    assert call("DELETE", f"/products/{temp_prod['id']}", token=token)[0] == 204
    assert call("GET", f"/products/{temp_prod['id']}", token=token)[0] == 404

    # --- 3. Exchange Service (Pessoa B - Mandatory Python) ---
    assert call("GET", "/exchanges/USD/BRL")[0] == 401
    status, rate_brl = call("GET", "/exchanges/USD/BRL", token=token)
    assert status == 200, (status, rate_brl)
    assert rate_brl["sell"] > 0 and rate_brl["buy"] > 0
    assert rate_brl["id-account"] == account["id"]
    assert "date" in rate_brl

    status, rate_same = call("GET", "/exchanges/USD/USD", token=token)
    assert status == 200 and rate_same["sell"] == 1.0 and rate_same["buy"] == 1.0
    assert call("GET", "/exchanges/USD/INVALID", token=token)[0] == 422

    # --- 4. Order Service + Exchange Integration + RabbitMQ Messaging (Pessoa B) ---
    assert call("GET", "/orders")[0] == 401
    # Nonexistent product must return 400
    assert (
        call(
            "POST",
            "/orders",
            {"items": [{"idProduct": str(uuid.uuid4()), "quantity": 1}]},
            token=token,
        )[0]
        == 400
    )

    status, created_order = call(
        "POST",
        "/orders",
        {
            "items": [
                {"idProduct": prod1["id"], "quantity": 2},
                {"idProduct": prod2["id"], "quantity": 1},
            ]
        },
        token=token,
    )
    assert status == 201, (status, created_order)
    expected_usd = float(
        (Decimal(str(prod1["price"])) * 2 + Decimal(str(prod2["price"])) * 1).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    )
    assert created_order["total"] == expected_usd, (created_order["total"], expected_usd)

    # Account 1 lists its orders; Account 2 sees none of Account 1's orders and gets 404 on detail
    status, orders_acc1 = call("GET", "/orders", token=token)
    assert status == 200 and any(o["id"] == created_order["id"] for o in orders_acc1)
    status, orders_acc2 = call("GET", "/orders", token=token2)
    assert status == 200 and all(o["id"] != created_order["id"] for o in orders_acc2)
    assert call("GET", f"/orders/{created_order['id']}", token=token2)[0] == 404

    # On-the-fly conversion to BRL via Exchange without mutating stored USD total
    status, order_brl = call("GET", f"/orders/{created_order['id']}?currency=BRL", token=token)
    assert status == 200, (status, order_brl)
    assert order_brl["currency"] == "BRL"
    assert order_brl["total"] > expected_usd

    status, order_usd_again = call("GET", f"/orders/{created_order['id']}", token=token)
    assert status == 200 and order_usd_again["currency"] == "USD" and order_usd_again["total"] == expected_usd
    assert call("GET", f"/orders/{created_order['id']}?currency=INVALID", token=token)[0] == 422

    # RabbitMQ async event consumption & idempotency
    notif_res = wait_for_notification(created_order["id"], token)
    assert notif_res["status"] == "PROCESSED"
    assert notif_res["notification"]["duplicate_deliveries"] == 0

    status, replay = call("POST", f"/orders/{created_order['id']}/events/replay", token=token)
    assert status == 200 and replay["status"] == "PROCESSED"
    assert replay["notification"]["duplicate_deliveries"] >= 1

    print(
        "PASS: all 6 microservices verified (Account, Auth, Gateway, Product+Redis, Exchange, Order+RabbitMQ)"
    )


if __name__ == "__main__":
    main()
