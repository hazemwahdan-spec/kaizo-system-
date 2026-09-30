# KAIZO Wearables — P09

Governed wearable/device observation workspace.

## Boundary
Raw device measurement is kept separate from coach interpretation. This interface does not establish medical findings, injury risk, scientific validity, normative thresholds, rankings, predictions or autonomous coaching decisions.

Demo data is browser-local and non-authoritative.

Separate dependencies: P05 persistence, P13 production RBAC, P14 minor/guardian consent, P15 scalable analytics.

Local run:
python3 -m http.server 8080 --directory wearables