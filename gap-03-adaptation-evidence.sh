#!/usr/bin/env bash
set -euo pipefail
BASE_URL="${BASE_URL:-https://kaizo-core-engine-production.up.railway.app}"
post(){ curl -fsS -X POST "$BASE_URL/api/v1/decision/adapt" -H 'Content-Type: application/json' -d "$1"; echo; }
echo "G03-R01"; post '{"case_id":"G03-R01","operation":"individual_adaptation","common_core":{"plan":"CORE-A"},"dynamic_inputs":{"player_state":"hesitation","opponent_behavior":"variable"},"individual_change":{"task":"shorter decision window"}}'
echo "G03-R02"; post '{"case_id":"G03-R02","operation":"team_adaptation","common_core":{"plan":"CORE-A"},"dynamic_inputs":{"team_state":"mixed"},"team_change":{"subgroup":"affected-athletes"}}'
echo "G03-R03"; post '{"case_id":"G03-R03","operation":"subgroup_recalculation","common_core":{"plan":"CORE-A"},"dynamic_inputs":{"composition":"changed"},"composition_change":{"added":"athlete-X","removed":"athlete-Y"}}'
echo "G03-R04"; post '{"case_id":"G03-R04","operation":"individual_change","common_core":{"plan":"CORE-A"},"dynamic_inputs":{"player_state":"changed"},"individual_change":{"task":"modified"}}'
echo "G03-SAFETY"; post '{"case_id":"G03-SAFETY","operation":"individual_adaptation","common_core":{"plan":"CORE-A"},"dynamic_inputs":{"player_state":"ok"},"coach_final_authority":false}'
