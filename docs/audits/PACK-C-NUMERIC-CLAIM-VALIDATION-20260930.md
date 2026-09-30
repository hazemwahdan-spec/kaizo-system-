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

## Stage 4 — Judo-/Weight-Class-Specific Evidence Gate
A targeted search was performed for judo-specific handgrip norms and for evidence stratified by youth age, sex, and body-weight class.

Relevant evidence found:
- A peer-reviewed study provides normative handgrip reference values for 137 youth judokas, but its participants were under-18 and under-21; it does not provide the exact U11 male -42 kg threshold set. citeturn0search0
- A study of 11–12-year-old judo competitors reports dominant-hand mean 21.34 kgf (range 14.20–30.70) and non-dominant mean 19.81 kgf (range 14.40–28.40), including relative-to-body-mass values. This is the closest judo-specific age evidence located, but it still does not establish the 25/18/15 kg thresholds or the -42 kg category mapping. citeturn0search3
- A large child normative dataset reports boys aged 10–11 with dominant-hand mean 13.4 kg and non-dominant mean 13.1 kg, while emphasizing age/sex rather than judo weight class. citeturn0search1
- A 2025 child cohort reports boys aged 10–11 mean maximum grip strength 16.66 ± 4.17 kg, again without judo-specific weight-class stratification. citeturn0search2

Evidence-gate result:
NO SOURCE LOCATED establishes the exact combination:
U11 + male + judo + -42 kg + grip-strength metric + thresholds 15/18/25 kg.

Therefore the exact numeric claim cannot be validated from the located literature.

### Stage 4 Decision
- Claim status: UNVALIDATED
- Evidence level: E0
- Production decision use: BLOCKED
- Threshold values: PRESERVED FOR PROVENANCE ONLY
- Numeric claim: NON-FROZEN
- Governance control: VERIFIED

No threshold substitution, averaging, interpolation, percentile conversion, or expert-style inference is permitted as a replacement for missing authoritative evidence.

## Stage 5 — KAIZO Provenance Recovery
A dedicated provenance-recovery pass was performed against the KAIZO Library and the historical KAIZO source set, using exact-value and semantic searches for:

- 25.0 / 18.0 / 15.0
- 25 / 18 / 15 with grip strength terminology
- under11 / male / -42kg / grip_strength
- قوة القبضة / Handgrip / grip-strength
- the claim identity NC-UNDER11-MALE-42KG-GRIP

### KAIZO source findings
1. **Legacy Core Engine implementation**
   The exact 25.0 / 18.0 / 15.0 values are present in the legacy `NORMATIVE_STANDARDS` implementation for:
   `under11 | male | -42kg | grip_strength`.
   This establishes implementation provenance, but not scientific/source provenance. The associated developer-handover material is an implementation proposal/working asset and does not contain an authoritative citation mapping these exact thresholds to a source.

2. **KAIZO Library — "اختبار قبضة اليد.docx"**
   This KAIZO source explains maximal isometric handgrip testing and cites relevant judo research. It states that classificatory tables exist for different age groups, sexes and weight categories, but the document's cited classifications concern judo-specific tests and adult/cadet/junior populations; the document does not establish the exact 25/18/15 kg thresholds for an under-11 male -42 kg profile. Its references include Agostinho et al. (2018), Branco et al. (2017), Franchini et al. (2011), Franchini et al. (2018), and Franchini et al. (2020). fileciteturn264file3L78-L94

3. **KAIZO Library — Franchini/Miarka judo grip-strength literature**
   The KAIZO Library contains the 2011 judo grip-strength study by Franchini et al. Its sample is adult male judo athletes with long training histories, and its focus is judogi grip-strength endurance rather than an under-11 -42 kg handgrip threshold set. Therefore it cannot serve as the exact provenance source for 25/18/15 kg. fileciteturn264file0

4. **KAIZO normative-matrix artifact**
   The KAIZO Library also contains a normative-score matrix with grip-related measures, including adult elite handgrip values and a Kumi-kata time measure. These are different constructs/populations and do not establish the target 25/18/15 kg thresholds for U11 male -42 kg grip strength.

### Provenance Recovery Result
The provenance search located the **originating implementation values**, but did **not** locate an authoritative upstream source from which the exact 25/18/15 kg thresholds can be demonstrated to have been derived.

Therefore:

- Implementation provenance: FOUND
- Scientific/source provenance: NOT FOUND
- Exact source-to-claim mapping: NOT FOUND
- Claim status: UNVALIDATED
- Evidence level: E0
- Production decision use: BLOCKED
- Threshold values: PRESERVED FOR PROVENANCE ONLY
- Numeric claim: NON-FROZEN
- Governance control: VERIFIED

### Stage 5 Decision
Stage 5 is COMPLETE.

The claim must **not** be promoted, recalibrated, interpolated, or replaced using adjacent studies. The next validation path, if pursued, must obtain a source or expert-approved normative dataset that explicitly supports the exact population, metric, units, and threshold semantics.

No Core Engine rebuild.
No reopening of K14/K15/K16/K17.
No replacement of the missing evidence with inferred values.

Rule:
Reuse Before Rebuild -> Verify Before Reuse -> Evidence Before Claim.
