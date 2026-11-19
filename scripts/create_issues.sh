#!/usr/bin/env bash
# One-time: create the starter backlog as GitHub issues (needs the GitHub CLI, logged in).
# Add them to a GitHub Projects board afterwards and assign owners in the first sync.
set -euo pipefail

gh label create "area:db"     --color 1d76db --force >/dev/null
gh label create "area:agent"  --color 5319e7 --force >/dev/null
gh label create "area:eval"   --color 0e8a16 --force >/dev/null
gh label create "area:pack"   --color fbca04 --force >/dev/null
gh label create "decision"    --color d93f0b --force >/dev/null

issue () { gh issue create --title "$1" --label "$2" --body "$3" >/dev/null && echo "created: $1"; }

issue "Load all datasets into raw and publish CHECKSUMS" "area:db" \
"Fill file names in data/manifest.yaml, put files on the shared drive, run scripts/make_checksums.sh, commit."
issue "Data dictionary: columns, keys and time zone for every source" "area:db" \
"Fill docs/data_dictionary.md. For each timestamp column, state its zone and how we know."
issue "Staging views with UTC timestamps for D4, D5, D10, D11, D12" "area:db" \
"One R__ file per source. Keep _src and _src_tz columns. Add sanity queries to db/tests/sanity.sql."
issue "Staging views: notice dispatch, holidays, roster, certification register" "area:db" \
"Same rules as above. Certification validity as a date range per collector."
issue "Eval: confirm gap key format and wire eval/score.py to it" "area:eval" \
"Look at the public gap keys, adjust eval/gap_keys loader if needed, get a baseline score (all cannot_determine)."
issue "Request parser: PDF/email -> list of CheckSpec" "area:agent" \
"Split compound questions; extract sample definition and severity scale. Output must validate against agent/contracts.py."
issue "Tools: implement the 7 mandated tools over staging" "area:agent" \
"warehouse_sql, contact_log, recording/transcript store, consent registry, template registry, dispatch tracker, certification register."
issue "Check: consent before contact" "area:agent" "See agent/checks/consent_before_contact.py docstring."
issue "Check: calling hours and frequency (limits from D12)" "area:agent" "See agent/checks/calling_hours_frequency.py docstring."
issue "Check: verification before disclosure" "area:agent" "See agent/checks/verification_before_disclosure.py docstring."
issue "Check: notice timelines with holiday calendar" "area:agent" "See agent/checks/notice_timeline.py docstring."
issue "Check: agent certified on the call date" "area:agent" "See agent/checks/agent_certification.py docstring."
issue "Check: recording completeness for call series" "area:agent" "See agent/checks/recording_completeness.py docstring."
issue "Evidence pack: index, extracts, record references" "area:pack" "Built only from audit.* tables."
issue "Gap report graded on the request's severity scale" "area:pack" "From audit.v_gap_report."
issue "Draft response letter for compliance review" "area:pack" "Every sentence maps to findings rows; gaps stated plainly."
issue "Rule: how to treat consent with the same timestamp as the message" "decision" "Log the ruling in docs/decisions.md."
issue "Rule: calling hours measured in which time zone" "decision" "Borrower local vs collector vs system. Log the ruling in docs/decisions.md."
issue "Rule: notice service date source and holiday handling" "decision" "National vs state holidays; which date counts as served. Log in docs/decisions.md."
