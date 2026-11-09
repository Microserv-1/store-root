"""Validate a real Account container restart without dropping PostgreSQL data."""
import subprocess
import time
import uuid
from smoke import call

credentials = {"email": f"persistence-{uuid.uuid4().hex}@example.com", "password": "test-persistence-Password123!"}
status, account = call("POST", "/accounts", {"name": "Persistence", **credentials})
assert status == 201, account
subprocess.run(["docker", "compose", "restart", "account"], check=True)
for _ in range(30):
    status, result = call("POST", "/auth/login", credentials)
    if status == 200:
        break
    time.sleep(1)
assert status == 200, result
assert call("GET", "/accounts/me", token=result["access_token"]) == (200, account)
print("PASS: persisted account survives container restart and can authenticate again")
