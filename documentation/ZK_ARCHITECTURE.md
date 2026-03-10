# Coldstar.dev — Zero-Knowledge Proof Transaction Layer Architecture

**Version**: 0.1.0 (MVP)  
**Date**: 2026-03-10  
**Status**: Implementation Draft

---

## 1. Problem Statement

Coldstar.dev is a CLI-first Solana cold wallet that turns USB drives into offline signing devices. Today, all transactions are fully public: sender, receiver, amount, and intent are visible on-chain and in the transaction artifact itself.

Many operators need the ability to sign transactions where certain properties (ownership, policy compliance, transfer bounds) can be proven without exposing all metadata. This is critical for:

- **Treasury operations** where exact amounts should not be visible to all staff
- **DAO governance** where voting authority must be proven without key exposure
- **Compliance workflows** where policy adherence must be provable without revealing internal limits
- **Operational security** where signing authority must be demonstrated selectively

## 2. Why Coldstar Needs Both Public and Private Transaction Modes

**Public mode** is the default. It is fast, simple, and fully compatible with the Solana ecosystem. Most transactions should use public mode.

**Private mode** exists for transactions where the operator wants to prove correctness—ownership, policy compliance, amount bounds—without revealing unnecessary internal metadata. Private mode adds a zero-knowledge proof layer before signing.

The two modes must coexist cleanly. The user explicitly selects the mode before signing. There is no automatic switching, no silent upgrade, and no ambiguity.

## 3. Threat Model

### What we defend against:

| Threat | Mitigation |
|--------|-----------|
| Unauthorized signing | Offline signer requires proof + policy checks before signing |
| Mode confusion (private tx signed as public) | Mode is cryptographically bound to transaction context |
| Proof reuse across transactions | Proofs are bound to transaction hash + nonce |
| Replay attacks | Domain separation + fresh nonce per proof |
| Metadata leakage in private mode | Proofs reveal only what is explicitly disclosed |
| Tampered transfer envelope | Envelope integrity protected by HMAC |
| Signing without proof in private mode | Signer rejects private transactions missing valid proofs |

### What we do NOT defend against (out of scope for MVP):

| Non-goal | Reason |
|----------|--------|
| On-chain transaction privacy | Solana is a transparent ledger; sender/receiver/amount are visible on-chain |
| MEV protection | Requires protocol-level changes beyond wallet scope |
| Network-layer anonymity | Requires Tor/mixnet integration, out of scope |
| Fully private transfers hiding on-chain amounts | Not possible on Solana L1 without protocol extensions |
| Trusted setup ceremonies | MVP uses proof systems that require no trusted setup |

## 4. Privacy Goals

### MVP Goals:
1. **Prove wallet ownership** without exposing the private key or signing material beyond what is necessary
2. **Prove transfer amount is within policy bounds** without revealing the exact policy limits or internal metadata
3. **Prove transaction satisfies policy constraints** without revealing policy details
4. **Bind proofs to specific transaction intent** so proofs cannot be repurposed
5. **Enable offline proof verification** on the USB signer before signing

### Non-Goals for MVP:
- On-chain privacy (Solana does not support this natively)
- Hiding sender/receiver addresses on-chain
- Confidential token transfers
- Fully homomorphic computation over transactions

## 5. Trust Assumptions

1. The offline USB signer is physically secure and not compromised
2. The Rust cryptographic libraries (curve25519-dalek, ed25519-dalek) are correct
3. The random number generator (OS-provided via OsRng) is cryptographically secure
4. The user's password for key decryption is strong
5. The transfer medium (USB drive) between online and offline machines may be observed but not silently modified (integrity is checked)
6. The online machine may be compromised — proofs must be verifiable independently on the offline signer

## 6. System Components

