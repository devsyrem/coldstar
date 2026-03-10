# Coldstar ZK Security Controls

## Overview

This document describes the security controls implemented in the ZK transaction layer.
Each control is mapped to a specific threat and its implementation.

## Control Matrix

### C1: Explicit Mode Selection
- **Threat**: User signs a transaction under unintended privacy level
- **Control**: `ModeSelector` state machine requires explicit `select("public"|"private")` call
- **Enforcement**: No default mode. `UNSELECTED` state blocks all operations.
- **Location**: `src/privacy/mode.py`

### C2: Mode Locking After Proof Generation
- **Threat**: Mode switch after proofs generated (proof/mode mismatch)
- **Control**: `ModeState.LOCKED` — once proofs are generated, mode cannot change
- **Enforcement**: `select()` raises `ValueError` if state is `LOCKED`
- **Location**: `src/privacy/mode.py:ModeSelector.lock()`

### C3: Proof-to-Transaction Binding
- **Threat**: Proofs detached and reused for different transaction
- **Control**: SHA-256 binding hash computed over `tx_context + all_proofs + nonce + timestamp`
- **Enforcement**: Binding verified on offline signer before signing
- **Location**: `src/zk/engine.py:compute_binding()`, `coldstar_zk/src/binding.rs`

### C4: Envelope Integrity (HMAC)
- **Threat**: Envelope modified during USB transfer
- **Control**: HMAC-SHA256 over full envelope contents, domain-separated key
- **Enforcement**: `verify_envelope_integrity()` checked before any signing
- **Location**: `src/zk/engine.py:_compute_envelope_hmac()`, `coldstar_zk/src/envelope.rs`

### C5: Replay Protection
- **Threat**: Previously-signed envelope re-submitted
- **Control**: Unique nonce per transaction, tracked in `_seen_nonces` set
- **Enforcement**: Policy engine rejects duplicate nonces
- **Location**: `src/privacy/policy.py:_check_replay()`, `coldstar_zk/src/policy.rs`

### C6: Transfer Limits
- **Threat**: Excessive transfer amount
- **Control**: Configurable `max_transfer_lamports` in policy engine
- **Enforcement**: Transactions exceeding limit are rejected
- **Location**: `src/privacy/policy.py:_check_amount()`

### C7: Destination Allowlist
- **Threat**: Transfer to unauthorized address
- **Control**: Optional allowlist enforcement via `require_destination_allowlist`
- **Enforcement**: When enabled, only pre-approved destinations accepted
- **Location**: `src/privacy/policy.py:_check_destination()`

### C8: Domain Separation
- **Threat**: Cross-protocol attacks (hash collision between different operations)
- **Control**: Unique domain-prefix bytes for each operation (10 domains)
- **Enforcement**: All hashing operations prepend domain constant
- **Location**: `src/zk/engine.py` (Python), `coldstar_zk/src/domain.rs` (Rust)

### C9: Sensitive Key Zeroization
- **Threat**: Secret key material left in memory after use
- **Control**: `zeroize` crate applied to Rust `Scalar` types
- **Enforcement**: Automatic via `Drop` trait on `Zeroize`-derived types
- **Location**: `coldstar_zk/src/proofs/ownership.rs`, `coldstar_zk/src/proofs/range.rs`

### C10: No Trusted Setup
- **Threat**: Compromised setup ceremony
- **Control**: All proof systems use standard model (no CRS beyond group generators)
- **Enforcement**: Generator H derived via hash-to-point (nothing-up-my-sleeve)
- **Location**: `coldstar_zk/src/commitment.rs:generator_h()`

### C11: Structure Validation
- **Threat**: Malformed envelope accepted
- **Control**: `validate_envelope_structure()` checks mode/proof consistency
- **Enforcement**: Public envelopes must not contain proofs; private must contain them
- **Location**: `src/zk/engine.py:validate_envelope_structure()`

## Threat Model

| Actor | Capability | Mitigation |
|-------|-----------|------------|
| Malicious USB content | Inject/modify envelope | C4 (HMAC), C3 (binding) |
| Replay attacker | Re-submit old envelope | C5 (nonce tracking) |
| Social engineering | Trick user into wrong mode | C1 (explicit selection), C2 (locking) |
| Memory forensics | Read key material from RAM | C9 (zeroization) |
| Protocol confusion | Cross-domain hash attacks | C8 (domain separation) |

## Audit Recommendations

1. **Priority 1**: HMAC key derivation should use a pre-shared secret, not domain constants
2. **Priority 2**: Nonce tracking should be persistent (currently in-memory only)
3. **Priority 3**: Python fallback proofs should be clearly blocked in production builds
4. **Priority 4**: Consider formal verification of Rust proof implementations
5. **Priority 5**: Add timing-attack resistance to Python comparison operations
