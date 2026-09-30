# KAIZO PACK-C — Numeric Claim Validation
Date: 2026-09-30
Status: GOVERNANCE CONTROL VERIFIED / NUMERIC CLAIM VALIDATION PENDING

## Review Result
PACK-C reviewed the numeric decision claim currently present in the Rule Engine:

- Claim ID: NC-UNDER11-MALE-42KG-GRIP
- Profile: under11 | male | -42kg | grip_strength
- Thresholds present in legacy implementation: excellent 25.0 kg / average 18.0 kg / weak 15.0 kg
- Current validation status: UNVALIDATED
- Evidence level: E0
- Source mapping: none established for the exact profile and threshold set

The values are preserved for provenance/audit only. They are no longer permitted to drive a production decision.

## Evidence Review — Stage 2 Completed
A targeted external evidence search was completed for the exact threshold set and profile.

Sources reviewed included:
- Paediatric dominant and non-dominant handgrip reference curves for males aged 6–19.9 years. The published values are age-based reference percentiles and do not establish the exact KAIZO thresholds 25/18/15 kg for the under-11 male -42 kg judo profile.
- Normative data for handgrip strength in Iranian healthy children/adolescents aged 7–18 years. The data are age/hand based and do not establish the exact KAIZO profile or threshold set.
- Grip/pinch reference values for children/adolescents from India. The study provides age/sex reference data but does not establish the exact KAIZO thresholds.
- Saudi normative values for hand grip/pinch strength for ages 6–18 years. Again, the evidence is age-based and does not establish the exact KAIZO profile/threshold mapping.
- A large child cohort study of grip strength also provides population measurements but does not validate the exact KAIZO threshold set.

Additional judo-specific literature was then searched. A 2024 study of 11–12-year-old judo competitors reported mean dominant-hand grip strength of 21.34 kgf (range 14.20–30.70) and non-dominant 19.81 kgf (range 14.40–28.40). This is relevant domain evidence, but it does not validate the exact 25/18/15 kg thresholds, and its sample is older than the under-11 target. citeturn1search42

A study of adolescent judo athletes reported handgrip strength means around 21.6–28.1 kgf across age/maturity groups, again without establishing the exact KAIZO threshold set or the -42 kg under-11 profile. citeturn1search0

Conclusion of this evidence stage:
NO AUTHORITATIVE EXACT MATCH FOUND.

## Stage 3 — Threshold Plausibility Check
Independent youth-sport data provide a plausibility check but not validation. A U11 male tennis meta-analysis reports dominant-hand grip strength of 21.20 kg (single-study estimate; n=4) and non-dominant 19.20 kg (single-study estimate; n=4), with substantial uncertainty due to the very small sample. citeturn0search0 A youth-soccer study reports U11 grip strength of 17.8 ± 2.6 kg in trial 1 and 17.7 ± 2.9 kg in trial 2. citeturn0search47 Another 10–12-year-old soccer cohort reports U11 mean grip strength 15.3 ± 1.85 kg. citeturn0search3

These findings show that 15–25 kg is within the broad range reported in some U11 youth samples, but they do NOT establish that 15/18/25 kg are appropriate decision thresholds for male U11 judoka in the -42 kg category. Weight-category-specific and judo-specific normative evidence remains missing.

Decision after Stage 3: CLAIM REMAINS UNVALIDATED / NON-FROZEN.

These sources may be retained as contextual evidence, but none is sufficient to promote the 25/18/15 kg thresholds to VALIDATED status. The absence of an exact evidence mapping is therefore preserved as an explicit validation gap rather than being resolved by approximation.

## Runtime Control
Production behavior was changed so an unvalidated numeric claim returns:

HOLD / NUMERIC_CLAIM_VALIDATION_REQUIRED / decision_blocked=true

and records:
NUMERIC_CLAIM_VALIDATION_HOLD

Missing required input continues to return:
HOLD / MISSING_REQUIRED_INPUT

## Independent Production Evidence
GitHub Actions:
- Workflow: PACK-C Numeric Claim Governance Evidence
- Run: 36681091090
- Job: 109776483151
- Result: SUCCESS
- Final assertion: PACK-C PRODUCTION NUMERIC-GOVERNANCE RED TEAM: PASS

Observed production response for actual_value=20:
HOLD / NUMERIC_CLAIM_VALIDATION_REQUIRED
validation_status=UNVALIDATED
evidence_level=E0
decision_blocked=true

## Governance Decision
The safety/governance objective of PACK-C is evidenced: no unvalidated numeric claim can silently become a production decision.

The numeric claim itself has NOT been scientifically/technically validated. It therefore remains non-frozen.

## Closure Gate
PACK-C cannot be marked CLOSED/FROZEN as a validated numeric-claim project until the exact claim receives an authoritative evidence mapping and appropriate validation.

No numeric value is to be promoted merely because a runtime test passes.
No runtime evidence substitutes for source/expert validation.

Rule:
Reuse Before Rebuild -> Verify Before Reuse -> Evidence Before Claim.
