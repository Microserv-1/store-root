"""Black-box acceptance of Python Account + Java Auth through the Go Gateway."""
import json
import os
import time
import uuid
import urllib.error
import urllib.request

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:8080")
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

def call(method, path, payload=None, token=None, headers=None):
    hdrs = {"Content-Type": "application/json", **(headers or {})}
    if token:
        hdrs["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode() if payload is not None else None,
                                 headers=hdrs, method=method)
    try:
        result = opener.open(req, timeout=15)
    except urllib.error.HTTPError as err:
        result = err
    data = result.read()
    try:
        data = json.loads(data)
    except ValueError:
        data = data.decode()
    return result.status, data

def main():
    for _ in range(60):
        try:
            if call("GET", "/health-check")[0] == 200:
                break
        except OSError:
            pass
        time.sleep(1)
    email = f"acceptance-{uuid.uuid4().hex}@example.com"
    password = "local-test-Password123!"
    status, account = call("POST", "/accounts", {"name": "Acceptance", "email": email, "password": password})
    assert status == 201, (status, account)
    assert "password" not in account
    assert call("POST", "/accounts", {"name": "Duplicate", "email": email.upper(), "password": password})[0] == 409
    # Auth may still be starting after Gateway is reachable.
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
    status, me = call("GET", "/accounts/me", token=session2["access_token"], headers={"X-Account-ID": account["id"]})
    assert status == 200 and me["id"] == account2["id"] != account["id"]
    print("PASS: registration, duplicate email, Java JWT, Go routing, Python identity, two-account isolation, invalid tokens, password rejection and blocked internal route")

if __name__ == "__main__":
    main()
