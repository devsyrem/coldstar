# Coldstar ZK Transaction Layer

## Overview

The ZK Transaction Layer adds a **zero-knowledge proof pipeline** to Coldstar's cold wallet signing flow. Before every transaction is signed, the user explicitly chooses between:

1. **Public** — Standard Solana transfer (no proofs, fastest path)
2. **Private** — ZK-proof-protected signing pipeline (Schnorr ownership, range proofs, policy compliance, HMAC integrity)

> **Important**: Solana transactions are public on-chain. The ZK proofs protect **metadata in the signing pipeline** (online machine → USB → offline signer), not on-chain visibility. This is an engineering-honest limitation documented throughout.

## Architecture

```
┌────────────────────┐     USB (JSON)     ┌─────────────────────┐
│   Online Machine   │ ─────────────────► │   Offline Signer    │
│                    │                     │                     │
│  Mode Selection    │                     │  Verify Integrity   │
│  Proof Generation  │                     │  Verify Proofs      │
│  Envelope Build    │                     │  Policy Check       │
│  HMAC Seal         │                     │  Sign (if approved) │
└────────────────────┘                     └─────────────────────┘
```

### Components

| Component | Language | Location | Purpose |
|-----------|----------|----------|---------|
| `coldstar_zk` | Rust | `coldstar_zk/` | Core ZK proofs (Ristretto, Schnorr, range proofs) |
| `src/zk/types.py` | Python | `src/zk/` | Type definitions (dataclasses mirroring Rust) |
| `src/zk/engine.py` | Python | `src/zk/` | Proof engine (Rust FFI + Python fallback) |
| `src/privacy/mode.py` | Python | `src/privacy/` | Mode selector state machine |
| `src/privacy/policy.py` | Python | `src/privacy/` | Signing policy engine |
| `src/privacy/validator.py` | Python | `src/privacy/` | Top-level validation orchestrator |
| `coldstar_cli.py` | Python | root | CLI commands (`tx create`, `zk prove`, etc.) |

## Proof Systems

### Ownership Proof (Schnorr NIZK)
Proves the signer holds the private key for the declared public key without revealing the key.

- **Protocol**: Sigma protocol with Fiat-Shamir transform
- **Group**: Ristretto255 (prime-order group on Curve25519, no cofactor issues)
- **Soundness**: Computational, under discrete-log assumption

### Range Proof (Bit Decomposition + CDS OR-Proofs)
Proves the transfer amount lies in `[0, 2^64)` without revealing the amount.

- **Technique**: Decompose value into bits, prove each bit ∈ {0,1} with Sigma OR-proofs (CDS technique)
- **Commitments**: Pedersen (`v·G + r·H`) with nothing-up-my-sleeve `H`
- **Consistency**: Sum of bit commitments equals total commitment

### Policy Proof
Proves the transaction satisfies policy constraints (transfer limits, destination allowlists).

- **Technique**: Hash-commitment with Schnorr proof of knowledge

### Proof Binding
Cryptographic binding tying all proofs to a specific transaction via SHA-256.

### Envelope Integrity
HMAC-SHA256 over the entire transfer envelope, domain-separated.

## CLI Usage

### Check ZK status
```bash
python3 coldstar_cli.py zk init
```

### Create a public transaction
```bash
python3 coldstar_cli.py tx create \
  --mode public \
  --from-pubkey <sender> \
  --to-pubkey <recipient> \
  --amount-lamports 1000000000
```

### Create a private transaction
```bash
python3 coldstar_cli.py tx create \
  --mode private \
  --from-pubkey <sender> \
  --to-pubkey <recipient> \
  --amount-lamports 1000000000 \
  --secret-key-hex <32-byte-hex>
```

### Generate standalone proofs
```bash
python3 coldstar_cli.py zk prove \
  --from-pubkey <sender> \
  --to-pubkey <recipient> \
  --amount-lamports 1000000000 \
  --secret-key-hex <32-byte-hex> \
  --output proofs.json
```

