#!/usr/bin/env bash
set -euo pipefail
BASE="https://kaizo-core-engine-production.up.railway.app"
echo "A0 $(curl -sS -o /tmp/health -w "%{http_code}" "$BASE/api/v1/health")"
echo "A3 $(curl -sS -o /tmp/a3 -w "%{http_code}" -X POST "$BASE/api/v1/rules/evaluate" -H "Content-Type: application/json" -d '{"athlete_id":"PACK-A-CONTROL-001","age_group":"under11","gender":"male","weight_category":"-42kg","metric_name":"grip_strength","actual_value":18.0}')"
cat /tmp/a3
echo
echo "A5 $(curl -sS -o /tmp/a5 -w "%{http_code}" -X POST "$BASE/api/v1/knowledge/ingest" -H "Content-Type: application/json" -d '{"item_id":"PACK-A-INTERVENTION-001","domain":"Evidence","title":"PACK-A intervention evidence","content":{"decision":"Average","recommendation":"Grip Endurance Protocol A (SOL-000032)"},"user_id":"PACK-A-EVIDENCE"}')"
cat /tmp/a5
echo
echo "A6 $(curl -sS -o /tmp/a6 -w "%{http_code}" -X POST "$BASE/api/v1/rules/evaluate" -H "Content-Type: application/json" -d '{"athlete_id":"PACK-A-RETEST-001","age_group":"under11","gender":"male","weight_category":"-42kg","metric_name":"grip_strength","actual_value":18.0}')"
cat /tmp/a6
echo
echo "A7 $(curl -sS -o /tmp/a7 -w "%{http_code}" "$BASE/api/v1/audit/logs")"
cat /tmp/a7
