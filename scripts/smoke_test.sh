#!/usr/bin/env bash
# End-to-end smoke test against a running stack (docker compose up).
# Usage: BASE=http://localhost:8080 ./scripts/smoke_test.sh
set -euo pipefail
BASE="${BASE:-http://localhost:8080}"
j() { python3 -c "import sys,json;d=json.load(sys.stdin);print($1)"; }

echo "==> Waiting for $BASE/api/health"
for i in $(seq 1 60); do
  if curl -fsS "$BASE/api/health" >/dev/null 2>&1; then break; fi
  sleep 2
done
curl -fsS "$BASE/api/health" | tee /dev/stderr | j 'd["status"]' | grep -q ok
echo; echo "==> Frontend served"
curl -fsS "$BASE/" | grep -q "RaktaSetu"

echo "==> OTP login (demo mode)"
OTP=$(curl -fsS -X POST "$BASE/api/auth/request-otp" -H 'content-type: application/json' -d '{"phone":"9876500001"}' | j 'd["demo_otp"]')
TOKEN=$(curl -fsS -X POST "$BASE/api/auth/verify-otp" -H 'content-type: application/json' -d "{\"phone\":\"9876500001\",\"otp\":\"$OTP\"}" | j 'd["token"]')

echo "==> Create an emergency blood request"
RID=$(curl -fsS -X POST "$BASE/api/requests" -H "authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"blood_group":"O+","units":2,"hospital":"Victoria Hospital","lat":12.9634,"lon":77.5737,"urgency":"critical","patient_name":"Smoke Test"}' | j 'd["id"]')
echo "request id: $RID"

echo "==> Verify ML-ranked donors were alerted"
N=$(curl -fsS "$BASE/api/requests/$RID" -H "authorization: Bearer $TOKEN" | j 'len(d["matches"])')
echo "donors alerted: $N"; test "$N" -gt 0

echo "==> Multilingual assistant (Kannada)"
curl -fsS -X POST "$BASE/api/voice/turn" -H 'content-type: application/json' -d '{"lang":"kn","text":"__start__"}' | j 'd["reply"]'

echo "==> ML service via backend"
curl -fsS "$BASE/api/health" | j 'd["ml_service"]' | grep -q True
echo "SMOKE TEST PASSED"