```
┌─────────────────────────────────────────────────────────┐
│                    ONLINE MACHINE                        │
│                                                         │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │   CLI    │──│ Mode Selector │──│ TX Builder       │  │
│  │ coldstar │  │ public/private│  │ (Solana SDK)     │  │
│  └──────────┘  └──────┬───────┘  └────────┬─────────┘  │
│                       │                    │             │
│              ┌────────┴────────┐           │             │
│              │                 │           │             │
│         ┌────▼─────┐   ┌──────▼──────┐    │             │
│         │ Public   │   │ Private     │    │             │
│         │ Path     │   │ Path        │    │             │
│         │ (no ZK)  │   │ (ZK proofs) │    │             │
│         └────┬─────┘   └──────┬──────┘    │             │
│              │                │            │             │
│              └────────┬───────┘            │             │
│                       │                    │             │
│              ┌────────▼────────────────────▼──┐         │
│              │    Transfer Envelope Builder    │         │
│              │ (transaction + mode + proofs)   │         │
│              └────────────────┬────────────────┘         │
│                               │                          │
└───────────────────────────────┼──────────────────────────┘
                                │ USB Transfer
┌───────────────────────────────┼──────────────────────────┐
│                    OFFLINE USB SIGNER                     │
│                               │                          │
│              ┌────────────────▼────────────────┐         │
│              │    Envelope Validator            │         │
│              │ (integrity + mode check)         │         │
│              └────────────────┬────────────────┘         │
│                               │                          │
│              ┌────────┬───────┘                          │
│              │        │                                  │
│         ┌────▼─────┐  ┌──────▼──────┐                   │
│         │ Public   │  │ Private     │                   │
│         │ Policy   │  │ Policy +    │                   │
│         │ Check    │  │ Proof Check │                   │
│         └────┬─────┘  └──────┬──────┘                   │
│              │               │                           │
│              └───────┬───────┘                           │
│                      │                                   │
│              ┌───────▼───────┐                           │
│              │ Human-Readable│                           │
│              │ Summary       │                           │
│              │ (dest, amount,│                           │
│              │  mode, fees,  │                           │
│              │  proof status)│                           │
│              └───────┬───────┘                           │
│                      │ User confirms                     │
│              ┌───────▼───────┐                           │
│              │  Rust Secure  │                           │
│              │  Signer       │                           │
│              │  (ed25519)    │                           │
│              └───────┬───────┘                           │
│                      │                                   │
│              ┌───────▼───────┐                           │
│              │ Signed Artifact│                          │
│              │ (tx + proofs) │                           │
│              └───────────────┘                           │
└──────────────────────────────────────────────────────────┘
```

## 7. Public Transaction Flow

1. User runs `coldstar tx create --mode public`
2. CLI builds unsigned Solana transaction (standard Coldstar flow)
3. Standard policy checks run (address validation, amount validation, fee calculation)
4. Transfer envelope is created with `mode: "public"`, transaction bytes, no proof artifacts
5. Envelope is written to USB drive inbox
6. Offline signer reads envelope, verifies mode is `public`
7. Standard policy checks run on signer
8. Human-readable summary displayed: destination, amount, fees, mode=PUBLIC
9. User confirms
10. Rust secure signer signs transaction (standard Ed25519)
11. Signed transaction written to USB drive outbox
12. Online machine reads signed transaction for broadcast

## 8. Private Transaction Flow

1. User runs `coldstar tx create --mode private`
2. CLI builds unsigned Solana transaction
3. CLI enters ZK proof pipeline:
   a. **Ownership proof**: Schnorr NIZK proving control of the signing key
   b. **Range proof**: Proving transfer amount is within allowed bounds (e.g., [0, max_allowed])
   c. **Policy proof**: Proving transaction satisfies policy constraints
4. Proofs are bound to transaction intent via domain-separated hash
5. Transfer envelope is created with `mode: "private"`, transaction bytes, proof bundle, binding
6. Envelope integrity is protected with HMAC
7. Envelope is written to USB drive inbox
8. Offline signer reads envelope, verifies mode is `private`
9. Signer verifies:
   a. Envelope integrity (HMAC)
   b. All required proofs are present
   c. Each proof is valid
   d. Proofs are correctly bound to the transaction
   e. Policy compliance checks pass
   f. No proof reuse (nonce freshness)
10. Human-readable summary displayed: destination, amount, fees, mode=PRIVATE, proof verification=PASSED
11. User confirms
12. Rust secure signer signs transaction
13. Signed artifact (transaction + proof bundle) written to USB drive outbox

## 9. Data Flow

### Transfer Envelope Format (JSON)

```json
{
  "version": "1.0.0",
  "mode": "public" | "private",
  "created_at": "ISO-8601 timestamp",
  "transaction": {
    "unsigned_bytes": "base64-encoded unsigned transaction",
    "from_pubkey": "base58 public key",
    "to_pubkey": "base58 public key",
    "amount_lamports": 1000000000,
    "fee_lamports": 5000,
    "recent_blockhash": "base58 blockhash"
  },
  "proof_bundle": {            // Only present in private mode
    "ownership_proof": { ... },
    "range_proof": { ... },
    "policy_proof": { ... },
    "binding": "hex-encoded binding hash",
    "nonce": "hex-encoded 32-byte nonce"
  },
  "integrity": "hex-encoded HMAC-SHA256"
}
```

## 10. Cryptographic Choices

### Proof Systems

