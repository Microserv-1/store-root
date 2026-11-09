"""Delete a single Account pod only in the named local Kind cluster and verify recovery."""
import json
from pathlib import Path
import subprocess
import time
import uuid
from smoke import call

base = ["kubectl", "--context", "kind-microserv-store", "-n", "store"]
credentials = {"email": f"recovery-{uuid.uuid4().hex}@example.com", "password": "recovery-test-Password123!"}
status, account = call("POST", "/accounts", {"name": "Recovery", **credentials})
assert status == 201, account
status, session = call("POST", "/auth/login", credentials)
assert status == 200, session
before = json.loads(subprocess.check_output(base+["get", "pods", "-l", "app=account", "-o", "json"]))
victim = before["items"][0]["metadata"]["name"]
subprocess.run(base+["delete", "pod", victim, "--wait=false"], check=True)
results = []
for _ in range(30):
    try:
        status, body = call("GET", "/accounts/me", token=session["access_token"])
        results.append(status)
        if status == 200:
            assert body["id"] == account["id"]
    except OSError:
        results.append(0)
    time.sleep(.2)
subprocess.run(base+["rollout", "status", "deployment/account", "--timeout=120s"], check=True)
after = json.loads(subprocess.check_output(base+["get", "pods", "-l", "app=account", "-o", "json"]))
assert victim not in {p["metadata"]["name"] for p in after["items"]}
assert results.count(200) > 0
assert call("GET", "/accounts/me", token=session["access_token"])[0] == 200
report = {"deleted_local_pod":victim,"before":[p["metadata"]["name"] for p in before["items"]],
          "after":[p["metadata"]["name"] for p in after["items"]],"response_statuses":results,
          "note":"Single local pod deletion; not a full availability or multi-AZ test."}
Path("artifacts").mkdir(exist_ok=True)
Path("artifacts/pod-recovery.json").write_text(json.dumps(report,indent=2))
print("PASS: local Account pod replaced, persisted identity remains accessible", results)