### Verify an envelope
```bash
python3 coldstar_cli.py zk verify --envelope-file envelope.json
```

### Interactive guided flow
```bash
python3 coldstar_cli.py tx guided
```

### Export / Import envelopes (for USB transfer)
```bash
python3 coldstar_cli.py tx export --output /usb/envelope.json
python3 coldstar_cli.py tx import --input /usb/envelope.json
```

## Transaction Flow

### Public Mode
```
1. User selects "public" mode
2. TransactionContext is created with mode=PUBLIC
3. Envelope is built (no proofs, HMAC integrity)
4. Policy checks run (amount limits, destination allowlist, replay)
5. If approved → ready for signing
```

### Private Mode
```
1. User selects "private" mode
2. TransactionContext is created with mode=PRIVATE
3. ZK proofs are generated:
   a. Ownership proof (Schnorr NIZK)
   b. Range proof (64-bit decomposition)
   c. Policy proofs (optional, per-constraint)
4. Binding hash computed over tx + proofs
5. Private envelope built with HMAC integrity
6. Mode locked (cannot switch after proofs generated)
7. Full validation: integrity + structure + policy + proofs + binding
8. If approved → ready for signing
```

## Security Properties

| Property | Mechanism | Status |
|----------|-----------|--------|
| Explicit mode selection | ModeSelector state machine | ✓ Implemented |
| Mode locking after proofs | ModeState.LOCKED | ✓ Implemented |
| Proof-to-transaction binding | SHA-256 binding hash | ✓ Implemented |
| Envelope integrity | HMAC-SHA256 | ✓ Implemented |
| Replay protection | Nonce tracking (per-engine) | ✓ Implemented |
| Domain separation | Constant byte prefixes | ✓ Implemented |
| Sensitive data zeroization | `zeroize` crate (Rust) | ✓ Implemented |
| No trusted setup | All proofs use standard model | ✓ By design |

## Testing

### Rust tests (47 tests)
```bash
cd coldstar_zk && cargo test
```

### Python tests (61 tests)
```bash
python3 -m pytest tests/ -v
```

Test suites:
- `test_zk_types.py` — Type serialization roundtrips
- `test_transaction_mode.py` — Mode selector state machine
- `test_policy.py` — Policy engine (limits, replay, allowlists)
- `test_zk_proofs.py` — Proof generation/verification, envelopes
- `test_roundtrip.py` — Full online→offline roundtrip, validator flows

## MVP Limitations (Documented Honestly)

1. **No on-chain privacy**: Solana transactions are public. ZK proofs protect the signing pipeline only.
2. **Python fallback**: Hash-based proofs when Rust library is unavailable. Structurally correct but not cryptographically equivalent.
3. **HMAC key derivation**: MVP derives HMAC key from domain constants. Production should use a pre-shared secret.
4. **Nonce storage**: In-memory only. Production needs persistent nonce tracking.
5. **No Bulletproofs**: Uses bit-decomposition (O(n) proof size). Production should upgrade to Bulletproofs for O(log n).
6. **CLI-based SPL confidential transfers**: Uses `spl-token` CLI subprocess calls. Future versions will build Token-2022 instructions natively for cold-wallet flow.

## Roadmap

| Phase | Focus | Status |
|-------|-------|--------|
| 1 | Core ZK engine + mode system | ✓ Complete |
| 2 | CLI integration + tests | ✓ Complete |
| 3 | SPL Token-2022 confidential transfers | ✓ Complete |
| 4 | Bulletproofs, persistent nonce store | Planned |
| 5 | Native Token-2022 instruction building, multi-sig | Planned |

## SPL Token Confidential Transfers

### Overview
Coldstar supports **SPL Token-2022 Confidential Transfers**, enabling privacy-preserving
token transfers on Solana. Transfer amounts are ElGamal-encrypted on-chain with ZK proofs
for validity.

