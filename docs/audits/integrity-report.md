# KAIZO — Integrity & Transfer Manifest

Date: 2026-09-29

## Source-side verified binary fingerprints

### Previously verified finished-project artifacts
| Artifact | SHA-256 | Repository binary status |
|---|---|---|
| KAIZO kumi kata.xlsx | `dac9e996ffa4f8a6246889505e0ea37e3499cb2dfd3d02f6bbf9905ff9f03` | PENDING binary capability |
| KAIZO randori.xlsx | `ac446162f75828dcd0bc33c7e4c93126fff2d41a018b0b1a0ecc272f84def0b1` | PENDING binary capability |
| KAIZO_Historical_Lineage_Near_Semantic_Closure_Package_v1.0.xlsx | `29b669619b30b4af6c4b122b3e26faa2988b6f4d1aff41884eb7f168abd611ca` | PENDING binary capability |
| KAIZO_Historical_Lineage_Near_Semantic_Closure_Package_v1.1.xlsx | `0be2f5ca7c9616be50ceae8fce0f51b428df95235fc130c887f6d339a0003134` | PENDING binary capability |

### Current high-confidence binary evidence set inspected in this execution
| Artifact | Source SHA-256 | Repository binary status |
|---|---|---|
| KAIZO_C04_Canonicalization_Layer_v1.xlsx | `35b4e9ee3f397e4d4f3e003fd3dde876929cf0a277740f52cd00272bc7de753b` | PENDING binary capability |
| KAIZO_K13_FINAL_CLOSURE_PACK_v1.1.xlsx | `f555d64c78120ddb32b26b16e2e63cbc18fb964127868928138eab97a221b4ad` | PENDING binary capability |
| KAIZO_K13_RUNTIME_EVIDENCE_PACK_v1.0.xlsx | `ec745be0556e916a5b4fd57b76cb3bdaccb54c752abc6c72451c0844f115b780` | PENDING binary capability |
| KAIZO_K16_RUNTIME_EXECUTION_EVIDENCE_v1.0.xlsx | `b1bb1a6f67ce34826553b1574d833a1854fb0f7f4c01779b14773058558b94d5` | PENDING binary capability |
| KAIZO_K17_E6_CANONICAL_RUNTIME_EVIDENCE_v1.0.xlsx | `9d165af910829ff8a916c5a118dac3dbf20962e867bf5f7c269cd34b4d34d130` | PENDING binary capability |

## Integrity rule

A binary artifact is considered **TRANSFERRED** only when the exact bytes are present in GitHub and the post-transfer SHA-256 equals the source SHA-256.

No such binary acceptance is claimed in this execution.

## Text artifacts

Verified source text artifacts have been copied as UTF-8 GitHub files without binary conversion or content reconstruction.

## Safety

No destructive source move was performed. No original Library artifact was deleted or overwritten.

## Final binary gate

**BLOCKED BY TOOL CAPABILITY — NOT BY KAIZO GOVERNANCE**

The available GitHub connector can create UTF-8 files and Git objects, but does not expose a safe direct local-binary upload operation. Therefore XLSX/PDF/DOCX/ZIP binaries remain in Library and are represented in GitHub by audit/integrity metadata only until a binary-capable transfer path exists.