| Component | System | Rationale |
|-----------|--------|-----------|
| Wallet ownership proof | Schnorr NIZK (Fiat-Shamir on Ristretto) | Simple, efficient, no trusted setup, uses same curve as Ed25519 |
| Amount range proof | Bit-decomposition with Sigma OR-proofs | Real ZK range proof, no trusted setup, O(n) proof size where n = bit width |
| Policy compliance proof | Hash-based commitment with Schnorr proof | Proves knowledge of policy satisfaction without revealing policy |
| Proof binding | SHA-256 domain-separated hash | Binds proofs to transaction intent, prevents repurposing |
| Envelope integrity | HMAC-SHA-256 | Detects tampering in transit |

### Why These Choices?

**Schnorr NIZK over zk-SNARKs**: zk-SNARKs (Groth16) require a trusted setup ceremony that is inappropriate for an MVP cold wallet. Schnorr proofs are simpler, well-audited, and sufficient for wallet-level proofs.

**Bit-decomposition over Bulletproofs**: Bulletproofs would give O(log n) proof size but require a complex implementation. Bit-decomposition gives O(n) proofs but is easier to implement correctly and audit. For 64-bit values, proof size is ~4KB — acceptable for USB transfer.

**Ristretto over raw Ed25519 points**: Ristretto eliminates cofactor issues and provides a prime-order group, making proof construction simpler and safer.

**No trusted setup**: All proof systems used require no trusted setup, eliminating a major operational and security burden.

### Libraries

| Library | Version | Purpose |
|---------|---------|---------|
| `curve25519-dalek` | 4.x | Ristretto group operations, scalar arithmetic |
| `ed25519-dalek` | 2.1 | Ed25519 signing (existing dependency) |
| `sha2` | 0.10 | SHA-256/SHA-512 for hashing |
| `rand` / `rand_core` | 0.8 / 0.6 | Cryptographic random number generation |
| `zeroize` | 1.7 | Secure memory cleanup |
| `serde` / `serde_json` | 1.0 | Serialization |

## 11. Solana Integration Strategy

### What happens on-chain:
- Standard Solana transaction (transfer, program call, etc.)
- Transaction is fully public on-chain (Solana limitation)

### What happens off-chain:
- ZK proof generation (on online machine)
- ZK proof verification (on offline signer)
- Proof binding to transaction
- Policy compliance checking

### Hybrid verification path (future):
- Deploy a Solana program that verifies ZK proofs on-chain
- Anchor proof verification to transaction via memo or custom instruction
- Enable third-party verification of proof-gated transactions

### MVP approach:
- All proofs are generated and verified off-chain
- Proofs accompany the transaction as metadata
- The offline signer is the trust anchor for verification
- On-chain, the transaction appears as a normal Solana transaction

## 12. Verification Model

### Off-chain (MVP):
- Proof generation: Online machine
- Proof verification: Offline USB signer
- Trust anchor: Physical possession of USB signer

### Why not on-chain verification for MVP:
1. Solana compute budget limits make complex proof verification expensive
2. No standard for on-chain ZK verification on Solana (unlike Ethereum's precompiles)
3. Cold wallet use case benefits from offline verification (air-gapped security)
4. On-chain verification can be added later without changing the proof format

## 13. Limitations of MVP

1. **No on-chain privacy**: Solana transactions are public. The ZK proofs protect metadata in the signing pipeline, not on-chain.
2. **Range proofs are O(n)**: Not as efficient as Bulletproofs. Acceptable for USB transfer but not for on-chain verification.
3. **No confidential tokens**: True confidential transfers require protocol-level support (e.g., SPL Confidential Transfer extension). Not in MVP scope.
4. **Single signer only**: Multi-party proofs and threshold signing are future work.
5. **No on-chain proof anchoring**: Proofs are not recorded on-chain in the MVP.
6. **Policy proofs are simplified**: MVP proves policy satisfaction via hash commitments, not arbitrary policy circuits.

## 14. Roadmap for Production

### Phase 1 (MVP — Current):
- [x] Transaction mode selector (public/private)
- [x] Schnorr NIZK ownership proof
- [x] Bit-decomposition range proof
- [x] Policy compliance proof
- [x] Proof-to-transaction binding
- [x] Transfer envelope format
- [x] Offline signer verification
- [x] CLI commands

### Phase 2:
- [ ] Bulletproofs for efficient range proofs
- [ ] SPL Confidential Transfer integration
- [ ] On-chain proof anchoring via Solana program
- [ ] Multi-party proof generation

### Phase 3:
- [ ] Selective disclosure framework
- [ ] DAO treasury approval proofs
- [ ] Compliance proof generation for regulated entities
- [ ] Cross-chain proof portability

### Phase 4:
- [ ] Full zk-SNARK circuits for complex policy proofs
- [ ] Recursive proof composition
- [ ] Privacy-preserving audit trail
- [ ] Hardware security module (HSM) integration for proof generation