### How It Works
```
┌─────────────────────┐    Token-2022 Program    ┌─────────────────────┐
│  Public Balance      │ ──── deposit ─────────► │  Confidential Bal.  │
│  (visible on-chain)  │                          │  (ElGamal encrypted)│
│                      │ ◄─── withdraw ────────  │                     │
└─────────────────────┘                          └─────────────────────┘
                                                          │
                                              confidential transfer
                                              (amount hidden, ZK proofs)
                                                          │
                                                          ▼
                                                 ┌─────────────────┐
                                                 │  Recipient       │
                                                 │  Pending Balance │
                                                 └─────────────────┘
```

### What's Hidden vs. Visible
| Data | On-Chain Visibility |
|------|--------------------|
| Transfer amount | **Encrypted** (ElGamal) |
| Sender address | Visible |
| Recipient address | Visible |
| Token mint | Visible |
| Transaction signature | Visible |

### Supported Tokens
Any SPL token using the **Token-2022** program with the confidential transfer extension
enabled. This includes tokens you create and any Token-2022 tokens that opt-in to
confidential transfers.

> **Note:** Native SOL cannot use confidential transfers — only SPL tokens on Token-2022.

### Quick Start
```bash
# Check prerequisites
python3 test_confidential_transfer.py --check-only

# Full test: create mint → configure → deposit → withdraw
python3 test_confidential_transfer.py --supply 1000

# Python API usage
from src.privacy.confidential_transfer import ConfidentialTransferManager

mgr = ConfidentialTransferManager(
    keypair_path="~/.config/solana/id.json"
)

# One-shot setup: mint + account + configure + fund
result = mgr.setup_confidential_token(decimals=6, initial_supply=1000)

# Deposit to confidential balance
mgr.deposit_to_confidential(result["mint"], 500)

# Confidential transfer (amount hidden on-chain)
mgr.confidential_transfer(result["mint"], 100, "<recipient_pubkey>")

# Recipient applies pending balance
mgr.apply_pending_balance()

# Withdraw back to public balance
mgr.withdraw_from_confidential(result["mint"], 200)
```

### ZK Proofs Generated On-Chain
The Token-2022 confidential transfer extension uses three on-chain ZK proofs:

| Proof | Purpose |
|-------|---------|
| **Range Proof** | Transfer amount ∈ [0, 2^64) |
| **Equality Proof** | Sender & recipient ciphertexts encrypt same value |
| **Validity Proof** | Ciphertexts are well-formed ElGamal encryptions |

These proofs are generated automatically by the `spl-token` CLI and verified
by the on-chain Token-2022 program.

## File Structure

```
coldstar_zk/                  # Rust ZK crate
  src/
    lib.rs                    # Library root
    error.rs                  # ZkError enum
    domain.rs                 # Domain separation constants
    types.rs                  # Core types
    transcript.rs             # Fiat-Shamir transcript (SHA-512)
    commitment.rs             # Pedersen commitments (Ristretto)
    proofs/
      ownership.rs            # Schnorr NIZK
      range.rs                # Bit-decomposition range proofs
      policy.rs               # Policy compliance proofs
    binding.rs                # Proof-to-transaction binding
    envelope.rs               # Transfer envelope + HMAC
    policy.rs                 # Signing policy engine
    ffi.rs                    # C FFI for Python

src/zk/                       # Python ZK module
  types.py                    # Dataclass types
  engine.py                   # Proof engine (Rust FFI + fallback)

src/privacy/                  # Python privacy module
  mode.py                     # Mode selector state machine
  policy.py                   # Signing policy engine
  validator.py                # Top-level validator

tests/                        # Python test suite
  test_zk_types.py
  test_transaction_mode.py
  test_policy.py
  test_zk_proofs.py
  test_roundtrip.py

coldstar_cli.py               # CLI entry point
documentation/ZK_ARCHITECTURE.md  # Full architecture document
```
