## 001. Grades encrypted at rest via AES-256-GCM

* Status: Accepted
* Date: 2026-07-07

## Context

* Data: Bot stores highly sensitive university passwords and grade data.
* Risk: Plaintext risks total account compromise and privacy violations.
* History: First pass used AES-256-CBC. Rejected because CBC provides confidentiality but lacks integrity validation (vulnerable to bit-flipping attacks).

## Decision
Encrypt all sensitive columns (UserCredential, encrypted_grade, etc.) using AES-256-GCM for authenticated encryption.
## Alternatives Considered

* Plaintext: Rejected. One database leak exposes all credentials.
* AES-256-CBC: Rejected. Lacks integrity checking. Encrypt-then-MAC adds too much manual complexity compared to GCM.
* Deterministic Encryption (AES-SIV): Deferred. Would allow ciphertext comparison for grade changes, but requires further study.

## Consequences & Risks

* Tag Storage: Must decide if the authentication tag is appended to the ciphertext blob or stored in a separate column.
* Crypto Danger: Nonces must never be reused. Must implement a guaranteed fresh random value per encryption call.
* Open Question: The canary scanner must currently decrypt data to detect grade updates. If decryption becomes a bottleneck, create a future ADR to evaluate deterministic encryption.