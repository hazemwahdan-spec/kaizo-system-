# KAIZO P14 — Minor/Child Data & Consent Layer

Reference implementation for a separate consent gate above the frozen Core.

P14 is intentionally distinct from P13 RBAC: role authorization does not itself establish guardian consent. Access is denied by default and requires an active, unexpired consent matching child, guardian, academy, resource and action.

This demo keeps state in memory for runtime verification only. It is not production persistence and does not constitute legal/privacy compliance certification.
